#!/usr/bin/env python3
"""
================================================================================
 NOMI NOMI NO MI  (motor de descoberta de schema por linguagem natural)  —  v1.0
================================================================================
Motor de descoberta de schema genérico: dado um pedido em linguagem
natural (PT-BR) e uma base de metadados de schema (5 tabelas — ver
contextos/README.md), retorna as tabelas mais relevantes, suas colunas
(com descrição de negócio) e os relacionamentos (FKs) entre elas —
tudo que é necessário para a skill Vegapunk escrever T-SQL correto sem
"adivinhar" nomes de tabela/coluna.

O motor é 100% agnóstico de domínio: TUDO que descreve um schema
específico — tabelas, colunas, relacionamentos, sistemas/módulos e
sinônimos de negócio — vem de dentro do próprio banco Punk Records
(`contextos/punk_records.db`), em 5 tabelas:

    tabelas          — metadados estruturais por tabela
    colunas          — nome + descrição de negócio (PT-BR) de cada coluna
    relacionamentos  — FKs entre tabelas
    sistemas         — código do sistema/módulo -> nome (ex: 'F' -> 'Folha')
    sinonimos        — termo -> sinônimo (vocabulário coloquial -> vocabulário do schema)

Nada disso fica hardcoded no motor nem em arquivo de config externo —
não existe mais `--dominio`/JSON separado. O banco publicado neste
repositório vem com as 5 tabelas VAZIAS (só o schema); para usar,
importe seus próprios metadados (ver contextos/README.md, seção "Como
importar seus dados"). Um comando `importar` está incluído para isso
(ver "3) Importar seus dados" abaixo).

Uso via linha de comando (chamado pela skill Vegapunk):

    # 1) Descobrir tabelas candidatas a partir de um pedido em PT-BR
    python3 nomi_nomi_no_mi.py buscar "preciso da data de admissão dos colaboradores"

    # 2) Detalhar tabelas específicas (colunas + relacionamentos/FKs)
    python3 nomi_nomi_no_mi.py detalhar F_FUNCIONARIO T_APROVACAO_EXPORTACAO

    # 3) Importar seus dados a partir de CSVs (ver contextos/README.md)
    python3 nomi_nomi_no_mi.py importar --dir ./meus_csvs/

    # 4) Saída em JSON puro (para parsing programático)
    python3 nomi_nomi_no_mi.py buscar "folha de pagamento" --json
    python3 nomi_nomi_no_mi.py detalhar F_FUNCIONARIO --json

    # 5) Apontar para outro banco (ex: uma cópia fora do repositório)
    python3 nomi_nomi_no_mi.py --db /caminho/privado/schema.db buscar "..."

--------------------------------------------------------------------------------
DECISÕES DE ARQUITETURA
--------------------------------------------------------------------------------
Por que o motor busca contra `colunas.descricao`, e não contra o NOME da
tabela: nomes de tabela costumam ser códigos (ex: `F_FUNCIONARIO`,
`T_APROVACAO_EXPORTACAO`) e não palavras do português, e
`tabelas.descricao` normalmente vem vazia (o dado de negócio real está
em `colunas.descricao`). Buscar só pelo nome da tabela praticamente
nunca encontra nada; buscar pelas descrições de negócio em PT-BR (ex.:
"Matrícula do funcionário", "Data de admissão do colaborador"),
ignorando acentuação/caixa, funciona porque essa é a única parte do
schema com significado léxico de fato.

Por que a fórmula de score usa `log(1 + conexoes)` em vez de conexões
brutas: uma tabela "hub" muito conectada (ex.: a tabela de
empresa/coligada, referenciada por quase toda tabela do schema via FK)
tiraria a maior parte do seu score desse termo sozinho, batendo tabelas
semanticamente corretas mesmo com match de conteúdo muito mais fraco.
`log(1 + conexoes)` comprime esse outlier sem descartar o sinal.

Por que o match é por TOKEN exato, e não substring: substring puro gera
muito falso positivo em termos curtos (um radical de 4 letras batendo
em centenas de colunas sem relação real com o termo). O índice tokeniza
as descrições e o match é contra o CONJUNTO DE TOKENS exato, tolerante
a plural via stemming leve (ver função `radical`).

Por que cada match é ponderado por IDF (raridade do termo): sem esse
peso, termos genéricos de auditoria ("registro", "data", "código" —
presentes em boa parte de qualquer schema real) inflariam tabelas
genéricas tanto quanto termos raros e discriminantes. Cada match usa
peso `idf = log(N / (1 + df(termo)))`, então termos raros pesam muito
mais que termos comuns.

Por que existe um dicionário de sinônimos: termos coloquiais do pedido
do usuário (ex.: "colaborador") nem sempre batem nas colunas quando o
schema usa a forma formal (ex.: "funcionário") no texto de negócio. O
dicionário de sinônimos expande termos coloquiais para o vocabulário
efetivo do schema antes da busca.

Por que o módulo é inferido A POSTERIORI (a partir das tabelas
críticas efetivamente encontradas, ponderado pelo score de cada uma), e
não a partir de palavras do pedido em português: palavras do pedido não
têm relação léxica com os prefixos de módulo do schema alvo — usar a 1ª
letra de uma palavra do usuário e compará-la ao prefixo de módulo seria
coincidência, não inferência.

Por que módulos (`sistemas`) e sinônimos vivem dentro do próprio banco
Punk Records, e não num arquivo de configuração externo: manter dois
artefatos para importar/versionar (o banco + um JSON à parte) é mais
frágil que manter um só. O motor carrega os três
(`MODULOS_PRIORIZADOS`, `MODULO_NOMES`, `SINONIMOS`) das tabelas
`sistemas`/`sinonimos` do banco no momento da conexão — apontar `--db`
para um banco diferente já basta, sem tocar no código. Resultado: um
único artefato (`punk_records.db`, 5 tabelas) descreve o schema inteiro,
e o motor não carrega absolutamente nenhum conhecimento de domínio no
próprio código-fonte — só sabe ler essas 5 tabelas, sejam elas de qual
sistema for.

Todas as decisões acima foram validadas empiricamente contra a suite de
testes de regressão (`testes_regressao.py`), rodando pedidos rotulados
manualmente (pedido -> tabela esperada) antes e depois de cada mudança,
separados em grupos de calibração/held-out/validação cega — ver
[Suite de testes] em `contextos/README.md`.
================================================================================
"""

