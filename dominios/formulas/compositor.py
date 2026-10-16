"""
Motor de composição e explicação.

Divisão de trabalho (a mesma do motor de consultas):
  * ENTENDER o pedido e escolher funções é feito com apoio de `buscar`
    (dicionário ranqueado) — quem raciocina sobre o pedido (a skill/LLM)
    só pode usar o que a busca devolveu;
  * COMPOR é determinístico: um PLANO estruturado (JSON) vira texto na
    sintaxe do dialeto — palavras-chave, aspas e separadores vêm do
    dialeto, nunca de string fixa no código;
  * toda composição passa pelo VALIDADOR; se houver erro, a fórmula NÃO é
    entregue como final (vai em `rascunho_rejeitado`, com os motivos).

Formato do plano (nós):
    {"chamar": "NOME", "args": [nó, ...]}       chamada (args omitido = sem parênteses)
    {"numero": 1.5} | {"texto": "01"} | {"data": "01/01/2024"} | {"booleano": true}
    {"marcador": "CÓDIGO DO EVENTO"}            argumento que só o usuário conhece: <<CÓDIGO DO EVENTO>>
    {"variavel": "X"}                           variável declarada
    {"op": "+", "esq": nó, "dir": nó}           aritmética / comparação / lógico do dialeto
    {"grupo": nó}                                (expr)
    {"negativo": nó}                             -expr
    {"se": nó, "entao": nó|[nó], "senao": nó|[nó]}
    {"declarar": ["A", "B"]}
    {"atribuir": "A", "valor": nó}
    {"repita": [nó, ...], "ate": nó}
    [nó, nó, ...]                                sequência de instruções
"""

from .sintaxe import MARCA, Dialeto, analisar
from .validador import validar
from .conhecimento import resumo_funcao


class ErroPlano(ValueError):
    pass


def _fmt_num(v):
    if isinstance(v, bool):
        raise ErroPlano('booleano em nó "numero"')
    s = repr(float(v)) if isinstance(v, float) else str(int(v))
    return s[:-2] if s.endswith('.0') else s


class Renderizador:
    def __init__(self, dialeto_dict):
        self.dial = Dialeto(dialeto_dict)
        self.d = dialeto_dict
        self.aspa = (dialeto_dict.get('delimitadores_texto') or ["'"])[0]
        bools = dialeto_dict.get('literais_booleanos') or []
        self.verdade, self.falso = (bools + [None, None])[:2]
        ops = dialeto_dict.get('operadores', {})
        self.ops = set(ops.get('aritmeticos', [])) | set(ops.get('comparacao', [])) | \
            {o.upper() for o in ops.get('logicos', [])}

    def texto(self, v):
        v = str(v)
        if self.aspa in v:
            raise ErroPlano(f'texto contém o delimitador {self.aspa}: {v!r}')
        return f'{self.aspa}{v}{self.aspa}'

    def instrucoes(self, nos, nivel):
        sep = self.dial.sep
        ind = '  ' * nivel
        return (sep + '\n').join(ind + self.no(n, nivel) for n in nos)

    def bloco(self, x, nivel):
        nos = x if isinstance(x, list) else [x]
        return self.instrucoes(nos, nivel)

    def no(self, n, nivel=0):
        if isinstance(n, list):
            return self.instrucoes(n, nivel).lstrip()
        if not isinstance(n, dict):
            raise ErroPlano(f'nó inválido: {n!r}')
        c, r = self.dial.cond, self.dial.rep
        if 'chamar' in n:
            nome = str(n['chamar']).upper()
            if 'args' not in n:
                return nome
            return f"{nome}({', '.join(self.no(a, nivel) for a in n['args'])})"
        if 'numero' in n:
            return _fmt_num(n['numero'])
        if 'texto' in n:
            return self.texto(n['texto'])
        if 'data' in n:
            return self.texto(n['data'])
        if 'marcador' in n:
            nome = str(n['marcador']).strip()
            if self.dial.marcador_colide:
                raise ErroPlano(f'a marca {MARCA[0]} {MARCA[1]} colide com o dialeto ({", ".join(self.dial.marcador_colide)}): '
                                'argumento marcado não pode ser usado')
            if not nome or any(x in nome for x in '<>\n'):
                raise ErroPlano(f'nome de argumento marcado inválido: {nome!r}')
            return f'{MARCA[0]}{nome}{MARCA[1]}'
        if 'booleano' in n:
            lit = self.verdade if n['booleano'] else self.falso
            if not lit:
                raise ErroPlano('o dialeto não documenta literais booleanos')
            return lit
        if 'variavel' in n:
            return str(n['variavel']).upper()
        if 'op' in n:
            op = str(n['op'])
            if op.upper() not in self.ops and op not in self.ops:
                raise ErroPlano(f'operador "{op}" não documentado no dialeto')
            return f"{self.no(n['esq'], nivel)} {op.upper() if op.isalpha() else op} {self.no(n['dir'], nivel)}"
        if 'grupo' in n:
            return f"({self.no(n['grupo'], nivel)})"
        if 'negativo' in n:
            return f"-{self.no(n['negativo'], nivel)}"
        if '_literal' in n:          # uso interno de `formatar` (literal já validado pelo parser)
            return str(n['_literal'])
        if 'se' in n:
            if not c:
                raise ErroPlano('o dialeto não documenta estrutura condicional')
            ind = '  ' * nivel
            s = f"{c['inicio']} {self.no(n['se'], nivel)} {c['entao']}\n{self.bloco(n['entao'], nivel + 1)}"
            if n.get('senao') is not None:
                if not c.get('senao'):
                    raise ErroPlano('o dialeto não documenta SENAO')
                s += f"\n{ind}{c['senao']}\n{self.bloco(n['senao'], nivel + 1)}"
            return s + f"\n{ind}{c['fim']}"
        if 'declarar' in n:
            if not self.dial.decl:
                raise ErroPlano('o dialeto não documenta declaração de variáveis')
            return f"{self.dial.decl} {', '.join(str(v).upper() for v in n['declarar'])}"
        if 'atribuir' in n:
            if not self.dial.atrib:
                raise ErroPlano('o dialeto não documenta atribuição')
            return f"{self.dial.atrib}({str(n['atribuir']).upper()}, {self.no(n['valor'], nivel)})"
        if 'repita' in n:
            if not r:
                raise ErroPlano('o dialeto não documenta repetição')
            ind = '  ' * nivel
            return f"{r['inicio']}\n{self.bloco(n['repita'], nivel + 1)}\n{ind}{r['fim']} {self.no(n['ate'], nivel)}"
        raise ErroPlano(f'nó desconhecido: chaves {sorted(n)}')


