"""
Cobertura de intenções (fase 4 da v3): a métrica do portão das soluções.

Um caso de solução é um pedido com várias intenções (quem quebra o pedido é o
Claude que usa a skill; aqui as intenções já vêm no caso). Para cada
intenção, o caso diz o domínio e o item esperado:
  - formulas: alguma das funções esperadas entre os 3 primeiros da busca de
    fórmulas daquela intenção (no contexto do caso). `proibido_no_top3`:
    funções que, se aparecerem entre os 3 primeiros, fazem a intenção errar;
  - schema: alguma das tabelas esperadas entre as 3 primeiras críticas;
  - cadastro: o argumento de código da função (o da `posicao`, se a função
    tem mais de um) aponta para o cadastro esperado do mapa.
    `proibido_ligado`: {função: cadastro} que não pode aparecer ligado;
  - lacuna: a intenção espera "sem resposta". Só conta como acerto quando a
    resposta é vazia (a busca não devolve nada, nenhum candidato atende o
    termo `essencial` da intenção, ou o código não está ligado).
  - `essencial` (opcional, vem do Claude no contrato da intenção): o motor só
    aceita candidato cujo texto documentado contém o essencial
    (`dominios/formulas/essencial.py`); sem nenhum, a intenção é lacuna.

Cobertura do caso = fração das intenções certas; a métrica é a média sobre os
casos. Módulo puro: a busca de cada versão do motor entra por um adaptador
com três métodos (`formulas(texto, contexto, essencial)`, `schema`,
`ligacao(funcao, contexto, posicao)`),
para medir com os MESMOS
casos e dados o código de qualquer tag.
"""

TOP = 3


def avaliar_intencao(it, contexto, motor):
    """(acertou, detalhe)."""
    d = it['dominio']
    if d == 'formulas':
        nomes = motor.formulas(it['texto'], contexto, it.get('essencial'))[:TOP]
        if it.get('lacuna'):
            return not nomes, nomes
        if set(nomes) & set(it.get('proibido_no_top3', [])):
            return False, nomes
        return bool(set(nomes) & set(it['esperado'])), nomes
    if d == 'schema':
        tabelas = [t.upper() for t in motor.schema(it['texto'])[:TOP]]
        if it.get('lacuna'):
            return not tabelas, tabelas
        return bool(set(tabelas) & {t.upper() for t in it['esperado']}), tabelas
    if d == 'cadastro':
        ligado = motor.ligacao(it['funcao'], contexto, it.get('posicao'))
        for fn, cad in (it.get('proibido_ligado') or {}).items():
            if motor.ligacao(fn, contexto, None) == cad:
                return False, {'ligado': ligado, 'proibido_ligado': fn}
        if it.get('lacuna'):
            return ligado is None, {'ligado': ligado}
        return ligado in it['esperado'], {'ligado': ligado}
    raise ValueError(f'domínio desconhecido: {d}')


def avaliar(casos, motor):
    """{'cobertura': média, 'casos': [...], 'por_dominio': {...}, 'por_nivel': {...}}."""
    out, por_dom, por_nivel = [], {}, {}
    for c in casos:
        if hasattr(motor, 'preparar'):      # motor que resolve o pedido inteiro (padrões, promoção)
            motor.preparar(c)
        res = []
        for it in c['intencoes']:
            ok, det = avaliar_intencao(it, c.get('contexto'), motor)
            res.append({'id': it['id'], 'dominio': it['dominio'], 'lacuna': bool(it.get('lacuna')), 'acertou': ok,
                        'resposta': det})
            chave = 'lacuna' if it.get('lacuna') else it['dominio']
            a, n = por_dom.get(chave, (0, 0))
            por_dom[chave] = (a + ok, n + 1)
        # 4e: o caso inteiro também é medido pela escada (nível da solução até
        # `nivel_maximo`) e pela consulta nova entregue (`consulta_nova`)
        if c.get('nivel_maximo') is not None and hasattr(motor, 'nivel'):
            n = motor.nivel()
            res.append({'id': f'{c["id"]}.nivel', 'dominio': 'nivel', 'lacuna': False,
                        'acertou': n is not None and n <= c['nivel_maximo'], 'resposta': {'nivel': n}})
        if c.get('consulta_nova') and hasattr(motor, 'consulta_nova'):
            ok = motor.consulta_nova()
            res.append({'id': f'{c["id"]}.consulta_nova', 'dominio': 'consulta_nova', 'lacuna': False,
                        'acertou': ok, 'resposta': {'consulta_nova': ok}})
        for r in res[len(c['intencoes']):]:
            a, n = por_dom.get(r['dominio'], (0, 0))
            por_dom[r['dominio']] = (a + r['acertou'], n + 1)
        cob = sum(r['acertou'] for r in res) / len(res) if res else 0.0
        a, n = por_nivel.get(c.get('nivel'), (0.0, 0))
        por_nivel[c.get('nivel')] = (a + cob, n + 1)
        out.append({'id': c['id'], 'cobertura': round(cob, 4), 'intencoes': res})
    media = sum(c['cobertura'] for c in out) / len(out) if out else 0.0
    return {'cobertura': round(media, 4), 'casos': out,
            'por_dominio': {k: {'acertos': a, 'intencoes': n} for k, (a, n) in sorted(por_dom.items())},
            'por_nivel': {str(k): round(a / n, 4) for k, (a, n) in sorted(por_nivel.items(), key=lambda x: str(x[0]))}}