import sqlite3
import re
import sys
import os
import json
import math
import argparse
import unicodedata
from collections import defaultdict, Counter
from typing import List, Dict, Set

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

STOP_WORDS = set([
    'de', 'da', 'do', 'das', 'dos', 'em', 'para', 'por', 'com',
    'no', 'na', 'nos', 'nas', 'ao', 'aos', 'pelo', 'pela',
    'a', 'o', 'e', 'ou', 'um', 'uma', 'os', 'as',
    'é', 'são', 'ser', 'foi', 'foram', 'sendo', 'devem',
    'que', 'se', 'qual', 'como', 'caso', 'quando', 'onde',
    'preciso', 'quero', 'gostaria', 'traga', 'trazer', 'mostre', 'mostrar',
    'tabela', 'tabelas', 'dados', 'informacao', 'informacoes'
])

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'contextos', 'punk_records.db'
)


def carregar_dominio_do_db(conn: sqlite3.Connection):
    """Carrega módulos e sinônimos das tabelas `sistemas` e `sinonimos`
    do próprio banco — nunca de um arquivo externo. Assim o mesmo motor
    serve para qualquer schema: basta importar dados diferentes para
    `--db` (ver comando `importar`), sem tocar no código.

    `sistemas`: codsistema, nomesistema, descricao (uma linha por módulo)
    `sinonimos`: termo, sinonimo (uma linha por par; um termo com N
                 sinônimos = N linhas)

    Se as tabelas ainda não existirem ou estiverem vazias (banco recém
    criado, sem import), devolve estruturas vazias — o motor continua
    funcionando, só sem inferência de módulo nem expansão de sinônimo.
    """
    cur = conn.cursor()
    modulos = {}
    try:
        cur.execute("SELECT codsistema, nomesistema FROM sistemas")
        for codsistema, nomesistema in cur.fetchall():
            modulos[codsistema] = nomesistema
    except sqlite3.OperationalError:
        pass  # tabela `sistemas` ainda não existe neste banco

    sinonimos = defaultdict(list)
    try:
        cur.execute("SELECT termo, sinonimo FROM sinonimos")
        for termo, sinonimo in cur.fetchall():
            sinonimos[termo].append(sinonimo)
    except sqlite3.OperationalError:
        pass  # tabela `sinonimos` ainda não existe neste banco

    modulos_priorizados = set(modulos.keys())
    return modulos_priorizados, dict(sinonimos), modulos


# Valores padrão até uma conexão real ser aberta (ver
# `NomiNomiNoMi.__init__`, que chama `carregar_dominio_do_db` e
# reatribui estes três globais a partir do banco em uso). Ficam no
# módulo, não na instância, para não precisar passar `engine` por toda
# a cadeia de funções utilitárias do motor.
MODULOS_PRIORIZADOS: Set[str] = set()
SINONIMOS: Dict[str, list] = {}
MODULO_NOMES: Dict[str, str] = {}


def _modulo_default() -> str:
    """Módulo usado quando nada foi encontrado/inferido ainda — o
    primeiro módulo (ordem alfabética) do domínio carregado, em vez de
    uma letra fixa (que só fazia sentido para um schema específico)."""
    return sorted(MODULOS_PRIORIZADOS)[0] if MODULOS_PRIORIZADOS else '?'

# ESTRUTURA + CONCEITOS: antes eram 3 pesos por módulo, com relevancia e
# conexoes competindo em escalas diferentes e incomparáveis com o termo
# semântico. Agora ESTRUTURA (relevancia + conexoes, normalizadas 0-1
# em conjunto, por busca) e CONCEITOS (match semântico, também 0-1)
# são as duas dimensões, na mesma escala — o peso passa a significar
# de fato "quanto pesa" essa dimensão, não fica refém de magnitude bruta.
# Calibrado via grid search contra testes_regressao.py (não chute):
# testadas as combinações 0.70/0.30 até 0.10/0.90 de estrutura/conceitos;
# 0.30/0.70 venceu de forma estável entre os grupos de calibração e
# held-out. Os números atuais de acerto por grupo (calibração/held-out/
# validação cega) estão em contextos/README.md — rode
# `testes_regressao.py` para reproduzir. Os casos de teste disponíveis
# (poucos por módulo) não davam base pra calibrar módulo a módulo sem
# overfitting, por isso o mesmo peso vale para todos os módulos (que
# nesta versão são dinâmicos, vindos da tabela `sistemas` do banco em
# uso — por isso só existe a chave 'DEFAULT' abaixo, usada para
# qualquer código de módulo que o banco importado tiver). Expandir a
# suite (mais casos por módulo) é pré-requisito para calibração por
# módulo no futuro.
PESOS_POR_MODULO = {
    'DEFAULT': {'estrutura': 0.30, 'conceitos': 0.70},
}

