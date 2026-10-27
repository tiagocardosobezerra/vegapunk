#!/usr/bin/env python3
"""
================================================================================
 SHAKA — motor de COMPOSIÇÃO E VALIDAÇÃO DE FÓRMULAS do Vegapunk
================================================================================
Nome de referência: Shaka é o satélite da sabedoria/lógica ("bem") — aqui, o
motor que raciocina sobre um dicionário técnico de funções para montar,
validar e explicar fórmulas, e que se recusa a afirmar o que o dicionário
não sustenta.

Totalmente separado do motor de schema (`nomi_nomi_no_mi/`): não
importa nada dele, não lê `punk_records.db`, não grava em
`punk_records_log.jsonl` (tem log PRÓPRIO, na camada privada). O
conhecimento vem de PACOTES (ver `punk_records/pacotes/` e referencias/formulas.md):

    punk_records/pacotes/publico/<pacote>/   distribuível
    punk_records/pacotes/privado/<pacote>/   só desta instalação (opcional)

Não tem CLI própria desde a fase 1 da v3: o fluxo entra pela Stella, que
monta a linha de comando e chama `executar` (contexto = família de
fórmulas; liste com `stella.py contextos`):
    python3 stella.py buscar   --dominio formulas "arredondar com duas casas" --contexto <CTX>
    python3 stella.py detalhar --dominio formulas FUNCAO1 FUNCAO2 --contexto <CTX>
    python3 stella.py validar  "<fórmula>" --contexto <CTX> [--uso selecao]
    python3 stella.py explicar "<fórmula>" --contexto <CTX>
    python3 stella.py compor   --plano plano.json --contexto <CTX>
    python3 stella.py confirmar --dominio formulas "<pedido original>" FUNCAO --contexto <CTX>
    python3 stella.py formatar "<fórmula>"
    python3 stella.py pacotes | contextos | status

    --json em qualquer comando (antes ou depois do nome do comando). Flags
    gerais: --somente-publico (ignora a camada privada), --pacote ID,
    --pacotes DIR (raiz alternativa dos pacotes), --privado DIR.
    Isolamento entre camadas e domínios: `atlas.py isolamento`.

Toda saída textual segue o padrão pt-BR (`1.234,56`), como o Nomi Nomi no Mi.
Saída 0 = ok / fórmula válida; 1 = fórmula inválida ou sem suporte; 2 = uso.
================================================================================
"""

import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))   # raiz da skill: pacote `dominios`

from dominios.formulas import conhecimento as kb  # noqa: E402
from dominios import lembretes  # noqa: E402
from dominios.formulas import historico  # noqa: E402
from dominios.formulas.validador import validar  # noqa: E402
from dominios.formulas.compositor import compor, explicar, formatar  # noqa: E402
from dominios.formulas.texto import formatar_numero_ptbr  # noqa: E402


def _json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def _pos(m):
    return f" (linha {m['linha']}, col {m['coluna']})" if m.get('linha') else ''


def _texto_validacao(v):
    linhas = [('VÁLIDA' if v['valida'] else 'INVÁLIDA') + f" — contexto {v.get('contexto') or '(todos)'}"
              + (f", uso {v['uso']}" if v.get('uso') else '')]
    linhas += [f"  ERRO [{e['codigo']}]{_pos(e)}: {e['mensagem']}" for e in v['erros']]
    linhas += [f"  aviso [{a['codigo']}]{_pos(a)}: {a['mensagem']}" for a in v['avisos']]
    if v.get('funcoes_usadas'):
        linhas.append('  funções usadas: ' + ', '.join(f"{u['nome']} ({u['contexto']}, {u['camada']})"
                                                       for u in v['funcoes_usadas']))
    return '\n'.join(linhas)


def _texto_busca(r):
    out = [f"Pedido: {r['pedido']}  | contexto: {r['contexto'] or '(todos)'}  | termos: {', '.join(r['termos'])}"]
    out += [f'AVISO: {a}' for a in r.get('avisos') or ([r['aviso']] if r.get('aviso') else [])]
    for i, x in enumerate(r['resultados'], 1):
        out.append(f"{i:2d}. {x['nome']:<22} [{x['contexto']}/{x['camada']}] "
                   f"score={formatar_numero_ptbr(x['score'])}  conf={x['confianca_extracao']}  "
                   f"{(x['descricao'] or 'sem descrição')[:90]}")
        if x['assinaturas']:
            out.append(f"      sintaxe: {' | '.join(x['assinaturas'])[:120]}")
        if x['usos_proibidos']:
            out.append(f"      não usar em: {', '.join(x['usos_proibidos'])}")
    out += [f"  receita: {rc.get('nome')} — {rc.get('formula')}" for rc in r['receitas']]
    return '\n'.join(out)


