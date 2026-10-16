"""
Grafo de FKs: expansão das tabelas críticas pelos vizinhos (paginada) e
consolidação de críticas + expandidas.

Parte do Nomi Nomi no Mi, movida sem mudança de algoritmo do antigo
`scripts/nomi_nomi_no_mi.py` (fase 1 da v3).
"""

from typing import Dict, List, Set

import heapq
from collections import Counter, defaultdict

from dominios.schema.config import MAX_PAGINAS, MAX_SALTOS_CAMINHO, TAMANHO_PAGINA


def _join(tabela, fk):
    """JOIN pronto, do ponto de vista de `tabela`, usando a chave completa."""
    filha, mae = fk['tabela_filha'], fk['tabela_mae']
    alias_mae = f'{mae}_MAE' if filha == mae else mae
    on = ' AND '.join(f"{filha}.{c['campo_filho']} = {alias_mae}.{c['campo_mae']}" for c in fk['colunas'])
    if filha == mae:
        return on, f'INNER JOIN {mae} AS {alias_mae} ON {on}'
    outra = mae if tabela == filha else filha
    return on, f'INNER JOIN {outra} ON {on}'


ORIGEM_CONSTRAINT = 'constraint'
ORIGEM_LIGACAO_UNICA = 'ligação única + chave da mãe'
ORIGEM_CHAVE_DA_MAE = 'chave da mãe'
ORIGEM_DICIONARIO = 'dicionário'


def _fk(tabela, nome, origem, filha, mae, colunas):
    fk = {'constraint': nome, 'origem': origem, 'tabela_filha': filha, 'tabela_mae': mae,
          'papel': 'ambas' if filha == mae else ('filha' if tabela == filha else 'mae'),
          'colunas': [{'campo_filho': b['campo_filho'], 'campo_mae': b['campo_mae']} for b in colunas]}
    fk['composta'] = len(fk['colunas']) > 1
    fk['on'], fk['join'] = _join(tabela, fk)
    return fk


def provar_agrupamento(linhas: List[Dict], pk: Dict[str, int]):
    """Agrupamento das linhas sem constraint de UM par (filha, mãe), só
    quando a estrutura o prova pela chave primária da mãe (fase 2b da v3).

    `pk`: colunas da PK da mãe (em maiúsculas) -> posição. Devolve
    (origem, [grupos de linhas]) ou (motivo, None):
    - ligação única + chave da mãe: nenhum campo da filha nem da mãe se
      repete e os campos da mãe são exatamente a PK. Uma ligação só, nesta
      ordem da PK.
    - chave da mãe: há repetição, mas os campos da mãe são exatamente a PK,
      cada coluna da PK aparece 1 ou N vezes, e só uma coluna tem variantes
      (as outras se repetem iguais ou aparecem uma vez): N ligações, cada
      uma com as colunas fixas e uma das variantes. Uma forma só.
    - senão, o motivo: mae_sem_pk, chave_incompleta ou agrupamento_ambiguo.
      Uma ligação com o mesmo campo da filha em duas colunas da mãe também é
      ambígua: nenhuma FK física do gabarito tem essa forma.
    Nunca um palpite: em qualquer dúvida, devolve o motivo.
    Medido contra os pares com constraint declarada (gabarito físico): 0 erros."""
    if not pk:
        return 'mae_sem_pk', None
    chave = lambda l: (l['campo_filho'].strip().upper(), l['campo_mae'].strip().upper())  # noqa: E731
    vistas, unicas = set(), []          # linha repetida igual = a mesma coluna em outra ligação
    for l in linhas:
        if chave(l) not in vistas:
            vistas.add(chave(l))
            unicas.append(l)
    mae_u = defaultdict(int)
    filho_u = defaultdict(int)
    mae = defaultdict(int)
    for l in unicas:
        mae_u[chave(l)[1]] += 1
        filho_u[chave(l)[0]] += 1
    for l in linhas:
        mae[chave(l)[1]] += 1
    conj, K = set(mae_u), set(pk)
    ordem = lambda l: (pk.get(chave(l)[1], 0), chave(l)[0])  # noqa: E731
    if max(mae_u.values()) == 1 and max(filho_u.values()) == 1:
        if conj != K:
            return 'chave_incompleta', None
        if len(unicas) < len(linhas):
            # linha repetida igual = a mesma coluna em duas ligações: a PK sozinha
            # não prova como separá-las (o dicionário desmentiu a junção, fase 3-0b)
            return 'agrupamento_ambiguo', None
        return ORIGEM_LIGACAO_UNICA, [sorted(unicas, key=ordem)]
    if conj != K:
        return 'agrupamento_ambiguo', None
    n = max(mae.values())
    if any(v not in (1, n) for v in mae.values()):
        return 'agrupamento_ambiguo', None
    variantes = [k for k in K if mae_u[k] > 1]
    if len(variantes) > 1 or (variantes and mae[variantes[0]] != n):
        return 'agrupamento_ambiguo', None
    if not variantes:                   # só o campo da filha se repete: forma sem gabarito
        return 'agrupamento_ambiguo', None
    fixas = [l for l in unicas if chave(l)[1] != variantes[0]]
    grupos = [sorted(fixas + [l], key=ordem) for l in unicas if chave(l)[1] == variantes[0]]
    if any(len({chave(l)[0] for l in g}) < len(g) for g in grupos):
        return 'agrupamento_ambiguo', None
    return ORIGEM_CHAVE_DA_MAE, grupos