TAMANHO_PAGINA = 25
MAX_PAGINAS = 10  # até 250 vizinhos por tabela âncora

# Constantes da fórmula de score (nível de módulo para poderem ser
# recalibradas/grid-searched sem editar dentro dos métodos):
ESCALA_CONCEITOS = 6.0      # escala o IDF bruto para magnitude comparável à estrutura (0-100)
ALPHA_TERMOS_EXTRA = 0.3    # peso dos termos batidos ALÉM do mais específico (ver
                             # _buscar_criticas — o termo de maior IDF entra com peso
                             # cheio, os demais entram reduzidos, para tabelas pequenas
                             # e certeiras não perderem para tabelas grandes que batem
                             # vários termos genéricos). Calibrado via grid search contra
                             # os casos de calibração/held-out de testes_regressao.py —
                             # números de acerto atuais em contextos/README.md.

# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================

_ORDINAIS_POR_EXTENSO = {
    'decimo terceiro': '13', 'décimo terceiro': '13',
    'decimo quarto': '14', 'décimo quarto': '14',
}


def normalizar(texto: str) -> str:
    """Lowercase + remove acentuação, para comparação tolerante a acentos/caixa."""
    if not texto:
        return ''
    nfkd = unicodedata.normalize('NFKD', texto)
    sem_acento = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


def _substituir_ordinais_por_extenso(texto_normalizado: str) -> str:
    """Muitos schemas de negócio escrevem '13º Salário', nunca 'décimo
    terceiro salário' — então converte a forma por extenso pro numeral
    ANTES de tokenizar, senão o número (só 2 dígitos) nunca passaria no
    filtro de 4+ caracteres e a busca nunca bateria em tabelas como
    (hipoteticamente) 'FPROVISAODECIMOTERCEIRO'. Não há dataset nenhum
    embutido neste pacote — este é só um nome ilustrativo do tipo de
    tabela que esse tratamento resolve; ver testes_regressao.py, que
    gera sua própria fixture fictícia sob demanda para exercitar isso."""
    for extenso, numero in _ORDINAIS_POR_EXTENSO.items():
        texto_normalizado = texto_normalizado.replace(normalizar(extenso), numero)
    return texto_normalizado


def formatar_numero_ptbr(valor: float, casas: int = 2) -> str:
    """Formata número no padrão pt-BR: '.' como separador de milhar e ',' como decimal.

    Ex.: 12345.6 -> '12.345,60'. Usado em toda a saída textual do motor
    (nunca o padrão en-US de vírgula-milhar/ponto-decimal).
    """
    texto = f"{valor:,.{casas}f}"
    texto = texto.replace(',', '§').replace('.', ',').replace('§', '.')
    return texto


_SUFIXOS_PLURAL = ('oes', 'aes', 'ais', 'eis', 'is', 'ns', 's')


def radical(termo: str) -> str:
    """Stemming bem leve: reduz plurais comuns em PT-BR a uma forma
    aproximada, só para permitir comparação tolerante a plural/singular
    (ex.: 'funcionarios' ~ 'funcionario'). Não é um stemmer linguístico
    completo — é deliberadamente conservador para não gerar colisões
    falsas entre palavras diferentes.
    """
    if len(termo) <= 4:
        return termo
    for suf in _SUFIXOS_PLURAL:
        if termo.endswith(suf) and len(termo) - len(suf) >= 4:
            return termo[:-len(suf)]
    return termo


def tokenizar(texto: str) -> Set[str]:
    """Extrai o conjunto de tokens normalizados (4+ caracteres, ou
    números isolados de 2-3 dígitos como '13' em '13º Salário') de um
    texto."""
    return set(re.findall(r'\w{4,}|(?<!\d)\d{2,3}(?!\d)', normalizar(texto)))


def extrair_termos(pedido: str) -> List[str]:
    """Extrai termos relevantes (4+ caracteres, sem stop words) de um
    pedido, e EXPANDE com sinônimos de domínio conhecidos (solução 4).
    A ordem é preservada e sem duplicatas.
    """
    texto_norm = _substituir_ordinais_por_extenso(normalizar(pedido))
    termos_norm = re.findall(r'\w{4,}|(?<!\d)\d{2,3}(?!\d)', texto_norm)
    termos = [t for t in termos_norm if t not in STOP_WORDS]

    # Expande sinônimos EM CADEIA (ponto fixo), não só uma passada: um
    # sinônimo pode por sua vez ter outro sinônimo (ex.: "desligamento"
    # -> "rescisao" -> "recisao", o typo real do banco). Limitado a 5
    # iterações como trava de segurança contra ciclos no dicionário.
    expandidos = list(termos)
    for _ in range(5):
        novos = []
        for t in expandidos:
            for sinonimo in SINONIMOS.get(t, []):
                if sinonimo not in expandidos and sinonimo not in novos:
                    novos.append(sinonimo)
        if not novos:
            break
        expandidos.extend(novos)
    return expandidos


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
        if modulo in MODULOS_PRIORIZADOS:
            peso_por_modulo[modulo] += t.get('score_dinamico', 1.0)
    if not peso_por_modulo:
        return _modulo_default()
    return peso_por_modulo.most_common(1)[0][0]


