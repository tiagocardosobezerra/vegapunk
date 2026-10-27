#!/usr/bin/env python3
"""
================================================================================
 ATLAS — guarda de regressão "golden" dos motores de CONSULTAS (Nomi Nomi no
 Mi) e de FÓRMULAS (Shaka)
================================================================================
Nome de referência: Atlas é a satélite da força bruta — aqui, a que martela
o motor de consultas com a mesma bateria de pedidos e exige que a saída
continue IDÊNTICA, bit a bit, à que foi gravada antes de uma mudança.

Por que existe, se já há o Pythagoras: `pythagoras.py avaliar` mede QUALIDADE
(a tabela esperada aparece no top-N?). Uma mudança pode manter 31/31 lá e
mesmo assim alterar ranking, scores, avisos, vizinhos expandidos ou o JSON
de `detalhar` — ou seja, mudar o comportamento que o usuário vê. Atlas mede
IDENTIDADE de comportamento: grava um snapshot ("golden") de `buscar()` e
`detalhar()` e depois compara. Foi criado junto com o motor de fórmulas
(Shaka) para provar que a introdução de fórmulas não tocou nas consultas.

Domínio de fórmulas (fase 0 da v3): o mesmo princípio vale para o Shaka.
O snapshot guarda `buscar` (pedidos dos `casos/busca.json` de cada pacote,
a descrição de cada função como pedido e pedidos extras genéricos), a ficha
de `detalhar` das três primeiras de cada busca, `validar`/`explicar` das
receitas e dos `casos/validacao.json`, `compor` dos `casos/composicao.json`
e os avisos de merge da base. Chama a biblioteca `formulas` direto: nunca
grava no log de confirmações do Shaka.

Atlas NUNCA grava em `punk_records_log.jsonl`: chama os métodos da classe
`NomiNomiNoMi` direto (só a CLI registra uso), e só usa a CLI contra a
fixture fictícia temporária (`casos/fixture_schema.py`).

Uso:
    python3 atlas.py capturar               # fixtures fictícias -> casos/golden/golden_consultas_fixture.json
                                            #                     + casos/golden/golden_formulas_fixture.json
    python3 atlas.py verificar              # compara as fixtures fictícias com os goldens
    python3 atlas.py capturar  --db ../egghead/punk_records.db
    python3 atlas.py verificar --db ../egghead/punk_records.db
        # instância real -> goldens PRIVADOS, fora do controle de versão:
        #   consultas: egghead/punk_records_golden.json (ao lado do banco;
        #              contém nomes reais de tabela, mesma regra do .db)
        #   fórmulas:  egghead/atlas_formulas_golden.json
        #              (pacotes instalados, públicos + privados)
    --dominio schema|formulas restringe a um domínio (padrão: os dois).
    python3 atlas.py isolamento [--json] [--pacotes DIR] [--rapido]
        # isolamento entre camadas e domínios (antes: shaka.py verificar-isolamento)
    python3 atlas.py distribuir --destino <pasta nova, fora do repositório>
        # a única saída para fora da instância: só a superfície distribuível,
        # sem .git; falha (e apaga a pasta gerada) se algo sair da allowlist

Saída 0 = idêntico; 1 = divergência (mostra as primeiras diferenças).
================================================================================
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))   # raiz da skill: pacote `casos`

GOLDEN_FIXTURE = os.path.join(AQUI, '..', 'casos', 'golden', 'golden_consultas_fixture.json')
GOLDEN_FORMULAS_FIXTURE = os.path.join(AQUI, '..', 'casos', 'golden', 'golden_formulas_fixture.json')
FIXTURE_FORMULAS = os.path.join(AQUI, '..', 'casos', 'fixtures', 'formulas')
GOLDEN_FORMULAS_REAL = os.path.join(os.environ.get('VEGAPUNK_EGGHEAD') or os.path.join(AQUI, '..', 'egghead'),
                                    'atlas_formulas_golden.json')

# Os motores são importados só quando o domínio é usado: cada domínio
# continua rodando sem o outro instalado.
NomiNomiNoMi = gerar_fixture_db = casos_consultas = None


def _importar_consultas():
    global NomiNomiNoMi, gerar_fixture_db, casos_consultas
    if NomiNomiNoMi is None:
        from nomi_nomi_no_mi import NomiNomiNoMi as motor
        from casos.fixture_schema import gerar_fixture_db as gerar
        from casos import casos_consultas as carregar
        NomiNomiNoMi, gerar_fixture_db, casos_consultas = motor, gerar, carregar

# Pedidos extras, genéricos (sem nenhum nome de schema real), cobrindo
# caminhos que os casos de casos/consultas_fixture.json não exercitam: só stop words, termo
# inexistente (fuzzy/vazio), ordinal por extenso, pedido muito longo.
PEDIDOS_EXTRAS = [
    'quero os dados da tabela',
    'xyzwq inexistente blablabla',
    'decimo terceiro salario do funcionario',
    'preciso de um relatorio com nome, cpf, data de admissao, salario, cargo e lotacao dos colaboradores ativos',
    'funcionarios',
]


def _pedidos(db_path):
    pedidos = []
    casos = casos_consultas()
    for grupo in (casos['calibracao'], casos['heldout'], casos['validacao_cega']):
        pedidos.extend(c[0] for c in grupo)
    pedidos.extend(PEDIDOS_EXTRAS)
    # Banco real: soma os pedidos que o próprio usuário já fez (log de uso),
    # que são a melhor amostra de comportamento real a preservar.
    if db_path:
        log = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'punk_records_log.jsonl')
        if os.path.exists(log):
            with open(log, encoding='utf-8') as f:
                for linha in f:
                    try:
                        p = json.loads(linha).get('pedido')
                    except json.JSONDecodeError:
                        continue
                    if p:
                        pedidos.append(p)
    vistos, unicos = set(), []
    for p in pedidos:
        if p not in vistos:
            vistos.add(p)
            unicos.append(p)
    return unicos


def _tabelas_para_detalhar(snapshot_buscas):
    tabs = []
    for r in snapshot_buscas.values():
        for t in r.get('criticas', [])[:3]:
            if t['tabela'] not in tabs:
                tabs.append(t['tabela'])
    return sorted(tabs)


def capturar_snapshot(db_path, com_cli, so_pedidos=None):
    """`so_pedidos`: no `verificar` da instância real, só os pedidos que o
    golden tem (os que entraram no log depois da captura ficam de fora)."""
    _importar_consultas()
    engine = NomiNomiNoMi(db_path)
    try:
        buscas = {}
        for p in _pedidos(None if com_cli else db_path):
            if so_pedidos is None or p in so_pedidos:
                buscas[p] = engine.buscar(p)
        detalhes = engine.detalhar(_tabelas_para_detalhar(buscas))
    finally:
        engine.fechar()
    snap = {'buscar': buscas, 'detalhar': detalhes}
    # normaliza via JSON (tuplas -> listas, floats idênticos ao que a CLI emite)
    snap = json.loads(json.dumps(snap, ensure_ascii=False, sort_keys=True))
    if com_cli:
        snap['cli'] = _snapshot_cli(db_path)
    return snap


def _snapshot_cli(db_path):
    """Round-trip pela CLI real (`--json`) — só contra a fixture temporária,
    porque a CLI grava log de uso ao lado do banco."""
    stella = os.path.join(os.path.dirname(AQUI), 'stella.py')   # entrada única do fluxo
    env = dict(os.environ, PYTHONIOENCODING='utf-8')   # JSON em UTF-8 também no Windows
    saida = {}
    for p in ['ferias do colaborador', 'salario do funcionario']:
        r = subprocess.run([sys.executable, stella, '--db', db_path, 'buscar', '--dominio', 'schema', p, '--json'],
                           capture_output=True, text=True, encoding='utf-8', env=env)
        saida['buscar::' + p] = json.loads(r.stdout) if r.returncode == 0 else {'erro': r.stderr}
    r = subprocess.run([sys.executable, stella, '--db', db_path, 'checar-modulos', '--json'],
                       capture_output=True, text=True, encoding='utf-8', env=env)
    saida['checar-modulos'] = json.loads(r.stdout) if r.returncode == 0 else {'erro': r.stderr}
    return saida


# Pedidos extras de fórmulas, genéricos (nenhum nome de fornecedor), cobrindo
# caminhos que os casos não exercitam: só stop words, termo inexistente
# (fuzzy/vazio), pedido longo e pedido curto sem contexto.
PEDIDOS_EXTRAS_FORMULAS = [
    'quero uma formula',
    'xyzwq inexistente blablabla',
    'arredondar com duas casas decimais',
    'somar o valor do mes anterior com o valor do mes atual e arredondar o resultado para duas casas',
    'data',
]


def _ler_json(caminho, padrao):
    if not os.path.exists(caminho):
        return padrao
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def _seguro(func):
    """Erro de composição/validação também é comportamento a preservar."""
    try:
        return func()
    except Exception as e:  # noqa: BLE001
        return {'excecao': type(e).__name__, 'mensagem': str(e)}


def capturar_snapshot_formulas(raiz, db_schema=None):
    """Snapshot do Shaka contra os pacotes de `raiz` (None = instalação real,
    públicos + privados). Ignora a variável de ambiente de pacotes privados
    extras, para o golden depender só do que está em disco. Com `db_schema`
    e a camada Mapa compilada nele (fase 3), guarda também as ligações de
    parâmetro e o SQL de apoio de cada função detalhada."""
    from dominios.formulas import conhecimento as kb
    from dominios.formulas.validador import validar
    from dominios.formulas.compositor import compor, explicar

    anterior = os.environ.pop(kb.VAR_AMBIENTE_PRIVADO, None)
    try:
        base = kb.carregar(raiz)
    finally:
        if anterior is not None:
            os.environ[kb.VAR_AMBIENTE_PRIVADO] = anterior

    pedidos = []
    for p in base.pacotes:
        for c in _ler_json(os.path.join(p.dir, 'casos', 'busca.json'), {}).get('casos', []):
            pedidos.append((c['pedido'], c.get('contexto')))
    for f in sorted(base.funcoes.values(), key=lambda f: f['id']):
        if f.get('descricao'):
            pedidos.append((f['descricao'], f['contexto']))
    pedidos += [(p, None) for p in PEDIDOS_EXTRAS_FORMULAS]

    buscas, a_detalhar = {}, []
    for pedido, ctx in pedidos:
        chave = f'{ctx or "-"}::{pedido}'
        if chave in buscas:
            continue
        r = base.buscar(pedido, ctx, limite=10)
        buscas[chave] = r
        for x in r['resultados'][:3]:
            if (x['nome'], ctx) not in a_detalhar:
                a_detalhar.append((x['nome'], ctx))

    detalhes = {}
    for nome, ctx in sorted(a_detalhar, key=lambda t: (t[0], t[1] or '')):
        dentro, fora = base.resolver(nome, ctx)
        detalhes[f'{ctx or "-"}::{nome}'] = {
            'dentro': [{k: v for k, v in f.items() if k != 'texto_original'} for f in dentro],
            'fora': sorted({f['contexto'] for f in fora}),
        }

    formulas = [(r['formula'], r.get('contexto'), None) for r in base.receitas if r.get('formula')]
    planos = []
    for p in base.pacotes:
        for c in _ler_json(os.path.join(p.dir, 'casos', 'validacao.json'), []):
            formulas.append((c['formula'], c.get('contexto'), c.get('uso')))
        for c in _ler_json(os.path.join(p.dir, 'casos', 'composicao.json'), []):
            planos.append((c['plano'], c.get('contexto'), p.id))

    validacoes = {}
    for texto, ctx, uso in formulas:
        v = _seguro(lambda: validar(texto, base, ctx, None, uso))
        v.pop('ast', None)
        validacoes[f'{ctx or "-"}::{uso or "-"}::{texto}'] = {
            'validar': v, 'explicar': _seguro(lambda: explicar(texto, base, ctx, None, uso))}

    composicoes = [{'contexto': ctx, 'pacote': pac,
                    'resultado': _seguro(lambda: compor(plano, base, ctx, pac))} for plano, ctx, pac in planos]

    snap = {'avisos_base': base.avisos, 'buscar': buscas, 'detalhar': detalhes,
            'validar_explicar': validacoes, 'compor': composicoes}
    if db_schema:
        from dominios.integracao import enriquecedor_de_detalhe
        enriquecer = enriquecedor_de_detalhe(db_schema)
        if enriquecer:
            import copy
            ligacoes = {}
            for chave, d in detalhes.items():
                fichas = enriquecer(copy.deepcopy(d['dentro']))
                itens = [{'funcao': f['id'], 'ligacoes': f['ligacoes_parametros']}
                         for f in fichas if f.get('ligacoes_parametros')]
                if itens:
                    ligacoes[chave] = itens
            snap['ligacoes_parametros'] = ligacoes
    # normaliza via JSON, como no snapshot de consultas
    return json.loads(json.dumps(snap, ensure_ascii=False, sort_keys=True, default=str))


GRUPOS_DIFERENCA = ('campos_novos', 'avisos_novos', 'mudanca_de_corpus', 'outras')
_CHAVES_DE_AVISO = ('aviso', 'avisos')


def _chave_de_score(caminho):
    """Número que só mede (score, margem): mudar o valor sem mudar a ordem dos
    resultados é mudança de corpus (documentação nova, sinônimo novo), não de
    comportamento. A ordem, se mudar, aparece como diferença de nome."""
    k = caminho.rsplit('/', 1)[-1].split('[')[0]
    return k == 'score' or k.startswith('score_') or k.endswith('_score') or k == 'margem_top1_top2'


def classificar_diferencas(esperado, obtido, caminho='', acc=None):
    """Classifica o diff contra o golden em três grupos (fase 2 da v3):
    - campos_novos: chave que não existia no golden (o resto do objeto igual);
    - avisos_novos: item a mais numa lista de avisos, com os avisos antigos
      todos presentes e na mesma ordem;
    - outras: qualquer outra mudança (valor, ordem, chave que sumiu, lista
      com outro tamanho). Este grupo tem que ficar vazio para recapturar."""
    acc = {g: [] for g in GRUPOS_DIFERENCA} if acc is None else acc
    if isinstance(esperado, dict) and isinstance(obtido, dict):
        for k in sorted(set(esperado) | set(obtido)):
            if k not in esperado:
                acc['campos_novos'].append(f'{caminho}/{k}')
            elif k not in obtido:
                acc['outras'].append(f'{caminho}/{k}: sumiu')
            elif k in _CHAVES_DE_AVISO and isinstance(esperado[k], list) and isinstance(obtido[k], list):
                restante = iter(obtido[k])
                if all(any(x == y for y in restante) for x in esperado[k]):
                    for i in range(len(esperado[k]), len(obtido[k])):
                        acc['avisos_novos'].append(f'{caminho}/{k}')
                    if len(obtido[k]) > len(esperado[k]):
                        continue
                    if obtido[k] == esperado[k]:
                        continue
                acc['outras'].append(f'{caminho}/{k}: avisos antigos mudaram')
            else:
                classificar_diferencas(esperado[k], obtido[k], f'{caminho}/{k}', acc)
    elif isinstance(esperado, list) and isinstance(obtido, list):
        if len(esperado) != len(obtido):
            acc['outras'].append(f'{caminho}: tamanho {len(esperado)} != {len(obtido)}')
        for i, (x, y) in enumerate(zip(esperado, obtido)):
            classificar_diferencas(x, y, f'{caminho}[{i}]', acc)
    elif esperado != obtido or type(esperado) != type(obtido):
        numeros = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (esperado, obtido))
        grupo = 'mudanca_de_corpus' if numeros and _chave_de_score(caminho) else 'outras'
        acc[grupo].append(f'{caminho}: {esperado!r} != {obtido!r}')
    return acc


def _resumo_classificacao(acc, limite=12):
    """Agrupa caminhos iguais a menos dos índices, para o relatório caber na tela."""
    import re as _re

    def tipo(caminho):
        caminho = caminho.split(': ')[0]
        for padrao, troca in ((r'^/buscar/[^/]+', '/buscar/<pedido>'), (r'^/cli/[^/]+', '/cli/<comando>'),
                              (r'/tabelas/[^/]+', '/tabelas/<tabela>'),
                              (r'^/validar_explicar/[^/]+', '/validar_explicar/<formula>'), (r'\[\d+\]', '[*]')):
            caminho = _re.sub(padrao, troca, caminho)
        return caminho

    linhas = []
    for g in GRUPOS_DIFERENCA:
        tipos = {}
        for c in acc[g]:
            tipos[tipo(c)] = tipos.get(tipo(c), 0) + 1
        linhas.append(f'  {g}: {len(acc[g])}')
        for t, n in sorted(tipos.items(), key=lambda x: (-x[1], x[0]))[:limite]:
            linhas.append(f'      {n:>6}  {t}')
        if g == 'outras':
            for c in acc[g][:limite]:
                linhas.append(f'      ex.: {c[:200]}')
    return '\n'.join(linhas)


def _diferencas(a, b, caminho='', limite=20, acc=None):
    acc = [] if acc is None else acc
    if len(acc) >= limite:
        return acc
    if type(a) != type(b):
        acc.append(f'{caminho}: tipo {type(a).__name__} != {type(b).__name__}')
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                acc.append(f'{caminho}/{k}: novo (não existia no golden)')
            elif k not in b:
                acc.append(f'{caminho}/{k}: sumiu (existia no golden)')
            else:
                _diferencas(a[k], b[k], f'{caminho}/{k}', limite, acc)
    elif isinstance(a, list):
        if len(a) != len(b):
            acc.append(f'{caminho}: tamanho {len(a)} != {len(b)}')
        for i, (x, y) in enumerate(zip(a, b)):
            _diferencas(x, y, f'{caminho}[{i}]', limite, acc)
    elif a != b:
        acc.append(f'{caminho}: {a!r} != {b!r}')
    return acc


def _com_fixture(func):
    _importar_consultas()
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'fixture.db')
        gerar_fixture_db(db)
        return func(db)


def _saida_utf8():
    """Saída em UTF-8 mesmo em console Windows (cp1252). Até a fase 0 da
    v3, Atlas se reexecutava com PYTHONHASHSEED=0, porque a ordem entre
    tabelas empatadas dependia da iteração de `set`s; desde então o motor
    desempata pelo nome da tabela e a saída é a mesma com qualquer
    semente — o golden é comparado sem fixar semente nenhuma."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass


