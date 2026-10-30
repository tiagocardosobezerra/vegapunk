#!/usr/bin/env python3
"""
================================================================================
 EDISON — o analisador: sugere conhecimento novo a partir de fontes limpas
================================================================================
Nome: Edison é o satélite do Pensamento, das ideias. Na v3 ele só ANALISA e
SUGERE; quem grava na base é o York. Hoje ele minera candidatos a sinônimo
comparando o vocabulário já indexado do schema (descrições de coluna),
descartando o padrão particípio x agente (`aprovado`/`aprovador`: sentidos
diferentes). Não aplica nada: os pares revisados por humano entram com
`york.py gravar-sinonimos`.

Fase 3 da v3: `sugerir-mapa` cruza o rótulo de cada parâmetro de função
("código do X") com o mapa já compilado e com as descrições de coluna do
schema. Só sugere o que a documentação ou a estrutura provam sozinhas:
- o rótulo diz a mesma entidade de UM cadastro do mapa -> ligar a função a
  esse cadastro;
- nenhum cadastro, mas UMA tabela tem, na PK, a coluna cuja descrição é
  "código do X" -> cadastro novo, com a chave = a PK inteira.
Empate (mais de um cadastro ou de uma tabela) ou falta de evidência: fica de
fora e o parâmetro continua só um rótulo. Nada é gravado: as sugestões
aprovadas pelo usuário entram no mapa.json e o York compila.

Uso:
    python3 satelites/edison.py sugerir-sinonimos [--min-similaridade 0.84] [--min-frequencia 2]
                                                [--limite 30] [--json]
    python3 satelites/edison.py --db outro.db sugerir-sinonimos
    python3 satelites/edison.py --instancia NOME sugerir-sinonimos   # base de egghead-NOME/
    python3 satelites/edison.py sugerir-mapa [--json]
    python3 satelites/edison.py grafo-funcoes [--pacotes DIR] [--minimo N] [--funcao NOME] [--json]
        grafo de coocorrência de funções nas fontes limpas (receitas e exemplos da
        documentação): arestas com o mínimo de exemplos distintos viram
        conhecimento; as outras, sugestão. Só leitura.
    python3 satelites/edison.py tipos-inferidos [--pacotes DIR] [--json]
        tipo de retorno inferido pelo uso nas mesmas fontes limpas (evidência que
        concorda, no mínimo de exemplos); conflito ou abaixo do mínimo é sugestão.
================================================================================
"""

import argparse
import difflib
import json
import os
import sqlite3
import sys
from collections import Counter
from typing import Dict, List, Set

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))   # raiz da skill: pacote `nomi_nomi_no_mi`

if __name__ == '__main__':      # --instancia NOME antes do motor ler a pasta da instância
    from punk_records.instancias import ativar_ou_sair  # noqa: E402
    sys.argv[1:] = ativar_ou_sair(sys.argv[1:])

from nomi_nomi_no_mi import DEFAULT_DB_PATH, normalizar, radical, tokenizar  # noqa: E402


# ==============================================================================
# ITEM 2 — SUGESTÃO AUTOMÁTICA DE SINÔNIMOS (mineração, nunca aplica sozinho)
# ==============================================================================

_SUFIXOS_PARTICIPIO = ('ado', 'ada', 'ido', 'ida')
_SUFIXOS_AGENTE = ('ador', 'adora', 'edor', 'edora', 'idor', 'idora')


def _e_par_participio_agente(t1: str, t2: str) -> bool:
    """Item 4 (auditoria de inovação) — heurística que rejeita
    automaticamente pares tipo 'aprovado'/'aprovador' ou
    'avaliado'/'avaliador': particípio (estado/ação, ex. 'aprovado' =
    status já aprovado) vs. substantivo agente (pessoa/papel, ex.
    'aprovador' = quem aprova) são, em PT-BR, sistematicamente sentidos
    DIFERENTES — não variação ortográfica. Isso apareceu na prática ao
    revisar candidatos reais (empregado/empregador, aprovado/aprovador,
    avaliado/avaliador, trabalhado/trabalhador — todos descartados na
    auditoria manual original); em vez de continuar revisando isso à
    mão pra sempre, o padrão agora é detectado e descartado sozinho."""
    for suf_part in _SUFIXOS_PARTICIPIO:
        for suf_ag in _SUFIXOS_AGENTE:
            if t1.endswith(suf_part) and t2.endswith(suf_ag) and t1[:-len(suf_part)] == t2[:-len(suf_ag)]:
                return True
            if t2.endswith(suf_part) and t1.endswith(suf_ag) and t2[:-len(suf_part)] == t1[:-len(suf_ag)]:
                return True
    return False


