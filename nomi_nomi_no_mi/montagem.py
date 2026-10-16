"""
SQL da solução (fase 4 da v3, bloco 4b), lado da DESCOBERTA.

Duas tarefas, nenhuma executa SQL nem lê linha de conteúdo:

- `montar`: junta as tabelas das intenções de schema num SELECT. Só entra
  JOIN PROVADO, por constraint (catálogo) ou pela ligação do dicionário do
  sistema; cada JOIN diz a origem. Sem caminho provado entre duas tabelas,
  sai LACUNA, nunca um JOIN palpitado. Filtro que depende do usuário sai
  MARCADO (`<<CÓDIGO DA SEÇÃO>>`), com o SQL de apoio de cada argumento; SQL
  com marca nunca sai pronto para rodar.
- `conferir`: confere o SQL escrito pelo Claude. Tabela ou coluna que não
  existe na base é erro (o SQL não é entregue); JOIN cujas colunas não são
  as de uma ligação provada é aviso.

As provas são as mesmas do `detalhar` (`grafo.agrupar_fks`), mas aqui só
valem `constraint` e `dicionário`: o agrupamento provado só pela chave da
mãe não basta para um JOIN da solução.
"""

import heapq
import re
from collections import defaultdict

from dominios.schema.config import MAX_SALTOS_CAMINHO
from nomi_nomi_no_mi.grafo import ORIGEM_CONSTRAINT, ORIGEM_DICIONARIO, agrupar_fks

PROVAS = (ORIGEM_CONSTRAINT, ORIGEM_DICIONARIO)
MARCA = ('<<', '>>')
_RE_MARCA = re.compile(r'<<([^<>\n]+)>>')


# ------------------------------------------------------------------ provas
class Provas:
    """Ligações provadas da base (constraint ou dicionário), carregadas sob demanda."""

    def __init__(self, motor):
        self.m = motor
        self._adj = None
        self._colunas = None
        self._fks = {}

    def colunas(self):
        """{TABELA: {COLUNA, ...}} de toda a base (só nomes)."""
        if self._colunas is None:
            self._colunas = defaultdict(set)
            for t, c in self.m.cur.execute('SELECT tabela, coluna FROM colunas').fetchall():
                if c != '#':
                    self._colunas[t.upper()].add(c.upper())
        return self._colunas

    def adjacencia(self):
        """Grafo não dirigido só dos pares com linha de constraint ou de dicionário."""
        if self._adj is None:
            extras = self.m._colunas_de_estrutura()[1]
            conds = [f'{c} IS NOT NULL' for c in ('constraint_nome', 'ligacao') if c in extras]
            self._adj = defaultdict(set)
            if conds:
                for f, mae in self.m.cur.execute(
                        f"SELECT DISTINCT tabela_filha, tabela_mae FROM relacionamentos WHERE {' OR '.join(conds)}"
                ).fetchall():
                    f, mae = f.upper(), mae.upper()
                    if f != mae:
                        self._adj[f].add(mae)
                        self._adj[mae].add(f)
        return self._adj

    def fks(self, a, b):
        """FKs provadas entre a e b, do ponto de vista de a, uma por conjunto de
        campos (constraint e dicionário da mesma ligação contam uma vez só;
        a constraint vem primeiro)."""
        chave = (a, b)
        if chave not in self._fks:
            fks, _ = agrupar_fks(self.m._linhas_entre(a, b), a, self.m._pk_da_mae)
            unicas = {}
            for f in sorted((f for f in fks if f['origem'] in PROVAS), key=lambda f: f['origem'] != ORIGEM_CONSTRAINT):
                k = frozenset(frozenset(((f['tabela_filha'].upper(), c['campo_filho'].strip().upper()),
                                         (f['tabela_mae'].upper(), c['campo_mae'].strip().upper())))
                              for c in f['colunas'])
                unicas.setdefault(k, f)
            self._fks[chave] = list(unicas.items())
        return self._fks[chave]

    def caminho(self, origens, destino, max_saltos=MAX_SALTOS_CAMINHO):
        """Menor caminho provado de qualquer tabela de `origens` até `destino`
        (desempate pela ordem alfabética). Lista de tabelas ou None."""
        adj = self.adjacencia()
        fila = [(0, (o,)) for o in sorted(origens)]
        heapq.heapify(fila)
        vistos = set()
        while fila:
            n, cam = heapq.heappop(fila)
            t = cam[-1]
            if t == destino:
                return list(cam)
            if t in vistos or n >= max_saltos:
                continue
            vistos.add(t)
            for v in sorted(adj.get(t, ())):
                if v not in vistos:
                    heapq.heappush(fila, (n + 1, cam + (v,)))
        return None


