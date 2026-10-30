"""
Stella orquestradora (fase 4 da v3, bloco 4b): de intenções a uma solução.

Quem quebra o pedido em intenções é o Claude que usa a skill, não este código
(o motor é só biblioteca padrão e não tem modelo de linguagem). O Claude
entrega um CONTRATO em JSON:

    {"pedido": "texto do usuário",
     "contexto": "CTX",                         (fórmulas; opcional)
     "intencoes": [
       {"id": "1", "texto": "...", "dominio": "formulas", "essencial": "consulta"},
       {"id": "2", "texto": "...", "dominio": "schema", "filtrar": "CÓDIGO DA SEÇÃO"},
       {"id": "3", "texto": "...", "dominio": "cadastro", "funcao": "FUNCAO", "posicao": 1}],
     "formula": "texto com <<ARGUMENTO MARCADO>>"   ou   "plano": {...}   (opcionais)
     "sql": "SELECT ... escrito pelo Claude"                                (opcional)
    }

SQL da solução (`nomi_nomi_no_mi/montagem.py`): com intenções de schema e sem
`sql` no contrato, a Stella MONTA o SELECT com a 1ª tabela de cada intenção,
só com JOIN provado (constraint ou dicionário, com a origem de cada um); sem
caminho provado, lacuna. `filtrar` (o nome do argumento, nas palavras do
usuário) põe um WHERE marcado na chave completa da tabela, com o SQL de
apoio. Com `sql` no contrato, a Stella CONFERE: nome que não existe é erro,
JOIN sem prova é aviso. SQL com marca nunca sai pronto para rodar.

Para cada intenção a Stella busca no domínio certo, junta o que os domínios
sabem (ligação do parâmetro de código com o cadastro do mapa, SQL de apoio) e
aponta a LACUNA com o motivo quando não há resposta. Nenhuma intenção some: a
saída tem uma entrada por intenção do contrato, na mesma ordem.

Domínios da intenção:
  - formulas: funções do dicionário. Com `essencial`, só entra função cuja
    documentação contém o termo (`dominios/formulas/essencial.py`);
  - schema: tabelas da Punk Records. Quando a intenção nomeia um cadastro do
    mapa, a tabela do mapa vem primeiro (prova: o mapa); se sobram palavras
    que a tabela do cadastro não cobre, vêm antes as vizinhas por FK que as
    cobrem no nome ou na descrição;
  - cadastro: o argumento de código de uma função (`funcao`, `posicao`)
    ligado pelo mapa a uma tabela e coluna, com o SQL de apoio.

A fórmula (texto ou plano) é validada pelo Shaka. Argumento marcado
(`<<CÓDIGO DO EVENTO>>`) é o lugar de um valor que só o usuário conhece: a
fórmula marcada nunca sai pronta para cadastrar, e a saída lista os
argumentos a preencher, com a ligação do mapa quando houver. Se a marca
colide com a sintaxe do dialeto, a fórmula marcada é recusada.

Toda solução entregue é registrada como CANDIDATA a confirmação
(`solucoes_candidatas.jsonl`, ao lado da base, na instância), exatamente
como foi entregue: com os argumentos marcados, nunca com valores.
"""

import datetime
import hashlib
import json
import os

from dominios.anexar import anexar_linha

DOMINIOS = ('formulas', 'schema', 'cadastro')
LIMITE_PADRAO = 5
USAR_SINONIMOS_DA_BASE = False  # medido no 4c: sem ganho de cobertura e top-1 pior (S14.1, S24.1); decisão do usuário
PROFUNDIDADE_PADROES = 10      # candidatos por intenção que a promoção pelo grafo enxerga
ARQUIVO_CANDIDATAS = 'solucoes_candidatas.jsonl'

# Palavras que só dizem "o cadastro" ou "cada um": não pedem outra tabela.
_PALAVRAS_DO_CADASTRO = {'cadastro', 'cadastros', 'cadastrado', 'cadastrados', 'cadastrada', 'cadastradas',
                         'cada', 'todo', 'todos', 'toda', 'todas'}


