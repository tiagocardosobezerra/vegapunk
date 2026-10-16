"""
Extrator genérico de "fichas de função" a partir de documentação
semi-estruturada (linhas vindas de `html_linhas.converter`).

Não conhece nenhuma função específica. Reconhece PADRÕES DE LAYOUT comuns
em documentação técnica em PT-BR:

  * cabeçalho "Função NOME", "FUNÇÃO NOME:", "Função de Fórmula: NOME";
  * linha toda em negrito só com um IDENTIFICADOR em maiúsculas, seguida de
    "Sintaxe" ou de uma linha que começa com o identificador;
  * linha toda em negrito "NOME (ARG, ARG)" (cabeçalho + sintaxe);
  * título (h1..h6) só com um identificador (layout em tabela);
  * página inteira dedicada ("Função de Fórmula: NOME" no título da página).

Dentro de cada bloco, separa campos por RÓTULO (Descrição, Sintaxe,
Parâmetros, Tipo de Retorno, Exemplo, Observação, Dica, Atenção...). O que
não puder ser identificado com segurança fica como não documentado, e o
texto integral do bloco é preservado para leitura/raciocínio posterior.
"""

import re

from dominios.formulas.texto import normalizar
from dominios.formulas.sintaxe import analisar

IDENT = r'[A-Za-z_][A-Za-z0-9_]*'

_RE_FUNCAO = re.compile(
    r'^\s*(?:[-•·]\s*)?(?:\d+\s*[-.)]\s*)?fun[çc](?:[ãa]o|[õo]es)(?:\s+de\s+f[óo]rmula)?\s*:?\s+(' + IDENT + r')\b\.?\s*(?:[:=\-–]\s*)?(.*)$',
    re.I)
_RE_TITULO_PAGINA_DEDICADA = re.compile(r'fun[çc][ãa]o\s+de\s+f[óo]rmula\s*:?\s*(' + IDENT + r')\s*$', re.I)

_ROTULOS = [
    ('descricao', r'descri[çc][ãa]o'),
    ('sintaxe', r'sintaxe'),
    ('parametros', r'par[âa]metros?|\d+\s*[ºo°]\s*par[âa]metro|onde'),
    ('tipo_retorno', r'tipo\s+(?:d[eo]\s+)?retorno'),
    ('resultado', r'retorno|resultado(?:\s+da\s+f[óo]rmula)?|retorna'),
    ('exemplos', r'exemplos?(?:\s*\d+)?(?:\s+de\s+[\wçãéí ]+)?|sugest[ãa]o\s+de\s+f[óo]rmula'),
    ('observacoes', r'observa[çc][ãa]o|observa[çc][õo]es|obs\.?|dica|aten[çc][ãa]o|importante|nota'),
]
_RE_ROTULO = re.compile(
    r'^\s*(' + '|'.join(f'(?P<{k}>{p})' for k, p in _ROTULOS) + r')\s*(?:[:=\-–]+|$)\s*(.*)$', re.I)

_PALAVRAS_NAO_NOME = {
    'DE', 'DA', 'DO', 'QUE', 'PARA', 'COM', 'SEM', 'NO', 'NA', 'E', 'OU', 'O', 'A', 'OS', 'AS',
    'CONTEUDO', 'CONTEÚDO', 'EXEMPLO', 'EXEMPLOS', 'OBSERVACAO', 'SINTAXE', 'RETORNO',
    'PARAMETROS', 'IMPORTANTE', 'ATENCAO', 'DICA', 'NOTA', 'FUNCAO', 'FUNCOES', 'ONDE',
}


def _eh_nome_valido(nome, linha):
    if not re.fullmatch(IDENT, nome):
        return False
    # Nome tem que vir em MAIÚSCULAS no texto original, ou destacado em
    # negrito — evita capturar prosa ("Função receber como parâmetro...").
    # Palavras comuns ("da", "a", "que") só valem se vierem em MAIÚSCULAS
    # (há funções reais chamadas A, DA, E...).
    if normalizar(nome).upper() in _PALAVRAS_NAO_NOME:
        return nome.isupper()
    return nome.isupper() or any(nome in n for n in linha.negrito)