def _sql_apoio(tabela, chave, extra=()):
    cols = list(dict.fromkeys(list(chave) + [c for c in extra if c]))
    return f"SELECT {', '.join(cols)} FROM {tabela} ORDER BY {', '.join(chave)}"


# ------------------------------------------------------------------ montar
def montar(motor, tabelas, filtros=None, mapa=None, colunas_extra=None):
    """SELECT das `tabelas` (a primeira é a principal) só com JOIN provado.

    `filtros`: {TABELA: "NOME DO ARGUMENTO"}: a linha específica que o
    usuário escolhe; vira WHERE marcado na chave completa da tabela (a do
    cadastro, se o mapa tem a tabela; senão a PK). `mapa`: o de
    `nomi_nomi_no_mi.apoio.carregar_mapa`, para a chave e a descrição dos
    cadastros. `colunas_extra`: ['TABELA.COLUNA'] que o pedido cita (entram no
    SELECT só se a tabela entrou no SQL e a coluna existe nela)."""
    pv = Provas(motor)
    tabelas = list(dict.fromkeys(t.upper() for t in tabelas))
    cad_de = {c['tabela'].upper(): c for c in ((mapa or {}).get('cadastros') or {}).values()}
    out = {'sql': None, 'pronto_para_rodar': False, 'tabelas': [], 'joins': [], 'argumentos_a_preencher': [],
           'lacunas': [], 'avisos': [], 'erros': []}
    if not tabelas:
        return out
    juntas, linhas = [tabelas[0]], [f'FROM {tabelas[0]}']
    for t in tabelas[1:]:
        if t in juntas:
            continue
        cam = pv.caminho(juntas, t)
        if cam is None:
            out['lacunas'].append(f'sem caminho de JOIN provado (constraint ou dicionário) entre {t} e '
                                  f'{", ".join(juntas)}: a tabela fica fora do SQL')
            continue
        passos = []
        for x, y in zip(cam, cam[1:]):
            fks = pv.fks(x, y)
            if len(fks) != 1:
                passos = None
                motivo = ('nenhuma ligação provada' if not fks else
                          f'{len(fks)} ligações provadas diferentes (' + ' | '.join(f["on"] for _, f in fks) +
                          '): o usuário escolhe qual')
                out['lacunas'].append(f'JOIN entre {x} e {y}: {motivo}')
                break
            passos.append((x, y, fks[0][1]))
        if passos is None:
            continue
        for x, y, f in passos:
            if y in juntas:
                continue
            juntas.append(y)
            linhas.append(f['join'])
            out['joins'].append({'de': x, 'para': y, 'origem': f['origem'], 'constraint': f['constraint'],
                                 'on': f['on'], 'cobre_chave_da_mae': f.get('cobre_chave_da_mae')})
            if f.get('cobre_chave_da_mae') is False:
                out['avisos'].append(f'o JOIN {x}–{y} não usa a chave primária inteira de {f["tabela_mae"]}: '
                                     'pode trazer mais de uma linha; confira antes de somar ou contar')
    out['tabelas'] = juntas
    # colunas: a chave da principal e, de cada cadastro do mapa, código e descrição
    cols = [f'{tabelas[0]}.{c}' for c in sorted(motor._pk_da_mae(tabelas[0]), key=motor._pk_da_mae(tabelas[0]).get)]
    for t in juntas:
        c = cad_de.get(t)
        if c:
            cols += [f'{t}.{x}' for x in (c['coluna_codigo'], c.get('coluna_descricao')) if x]
    nomes = pv.colunas()
    for tc in colunas_extra or []:
        t, _, c = tc.upper().partition('.')
        if t in juntas and c in nomes.get(t, ()):
            cols.append(f'{t}.{c}')
    cols = list(dict.fromkeys(cols)) or [f'{tabelas[0]}.*']
    where = []
    for t, nome in (filtros or {}).items():
        t = t.upper()
        if t not in juntas:
            out['lacunas'].append(f'filtro em {t}: a tabela não entrou no SQL')
            continue
        c = cad_de.get(t)
        pk = motor._pk_da_mae(t)
        chave = list(c['chave']) if c else sorted(pk, key=pk.get)
        if not chave:
            out['lacunas'].append(f'filtro em {t}: a tabela não tem chave conhecida (nem mapa nem PK)')
            continue
        codigo = c['coluna_codigo'] if c else chave[-1]
        apoio = _sql_apoio(t, chave, [codigo, c.get('coluna_descricao') if c else None])
        for col in [codigo] + [k for k in chave if k != codigo]:
            marca = nome if col == codigo else col
            where.append(f'{t}.{col} = {MARCA[0]}{marca}{MARCA[1]}')
            arg = {'marcador': marca, 'tabela': t, 'coluna': col, 'sql_apoio': apoio}
            if len(chave) > 1 and col == codigo:
                arg['chave_completa'] = (f'o código só é único junto com {", ".join(k for k in chave if k != codigo)}'
                                         f': preencha todos da mesma linha')
            out['argumentos_a_preencher'].append(arg)
    sql = f"SELECT {', '.join(cols)}\n" + '\n'.join(linhas)
    if where:
        sql += '\nWHERE ' + '\n  AND '.join(where)
    out['sql'] = sql
    out['pronto_para_rodar'] = not out['argumentos_a_preencher'] and not out['lacunas']
    if len(cols) == 1 or cols[0].endswith('*'):
        out['avisos'].append('o SELECT traz só a chave: acrescente as colunas que o usuário pediu (use `detalhar`)')
    return out


