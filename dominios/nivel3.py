"""
Escada de complexidade e nível 3 (fase 4 da v3, bloco 4e), lado da Stella.

A solução tem um NÍVEL: 1 = só funções; 2 = funções com argumento que é
código de cadastro (ou argumento marcado); 3 = fórmula que executa uma
consulta (o 1º candidato de alguma intenção de fórmula é uma função de
consulta do dialeto). A Stella sempre entrega a menor solução que resolve:
o nível sai da própria solução, e o avaliador conta como erro uma solução
acima do `nivel_maximo` do caso.

No nível 3, o bloco `nivel_3` traz, nesta ordem:
- REAPROVEITAR antes de criar: o SQL de apoio do cadastro de consultas (mapa)
  para o usuário procurar, no banco dele, uma consulta já cadastrada sem
  parâmetro que devolva os campos;
- a capacidade declarada no dialeto (`parametros_na_chamada`): sem parâmetro
  na chamada, o filtro vai no próprio SQL ou na comparação dentro do laço;
- CONSULTA NOVA, quando há intenção de schema resolvida (fora do próprio
  cadastro de consultas): o SQL escrito pela descoberta (só JOIN provado,
  colunas que o pedido cita), o modelo do laço documentado validado pelo
  Shaka contra o SELECT e a instrução de cadastro manual. O motor nunca grava
  no sistema de origem.
"""

MARCA_CONSULTA_NOVA = 'CÓDIGO DA CONSULTA NOVA'


def papeis(cam, pacote=None):
    if cam.base is None or not cam.base.pacotes:
        return {}
    from dominios.formulas.consulta import papeis as _p
    try:
        return _p(cam.base.dialeto(pacote))
    except ValueError:
        return {}


def capacidade(cam, nome, pacote=None):
    """(valor, evidência) de uma capacidade booleana do bloco `consulta` do
    dialeto, ou (None, None) se não declarada."""
    if cam.base is None or not cam.base.pacotes:
        return None, None
    d = cam.base.dialeto(pacote)
    c = (d.get('consulta') or {})
    if not isinstance(c.get(nome), bool):
        return None, None
    return c[nome], (d.get('evidencias') or {}).get(f'consulta.{nome}')


def aplicar_escada(intencoes, p):
    """Escada nos candidatos: numa intenção de fórmula cujo 1º candidato NÃO é
    função de consulta, as funções de consulta saem da lista (subiriam a
    solução para o nível 3 sem necessidade). Roda antes da promoção pelo grafo."""
    funcoes_consulta = set(p.values())
    if not funcoes_consulta:
        return
    for e in intencoes:
        if e['dominio'] != 'formulas' or not e['candidatos'] or e['candidatos'][0]['nome'] in funcoes_consulta:
            continue
        fora = [c['nome'] for c in e['candidatos'] if c['nome'] in funcoes_consulta]
        if fora:
            e['candidatos'] = [c for c in e['candidatos'] if c['nome'] not in funcoes_consulta]
            e['avisos'].append(f'escada: {", ".join(fora)} fora da lista; {e["candidatos"][0]["nome"]} resolve sem '
                               'executar consulta')


def nivel(saida, p):
    funcoes_consulta = set(p.values())
    for e in saida['intencoes']:
        if e['dominio'] == 'formulas' and e['candidatos'] and e['candidatos'][0]['nome'] in funcoes_consulta:
            return 3
    f = saida.get('formula') or {}
    if funcoes_consulta & set(f.get('funcoes_usadas') or []):
        return 3
    if f.get('argumentos_a_preencher') or any(e['dominio'] == 'cadastro' and e['status'] == 'resolvida'
                                              for e in saida['intencoes']):
        return 2
    return 1