# ==============================================================================
# CLASSE PRINCIPAL DO MOTOR
# ==============================================================================

class NomiNomiNoMi:
    """
    Nomi Nomi no Mi — motor de descoberta de schema por linguagem
    natural, genérico quanto ao schema. Consulta uma base de metadados
    ("Punk Records") no formato descrito em contextos/README.md. O
    `punk_records.db` publicado neste repositório vem VAZIO; para
    usar, importe seus próprios metadados (ver contextos/README.md,
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
        global MODULOS_PRIORIZADOS, SINONIMOS, MODULO_NOMES
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
        MODULOS_PRIORIZADOS, SINONIMOS, MODULO_NOMES = carregar_dominio_do_db(self.conn)

    # ---- índice de colunas (para casar termos com descrições de negócio) ----
    def _carregar_indice(self):
        """Carrega o índice de colunas já TOKENIZADO (solução 2: matching
        por token exato, não substring) e pré-computa a frequência de
        documento (df) de cada token, para o peso IDF (solução 3).
        """
        if self._indice is not None:
            return
        self.cur.execute("SELECT tabela, coluna, descricao FROM colunas")
        indice = []
        df = Counter()
        for row in self.cur.fetchall():
            desc = row['descricao'] or ''
            tokens_desc = tokenizar(desc)
            # também indexamos o radical de cada token (tolerância a
            # plural leve), sem substituir o token original
            tokens_desc |= {radical(t) for t in tokens_desc}
            indice.append({
                'tabela': row['tabela'],
                'coluna': row['coluna'],
                'descricao': desc,
                '_tokens_desc': tokens_desc,
                '_norm_tabela': normalizar(row['tabela']),
            })
            for tk in tokens_desc:
                df[tk] += 1
        self._indice = indice
        self._df = df
        self._n_colunas = len(indice)

    def _idf(self, termo: str) -> float:
        """Peso IDF de um termo: raro no schema = peso alto, comum = peso
        baixo. `+1` no denominador evita divisão por zero para termos
        inéditos; `log` comprime a escala (mesmo racional do log nas
        conexões, solução 1)."""
        df_termo = self._df.get(termo, 0) if self._df else 0
        return math.log(self._n_colunas / (1 + df_termo)) if self._n_colunas else 1.0

    # ---- API principal ----
    def buscar(self, pedido: str, limite_criticas: int = 30) -> Dict:
        """Busca tabelas relevantes do schema a partir de um pedido em PT-BR."""

        resultado = {
            'pedido': pedido,
            'termos': [],
            'modulo': _modulo_default(),
            'modulo_nome': MODULO_NOMES.get(_modulo_default(), ''),
            'criticas': [],
            'expandidas': [],
            'total_tabelas': 0,
            'aviso': [],
            'metodo': 'basico'
        }

        termos = extrair_termos(pedido)
        resultado['termos'] = termos

        if not termos:
            resultado['aviso'].append('Nenhum termo útil encontrado (tudo era stop word).')
            return resultado

        tabelas_criticas = self._buscar_criticas(termos, limite=limite_criticas)
        resultado['criticas'] = tabelas_criticas

        # módulo inferido A POSTERIORI, a partir do que foi de fato
        # encontrado — não mais de palavras soltas do pedido (solução 5)
        modulo = inferir_modulo_por_resultado(tabelas_criticas)
        resultado['modulo'] = modulo
        resultado['modulo_nome'] = MODULO_NOMES.get(modulo, modulo)

        if not tabelas_criticas:
            resultado['aviso'].append(
                'Nenhuma tabela crítica encontrada para os termos: ' + ', '.join(termos) +
                '. Tente termos mais genéricos ou verifique sinônimos em português.'
            )
            return resultado

        tabelas_expandidas = self._expandir_com_vizinhos_paginados(
            [t['tabela'] for t in tabelas_criticas]
        )
        resultado['expandidas'] = tabelas_expandidas

        todas = self._consolidar(tabelas_criticas, tabelas_expandidas)
        resultado['total_tabelas'] = len(todas)
        resultado['metodo'] = f'dynamic_score_idf ({modulo})'

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
            # Sem `sistemas` importado (MODULOS_PRIORIZADOS vazio), não
            # há módulo nenhum para filtrar — considera todas as
            # tabelas, em vez de excluir tudo por engano.
            if MODULOS_PRIORIZADOS and item['_norm_tabela'][:1].upper() not in MODULOS_PRIORIZADOS:
                continue

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
                   COALESCE(total_registros, 0) AS total_registros
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
            # testes_regressao.py — ver números atuais em
            # contextos/README.md.
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
                'total_registros': row['total_registros'] if row else 0,
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
        # conhecidas" em contextos/README.md) com um "peso
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

            pesos = PESOS_POR_MODULO.get(r['tabela'][0], PESOS_POR_MODULO['DEFAULT'])
            score_dinamico = pesos['estrutura'] * 100.0 * estrutura + pesos['conceitos'] * conceitos_abs

            resultados.append({
                'tabela': r['tabela'],
                'colunas_relevantes': r['colunas_relevantes'],
                'n_colunas_batidas': r['n_colunas_batidas'],
                'score_relevancia': r['score_relevancia'],
                'score_idf': round(r['score_idf_bruto'], 2),
                'score_estrutura_norm': round(estrutura, 3),
                'score_dinamico': round(score_dinamico, 2),
                'conexoes': r['conexoes'],
                'total_registros': r['total_registros'],
                'ranking': r['ranking'],
            })

        resultados.sort(key=lambda x: x['score_dinamico'], reverse=True)
        return resultados[:limite]

    def _expandir_com_vizinhos_paginados(self, tabelas_ancoras: List[str]) -> List[Dict]:
        """Expande tabelas críticas com vizinhos via FK (relacionamentos), paginado."""
        expandidas: Set[str] = set()
        anchor_set = set(tabelas_ancoras)

        for tabela in tabelas_ancoras[:30]:
            pagina = 0
            while pagina < MAX_PAGINAS:
                offset = pagina * TAMANHO_PAGINA
                # Sem `sistemas` importado (MODULOS_PRIORIZADOS vazio),
                # não há como filtrar vizinhos por módulo — aceita
                # qualquer tabela como vizinha em vez de gerar um
                # `IN ()` vazio (SQL inválido).
                if MODULOS_PRIORIZADOS:
                    filtro_modulo = "WHERE SUBSTR(tabela, 1, 1) IN ({placeholders})".format(
                        placeholders=','.join('?' for _ in MODULOS_PRIORIZADOS)
                    )
                    params_modulo = tuple(sorted(MODULOS_PRIORIZADOS))
                else:
                    filtro_modulo = ""
                    params_modulo = ()
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
                WHERE tabela_vizinha IN (
                    SELECT tabela FROM tabelas
                    {filtro_modulo}
                )
                ORDER BY tabela_vizinha
                LIMIT ? OFFSET ?
                """.format(filtro_modulo=filtro_modulo)
                self.cur.execute(
                    sql,
                    (tabela, tabela, *params_modulo, TAMANHO_PAGINA, offset)
                )
                vizinhos = [row[0] for row in self.cur.fetchall()]
                if not vizinhos:
                    break
                expandidas.update(v for v in vizinhos if v not in anchor_set)
                if len(expandidas) >= 100:
                    break
                pagina += 1

        return [{'tabela': t} for t in sorted(expandidas)]

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
                   COALESCE(total_registros, 0) AS total_registros,
                   COALESCE(tabelas_filhas, 0) AS tabelas_filhas,
                   COALESCE(tabelas_pais, 0) AS tabelas_pais,
                   COALESCE(conexoes_totais, 0) AS conexoes_totais
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

        for tabela in tabelas:
            if tabela not in encontradas:
                continue

            self.cur.execute(
                "SELECT coluna, descricao FROM colunas WHERE tabela = ? ORDER BY coluna",
                (tabela,)
            )
            colunas = [dict(row) for row in self.cur.fetchall()]

            self.cur.execute(
                """
                SELECT tabela_filha, campo_filho, tabela_mae, campo_mae
                FROM relacionamentos WHERE tabela_filha = ? OR tabela_mae = ?
                """,
                (tabela, tabela)
            )
            relacionamentos = [dict(row) for row in self.cur.fetchall()]

            resultado['tabelas'][tabela] = {
                'metadados': metas[tabela],
                'total_colunas': len(colunas),
                'colunas': colunas,
                'relacionamentos': relacionamentos,
            }

        return resultado

    def fechar(self):
        self.conn.close()