def _gravar_ou_comparar(acao, golden, snap, rotulo, resumo, classificar=False):
    if acao == 'capturar':
        os.makedirs(os.path.dirname(golden), exist_ok=True)
        with open(golden, 'w', encoding='utf-8') as f:
            json.dump(snap, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f'Golden de {rotulo} gravado: {golden} ({resumo})')
        return 0

    if not os.path.exists(golden):
        print(f'Golden de {rotulo} não encontrado: {golden} — rode `capturar` antes da mudança.')
        return 1
    with open(golden, encoding='utf-8') as f:
        esperado = json.load(f)
    if classificar:
        acc = classificar_diferencas(esperado, snap)
        estado = ('IDÊNTICO' if not any(acc.values()) else 'OUTRAS MUDANÇAS' if acc['outras'] else
                  'SÓ CAMPOS/AVISOS NOVOS' if not acc['mudanca_de_corpus'] else
                  'MUDANÇA DE CORPUS (mesma ordem, só score)' + (' + campos/avisos novos'
                                                                if acc['campos_novos'] or acc['avisos_novos'] else ''))
        print(f'ATLAS (classificado): {rotulo} — {estado} ({resumo})')
        print(_resumo_classificacao(acc))
        return 1 if acc['outras'] else 0
    difs = _diferencas(esperado, snap)
    if difs:
        print(f'ATLAS: DIVERGÊNCIA em {rotulo} contra {golden}')
        for d in difs:
            print('  -', d)
        return 1
    print(f'ATLAS: comportamento de {rotulo} IDÊNTICO ao golden ({resumo}).')
    return 0