def _campos(grupo):
    return frozenset((b['campo_filho'].strip().upper(), b['campo_mae'].strip().upper()) for b in grupo)


def agrupar_fks(linhas: List[Dict], tabela: str, pk_da_mae=None, relatorio=None):
    """Agrupa as linhas de FK (fase 2 da v3; 2b e 3-0b para as sem constraint).

    `linhas`: dicts com tabela_filha, campo_filho, tabela_mae, campo_mae e,
    se a base tiver, constraint_nome, ordem e ligacao (número da ligação no
    dicionário do sistema). `pk_da_mae(tabela)`: PK da mãe (colunas em
    maiúsculas -> posição), ou None quando a base não tem.
    Devolve (fks, sem_constraint):
    - fks: uma entrada por FK, com as colunas e o JOIN pronto. A `origem` diz
      o que prova o agrupamento, nesta ordem de força:
        constraint  (nome da FK física, catálogo);
        dicionário  (a ligação do dicionário do sistema; igual às constraints
                     declaradas em todos os pares do gabarito);
        ligação única + chave da mãe / chave da mãe  (`provar_agrupamento`).
      `confirmado_pelo_dicionario`: True quando o dicionário traz a mesma
      ligação, None quando o par não tem ligação do dicionário.
      `cobre_chave_da_mae`: os campos da mãe são exatamente a PK dela (None =
      PK desconhecida).
    - sem_constraint: as linhas que nada prova, com o `motivo`. Não são
      agrupadas por palpite.
    Constraint x dicionário são comparados por conjunto de campos dentro do
    par (linhas idênticas são intercambiáveis). Em conflito, nenhum vence: as
    linhas do par vão para sem_constraint (conflito_constraint_dicionario).
    Dicionário x chave da mãe: vence o dicionário. `relatorio` (Counter),
    se passado, conta os dois conflitos.
    """
    par_de = lambda r: (r['tabela_filha'], r['tabela_mae'])  # noqa: E731
    campo = lambda r: (r['campo_filho'].strip().upper(), r['campo_mae'].strip().upper())  # noqa: E731
    base = [{k: r[k] for k in ('tabela_filha', 'campo_filho', 'tabela_mae', 'campo_mae')} for r in linhas]
    por_par = defaultdict(list)
    for i, r in enumerate(linhas):
        por_par[par_de(r)].append(i)

    def pk_de(mae):
        return (pk_da_mae(mae) if pk_da_mae else None) or {}

    def com_cobertura(fk, confirmado):
        pk = pk_de(fk['tabela_mae'])
        fk['confirmado_pelo_dicionario'] = confirmado
        fk['cobre_chave_da_mae'] = ({c['campo_mae'].strip().upper() for c in fk['colunas']} == set(pk)) if pk else None
        return fk

    fks_constraint, inferidas, motivos, provadas = [], [], {}, set()
    for (filha, mae), idxs in sorted(por_par.items()):
        pk = pk_de(mae)
        por_constraint = defaultdict(list)
        for i in idxs:
            if linhas[i].get('constraint_nome'):
                por_constraint[linhas[i]['constraint_nome']].append((linhas[i].get('ordem') or 0, i))
        soltas = [i for i in idxs if not linhas[i].get('constraint_nome')]
        com_lig = [i for i in idxs if linhas[i].get('ligacao') is not None]

        confirmado = None
        resto_dic = []                      # ligações do dicionário para as linhas soltas
        if com_lig:
            por_ligacao = defaultdict(list)
            for i in com_lig:
                por_ligacao[linhas[i]['ligacao']].append(i)
            fs_dic = Counter(frozenset(campo(linhas[i]) for i in g) for g in por_ligacao.values())
            fs_con = Counter(frozenset(campo(linhas[i]) for _, i in g) for g in por_constraint.values())
            sobra = fs_dic - fs_con
            soltas_lig = [i for i in soltas if linhas[i].get('ligacao') is not None]
            consistente = (not (fs_con - fs_dic)
                           and Counter(c for fs, n in sobra.items() for c in fs for _ in range(n))
                           == Counter(campo(linhas[i]) for i in soltas_lig))
            if not consistente:
                if relatorio is not None:
                    relatorio['conflito_constraint_dicionario'] += 1
                for i in idxs:
                    motivos[i] = 'conflito_constraint_dicionario'
                continue
            confirmado = True
            resto_dic = sorted(sobra, key=lambda fs: sorted(fs))
        for nome, itens in por_constraint.items():
            itens.sort()
            fks_constraint.append(((nome, filha, mae), com_cobertura(
                _fk(tabela, nome, ORIGEM_CONSTRAINT, filha, mae, [base[i] for _, i in itens]), confirmado)))
        if not soltas:
            continue

        soltas_lig = [i for i in soltas if linhas[i].get('ligacao') is not None]
        if soltas_lig:
            soltas_sem_lig = [i for i in soltas if linhas[i].get('ligacao') is None]
            origem, grupos_pk = (provar_agrupamento([base[i] for i in soltas_lig], pk)
                                 if len(idxs) >= 2 and len(soltas_lig) >= 2 and not soltas_sem_lig
                                 else (None, None))
            if grupos_pk is not None and {_campos(g) for g in grupos_pk} == set(resto_dic):
                for g in grupos_pk:         # chave da mãe e dicionário concordam: a mesma FK de antes
                    inferidas.append(com_cobertura(_fk(tabela, None, origem, filha, mae, g), True))
            else:                           # o dicionário vence (ou é a única prova)
                if grupos_pk is not None and relatorio is not None:
                    relatorio['dicionario_vence_chave_da_mae'] += 1
                linha_de = {}
                for i in soltas_lig:
                    linha_de.setdefault(campo(linhas[i]), base[i])
                ordem = lambda b: (pk.get(b['campo_mae'].strip().upper(), 0), b['campo_filho'].strip().upper())  # noqa: E731
                for fs in resto_dic:
                    g = sorted((linha_de[c] for c in fs), key=ordem)
                    inferidas.append(com_cobertura(_fk(tabela, None, ORIGEM_DICIONARIO, filha, mae, g), True))
            provadas |= set(soltas_lig)
            for i in soltas_sem_lig:        # linha sem ligação num par que o dicionário cobre em parte
                motivos[i] = 'resto_de_ligacao_do_dicionario'
            continue

        if len(idxs) < 2:
            motivos[soltas[0]] = 'ligacao_simples'
            continue
        if len(soltas) < 2:
            motivos[soltas[0]] = 'resto_de_constraint_parcial'
            continue
        origem, grupos_pk = provar_agrupamento([base[i] for i in soltas], pk)
        if grupos_pk is None:
            for i in soltas:
                motivos[i] = origem
            continue
        provadas |= set(soltas)
        for g in grupos_pk:
            inferidas.append(com_cobertura(_fk(tabela, None, origem, filha, mae, g), None))

    fks = [fk for _, fk in sorted(fks_constraint, key=lambda x: x[0])] + inferidas
    sem_constraint = [{**base[i], 'motivo': motivos[i]} for i in range(len(linhas))
                      if i in motivos and i not in provadas]
    return fks, sem_constraint


