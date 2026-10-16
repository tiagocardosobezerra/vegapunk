"""
Lexer + parser GENÉRICOS de linguagens de fórmula, guiados por um DIALETO
(dados em `dialeto.json` do pacote de conhecimento — nada aqui é específico
de um fornecedor).

O dialeto declara: sensibilidade a caixa, separador de instruções,
delimitadores de texto, comentários, literais booleanos, operadores
(aritméticos, comparação, lógicos) e as palavras-chave de 4 estruturas:

    condicional   INICIO cond ENTAO bloco [SENAO bloco] FIM
    repeticao     INICIO bloco FIM cond
    declaracao    PALAVRA [(] ident {, ident} [)]
    atribuicao    FUNCAO(ident, expr)          (é uma chamada comum, aridade fixa)

O parser produz uma AST de dicts (com linha/coluna) e uma lista de erros
de SINTAXE. Ele não sabe se uma função existe — isso é o validador.

Argumento marcado (fase 4): `<<CÓDIGO DO EVENTO>>` é o lugar de um valor que
só o usuário conhece (um código do banco dele). Vira o nó `marcador`. Só vale
quando a marca não colide com o dialeto: se algum operador, símbolo,
comentário ou delimitador de texto do dialeto contém `<<` ou `>>`, a marca
não é reconhecida (`Dialeto.marcador_colide`) e quem entrega a solução recusa
a fórmula marcada.
"""

import re

# --------------------------------------------------------------------- lexer


class Token:
    __slots__ = ('tipo', 'valor', 'linha', 'coluna', 'bruto')

    def __init__(self, tipo, valor, linha, coluna, bruto):
        self.tipo, self.valor, self.linha, self.coluna, self.bruto = tipo, valor, linha, coluna, bruto

    def __repr__(self):
        return f'{self.tipo}:{self.valor!r}@{self.linha}:{self.coluna}'


class ErroSintaxe(Exception):
    def __init__(self, msg, linha=None, coluna=None):
        super().__init__(msg)
        self.msg, self.linha, self.coluna = msg, linha, coluna


class Dialeto:
    def __init__(self, d):
        self.d = d or {}
        self.caixa = bool(self.d.get('sensivel_a_caixa', False))
        self.sep = self.d.get('separador_instrucoes', ';')
        self.aspas = self.d.get('delimitadores_texto', ["'", '"'])
        self.coment = [tuple(c) for c in self.d.get('comentarios', [])]
        self.booleanos = {self.norm(b) for b in self.d.get('literais_booleanos', [])}
        ops = self.d.get('operadores', {})
        self.op_arit = ops.get('aritmeticos', ['+', '-', '*', '/'])
        self.op_cmp = ops.get('comparacao', ['=', '<>', '>=', '<=', '>', '<'])
        self.op_log = [self.norm(o) for o in ops.get('logicos', [])]
        est = self.d.get('estruturas', {})
        self.cond = {k: self.norm(v) for k, v in est.get('condicional', {}).items()}
        self.rep = {k: self.norm(v) for k, v in est.get('repeticao', {}).items()}
        self.decl = self.norm(est.get('declaracao', {}).get('palavra', '')) or None
        atr = est.get('atribuicao', {})
        self.atrib = self.norm(atr.get('funcao', '')) or None
        self.atrib_aridade = atr.get('aridade', 2)
        self.palavras = {v for v in list(self.cond.values()) + list(self.rep.values()) if v}
        if self.decl:
            self.palavras.add(self.decl)
        simbolos = set(self.op_arit) | set(self.op_cmp) | {'(', ')', ',', self.sep}
        simbolos |= {o for o in ops.get('logicos', []) if not o.isalpha()}
        self.simbolos = sorted(simbolos, key=len, reverse=True)
        self.max_constantes = self.d.get('limites', {}).get('max_constantes')
        delimitadores = list(self.simbolos) + list(self.aspas) + [x for c in self.coment for x in c]
        self.marcador_colide = sorted({x for x in delimitadores if MARCA[0] in x or MARCA[1] in x})

    def norm(self, s):
        return s if self.caixa else (s or '').upper()


MARCA = ('<<', '>>')
_RE_MARCADOR = re.compile(r'<<([^<>\n]+)>>')

_RE_NUM = re.compile(r'\d+(?:\.\d+)?')
_RE_IDENT = re.compile(r'[A-Za-z_À-ÿ][A-Za-z0-9_À-ÿ]*')