def _inicia_com_chamada(texto, nome):
    return re.match(r'^\s*' + re.escape(nome) + r'\s*:?\s*(\(|$)', texto, re.I) is not None


def _tem_literal(args):
    """Assinatura com valores concretos (números, datas, textos entre aspas
    com conteúdo de exemplo) é EXEMPLO de uso, não cabeçalho de função."""
    return bool(re.search(r"\(\s*\d|,\s*\d|'\s*\d|\d{2}/\d{2}", args))


def detectar_cabecalho(linhas, i):
    """Se a linha i abre o bloco de uma função, devolve (NOME, resto_da_linha,
    sintaxe_embutida, padrao). Senão, None."""
    ln = linhas[i]
    t = ln.texto
    m = _RE_FUNCAO.match(t)
    plural_sem_delimitador = m and re.match(r'^\W*fun[çc][õo]es', t, re.I) and \
        not re.search(re.escape(m.group(1)) + r'\s*[:=\-–]', t)
    # "Funções A" (índice de letras) não é cabeçalho; "Funções INTREF: ..." (erro de digitação) é
    if m and _eh_nome_valido(m.group(1), ln) and not plural_sem_delimitador:
        negrito = ' '.join(ln.negrito)
        resto = m.group(2).strip()
        destacado = bool(ln.negrito and re.search(r'fun[çc][ãa]o', negrito, re.I)) or ln.lista or ln.titulo
        # linha simples "Função NOME" (sem negrito) só é cabeçalho se for
        # curta ou se o nome vier logo seguido de delimitador (= : -)
        isolado = m.group(1).isupper() and (len(t) <= 40 or re.match(
            r'^\s*\S*\s*fun[çc][ãa]o(?:\s+de\s+f[óo]rmula)?\s*:?\s+' + IDENT + r'\s*[:=\-–]', t, re.I))
        if destacado or isolado:
            return m.group(1).upper(), resto, None, 'rotulo_funcao'
    seguintes = [x.texto for x in linhas[i + 1:i + 7]]
    if ln.toda_negrito or ln.titulo:
        m = re.fullmatch(r'\s*(' + IDENT + r')\s*\.?\s*', t)
        if m and m.group(1).isupper() and normalizar(m.group(1)).upper() not in _PALAVRAS_NAO_NOME:
            nome = m.group(1)
            if any(re.match(r'\s*sintaxe', s, re.I) or _inicia_com_chamada(s, nome) for s in seguintes) \
                    or (ln.titulo and any(s.strip().upper() == nome for s in seguintes)):
                return nome.upper(), '', None, 'identificador_destacado'
        m = re.fullmatch(r'\s*(' + IDENT + r')\s*(\(.*\))\s*', t)
        if m and m.group(1).isupper() and ln.toda_negrito and not _tem_literal(m.group(2)):
            return m.group(1).upper(), '', t.strip(), 'assinatura_destacada'
    # "NOME(args): essa função retorna ..." numa linha corrida
    m = re.match(r'^\s*([A-Z][A-Z0-9_]{2,})\s*(\([^()]*\))\s*:\s*(.+)$', t)
    if m and re.search(r'fun[çc][ãa]o|retorna', m.group(3), re.I) and not _tem_literal(m.group(2)):
        return m.group(1), m.group(3).strip(), m.group(1) + m.group(2), 'assinatura_em_linha'
    return None


