"""
Busca: a classe `NomiNomiNoMi` (buscar, críticas, detalhar), montada com
o índice (indice.py) e o grafo (grafo.py), e a inferência do módulo a
partir do resultado.

Parte do Nomi Nomi no Mi, movida sem mudança de algoritmo do antigo
`scripts/nomi_nomi_no_mi.py` (fase 1 da v3).
"""

import json
import math
import os
import sqlite3
from collections import Counter, defaultdict
from typing import Dict, List, Set

from dominios.schema import config
from dominios.schema.config import COLUNAS_ESTRUTURA, LIMITE_PARES_SEM_CAMINHO, MAX_SALTOS_CAMINHO
from dominios.schema.config import (
    ALPHA_TERMOS_EXTRA, ESCALA_CONCEITOS, LIMIAR_AMBIGUIDADE, PENALIDADE_MODULO_NAO_CADASTRADO,
    PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL, PESOS_POR_MODULO, _modulo_default, carregar_dominio_do_db,
)
from nomi_nomi_no_mi.grafo import GrafoMixin, agrupar_fks
from nomi_nomi_no_mi.indice import IndiceMixin
from nomi_nomi_no_mi.texto import extrair_termos, normalizar, radical


def inferir_modulo_por_resultado(tabelas_criticas: List[Dict]) -> str:
    """Infere o módulo provável A POSTERIORI, a partir do módulo
    predominante entre as tabelas críticas de fato encontradas
    (ponderado pelo score de cada uma) — não a partir de palavras do
    pedido em português, que não têm relação léxica com os prefixos de
    módulo do schema alvo ('obter_modulo' comparando
    a 1ª letra de uma palavra do usuário com o prefixo do módulo, o
    que é coincidência, não inferência).
    """
    if not tabelas_criticas:
        return _modulo_default()
    peso_por_modulo = Counter()
    for t in tabelas_criticas:
        modulo = t['tabela'][0].upper()
        if modulo in config.MODULOS_PRIORIZADOS:
            peso_por_modulo[modulo] += t.get('score_dinamico', 1.0)
    if not peso_por_modulo:
        return _modulo_default()
    return peso_por_modulo.most_common(1)[0][0]


# ==============================================================================
# CLASSE PRINCIPAL DO MOTOR
# ==============================================================================