def tokenizar(texto, dial):
    toks, erros = [], []
    i, linha, col0 = 0, 1, 0
    n = len(texto)

    def pos():
        return linha, i - col0 + 1

    while i < n:
        c = texto[i]
        if c == '\n':
            linha += 1
            i += 1
            col0 = i
            continue
        if c.isspace():
            i += 1
            continue
        coment = next((cm for cm in dial.coment if texto.startswith(cm[0], i)), None)
        if coment:
            fim = texto.find(coment[1], i + len(coment[0]))
            if fim < 0:
                erros.append(ErroSintaxe(f'comentário "{coment[0]}" sem fechamento "{coment[1]}"', *pos()))
                break
            trecho = texto[i:fim + len(coment[1])]
            linha += trecho.count('\n')
            if '\n' in trecho:
                col0 = i + trecho.rfind('\n') + 1
            i = fim + len(coment[1])
            continue
        if c in dial.aspas:
            l, cc = pos()
            fim = texto.find(c, i + 1)
            if fim < 0:
                erros.append(ErroSintaxe(f'texto iniciado com {c} sem fechamento', l, cc))
                break
            toks.append(Token('TEXTO', texto[i + 1:fim], l, cc, texto[i:fim + 1]))
            i = fim + 1
            continue
        if c in '‘’“”':
            erros.append(ErroSintaxe(f'aspas tipográficas ({c}) não são delimitador de texto — use '
                                     + ' ou '.join(dial.aspas), *pos()))
            i += 1
            continue
        if texto.startswith(MARCA[0], i) and not dial.marcador_colide:
            l, cc = pos()
            m = _RE_MARCADOR.match(texto, i)
            if not m or not m.group(1).strip():
                erros.append(ErroSintaxe(f'argumento marcado iniciado com {MARCA[0]} sem nome ou sem {MARCA[1]}', l, cc))
                break
            toks.append(Token('MARCADOR', m.group(1).strip(), l, cc, m.group(0)))
            i = m.end()
            continue
        m = _RE_NUM.match(texto, i)
        if m:
            l, cc = pos()
            toks.append(Token('NUMERO', m.group(0), l, cc, m.group(0)))
            i = m.end()
            continue
        m = _RE_IDENT.match(texto, i)
        if m:
            l, cc = pos()
            v = dial.norm(m.group(0))
            if v in dial.palavras:
                tipo = 'PALAVRA'
            elif v in dial.booleanos:
                tipo = 'BOOLEANO'
            elif v in dial.op_log:
                tipo = 'OPLOG'
            else:
                tipo = 'IDENT'
            toks.append(Token(tipo, v, l, cc, m.group(0)))
            i = m.end()
            continue
        sim = next((s for s in dial.simbolos if texto.startswith(s, i)), None)
        if sim:
            l, cc = pos()
            tipo = ('SEP' if sim == dial.sep else 'ABRE' if sim == '(' else 'FECHA' if sim == ')' else
                    'VIRGULA' if sim == ',' else 'OPCMP' if sim in dial.op_cmp else
                    'OPLOG' if sim in dial.op_log else 'OPARIT')
            toks.append(Token(tipo, sim, l, cc, sim))
            i += len(sim)
            continue
        erros.append(ErroSintaxe(f'caractere não reconhecido pelo dialeto: {c!r}', *pos()))
        i += 1
    toks.append(Token('FIM', '', linha, i - col0 + 1, ''))
    return toks, erros


# --------------------------------------------------------------------- parser


