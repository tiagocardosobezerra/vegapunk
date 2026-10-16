"""
Tipos de retorno inferidos pelo uso (fase 4 da v3, bloco 4d).

Fontes: as mesmas do grafo (`grafo.exemplos_limpos`): receitas e exemplos da
documentação que analisam no dialeto, um por texto distinto, e as soluções
aceitas. Nunca fórmulas do sistema de origem.

Evidência de uso de uma função F num exemplo:
- comparada com um literal (número, texto, data dd/mm/aaaa ou booleano do
  dialeto): o tipo do literal;
- operando de conta (+ - * /) com um literal numérico: número;
- argumento de um parâmetro com tipo documentado (número, texto, data) de
  outra função: esse tipo. Parâmetro numérico documentado entre aspas não
  conta (a documentação o escreve como texto);
- condição direta de um SE ou de um REPITA ... ATE: booleano.

O tipo só vira conhecimento (`tipo_retorno_inferido`, com
`evidencia: inferido_de_uso` e a contagem de exemplos) quando TODA a
evidência concorda e aparece em pelo menos `MIN_EXEMPLOS` exemplos
distintos. Evidência em conflito ou abaixo do mínimo é sugestão para revisão.
Função com tipo de retorno documentado não recebe inferência: a
documentação vence. O validador usa o tipo inferido só para AVISO.
"""

import re
from collections import defaultdict

from .grafo import MIN_EXEMPLOS, exemplos_limpos
from .sintaxe import Dialeto, analisar, percorrer

TIPOS = ('numero', 'texto', 'data', 'booleano')
_RE_DATA = re.compile(r'^\d{2}/\d{2}/\d{4}$')


def tipo_documentado(ficha):
    t = ficha.get('tipo_retorno')
    return t if t in TIPOS else None


def _tipo_literal(no):
    t = no.get('tipo')
    if t == 'numero' or (t == 'unario' and no['valor'].get('tipo') == 'numero'):
        return 'numero'
    if t == 'texto':
        return 'data' if _RE_DATA.match(no['valor'].strip()) else 'texto'
    if t == 'booleano':
        return 'booleano'
    return None


def tipo_do_parametro(base, nome, posicao):
    """Tipo documentado do parâmetro, ou None (desconhecido, ou numérico
    documentado entre aspas)."""
    for f in base.por_nome.get(nome, []):
        for p in f.get('parametros') or []:
            if p.get('posicao') == posicao:
                tp = p.get('tipo')
                if tp == 'numero' and p.get('entre_aspas_na_documentacao'):
                    return None
                return tp if tp in ('numero', 'texto', 'data') else None
    return None


def _chamada(no, base, estrutura):
    if no.get('tipo') == 'grupo':
        return _chamada(no['valor'], base, estrutura)
    if no.get('tipo') in ('chamada', 'identificador') and no['nome'] in base.por_nome and no['nome'] not in estrutura:
        return no['nome']
    return None


def evidencias_do_codigo(codigo, base, dialeto_dict):
    """{função: {tipo}} das evidências de uso num código (vazio se não analisa)."""
    ast, erros, _ = analisar(codigo or '', dialeto_dict)
    if erros or ast is None:
        return {}
    dial = Dialeto(dialeto_dict)
    estrutura = {x for x in (dial.atrib, dial.decl) if x}
    ev = defaultdict(set)
    for no in percorrer(ast):
        t = no.get('tipo')
        if t == 'comparacao':
            for a, b in ((no['esq'], no['dir']), (no['dir'], no['esq'])):
                fn, lit = _chamada(a, base, estrutura), _tipo_literal(b)
                if fn and lit:
                    ev[fn].add(lit)
        elif t == 'aritmetica':
            for a, b in ((no['esq'], no['dir']), (no['dir'], no['esq'])):
                fn = _chamada(a, base, estrutura)
                if fn and _tipo_literal(b) == 'numero':
                    ev[fn].add('numero')
        elif t == 'chamada' and no['nome'] not in estrutura:
            for i, a in enumerate(no.get('args', []), 1):
                fn = _chamada(a, base, estrutura)
                tp = tipo_do_parametro(base, no['nome'], i) if fn else None
                if fn and tp:
                    ev[fn].add(tp)
        elif t in ('condicional', 'repeticao'):
            fn = _chamada(no['condicao'], base, estrutura)
            if fn:
                ev[fn].add('booleano')
    return ev


def inferir(base, pacote=None, aceitas=(), minimo=MIN_EXEMPLOS):
    """{'inferidos': {função: {'tipo', 'evidencia', 'ocorrencias', 'exemplos'}},
    'sugestoes': {função: {'tipos': {tipo: n}, 'motivo', 'exemplos'}}, 'minimo'}."""
    dial = base.dialeto(pacote)
    por_fn = defaultdict(lambda: defaultdict(list))
    for origem, codigo in _codigos(base, aceitas):
        for fn, tipos in evidencias_do_codigo(codigo, base, dial).items():
            for tp in tipos:
                por_fn[fn][tp].append(origem)
    inferidos, sugestoes = {}, {}
    for fn, tipos in sorted(por_fn.items()):
        if any(tipo_documentado(f) for f in base.por_nome.get(fn, [])):
            continue                                  # a documentação vence
        contagem = {tp: len(set(o)) for tp, o in tipos.items()}
        exemplos = sorted({o for os_ in tipos.values() for o in os_})
        if len(contagem) == 1 and next(iter(contagem.values())) >= minimo:
            tp, n = next(iter(contagem.items()))
            inferidos[fn] = {'tipo': tp, 'evidencia': 'inferido_de_uso', 'ocorrencias': n, 'exemplos': exemplos}
        else:
            sugestoes[fn] = {'tipos': contagem, 'exemplos': exemplos,
                             'motivo': 'evidência em conflito' if len(contagem) > 1 else
                                       f'abaixo do mínimo de {minimo} exemplos'}
    return {'inferidos': inferidos, 'sugestoes': sugestoes, 'minimo': minimo}


def _codigos(base, aceitas):
    """(origem, código) dos exemplos distintos que analisam (mesma regra do grafo)."""
    vistos = set()
    from .grafo import _chave_texto
    fontes = [(r.get('id') or r.get('nome'), r.get('formula')) for r in base.receitas]
    for f in sorted(base.funcoes.values(), key=lambda f: f['id']):
        fontes += [(f'{f["id"]}#exemplo{i + 1}', e.get('codigo'))
                   for i, e in enumerate(f.get('exemplos') or []) if isinstance(e, dict)]
    fontes += [(f'solucao_aceita#{i + 1}', c) for i, c in enumerate(aceitas)]
    validos = {o for o, _fs in exemplos_limpos(base, aceitas=aceitas)}
    for origem, codigo in fontes:
        k = _chave_texto(codigo)
        if k and k not in vistos:
            vistos.add(k)
            if origem in validos:
                yield origem, codigo