def compor(plano, base, contexto=None, pacote=None, uso=None):
    dial = base.dialeto(pacote)
    try:
        texto = Renderizador(dial).no(plano['expressao'] if isinstance(plano, dict) and 'expressao' in plano
                                      else plano)
    except ErroPlano as e:
        return {'formula': None, 'valida': False, 'erros': [{'nivel': 'erro', 'codigo': 'plano', 'mensagem': str(e)}],
                'avisos': [], 'explicacao': None}
    v = validar(texto, base, contexto, pacote, uso)
    saida = {'formula': texto if v['valida'] else None, 'valida': v['valida'],
             'erros': v['erros'], 'avisos': v['avisos'], 'funcoes_usadas': v['funcoes_usadas']}
    if v.get('marcadores'):     # com argumento marcado, nunca sai pronta para cadastrar
        saida['marcadores'] = v['marcadores']
        saida['pronta_para_cadastrar'] = False
    if v['valida']:
        saida['explicacao'] = explicar(texto, base, contexto, pacote, uso, validacao=v)
    else:
        saida['rascunho_rejeitado'] = texto
    return saida


# ------------------------------------------------------------------ explicação

def explicar(texto, base, contexto=None, pacote=None, uso=None, validacao=None):
    v = validacao or validar(texto, base, contexto, pacote, uso)
    dial_d = base.dialeto(pacote)
    dial = Dialeto(dial_d)
    ev = dial_d.get('evidencias', {})
    linhas, componentes = [], {}

    def desc_no(n, nivel):
        ind = '  ' * nivel
        t = n.get('tipo')
        if t == 'bloco':
            for i in n['instrucoes']:
                desc_no(i, nivel)
        elif t == 'declaracao':
            linhas.append(f"{ind}• {dial.decl} {', '.join(n['nomes'])}: declara variável(is) "
                          f"[regra do dialeto: {ev.get('declaracao', 'documentada')}]")
        elif t == 'condicional':
            linhas.append(f"{ind}• {dial.cond['inicio']} … {dial.cond['entao']} … "
                          f"{dial.cond.get('senao', '')} … {dial.cond['fim']}: condicional")
            linhas.append(f'{ind}  condição:')
            desc_no(n['condicao'], nivel + 2)
            linhas.append(f'{ind}  se verdadeira:')
            desc_no(n['entao'], nivel + 2)
            if n.get('senao'):
                linhas.append(f'{ind}  senão:')
                desc_no(n['senao'], nivel + 2)
        elif t == 'repeticao':
            linhas.append(f"{ind}• {dial.rep['inicio']} … {dial.rep['fim']}: repete o bloco até a condição ser verdadeira")
            desc_no(n['corpo'], nivel + 1)
            linhas.append(f'{ind}  condição de parada:')
            desc_no(n['condicao'], nivel + 2)
        elif t in ('comparacao', 'aritmetica', 'logico'):
            linhas.append(f"{ind}• operador {n['op']}")
            desc_no(n['esq'], nivel + 1)
            desc_no(n['dir'], nivel + 1)
        elif t == 'grupo':
            desc_no(n['valor'], nivel)
        elif t == 'unario':
            desc_no(n['valor'], nivel)
        elif t in ('chamada', 'identificador'):
            nome = n['nome']
            if nome in v.get('variaveis_declaradas', []):
                linhas.append(f'{ind}• {n["bruto"]}: variável declarada na própria fórmula')
                return
            dentro, _ = base.resolver(nome, contexto, pacote)
            if not dentro:
                linhas.append(f'{ind}• {n["bruto"]}: NÃO ENCONTRADA no dicionário')
                return
            f = dentro[0]
            componentes[f['id']] = f
            ret = f.get('tipo_retorno')
            linhas.append(f"{ind}• {nome}" + (f"({len(n.get('args', []))} arg.)" if t == 'chamada' else '') +
                          f": {f.get('descricao') or 'descrição não documentada'}"
                          + (f" [retorno: {ret}]" if ret and ret != 'nao_documentado' else ''))
            params = f.get('parametros') or []
            for i, a in enumerate(n.get('args', [])):
                p = params[i] if i < len(params) else None
                rot = (p.get('rotulo_documentado') if p else None) or f'arg {i + 1}'
                d = (p.get('descricao') if p else None)
                linhas.append(f"{ind}    {i + 1}. {rot}" + (f' — {d}' if d else '') + ':')
                desc_no(a, nivel + 3)
        elif t in ('numero', 'texto', 'booleano'):
            linhas.append(f"{ind}• constante {t}: {n['valor']}")
        elif t == 'marcador':
            linhas.append(f"{ind}• {n['bruto']}: argumento a preencher pelo usuário (o motor não conhece o valor)")

    if v['ast']:
        desc_no(v['ast'], 0)
    return {
        'formula': texto,
        'valida': v['valida'],
        'passo_a_passo': linhas,
        'componentes': [dict(resumo_funcao(f), fontes=[o.get('url') or o.get('pacote') for o in f.get('origens', [])],
                             observacoes=[o['texto'] for o in f.get('observacoes', [])][:3])
                        for f in componentes.values()],
        'erros': v['erros'],
        'avisos': v['avisos'],
    }