class Parser:
    def __init__(self, toks, dial):
        self.t, self.i, self.d = toks, 0, dial

    @property
    def atual(self):
        return self.t[self.i]

    def _avancar(self):
        tk = self.t[self.i]
        self.i += 1
        return tk

    def _eh_palavra(self, v):
        return self.atual.tipo == 'PALAVRA' and self.atual.valor == v

    def _esperar_palavra(self, v, contexto):
        if not self._eh_palavra(v):
            raise ErroSintaxe(f'esperado "{v}" {contexto}, encontrado "{self.atual.bruto or "fim da fórmula"}"',
                              self.atual.linha, self.atual.coluna)
        return self._avancar()

    def programa(self, terminadores=()):
        instr = []
        while True:
            if self.atual.tipo == 'FIM' or (self.atual.tipo == 'PALAVRA' and self.atual.valor in terminadores):
                break
            if self.atual.tipo == 'SEP':
                self._avancar()
                continue
            instr.append(self.instrucao())
            if self.atual.tipo == 'SEP':
                self._avancar()
            elif self.atual.tipo == 'FIM' or (self.atual.tipo == 'PALAVRA' and self.atual.valor in terminadores):
                break
            else:
                raise ErroSintaxe(f'esperado "{self.d.sep}" ou fim de bloco antes de "{self.atual.bruto}"',
                                  self.atual.linha, self.atual.coluna)
        return {'tipo': 'bloco', 'instrucoes': instr}

    def instrucao(self):
        tk = self.atual
        if self.d.decl and self._eh_palavra(self.d.decl):
            self._avancar()
            com_par = self.atual.tipo == 'ABRE'
            if com_par:
                self._avancar()
            nomes = []
            while True:
                if self.atual.tipo != 'IDENT':
                    raise ErroSintaxe(f'esperado nome de variável após {self.d.decl}', self.atual.linha, self.atual.coluna)
                nomes.append(self._avancar().valor)
                if self.atual.tipo == 'VIRGULA':
                    self._avancar()
                    continue
                break
            if com_par:
                if self.atual.tipo != 'FECHA':
                    raise ErroSintaxe('esperado ")" fechando a declaração', self.atual.linha, self.atual.coluna)
                self._avancar()
            return {'tipo': 'declaracao', 'nomes': nomes, 'linha': tk.linha, 'coluna': tk.coluna}
        if self.d.rep.get('inicio') and self._eh_palavra(self.d.rep['inicio']):
            self._avancar()
            corpo = self.programa(terminadores=(self.d.rep['fim'],))
            self._esperar_palavra(self.d.rep['fim'], f'fechando {self.d.rep["inicio"]} (linha {tk.linha})')
            cond = self.expressao()
            return {'tipo': 'repeticao', 'corpo': corpo, 'condicao': cond, 'linha': tk.linha, 'coluna': tk.coluna}
        return self.expressao()

    def expressao(self):
        esq = self.comparacao()
        while self.atual.tipo == 'OPLOG':
            op = self._avancar()
            dir_ = self.comparacao()
            esq = {'tipo': 'logico', 'op': op.valor, 'esq': esq, 'dir': dir_, 'linha': op.linha, 'coluna': op.coluna}
        return esq

    def comparacao(self):
        esq = self.soma()
        if self.atual.tipo == 'OPCMP':
            op = self._avancar()
            dir_ = self.soma()
            return {'tipo': 'comparacao', 'op': op.valor, 'esq': esq, 'dir': dir_, 'linha': op.linha, 'coluna': op.coluna}
        return esq

    def soma(self):
        esq = self.termo()
        while self.atual.tipo == 'OPARIT' and self.atual.valor in ('+', '-'):
            op = self._avancar()
            esq = {'tipo': 'aritmetica', 'op': op.valor, 'esq': esq, 'dir': self.termo(),
                   'linha': op.linha, 'coluna': op.coluna}
        return esq

    def termo(self):
        esq = self.unario()
        while self.atual.tipo == 'OPARIT' and self.atual.valor in ('*', '/'):
            op = self._avancar()
            esq = {'tipo': 'aritmetica', 'op': op.valor, 'esq': esq, 'dir': self.unario(),
                   'linha': op.linha, 'coluna': op.coluna}
        return esq

    def unario(self):
        if self.atual.tipo == 'OPARIT' and self.atual.valor in ('-', '+'):
            op = self._avancar()
            return {'tipo': 'unario', 'op': op.valor, 'valor': self.unario(), 'linha': op.linha, 'coluna': op.coluna}
        return self.primario()

    def primario(self):
        tk = self.atual
        if tk.tipo == 'NUMERO':
            self._avancar()
            return {'tipo': 'numero', 'valor': tk.valor, 'linha': tk.linha, 'coluna': tk.coluna}
        if tk.tipo == 'TEXTO':
            self._avancar()
            return {'tipo': 'texto', 'valor': tk.valor, 'linha': tk.linha, 'coluna': tk.coluna}
        if tk.tipo == 'MARCADOR':
            self._avancar()
            return {'tipo': 'marcador', 'nome': tk.valor, 'bruto': tk.bruto, 'linha': tk.linha, 'coluna': tk.coluna}
        if tk.tipo == 'BOOLEANO':
            self._avancar()
            # alguns dialetos documentam o literal também como função sem argumentos: VERDADE()
            if self.atual.tipo == 'ABRE' and self.t[self.i + 1].tipo == 'FECHA':
                self.i += 2
                return {'tipo': 'chamada', 'nome': tk.valor, 'bruto': tk.bruto, 'args': [],
                        'com_parenteses': True, 'linha': tk.linha, 'coluna': tk.coluna}
            return {'tipo': 'booleano', 'valor': tk.valor, 'linha': tk.linha, 'coluna': tk.coluna}
        if tk.tipo == 'ABRE':
            self._avancar()
            e = self.expressao()
            if self.atual.tipo != 'FECHA':
                raise ErroSintaxe(f'esperado ")" (parêntese aberto na linha {tk.linha}, coluna {tk.coluna})',
                                  self.atual.linha, self.atual.coluna)
            self._avancar()
            return {'tipo': 'grupo', 'valor': e, 'linha': tk.linha, 'coluna': tk.coluna}
        if self.d.cond.get('inicio') and self._eh_palavra(self.d.cond['inicio']):
            return self.condicional()
        if tk.tipo == 'IDENT':
            self._avancar()
            if self.atual.tipo == 'ABRE':
                abre = self._avancar()
                args = []
                if self.atual.tipo != 'FECHA':
                    while True:
                        args.append(self.expressao())
                        if self.atual.tipo == 'VIRGULA':
                            self._avancar()
                            continue
                        break
                if self.atual.tipo != 'FECHA':
                    raise ErroSintaxe(f'esperado ")" fechando a chamada de {tk.bruto} (aberta na coluna {abre.coluna})',
                                      self.atual.linha, self.atual.coluna)
                self._avancar()
                return {'tipo': 'chamada', 'nome': tk.valor, 'bruto': tk.bruto, 'args': args,
                        'com_parenteses': True, 'linha': tk.linha, 'coluna': tk.coluna}
            return {'tipo': 'identificador', 'nome': tk.valor, 'bruto': tk.bruto,
                    'linha': tk.linha, 'coluna': tk.coluna}
        if tk.tipo == 'FIM':
            raise ErroSintaxe('fórmula terminou antes do esperado', tk.linha, tk.coluna)
        raise ErroSintaxe(f'token inesperado "{tk.bruto}"', tk.linha, tk.coluna)

    def condicional(self):
        c = self.d.cond
        tk = self._avancar()
        cond = self.expressao()
        self._esperar_palavra(c['entao'], f'após a condição do {c["inicio"]} (linha {tk.linha})')
        entao = self.programa(terminadores=tuple(v for v in (c.get('senao'), c['fim']) if v))
        senao = None
        if c.get('senao') and self._eh_palavra(c['senao']):
            self._avancar()
            senao = self.programa(terminadores=(c['fim'],))
        self._esperar_palavra(c['fim'], f'fechando o {c["inicio"]} da linha {tk.linha}')
        return {'tipo': 'condicional', 'condicao': cond, 'entao': entao, 'senao': senao,
                'linha': tk.linha, 'coluna': tk.coluna}


