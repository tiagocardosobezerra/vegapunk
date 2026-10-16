"""
Validador de fórmulas — a barreira contra fórmula "parecida com válida".

Etapas (todas genéricas; o que é específico vem do dialeto e do dicionário):

  1. léxico/sintaxe        parser do dialeto (sintaxe.py)
  2. identificadores       todo nome precisa ser: palavra-chave, literal,
                           variável declarada, ou função EXISTENTE no
                           dicionário do contexto. Senão: ERRO (nunca aviso)
  3. contexto              função que só existe em outro contexto: ERRO
  4. forma de chamada      com/sem parênteses conforme a sintaxe documentada
  5. aridade               nº de argumentos ∈ aridades documentadas
                           (respeitando parâmetros documentados como opcionais)
  6. tipos de literais     literal incompatível com o tipo do parâmetro: AVISO
  7. usos proibidos        restrições documentadas (ex.: fórmula de seleção): ERRO
  8. limites do dialeto    ex.: máximo de constantes: ERRO
  9. confiança             ficha com extração de baixa confiança: AVISO

Quando a documentação NÃO permite afirmar algo (ex.: sintaxe não
documentada), o resultado é AVISO "não verificável" — nunca uma aprovação
silenciosa e nunca uma regra inventada.
"""

import difflib
import re

from .sintaxe import analisar, marcadores, percorrer, Dialeto

_RE_DATA = re.compile(r'^\d{2}/\d{2}/\d{4}$')


def _msg(nivel, codigo, mensagem, no=None, **extra):
    d = {'nivel': nivel, 'codigo': codigo, 'mensagem': mensagem}
    if no is not None:
        d['linha'], d['coluna'] = no.get('linha'), no.get('coluna')
    d.update(extra)
    return d


def _tipo_literal(no):
    if no['tipo'] == 'numero' or (no['tipo'] == 'unario' and no['valor']['tipo'] == 'numero'):
        return 'numero'
    if no['tipo'] == 'texto':
        return 'data' if _RE_DATA.match(no['valor'].strip()) else 'texto'
    if no['tipo'] == 'booleano':
        return 'booleano'
    return None


def _tipo_de_retorno(no, base, contexto, pacote, declaradas):
    """(tipo, origem) do retorno de uma chamada: o documentado, ou o inferido
    pelo uso (`tipo_retorno_inferido`, 4d); None se não se sabe."""
    while no.get('tipo') == 'grupo':
        no = no['valor']
    if no.get('tipo') not in ('chamada', 'identificador') or no['nome'] in declaradas:
        return None
    dentro, _ = base.resolver(no['nome'], contexto, pacote)
    for f in dentro:
        if f.get('tipo_retorno') in ('numero', 'texto', 'data', 'booleano'):
            return f['tipo_retorno'], 'documentado'
    for f in dentro:
        inf = f.get('tipo_retorno_inferido')
        if inf:
            return inf['tipo'], f'inferido pelo uso em {inf["ocorrencias"]} exemplo(s) da documentação'
    return None


def _aridades_aceitas(fichas):
    """União das aridades documentadas nas fichas visíveis + aridades menores
    permitidas por parâmetros documentados como opcionais."""
    aceitas, documentou = set(), False
    for f in fichas:
        ar = f.get('aridades_documentadas') or []
        if ar or f.get('assinaturas'):
            documentou = True
        aceitas.update(ar)
        params = f.get('parametros') or []
        if params:
            # opcionais só no fim da lista podem ser omitidos
            n = len(params)
            while n > 0 and params[n - 1].get('obrigatorio') is False:
                n -= 1
                aceitas.add(n)
    return aceitas, documentou


