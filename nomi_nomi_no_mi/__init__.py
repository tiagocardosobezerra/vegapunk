#!/usr/bin/env python3
"""
================================================================================
 NOMI NOMI NO MI  (motor de descoberta de schema por linguagem natural)  —  v1.0
================================================================================
Motor de descoberta de schema genérico: dado um pedido em linguagem
natural (PT-BR) e uma base de metadados de schema (5 tabelas — ver
referencias/schema.md), retorna as tabelas mais relevantes, suas colunas
(com descrição de negócio) e os relacionamentos (FKs) entre elas —
tudo que é necessário para a skill Vegapunk escrever T-SQL correto sem
"adivinhar" nomes de tabela/coluna.

O motor é 100% agnóstico de domínio: TUDO que descreve um schema
específico — tabelas, colunas, relacionamentos, sistemas/módulos e
sinônimos de negócio — vem de dentro do próprio banco Punk Records
(`egghead/punk_records.db`), em 5 tabelas:

    tabelas          — metadados estruturais por tabela
    colunas          — nome + descrição de negócio (PT-BR) de cada coluna
    relacionamentos  — FKs entre tabelas
    sistemas         — código do sistema/módulo -> nome (ex: 'F' -> 'Folha')
    sinonimos        — termo -> sinônimo (vocabulário coloquial -> vocabulário do schema)

Nada disso fica hardcoded no motor nem em arquivo de config externo —
não existe mais `--dominio`/JSON separado. O banco publicado neste
repositório vem com as 5 tabelas VAZIAS (só o schema); para usar,
importe seus próprios metadados (ver referencias/schema.md, seção "Como
importar seus dados"). Um comando `importar` está incluído para isso
(ver "3) Importar seus dados" abaixo).

Uso via linha de comando (chamado pela skill Vegapunk):

    # 1) Descobrir tabelas candidatas a partir de um pedido em PT-BR
    python3 stella.py buscar --dominio schema "preciso da data de admissão dos colaboradores"

    # 2) Detalhar tabelas específicas (colunas + relacionamentos/FKs)
    python3 stella.py detalhar --dominio schema F_FUNCIONARIO T_APROVACAO_EXPORTACAO

    # 3) Importar seus dados a partir de CSVs (ver referencias/schema.md)
    python3 satelites/york.py importar --dir ./meus_csvs/

    # 4) Saída em JSON puro (para parsing programático)
    python3 stella.py buscar --dominio schema "folha de pagamento" --json
    python3 stella.py detalhar --dominio schema F_FUNCIONARIO --json

    # 5) Apontar para outro banco (ex: uma cópia fora do repositório)
    python3 stella.py --db /caminho/privado/schema.db buscar --dominio schema "..."

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
avaliação do schema (`satelites/pythagoras.py avaliar --dominio schema`), rodando pedidos rotulados
manualmente (pedido -> tabela esperada) antes e depois de cada mudança,
separados em grupos de calibração/held-out/validação cega — ver
"Suite de testes" em `referencias/schema.md`.
================================================================================
"""

# API pública do núcleo (cada parte mora no seu módulo; ver a lista abaixo).
#   texto_comum.py  normalização e formatação pt-BR comuns aos dois domínios
#   texto.py        radical, tokenização e extração de termos do schema
#   indice.py       índice de colunas, IDF, fuzzy
#   busca.py        NomiNomiNoMi (buscar, detalhar) e inferência de módulo
#   grafo.py        expansão por FK e consolidação
#   saida.py        saída em texto
#   manutencao.py   cobertura de módulos
#   historico.py    log de uso e confirmações
# Configuração e constantes do domínio: dominios/schema/config.py.
#
# Os nomes abaixo são resolvidos sob demanda (PEP 562): importar
# `nomi_nomi_no_mi.texto_comum` não carrega o domínio schema, e o domínio de
# fórmulas pode usar o núcleo comum sem depender dele.
_EXPORTS = {
    'DEFAULT_DB_PATH': 'dominios.schema.config', 'PESOS_POR_MODULO': 'dominios.schema.config',
    'NomiNomiNoMi': 'nomi_nomi_no_mi.busca', 'inferir_modulo_por_resultado': 'nomi_nomi_no_mi.busca',
    'ler_historico_confirmado': 'nomi_nomi_no_mi.historico', 'registrar_uso': 'nomi_nomi_no_mi.historico',
    'checar_cobertura_modulos': 'nomi_nomi_no_mi.manutencao',
    'formatar_busca_texto': 'nomi_nomi_no_mi.saida', 'formatar_detalhar_texto': 'nomi_nomi_no_mi.saida',
    'extrair_termos': 'nomi_nomi_no_mi.texto', 'radical': 'nomi_nomi_no_mi.texto', 'tokenizar': 'nomi_nomi_no_mi.texto',
    'normalizar': 'nomi_nomi_no_mi.texto_comum', 'formatar_numero_ptbr': 'nomi_nomi_no_mi.texto_comum',
}


def __getattr__(nome):
    if nome in _EXPORTS:
        import importlib
        return getattr(importlib.import_module(_EXPORTS[nome]), nome)
    raise AttributeError(f'module {__name__!r} has no attribute {nome!r}')