# ==============================================================================
# FORMATAÇÃO PARA TERMINAL (saída padrão, legível por humanos/pela skill)
# ==============================================================================

def formatar_busca_texto(r: Dict) -> str:
    linhas = []
    linhas.append(f"Pedido: {r['pedido']}")
    linhas.append(f"Termos considerados: {', '.join(r['termos']) or '(nenhum)'}")
    linhas.append(f"Módulo provável: {r['modulo']} - {r.get('modulo_nome', '')}")
    linhas.append(f"Método: {r['metodo']}")
    linhas.append("")

    if r['criticas']:
        linhas.append(f"TABELAS CRÍTICAS ({len(r['criticas'])}) — prioridade para o SQL:")
        for t in r['criticas']:
            linhas.append(
                f"  • {t['tabela']:<28} score={formatar_numero_ptbr(t['score_dinamico']):>10}  "
                f"colunas_batidas={t['n_colunas_batidas']:<3} "
                f"registros≈{formatar_numero_ptbr(t['total_registros'], 0):<10} "
                f"| colunas relevantes: {', '.join(t['colunas_relevantes'])}"
            )
    else:
        linhas.append("Nenhuma tabela crítica encontrada.")

    if r['expandidas']:
        nomes = [t['tabela'] for t in r['expandidas']]
        linhas.append("")
        linhas.append(f"TABELAS RELACIONADAS VIA FK ({len(nomes)}) — candidatas a JOIN:")
        linhas.append("  " + ', '.join(nomes[:40]) + (" ..." if len(nomes) > 40 else ""))

    if r['aviso']:
        linhas.append("")
        linhas.append("Avisos:")
        for a in r['aviso']:
            linhas.append(f"  ! {a}")

    linhas.append("")
    linhas.append(
        "Próximo passo: rode `nomi_nomi_no_mi.py detalhar <TABELA1> <TABELA2> ...` "
        "com as tabelas críticas (e as relacionadas que fizerem sentido) para obter "
        "as colunas exatas e os relacionamentos antes de escrever o T-SQL."
    )
    return '\n'.join(linhas)


