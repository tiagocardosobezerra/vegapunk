"""
Configuração do domínio schema: caminho padrão da base, módulos e
sinônimos carregados da própria base (`carregar_dominio_do_db`) e as
constantes da fórmula de score (pesos, penalidades, limiares).

`MODULOS_PRIORIZADOS`, `SINONIMOS` e `MODULO_NOMES` são estado do
domínio carregado: `NomiNomiNoMi.__init__` os reatribui aqui, e quem lê
acessa sempre `config.<NOME>`, nunca uma cópia importada.

Parte do Nomi Nomi no Mi, movida sem mudança de algoritmo do antigo
`scripts/nomi_nomi_no_mi.py` (fase 1 da v3).
"""

import os
import sqlite3
from collections import defaultdict
from typing import Dict, Set

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

# Instância local (Egghead): pasta da base, dos logs e dos goldens reais.
# VEGAPUNK_EGGHEAD aponta para outra pasta (ex.: o Atlas, para provar que o
# domínio de fórmulas roda sem a base de schema).
VAR_AMBIENTE_EGGHEAD = 'VEGAPUNK_EGGHEAD'
RAIZ_EGGHEAD = os.environ.get(VAR_AMBIENTE_EGGHEAD) or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'egghead')
DEFAULT_DB_PATH = os.path.join(RAIZ_EGGHEAD, 'punk_records.db')

# Estrutura de coluna guardada na base a partir da migração 002 (fase 2 da
# v3). Nenhuma delas entra no ranking da busca; o `detalhar` as expõe.
COLUNAS_ESTRUTURA = ('tipo', 'tamanho', 'precisao', 'escala', 'nulo', 'ordem', 'pk_ordem')

# Caminho de JOIN entre tabelas pedidas no detalhar (fase 2): menor caminho
# no grafo de FK, até este número de saltos.
MAX_SALTOS_CAMINHO = 4

# Aviso "Sem caminho" do detalhar (fase 2b): lista só os primeiros pares;
# a lista completa fica em `caminhos`.
LIMITE_PARES_SEM_CAMINHO = 10


def carregar_dominio_do_db(conn: sqlite3.Connection):
    """Carrega módulos e sinônimos das tabelas `sistemas` e `sinonimos`
    do próprio banco — nunca de um arquivo externo. Assim o mesmo motor
    serve para qualquer schema: basta importar dados diferentes para
    `--db` (ver comando `importar`), sem tocar no código.

    `sistemas`: codigo_sistema, nome_sistema, descricao (uma linha por módulo)
    `sinonimos`: termo, sinonimo (uma linha por par; um termo com N
                 sinônimos = N linhas)

    Se as tabelas ainda não existirem ou estiverem vazias (banco recém
    criado, sem import), devolve estruturas vazias — o motor continua
    funcionando, só sem inferência de módulo nem expansão de sinônimo.
    """
    cur = conn.cursor()
    modulos = {}
    try:
        cur.execute("SELECT codigo_sistema, nome_sistema FROM sistemas")
        for codigo_sistema, nome_sistema in cur.fetchall():
            modulos[codigo_sistema] = nome_sistema
    except sqlite3.OperationalError:
        pass  # tabela `sistemas` ainda não existe neste banco

    sinonimos = defaultdict(list)
    try:
        # migração 008: `uso` separa os pares da busca (NULL ou 'busca') dos de
        # outra regra (ex.: 'essencial', só da regra do termo essencial)
        tem_uso = 'uso' in {r[1] for r in cur.execute('PRAGMA table_info(sinonimos)').fetchall()}
        cur.execute("SELECT termo, sinonimo FROM sinonimos"
                    + (" WHERE uso IS NULL OR uso = 'busca'" if tem_uso else ''))
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
# Calibrado via grid search contra os casos de casos/consultas_fixture.json (não chute):
# testadas as combinações 0.70/0.30 até 0.10/0.90 de estrutura/conceitos;
# 0.30/0.70 venceu de forma estável entre os grupos de calibração e
# held-out. Os números atuais de acerto por grupo (calibração/held-out/
# validação cega) estão em egghead/linha_de_base_v3.json (instância) — rode
# `pythagoras.py avaliar --dominio schema` para reproduzir. Os casos de teste disponíveis
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

