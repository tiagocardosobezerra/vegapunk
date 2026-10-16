"""
Grafo de coocorrência de funções (fase 4 da v3, bloco 4c).

Só fontes limpas, que são verdade por definição: as receitas e os exemplos
da documentação do pacote, e as soluções que o usuário aceitou (4f). Nunca
fórmulas do sistema de origem.

Cada fonte é um EXEMPLO: o texto é analisado pelo parser do dialeto (exemplo
que não analisa não conta) e dele saem as funções do dicionário chamadas,
sem as palavras de estrutura do dialeto (atribuição, declaração). Exemplos
iguais (mesmo texto, a menos de espaço e caixa) contam uma vez: a mesma
receita copiada em dois pacotes não é evidência dobrada.

Uma aresta (função A, função B) vale o número de exemplos DISTINTOS em que
as duas aparecem juntas. Só vira conhecimento com pelo menos
`MIN_EXEMPLOS`; abaixo disso é sugestão para revisão. `MIN_EXEMPLOS` é uma
constante a calibrar pelo Pythagoras (fase 5), nunca nos casos de validação.
"""

import re
from collections import defaultdict
from itertools import combinations

from .sintaxe import Dialeto, analisar, percorrer

MIN_EXEMPLOS = 2


def _chave_texto(codigo):
    return re.sub(r'\s+', ' ', (codigo or '').strip()).upper()


def funcoes_do_codigo(codigo, base, dialeto_dict):
    """Nomes das funções do dicionário chamadas no código, ou None se o código
    não analisa no dialeto."""
    ast, erros, _ = analisar(codigo or '', dialeto_dict)
    if erros or ast is None:
        return None
    dial = Dialeto(dialeto_dict)
    estrutura = {x for x in (dial.atrib, dial.decl) if x}
    nomes = set()
    for no in percorrer(ast):
        if no.get('tipo') in ('chamada', 'identificador') and no['nome'] not in estrutura \
                and no['nome'] in base.por_nome:
            nomes.add(no['nome'])
    return nomes


def exemplos_limpos(base, pacote=None, aceitas=()):
    """[(origem, frozenset(funções))] dos exemplos distintos que analisam."""
    dial = base.dialeto(pacote)
    vistos, out = set(), []

    def incluir(origem, codigo):
        k = _chave_texto(codigo)
        if not k or k in vistos:
            return
        vistos.add(k)
        fs = funcoes_do_codigo(codigo, base, dial)
        if fs:
            out.append((origem, frozenset(fs)))

    for r in base.receitas:
        incluir(r.get('id') or r.get('nome'), r.get('formula'))
    for f in sorted(base.funcoes.values(), key=lambda f: f['id']):
        for i, e in enumerate(f.get('exemplos') or []):
            if isinstance(e, dict):
                incluir(f'{f["id"]}#exemplo{i + 1}', e.get('codigo'))
    for i, codigo in enumerate(aceitas):
        incluir(f'solucao_aceita#{i + 1}', codigo)
    return out


def coocorrencia(base, pacote=None, aceitas=(), minimo=MIN_EXEMPLOS):
    """{'conhecimento': {(A, B): n}, 'sugestoes': {(A, B): n}, 'exemplos': {(A, B): [origens]},
    'n_exemplos': int, 'minimo': int}, com A < B."""
    ex = exemplos_limpos(base, pacote, aceitas)
    peso, origens = defaultdict(int), defaultdict(list)
    for origem, fs in ex:
        for a, b in combinations(sorted(fs), 2):
            peso[(a, b)] += 1
            origens[(a, b)].append(origem)
    return {'conhecimento': {k: n for k, n in peso.items() if n >= minimo},
            'sugestoes': {k: n for k, n in peso.items() if n < minimo},
            'exemplos': dict(origens), 'n_exemplos': len(ex), 'minimo': minimo}


def vizinhas(grafo, nome):
    """[(vizinha, peso)] das arestas de conhecimento de `nome`, mais forte primeiro."""
    out = [(b if a == nome else a, n) for (a, b), n in grafo['conhecimento'].items() if nome in (a, b)]
    return sorted(out, key=lambda x: (-x[1], x[0]))