def _rotulo(texto):
    m = _RE_ROTULO.match(texto)
    if not m:
        return None, texto
    for k, _ in _ROTULOS:
        if m.group(k) is not None:
            resto = m.groups()[-1] or ''
            # "Retorna o valor..." é descrição, não rótulo: só aceita
            # "retorna" como rótulo quando vem seguido de ':' (ex.: "Retorna: 1997")
            if k == 'resultado' and m.group(k).lower() == 'retorna' and ':' not in texto[:len(m.group(1)) + 2]:
                return None, texto
            return k, resto.strip()
    return None, texto


def _balancear(s, inicio):
    """Índice do ')' que fecha o '(' em s[inicio]; ignora parênteses em texto entre aspas."""
    prof, aspas = 0, None
    for j in range(inicio, len(s)):
        c = s[j]
        if aspas:
            if c == aspas:
                aspas = None
            continue
        if c in "'‘’\"" and prof >= 1:
            # só trata como aspas se houver fechamento adiante
            fecho = {'‘': '’'}.get(c, c)
            if fecho in s[j + 1:]:
                aspas = fecho if c != '’' else '’'
            continue
        if c == '(':
            prof += 1
        elif c == ')':
            prof -= 1
            if prof == 0:
                return j
    return -1


def _dividir_args(conteudo):
    args, prof, atual, aspas = [], 0, [], None
    for c in conteudo:
        if aspas:
            atual.append(c)
            if c == aspas:
                aspas = None
            continue
        if c in "'\"":
            aspas = c
        elif c == '(':
            prof += 1
        elif c == ')':
            prof -= 1
        if c == ',' and prof == 0:
            args.append(''.join(atual).strip())
            atual = []
        else:
            atual.append(c)
    ult = ''.join(atual).strip()
    if ult or args:
        args.append(ult)
    return args


def analisar_sintaxe(sintaxe, nome):
    """Lê uma linha de sintaxe documentada. Devolve dict com
    nome_na_sintaxe, tem_parenteses, argumentos (texto bruto), resto, avisos."""
    avisos = []
    s = sintaxe.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
    m = re.search(r'(' + IDENT + r')\s*:?\s*(\()', s)
    alvo = None
    for mm in re.finditer(r'(' + IDENT + r')\s*:?\s*(\()?', s):
        if mm.group(1).upper() == nome:
            alvo = mm
            break
    if alvo is None and m:
        alvo = m
        avisos.append(f'sintaxe documentada usa o nome "{m.group(1)}", diferente de "{nome}"')
    if alvo is None:
        sem = re.fullmatch(r'\s*(' + IDENT + r')\s*[.;]?\s*', s)
        if sem:
            if sem.group(1).upper() != nome:
                avisos.append(f'sintaxe documentada usa o nome "{sem.group(1)}", diferente de "{nome}"')
            return {'nome_na_sintaxe': sem.group(1).upper(), 'tem_parenteses': False,
                    'argumentos': [], 'resto': '', 'avisos': avisos}
        return None
    if not alvo.group(2):
        resto = s[alvo.end():].strip()
        return {'nome_na_sintaxe': alvo.group(1).upper(), 'tem_parenteses': False,
                'argumentos': [], 'resto': resto, 'avisos': avisos}
    ini = s.index('(', alvo.start())
    fim = _balancear(s, ini)
    if fim < 0:
        avisos.append('parênteses desbalanceados na sintaxe documentada')
        conteudo, resto = s[ini + 1:].rstrip(') '), ''
    else:
        conteudo, resto = s[ini + 1:fim], s[fim + 1:].strip()
    pedacos = conteudo.split(',')
    aspas_quebradas = len(pedacos) > 1 and all((x.count("'") + x.count('"')) % 2 for x in pedacos)
    if conteudo.count("'") % 2 or conteudo.count('"') % 2 or aspas_quebradas:
        # texto da fonte corrompido (ex.: "TABFUNC (DO FUNCIONÁRIO', DE RETORNO')"):
        # aspas não delimitam nada confiável — conta argumentos só pelas vírgulas
        avisos.append('aspas desbalanceadas na sintaxe documentada')
        args = [a.strip() for a in conteudo.split(',')] if conteudo.strip() and '(' not in conteudo else \
            _dividir_args(conteudo.replace("'", '').replace('"', ''))
    else:
        args = _dividir_args(conteudo) if conteudo.strip() else []
    return {'nome_na_sintaxe': alvo.group(1).upper(), 'tem_parenteses': True,
            'argumentos': args, 'resto': resto, 'avisos': avisos}