class NomiNomiNoMi(IndiceMixin, GrafoMixin):
    """
    Nomi Nomi no Mi — motor de descoberta de schema por linguagem
    natural, genérico quanto ao schema. Consulta uma base de metadados
    ("Punk Records") no formato descrito em referencias/schema.md. O
    `punk_records.db` publicado neste repositório vem VAZIO; para
    usar, importe seus próprios metadados (ver referencias/schema.md,
    seção "Como importar seus dados").

    Fluxo de busca (6 passos):
      1. Extrai termos do pedido em linguagem natural + expande sinônimos
      2. Normaliza (remove acentos/caixa) e tokeniza para comparação
         tolerante a acento/caixa/plural
      3. Busca tabelas críticas: casa TOKENS (não substring) contra
         descrições de COLUNA e contra o nome da tabela, ponderando
         cada match por IDF (raridade do termo no schema)
      4. Calcula score dinâmico combinando relevância estrutural,
         match semântico (IDF) e conexões FK (em escala log, para não
         deixar tabelas "hub" dominarem o ranking)
      5. Expande com vizinhos via FK (relacionamentos), paginado
      6. Infere o módulo provável A POSTERIORI a partir das tabelas
         críticas encontradas, e consolida críticas + expandidas
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._indice = None  # carregado sob demanda (lazy)
        self._df = None      # document frequency por termo (para IDF)
        self._n_colunas = 0  # total de colunas indexadas (N do IDF)

        # módulos e sinônimos vêm das tabelas `sistemas`/`sinonimos`
        # DESTE banco — cada `NomiNomiNoMi(db_path)` recarrega o domínio
        # do banco que está abrindo, então apontar `--db` para um banco
        # diferente já basta; não existe mais `--dominio` separado.
        config.MODULOS_PRIORIZADOS, config.SINONIMOS, config.MODULO_NOMES = carregar_dominio_do_db(self.conn)

        # Item 6 (pesos por módulo): parte do PESOS_POR_MODULO global
        # (só 'DEFAULT') e, se existir um `punk_records_pesos.json` ao
        # lado do banco (gerado por satelites/pythagoras.py
        # a partir de casos reais/sintéticos), sobrepõe módulo a módulo.
        # Fica em arquivo de dado ao lado do .db, não em código, pelo
        # mesmo motivo dos módulos/sinônimos: recalibrar não deve exigir
        # editar o motor.
        self._pesos_por_modulo = dict(PESOS_POR_MODULO)
        caminho_pesos = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'punk_records_pesos.json')
        if os.path.exists(caminho_pesos):
            try:
                with open(caminho_pesos, 'r', encoding='utf-8') as f:
                    overrides = json.load(f)
                if isinstance(overrides, dict):
                    self._pesos_por_modulo.update(overrides)
            except (json.JSONDecodeError, OSError):
                pass  # arquivo de calibração corrompido/ilegível: segue com o DEFAULT

    # ---- API principal ----
    def buscar(self, pedido: str, limite_criticas: int = 30) -> Dict:
        """Busca tabelas relevantes do schema a partir de um pedido em PT-BR."""

        resultado = {
            'pedido': pedido,
            'termos': [],
            'modulo': _modulo_default(),
            'modulo_nome': config.MODULO_NOMES.get(_modulo_default(), ''),
            'criticas': [],
            'expandidas': [],
            'total_tabelas': 0,
            'aviso': [],
            'metodo': 'basico',
            'fuzzy_aplicado': None,     # item 3
            'ambiguidade': False,       # item 4
            'margem_top1_top2': None,   # item 4
        }

        termos = extrair_termos(pedido)
        resultado['termos'] = termos

        if not termos:
            resultado['aviso'].append('Nenhum termo útil encontrado (tudo era stop word).')
            return resultado

        # Item 3 — fuzzy fallback: identifica, ANTES da busca principal,
        # quaisquer termos do pedido que não batem em NADA do
        # vocabulário real do schema (df==0 — nem literal, nem
        # sinônimo, nem radical) e tenta uma correção aproximada
        # (distância de edição) contra esse mesmo vocabulário. É
        # proativo (roda mesmo quando outros termos do pedido já
        # bateram em algo), porque um termo com erro de digitação pode
        # conviver com outros termos corretos no mesmo pedido — se só
        # disparasse com o resultado inteiro vazio, um termo-chave
        # digitado errado (mas com outro termo genérico batendo em
        # tabela errada) nunca seria corrigido. Termos que já batem
        # literalmente NUNCA são tocados — o fuzzy só preenche a lacuna
        # de termos que hoje não contribuem em nada para a busca.
        correcoes = self._sugestoes_fuzzy(termos)
        termos_para_busca = list(termos)
        if correcoes:
            for original, corrigido in correcoes.items():
                if corrigido not in termos_para_busca:
                    termos_para_busca.append(corrigido)

        tabelas_criticas = self._buscar_criticas(termos_para_busca, limite=limite_criticas)

        if correcoes and tabelas_criticas:
            resultado['fuzzy_aplicado'] = correcoes
            resultado['aviso'].append(
                'Termo(s) sem match literal no schema; foi aplicada correção aproximada '
                '(fuzzy) para: ' +
                ', '.join(f"\"{o}\" -> \"{c}\"" for o, c in correcoes.items()) +
                '. Confirme se a interpretação faz sentido antes de confiar no resultado.'
            )

        resultado['criticas'] = tabelas_criticas

        # módulo inferido A POSTERIORI, a partir do que foi de fato
        # encontrado — não mais de palavras soltas do pedido (solução 5)
        modulo = inferir_modulo_por_resultado(tabelas_criticas)
        resultado['modulo'] = modulo
        resultado['modulo_nome'] = config.MODULO_NOMES.get(modulo, modulo)

        if not tabelas_criticas:
            resultado['aviso'].append(
                'Nenhuma tabela crítica encontrada para os termos: ' + ', '.join(termos) +
                '. Tente termos mais genéricos ou verifique sinônimos em português.'
            )
            return resultado

        # Item 2 — se a melhor tabela encontrada pertence a um módulo
        # não cadastrado em `sistemas`, avisa explicitamente (mesmo ela
        # tendo entrado no ranking, já com a penalidade de score
        # aplicada em `_buscar_criticas`) — é o mesmo tipo de gap que
        # escondeu o módulo 'Z' inteiro antes de virar visível.
        if tabelas_criticas and not tabelas_criticas[0].get('modulo_cadastrado', True):
            resultado['aviso'].append(
                f"A tabela mais bem colocada (\"{tabelas_criticas[0]['tabela']}\") pertence a um "
                f"módulo não cadastrado em `sistemas` (prefixo \"{tabelas_criticas[0]['tabela'][0]}\"). "
                f"Rode `checar-modulos` para ver todos os prefixos faltando e considere cadastrá-los."
            )

        # Item 4 — detecção de ambiguidade: quando o 1º e o 2º colocado
        # ficam com score muito próximo, isso é sinal estatístico de
        # ambiguidade léxica (ex.: "portaria" = recepção OU decreto) ou
        # de duas tabelas igualmente defensáveis — sinaliza em vez de
        # escolher em silêncio.
        if len(tabelas_criticas) >= 2 and tabelas_criticas[0]['score_dinamico'] > 0:
            top1 = tabelas_criticas[0]['score_dinamico']
            top2 = tabelas_criticas[1]['score_dinamico']
            margem = (top1 - top2) / top1
            resultado['margem_top1_top2'] = round(margem, 3)
            if margem < LIMIAR_AMBIGUIDADE:
                resultado['ambiguidade'] = True
                resultado['aviso'].append(
                    f"Ambiguidade: \"{tabelas_criticas[0]['tabela']}\" e "
                    f"\"{tabelas_criticas[1]['tabela']}\" ficaram com scores próximos "
                    f"(diferença de {margem * 100:.0f}%). Confirme com o usuário qual sentido "
                    f"é o pretendido antes de escrever o SQL, em vez de assumir o 1º colocado."
                )

        tabelas_expandidas = self._expandir_com_vizinhos_paginados(
            [t['tabela'] for t in tabelas_criticas]
        )
        resultado['expandidas'] = tabelas_expandidas
        empate = getattr(self, '_corte_empate', None)
        usados, total = getattr(self, '_corte_vizinhos', (0, 0))
        if total > usados:
            resultado['aviso'].append(
                f'Vizinhos via FK cortados: {usados} de {total} tabelas ligadas às críticas entraram em '
                '`expandidas` (por tabela crítica, em ordem alfabética, até cerca de 100). Para ligar duas '
                'tabelas específicas, use `detalhar` com as duas: ele mostra o menor caminho de JOIN.'
            )
        if empate:
            score, dentro, fora = empate
            resultado['aviso'].append(
                f'O corte de {len(tabelas_criticas)} tabelas críticas caiu no meio de um empate: {dentro + fora} '
                f'tabelas têm o mesmo score ({score}); {dentro} entraram (por ordem de nome) e {fora} ficaram de '
                'fora. Se a tabela certa pode estar entre elas, refine o pedido com termos mais específicos.'
            )

        todas = self._consolidar(tabelas_criticas, tabelas_expandidas)
        resultado['total_tabelas'] = len(todas)
        resultado['metodo'] = f'dynamic_score_idf ({modulo})' + (' +fuzzy' if resultado['fuzzy_aplicado'] else '')

        return resultado

    def _buscar_criticas(self, termos: List[str], limite: int = 30) -> List[Dict]:
        """Casa termos contra descrições de coluna e nomes de tabela.

        Match por TOKEN exato (não substring), cada
        match pesado por IDF (raridade do termo no schema — solução 3),
        e a fórmula final usa log(1+conexoes) em vez de conexoes bruto
        (solução 1), para que tabelas "hub" muito conectadas (ex.: a
        tabela de empresa, referenciada por quase toda tabela do schema
        via FK) não dominem o ranking só pela conectividade.
        """
        self._carregar_indice()

        termos_norm = [normalizar(t) for t in termos]
        termos_e_radicais = set(termos_norm) | {radical(t) for t in termos_norm}

        # matches[tabela] = {coluna: {termos batidos nessa coluna}}
        #   guardado por coluna só para exibição (colunas_relevantes);
        # termos_por_tabela[tabela] = {termos únicos batidos em QUALQUER
        #   coluna da tabela} — é isto que decide o score (ver nota abaixo)
        matches: Dict[str, Dict[str, Set[str]]] = defaultdict(dict)
        termos_por_tabela: Dict[str, Set[str]] = defaultdict(set)
        match_por_nome_tabela: Set[str] = set()

        for item in self._indice:
            # ITEM 2 (auditoria de inovação, pós-descoberta do módulo
            # 'Z' invisível): antes, uma tabela fora de um módulo
            # cadastrado em `sistemas` era IGNORADA por completo aqui —
            # um "continue" que a excluía de QUALQUER busca, sem aviso.
            # Isso escondeu 64 tabelas reais (712 colunas) até serem
            # achadas por acidente numa auditoria manual, não por
            # processo. Agora NUNCA excluímos por módulo — só marcamos
            # como "não classificado" (ver `modulo_cadastrado` abaixo) e
            # aplicamos uma penalidade de score, para que ainda apareça
            # quando for de fato a melhor resposta, só com prioridade
            # menor que uma tabela de módulo conhecido com força de
            # match equivalente.
            termos_batidos = termos_e_radicais & item['_tokens_desc']
            if termos_batidos:
                matches[item['tabela']][item['coluna']] = termos_batidos
                termos_por_tabela[item['tabela']] |= termos_batidos

            # nome da tabela é um código (ex: FPROVISAODECIMOTERCEIRO) —
            # não é uma frase tokenizável, então aqui mantemos substring,
            # mas só sobre termos com 5+ caracteres para reduzir colisão
            for t in termos_norm:
                if (len(t) >= 5 or t.isdigit()) and t in item['_norm_tabela']:
                    match_por_nome_tabela.add(item['tabela'])

        tabelas_encontradas = set(matches.keys()) | match_por_nome_tabela
        if not tabelas_encontradas:
            return []

        tabelas = list(tabelas_encontradas)
        placeholders = ','.join('?' for _ in tabelas)
        self.cur.execute(
            f"""
            SELECT tabela, descricao, score_relevancia, ranking,
                   COALESCE(conexoes_totais, 0) AS conexoes_totais,
                   COALESCE(tem_dados, 0) AS tem_dados
            FROM tabelas
            WHERE tabela IN ({placeholders})
            """,
            tabelas
        )
        meta = {row['tabela']: row for row in self.cur.fetchall()}

        resultados_brutos = []
        for tabela in tabelas_encontradas:
            row = meta.get(tabela)
            score_rel = (row['score_relevancia'] if row else 0) or 0
            conexoes = (row['conexoes_totais'] if row else 0) or 0
            tem_dados = bool(row['tem_dados']) if row else False
            ranking = (row['ranking'] if row and row['ranking'] is not None else 999999)

            colunas_batidas = matches.get(tabela, {})
            n_conceitos = len(colunas_batidas)

            # score do match semântico: somar o IDF de TODOS os
            # termos únicos batidos igualmente. Isso favorecia tabelas
            # que batem VÁRIOS termos genéricos (ex.: "trabalho" +
            # "funcionario", ambos comuns) sobre tabelas pequenas que
            # batem UM termo bem específico e decisivo (ex.: T_HORARIO
            # só bate "horario", mas é exatamente a resposta certa).
            # o termo de MAIOR idf (o mais específico/decisivo)
            # entra com peso cheio; os demais termos batidos entram
            # como reforço, mas com peso reduzido (ALPHA_TERMOS_EXTRA),
            # em vez de contarem 100% como antes. Validado via grid
            # search contra os casos de calibração + held-out (usados só
            # para checar generalização, não para calibrar) de
            # casos/consultas_fixture.json — números atuais em
            # egghead/linha_de_base_v3.json.
            termos_unicos = termos_por_tabela.get(tabela, set())
            idfs_da_tabela = sorted((self._idf(t) for t in termos_unicos), reverse=True)
            if idfs_da_tabela:
                score_idf_total = idfs_da_tabela[0] + ALPHA_TERMOS_EXTRA * sum(idfs_da_tabela[1:])
            else:
                score_idf_total = 0.0
            bonus_nome = 5.0 if tabela in match_por_nome_tabela else 0.0

            resultados_brutos.append({
                'tabela': tabela,
                'colunas_relevantes': sorted(colunas_batidas.keys())[:8],
                'n_colunas_batidas': n_conceitos,
                'score_relevancia': score_rel,
                'conexoes_log': math.log(1 + conexoes),  # solução 1
                'score_idf_bruto': score_idf_total + bonus_nome,
                'conexoes': conexoes,
                'tem_dados': tem_dados,
                'ranking': ranking,
            })

        # --- solução A+B: normalização só no eixo ESTRUTURAL ---
        # `score_relevancia` e `conexoes_log` são dois sinais da MESMA
        # dimensão ("a tabela é estruturalmente importante no schema"),
        # com escalas absolutas arbitrárias e sem significado fora do
        # schema (por isso min-max faz sentido aqui: comprime outliers
        # tipo a tabela hub de empresa para uma escala comparável 0-1).
        #
        # 'conceitos' (o match semântico via IDF) é DIFERENTE: o IDF já
        # é, por definição, uma medida comparável entre buscas (raridade
        # do termo no schema inteiro, não relativa a quem mais apareceu
        # nesta busca). Normalizar esse eixo também com min-max foi um
        # erro (detectado no caso "desligamento
        # do funcionário"): qualquer tabela com o maior IDF bruto do
        # conjunto virava automaticamente 1.0 (nota máxima), mesmo que a
        # vantagem real sobre a 2ª colocada fosse pequena. Aqui o IDF
        # fica em escala ABSOLUTA (só multiplicado por uma constante
        # fixa para ficar comparável em magnitude ao eixo estrutura).
        #
        # NOTA: uma tentativa anterior tentou resolver o problema
        # de tabelas pequenas/órfãs específicas (ver "Limitações
        # conhecidas" em referencias/schema.md) com um "peso
        # dinâmico" (reduzir o peso da estrutura quando o match
        # semântico parecesse decisivo). Testado com grid search e
        # DESCARTADO: não mudava o resultado em NENHUM valor testado,
        # porque o problema nunca foi "estrutura demais atrapalhando um
        # vencedor semântico" — era a fórmula de soma linear do IDF
        # (corrigida acima) escondendo o vencedor semântico real atrás
        # de tabelas com muitos matches fracos. Registrado aqui para não
        # reintroduzir a mesma ideia sem essa mesma evidência.

        def _minmax(valores):
            lo, hi = min(valores), max(valores)
            if hi - lo < 1e-9:
                return {i: 1.0 for i in range(len(valores))}
            return {i: (v - lo) / (hi - lo) for i, v in enumerate(valores)}

        rel_norm = _minmax([r['score_relevancia'] for r in resultados_brutos])
        conx_norm = _minmax([r['conexoes_log'] for r in resultados_brutos])

        resultados = []
        for i, r in enumerate(resultados_brutos):
            estrutura = (rel_norm[i] + conx_norm[i]) / 2.0
            conceitos_abs = r['score_idf_bruto'] * ESCALA_CONCEITOS

            pesos = self._pesos_por_modulo.get(r['tabela'][0], self._pesos_por_modulo['DEFAULT'])
            score_dinamico = pesos['estrutura'] * 100.0 * estrutura + pesos['conceitos'] * conceitos_abs

            # Item 2 — módulo não cadastrado em `sistemas`: nunca exclui
            # (ver comentário no loop de indexação acima), só despriorizada.
            modulo_cadastrado = (not config.MODULOS_PRIORIZADOS) or (r['tabela'][0].upper() in config.MODULOS_PRIORIZADOS)
            if not modulo_cadastrado:
                score_dinamico *= PENALIDADE_MODULO_NAO_CADASTRADO

            # v1.3: "sem lastro estrutural" exigia conexoes==0 E
            # total_registros==0 (dois sinais). v1.4 removeu
            # total_registros inteiro (contagem de linha é dado sensível
            # de volume de negócio) e a condição ficou só conexoes==0 —
            # um efeito colateral real disso: uma tabela pequena mas
            # LEGÍTIMA, só sem FK modelada, passou a levar a mesma
            # penalidade que uma tabela de staging vazia (achado rodando
            # a avaliação do schema — ver casos/consultas_fixture.json, caso "visitante
            # registrado na portaria").
            #
            # v1.5 reintroduz um SEGUNDO sinal, mas binário em vez de
            # contagem exata: `tem_dados` (populada ou vazia — ver
            # `importar_csvs`). Isso restaura a precisão original (só
            # penaliza quando NENHUM dos dois eixos tem evidência) sem
            # voltar a expor volume de negócio nenhum — "tem dado" não
            # diz se são 12 linhas ou 12 milhões.
            sem_lastro_estrutural = (r['conexoes'] == 0 and not r['tem_dados'])
            if sem_lastro_estrutural:
                score_dinamico *= PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL

            resultados.append({
                'tabela': r['tabela'],
                'colunas_relevantes': r['colunas_relevantes'],
                'n_colunas_batidas': r['n_colunas_batidas'],
                'score_relevancia': r['score_relevancia'],
                'score_idf': round(r['score_idf_bruto'], 2),
                'score_estrutura_norm': round(estrutura, 3),
                'score_dinamico': round(score_dinamico, 2),
                'conexoes': r['conexoes'],
                'tem_dados': r['tem_dados'],
                'ranking': r['ranking'],
                'modulo_cadastrado': modulo_cadastrado,
                'sem_lastro_estrutural': sem_lastro_estrutural,
            })

        # empate de score: desempata pelo nome da tabela, para a ordem (e o
        # corte em `limite`) não depender da ordem de iteração do `set`
        # (PYTHONHASHSEED)
        resultados.sort(key=lambda x: (-x['score_dinamico'], x['tabela']))
        # Fase 2: o corte em `limite` pode cair no meio de um grupo de score
        # idêntico (desempatado só pelo nome). A lista devolvida não muda;
        # o buscar avisa quantas tabelas empatadas ficaram de fora.
        self._corte_empate = None
        if len(resultados) > limite > 0 and \
                resultados[limite - 1]['score_dinamico'] == resultados[limite]['score_dinamico']:
            score = resultados[limite]['score_dinamico']
            self._corte_empate = (score,
                                  sum(1 for r in resultados[:limite] if r['score_dinamico'] == score),
                                  sum(1 for r in resultados[limite:] if r['score_dinamico'] == score))
        return resultados[:limite]

    # ---- Detalhamento (colunas + relacionamentos) para construir o SQL ----
    def detalhar(self, tabelas: List[str]) -> Dict:
        """
        Retorna, para cada tabela pedida: metadados, todas as colunas
        (com descrição de negócio) e todos os relacionamentos (FKs) em
        que a tabela participa como filha ou como mãe.

        Isto é o que a skill Vegapunk deve usar como fonte da verdade
        para nomes de coluna e joins - nunca inventar nomes de coluna
        do schema de memória.
        """
        resultado = {'tabelas': {}, 'aviso': []}

        tabelas = [t.strip().upper() for t in tabelas if t.strip()]
        if not tabelas:
            resultado['aviso'].append('Nenhuma tabela informada.')
            return resultado

        placeholders = ','.join('?' for _ in tabelas)

        self.cur.execute(
            f"""
            SELECT tabela, descricao, score_relevancia, ranking,
                   COALESCE(tabelas_filhas, 0) AS tabelas_filhas,
                   COALESCE(tabelas_pais, 0) AS tabelas_pais,
                   COALESCE(conexoes_totais, 0) AS conexoes_totais,
                   COALESCE(tem_dados, 0) AS tem_dados
            FROM tabelas WHERE tabela IN ({placeholders})
            """,
            tabelas
        )
        metas = {row['tabela']: dict(row) for row in self.cur.fetchall()}

        encontradas = set(metas.keys())
        nao_encontradas = [t for t in tabelas if t not in encontradas]
        if nao_encontradas:
            resultado['aviso'].append(
                'Tabelas não encontradas no schema: ' + ', '.join(nao_encontradas)
            )

        estrutura_col, estrutura_rel = self._colunas_de_estrutura()
        sem_constraint_total = 0
        motivos_sem_constraint = Counter()
        for tabela in tabelas:
            if tabela not in encontradas:
                continue

            extras = ''.join(f', {c}' for c in estrutura_col)
            self.cur.execute(
                f"SELECT coluna, descricao{extras} FROM colunas WHERE tabela = ? ORDER BY coluna",
                (tabela,)
            )
            colunas = []
            for row in self.cur.fetchall():
                c = dict(row)
                for campo in COLUNAS_ESTRUTURA:   # fase 2: estrutura da coluna (None = desconhecida)
                    c.setdefault(campo, None)
                colunas.append(c)

            extras = ''.join(f', {c}' for c in estrutura_rel)
            self.cur.execute(
                f"""
                SELECT tabela_filha, campo_filho, tabela_mae, campo_mae{extras}
                FROM {self._relacionamentos()} WHERE tabela_filha = ? OR tabela_mae = ?
                """,
                (tabela, tabela)
            )
            linhas_fk = [dict(row) for row in self.cur.fetchall()]
            relacionamentos = [{k: r[k] for k in ('tabela_filha', 'campo_filho', 'tabela_mae', 'campo_mae')}
                               for r in linhas_fk]
            fks, sem_constraint = agrupar_fks(linhas_fk, tabela, self._pk_da_mae)
            sem_constraint_total += len(sem_constraint)
            motivos_sem_constraint.update(r['motivo'] for r in sem_constraint)

            meta = dict(metas[tabela])
            meta['pk'] = [c['coluna'] for c in sorted((c for c in colunas if c['pk_ordem']),
                                                       key=lambda c: c['pk_ordem'])]
            resultado['tabelas'][tabela] = {
                'metadados': meta,
                'total_colunas': len(colunas),
                'colunas': colunas,
                'relacionamentos': relacionamentos,
                'fks': fks,
                'fks_sem_constraint': sem_constraint,
            }

        achadas = [t for t in tabelas if t in resultado['tabelas']]
        resultado['caminhos'] = (self.caminhos_de_join(achadas, self._linhas_entre, self._pk_da_mae)
                                 if len(achadas) > 1 else [])
        sem_caminho = [f"{c['de']} e {c['para']}" for c in resultado['caminhos'] if c['tabelas'] is None]
        if sem_caminho:
            mais = len(sem_caminho) - LIMITE_PARES_SEM_CAMINHO
            resultado['aviso'].append(
                f'Sem caminho de FK de até {MAX_SALTOS_CAMINHO} saltos entre: '
                + '; '.join(sem_caminho[:LIMITE_PARES_SEM_CAMINHO])
                + (f'; e mais {mais} par(es) (lista completa em `caminhos`)' if mais > 0 else '')
                + '. Não invente a ligação: confirme com o usuário como essas tabelas se relacionam.'
            )
        if sem_constraint_total:
            incompletas = motivos_sem_constraint['chave_incompleta']
            resultado['aviso'].append(
                f'{sem_constraint_total} ligação(ões) de FK das tabelas pedidas sem agrupamento provado (nem '
                'constraint na base, nem chave primária da mãe): não há JOIN pronto para elas (use uma condição '
                'ON por campo e confira com o usuário). '
                + (f'{incompletas} delas não cobrem a chave primária inteira da mãe: o JOIN pode multiplicar '
                   'linhas. ' if incompletas else '')
                + 'Para provar o agrupamento pela constraint, rode punk_records/extracao/relacionamentos.sql e '
                '`york.py enriquecer`.'
            )
        conflitos = motivos_sem_constraint['conflito_constraint_dicionario']
        if conflitos:
            resultado['aviso'].append(
                f'{conflitos} linha(s) de FK em que a constraint da base e a ligação do dicionário do sistema '
                'agrupam os campos de jeitos diferentes: nenhuma das duas vale sozinha, não há JOIN pronto. '
                'Mostre as duas ao usuário e pergunte qual é a ligação certa.'
            )
        nao_cobrem = sum(1 for t in resultado['tabelas'].values() for f in t['fks']
                         if f.get('cobre_chave_da_mae') is False)
        if nao_cobrem:
            resultado['aviso'].append(
                f'{nao_cobrem} FK(s) com JOIN pronto não usam exatamente a chave primária da mãe '
                '(`cobre_chave_da_mae` falso): o agrupamento está provado, mas o JOIN pode trazer mais de uma '
                'linha da mãe para cada linha da filha. Confira com o usuário antes de somar ou contar.'
            )
        return resultado

    def _pk_da_mae(self, tabela: str) -> Dict[str, int]:
        """PK de uma tabela (colunas em maiúsculas -> posição), da base
        enriquecida; vazio quando a base não tem `pk_ordem`."""
        cache = self.__dict__.setdefault('_cache_pk', {})
        if tabela not in cache:
            if 'pk_ordem' not in self._colunas_de_estrutura()[0]:
                cache[tabela] = {}
            else:
                self.cur.execute('SELECT coluna, pk_ordem FROM colunas WHERE tabela = ? AND pk_ordem IS NOT NULL',
                                 (tabela,))
                cache[tabela] = {c.strip().upper(): o for c, o in self.cur.fetchall()}
        return cache[tabela]

    def _linhas_entre(self, a: str, b: str) -> List[Dict]:
        extras = ''.join(f', {c}' for c in self._colunas_de_estrutura()[1])
        self.cur.execute(
            f"""SELECT tabela_filha, campo_filho, tabela_mae, campo_mae{extras} FROM {self._relacionamentos()}
                WHERE (tabela_filha = ? AND tabela_mae = ?) OR (tabela_filha = ? AND tabela_mae = ?)""",
            (a, b, b, a))
        return [dict(r) for r in self.cur.fetchall()]

    def _relacionamentos(self):
        """Fonte da leitura DIRIGIDA das FKs: a view `relacionamentos_corrigidos`
        (migração 007: direção do dicionário corrigida pelo catálogo, sem as
        duplicatas inversas) quando a base a tem; senão, a tabela. A leitura
        não dirigida (vizinhos, caminhos) é a mesma nas duas."""
        if not hasattr(self, '_fonte_rel'):
            tem = self.cur.execute("SELECT 1 FROM sqlite_master WHERE type = 'view' "
                                   "AND name = 'relacionamentos_corrigidos'").fetchone()
            self._fonte_rel = 'relacionamentos_corrigidos' if tem else 'relacionamentos'
        return self._fonte_rel

    def _colunas_de_estrutura(self):
        """Colunas de estrutura (fase 2) que existem nesta base: uma base na
        versão 1 não tem nenhuma, e o detalhar segue com elas em None."""
        if not hasattr(self, '_estrutura'):
            col = {r[1] for r in self.cur.execute('PRAGMA table_info(colunas)')}
            rel = {r[1] for r in self.cur.execute('PRAGMA table_info(relacionamentos)')}
            self._estrutura = ([c for c in COLUNAS_ESTRUTURA if c in col],
                               [c for c in ('constraint_nome', 'ordem', 'ligacao') if c in rel])
        return self._estrutura

    def fechar(self):
        self.conn.close()