def formatar_detalhar_texto(r: Dict) -> str:
    linhas = []
    for tabela, info in r['tabelas'].items():
        m = info['metadados']
        linhas.append(f"### {tabela}")
        linhas.append(
            f"  registros≈{formatar_numero_ptbr(m['total_registros'], 0)}  "
            f"conexoes_totais={m['conexoes_totais']}  "
            f"tabelas_filhas={m['tabelas_filhas']}  tabelas_pais={m['tabelas_pais']}  "
            f"ranking={m['ranking']}"
        )
        linhas.append(f"  Colunas ({info['total_colunas']}):")
        for c in info['colunas']:
            desc = f" — {c['descricao']}" if c['descricao'] else ""
            linhas.append(f"    - {c['coluna']}{desc}")

        if info['relacionamentos']:
            linhas.append(f"  Relacionamentos (FKs) ({len(info['relacionamentos'])}):")
            for rel in info['relacionamentos']:
                linhas.append(
                    f"    - {rel['tabela_filha']}({rel['campo_filho']}) -> "
                    f"{rel['tabela_mae']}({rel['campo_mae']})"
                )
        linhas.append("")

    if r['aviso']:
        linhas.append("Avisos:")
        for a in r['aviso']:
            linhas.append(f"  ! {a}")

    return '\n'.join(linhas)


# ==============================================================================
# ==============================================================================
# IMPORTAÇÃO (CSV -> punk_records.db)
# ==============================================================================

# Uma linha por par (tabela, coluna) obrigatória, coluna extra opcional.
COLUNAS_OBRIGATORIAS_CSV = {
    'tabelas.csv': {'tabela'},                                        # + total_registros (opcional), descricao (opcional)
    'colunas.csv': {'tabela', 'coluna'},                              # + descricao (opcional)
    'relacionamentos.csv': {'tabela_filha', 'campo_filho', 'tabela_mae', 'campo_mae'},
    'sistemas.csv': {'codsistema', 'nomesistema'},                    # + descricao (opcional)
    'sinonimos.csv': {'termo', 'sinonimo'},
}

# Só estes dois são indispensáveis pro motor funcionar; os outros 3
# melhoram o resultado mas o motor degrada graciosamente sem eles (ver
# `carregar_dominio_do_db` e os guards de MODULOS_PRIORIZADOS acima).
CSV_OBRIGATORIOS = {'tabelas.csv', 'colunas.csv'}


def _ler_csv(caminho: str, colunas_obrigatorias: Set[str]) -> List[Dict[str, str]]:
    import csv
    with open(caminho, 'r', encoding='utf-8-sig', newline='') as f:
        leitor = csv.DictReader(f)
        header = set(leitor.fieldnames or [])
        faltando = colunas_obrigatorias - header
        if faltando:
            raise ValueError(
                f"{os.path.basename(caminho)}: faltam colunas obrigatórias no cabeçalho: "
                f"{', '.join(sorted(faltando))} (encontrado: {', '.join(sorted(header))})"
            )
        return [row for row in leitor]


def criar_schema(conn: sqlite3.Connection):
    """Cria as 5 tabelas (schema vazio). Usado tanto para gerar o banco
    vazio publicado no repositório quanto como primeiro passo do
    `importar` (que recria do zero antes de popular)."""
    cur = conn.cursor()
    cur.executescript("""
        DROP TABLE IF EXISTS tabelas;
        DROP TABLE IF EXISTS colunas;
        DROP TABLE IF EXISTS relacionamentos;
        DROP TABLE IF EXISTS sistemas;
        DROP TABLE IF EXISTS sinonimos;

        CREATE TABLE tabelas (
            tabela TEXT PRIMARY KEY,
            descricao TEXT,
            score_relevancia REAL,
            ranking INTEGER,
            total_registros INTEGER,
            tabelas_filhas INTEGER,
            tabelas_pais INTEGER,
            conexoes_totais INTEGER
        );
        CREATE TABLE colunas (
            tabela TEXT,
            coluna TEXT,
            descricao TEXT
        );
        CREATE TABLE relacionamentos (
            tabela_filha TEXT,
            campo_filho TEXT,
            tabela_mae TEXT,
            campo_mae TEXT
        );
        CREATE TABLE sistemas (
            codsistema TEXT PRIMARY KEY,
            nomesistema TEXT,
            descricao TEXT
        );
        CREATE TABLE sinonimos (
            termo TEXT,
            sinonimo TEXT
        );
        CREATE INDEX idx_colunas_tabela ON colunas(tabela);
        CREATE INDEX idx_rel_filha ON relacionamentos(tabela_filha);
        CREATE INDEX idx_rel_mae ON relacionamentos(tabela_mae);
        CREATE INDEX idx_sinonimos_termo ON sinonimos(termo);
    """)
    conn.commit()