# ------------------------------------------------------------------ conferir
_PALAVRAS = {'ON', 'WHERE', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS', 'OUTER', 'JOIN', 'GROUP', 'ORDER',
             'HAVING', 'UNION', 'WITH', 'AS', 'SELECT', 'FROM', 'AND', 'OR', 'NOLOCK'}
_RE_TABELA = re.compile(r'\b(FROM|JOIN)\s+([A-Za-z_][\w.]*)(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?', re.I)
_RE_JOIN_ON = re.compile(r'\bJOIN\s+([A-Za-z_][\w.]*)(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?\s+ON\s+(.*?)'
                         r'(?=\b(?:INNER|LEFT|RIGHT|FULL|CROSS|JOIN|WHERE|GROUP|ORDER|HAVING|UNION)\b|$)', re.I | re.S)
_RE_IGUAL = re.compile(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)')
_RE_REF = re.compile(r'\b([A-Za-z_]\w*)\.([A-Za-z_]\w*|\*)')


_RE_COL_MARCA = re.compile(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*=\s*<<([^<>\n]+)>>|<<([^<>\n]+)>>\s*=\s*'
                           r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)')


_RE_LITERAL = re.compile(r"'[^']*'|(?<![\w.])\d+(?:\.\d+)?(?![\w.])")


def literais(sql):
    """Valores literais (texto entre aspas ou número) fora dos argumentos
    marcados: num SQL aceito, o filtro tem de estar marcado, nunca com valor."""
    sem_comentario = re.sub(r'--[^\n]*|/\*.*?\*/', ' ', sql or '', flags=re.S)
    return _RE_LITERAL.findall(_RE_MARCA.sub(' ', sem_comentario))