# Item 4 (ambiguidade): quando a diferença relativa entre o score do
# 1º e do 2º colocado é menor que este limiar, os dois são "próximos
# demais" para decidir sozinho — sinaliza em vez de escolher em
# silêncio. Não é uma calibração fina (não há suíte rotulada de
# ambiguidade ainda), é um valor conservador: 12% de diferença já é
# folga razoável entre 1º e 2º lugar em scores que passam por min-max.
LIMIAR_AMBIGUIDADE = 0.12

# Item 3 (fuzzy fallback): distância mínima de similaridade (0-1,
# SequenceMatcher.ratio) para aceitar um termo do vocabulário do
# schema como correção aproximada de um termo do pedido que não bateu
# literalmente em nada. 0.82 é conservador de propósito — o objetivo é
# pegar erro de digitação/abreviação óbvia, não "adivinhar" um termo
# não relacionado.
FUZZY_CUTOFF_PADRAO = 0.82

# Item 2 (auditoria de inovação): penalidade multiplicativa aplicada ao
# score_dinamico de tabelas cujo prefixo NÃO está cadastrado na tabela
# `sistemas`. 0.6 é conservador de propósito — reduz a prioridade sem
# zerar, porque uma tabela "não classificada" ainda pode ser a resposta
# certa (era exatamente o caso do módulo 'Z': tabelas reais, só sem
# cadastro). Ajustável aqui sem editar a lógica de busca.
PENALIDADE_MODULO_NAO_CADASTRADO = 0.6

# Achado em auditoria (relatório de lote contábil, setembro/2026):
# uma tabela de STAGING/temporária bem documentada (muitas colunas com
# descrição rica) pode vencer o ranking com score_dinamico alto mesmo tendo
# ZERO sinal estrutural — porque o eixo `conceitos` (IDF de coluna) entra em
# escala ABSOLUTA e não é achatado pelo eixo `estrutura` quando este é zero.
# Caso real: uma tabela de staging vazia (0 FKs no snapshot) ficou em 1º
# lugar na frente da tabela realmente persistida (com FKs) — nomes de
# tabela/fornecedor não repetidos aqui, ver AVISO.md. Esta
# penalidade é deliberadamente estreita: só dispara quando a tabela não tem
# NENHUMA conexão via FK, não para qualquer tabela pequena — uma tabela
# nova/recém-implantada mas já com FKs declaradas não é penalizada por isto.
# 0.5 é conservador de propósito, no mesmo espírito de
# PENALIDADE_MODULO_NAO_CADASTRADO: reduz a prioridade sem zerar, porque
# a tabela ainda PODE ser a resposta certa (ambiente recém-implantado).
#
# ATUALIZAÇÃO (auditoria de privacidade, setembro/2026): a condição original
# também exigia total_registros==0 além de conexoes==0 ("E", não "OU"). Esse
# segundo termo foi removido junto com a própria coluna `total_registros`
# (o motor não lê/grava mais contagem de linha de tabela nenhuma — é dado
# sensível de volume de negócio, desnecessário para achar a tabela certa).
# Na prática isso já era quase irrelevante: no ambiente real onde o caso
# acima foi encontrado, `total_registros` estava em 0 para 100% das tabelas
# importadas, então a condição "E" já rodava, de fato, como se fosse só
# `conexoes == 0`. Agora isso é literal, não um efeito colateral de dado
# ausente.
# 0.5 não foi calibrado por grid search nem por casos confirmados — foi
# escolhido por analogia ao 0.6 acima. Recalibrar quando houver massa
# suficiente de uso real (ver pythagoras.py).
PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL = 0.5

# Constantes da fórmula de score (nível de módulo para poderem ser
# recalibradas/grid-searched sem editar dentro dos métodos):
ESCALA_CONCEITOS = 6.0      # escala o IDF bruto para magnitude comparável à estrutura (0-100)
ALPHA_TERMOS_EXTRA = 0.3    # peso dos termos batidos ALÉM do mais específico (ver
                             # _buscar_criticas — o termo de maior IDF entra com peso
                             # cheio, os demais entram reduzidos, para tabelas pequenas
                             # e certeiras não perderem para tabelas grandes que batem
                             # vários termos genéricos). Calibrado via grid search contra
                             # os casos de calibração/held-out (casos/consultas_fixture.json) —
                             # números de acerto atuais em egghead/linha_de_base_v3.json.
