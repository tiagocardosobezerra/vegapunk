"""
Padrões antes de funções (fase 4 da v3, bloco 4c), no nível da solução.

Uma intenção sozinha é uma busca de função; um pedido com várias intenções
é um PADRÃO, e as funções são os ingredientes. Três regras, todas com prova
em fonte limpa (documentação ou solução aceita):

1. Promoção pelo grafo (`dominios/formulas/grafo.py`): numa intenção de
   fórmula cujo 1º candidato não coocorre (aresta de conhecimento) com o 1º
   candidato de nenhuma outra intenção de fórmula do pedido, o candidato da
   própria lista que coocorre vem para o topo, com a prova (com quem e em
   quantos exemplos). Intenção cujo 1º já coocorre não muda.
2. Padrões do pedido: receitas documentadas cujos ingredientes cobrem pelo
   menos duas intenções de fórmula (um ingrediente na lista de candidatos de
   cada uma). Saem na solução como referência, com a fórmula documentada.
3. Colunas lidas pelo padrão: as funções de leitura de campo do mapa
   (`mapa_funcoes_consulta`, papel `ler_campo`) recebem o nome do campo no
   parâmetro cujo rótulo documentado diz "campo". As tabelas da base que têm
   TODAS essas colunas são a prova estrutural para uma intenção de schema
   que cita um desses campos; vêm primeiro, na ordem da busca de schema.
"""

from collections import OrderedDict

from dominios.formulas.grafo import _chave_texto, funcoes_do_codigo
from dominios.formulas.sintaxe import analisar, percorrer


def _nomes(e):
    return [c['nome'] for c in e['candidatos']]


def promover_pelo_grafo(intencoes, grafo):
    """Reordena os candidatos das intenções de fórmula (no lugar)."""
    forte = grafo['conhecimento']

    def peso(a, b):
        return forte.get((a, b) if a < b else (b, a), 0)

    alvo = [e for e in intencoes if e['dominio'] == 'formulas' and e['candidatos']]
    for e in alvo:
        outras = [o['candidatos'][0]['nome'] for o in alvo if o is not e]
        if not outras:
            continue
        topo = e['candidatos'][0]['nome']
        if any(peso(topo, o) for o in outras):
            continue
        melhor = None
        for i, c in enumerate(e['candidatos'][1:], 1):
            ligacoes = sorted(((peso(c['nome'], o), o) for o in outras if peso(c['nome'], o)), reverse=True)
            if ligacoes and (melhor is None or ligacoes[0][0] > melhor[1][0][0]):
                melhor = (i, ligacoes)
        if melhor:
            i, ligacoes = melhor
            c = e['candidatos'].pop(i)
            c['prova'] = 'coocorre com ' + ', '.join(f'{o} em {n} exemplo(s) da documentação' for n, o in ligacoes)
            e['candidatos'].insert(0, c)


def selecionar_padroes(base, intencoes, pacote=None, limite=3):
    dial = base.dialeto(pacote)
    alvo = [e for e in intencoes if e['dominio'] == 'formulas' and e['candidatos']]
    todos = {n for e in alvo for n in _nomes(e)}
    vistos, out = set(), []
    for r in base.receitas:
        k = _chave_texto(r.get('formula'))
        if not k or k in vistos:
            continue
        vistos.add(k)
        ingred = funcoes_do_codigo(r.get('formula'), base, dial) or set()
        cobertas = [e['id'] for e in alvo if ingred & set(_nomes(e))]
        if len(cobertas) >= 2:
            out.append((-len(cobertas), -len(ingred & todos), r.get('camada') != 'publico', r.get('id') or '', r,
                        sorted(ingred), cobertas))
    out.sort(key=lambda x: x[:4])
    unicos, chaves = [], set()
    for x in out:            # o mesmo exemplo em dois pacotes (texto quase igual): fica o público
        k = (tuple(x[5]), tuple(x[6]))
        if k not in chaves:
            chaves.add(k)
            unicos.append(x)
    out = unicos
    return [{'id': r.get('id'), 'nome': r.get('nome'), 'formula': r.get('formula'), 'funcoes': ingred,
             'intencoes_cobertas': cobertas, 'url': (r.get('origem') or {}).get('url')}
            for *_x, r, ingred, cobertas in out[:limite]]


def campos_lidos(base, formula, funcoes_leitura, pacote=None):
    """Campos (literais de texto) passados às funções de leitura no parâmetro
    cujo rótulo documentado diz "campo"."""
    from dominios.formulas.texto import normalizar
    ast, erros, _ = analisar(formula or '', base.dialeto(pacote))
    if erros or ast is None:
        return []
    pos = {}
    for fn in funcoes_leitura:
        for f in base.por_nome.get(fn.upper(), []):
            for p in f.get('parametros') or []:
                if 'campo' in normalizar(p.get('rotulo_documentado') or '').split():
                    pos[fn.upper()] = p.get('posicao')
    out = OrderedDict()
    for no in percorrer(ast):
        if no.get('tipo') == 'chamada' and no['nome'] in pos:
            i = pos[no['nome']] - 1
            if 0 <= i < len(no['args']) and no['args'][i].get('tipo') == 'texto':
                out[no['args'][i]['valor'].strip().upper()] = True
    return list(out)