def menor_caminho(adjacencia: Dict[str, Set[str]], origem: str, destino: str, max_saltos: int = MAX_SALTOS_CAMINHO):
    """Menor caminho (em saltos de FK) entre duas tabelas, ou None.

    Critério de desempate entre caminhos do mesmo tamanho, nesta ordem: a
    menor soma de vizinhos das tabelas intermediárias (evita atravessar uma
    tabela "hub", ligada a quase tudo) e a ordem alfabética do caminho.
    Determinístico."""
    if origem == destino:
        return [origem]
    grau = lambda t: len(adjacencia.get(t, ()))   # noqa: E731
    fila = [(0, 0, (origem,))]
    melhor = {origem: (0, 0, (origem,))}
    while fila:
        saltos, custo, caminho = heapq.heappop(fila)
        atual = caminho[-1]
        if atual == destino:
            return list(caminho)
        if saltos >= max_saltos or melhor.get(atual) < (saltos, custo, caminho):
            continue
        for viz in sorted(adjacencia.get(atual, ())):
            if viz in caminho:
                continue
            chave = (saltos + 1, custo + (grau(viz) if viz != destino else 0), caminho + (viz,))
            if viz not in melhor or chave < melhor[viz]:
                melhor[viz] = chave
                heapq.heappush(fila, chave)
    return None