def _colunas_citadas(cam, tabela, texto):
    from nomi_nomi_no_mi.texto import STOP_WORDS, normalizar, radical, tokenizar
    toks = {radical(t) for t in tokenizar(texto) if t not in STOP_WORDS}
    if not toks or not cam.db_path:
        return []
    out = []
    for c, d in cam._consultar('SELECT coluna, descricao FROM colunas WHERE UPPER(tabela) = ? ORDER BY rowid',
                               (tabela.upper(),)):
        alvo = ' '.join(radical(t) for t in tokenizar(normalizar(d or '')))
        if c != '#' and any(t in alvo.split() for t in toks):
            out.append(f'{tabela.upper()}.{c.upper()}')
    return out


def bloco(cam, saida, contrato, pacote=None, uso=None):
    p = papeis(cam, pacote)
    b = {'reaproveitar': None, 'parametros_na_chamada': None, 'consulta_nova': None}
    cad = (cam.mapa or {}).get('cadastros', {}).get('consulta')
    if cad:
        from nomi_nomi_no_mi.apoio import sql_de_apoio
        b['reaproveitar'] = {'sql_apoio': sql_de_apoio(cad), 'tabela': cad['tabela'],
                             'instrucao': 'antes de criar, procure no seu banco uma consulta já cadastrada, sem '
                                          'parâmetro, que devolva os campos de que a fórmula precisa'}
    v, ev = capacidade(cam, 'parametros_na_chamada', pacote)
    if v is False:
        b['parametros_na_chamada'] = {'valor': False, 'evidencia': ev,
                                      'nota': 'a consulta não recebe parâmetro na chamada: o filtro vai no próprio '
                                              'SQL ou na comparação dentro do laço'}
    excluir = set()
    if cad:
        t = cad['tabela'].upper()
        excluir = {t} | set(cam.vizinhos.get(t, ()))
    esquema = [e for e in saida['intencoes'] if e['dominio'] == 'schema' and e['status'] == 'resolvida'
               and e['candidatos'][0]['tabela'].upper() not in excluir]
    if not esquema or cam.schema is None or len(p) < 3:
        return b
    from nomi_nomi_no_mi import montagem
    tabelas = [e['candidatos'][0]['tabela'].upper() for e in esquema]
    filtros = {}
    extra = []
    for it, e in zip(contrato['intencoes'], saida['intencoes']):
        if e in esquema:
            t = e['candidatos'][0]['tabela'].upper()
            extra += _colunas_citadas(cam, t, e['texto'] + ' ' + contrato.get('pedido', ''))
            if it.get('filtrar'):
                filtros[t] = it['filtrar']
    sql = montagem.montar(cam.schema, tabelas, filtros, cam.mapa, colunas_extra=extra)
    if not sql.get('sql'):
        return b
    campos = [c.split('.', 1)[1] for c in sql['sql'].split('\n', 1)[0][len('SELECT '):].split(', ')]
    lido = next((c.split('.', 1)[1] for c in extra), None) or campos[-1]
    modelo = _modelo_do_laco(cam, p, lido, contrato.get('contexto'), pacote, uso, campos)
    b['consulta_nova'] = dict(sql, campos=campos, modelo=modelo,
                              instrucao=('O motor não grava no sistema de origem. Cadastre esta consulta à mão no '
                                         'cadastro de consultas SQL do sistema, anote o código que ela receber e '
                                         f'preencha <<{MARCA_CONSULTA_NOVA}>> na fórmula. Ajuste a conta do laço ao '
                                         'que o pedido quer (o modelo só lê o campo).'))
    # Regra de segurança (usuário, 16/10): tabela que veio só do ranking da busca,
    # sem prova do mapa nem da documentação, sai marcada, com as alternativas do
    # top-3, e a consulta nova NÃO sai pronta
    sem_prova = []
    for e in esquema:
        c0 = e['candidatos'][0]
        if c0.get('prova') in ('mapa', 'padrao') or _citada_na_documentacao(cam, c0['tabela']):
            continue
        sem_prova.append({'intencao': e['id'], 'tabela': c0['tabela'].upper(), 'descricao': c0.get('descricao'),
                          'prova': 'escolhida pela busca, sem prova',
                          'alternativas': [{'tabela': c['tabela'].upper(), 'descricao': c.get('descricao')
                                            or _descricao_tabela(cam, c['tabela']), 'prova': 'top-3 da busca'}
                                           for c in e['candidatos'][1:3]]
                                          # além do top-3: só candidata COM prova (mapa, padrão ou documentação)
                                          + [{'tabela': c['tabela'].upper(), 'descricao': c.get('descricao')
                                              or _descricao_tabela(cam, c['tabela']),
                                              'prova': 'citada na documentação'
                                              if c.get('prova') not in ('mapa', 'padrao') else c['prova']}
                                             for c in e['candidatos'][3:]
                                             if c.get('prova') in ('mapa', 'padrao')
                                             or _citada_na_documentacao(cam, c['tabela'])]})
        if not sem_prova[-1]['descricao']:
            sem_prova[-1]['descricao'] = _descricao_tabela(cam, c0['tabela'])
    if sem_prova:
        b['consulta_nova']['tabelas_sem_prova'] = sem_prova
        b['consulta_nova']['pronta'] = False
        b['consulta_nova']['motivo_nao_pronta'] = 'NÃO está pronta: confirme a tabela antes de cadastrar a consulta'
    else:
        b['consulta_nova']['pronta'] = bool(modelo.get('valida'))
    return b


