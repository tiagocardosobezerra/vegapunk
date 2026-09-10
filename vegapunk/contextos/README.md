# Contexto: Punk Records — schema vazio (importe seus próprios dados)

Este diretório contém o **contexto de domínio** que a skill **Vegapunk**
consome para escrever T-SQL correto contra uma base cadastrada: a base em
si, chamada **Punk Records** (`punk_records.db`), e a documentação do
motor que a consulta — o **Nomi Nomi no Mi** (`scripts/nomi_nomi_no_mi.py`,
na pasta `../scripts`).

> ℹ️ **`punk_records.db` vem vazio nesta versão** — só as 5 tabelas de
> metadados (`tabelas` / `colunas` / `relacionamentos` / `sistemas` /
> `sinonimos`), sem nenhuma linha. Nenhuma tabela, coluna, módulo,
> sinônimo ou estrutura de nenhum ERP real acompanha este pacote — é um
> schema em branco para você importar os metadados do **seu próprio**
> sistema. Ver ["Como importar seus dados"](#como-importar-seus-dados) e
> "Licença e propriedade" no final deste documento.

- **Escopo:** motor genérico de descoberta de schema; banco vazio, pronto para import
- **Tecnologia:** Python 3.8+ (stdlib apenas) + SQLite
- **Status:** motor em produção; base local vazia por design

---

## Sumário

- [O que tem aqui](#o-que-tem-aqui)
- [Como importar seus dados](#como-importar-seus-dados)
- [Formato dos CSVs de import](#formato-dos-csvs-de-import)
- [Como a skill Vegapunk usa isto](#como-a-skill-vegapunk-usa-isto)
- [Arquitetura do motor (Nomi Nomi no Mi)](#arquitetura-do-motor-nomi-nomi-no-mi)
- [Suite de testes](#suite-de-testes)
- [Limitações conhecidas](#limitações-conhecidas)
- [Licença e propriedade](#licença-e-propriedade)

---

## O que tem aqui

```
contextos/
├── punk_records.db   # Punk Records — schema VAZIO (5 tabelas, 0 linhas)
└── README.md         # Este arquivo
```

O motor em si, o **Nomi Nomi no Mi** (`nomi_nomi_no_mi.py`), fica em
`../scripts/`, porque é código executável, não contexto — mas ele só
existe para consultar o que está aqui. O motor é **100% agnóstico de
domínio**: tudo que descreve um schema específico — tabelas, colunas,
relacionamentos, módulos e sinônimos — mora dentro do próprio
`punk_records.db`, em 5 tabelas. Não existe nenhum arquivo de
configuração externo: para usar em outro schema, basta importar dados
diferentes (ver "Como importar seus dados" abaixo), sem tocar no
código do motor.

### Estrutura da base (Punk Records — `punk_records.db`)

| Tabela            | Linhas hoje | Conteúdo esperado (depois do import)                                    |
|-------------------|-------------|---------------------------------------------------------------------------|
| `tabelas`         | 0           | Metadados por tabela: `score_relevancia`, `ranking`, `total_registros`, `tabelas_filhas`, `tabelas_pais`, `conexoes_totais`. Todos calculados automaticamente pelo comando `importar` — você não digita esses números. |
| `colunas`         | 0           | `tabela`, `coluna`, `descricao` — a descrição de negócio em PT-BR é a fonte real de significado para o matching semântico do motor. |
| `relacionamentos` | 0           | `tabela_filha`, `campo_filho`, `tabela_mae`, `campo_mae` — as FKs, usadas para montar JOINs e para calcular `tabelas_filhas`/`tabelas_pais`/`conexoes_totais`. |
| `sistemas`        | 0           | `codigo_sistema`, `nome_sistema`, `descricao` — o(s) módulo(s) do seu schema (prefixo de letra do nome da tabela → nome do módulo). Opcional: sem isso, o motor funciona mas não infere módulo nem filtra vizinhos por módulo. |
| `sinonimos`       | 0           | `termo`, `sinonimo` — vocabulário coloquial → vocabulário efetivamente usado nas descrições do seu schema (ex.: "colaborador" → "funcionário"). Opcional: sem isso, o motor busca só pelos termos literais do pedido. |

## Como importar seus dados

O motor inclui um comando `importar` que lê 5 arquivos CSV, **calcula
sozinho** os campos derivados (contagem de FKs, score de relevância,
ranking — você não precisa calcular isso na mão) e grava tudo no
`punk_records.db`:

```bash
python3 scripts/nomi_nomi_no_mi.py importar --dir ./meus_csvs/
# se contextos/punk_records.db já existir e você quiser sobrescrever:
python3 scripts/nomi_nomi_no_mi.py importar --dir ./meus_csvs/ --forcar
```

Passo a passo para chegar aos CSVs:

1. No seu próprio ambiente (você precisa já ter acesso legítimo/
   licenciado a ele), rode consultas de introspecção contra o
   dicionário de dados e o catálogo de relacionamentos do sistema (não
   contra dados de negócio) para extrair tabela/coluna/descrição, as
   FKs, os módulos/sistemas e, se fizer sentido no seu domínio, um
   dicionário de sinônimos coloquial → vocabulário do schema.
2. Exporte cada conjunto para um CSV com o formato descrito abaixo.
3. Rode `importar --dir`.
4. Teste: `python3 scripts/nomi_nomi_no_mi.py buscar "..."`.

Depois de importar, mantenha `contextos/punk_records.db` **fora do
controle de versão público** (`.gitignore`) — é metadado do schema de
um sistema de terceiros ao qual você tem acesso licenciado, não algo
para redistribuir. Ver ["Licença e propriedade"](#licença-e-propriedade).

## Formato dos CSVs de import

Todos em UTF-8, cabeçalho na primeira linha, um arquivo por tabela.
`tabelas.csv` e `colunas.csv` são **obrigatórios**; `relacionamentos.csv`,
`sistemas.csv` e `sinonimos.csv` são opcionais (o motor degrada
graciosamente sem eles — ver [Limitações conhecidas](#limitações-conhecidas)).

| Arquivo | Colunas obrigatórias | Colunas opcionais | Observação |
|---|---|---|---|
| `tabelas.csv` | `tabela` | `total_registros`, `descricao` | Uma linha por tabela. `score_relevancia`/`ranking`/`tabelas_filhas`/`tabelas_pais`/`conexoes_totais` são calculados pelo `importar`, não vão neste CSV. |
| `colunas.csv` | `tabela`, `coluna` | `descricao` | Uma linha por coluna. A `descricao` (negócio, em PT-BR) é o que o motor usa para casar com o pedido do usuário — sem ela, a busca semântica não funciona para essa coluna. |
| `relacionamentos.csv` | `tabela_filha`, `campo_filho`, `tabela_mae`, `campo_mae` | — | Uma linha por FK. Chave composta = uma linha por campo da composição. O `importar` confere se `tabela_filha`/`tabela_mae`/`campo_filho`/`campo_mae` realmente existem em `tabelas.csv`/`colunas.csv` — uma FK com typo não trava o import, mas sai um aviso no final apontando exatamente a linha problemática (essa FK fica no banco, só não vai gerar um `JOIN` válido até você corrigir o CSV e reimportar). |
| `sistemas.csv` | `codigo_sistema`, `nome_sistema` | `descricao` | Uma linha por módulo (ex.: `F,Folha,Modulo de folha de pagamento`). `codigo_sistema` deve bater com o prefixo de 1 letra do nome das tabelas desse módulo. |
| `sinonimos.csv` | `termo`, `sinonimo` | — | Uma linha por par. Um termo com 3 sinônimos = 3 linhas. Cadeias funcionam (ex.: `demissao,desligamento` + `desligamento,deligamento` expande "demissao" até "deligamento"). |

---

## Como a skill Vegapunk usa isto

A skill não lê o `.db` diretamente — ela chama o **Nomi Nomi no Mi**
(`nomi_nomi_no_mi.py`) via bash. Ver `../SKILL.md`, seção "Fluxo de
Descoberta de Schema", para o passo a passo completo. Resumo:

1. `python3 scripts/nomi_nomi_no_mi.py buscar "<pedido em pt-br>"` → tabelas candidatas (críticas + relacionadas via FK)
2. `python3 scripts/nomi_nomi_no_mi.py detalhar TAB1 TAB2 ...` → colunas exatas + FKs dessas tabelas
3. Só então o T-SQL é escrito, usando exclusivamente os nomes retornados pelo motor — nunca por memória/suposição.

Toda saída textual do motor (contagens, scores) segue o padrão numérico
pt-BR: `.` como separador de milhar e `,` como separador decimal (ex.:
`1.234.567,89`). Ao apresentar resultados de consultas T-SQL ao usuário,
a skill Vegapunk segue a mesma convenção, além de datas no formato
`dd/MM/aaaa` — nunca o padrão en-US (`MM/DD/YYYY`, `,` como decimal).

---

## Arquitetura do motor (Nomi Nomi no Mi)

```
0. CARREGAR DOMÍNIO DO BANCO
   Ao conectar, lê as tabelas `sistemas` e `sinonimos` do próprio
   punk_records.db e monta MODULOS_PRIORIZADOS / MODULO_NOMES /
   SINONIMOS em memória. Se vierem vazias (banco sem esse import),
   o motor funciona mesmo assim, só sem inferência de módulo/sinônimo.

1. EXTRAIR TERMOS + EXPANDIR SINÔNIMOS
   Input: "quero saber o salario dos colaboradores"
   → tokeniza (4+ caracteres, remove stop words)
   → expande sinônimos de domínio em cadeia (tabela `sinonimos`):
     "salario" → +remuneracao, +vencimento
   → normaliza números ordinais por extenso: "décimo terceiro" → "13"
   Output: [salario, colaboradores, remuneracao, vencimento]

2. NORMALIZAR + TOKENIZAR O ÍNDICE
   Remove acentuação/caixa; o índice de colunas.descricao é pré-tokenizado
   e pré-computa document frequency (df) de cada token, para IDF.

3. BUSCAR TABELAS CRÍTICAS (match por TOKEN exato, não substring)
   Casa termos contra o conjunto de tokens de colunas.descricao (e,
   à parte, contra o nome da tabela, para termos de 5+ caracteres ou
   números — códigos de tabela não são frases tokenizáveis).
   Cada termo pesado por IDF: idf(t) = log(N / (1 + df(t))).
   Score semântico = idf do termo MAIS ESPECÍFICO batido (peso cheio)
   + os demais termos batidos, com peso reduzido (ALPHA_TERMOS_EXTRA=0.3).

4. CALCULAR SCORE DINÂMICO
   'estrutura' = média de (score_relevancia, log(1+conexões)), cada um
   normalizado min-max dentro do conjunto de candidatos da busca.
   'conceitos' = score semântico do passo 3, em escala absoluta.
   score = peso_estrutura*100*estrutura + peso_conceitos*conceitos*ESCALA_CONCEITOS

5. EXPANDIR COM VIZINHOS FK
   Descoberta paginada: até 25 vizinhos × 10 páginas = 250 por âncora
   (evita carregar o grafo de relacionamento inteiro)

6. INFERIR MÓDULO + CONSOLIDAR
   Módulo provável inferido A POSTERIORI, a partir do módulo predominante
   entre as tabelas críticas de fato encontradas (não de palavras do
   pedido). Mescla críticas + expandidas, remove duplicatas, ordena por score.
```

### Pesos e constantes da fórmula (ajustáveis no topo de `nomi_nomi_no_mi.py`)

```python
PESOS_POR_MODULO = {
    'DEFAULT': {'estrutura': 0.30, 'conceitos': 0.70},
}
ESCALA_CONCEITOS = 6.0    # escala o score semântico para magnitude comparável à estrutura
ALPHA_TERMOS_EXTRA = 0.3  # peso dos termos batidos além do mais específico
```

Todos os valores acima foram calibrados via grid search contra a suite de
testes (não são chutes) — ver [Suite de testes](#suite-de-testes). Módulos
e sinônimos não entram mais nessa configuração — são dados (tabelas
`sistemas`/`sinonimos`), não código; para outro schema, importe dados
diferentes, sem editar o motor.

---

## Suite de testes

`../scripts/stella.py` (nome de referência: Stella, a personalidade
original do Vegapunk, que dá a palavra final sobre as demais — aqui, a
suíte que confirma se o motor ainda se comporta como esperado depois de
qualquer mudança, seja import de dados novo ou alteração de
estrutura/fórmula) roda consultas reais rotuladas manualmente (pedido em
PT-BR → tabela(s) esperada(s)) contra o motor e reporta passou/falhou por
caso. Por padrão, o próprio script **gera uma fixture fictícia temporária**
(as 5 tabelas, dados inventados) para rodar contra — nada é escrito em
`contextos/`, e a fixture some ao final da execução:

```bash
python3 scripts/stella.py           # gera e usa a fixture fictícia embutida
python3 scripts/stella.py -v        # mostra o ranking completo por caso
python3 scripts/stella.py --db contextos/punk_records.db   # usa um banco já importado (seu schema real)
```

Os casos estão organizados em quatro grupos:

- **Integridade**: não é sobre score/ranking — é um smoke test do caminho
  `importar` (CSV) → `detalhar`/`buscar` → JSON, que os três grupos
  abaixo não cobrem (eles chamam `buscar()` direto em memória contra uma
  fixture que já nasce pronta, nunca passando pelo parsing de CSV nem
  pelo `detalhar`). Faz um round-trip real de CSV com uma FK
  propositalmente errada e confirma que o aviso de integridade
  referencial (ver "Formato dos CSVs de import" acima) continua
  disparando, que `detalhar()` devolve o esperado, e que tudo é
  serializável em JSON.
- **Calibração** (12 casos): usados para ajustar pesos/constantes da fórmula.
  Passar aqui não é evidência forte — é o mínimo esperado.
- **Held-out** (10 casos): cobrem os mesmos tipos de caso-limite (tabela
  hub, tabela órfã, termo genérico, ordinal por extenso) sem terem sido
  usados para calibrar os pesos atuais.
- **Validação cega** (8 casos): criados por último, sem uso nenhum na
  calibração. É o número mais confiável de "o motor generaliza ou só
  decorou os exemplos".

Misturar os três últimos grupos ao calibrar a fórmula invalida a validação.

**Resultado atual, contra a fixture fictícia embutida:** integridade OK +
30/30 (100%) nos grupos de calibração — 12/12 calibração, 10/10 held-out,
8/8 validação cega. Medido rodando o comando acima; não é uma garantia
para o seu schema real (maior, com distribuição de termos diferente).
Depois de importar seus dados, escreva seus próprios casos (mesmo
formato: pedido → tabela(s) esperada(s), 3 grupos) usando os nomes reais
do seu schema e rode com `--db` — é o que dá sinal de qualidade real para
o SEU schema.

A fixture fictícia embutida é gerada com um `random.Random` isolado por
tabela (semente + nome da tabela) — os dados sintéticos de uma tabela
nunca mudam por causa de outra tabela ter sido adicionada, removida ou
alterada, então uma mudança no número de tabelas de ruído (ou em
qualquer outra parte da fixture) nunca desloca o resultado de um caso
que não tem nada a ver com essa mudança. O `score_relevancia`/`ranking`
sintéticos são calculados pela MESMA função usada pelo `importar`
(`calcular_metricas_e_scores`, não uma cópia) — se a fórmula real mudar,
a suíte passa a validar contra a fórmula nova automaticamente.

Ao adicionar uma constante nova à fórmula, siga o mesmo processo: crie casos
de teste ANTES de calibrar, guarde-os de lado, calibre só contra
calibração+held-out, e só então valide contra os casos novos. Se um caso
"held-out" ou "validação cega" for usado para ajustar algo, ele deixa de
servir para medir generalização — mova-o para "calibração" e crie um lote
novo.

---

## Limitações conhecidas

1. **Tamanho mínimo de termo:** só palavras com 4+ caracteres entram na
   busca (exceto números de 2-3 dígitos, ex.: "13").
2. **Limite de vizinhos:** máximo 250 tabelas relacionadas por âncora (por desenho).
3. **Sinônimos são um dicionário fixo, não NLP:** procure padrões nas
   descrições reais de coluna do seu schema (atalhos, abreviações,
   typos legados) e coloque em `sinonimos.csv` — o motor não infere
   sinônimo sozinho.
4. **Sem `sistemas`/`sinonimos` importados, o motor ainda funciona, mas
   pior:** sem inferência de módulo (mostra `?`) e sem expansão de
   termo coloquial — a busca passa a depender só dos termos literais
   do pedido batendo literalmente nas descrições de coluna.
5. **Tabelas pequenas/órfãs ainda podem perder posição:** tabelas com
   poucas conexões e baixo `score_relevancia` podem ficar fora do
   top-3/5 quando a consulta usa também termos genéricos que batem em
   tabelas maiores — sensível ao tamanho e à distribuição estatística
   do schema importado.
6. **Ambiguidade lexical:** palavras polissêmicas (ex.: "portaria" =
   recepção OU decreto administrativo) podem puxar tabelas erradas — é
   uma limitação inerente de matching léxico, não um bug pontual
   corrigível sem busca semântica (embeddings).
7. **Idioma:** português (BR) apenas.
8. **Amostra de calibração pequena:** os pesos da fórmula foram
   calibrados contra 30 casos rotulados manualmente — suficiente para
   pegar erros grosseiros, mas pequeno para calibração fina por módulo.
9. **Snapshot:** a base Punk Records é uma foto do schema no momento do
   import; se o schema real mudar, rode `importar` de novo.

---

## Licença e propriedade

O motor **Nomi Nomi no Mi** é deste repositório. O `punk_records.db`
publicado é um schema **vazio** — só a estrutura de 5 tabelas de
metadados (nome de tabela/coluna, descrição de negócio, módulo,
sinônimo — nunca dados de cliente), sem conteúdo de nenhum sistema
real. Foi desenhado para ser genérico e reutilizável contra qualquer
schema, incluindo ERPs proprietários de mercado — preenchido localmente
por você (ver ["Como importar seus dados"](#como-importar-seus-dados))
a partir de um ambiente ao qual já tem acesso legítimo. Mantenha o
arquivo populado **fora do controle de versão público** depois de
importar.