def _texto_detalhe(f):
    """Ficha legível — mesmo papel do `detalhar` em texto do motor de consultas."""
    if f.get('encontrada') is False:
        outros = ', '.join(f['existe_em_outros_contextos']) or 'nenhum'
        return f"{f['nome']}: NÃO encontrada neste contexto (existe em: {outros}). {f['mensagem']}"
    o = (f.get('origens') or [{}])[0]
    linhas = [f"=== {f['nome']}  [{f['contexto']}/{f.get('camada')}]  confiança da extração: "
              f"{f.get('confianca_extracao')}",
              f"  descrição: {f.get('descricao') or 'não documentada'}"]
    linhas += [f'  sintaxe:   {a["texto"]}' for a in f.get('assinaturas', [])] or ['  sintaxe:   não documentada']
    ligacoes = {x['posicao']: x for x in f.get('ligacoes_parametros', [])}
    for p in f.get('parametros', []):
        linhas.append(f"  param {p['posicao']}: {p.get('rotulo_documentado')} ({p.get('tipo')}"
                      f"{', opcional' if p.get('obrigatorio') is False else ''})"
                      + (f" — {p['descricao']}" if p.get('descricao') else ''))
        lg = ligacoes.get(p['posicao'])
        if lg and lg['ligado']:
            linhas.append(f"      ligado pelo mapa: cadastro {lg['cadastro']} -> {lg['tabela']}.{lg['coluna_codigo']}"
                          f" (chave: {', '.join(lg['chave'])})")
            if lg.get('chave_completa'):
                linhas.append(f"      {lg['chave_completa']}")
            if lg.get('sql_apoio'):
                linhas.append(f"      SQL de apoio (rode no seu banco para achar o código; o motor não executa): "
                              f"{lg['sql_apoio']}")
            for av in lg.get('avisos', []):
                linhas.append(f"      aviso: {av}")
        elif lg:
            linhas.append(f"      {lg['motivo']}")
    linhas.append(f"  retorno:   {f.get('tipo_retorno_documentado') or 'não documentado'}")
    for e in f.get('exemplos', [])[:3]:
        linhas.append('  exemplo:   ' + e['codigo'].replace('\n', ' ')
                      + (f"  -> {e['resultado']}" if e.get('resultado') else ''))
    for u in f.get('usos_proibidos', []):
        linhas.append(f"  NÃO usar em fórmula de {u['uso']}: {u.get('evidencia', '')[:120]}")
    for ob in f.get('observacoes', [])[:3]:
        linhas.append(f"  {ob.get('tipo', 'obs')}: {ob['texto'][:160]}".replace('\n', ' '))
    for n in f.get('anotacoes', []):
        linhas.append(f"  anotação ({n.get('camada')}): {n.get('texto')}")
    if f.get('nao_documentado'):
        linhas.append('  não documentado: ' + ', '.join(f['nao_documentado']))
    linhas.append(f"  fonte:     {o.get('url') or o.get('fonte') or o.get('pacote')}")
    return '\n'.join(linhas)