def importar_csvs(dir_csvs: str, db_path: str, sobrescrever: bool = True) -> Dict[str, int]:
    """Lê tabelas.csv / colunas.csv / relacionamentos.csv / sistemas.csv
    / sinonimos.csv de `dir_csvs`, calcula os campos derivados
    (tabelas_filhas, tabelas_pais, conexoes_totais, score_relevancia,
    ranking — a pessoa não precisa calcular isso na mão) e grava tudo
    em `db_path`, recriando o schema do zero.

    `sistemas.csv` e `sinonimos.csv` são opcionais — se ausentes, o
    motor funciona sem inferência de módulo/expansão de sinônimo (ver
    guards de MODULOS_PRIORIZADOS/SINONIMOS no motor).
    """
    if not os.path.isdir(dir_csvs):
        raise FileNotFoundError(f"Diretório não encontrado: {dir_csvs}")

    presentes = {f for f in COLUNAS_OBRIGATORIAS_CSV if os.path.exists(os.path.join(dir_csvs, f))}
    faltando_obrigatorios = CSV_OBRIGATORIOS - presentes
    if faltando_obrigatorios:
        raise FileNotFoundError(
            f"Arquivo(s) obrigatório(s) não encontrado(s) em {dir_csvs}: "
            f"{', '.join(sorted(faltando_obrigatorios))}"
        )

    dados = {}
    for nome_arquivo, colunas_obrig in COLUNAS_OBRIGATORIAS_CSV.items():
        caminho = os.path.join(dir_csvs, nome_arquivo)
        dados[nome_arquivo] = _ler_csv(caminho, colunas_obrig) if nome_arquivo in presentes else []

    if os.path.exists(db_path) and not sobrescrever:
        raise FileExistsError(f"{db_path} já existe (use sobrescrever=True/--forcar para substituir)")

    conn = sqlite3.connect(db_path)
    criar_schema(conn)
    cur = conn.cursor()

    # --- colunas / relacionamentos / sistemas / sinonimos: import direto ---
    for row in dados['colunas.csv']:
        cur.execute(
            "INSERT INTO colunas (tabela, coluna, descricao) VALUES (?,?,?)",
            (row['tabela'].strip(), row['coluna'].strip(), (row.get('descricao') or '').strip())
        )
    for row in dados['relacionamentos.csv']:
        cur.execute(
            "INSERT INTO relacionamentos (tabela_filha, campo_filho, tabela_mae, campo_mae) VALUES (?,?,?,?)",
            (row['tabela_filha'].strip(), row['campo_filho'].strip(),
             row['tabela_mae'].strip(), row['campo_mae'].strip())
        )
    for row in dados['sistemas.csv']:
        cur.execute(
            "INSERT INTO sistemas (codsistema, nomesistema, descricao) VALUES (?,?,?)",
            (row['codsistema'].strip(), row['nomesistema'].strip(), (row.get('descricao') or '').strip())
        )
    for row in dados['sinonimos.csv']:
        cur.execute(
            "INSERT INTO sinonimos (termo, sinonimo) VALUES (?,?)",
            (row['termo'].strip().lower(), row['sinonimo'].strip().lower())
        )

    # --- tabelas: total_registros vem do CSV; o resto é CALCULADO, não digitado ---
    linhas_tabelas = {
        row['tabela'].strip(): {
            'descricao': (row.get('descricao') or '').strip(),
            'total_registros': int(row['total_registros']) if (row.get('total_registros') or '').strip().isdigit() else 0,
        }
        for row in dados['tabelas.csv']
    }

    cur.execute("SELECT tabela_filha, tabela_mae FROM relacionamentos")
    rels = cur.fetchall()
    filhas_por_tabela = defaultdict(set)   # tabela_mae -> {tabela_filha, ...}
    pais_por_tabela = defaultdict(set)     # tabela_filha -> {tabela_mae, ...}
    for tabela_filha, tabela_mae in rels:
        filhas_por_tabela[tabela_mae].add(tabela_filha)
        pais_por_tabela[tabela_filha].add(tabela_mae)

    metricas = {}
    for tabela, meta in linhas_tabelas.items():
        n_filhas = len(filhas_por_tabela.get(tabela, ()))
        n_pais = len(pais_por_tabela.get(tabela, ()))
        metricas[tabela] = {
            'descricao': meta['descricao'],
            'total_registros': meta['total_registros'],
            'tabelas_filhas': n_filhas,
            'tabelas_pais': n_pais,
            'conexoes_totais': n_filhas + n_pais,
        }

    # score_relevancia: mesma fórmula usada desde a extração original
    # (40% filhas + 30% conexões + 15% pais + 15% log do volume de
    # registros, cada componente normalizado 0-100 pelo máximo do
    # conjunto importado) — ver contextos/README.md.
    max_filhas = max((m['tabelas_filhas'] for m in metricas.values()), default=0) or 1
    max_conexoes = max((m['conexoes_totais'] for m in metricas.values()), default=0) or 1
    max_pais = max((m['tabelas_pais'] for m in metricas.values()), default=0) or 1
    max_logreg = max((math.log10(m['total_registros'] + 1) for m in metricas.values()), default=0) or 1

    scores = []
    for tabela, m in metricas.items():
        logreg = math.log10(m['total_registros'] + 1)
        score = (
            100.0 * m['tabelas_filhas'] / max_filhas * 0.40
            + 100.0 * m['conexoes_totais'] / max_conexoes * 0.30
            + 100.0 * m['tabelas_pais'] / max_pais * 0.15
            + 100.0 * logreg / max_logreg * 0.15
        )
        scores.append((tabela, round(score, 2)))
    scores.sort(key=lambda par: -par[1])
    ranking_por_tabela = {tabela: i for i, (tabela, _) in enumerate(scores, start=1)}
    score_por_tabela = dict(scores)

    for tabela, m in metricas.items():
        cur.execute(
            """INSERT INTO tabelas
               (tabela, descricao, score_relevancia, ranking, total_registros,
                tabelas_filhas, tabelas_pais, conexoes_totais)
               VALUES (?,?,?,?,?,?,?,?)""",
            (tabela, m['descricao'] or None, score_por_tabela[tabela], ranking_por_tabela[tabela],
             m['total_registros'], m['tabelas_filhas'], m['tabelas_pais'], m['conexoes_totais'])
        )

    conn.commit()
    contagens = {
        'tabelas': len(metricas),
        'colunas': len(dados['colunas.csv']),
        'relacionamentos': len(dados['relacionamentos.csv']),
        'sistemas': len(dados['sistemas.csv']),
        'sinonimos': len(dados['sinonimos.csv']),
    }
    conn.close()
    return contagens