def sugerir_sinonimos(db_path: str, min_similaridade: float = 0.84, min_frequencia: int = 2) -> List[Dict]:
    """Minera candidatos a par sinônimo comparando similaridade textual
    (distância de edição via difflib) entre os tokens que já aparecem
    em `colunas.descricao`. NUNCA aplica nada sozinho — só lista
    candidatos para revisão humana, porque falso positivo aqui (dois
    termos parecidos mas com sentido diferente, ex. 'salario'/'saldo')
    contaminaria a busca de forma silenciosa. Isto reduz "escrever
    sinonimos.csv do zero" para "revisar uma lista já pré-populada".

    Descarta automaticamente pares no padrão particípio/agente (ver
    `_e_par_participio_agente`) — um tipo de falso positivo sistemático
    e previsível, não um caso a rejulgar caso a caso.

    Performance: comparar todo par de tokens é O(n²) — medido contra um
    schema real de ~2.100 tabelas, isso levava ~48s. A poda abaixo é
    matematicamente segura (não é heurística aproximada, é uma cota
    superior provada): para dois tokens de tamanho l1<=l2,
    SequenceMatcher.ratio() nunca excede 2*l1/(l1+l2) — se essa cota já
    fica abaixo de `min_similaridade`, o par JAMAIS passaria no filtro
    de qualquer jeito, então nem chega a comparar caractere a caractere.
    Isso corta a maior parte dos pares sem perder nenhum candidato
    legítimo (ex.: 'coligada'/'gcoligada', tamanhos 8/9, continua
    dentro da janela)."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT descricao FROM colunas")
    df = Counter()
    for (desc,) in cur.fetchall():
        for tk in tokenizar(desc or ''):
            df[tk] += 1

    ja_conhecidos: Set = set()
    try:
        cur.execute("SELECT termo, sinonimo FROM sinonimos")
        for termo, sinonimo in cur.fetchall():
            ja_conhecidos.add(frozenset((normalizar(termo), normalizar(sinonimo))))
    except sqlite3.OperationalError:
        pass
    conn.close()

    # ordenado por tamanho (não alfabético) — é o que permite a poda
    # por janela abaixo, via busca binária no tamanho. Empate de tamanho:
    # ordem alfabética, para não depender da ordem do `set` de tokens.
    tokens = sorted((t for t, freq in df.items() if freq >= min_frequencia), key=lambda t: (len(t), t))
    tamanhos = [len(t) for t in tokens]

    # para um token de tamanho l, só tokens com tamanho em
    # [l * s/(2-s), l * (2-s)/s] podem, na teoria, atingir `min_similaridade`
    razao_max = (2 - min_similaridade) / min_similaridade

    candidatos = []
    matcher = difflib.SequenceMatcher()
    n = len(tokens)
    for i, t1 in enumerate(tokens):
        l1 = tamanhos[i]
        limite_superior_tamanho = l1 * razao_max
        # tokens[i+1:] já é maior-ou-igual em tamanho (lista ordenada
        # por len) — para assim que o tamanho ultrapassar a janela,
        # em vez de varrer o resto da lista inteira.
        j = i + 1
        while j < n and tamanhos[j] <= limite_superior_tamanho:
            t2 = tokens[j]
            j += 1
            if radical(t1) == radical(t2):
                continue  # já coberto pelo stemmer leve — não é sinônimo novo
            if frozenset((t1, t2)) in ja_conhecidos:
                continue
            if _e_par_participio_agente(t1, t2):
                continue  # padrão sistemático de sentido diferente (ver docstring)
            # quick_ratio() é uma 2ª cota superior, mais barata que
            # ratio() completo — só paga o cálculo caractere a
            # caractere se ainda houver chance real de passar.
            matcher.set_seqs(t1, t2)
            if matcher.quick_ratio() < min_similaridade:
                continue
            sim = matcher.ratio()
            if sim >= min_similaridade:
                candidatos.append({
                    'termo_a': t1, 'freq_a': df[t1],
                    'termo_b': t2, 'freq_b': df[t2],
                    'similaridade': round(sim, 3),
                    'tipo': classificar_par(t1, df[t1], t2, df[t2]),
                })
    # primeiro os prováveis erros de digitação (o que o Edison acha bem),
    # depois as palavras diferentes parecidas (revisão cuidadosa)
    candidatos.sort(key=lambda c: (c['tipo'] != TIPO_DIGITACAO, -c['similaridade'], c['termo_a'], c['termo_b']))
    return candidatos


TIPO_DIGITACAO = 'provavel_erro_de_digitacao'
TIPO_PALAVRAS = 'palavras_diferentes_parecidas'
FREQUENTE = 5          # ocorrências a partir das quais um token é palavra do vocabulário, não deslize
RAZAO_RARA = 4         # um lado tantas vezes mais raro que o outro: cara de deslize


def classificar_par(t1, f1, t2, f2):
    """Tipo do par parecido. Grafia parecida junta dois casos que pedem
    revisões diferentes: a variação ou o deslize de digitação (um começa com
    o outro, como 'calcula'/'calcular', ou um lado bem mais raro) e duas
    palavras reais do vocabulário ('contato'/'contrato', 'emissao'/'demissao':
    começando diferente, ou as duas frequentes). Medido nas duas bases reais:
    letra somada no início quase sempre forma outra palavra."""
    if t1.startswith(t2) or t2.startswith(t1):
        return TIPO_DIGITACAO
    if t1[0] != t2[0]:
        return TIPO_PALAVRAS
    if min(f1, f2) >= FREQUENTE and max(f1, f2) < RAZAO_RARA * min(f1, f2):
        return TIPO_PALAVRAS
    return TIPO_DIGITACAO


def sugerir_mapa(db_path, raiz_conhecimento=None):
    """Sugestões de ligação de parâmetro -> cadastro (não grava nada)."""
    from dominios.formulas import conhecimento as kb
    from dominios.mapa_rotulos import entidade_de_codigo, entidade_de_descricao, ligar_parametro

    base = kb.carregar(raiz_conhecimento or kb.RAIZ_CONHECIMENTO)
    conn = sqlite3.connect(f'file:{os.path.abspath(db_path)}?mode=ro', uri=True)
    try:
        cadastros = {c: {'cadastro': c, 'tabela': t, 'funcoes': set(), 'entidades': set()}
                     for c, t in conn.execute('SELECT cadastro, tabela FROM mapa_cadastros')}
        for c, fn in conn.execute('SELECT cadastro, funcao FROM mapa_funcoes'):
            cadastros[c]['funcoes'].add(fn.upper())
        for c, r in conn.execute('SELECT cadastro, rotulo FROM mapa_rotulos'):
            e = entidade_de_codigo(r)
            if e:
                cadastros[c]['entidades'].add(e)
        # Descrição da origem conhecida como errada (confirmado pelo usuário):
        # nunca é evidência para sugerir nada.
        try:
            erradas = {(t.upper(), c_.upper()) for t, c_ in conn.execute(
                'SELECT tabela, coluna FROM mapa_papeis WHERE descricao_errada = 1')}
        except sqlite3.OperationalError:
            erradas = set()
        pk, desc = {}, {}
        for t, col, d, o in conn.execute('SELECT tabela, coluna, descricao, pk_ordem FROM colunas'):
            if col == '#' or (t.upper(), col.upper()) in erradas:
                continue
            desc.setdefault(t, []).append((col, d or ''))
            if o is not None:
                pk.setdefault(t, []).append((o, col))
    finally:
        conn.close()
    por_entidade_pk = {}          # entidade -> {(tabela, coluna)} de colunas da PK com descrição "código do X"
    for t, cols in desc.items():
        pk_t = {c for _, c in pk.get(t, [])}
        for col, d in cols:
            e = entidade_de_codigo(d)
            if e and col in pk_t:
                por_entidade_pk.setdefault(e, set()).add((t, col))

    ligados, sugestoes, de_fora = [], [], []
    for f in sorted(base.funcoes.values(), key=lambda x: x['nome']):
        for p in f.get('parametros') or []:
            rotulo = p.get('rotulo_documentado') or ''
            e = entidade_de_codigo(rotulo)
            if e is None:
                continue
            item = {'funcao': f['nome'].upper(), 'posicao': p.get('posicao'), 'rotulo': rotulo, 'entidade': e}
            ja = ligar_parametro(item['funcao'], rotulo, cadastros.values())
            if ja:
                ligados.append({**item, 'cadastro': ja})
                continue
            if not e:
                de_fora.append({**item, 'motivo': 'rótulo só diz "código", sem entidade'})
                continue
            donos = [c for c in cadastros.values() if e in c['entidades']]
            if len(donos) == 1:
                sugestoes.append({**item, 'tipo': 'ligar_a_cadastro', 'cadastro': donos[0]['cadastro'],
                                  'tabela': donos[0]['tabela'],
                                  'prova': 'documentação: o rótulo diz a mesma entidade de um cadastro do mapa'})
                continue
            if len(donos) > 1:
                de_fora.append({**item, 'motivo': f'empate: {len(donos)} cadastros do mapa com essa entidade'})
                continue
            cand = por_entidade_pk.get(e, set())
            tabelas = {t for t, _ in cand}
            if len(tabelas) == 1 and len(cand) == 1:
                (t, col), = cand
                chave = [c for _, c in sorted(pk[t])]
                descs = [c for c, d in desc[t] if entidade_de_descricao(d) == e]
                sugestoes.append({**item, 'tipo': 'novo_cadastro', 'tabela': t, 'coluna_codigo': col, 'chave': chave,
                                  'coluna_descricao': descs[0] if len(descs) == 1 else None,
                                  'prova': 'estrutura: única coluna da PK no schema descrita como código dessa entidade'})
            elif not cand:
                de_fora.append({**item, 'motivo': 'nenhuma coluna da PK descrita como código dessa entidade'})
            else:
                de_fora.append({**item, 'motivo': f'empate: {len(tabelas)} tabela(s) / {len(cand)} coluna(s) candidatas'})
    for i, sg in enumerate(sugestoes, 1):
        sg['id'] = i
    return {'ligados': ligados, 'sugestoes': sugestoes, 'fica_de_fora': de_fora}


def _tipos_inferidos(args):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    from dominios.formulas import conhecimento as kb
    from dominios.formulas.tipos import inferir
    from dominios.aceite import formulas_aceitas
    r = inferir(kb.carregar(args.pacotes), aceitas=formulas_aceitas(os.path.dirname(os.path.abspath(args.db))))
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    print(f"Tipo de retorno inferido pelo uso (mínimo {r['minimo']} exemplos distintos, evidência que concorda): "
          f"{len(r['inferidos'])} função(ões)")
    for fn, x in r['inferidos'].items():
        print(f"  {fn}: {x['tipo']} ({x['ocorrencias']} exemplo(s))")
    print(f"Sugestões para revisão: {len(r['sugestoes'])}")
    for fn, x in r['sugestoes'].items():
        print(f"  {fn}: {x['tipos']} — {x['motivo']}")
    return 0


def _grafo_funcoes(args):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    from dominios.formulas import conhecimento as kb
    from dominios.formulas.grafo import MIN_EXEMPLOS, coocorrencia
    from dominios.aceite import formulas_aceitas
    base = kb.carregar(args.pacotes)
    aceitas = formulas_aceitas(os.path.dirname(os.path.abspath(args.db)))   # 4f: soluções aceitas
    g = coocorrencia(base, aceitas=aceitas, minimo=args.minimo or MIN_EXEMPLOS)

    def filtrar(arestas):
        return sorted(((a, b, n) for (a, b), n in arestas.items() if not args.funcao or args.funcao.upper() in (a, b)),
                      key=lambda x: (-x[2], x[0], x[1]))
    con, sug = filtrar(g['conhecimento']), filtrar(g['sugestoes'])
    if args.json:
        print(json.dumps({'n_exemplos': g['n_exemplos'], 'minimo': g['minimo'],
                          'conhecimento': [{'a': a, 'b': b, 'exemplos': n, 'origens': g['exemplos'][(a, b)]}
                                           for a, b, n in con],
                          'sugestoes': [{'a': a, 'b': b, 'exemplos': n, 'origens': g['exemplos'][(a, b)]}
                                        for a, b, n in sug]}, ensure_ascii=False, indent=1))
        return 0
    print(f"{g['n_exemplos']} exemplo(s) distinto(s) nas fontes limpas; mínimo para conhecimento: {g['minimo']}")
    print(f'Conhecimento ({len(con)} aresta(s)):')
    for a, b, n in con:
        print(f'  {a} — {b}: {n} exemplo(s)')
    print(f'Sugestões para revisão ({len(sug)}, abaixo do mínimo):')
    for a, b, n in sug[:50]:
        print(f'  {a} — {b}: {n}')
    return 0


def main():
    parser = argparse.ArgumentParser(description='Edison — sugestões de conhecimento a partir de fontes limpas')
    parser.add_argument('--db', default=DEFAULT_DB_PATH, help='Caminho do banco de schema')
    sub = parser.add_subparsers(dest='comando', required=True)
    p_sinonimos = sub.add_parser(
        'sugerir-sinonimos',
        help='Sugere pares candidatos a sinônimo minerados do próprio schema, para revisão (não aplica nada sozinho)'
    )
    p_sinonimos.add_argument('--min-similaridade', type=float, default=0.84)
    p_sinonimos.add_argument('--min-frequencia', type=int, default=2)
    p_sinonimos.add_argument('--limite', type=int, default=30)
    p_sinonimos.add_argument('--json', action='store_true')

    p_mapa = sub.add_parser('sugerir-mapa', help='sugere ligações de parâmetro de função -> cadastro do mapa '
                                                  '(só leitura; nada é gravado)')
    p_mapa.add_argument('--pacotes', help='raiz alternativa dos pacotes de conhecimento')
    p_mapa.add_argument('--json', action='store_true')

    p_grafo = sub.add_parser('grafo-funcoes', help='coocorrência de funções nas fontes limpas (só leitura)')
    p_grafo.add_argument('--pacotes', help='raiz alternativa dos pacotes de conhecimento')
    p_grafo.add_argument('--minimo', type=int, default=None, help='mínimo de exemplos distintos (padrão: o do motor)')
    p_grafo.add_argument('--funcao', help='só as arestas desta função')
    p_grafo.add_argument('--json', action='store_true')

    p_tipos = sub.add_parser('tipos-inferidos', help='tipo de retorno inferido pelo uso (só leitura)')
    p_tipos.add_argument('--pacotes', help='raiz alternativa dos pacotes de conhecimento')
    p_tipos.add_argument('--json', action='store_true')

    # Item 1 (auditoria de inovação) — checagem automática de cobertura
    args = parser.parse_args()

    if args.comando == 'grafo-funcoes':
        return _grafo_funcoes(args)
    if args.comando == 'tipos-inferidos':
        return _tipos_inferidos(args)

    if args.comando == 'sugerir-mapa':
        r = sugerir_mapa(args.db, args.pacotes)
        if args.json:
            print(json.dumps(r, indent=1, ensure_ascii=False))
            return 0
        print(f"Parâmetros de código já ligados pelo mapa: {len(r['ligados'])}")
        print(f"Sugestões (revise; nada foi gravado): {len(r['sugestoes'])}")
        for sg in r['sugestoes']:
            alvo = (f"cadastro '{sg['cadastro']}' ({sg['tabela']})" if sg['tipo'] == 'ligar_a_cadastro' else
                    f"NOVO cadastro {sg['tabela']}.{sg['coluna_codigo']} chave={sg['chave']} "
                    f"descrição={sg['coluna_descricao']}")
            print(f"  [{sg['id']}] {sg['funcao']} parâmetro {sg['posicao']} \"{sg['rotulo']}\" -> {alvo}")
            print(f"       prova: {sg['prova']}")
        print(f"Ficam só como rótulo: {len(r['fica_de_fora'])}")
        for x in r['fica_de_fora']:
            print(f"  - {x['funcao']} parâmetro {x['posicao']} \"{x['rotulo']}\": {x['motivo']}")
        return 0

    if args.comando == 'sugerir-sinonimos':
        if not os.path.exists(args.db):
            print(f"ERRO: banco não encontrado em: {args.db}", file=sys.stderr)
            sys.exit(1)
        candidatos = sugerir_sinonimos(args.db, args.min_similaridade, args.min_frequencia)[:args.limite]
        if args.json:
            print(json.dumps(candidatos, indent=2, ensure_ascii=False))
        else:
            print(f"{len(candidatos)} candidato(s) a sinônimo (revise antes de colocar em sinonimos.csv):")
            for tipo, titulo in ((TIPO_DIGITACAO, 'Variações e prováveis erros de digitação (um começa com o outro, ou um lado raro)'),
                                 (TIPO_PALAVRAS, 'Palavras diferentes e parecidas: quase sempre NÃO são sinônimos')):
                grupo = [c for c in candidatos if c['tipo'] == tipo]
                if grupo:
                    print(f"\n{titulo}:")
                for c in grupo:
                    print(f"  {c['termo_a']:<20} (freq {c['freq_a']:>3})  ~  {c['termo_b']:<20} "
                          f"(freq {c['freq_b']:>3})   similaridade={c['similaridade']}")
        return 0


if __name__ == '__main__':
    sys.exit(main())
