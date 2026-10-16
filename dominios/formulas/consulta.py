"""
Nível 3: fórmula que executa uma consulta (fase 4 da v3, bloco 4e), lado do
Shaka. As regras vêm do bloco `consulta` do dialeto (com as evidências da
documentação em `evidencias["consulta.*"]`); nada aqui é de um fornecedor.

Regras, na ordem:
1. leitura e avanço exigem a execução ANTES, da MESMA consulta (mesmo código):
   erro (`leitura_sem_execucao`), quando o dialeto declara
   `leitura_exige_execucao`;
2. variante documentada (ex.: grafia alternativa da função de avanço): aviso,
   com a forma dos exemplos;
3. o avanço fica na condição de saída de um laço e a leitura dentro do laço:
   aviso quando não (é o padrão dos exemplos, não uma regra escrita);
4. campo lido: numa consulta NOVA (o SELECT é conhecido), campo que não está
   no SELECT é erro; numa consulta já cadastrada (SELECT desconhecido), a
   lista de campos lidos sai como aviso para conferência, nunca como pergunta;
5. código que não é texto nem argumento marcado: aviso (não dá para conferir).
"""

from .sintaxe import percorrer


def papeis(dialeto_dict):
    """{papel: FUNÇÃO} do bloco `consulta` do dialeto, ou {}."""
    c = (dialeto_dict or {}).get('consulta') or {}
    return {k: c[k].upper() for k in ('executar', 'ler_campo', 'avancar_registro') if c.get(k)}


def _codigo(no):
    a = (no.get('args') or [None])[0]
    if a is None:
        return None
    if a.get('tipo') == 'texto':
        return ('texto', a['valor'].strip().upper())
    if a.get('tipo') == 'marcador':
        return ('marcador', a['nome'].strip().upper())
    return None


def _pos(no):
    return (no.get('linha') or 0, no.get('coluna') or 0)


def _msg(nivel, codigo, mensagem, no=None):
    d = {'nivel': nivel, 'codigo': codigo, 'mensagem': mensagem}
    if no is not None:
        d['linha'], d['coluna'] = no.get('linha'), no.get('coluna')
    return d


def validar_consulta(ast, dialeto_dict, campos_do_select=None):
    """(erros, avisos, resumo). `campos_do_select`: colunas do SELECT de uma
    consulta NOVA (None = consulta já cadastrada, SELECT desconhecido)."""
    cfg = (dialeto_dict or {}).get('consulta') or {}
    p = papeis(dialeto_dict)
    if not p or ast is None:
        return [], [], None
    variantes = {k.upper(): v.upper() for k, v in (cfg.get('variantes') or {}).items()}
    erros, avisos = [], []
    chamadas = []
    for no in percorrer(ast):
        if no.get('tipo') == 'chamada':
            nome = variantes.get(no['nome'], no['nome'])
            papel = next((k for k, v in p.items() if v == nome), None)
            if papel:
                chamadas.append((papel, no))
                if no['nome'] != nome:
                    avisos.append(_msg('aviso', 'variante_documentada',
                                       f'{no["nome"]} é grafia documentada de {nome}; os exemplos usam {nome}', no))
    if not chamadas:
        return [], [], None
    executadas = {}
    for papel, no in sorted(chamadas, key=lambda x: _pos(x[1])):
        cod = _codigo(no)
        if cod is None:
            avisos.append(_msg('aviso', 'codigo_nao_conferivel',
                               f'{no["nome"]}: o código da consulta não é texto nem argumento marcado; não dá para '
                               'conferir se é a mesma consulta executada', no))
            continue
        if papel == 'executar':
            executadas.setdefault(cod, _pos(no))
        elif cfg.get('leitura_exige_execucao') and (cod not in executadas or executadas[cod] > _pos(no)):
            erros.append(_msg('erro', 'leitura_sem_execucao',
                              f'{no["nome"]}({cod[1]}) sem {p["executar"]}({cod[1]}) antes: a leitura e o avanço '
                              f'exigem a execução da mesma consulta antes (evidência no dialeto)', no))
    lacos = [no for no in percorrer(ast) if no.get('tipo') == 'repeticao']
    nos_condicao = {id(x) for la in lacos for x in percorrer(la['condicao'])}
    nos_corpo = {id(x) for la in lacos for x in percorrer(la['corpo'])}
    tem_avanco = any(pa == 'avancar_registro' for pa, _ in chamadas)
    for papel, no in chamadas:
        if papel == 'avancar_registro' and id(no) not in nos_condicao:
            avisos.append(_msg('aviso', 'avanco_fora_da_saida_do_laco',
                               f'{no["nome"]} fora da condição de saída de um laço; o padrão documentado é '
                               f'REPITA ... ATE {no["nome"]}(código) = FALSO', no))
        if papel == 'ler_campo' and tem_avanco and id(no) not in nos_corpo:
            avisos.append(_msg('aviso', 'leitura_fora_do_laco',
                               f'{no["nome"]} fora do laço que percorre a consulta: lê só a linha corrente', no))
    campos = []
    for papel, no in chamadas:
        if papel == 'ler_campo' and len(no.get('args') or []) > 1 and no['args'][1].get('tipo') == 'texto':
            c = no['args'][1]['valor'].strip().upper()
            if c not in campos:
                campos.append(c)
            if campos_do_select is not None and c not in {x.upper() for x in campos_do_select}:
                erros.append(_msg('erro', 'campo_fora_do_select',
                                  f'{no["nome"]} lê o campo {c}, que não está no SELECT da consulta nova', no))
    if campos and campos_do_select is None:
        avisos.append(_msg('aviso', 'campos_da_consulta_cadastrada',
                           'confira que a consulta cadastrada devolve os campos lidos: ' + ', '.join(campos)))
    return erros, avisos, {'campos_lidos': campos, 'consultas': sorted({c[1] for c in executadas})}