def analisar(texto, dialeto_dict):
    """Devolve (ast | None, erros_de_sintaxe:list[dict], tokens)."""
    dial = Dialeto(dialeto_dict)
    toks, erros_lex = tokenizar(texto, dial)
    erros = [{'nivel': 'erro', 'codigo': 'lexico', 'mensagem': e.msg, 'linha': e.linha, 'coluna': e.coluna}
             for e in erros_lex]
    if erros:
        return None, erros, toks
    p = Parser(toks, dial)
    try:
        ast = p.programa()
        if p.atual.tipo != 'FIM':
            raise ErroSintaxe(f'"{p.atual.bruto}" sem estrutura correspondente aberta', p.atual.linha, p.atual.coluna)
    except ErroSintaxe as e:
        return None, [{'nivel': 'erro', 'codigo': 'sintaxe', 'mensagem': e.msg, 'linha': e.linha, 'coluna': e.coluna}], toks
    return ast, [], toks


def marcadores(ast):
    """Argumentos marcados da AST: [{'marcador', 'funcao', 'posicao', 'linha', 'coluna'}].
    `funcao`/`posicao` só quando a marca é argumento direto de uma chamada."""
    out, vistos = [], set()
    for no in percorrer(ast):
        if no.get('tipo') == 'chamada':
            for i, a in enumerate(no.get('args', []), 1):
                if a.get('tipo') == 'marcador':
                    vistos.add(id(a))
                    out.append({'marcador': a['nome'], 'funcao': no['nome'], 'posicao': i,
                                'linha': a.get('linha'), 'coluna': a.get('coluna')})
    for no in percorrer(ast):
        if no.get('tipo') == 'marcador' and id(no) not in vistos:
            out.append({'marcador': no['nome'], 'funcao': None, 'posicao': None,
                        'linha': no.get('linha'), 'coluna': no.get('coluna')})
    return sorted(out, key=lambda m: (m['linha'] or 0, m['coluna'] or 0))


def percorrer(no):
    """Gera todos os nós da AST (pré-ordem)."""
    if isinstance(no, dict):
        yield no
        for k, v in no.items():
            if isinstance(v, (dict, list)):
                yield from percorrer(v)
    elif isinstance(no, list):
        for x in no:
            yield from percorrer(x)