class GrafoMixin:
    """Expansão por FK do `NomiNomiNoMi` (ver busca.py)."""

    def _expandir_com_vizinhos_paginados(self, tabelas_ancoras: List[str]) -> List[Dict]:
        """Expande tabelas críticas com vizinhos via FK (relacionamentos), paginado.

        Item 2 (auditoria de inovação): antes, um vizinho só entrava
        aqui se seu prefixo estivesse cadastrado em `sistemas` — mesmo
        que a FK em si (tabela `relacionamentos`) já fosse um vínculo
        estrutural real e verificado. Isso não tinha uma justificativa
        forte: a FK É a prova de que a tabela participa do mesmo
        contexto de negócio, independente de alguém ter cadastrado o
        prefixo dela em `sistemas` ou não. Por isso o filtro por módulo
        foi removido inteiramente aqui (nunca mais gera `IN ()` vazio
        nem exclui vizinho nenhum) — diferente da busca crítica, aqui
        não existe "penalidade" a aplicar porque vizinhos não têm score,
        só entram ou não entram como candidato a JOIN.
        """
        expandidas: Set[str] = set()
        anchor_set = set(tabelas_ancoras)

        for tabela in tabelas_ancoras[:30]:
            pagina = 0
            while pagina < MAX_PAGINAS:
                offset = pagina * TAMANHO_PAGINA
                sql = """
                SELECT DISTINCT tabela_vizinha
                FROM (
                    SELECT DISTINCT tabela_mae as tabela_vizinha
                    FROM relacionamentos
                    WHERE tabela_filha = ?
                    UNION ALL
                    SELECT DISTINCT tabela_filha as tabela_vizinha
                    FROM relacionamentos
                    WHERE tabela_mae = ?
                )
                ORDER BY tabela_vizinha
                LIMIT ? OFFSET ?
                """
                self.cur.execute(
                    sql,
                    (tabela, tabela, TAMANHO_PAGINA, offset)
                )
                vizinhos = [row[0] for row in self.cur.fetchall()]
                if not vizinhos:
                    break
                expandidas.update(v for v in vizinhos if v not in anchor_set)
                if len(expandidas) >= 100:
                    break
                pagina += 1

        # Fase 2: a lista continua a mesma (ordem alfabética, ~100 vizinhos),
        # mas o corte deixa de ser silencioso: guarda quantos vizinhos
        # existiam no total, para o buscar avisar.
        self._corte_vizinhos = (len(expandidas), self._total_vizinhos(tabelas_ancoras[:30], anchor_set))
        return [{'tabela': t} for t in sorted(expandidas)]

    def _total_vizinhos(self, ancoras: List[str], excluir: Set[str]) -> int:
        if not ancoras:
            return 0
        marcas = ','.join('?' for _ in ancoras)
        self.cur.execute(
            f"""SELECT COUNT(DISTINCT v) FROM (
                   SELECT tabela_mae AS v FROM relacionamentos WHERE tabela_filha IN ({marcas})
                   UNION ALL
                   SELECT tabela_filha AS v FROM relacionamentos WHERE tabela_mae IN ({marcas})
               ) WHERE v NOT IN ({','.join('?' for _ in excluir) or "''"})""",
            list(ancoras) + list(ancoras) + sorted(excluir))
        return self.cur.fetchone()[0]

    def _adjacencia(self) -> Dict[str, Set[str]]:
        """Grafo não dirigido de tabelas ligadas por FK (carregado uma vez)."""
        if getattr(self, '_adj', None) is None:
            adj = defaultdict(set)
            for f, m in self.cur.execute('SELECT DISTINCT tabela_filha, tabela_mae FROM relacionamentos').fetchall():
                if f != m:
                    adj[f].add(m)
                    adj[m].add(f)
            self._adj = adj
        return self._adj

    def caminhos_de_join(self, tabelas: List[str], linhas_entre, pk_da_mae=None) -> List[Dict]:
        """Para cada par de tabelas pedidas, o menor caminho no grafo de FK e
        os JOINs de cada salto. `linhas_entre(a, b)` devolve as linhas de FK
        entre duas tabelas (com constraint, se a base tiver); `pk_da_mae`, a
        PK da mãe para provar o agrupamento sem constraint (`agrupar_fks`)."""
        adj = self._adjacencia()
        out = []
        for i, a in enumerate(tabelas):
            for b in tabelas[i + 1:]:
                caminho = menor_caminho(adj, a, b)
                item = {'de': a, 'para': b, 'tabelas': caminho}
                if caminho is None:
                    out.append(item)
                    continue
                saltos, joins, provado = [], [f'FROM {a}'], True
                for x, y in zip(caminho, caminho[1:]):
                    fks, sem = agrupar_fks(linhas_entre(x, y), x, pk_da_mae)
                    saltos.append({'de': x, 'para': y,
                                   'fks': [{'constraint': f['constraint'], 'origem': f['origem'], 'on': f['on'],
                                            'join': f['join']} for f in fks],
                                   'fks_sem_constraint': sem})
                    if fks:
                        joins.append(fks[0]['join'])
                    else:
                        provado = False
                item['saltos'] = saltos
                item['join'] = '\n'.join(joins) if provado else None
                out.append(item)
        return out

    def _consolidar(self, criticas: List[Dict], expandidas: List[Dict]) -> List[Dict]:
        tabelas_unicas = {}
        for t in criticas:
            tabelas_unicas[t['tabela']] = {**t, 'tipo': 'CRITICAL', 'ordem': 1}
        for t in expandidas:
            if t['tabela'] not in tabelas_unicas:
                tabelas_unicas[t['tabela']] = {'tabela': t['tabela'], 'tipo': 'EXPANDED', 'ordem': 2}
        resultado = list(tabelas_unicas.values())
        resultado.sort(key=lambda x: (x['ordem'], -x.get('score_dinamico', 0)))
        return resultado