# ==============================================================================
# CLI
# ==============================================================================

def main():
    global MODULOS_PRIORIZADOS, SINONIMOS, MODULO_NOMES

    parser = argparse.ArgumentParser(
        description='Nomi Nomi no Mi - motor de descoberta de schema por linguagem natural (genérico, ver contextos/README.md)'
    )
    parser.add_argument(
        '--db', default=DEFAULT_DB_PATH,
        help='Caminho do banco de schema (padrão: contextos/punk_records.db ao lado deste script)'
    )
    sub = parser.add_subparsers(dest='comando', required=True)

    p_buscar = sub.add_parser('buscar', help='Busca tabelas a partir de um pedido em PT-BR')
    p_buscar.add_argument('pedido', help='Pedido em linguagem natural, em português')
    p_buscar.add_argument('--limite', type=int, default=30, help='Máximo de tabelas críticas')
    p_buscar.add_argument('--json', action='store_true', help='Saída em JSON')

    p_detalhar = sub.add_parser('detalhar', help='Detalha colunas e FKs de tabelas específicas')
    p_detalhar.add_argument('tabelas', nargs='+', help='Nomes das tabelas (ex: F_FUNCIONARIO N_UNIDADE)')
    p_detalhar.add_argument('--json', action='store_true', help='Saída em JSON')

    p_importar = sub.add_parser(
        'importar',
        help='Importa tabelas/colunas/relacionamentos/sistemas/sinonimos a partir de CSVs e (re)gera o banco'
    )
    p_importar.add_argument('--dir', required=True, help='Diretório com os CSVs (ver contextos/README.md)')
    p_importar.add_argument(
        '--forcar', action='store_true',
        help='Sobrescreve --db se já existir (padrão: recusa se o arquivo já existir, para evitar apagar por engano)'
    )

    args = parser.parse_args()

    if args.comando == 'importar':
        if os.path.exists(args.db) and not args.forcar:
            print(
                f"ERRO: {args.db} já existe. Use --forcar para sobrescrever "
                f"(cuidado: isso apaga o conteúdo atual do banco).",
                file=sys.stderr
            )
            sys.exit(1)
        try:
            contagens = importar_csvs(args.dir, args.db, sobrescrever=True)
        except (FileNotFoundError, ValueError) as e:
            print(f"ERRO ao importar: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Importação concluída em: {args.db}")
        for nome, n in contagens.items():
            print(f"  {nome}: {n}")
        return

    if not os.path.exists(args.db):
        print(
            f"ERRO: banco de dados não encontrado em: {args.db}\n"
            f"Rode `nomi_nomi_no_mi.py importar --dir <seus_csvs>` primeiro "
            f"(ver contextos/README.md).",
            file=sys.stderr
        )
        sys.exit(1)

    engine = NomiNomiNoMi(args.db)
    try:
        if args.comando == 'buscar':
            resultado = engine.buscar(args.pedido, limite_criticas=args.limite)
            if args.json:
                print(json.dumps(resultado, indent=2, ensure_ascii=False))
            else:
                print(formatar_busca_texto(resultado))
        elif args.comando == 'detalhar':
            resultado = engine.detalhar(args.tabelas)
            if args.json:
                print(json.dumps(resultado, indent=2, ensure_ascii=False))
            else:
                print(formatar_detalhar_texto(resultado))
    finally:
        engine.fechar()


if __name__ == '__main__':
    main()