def _isolamento(args):
    """Isolamento entre camadas (público x privado) e entre domínios: as
    checagens estáticas do antigo `shaka.py verificar-isolamento` (mesma
    saída) e, sem --rapido, a dinâmica de cada domínio rodando sem o outro
    (dominios/separacao.py)."""
    from dominios.isolamento import verificar_isolamento
    from dominios.separacao import verificar_dominios_separados

    from dominios.nomes_reais import verificar_na_superficie

    r = verificar_isolamento(os.path.join(AQUI, '..'), args.pacotes)
    r['verificacoes'].append(verificar_na_superficie(os.path.join(AQUI, '..'), args.pacotes))
    r['ok'] = all(c['ok'] for c in r['verificacoes'])
    if not args.rapido:
        r['verificacoes'] += verificar_dominios_separados(os.path.join(AQUI, '..'))
        r['ok'] = all(c['ok'] for c in r['verificacoes'])
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    else:
        for c in r['verificacoes']:
            print(f"{'OK  ' if c['ok'] else 'FALHA'} {c['verificacao']}" + (f" — {c['detalhe']}" if c['detalhe'] else ''))
    return 0 if r['ok'] else 1


def _distribuir(args):
    from dominios.distribuicao import DistribuicaoRecusada, distribuir
    if not args.destino:
        print('ERRO: informe --destino (pasta nova, fora do repositório).', file=sys.stderr)
        return 1
    try:
        r = distribuir(os.path.join(AQUI, '..'), args.destino, args.pacotes)
    except DistribuicaoRecusada as e:
        print(f'DISTRIBUIÇÃO RECUSADA: {e}', file=sys.stderr)
        return 1
    print(f"Distribuição gerada em {r['destino']}: {r['arquivos']} arquivos (só a superfície distribuível, sem .git).")
    return 0