def _blocos(linhas, titulo_pagina):
    """Segmenta as linhas em blocos (nome, padrão, cabeçalho, linhas)."""
    blocos, atual = [], None
    for i, ln in enumerate(linhas):
        cab = detectar_cabecalho(linhas, i)
        if cab:
            nome, resto, sintaxe_embutida, padrao = cab
            # mesmo nome dentro do bloco atual = conteúdo (layout em tabela
            # repete o nome; exemplos destacados repetem a chamada)
            if atual and atual['nome'] == nome:
                atual['linhas'].append(ln)
                continue
            atual = {'nome': nome, 'padrao': padrao, 'resto_cabecalho': resto,
                     'sintaxe_embutida': sintaxe_embutida, 'linhas': [], 'linha_inicial': i}
            blocos.append(atual)
        elif atual is not None:
            atual['linhas'].append(ln)
    if not blocos:
        m = _RE_TITULO_PAGINA_DEDICADA.search(titulo_pagina or '')
        if m:
            blocos.append({'nome': m.group(1).upper(), 'padrao': 'pagina_dedicada', 'resto_cabecalho': '',
                           'sintaxe_embutida': None, 'linhas': list(linhas), 'linha_inicial': 0})
    return blocos


def _campos(bloco):
    campos = {k: [] for k, _ in _ROTULOS}
    campos['observacoes'] = []
    campos['complemento'] = []
    atual = 'descricao'
    if bloco['resto_cabecalho']:
        campos['descricao'].append(bloco['resto_cabecalho'])
    for ln in bloco['linhas']:
        t = ln.texto
        if ln.titulo:
            continue   # títulos de seção ("01. VISÃO GERAL") ficam só no texto_original
        if atual == 'descricao' and not campos['descricao'] and ln.lista and ln.toda_negrito and len(t) < 40:
            continue   # sumário ("CONTEÚDO" / "Visão Geral" / ...) de página dedicada
        if re.fullmatch(r'\s*conte[úu]do\s*', t, re.I):
            continue
        if atual == 'sintaxe' and campos['sintaxe'] and not _inicia_com_chamada(t, bloco['nome']) \
                and not _rotulo(t)[0]:
            # depois da linha de sintaxe, texto corrido não é sintaxe
            atual = 'descricao' if not campos['descricao'] else 'complemento'
        if ln.celula and (t.strip().lower() in ('função', 'funcao') or t.strip().upper() == bloco['nome']):
            continue
        rot, resto = _rotulo(t)
        if rot:
            atual = rot
            if rot == 'observacoes':
                tipo = re.match(r'\s*(\w+)', t).group(1)
                if resto:
                    campos['observacoes'].append({'tipo': tipo, 'texto': resto})
                else:
                    campos['observacoes'].append({'tipo': tipo, 'texto': ''})
            elif resto:
                campos[rot].append(resto)
            continue
        if ln.macro and atual != 'observacoes':
            campos['observacoes'].append({'tipo': ln.macro, 'texto': t})
            continue
        if atual == 'observacoes':
            if campos['observacoes'] and not campos['observacoes'][-1]['texto']:
                campos['observacoes'][-1]['texto'] = t
            elif campos['observacoes']:
                campos['observacoes'][-1]['texto'] += '\n' + t
            else:
                campos['observacoes'].append({'tipo': 'observação', 'texto': t})
        else:
            campos[atual].append(t)
    return campos