def _descricao_tabela(cam, tabela):
    if not cam.db_path:
        return None
    r = cam._consultar('SELECT descricao FROM tabelas WHERE UPPER(tabela) = ?', (tabela.upper(),))
    return r[0][0] if r else None


def _citada_na_documentacao(cam, tabela):
    """A documentação do pacote cita a tabela pelo nome (prova documental)."""
    if cam.base is None:
        return False
    if getattr(cam, '_tabelas_na_doc', None) is None:
        from dominios.formulas.essencial import texto_documentado
        cam._tabelas_na_doc = ' '.join(texto_documentado(f) for f in cam.base.funcoes.values())
    return f' {tabela.lower()} ' in cam._tabelas_na_doc


def _modelo_do_laco(cam, p, campo, contexto, pacote, uso, campos):
    """Modelo do laço documentado (executar, ler dentro do laço, avançar na
    saída), composto pelo Shaka e validado contra o SELECT da consulta nova."""
    from dominios.formulas.compositor import compor
    from dominios.formulas.sintaxe import Dialeto
    from dominios.formulas.validador import validar
    cmp_ = Dialeto(cam.base.dialeto(pacote)).op_cmp
    igual = next((o for o in ('=', '==') if o in cmp_), None)
    if igual is None:
        return {'formula': None, 'valida': False, 'avisos': [],
                'erros': [{'nivel': 'erro', 'codigo': 'plano', 'mensagem': 'o dialeto não documenta operador de igualdade'}]}
    m = {'marcador': MARCA_CONSULTA_NOVA}
    plano = [{'declarar': ['VALOR']},
             {'atribuir': 'VALOR', 'valor': {'numero': 0}},
             {'se': {'op': igual, 'esq': {'chamar': p['executar'], 'args': [m]}, 'dir': {'booleano': True}},
              'entao': {'repita': [{'atribuir': 'VALOR',
                                    'valor': {'chamar': p['ler_campo'], 'args': [m, {'texto': campo}]}}],
                        'ate': {'op': igual, 'esq': {'chamar': p['avancar_registro'], 'args': [m]},
                                'dir': {'booleano': False}}}},
             {'variavel': 'VALOR'}]
    r = compor(plano, cam.base, contexto, pacote, uso)
    texto = r.get('formula') or r.get('rascunho_rejeitado')
    if not texto:
        return {'formula': None, 'valida': False, 'erros': r['erros'], 'avisos': []}
    v = validar(texto, cam.base, contexto, pacote, uso, campos_consulta=campos)
    return {'formula': texto if v['valida'] else None, 'valida': v['valida'], 'pronta_para_cadastrar': False,
            'erros': v['erros'], 'avisos': v['avisos'], 'rascunho_rejeitado': None if v['valida'] else texto}