def formatar(texto, base, pacote=None):
    """Reescreve uma fórmula válida no estilo canônico do dialeto (identação)."""
    dial = base.dialeto(pacote)
    ast, erros, _ = analisar(texto, dial)
    if erros:
        return None, erros
    r = Renderizador(dial)
    return r.no(_ast_para_plano(ast)), []


def _ast_para_plano(n):
    t = n['tipo']
    if t == 'bloco':
        return [_ast_para_plano(i) for i in n['instrucoes']]
    if t == 'declaracao':
        return {'declarar': n['nomes']}
    if t == 'condicional':
        p = {'se': _ast_para_plano(n['condicao']), 'entao': _ast_para_plano(n['entao'])}
        if n.get('senao'):
            p['senao'] = _ast_para_plano(n['senao'])
        return p
    if t == 'repeticao':
        return {'repita': _ast_para_plano(n['corpo']), 'ate': _ast_para_plano(n['condicao'])}
    if t in ('comparacao', 'aritmetica', 'logico'):
        return {'op': n['op'], 'esq': _ast_para_plano(n['esq']), 'dir': _ast_para_plano(n['dir'])}
    if t == 'grupo':
        return {'grupo': _ast_para_plano(n['valor'])}
    if t == 'unario':
        inner = _ast_para_plano(n['valor'])
        return {'negativo': inner} if n['op'] == '-' else inner
    if t == 'chamada':
        return {'chamar': n['nome'], 'args': [_ast_para_plano(a) for a in n['args']]}
    if t == 'identificador':
        return {'chamar': n['nome']}
    if t == 'numero':
        return {'numero': float(n['valor']) if '.' in n['valor'] else int(n['valor'])}
    if t == 'texto':
        return {'texto': n['valor']}
    if t == 'booleano':
        return {'_literal': n['valor']}
    if t == 'marcador':
        return {'marcador': n['nome']}
    raise ErroPlano(t)