# ------------------------------------------------------------------ contrato
def validar_contrato(c):
    """Lista de erros do contrato (vazia = ok)."""
    if not isinstance(c, dict):
        return ['o contrato é um objeto JSON']
    erros = []
    if not isinstance(c.get('pedido'), str) or not c['pedido'].strip():
        erros.append('"pedido" (texto do usuário) é obrigatório')
    its = c.get('intencoes')
    if not isinstance(its, list) or not its:
        return erros + ['"intencoes" é uma lista não vazia']
    vistos = set()
    for i, it in enumerate(its, 1):
        onde = f'intenção {i}'
        if not isinstance(it, dict):
            erros.append(f'{onde}: é um objeto')
            continue
        iid = str(it.get('id', i))
        if iid in vistos:
            erros.append(f'{onde}: id "{iid}" repetido')
        vistos.add(iid)
        if not isinstance(it.get('texto'), str) or not it['texto'].strip():
            erros.append(f'{onde}: "texto" é obrigatório')
        if it.get('dominio') not in DOMINIOS:
            erros.append(f'{onde}: "dominio" é um de {", ".join(DOMINIOS)}')
        if it.get('dominio') == 'cadastro' and not it.get('funcao'):
            erros.append(f'{onde}: intenção de cadastro precisa de "funcao" (e "posicao" se a função tem mais de um código)')
        if it.get('essencial') is not None and (not isinstance(it['essencial'], str) or not it['essencial'].strip()):
            erros.append(f'{onde}: "essencial" é um texto')
        if it.get('filtrar') is not None and (it.get('dominio') != 'schema' or not isinstance(it['filtrar'], str)
                                              or not it['filtrar'].strip() or '<' in it['filtrar']
                                              or '>' in it['filtrar']):
            erros.append(f'{onde}: "filtrar" só em intenção de schema, com o nome do argumento (sem < >)')
        if it.get('capacidade') is not None and not isinstance(it['capacidade'], str):
            erros.append(f'{onde}: "capacidade" é o nome de uma capacidade do dialeto (texto)')
    if c.get('sql') is not None and (not isinstance(c['sql'], str) or not c['sql'].strip()):
        erros.append('"sql" é um texto')
    if c.get('formula') is not None and c.get('plano') is not None:
        erros.append('use "formula" ou "plano", não os dois')
    return erros