def main():
    _saida_utf8()
    ap = argparse.ArgumentParser(description='Atlas — golden de regressão dos motores de consultas e fórmulas')
    ap.add_argument('acao', choices=['capturar', 'verificar', 'isolamento', 'distribuir'])
    ap.add_argument('--db', help='Instância real (goldens privados). Omitido = fixtures fictícias.')
    ap.add_argument('--dominio', choices=['schema', 'formulas'], action='append',
                    help='restringe a um domínio (padrão: os dois)')
    ap.add_argument('--pacotes', help='isolamento: raiz alternativa dos pacotes de conhecimento')
    ap.add_argument('--json', action='store_true', help='isolamento: saída em JSON')
    ap.add_argument('--classificar', action='store_true',
                    help='verificar: classifica o diff em campos novos, avisos novos e outras mudanças')
    ap.add_argument('--rapido', action='store_true',
                    help='isolamento: só as checagens estáticas (sem rodar cada domínio sem o outro)')
    ap.add_argument('--destino', help='distribuir: pasta nova (ou vazia), fora do repositório')
    args = ap.parse_args()
    if args.acao == 'isolamento':
        return _isolamento(args)
    if args.acao == 'distribuir':
        return _distribuir(args)
    dominios = args.dominio or ['schema', 'formulas']

    codigo = 0
    if 'schema' in dominios:
        if args.db:
            golden = os.path.join(os.path.dirname(os.path.abspath(args.db)), 'punk_records_golden.json')
            so = None
            if args.acao == 'verificar' and os.path.exists(golden):
                # Um pedido que o usuário fez DEPOIS da captura não é mudança de
                # comportamento: o golden não tinha como conhecê-lo. Sem este
                # corte, toda busca real nova deixava o portão vermelho.
                _importar_consultas()
                so = set(_ler_json(golden, {}).get('buscar', {}))
                novos = [p for p in _pedidos(args.db) if p not in so]
                if novos:
                    print(f'ATLAS (info): {len(novos)} pedido(s) do log de uso depois da captura, fora da '
                          'comparação (entram no próximo `capturar`): ' + '; '.join(novos[:5])
                          + (' ...' if len(novos) > 5 else ''))
            snap = capturar_snapshot(args.db, com_cli=False, so_pedidos=so)
        else:
            golden = os.path.abspath(GOLDEN_FIXTURE)
            snap = _com_fixture(lambda db: capturar_snapshot(db, com_cli=True))
        resumo = (f'{len(snap["buscar"])} pedidos, '
                  f'{len(snap["detalhar"].get("tabelas", snap["detalhar"]))} detalhamentos')
        codigo |= _gravar_ou_comparar(args.acao, golden, snap, 'consultas', resumo, args.classificar)

    if 'formulas' in dominios:
        if args.db:
            # o golden real de fórmulas fica AO LADO do --db, como o de consultas:
            # medir numa cópia da base nunca toca no golden da instância
            golden = os.path.join(os.path.dirname(os.path.abspath(args.db)), 'atlas_formulas_golden.json')
            snap = capturar_snapshot_formulas(None, args.db)
        else:
            golden = os.path.abspath(GOLDEN_FORMULAS_FIXTURE)
            snap = capturar_snapshot_formulas(os.path.abspath(FIXTURE_FORMULAS))
        resumo = (f'{len(snap["buscar"])} pedidos, {len(snap["detalhar"])} detalhamentos, '
                  f'{len(snap["validar_explicar"])} validações, {len(snap["compor"])} composições')
        codigo |= _gravar_ou_comparar(args.acao, golden, snap, 'fórmulas', resumo, args.classificar)
    return codigo


if __name__ == '__main__':
    sys.exit(main())