def conferir(motor, sql, mapa=None):
    """Erros (nome que não existe) e avisos (JOIN sem prova) do SQL do Claude.
    Cada marca comparada com uma coluna (`T.COL = <<NOME>>`) ganha o SQL de
    apoio da chave completa da tabela (a do cadastro, se o mapa tem a tabela)."""
    pv = Provas(motor)
    nomes = pv.colunas()
    marcas = [m.group(1).strip() for m in _RE_MARCA.finditer(sql or '')]
    onde_marca = {}
    for m in _RE_COL_MARCA.finditer(sql or ''):
        a, c, nome = (m.group(1), m.group(2), m.group(3)) if m.group(3) else (m.group(5), m.group(6), m.group(4))
        onde_marca.setdefault(nome.strip(), (a.upper(), c.upper()))
    texto = _RE_MARCA.sub('0', sql or '')
    texto = re.sub(r"'[^']*'", "''", texto)                     # literais não são nomes
    texto = re.sub(r'--[^\n]*|/\*.*?\*/', ' ', texto, flags=re.S)
    out = {'sql': sql, 'pronto_para_rodar': False, 'joins': [], 'erros': [], 'avisos': [],
           'argumentos_a_preencher': [{'marcador': m} for m in dict.fromkeys(marcas)]}
    alias = {}
    for _, t, a in _RE_TABELA.findall(texto):
        t = t.split('.')[-1].upper()
        if t not in nomes:
            out['erros'].append(f'tabela {t} não existe na base')
            continue
        alias[t] = t
        if a and a.upper() not in _PALAVRAS:
            alias[a.upper()] = t
    for a, c in _RE_REF.findall(texto):
        t = alias.get(a.upper())
        if t is None:
            if a.upper() not in {x.upper() for x in nomes}:
                continue                      # esquema ou função: fora do que se confere aqui
            out['erros'].append(f'{a.upper()} usada sem estar no FROM/JOIN')
            continue
        if c != '*' and c.upper() not in nomes[t]:
            out['erros'].append(f'coluna {c.upper()} não existe na tabela {t}')
    for t, a, cond in _RE_JOIN_ON.findall(texto):
        t = t.split('.')[-1].upper()
        if t not in nomes:
            continue
        pares = defaultdict(set)
        for a1, c1, a2, c2 in _RE_IGUAL.findall(cond):
            t1, t2 = alias.get(a1.upper()), alias.get(a2.upper())
            if t1 and t2 and t1 != t2:
                outra = t2 if t1 == t else t1
                pares[outra].add(frozenset(((t1, c1.upper()), (t2, c2.upper()))))
        if not pares:
            out['avisos'].append(f'JOIN de {t}: condição sem igualdade entre colunas de duas tabelas; não há como '
                                 'conferir a ligação')
            continue
        for outra, usadas in pares.items():
            provadas = pv.fks(outra, t)
            achou = next(((k, f) for k, f in provadas if k == frozenset(usadas)), None)
            if achou:
                out['joins'].append({'de': outra, 'para': t, 'origem': achou[1]['origem'],
                                     'constraint': achou[1]['constraint']})
            elif any(frozenset(usadas) < k for k, _ in provadas):
                out['avisos'].append(f'JOIN {outra}–{t} usa só parte das colunas da ligação provada '
                                     f'({provadas[0][1]["on"]}): pode multiplicar linhas')
            else:
                out['avisos'].append(f'JOIN {outra}–{t} por colunas sem prova (nem constraint nem dicionário)'
                                     + (f'; ligação provada: {provadas[0][1]["on"]}' if provadas else ''))
    cad_de = {c['tabela'].upper(): c for c in ((mapa or {}).get('cadastros') or {}).values()}
    for arg in out['argumentos_a_preencher']:
        a, col = onde_marca.get(arg['marcador'], (None, None))
        t = alias.get(a) if a else None
        if not t:
            arg['motivo'] = 'a marca não está comparada com uma coluna conhecida: sem SQL de apoio'
            continue
        c = cad_de.get(t)
        pk = motor._pk_da_mae(t)
        chave = list(c['chave']) if c else sorted(pk, key=pk.get)
        arg.update({'tabela': t, 'coluna': col})
        if chave:
            arg['sql_apoio'] = _sql_apoio(t, chave, [col, c.get('coluna_descricao') if c else None])
            if len(chave) > 1:
                arg['chave_completa'] = (f'{t} só identifica uma linha pela chave inteira ({", ".join(chave)}): '
                                         'preencha todos da mesma linha')
    out['pronto_para_rodar'] = not out['erros'] and not marcas
    return out