# ------------------------------------------------------------------ camadas
class Camadas:
    """O que está instalado nesta cópia. Cada domínio é opcional."""

    def __init__(self, base=None, db_path=None, instancia=None):
        self.base = base
        self.db_path = db_path if db_path and os.path.exists(db_path) else None
        self.schema = self.mapa = self.enriquecer = None
        self.vizinhos = {}
        self.desc_tabelas = {}
        if self.db_path:
            try:
                from nomi_nomi_no_mi.busca import NomiNomiNoMi
                from nomi_nomi_no_mi.apoio import carregar_mapa
                from dominios.integracao import enriquecedor_de_detalhe
            except ImportError:
                pass
            else:
                self.schema = NomiNomiNoMi(self.db_path)
                self.mapa = carregar_mapa(self.db_path)
                self.enriquecer = enriquecedor_de_detalhe(self.db_path)
                if self.mapa:
                    self._ler_vizinhos()
        self.sinonimos_busca = self._sinonimos_da_base() if USAR_SINONIMOS_DA_BASE else {}
        self.sinonimos_essencial = {}
        if base is not None:
            from dominios.formulas.essencial import carregar_sinonimos, juntar
            da_base = self._sinonimos_da_base('essencial')
            self.sinonimos_essencial = juntar(base.sinonimos, da_base if da_base is not None
                                              else carregar_sinonimos(instancia))

    def _ler_vizinhos(self):
        """Vizinhas por FK (nas duas direções) das tabelas do mapa, e descrições."""
        import sqlite3
        alvo = {c['tabela'].upper() for c in self.mapa['cadastros'].values()}
        conn = sqlite3.connect(f'file:{os.path.abspath(self.db_path)}?mode=ro', uri=True)
        try:
            for f, m in conn.execute('SELECT tabela_filha, tabela_mae FROM relacionamentos'):
                f, m = (f or '').upper(), (m or '').upper()
                if f in alvo and m != f:
                    self.vizinhos.setdefault(f, set()).add(m)
                if m in alvo and f != m:
                    self.vizinhos.setdefault(m, set()).add(f)
            for t, d in conn.execute('SELECT tabela, descricao FROM tabelas'):
                self.desc_tabelas[t.upper()] = d or ''
        finally:
            conn.close()

    def _sinonimos_da_base(self, uso='busca'):
        """Pares de sinônimo revisados da Punk Records: os da busca, ou os de
        `uso = 'essencial'` (só a regra do termo essencial; None quando a base
        não tem a migração 008, e aí vale o arquivo da instância)."""
        if not self.db_path:
            return {} if uso == 'busca' else None
        from dominios.formulas.texto import normalizar
        cols = {r[1] for r in self._consultar('PRAGMA table_info(sinonimos)')}
        if uso == 'essencial':
            if 'uso' not in cols:
                return None
            sql = "SELECT termo, sinonimo FROM sinonimos WHERE uso = 'essencial'"
        else:
            sql = 'SELECT termo, sinonimo FROM sinonimos' + (" WHERE uso IS NULL OR uso = 'busca'" if 'uso' in cols
                                                             else '')
        out = {}
        for t, s in self._consultar(sql):
            out.setdefault(normalizar(t), set()).add(normalizar(s))
        return out

    @property
    def grafo(self):
        """Grafo de coocorrência das fontes limpas (calculado uma vez)."""
        if getattr(self, '_grafo', None) is None:
            from dominios.formulas.grafo import coocorrencia
            aceitas = ()
            if self.db_path:                  # 4f: as soluções aceitas também são exemplo limpo
                from dominios.aceite import formulas_aceitas
                aceitas = formulas_aceitas(os.path.dirname(os.path.abspath(self.db_path)))
            self._grafo = coocorrencia(self.base, aceitas=aceitas) if self.base is not None and self.base.pacotes else \
                {'conhecimento': {}, 'sugestoes': {}, 'exemplos': {}, 'n_exemplos': 0, 'minimo': 0}
        return self._grafo

    def _consultar(self, sql, args=()):
        import sqlite3
        conn = sqlite3.connect(f'file:{os.path.abspath(self.db_path)}?mode=ro', uri=True)
        try:
            return conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def funcoes_leitura(self):
        """Funções que leem um campo do resultado de consulta (papel do mapa)."""
        if not self.db_path:
            return []
        return [f for (f,) in self._consultar("SELECT funcao FROM mapa_funcoes_consulta WHERE papel = 'ler_campo'")]

    def tabelas_com_colunas(self, colunas):
        if not self.db_path or not colunas:
            return []
        marcas = ','.join('?' for _ in colunas)
        return sorted(t.upper() for (t,) in self._consultar(
            f'SELECT tabela FROM colunas WHERE UPPER(coluna) IN ({marcas}) GROUP BY tabela '
            f'HAVING COUNT(DISTINCT UPPER(coluna)) = ?', [c.upper() for c in colunas] + [len(set(colunas))]))

    def modo(self):
        out = []
        if self.base is None or not self.base.pacotes:
            out.append('modo básico: fórmulas não instaladas')
        if self.schema is None:
            out.append('modo básico: schema não instalado')
        elif not self.mapa:
            out.append('modo básico: mapa não compilado (sem ligação de parâmetro nem prova pelo mapa)')
        return out

    def fechar(self):
        if self.schema is not None:
            self.schema.fechar()
            self.schema = None


# ------------------------------------------------------------------ intenções
def _ficha_resumo(f):
    return {'nome': f['nome'], 'contexto': f.get('contexto'), 'camada': f.get('camada'),
            'descricao': f.get('descricao'), 'assinaturas': [a.get('texto') for a in f.get('assinaturas') or []]}


def intencao_formulas(cam, it, contexto=None, pacote=None, limite=LIMITE_PADRAO):
    if cam.base is None or not cam.base.pacotes:
        return [], 'fórmulas não instaladas nesta cópia', []
    from dominios.formulas.essencial import filtrar
    r = cam.base.buscar(it['texto'], contexto, pacote, max(limite * 2, 10), sinonimos_extra=cam.sinonimos_busca)
    fichas, scores = [], {}
    for x in r['resultados']:
        dentro, _ = cam.base.resolver(x['nome'], contexto, pacote)
        f = next((g for g in dentro if g.get('id') == x.get('id')), dentro[0] if dentro else None)
        if f is not None:
            fichas.append(f)
            scores[id(f)] = x.get('score')
    avisos = list(r.get('avisos') or ([r['aviso']] if r.get('aviso') else []))
    aceitas, lacuna = filtrar(fichas, it.get('essencial'), cam.sinonimos_essencial)
    unicas, vistos = [], {}
    for f in aceitas:                 # a mesma função em mais de um contexto visível: uma entrada só
        if f['nome'] in vistos:
            vistos[f['nome']]['tambem_em'].append(f.get('contexto'))
            continue
        c = dict(_ficha_resumo(f), score=scores.get(id(f)), tambem_em=[])
        vistos[f['nome']] = c
        unicas.append((c, f))
    unicas = unicas[:limite]
    if cam.enriquecer and unicas:
        enriquecidas = cam.enriquecer([dict(f) for _, f in unicas])
        for (c, _), f in zip(unicas, enriquecidas):
            if f.get('ligacoes_parametros'):
                c['ligacoes_parametros'] = f['ligacoes_parametros']
    cands = [c for c, _ in unicas]
    if not cands and not lacuna:
        lacuna = 'nenhuma função do dicionário responde a esta intenção'
    if r.get('ambiguidade') and cands and not any(a.startswith('Ambiguidade') for a in avisos):
        avisos.append('ambiguidade entre os primeiros candidatos: confirme com o usuário')
    if not cands:
        avisos = []      # numa lacuna, os avisos da busca (correção aproximada, ambiguidade) são ruído
    return cands, lacuna, avisos