def validar(texto, base, contexto=None, pacote=None, uso=None, campos_consulta=None):
    """`campos_consulta`: colunas do SELECT de uma consulta NOVA (nível 3); None =
    consulta já cadastrada (os campos lidos saem como aviso para conferir)."""
    dial_d = base.dialeto(pacote)
    dial = Dialeto(dial_d)
    ast, erros_sint, _ = analisar(texto, dial_d)
    erros, avisos, usadas = [], [], []
    if erros_sint:
        for e in erros_sint:
            m = re.search(r'encontrado "([^"]+)"|antes de "([^"]+)"', e['mensagem'])
            palavra = (m.group(1) or m.group(2)) if m else None
            if palavra and dial.norm(palavra) in {dial.norm(o) for o in dial_d.get('operadores_nao_documentados', [])}:
                e = dict(e, mensagem=e['mensagem'] + f' — "{palavra}" não é operador documentado neste dialeto '
                         f'(documentados: {", ".join(dial_d.get("operadores", {}).get("logicos", [])) or "nenhum"}).')
            erros.append(e)
        return _resultado(texto, contexto, uso, None, erros, avisos, usadas, [])

    declaradas = set()
    for no in percorrer(ast):
        if no.get('tipo') == 'declaracao':
            declaradas.update(no['nomes'])

    nomes_disponiveis = None

    def sugestoes(nome):
        nonlocal nomes_disponiveis
        if nomes_disponiveis is None:
            vis = base.contextos_visiveis(contexto, pacote)
            nomes_disponiveis = sorted({f['nome'] for f in base.funcoes.values()
                                        if (vis is None or f['contexto'] in vis) and (not pacote or f['pacote'] == pacote)})
        return difflib.get_close_matches(nome, nomes_disponiveis, n=3, cutoff=0.75)

    alvos_validos = dial_d.get('estruturas', {}).get('atribuicao', {}).get('alvos', ['identificador'])
    constantes = 0
    alvos_atribuicao = set()   # 1º argumento de SETVAR: já validado como variável
    for no in percorrer(ast):
        t = no.get('tipo')
        if t in ('numero', 'texto', 'marcador'):     # o argumento marcado vira uma constante
            constantes += 1
        if t not in ('chamada', 'identificador'):
            continue
        nome = no['nome']
        com_par = t == 'chamada'
        args = no.get('args', [])

        if id(no) in alvos_atribuicao:
            continue
        # atribuição (SETVAR) — regra estrutural do dialeto
        if dial.atrib and nome == dial.atrib:
            if args:
                alvos_atribuicao.add(id(args[0]))
            if len(args) != dial.atrib_aridade:
                erros.append(_msg('erro', 'aridade', f'{nome} exige {dial.atrib_aridade} argumentos; recebeu {len(args)}', no))
            elif args[0]['tipo'] not in alvos_validos:
                erros.append(_msg('erro', 'atribuicao', f'1º argumento de {nome} deve ser '
                                  + ' ou '.join({'identificador': 'nome de variável', 'texto': 'chave texto'}.get(x, x)
                                                for x in alvos_validos), no))
            elif args[0]['tipo'] == 'identificador' and args[0]['nome'] not in declaradas:
                erros.append(_msg('erro', 'variavel_nao_declarada',
                                  f'variável "{args[0]["bruto"]}" usada em {nome} sem {dial.decl or "declaração"}', no))
            continue

        if t == 'identificador' and nome in declaradas:
            continue
        dentro, fora = base.resolver(nome, contexto, pacote)
        if not dentro:
            if fora:
                ctxs = sorted({f['contexto'] for f in fora})
                erros.append(_msg('erro', 'fora_do_contexto',
                                  f'"{no["bruto"]}" existe no dicionário só no(s) contexto(s) {", ".join(ctxs)}, '
                                  f'não em {contexto}', no, contextos=ctxs))
            else:
                sug = sugestoes(nome)
                erros.append(_msg('erro', 'funcao_inexistente',
                                  f'"{no["bruto"]}" não existe no dicionário de fórmulas'
                                  + (f' (parecidas: {", ".join(sug)})' if sug else '')
                                  + '. Não há suporte documentado — não use.', no, sugestoes=sug))
            continue

        f = dentro[0]
        usadas.append({'nome': nome, 'id': f['id'], 'contexto': f['contexto'], 'camada': f.get('camada'),
                       'url': (f.get('origens') or [{}])[0].get('url')})
        assin = [a for g in dentro for a in g.get('assinaturas', [])]
        so_sem_par = assin and all(not a.get('tem_parenteses') for a in assin)
        so_com_par = assin and all(a.get('tem_parenteses') for a in assin)
        aceitas, documentou = _aridades_aceitas(dentro)
        em_exemplos = {x['aridade']: x for g in dentro for x in g.get('aridades_em_exemplos', [])}

        if not documentou:
            avisos.append(_msg('aviso', 'sintaxe_nao_documentada',
                               f'{nome}: a documentação não traz a sintaxe — forma de chamada e argumentos '
                               f'não verificáveis', no, funcao=f['id']))
        elif com_par and len(args) in em_exemplos and (so_sem_par or len(args) not in aceitas):
            ev = em_exemplos[len(args)]
            avisos.append(_msg('aviso', 'aridade_so_em_exemplo',
                               f'{nome} com {len(args)} argumento(s) não consta da sintaxe documentada '
                               f'({"; ".join(a["texto"] for a in assin)}), mas aparece num exemplo da documentação: '
                               f'{ev["exemplo"][:80]}', no, url=ev.get('url'), funcao=f['id']))
        elif com_par and so_sem_par and args:
            erros.append(_msg('erro', 'forma_de_chamada',
                              f'{nome} é documentada sem parâmetros (sintaxe: {assin[0]["texto"]})', no, funcao=f['id']))
        elif com_par and so_sem_par:
            avisos.append(_msg('aviso', 'forma_de_chamada',
                               f'{nome} é documentada sem parênteses (sintaxe: {assin[0]["texto"]})', no, funcao=f['id']))
        elif not com_par and so_com_par and (max(aceitas) if aceitas else 0) > 0 and 0 not in aceitas:
            erros.append(_msg('erro', 'aridade',
                              f'{nome} exige argumentos — sintaxe documentada: '
                              f'{"; ".join(a["texto"] for a in assin)}', no, funcao=f['id']))
        elif com_par and aceitas and len(args) not in aceitas:
            erros.append(_msg('erro', 'aridade',
                              f'{nome} recebeu {len(args)} argumento(s); documentado: '
                              f'{"; ".join(a["texto"] for a in assin)}', no, funcao=f['id'],
                              aridades_documentadas=sorted(aceitas)))

        # tipos de literais (só onde a documentação dá o tipo do parâmetro)
        # parâmetros: da ficha mais específica que os documente
        params = next((g.get('parametros') for g in dentro if g.get('parametros')), [])
        if com_par and len(args) == len(params):
            for a, p in zip(args, params):
                tl, tp = _tipo_literal(a), p.get('tipo')
                if tl is None or tp in (None, 'desconhecido'):
                    continue
                if tp == 'numero' and tl in ('texto', 'data') and not p.get('entre_aspas_na_documentacao'):
                    avisos.append(_msg('aviso', 'tipo_argumento',
                                       f'{nome}: parâmetro {p["posicao"]} ({p.get("rotulo_documentado")}) é numérico '
                                       f'na documentação; recebeu texto', a))
                elif tp == 'data' and tl == 'texto':
                    avisos.append(_msg('aviso', 'tipo_argumento',
                                       f'{nome}: parâmetro {p["posicao"]} ({p.get("rotulo_documentado")}) é data; '
                                       f'"{a["valor"]}" não está no formato dd/mm/aaaa', a))
                elif tp in ('texto', 'data') and tl == 'numero' and p.get('entre_aspas_na_documentacao'):
                    avisos.append(_msg('aviso', 'tipo_argumento',
                                       f'{nome}: parâmetro {p["posicao"]} ({p.get("rotulo_documentado")}) é '
                                       f'documentado entre aspas; recebeu número sem aspas', a))
            # tipos em EXPRESSÃO (4d): argumento que é chamada de função com tipo de
            # retorno documentado ou inferido pelo uso; sempre aviso, nunca erro
            for a, p in zip(args, params):
                tp = p.get('tipo')
                ret = _tipo_de_retorno(a, base, contexto, pacote, declaradas)
                if ret is None or tp in (None, 'desconhecido'):
                    continue
                tr, origem = ret
                aspas = p.get('entre_aspas_na_documentacao')
                if (tp == 'numero' and tr in ('texto', 'data') and not aspas) or \
                        (tp in ('texto', 'data') and tr == 'numero' and aspas):
                    avisos.append(_msg('aviso', 'tipo_expressao',
                                       f'{nome}: parâmetro {p["posicao"]} ({p.get("rotulo_documentado")}) é '
                                       f'{"numérico" if tp == "numero" else "texto/data"} na documentação; '
                                       f'{a["nome"]} devolve {tr} ({origem})', a))

        if uso:
            for u in f.get('usos_proibidos', []):
                if u['uso'] == uso:
                    erros.append(_msg('erro', 'uso_proibido',
                                      f'{nome} não deve ser usada em fórmula de uso "{uso}" segundo a documentação',
                                      no, evidencia=u.get('evidencia'), funcao=f['id']))
        if f.get('confianca_extracao') == 'baixa':
            avisos.append(_msg('aviso', 'baixa_confianca',
                               f'{nome}: ficha extraída com baixa confiança — confira na origem', no,
                               url=(f.get('origens') or [{}])[0].get('url')))

    if dial.max_constantes and constantes > dial.max_constantes:
        erros.append(_msg('erro', 'limite_constantes',
                          f'{constantes} constantes; o dialeto permite no máximo {dial.max_constantes}'))
    # nível 3 (4e): regras da consulta declaradas no dialeto; sem chamada de
    # consulta na fórmula, nada muda
    from .consulta import validar_consulta
    e3, a3, resumo3 = validar_consulta(ast, dial_d, campos_consulta)
    erros += e3
    avisos += a3
    r = _resultado(texto, contexto, uso, ast, erros, avisos, usadas, sorted(declaradas))
    if resumo3:
        r['consulta'] = resumo3
    marcas = marcadores(ast)
    if marcas:      # só aparece com argumento marcado: a saída de sempre não muda
        r['marcadores'] = marcas
        r['pronta_para_cadastrar'] = False
    return r


def _resultado(texto, contexto, uso, ast, erros, avisos, usadas, declaradas):
    vistos, unicos = set(), []
    for u in usadas:
        if u['id'] not in vistos:
            vistos.add(u['id'])
            unicos.append(u)
    return {'formula': texto, 'contexto': contexto, 'uso': uso, 'valida': not erros,
            'erros': erros, 'avisos': avisos, 'funcoes_usadas': unicos,
            'variaveis_declaradas': declaradas, 'ast': ast}