_RE_PARAM_SETA = re.compile(r'^\s*([^→:]+?)\s*(?:→|->)\s*(.+)$')
_RE_PARAM_ORDINAL = re.compile(r'^\s*(\d+)\s*[ºo°]?\s*(?:par[âa]metro)?\s*[-:–.]?\s*(.+)$', re.I)


def _descricoes_parametros(linhas_param, args):
    """Associa descrições documentadas aos argumentos (por nome ou ordinal)."""
    descr = {}
    for t in linhas_param:
        m = _RE_PARAM_SETA.match(t)
        if m:
            descr.setdefault(normalizar(m.group(1)).strip(" '\""), []).append(m.group(2).strip())
            continue
        m = re.match(r'^\s*(\d+)\s*[ºo°]\s*par[âa]metro\s*[:\-–]?\s*(.+)$', t, re.I) or \
            re.match(r'^\s*(\d+)\s*[-–]\s*(.+)$', t)
        if m:
            descr.setdefault('#' + m.group(1), []).append(m.group(2).strip())
            continue
        m = re.match(r"^\s*([A-Za-zÀ-ú0-9 _.]+?)\s*(?:'[^']*')?\s*[:\-–]\s*(.+)$", t)
        if m and len(m.group(1)) <= 30:
            descr.setdefault(normalizar(m.group(1)).strip(), []).append(m.group(2).strip())
    saida = []
    for i, a in enumerate(args):
        chave = normalizar(a).strip(" '\"")
        d = descr.get(chave) or descr.get('#' + str(i + 1)) or \
            descr.get(re.sub(r'\s+', '', chave)) or []
        saida.append(' '.join(d) if d else None)
    return saida


def inferir_tipo(arg, regras_tipos):
    """Tipo do parâmetro a partir do RÓTULO documentado na sintaxe, usando o
    vocabulário do dialeto (dado, não código). Sem casamento -> desconhecido."""
    n = normalizar(arg).upper()
    for tipo, palavras in regras_tipos.items():
        for p in palavras:
            if re.search(r'(?<![A-Z])' + re.escape(normalizar(p).upper()) + r'(?![A-Z])', n):
                return tipo
    return 'desconhecido'


# chamada em código de exemplo: identificador em MAIÚSCULAS/minúsculas
# isolado (não pedaço de palavra acentuada como "férias(1)")
_RE_CODIGO = re.compile(r'(?<![\wÀ-ÿ])([A-Za-z_][A-Za-z0-9_]*)\s*\(')


def _extrair_chamadas(texto, nomes_conhecidos=None):
    """Trechos 'NOME(...)' balanceados num texto de exemplo."""
    out = []
    s = texto.replace('‘', "'").replace('’', "'")
    for m in _RE_CODIGO.finditer(s):
        ini = s.index('(', m.start())
        fim = _balancear(s, ini)
        if fim > 0:
            out.append((m.group(1), s[m.start():fim + 1]))
    return out


def _incompleto(codigo, dialeto):
    """True se o parser do dialeto diz que o trecho TERMINOU ANTES do fim de
    uma estrutura (ex.: SE sem FIMSE) — sinal de que o exemplo continua na
    próxima linha da documentação."""
    _, erros, _ = analisar(codigo, dialeto)
    return bool(erros) and any(
        e['codigo'] == 'sintaxe' and ('fim da fórmula' in e['mensagem'] or 'terminou antes' in e['mensagem'])
        for e in erros)