def _singulares(token):
    from nomi_nomi_no_mi.texto import radical
    out = {token, radical(token)}
    if token.endswith(('oes', 'aes')):
        out.add(token[:-3] + 'ao')
    if token.endswith('s'):
        out.add(token[:-1])
    return out


def _cobre(tabela, desc, tokens):
    from nomi_nomi_no_mi.texto import normalizar, radical
    alvo = normalizar(tabela) + ' ' + normalizar(desc or '')
    return all(radical(t) in alvo for t in tokens)


def _pelo_mapa(cam, texto):
    """[(tabela, motivo)] que o mapa prova para a intenção, na ordem de entrega."""
    if not cam.mapa:
        return []
    from nomi_nomi_no_mi.texto import STOP_WORDS, normalizar, tokenizar
    tokens = {t for t in tokenizar(texto) if t not in STOP_WORDS}
    out = []
    for nome, cad in sorted(cam.mapa['cadastros'].items()):
        alvo = normalizar(nome)
        usados = {t for t in tokens if alvo in _singulares(t)}
        if not usados:
            continue
        resto = tokens - usados - _PALAVRAS_DO_CADASTRO
        tab = cad['tabela'].upper()
        motivo = f'tabela do cadastro "{nome}" no mapa'
        if not resto or _cobre(tab, cam.desc_tabelas.get(tab), resto):
            out.append((tab, motivo))
            continue
        viz = sorted((t for t in cam.vizinhos.get(tab, ()) if _cobre(t, cam.desc_tabelas.get(t), resto)),
                     key=lambda t: (len(t), t))
        out += [(t, f'vizinha por FK da tabela do cadastro "{nome}" ({tab}) que cobre: {", ".join(sorted(resto))}')
                for t in viz]
        out.append((tab, motivo))
    return out


def intencao_schema(cam, it, limite=LIMITE_PADRAO):
    if cam.schema is None:
        return [], 'schema não instalado nesta cópia', []
    r = cam.schema.buscar(it['texto'])
    cands, vistos = [], set()
    for tab, motivo in _pelo_mapa(cam, it['texto']):
        if tab not in vistos:
            vistos.add(tab)
            cands.append({'tabela': tab, 'descricao': cam.desc_tabelas.get(tab), 'prova': 'mapa', 'motivo': motivo})
    for x in r['criticas']:
        t = x['tabela'].upper()
        if t not in vistos:
            vistos.add(t)
            cands.append({'tabela': x['tabela'], 'descricao': x.get('descricao'), 'prova': 'busca',
                          'score': x.get('score')})
    # a ambiguidade da busca só vale quando é a busca que decide o primeiro lugar
    avisos = [a for a in (r.get('aviso') or []) if a.startswith('Ambiguidade')] \
        if cands and cands[0]['prova'] == 'busca' else []
    cands = cands[:limite]
    return cands, (None if cands else 'nenhuma tabela da base responde a esta intenção'), avisos


def _ligacoes_da_funcao(cam, fichas):
    """Ligações dos parâmetros de código de todas as fichas visíveis da função
    (a mesma função pode estar documentada em mais de um contexto, com rótulos
    diferentes); as ligadas primeiro."""
    lgs = [x for f in cam.enriquecer([dict(g) for g in fichas]) for x in f.get('ligacoes_parametros') or []]
    return sorted(lgs, key=lambda x: not x.get('ligado'))