def executar(a, erro):
    """Executa um comando de fórmulas. `a` traz os mesmos campos da antiga CLI
    do Shaka (cmd, json, raiz_pacotes, somente_publico, privado, pacote e os
    argumentos de cada comando); `erro(msg)` reporta erro de uso. A linha de
    comando é montada pela Stella. Os avisos de merge da base não saem mais
    aqui: estão em `stella.py status`."""
    como_json = getattr(a, 'json', False)
    base = kb.carregar(a.raiz_pacotes, somente_publico=a.somente_publico, extras=a.privado)

    if a.cmd == 'pacotes':
        _json([p.resumo() for p in base.pacotes])
        return 0
    if a.cmd == 'contextos':
        _json({f'{pac}:{c}': cfg for (pac, c), cfg in sorted(base.contextos.items())})
        return 0
    if a.cmd == 'buscar':
        r = base.buscar(a.pedido, a.contexto, a.pacote, a.limite)
        # Laço de feedback (igual ao `buscar` da CLI de consultas): registra o
        # uso; `confirmar` fecha o laço depois que a fórmula final é escrita.
        historico.registrar({'tipo': 'buscar', 'pedido': a.pedido, 'contexto': a.contexto,
                             'termos': r['termos'], 'ambiguidade': r['ambiguidade'],
                             'fuzzy_aplicado': r['fuzzy_aplicado'],
                             'top5': [x['nome'] for x in r['resultados'][:5]]}, a.raiz_pacotes)
        _json(r) if como_json else print(_texto_busca(r))
        return 0 if r['resultados'] else 1

    if a.cmd == 'confirmar':
        # 4f: uma solução tem várias funções; a 1ª continua em `funcao` (compatível)
        nomes = [n.strip().upper() for n in (a.funcao if isinstance(a.funcao, list) else [a.funcao])]
        for nome in nomes:
            dentro, fora = base.resolver(nome, a.contexto, a.pacote)
            if not dentro:
                # Não bloqueia (pode existir só na camada privada de outra máquina), mas avisa —
                # mesmo comportamento do `confirmar` de consultas.
                print(f'AVISO: "{nome}" não existe no dicionário para o contexto {a.contexto or "(todos)"}'
                      + (f' (existe em: {", ".join(sorted({f["contexto"] for f in fora}))})' if fora else '')
                      + ' — confira se não é erro de digitação. Registrando mesmo assim.', file=sys.stderr)
        reg = {'tipo': 'confirmacao', 'pedido': a.pedido, 'contexto': a.contexto, 'funcao': nomes[0]}
        if len(nomes) > 1:
            reg['funcoes'] = nomes
        if historico.registrar(reg, a.raiz_pacotes):
            print(f'Confirmado: "{a.pedido}" -> {", ".join(nomes)} ({a.contexto or "sem contexto"}). '
                  f'Registrado em {historico.caminho(a.raiz_pacotes)}')
        else:
            print(f'NÃO registrado (a pasta da instância não aceita gravação nesta cópia): "{a.pedido}" -> '
                  f'{", ".join(nomes)}', file=sys.stderr)
        return 0

    if a.cmd == 'detalhar':
        out = []
        for nome in a.nomes:
            dentro, fora = base.resolver(nome, a.contexto, a.pacote)
            if not dentro:
                out.append({'nome': nome.upper(), 'encontrada': False,
                            'existe_em_outros_contextos': sorted({f['contexto'] for f in fora}),
                            'mensagem': 'Não existe no dicionário para este contexto — não use.'})
                continue
            out += [{k: v for k, v in f.items() if a.completo or k != 'texto_original'} for f in dentro]
        enriquecer = getattr(a, 'enriquecer_detalhe', None)   # ponte da Stella (fase 3): ligações do mapa
        if enriquecer:
            out = enriquecer(out)
        _json(out) if como_json else print('\n\n'.join(_texto_detalhe(f) for f in out))
        lembretes.lembrar_confirmar('formulas')
        return 0 if all(o.get('encontrada', True) for o in out) else 1

    if a.cmd in ('validar', 'explicar'):
        if a.arquivo:
            with open(a.arquivo, encoding='utf-8') as fh:
                texto = fh.read()
        else:
            texto = a.formula
        if not texto:
            erro('informe a fórmula ou --arquivo')
        if a.cmd == 'validar':
            v = validar(texto, base, a.contexto, a.pacote, a.uso)
            v.pop('ast', None)
            _json(v) if como_json else print(_texto_validacao(v))
            return 0 if v['valida'] else 1
        e = explicar(texto, base, a.contexto, a.pacote, a.uso)
        if como_json:
            _json(e)
        else:
            print(e['formula'])
            print('\n'.join(e['passo_a_passo']))
            print('\nFontes:')
            for c in e['componentes']:
                print(f"  {c['nome']} ({c['contexto']}/{c['camada']}): {', '.join(x for x in c['fontes'] if x)}")
            if e['erros'] or e['avisos']:
                print(_texto_validacao({'valida': e['valida'], 'contexto': a.contexto, 'uso': a.uso,
                                        'erros': e['erros'], 'avisos': e['avisos']}))
        return 0 if e['valida'] else 1

    if a.cmd == 'compor':
        if a.plano:
            with open(a.plano, encoding='utf-8') as fh:
                plano = json.load(fh)
        else:
            plano = json.loads(a.plano_json)
        contexto = a.contexto or (plano.get('contexto') if isinstance(plano, dict) else None)
        r = compor(plano, base, contexto, a.pacote, a.uso)
        if como_json:
            _json(r)
        elif r['valida']:
            print(r['formula'])
            print()
            print('\n'.join(r['explicacao']['passo_a_passo']))
            for av in r['avisos']:
                print(f"  aviso [{av['codigo']}]: {av['mensagem']}")
        else:
            print('COMPOSIÇÃO REJEITADA — a fórmula não foi entregue:')
            for e in r['erros']:
                print(f"  ERRO [{e['codigo']}]: {e['mensagem']}")
            if r.get('rascunho_rejeitado'):
                print('  rascunho (NÃO usar): ' + r['rascunho_rejeitado'].replace('\n', ' '))
        return 0 if r['valida'] else 1

    if a.cmd == 'formatar':
        txt, erros = formatar(a.formula, base, a.pacote)
        if erros:
            _json(erros) if como_json else print('\n'.join(f"ERRO{_pos(e)}: {e['mensagem']}" for e in erros))
            return 1
        _json({'formula': txt}) if como_json else print(txt)
        return 0
    return 2