def extrair_pagina(bruto, linhas, dialeto):
    """Devolve lista de fichas brutas (antes de merge) de uma página."""
    regras_tipos = dialeto.get('tipos_parametro', {})
    # palavras que abrem um "programa" de fórmula (SE, DECL...) vêm do dialeto
    est = dialeto.get('estruturas', {})
    palavras = [v for v in (est.get('condicional', {}).get('inicio'), est.get('repeticao', {}).get('inicio'),
                            est.get('declaracao', {}).get('palavra'), est.get('atribuicao', {}).get('funcao')) if v]
    re_inicio_programa = (re.compile(r'^\s*(' + '|'.join(map(re.escape, palavras)) + r')\b', re.I)
                          if palavras else None)
    fichas = []
    for b in _blocos(linhas, bruto['titulo']):
        c = _campos(b)
        nome = b['nome']
        avisos = []
        sintaxes_txt = []
        if b['sintaxe_embutida']:
            sintaxes_txt.append(b['sintaxe_embutida'])
        for s in c['sintaxe']:
            # "NOME( A ) ou NOME( A , B )" = duas assinaturas alternativas documentadas
            partes = re.split(r'\s+ou\s+', s)
            if len(partes) > 1 and all(_inicia_com_chamada(p, nome) for p in partes):
                sintaxes_txt += partes
            elif s.strip():
                sintaxes_txt.append(s)
        origem_sintaxe = 'rotulada'
        if not sintaxes_txt:
            # sem rótulo "Sintaxe": procura linha que começa com a chamada
            for campo in ('descricao', 'exemplos', 'parametros'):
                for t in c[campo]:
                    if _inicia_com_chamada(t, nome) and len(t) < 160:
                        sintaxes_txt.append(t)
                        if campo == 'descricao':
                            c['descricao'].remove(t)
                        break
                if sintaxes_txt:
                    origem_sintaxe = 'inferida_de_linha_' + campo
                    break
        assinaturas, chamadas_concretas = [], []
        for s in sintaxes_txt:
            a = analisar_sintaxe(s, nome)
            if a:
                a['texto'] = s.strip()
                # "sintaxe" com valores concretos é uso de exemplo, não assinatura
                if assinaturas and a['tem_parenteses'] and _tem_literal('(' + ','.join(a['argumentos']) + ')'):
                    chamadas_concretas.append(a['texto'])
                    continue
                assinaturas.append(a)
                avisos += a.pop('avisos')
        if not assinaturas:
            avisos.append('sintaxe não documentada/não reconhecida')
        # parâmetros a partir da primeira assinatura com parênteses
        principal = next((a for a in assinaturas if a['tem_parenteses']), assinaturas[0] if assinaturas else None)
        parametros = []
        if principal:
            linhas_param = c['parametros'] + ([principal['resto']] if principal['resto'] else [])
            descrs = _descricoes_parametros(linhas_param, principal['argumentos'])
            texto_bloco = normalizar(' '.join(x.texto for x in b['linhas']))
            for i, arg in enumerate(principal['argumentos']):
                rotulo = arg.strip()
                entre_aspas = bool(re.match(r"""^\s*['"].*['"]\s*$""", rotulo)) or rotulo.startswith(("'", '"'))
                limpo = rotulo.strip(" '\"")
                opcional = None
                if limpo and (re.search(r'\[.*\]', rotulo) or
                              re.search(re.escape(normalizar(limpo)) + r'[^.]{0,60}opciona', texto_bloco)):
                    opcional = True
                parametros.append({
                    'posicao': i + 1,
                    'rotulo_documentado': limpo or None,
                    'tipo': inferir_tipo(limpo, regras_tipos) if limpo else 'desconhecido',
                    'entre_aspas_na_documentacao': entre_aspas,
                    'descricao': descrs[i],
                    'obrigatorio': (False if opcional else 'nao_documentado'),
                })
        exemplos = []
        linhas_ex = c['exemplos'] + chamadas_concretas
        k = 0
        while k < len(linhas_ex):
            t = linhas_ex[k]
            k += 1
            # chamada de código = identificador em MAIÚSCULAS, ou o próprio nome da função
            chamadas = [txt for n, txt in _extrair_chamadas(t) if n.isupper() or n.upper() == nome]
            t = re.sub(r'^\s*\d+\s*[-)]\s*', '', t)          # "1) POS(...)" / "2- HADNOT(...)"
            # começa com palavra-chave E é código (completo ou incompleto) — não
            # prosa como "Se o evento estiver cadastrado, a função retornará 1."
            eh_programa = bool(re_inicio_programa and re_inicio_programa.match(t)) and \
                (not analisar(t, dialeto)[1] or _incompleto(t, dialeto))
            if eh_programa:
                # programas de várias linhas (SE ... ENTAO / ... / FIMSE): junta as
                # linhas seguintes enquanto o parser do dialeto disser que a
                # estrutura está INCOMPLETA (no máximo 30 linhas)
                codigo, j = t.strip(), k
                while j < len(linhas_ex) and j - k < 30 and _incompleto(codigo, dialeto):
                    codigo += '\n' + linhas_ex[j].strip()
                    j += 1
                if not _incompleto(codigo, dialeto):
                    k = j
                else:
                    codigo = t.strip()
                # programa terminado em separador (DECL x; SETVAR(...);) continua
                # nas linhas seguintes enquanto o conjunto seguir sendo código válido
                sep = dialeto.get('separador_instrucoes', ';')
                while k < len(linhas_ex) and codigo.rstrip().endswith(sep):
                    candidato = codigo + '\n' + linhas_ex[k].strip()
                    j = k + 1
                    while j < len(linhas_ex) and j - k < 30 and _incompleto(candidato, dialeto):
                        candidato += '\n' + linhas_ex[j].strip()
                        j += 1
                    if analisar(candidato, dialeto)[1]:
                        break
                    codigo, k = candidato, j
                exemplos.append({'codigo': codigo, 'texto': codigo})
            elif chamadas:
                # uma única chamada de nível superior (as demais aninhadas nela) -> só ela
                externas = [c for c in chamadas if not any(c != o and c in o for o in chamadas)]
                codigo = externas[0] if len(externas) == 1 and analisar(t, dialeto)[1] else t.strip()
                exemplos.append({'codigo': codigo, 'texto': t.strip()})
            elif exemplos:
                exemplos[-1].setdefault('explicacao', [])
                exemplos[-1]['explicacao'].append(t.strip())
        resultados = [t.strip() for t in c['resultado'] if t.strip()]
        if resultados and exemplos and len(resultados) == len(exemplos):
            for e, r in zip(exemplos, resultados):
                e['resultado'] = r
        elif resultados:
            for e in exemplos[:1]:
                e['resultado'] = ' | '.join(resultados)
        descricao = ' '.join(t for t in c['descricao'] if t.strip()).strip()
        tipo_ret = ' '.join(c['tipo_retorno']).strip() or None
        nao_doc = [k for k, v in (('descricao', descricao), ('sintaxe', assinaturas),
                                   ('tipo_retorno', tipo_ret), ('exemplos', exemplos)) if not v]
        confianca = 'alta'
        if 'sintaxe' in nao_doc or any('desbalanceada' in a for a in avisos):
            confianca = 'baixa'
        elif origem_sintaxe != 'rotulada' or avisos or nao_doc:
            confianca = 'media'
        fichas.append({
            'nome': nome,
            'descricao': descricao or None,
            'assinaturas': [{'texto': a['texto'], 'nome_na_sintaxe': a['nome_na_sintaxe'],
                             'tem_parenteses': a['tem_parenteses'], 'argumentos': a['argumentos']}
                            for a in assinaturas],
            'origem_sintaxe': origem_sintaxe if assinaturas else None,
            'parametros': parametros,
            'tipo_retorno_documentado': tipo_ret,
            'exemplos': exemplos,
            'observacoes': [o for o in c['observacoes'] if o['texto'].strip()] +
                           ([{'tipo': 'complemento', 'texto': '\n'.join(c['complemento'])}]
                            if c['complemento'] else []),
            'texto_original': '\n'.join([x.texto for x in b['linhas']]),
            'nao_documentado': nao_doc,
            'avisos_extracao': avisos,
            'confianca_extracao': confianca,
            'padrao_layout': b['padrao'],
        })
    return fichas