def intencao_cadastro(cam, it, contexto=None, pacote=None):
    if cam.base is None or not cam.base.pacotes:
        return [], 'fórmulas não instaladas nesta cópia', []
    dentro, fora = cam.base.resolver(it['funcao'], contexto, pacote)
    if not dentro:
        return [], f'a função {it["funcao"].upper()} não existe no dicionário para este contexto', []
    if not cam.enriquecer:
        return [], 'mapa não compilado: o parâmetro de código continua só um rótulo', []
    lgs = _ligacoes_da_funcao(cam, dentro)
    if it.get('posicao') is not None:
        lgs = [x for x in lgs if x.get('posicao') == it['posicao']]
    ligados = [x for x in lgs if x.get('ligado')]
    if ligados:
        return ligados[:1], None, list(ligados[0].get('avisos') or [])
    if lgs:
        return [], lgs[0].get('motivo') or 'sem ligação provada no mapa', []
    return [], f'{it["funcao"].upper()} não tem parâmetro de código' + (
        f' na posição {it["posicao"]}' if it.get('posicao') is not None else ''), []


# ------------------------------------------------------------------ fórmula
def _formula(cam, contrato, contexto, pacote, uso, intencoes):
    from dominios.formulas.compositor import compor
    from dominios.formulas.sintaxe import MARCA, Dialeto
    from dominios.formulas.validador import validar
    texto = contrato.get('formula')
    if contrato.get('plano') is not None:
        r = compor(contrato['plano'], cam.base, contexto, pacote, uso)
        texto = r.get('formula') or r.get('rascunho_rejeitado')
        if texto is None:            # o plano nem virou texto
            return {'formula': None, 'valida': False, 'pronta_para_cadastrar': False, 'erros': r['erros'],
                    'avisos': [], 'argumentos_a_preencher': []}
    dial = Dialeto(cam.base.dialeto(pacote))
    if MARCA[0] in texto and dial.marcador_colide:
        return {'formula': None, 'valida': False, 'pronta_para_cadastrar': False, 'avisos': [],
                'argumentos_a_preencher': [], 'rascunho_rejeitado': texto,
                'erros': [{'nivel': 'erro', 'codigo': 'marcador_colide',
                           'mensagem': f'a marca {MARCA[0]} {MARCA[1]} colide com o dialeto '
                                       f'({", ".join(dial.marcador_colide)}): a fórmula marcada não é entregue'}]}
    v = validar(texto, cam.base, contexto, pacote, uso)
    marcas = v.get('marcadores') or []
    ligacoes = {}
    for it in intencoes:              # ligações já achadas nas intenções de cadastro
        for c in it['candidatos'] if it['dominio'] == 'cadastro' else []:
            ligacoes[(it['funcao'], c.get('posicao'))] = c
    preencher = []
    for m in marcas:
        item = {'marcador': m['marcador'], 'funcao': m['funcao'], 'posicao': m['posicao']}
        lg = ligacoes.get((m['funcao'], m['posicao']))
        if lg is None and m['funcao'] and cam.enriquecer:
            dentro, _ = cam.base.resolver(m['funcao'], contexto, pacote)
            if dentro:
                lg = next((x for x in _ligacoes_da_funcao(cam, dentro) if x.get('posicao') == m['posicao']), None)
        if lg and lg.get('ligado'):
            item.update({k: lg.get(k) for k in ('cadastro', 'tabela', 'coluna_codigo', 'chave', 'chave_completa',
                                                 'sql_apoio') if lg.get(k) is not None})
        elif lg:
            item['motivo'] = lg.get('motivo')
        preencher.append(item)
    out = {'formula': texto if v['valida'] else None, 'valida': v['valida'],
           'pronta_para_cadastrar': bool(v['valida'] and not marcas),
           'erros': v['erros'], 'avisos': v['avisos'], 'argumentos_a_preencher': preencher,
           'funcoes_usadas': [u['nome'] for u in v['funcoes_usadas']]}
    if not v['valida']:
        out['rascunho_rejeitado'] = texto
    return out


# ------------------------------------------------------------------ solução
def solucionar(contrato, cam, pacote=None, uso=None, limite=LIMITE_PADRAO):
    """Saída agrupada por intenção, com lacunas explícitas e a fórmula validada."""
    erros = validar_contrato(contrato)
    if erros:
        return {'erros_contrato': erros}
    contexto = contrato.get('contexto')
    saida = {'pedido': contrato['pedido'], 'contexto': contexto, 'modo': cam.modo(), 'intencoes': []}
    profundidade = max(limite, PROFUNDIDADE_PADROES)
    for i, it in enumerate(contrato['intencoes'], 1):
        d = it['dominio']
        cap = _capacidade_negada(cam, it, pacote)
        if cap:
            cands, lacuna, avisos = [], cap, []
        elif d == 'formulas':
            cands, lacuna, avisos = intencao_formulas(cam, it, contexto, pacote, profundidade)
        elif d == 'schema':
            cands, lacuna, avisos = intencao_schema(cam, it, limite)
        else:
            cands, lacuna, avisos = intencao_cadastro(cam, it, contexto, pacote)
        e = {'id': str(it.get('id', i)), 'texto': it['texto'], 'dominio': d,
             'status': 'lacuna' if lacuna and not cands else 'resolvida',
             'candidatos': cands, 'lacuna': lacuna if not cands else None, 'avisos': avisos}
        for k in ('essencial', 'funcao', 'posicao', 'filtrar', 'capacidade'):
            if it.get(k) is not None:
                e[k] = it[k]
        saida['intencoes'].append(e)
    _padroes(cam, saida, pacote, limite)
    saida['lacunas'] = [e['id'] for e in saida['intencoes'] if e['status'] == 'lacuna']
    tem_formula = contrato.get('formula') is not None or contrato.get('plano') is not None
    if tem_formula and cam.base is not None and cam.base.pacotes:
        f = _formula(cam, contrato, contexto, pacote, uso, saida['intencoes'])
        usadas = set(f.get('funcoes_usadas') or [])
        for e in saida['intencoes']:
            if e['dominio'] == 'formulas' and e['status'] == 'resolvida' and usadas \
                    and not usadas & {c['nome'] for c in e['candidatos']}:
                f['avisos'].append({'nivel': 'aviso', 'codigo': 'intencao_fora_da_formula',
                                    'mensagem': f'nenhum candidato da intenção {e["id"]} ("{e["texto"]}") está na fórmula'})
        saida['formula'] = f
    elif tem_formula:
        saida['formula'] = {'formula': None, 'valida': False, 'pronta_para_cadastrar': False,
                            'erros': [{'nivel': 'erro', 'codigo': 'sem_formulas',
                                       'mensagem': 'fórmulas não instaladas: a fórmula não pode ser validada'}],
                            'avisos': [], 'argumentos_a_preencher': []}
    sql = _sql(cam, contrato, saida['intencoes'])
    if sql is not None:
        saida['sql'] = sql
        if sql.get('lacunas'):
            saida['lacunas'].append('sql')
    from dominios import nivel3
    saida['nivel'] = nivel3.nivel(saida, nivel3.papeis(cam, pacote))
    if saida['nivel'] == 3:
        saida['nivel_3'] = nivel3.bloco(cam, saida, contrato, pacote, uso)
    return saida


def _capacidade_negada(cam, it, pacote):
    """Lacuna por capacidade declarada (regra 2 do usuário): a intenção pede uma
    capacidade que o dialeto declara que não existe."""
    if not it.get('capacidade'):
        return None
    from dominios import nivel3
    valor, ev = nivel3.capacidade(cam, it['capacidade'], pacote)
    if valor is False:
        return f'o dialeto declara que não há "{it["capacidade"]}"' + (f' ({ev})' if ev else '')
    return None


def _padroes(cam, saida, pacote, limite):
    """Padrões antes de funções (`dominios/padroes.py`): promoção pelo grafo,
    padrões documentados do pedido, colunas lidas como prova de schema; e as
    vizinhas de cada candidato. Corta as listas no `limite` no fim."""
    if cam.base is None or not cam.base.pacotes:
        return
    from dominios import padroes
    from dominios.formulas.grafo import vizinhas
    from nomi_nomi_no_mi.texto import normalizar
    its = saida['intencoes']
    from dominios import nivel3
    nivel3.aplicar_escada(its, nivel3.papeis(cam, pacote))
    padroes.promover_pelo_grafo(its, cam.grafo)
    escolhidos = padroes.selecionar_padroes(cam.base, its, pacote)
    if escolhidos:
        saida['padroes'] = escolhidos
    leitura = cam.funcoes_leitura()
    for p in escolhidos[:1]:
        campos = padroes.campos_lidos(cam.base, p['formula'], leitura, pacote)
        tabelas = cam.tabelas_com_colunas(campos)
        if not tabelas:
            continue
        p['campos_lidos'], p['tabelas_com_os_campos'] = campos, tabelas
        for e in its:
            if e['dominio'] != 'schema':
                continue
            from nomi_nomi_no_mi.texto import STOP_WORDS, radical, tokenizar
            toks = {radical(t) for t in tokenizar(e['texto']) if t not in STOP_WORDS}
            citados = [c for c in campos if any(t in normalizar(c) for t in toks)]
            if not citados:
                continue
            ordem = {c['tabela'].upper(): i for i, c in enumerate(e['candidatos'])}
            if cam.schema is not None:
                for i, x in enumerate(cam.schema.buscar(e['texto'], 100)['criticas']):
                    ordem.setdefault(x['tabela'].upper(), len(ordem) + i)
            novas = [{'tabela': t, 'descricao': cam.desc_tabelas.get(t) or _descricao(cam, t), 'prova': 'padrao',
                      'motivo': f'tem as colunas que o padrão {p["id"]} lê ({", ".join(campos)}); '
                                f'a intenção cita {", ".join(citados)}'}
                     for t in sorted(tabelas, key=lambda t: (ordem.get(t, 10 ** 6), t))]
            e['candidatos'] = novas + [c for c in e['candidatos'] if c['tabela'].upper() not in set(tabelas)]
            e['status'], e['lacuna'] = 'resolvida', None
    for e in its:
        if e['dominio'] == 'formulas':
            for c in e['candidatos']:
                vz = vizinhas(cam.grafo, c['nome'])
                if vz:
                    c['vizinhas'] = [{'funcao': n, 'exemplos': k} for n, k in vz[:5]]
        e['candidatos'] = e['candidatos'][:limite]


def _descricao(cam, tabela):
    r = cam._consultar('SELECT descricao FROM tabelas WHERE UPPER(tabela) = ?', (tabela,)) if cam.db_path else []
    return r[0][0] if r else None


def _sql(cam, contrato, intencoes):
    """SQL da solução: conferido (o do Claude) ou montado (só JOIN provado)."""
    from_contrato = contrato.get('sql')
    schema = [(it, e) for it, e in zip(contrato['intencoes'], intencoes) if e['dominio'] == 'schema']
    if from_contrato is None and not any(e['status'] == 'resolvida' for _, e in schema):
        return None
    if cam.schema is None:
        return {'sql': None, 'pronto_para_rodar': False, 'erros': [], 'avisos': [], 'argumentos_a_preencher': [],
                'lacunas': ['schema não instalado: o SQL não pode ser montado nem conferido']}
    from nomi_nomi_no_mi import montagem
    if from_contrato is not None:
        return dict(montagem.conferir(cam.schema, from_contrato, cam.mapa), origem='escrito pelo Claude, conferido')
    tabelas, filtros, avisos = [], {}, []
    for it, e in schema:
        if e['status'] != 'resolvida':
            continue
        t = e['candidatos'][0]['tabela'].upper()
        tabelas.append(t)
        if e['avisos']:
            avisos.append(f'intenção {e["id"]}: a tabela {t} é o 1º lugar de uma busca ambígua; confirme com o usuário')
        if it.get('filtrar'):
            filtros[t] = it['filtrar'].strip()
    r = montagem.montar(cam.schema, tabelas, filtros, cam.mapa)
    r['avisos'] = avisos + r['avisos']
    r['origem'] = 'montado pela Stella'
    return r


# ------------------------------------------------------------------ medição
class MotorDeCobertura:
    """Adaptador do avaliador de cobertura de intenções (`dominios/cobertura.py`)
    para o caminho da Stella orquestradora. `preparar(caso)` resolve o caso
    inteiro de uma vez (a promoção e os padrões dependem das outras intenções
    do mesmo pedido); as consultas por intenção leem o resultado. Só leitura."""

    def __init__(self, cam, limite=10):
        self.cam, self.limite = cam, limite
        self._caso, self._saida = {}, {}

    def preparar(self, caso):
        contrato = {'pedido': caso.get('pedido') or caso['id'], 'contexto': caso.get('contexto'),
                    'intencoes': [{k: it[k] for k in ('id', 'texto', 'dominio', 'essencial', 'funcao', 'posicao',
                                                      'filtrar', 'capacidade')
                                   if it.get(k) is not None} for it in caso['intencoes']]}
        s = solucionar(contrato, self.cam, limite=self.limite)
        self._saida = s
        self._caso = {e['texto']: e for e in s.get('intencoes', [])}

    def nivel(self):
        return self._saida.get('nivel')

    def consulta_nova(self):
        b = (self._saida.get('nivel_3') or {}).get('consulta_nova')
        return bool(b and b.get('sql') and b.get('instrucao') and (b.get('modelo') or {}).get('valida'))

    def _resolvida(self, texto, dominio):
        e = self._caso.get(texto)
        return e if e is not None and e['dominio'] == dominio else None

    def formulas(self, texto, contexto, essencial=None):
        e = self._resolvida(texto, 'formulas')
        if e is not None:
            return [c['nome'] for c in e['candidatos']]
        it = {'texto': texto, 'essencial': essencial}
        return [c['nome'] for c in intencao_formulas(self.cam, it, contexto, None, self.limite)[0]]

    def schema(self, texto):
        e = self._resolvida(texto, 'schema')
        if e is not None:
            return [c['tabela'] for c in e['candidatos']]
        return [c['tabela'] for c in intencao_schema(self.cam, {'texto': texto}, self.limite)[0]]

    def ligacao(self, funcao, contexto, posicao=None):
        c = intencao_cadastro(self.cam, {'texto': '', 'funcao': funcao, 'posicao': posicao}, contexto)[0]
        return c[0]['cadastro'] if c else None


# ------------------------------------------------------------------ candidata
def caminho_candidatas(db_path=None, instancia=None):
    pasta = instancia or (os.path.dirname(os.path.abspath(db_path)) if db_path else None) or \
        os.environ.get('VEGAPUNK_EGGHEAD') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'egghead')
    return os.path.join(pasta, ARQUIVO_CANDIDATAS)


def registrar_candidata(saida, caminho):
    """Guarda a solução como foi entregue (argumentos marcados, nunca valores).
    Devolve o id da candidata, ou None se a pasta da instância não existe."""
    if not os.path.isdir(os.path.dirname(caminho)):
        return None
    f = saida.get('formula') or {}
    reg = {'tipo': 'candidata',
           'data': datetime.datetime.now().isoformat(timespec='seconds'),
           'pedido': saida['pedido'], 'contexto': saida.get('contexto'),
           'intencoes': [dict({k: e.get(k) for k in ('id', 'texto', 'dominio', 'essencial', 'funcao', 'posicao',
                                                         'status')},
                              candidatos=[c.get('nome') or c.get('cadastro') or c.get('tabela')
                                          for c in e['candidatos']])
                         for e in saida['intencoes']],
           'formula': f.get('formula') or f.get('rascunho_rejeitado'),
           'valida': f.get('valida'), 'pronta_para_cadastrar': f.get('pronta_para_cadastrar'),
           'argumentos_marcados': list(dict.fromkeys(a['marcador'] for a in f.get('argumentos_a_preencher') or []))}
    q = saida.get('sql')
    if q:
        reg['sql'] = q.get('sql')
        reg['sql_pronto_para_rodar'] = q.get('pronto_para_rodar')
        reg['sql_argumentos_marcados'] = list(dict.fromkeys(a['marcador'] for a in q.get('argumentos_a_preencher') or []))
        # 4f: o aceite do SQL depende da conferência (nomes, JOIN provado, sem valor literal)
        from nomi_nomi_no_mi.montagem import literais
        reg['sql_erros'] = list(q.get('erros') or [])
        reg['sql_lacunas'] = list(q.get('lacunas') or [])
        reg['sql_joins_sem_prova'] = [a for a in q.get('avisos') or []
                                      if a.startswith('JOIN') and ('sem prova' in a or 'parte das colunas' in a
                                                                   or 'sem igualdade' in a)]
        reg['sql_literais'] = literais(q.get('sql'))
    reg['id'] = hashlib.sha1(json.dumps({k: v for k, v in reg.items() if k != 'data'}, ensure_ascii=False,
                                        sort_keys=True).encode('utf-8')).hexdigest()[:12]
    try:
        anexar_linha(caminho, json.dumps(reg, ensure_ascii=False))   # trava: processos em paralelo
    except OSError:
        return None   # instância só de leitura: a solução sai, só não fica como candidata
    return reg['id']
