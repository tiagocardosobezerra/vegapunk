# Domínio schema: Punk Records e o motor Nomi Nomi no Mi

Referência técnica do domínio **schema** (descoberta de schema por
linguagem natural), carregada sob demanda a partir do `SKILL.md`: a base
**Punk Records** (`punk_records.db`), como importar seus metadados, o
formato dos CSVs e a arquitetura do motor **Nomi Nomi no Mi**
(`nomi_nomi_no_mi/`).

> ℹ️ **Duas versões, o mesmo motor.** No **Vegapunk** (distribuível) não
> existe base: a pasta `egghead/` vem vazia ou nem existe, e o domínio
> schema roda em modo básico até você importar os metadados do **seu
> próprio** sistema. No **Vegapunk com Punk Records** (privado, para uso
> no próprio ambiente) a base já foi importada e fica em
> `egghead/punk_records.db`. Os números atuais da sua base saem de
> `python3 stella.py status`; nenhum número fixo é repetido aqui. Ver
> ["Como importar seus dados"](#como-importar-seus-dados) e "Licença e
> propriedade" no final deste documento.

- **Escopo:** motor genérico de descoberta de schema
- **Tecnologia:** Python 3.8+ (stdlib apenas) + SQLite
- **Regra de ouro:** só estrutura entra (tabelas, colunas, descrições, tipos, ligações); nenhuma linha de conteúdo

---

## Sumário

- [O que tem aqui](#o-que-tem-aqui)
- [Como importar seus dados](#como-importar-seus-dados)
- [Formato dos CSVs de import](#formato-dos-csvs-de-import)
- [Estrutura física: tipos, PK e constraints (`enriquecer`)](#estrutura-física-tipos-pk-e-constraints-enriquecer)
- [Como a skill Vegapunk usa isto](#como-a-skill-vegapunk-usa-isto)
- [Arquitetura do motor (Nomi Nomi no Mi)](#arquitetura-do-motor-nomi-nomi-no-mi)
- [Suite de testes](#suite-de-testes)
- [Limitações conhecidas](#limitações-conhecidas)
- [Licença e propriedade](#licença-e-propriedade)

---

## O que tem aqui

```
egghead/                      instância local (fora do controle de versão)
├── punk_records.db           a base Punk Records (só estrutura)
├── punk_records_log.jsonl    log de uso: buscar / confirmar
├── punk_records_pesos.json   pesos calibrados pelo Pythagoras (se houver)
├── punk_records_golden.json  golden real do Atlas
└── backups/                  cópias de segurança das migrações
nomi_nomi_no_mi/              o motor: texto, índice, busca, grafo, saída, manutenção, histórico
dominios/schema/config.py     configuração e constantes do domínio
punk_records/schema.py        importação (usada só pelo York)
```

O motor **Nomi Nomi no Mi** é **100% agnóstico de domínio**: tudo que
descreve um schema específico — tabelas, colunas, relacionamentos,
módulos e sinônimos — mora dentro do próprio `punk_records.db`. Não
existe nenhum arquivo de configuração externo: para usar em outro schema,
basta importar dados diferentes (ver "Como importar seus dados" abaixo),
sem tocar no código do motor. A pasta da instância pode ser trocada pela
variável `VEGAPUNK_EGGHEAD`.

Para mais de um banco, crie uma instância por banco: `egghead-<nome>/`, ao
lado de `egghead/` e também fora do git. `--instancia <nome>` no `stella.py`
e no `york.py` aponta a pasta para aquele comando (`--instancia egghead`
volta à padrão), e `python3 stella.py instancias` lista todas, com a ativa
marcada. Um `instancia.json` opcional em cada pasta descreve o banco:

```json
{"descricao": "o que este banco guarda", "assuntos": ["palavra", "outra palavra"]}
```

É por ele, e por `python3 stella.py instancias --pedido "<pedido>"`, que o
Claude escolhe a instância de cada pedido. O `--pedido` mede, sem gravar
log, quantos termos do pedido cada base cobre (palavra de descrição,
radical, sinônimo da própria base ou pedaço de nome de tabela com 5+
letras) e quais assuntos ele cita; diz a mais provável ou `EMPATE`.

O que muda com várias instâncias:

- `--instancia` vale no `stella.py`, `york.py`, `edison.py`, `atlas.py` e
  `memory_card.py`; instância inexistente ou nome inválido sai com código 2.
- Logs de uso, confirmações e soluções candidatas ficam na instância usada.
  Confirmar uma tabela que só existe em outra instância avisa qual é.
- A base de cada instância tem os seus próprios sinônimos e sistemas.
- Um banco com mais de um schema e nomes de tabela repetidos entre eles: uma
  instância por schema (`egghead-<banco>-<schema>`). A Punk Records identifica
  tabela pelo nome, sem o schema; duas tabelas com o mesmo nome numa base só
  se confundem.
- Nome em caixa mista (`QzCadastro`) é achado em qualquer grafia no `detalhar`, e
  o SQL montado usa o nome gravado.
- Sigla de 2 ou 3 letras escrita em maiúsculas no pedido (`EPI`, `PIS`) vira
  termo e casa com a mesma sigla em maiúsculas nas descrições; em minúsculas
  ela é palavra comum e fica de fora, como antes.
- Cada instância pode ter um `casos_atlas.json` (lista de pedidos): o
  `atlas.py capturar --db <cópia>` protege esses pedidos no golden dela, e a
  suíte confere o golden de toda `egghead-<nome>/` que tem um.
- O Memory Card é um só (ver [memory-card.md](memory-card.md)).
- A checagem de nomes reais da distribuição confere contra todas as
  instâncias; o `termos_proibidos.json` de cada uma vale para a dela, e a
  chave `permitidos` tira da régua um nome real que só coincide com
  vocabulário do motor.

### Estrutura da base (Punk Records — `punk_records.db`)

| Tabela            | Linhas na versão vazia | Conteúdo esperado (depois do import)                                    |
|-------------------|-------------|---------------------------------------------------------------------------|
| `tabelas`         | 0           | Metadados por tabela: `score_relevancia`, `ranking`, `tabelas_filhas`, `tabelas_pais`, `conexoes_totais`. Todos calculados automaticamente pelo comando `importar` — você não digita esses números. O motor não lê nem grava contagem de linha (`total_registros`) de tabela nenhuma — só metadados estruturais (nome/coluna/FK), nunca volume de dado real (removido por privacidade, setembro/2026). A única exceção é `tem_dados` (0/1, opcional no CSV — ver tabela de formato abaixo): um booleano "a tabela tem alguma linha?", sem expor quantas — usado só para refinar a penalidade de tabela sem lastro estrutural (ver Limitações conhecidas, item 5). |
| `colunas`         | 0           | `tabela`, `coluna`, `descricao` — a descrição de negócio em PT-BR é a fonte real de significado para o matching semântico do motor. Desde a versão 2 da base, também a estrutura física (opcional, `NULL` quando não veio): `tipo` (tipo base do SQL Server), `tamanho` (em caracteres nos tipos Unicode; `-1` = max), `precisao`, `escala`, `nulo` (0/1), `ordem` (posição na tabela) e `pk_ordem` (posição na chave primária; `NULL` = fora da PK). |
| `relacionamentos` | 0           | `tabela_filha`, `campo_filho`, `tabela_mae`, `campo_mae` — as FKs, usadas para montar JOINs e para calcular `tabelas_filhas`/`tabelas_pais`/`conexoes_totais`. Desde a versão 2: `constraint_nome` e `ordem` (posição do campo na constraint). As linhas com o mesmo `constraint_nome` formam uma FK só; é isso que permite agrupar chave composta e entregar o JOIN pronto. Desde a versão 3: `ligacao`, o número da ligação do dicionário do sistema (as linhas com o mesmo número são uma ligação só). |
| `sistemas`        | 0           | `codigo_sistema`, `nome_sistema`, `descricao` — o(s) módulo(s) do seu schema (prefixo de letra do nome da tabela → nome do módulo). Opcional: sem isso, o motor funciona mas não infere módulo nem filtra vizinhos por módulo. |
| `sinonimos`       | 0           | `termo`, `sinonimo` — vocabulário coloquial → vocabulário efetivamente usado nas descrições do seu schema (ex.: "colaborador" → "funcionário"). Opcional: sem isso, o motor busca só pelos termos literais do pedido. |
| `meta`            | —           | `chave`, `valor` — versão do schema da própria base (`versao_schema`) e registro de cada migração aplicada (`migracao:NNN`). Criada pela migração 001; uma base sem `meta` está na versão 0. Guarda também o hash do mapa compilado (`mapa:sha256`) e se ele é fictício (`mapa:ficticio`). |
| `mapa_*`          | 0           | Camada Mapa (versões 4 a 6): `mapa_cadastros`, `mapa_rotulos`, `mapa_funcoes`, `mapa_estruturas`, `mapa_papeis` e `mapa_funcoes_consulta`. Só nomes de tabela, coluna e função, preenchidos pelo `york.py compilar-mapa` a partir do `mapa.json` (ver [formulas.md](formulas.md), seção Mapa); nunca conteúdo. |

**Versão da base e migrações.** A estrutura da Punk Records muda só por
migrações numeradas (`punk_records/migracoes.py`, pelo York), nunca por
`ALTER TABLE` avulso. `python3 satelites/york.py migrar status` mostra a
versão e o que está pendente; `python3 satelites/york.py migrar aplicar`
faz antes uma cópia de segurança em `egghead/backups/` (fora do controle de
versão), roda cada migração numa transação e, se algo falhar, devolve a
cópia. O motor não migra sozinho ao abrir a base, e o `importar` preserva a
`meta` (ele só recria as 5 tabelas de schema). Migrações existentes: 001
(cria a `meta`), 002 (colunas de estrutura física em `colunas` e
`relacionamentos`, todas anuláveis; não mexe em nenhuma linha), 003
(`relacionamentos.ligacao`, anulável, preenchida pelo `enriquecer
--dicionario`), 004 (camada Mapa: tabelas `mapa_*`, vazias, preenchidas
pelo `york.py compilar-mapa`) e 005 (prova e fonte de cada rótulo do mapa).

## Como importar seus dados

O York tem um comando `importar` que lê 5 arquivos CSV, **calcula
sozinho** os campos derivados (contagem de FKs, score de relevância,
ranking — você não precisa calcular isso na mão) e grava tudo no
`punk_records.db`:

```bash
python3 satelites/york.py importar --dir ./meus_csvs/
# se egghead/punk_records.db já existir e você quiser sobrescrever:
python3 satelites/york.py importar --dir ./meus_csvs/ --forcar
```

O York é a única porta de escrita na base: importar, gravar sinônimos
revisados (`york.py gravar-sinonimos`) e migrar.

Passo a passo para chegar aos CSVs:

1. No seu próprio ambiente (você precisa já ter acesso legítimo/
   licenciado a ele), rode consultas de introspecção contra o
   dicionário de dados e o catálogo de relacionamentos do sistema (não
   contra dados de negócio) para extrair tabela/coluna/descrição, as
   FKs, os módulos/sistemas e, se fizer sentido no seu domínio, um
   dicionário de sinônimos coloquial → vocabulário do schema.
2. Exporte cada conjunto para um CSV com o formato descrito abaixo.
3. Rode `importar --dir`.
4. Teste: `python3 stella.py buscar --dominio schema "..."` e `python3 stella.py status`.

Depois de importar, mantenha `egghead/` **fora do
controle de versão** (o `.gitignore` do plugin já faz isso) — é metadado do schema de
um sistema de terceiros ao qual você tem acesso licenciado, não algo
para redistribuir. Ver ["Licença e propriedade"](#licença-e-propriedade).

## Formato dos CSVs de import

Todos em UTF-8, cabeçalho na primeira linha, um arquivo por tabela.
`tabelas.csv` e `colunas.csv` são **obrigatórios**; `relacionamentos.csv`,
`sistemas.csv` e `sinonimos.csv` são opcionais (o motor degrada
graciosamente sem eles — ver [Limitações conhecidas](#limitações-conhecidas)).

| Arquivo | Colunas obrigatórias | Colunas opcionais | Observação |
|---|---|---|---|
| `tabelas.csv` | `tabela` | `descricao`, `tem_dados` | Uma linha por tabela. `score_relevancia`/`ranking`/`tabelas_filhas`/`tabelas_pais`/`conexoes_totais` são calculados pelo `importar`, não vão neste CSV. Não inclua contagem de linha/registro — o motor não usa esse dado (é sensível e não é necessário para achar a tabela certa). `tem_dados` é a única exceção parcial: um booleano (`1`/`true`/`sim`/`s`/`yes`/`y` = verdadeiro, qualquer outro valor ou ausência = falso) que diz só *se* a tabela tem alguma linha, nunca *quantas* — usado para refinar a penalidade de tabela sem lastro estrutural (ver Limitações conhecidas, item 5). |
| `colunas.csv` | `tabela`, `coluna` | `descricao`, `tipo`, `tamanho`, `precisao`, `escala`, `nulo`, `ordem`, `pk_ordem` | Uma linha por coluna. A `descricao` (negócio, em PT-BR) é o que o motor usa para casar com o pedido do usuário — sem ela, a busca semântica não funciona para essa coluna. As colunas de estrutura física são opcionais (CSV antigo, só com as 3 primeiras, continua valendo). |
| `relacionamentos.csv` | `tabela_filha`, `campo_filho`, `tabela_mae`, `campo_mae` | `constraint`, `ordem` | Uma linha por campo de FK; `constraint` (nome da FK) agrupa os campos de uma chave composta. Também aceita o formato do dicionário do sistema: uma linha por ligação, com os campos em lista na mesma ordem nas duas pontas (`"CODEMP,CODPAI"`); o York grava uma linha por campo com o número da ligação. Chave composta = uma linha por campo da composição. O `importar` confere se `tabela_filha`/`tabela_mae`/`campo_filho`/`campo_mae` realmente existem em `tabelas.csv`/`colunas.csv` — uma FK com typo não trava o import, mas sai um aviso no final apontando exatamente a linha problemática (essa FK fica no banco, só não vai gerar um `JOIN` válido até você corrigir o CSV e reimportar). |
| `sistemas.csv` | `codigo_sistema`, `nome_sistema` | `descricao` | Uma linha por módulo (ex.: `F,Folha,Modulo de folha de pagamento`). `codigo_sistema` deve bater com o prefixo de 1 letra do nome das tabelas desse módulo. |
| `sinonimos.csv` | `termo`, `sinonimo` | — | Uma linha por par. Um termo com 3 sinônimos = 3 linhas. Cadeias funcionam (ex.: `demissao,desligamento` + `desligamento,deligamento` expande "demissao" até "deligamento"). |

O leitor do York aceita UTF-8 e UTF-16 (o padrão do SSMS), ignora linhas em
branco e o rodapé do SSMS ("Completion time", "rows affected") e desembrulha
a exportação "Save Results As" da grade (linha inteira entre aspas). Um CSV
vazio ou só com cabeçalho é recusado antes de qualquer escrita: quase sempre
é uma extração que falhou. O texto literal `NULL` (como o SSMS exporta um
campo nulo) vira vazio; o relatório do `importar` e do `enriquecer` diz
quantos campos foram convertidos.

## Estrutura física: tipos, PK e constraints (`enriquecer`)

A estrutura física vem do **catálogo** do SQL Server, por três consultas em
`punk_records/extracao/` (uma por CSV): `tabelas.sql`, `colunas.sql` e
`relacionamentos.sql`. Elas leem só `sys.*`, nunca uma tabela de usuário,
rodam no SSMS sem modo SQLCMD e não citam nome de banco (rode com o banco
certo selecionado). O schema é a variável `@esquema` no topo de cada uma
(padrão `dbo`); se o schema não tiver tabelas, a consulta falha e lista os
schemas que existem. Grave cada resultado em `egghead/extracao/` (fora do
controle de versão) e rode:

```bash
python3 satelites/york.py migrar aplicar        # uma vez: base na versão 2
python3 satelites/york.py enriquecer --dir egghead/extracao
```

**Views.** A extração lê só tabelas por padrão. Um relatório que usa uma
view (ex.: uma view de hierarquia) aparece no Memory Card e no `solucionar`
com "tabela ... não existe na base". Para trazer as views, rode o
`tabelas.sql` e o `colunas.sql` de novo com `@objeto = 'V'`, grave os dois
CSVs em `egghead/extracao/views/` e acrescente na base, no lugar:

```bash
python3 satelites/york.py atualizar --dicionario egghead/extracao/views --catalogo egghead/extracao/views
python3 satelites/york.py atualizar --dicionario egghead/extracao/views --catalogo egghead/extracao/views --aplicar
```

O primeiro só lista o que muda. A lista "tabelas fora do export" é o resto
da base e não é removida. As views entram sem PK, sem FK e com
`tem_dados=0`: a busca as acha pelas colunas, mas o JOIN com elas nunca sai
provado. Como a base muda, o golden do Atlas da instância precisa de uma
nova captura, com o seu aceite.

O `enriquecer` faz cópia de segurança e roda numa transação. Ele só faz
`UPDATE` em linhas que já existem (nome de tabela e coluna sem diferenciar
caixa): nunca cria tabela, coluna ou FK e nunca mexe em descrição, nos 4
campos de uma FK, em `tem_dados` ou nas métricas. A busca não muda.

As FKs do dicionário do ERP (lógicas) não têm identificador; as do catálogo
(físicas) têm nome. O `enriquecer` casa uma FK física com um relacionamento
lógico (mesma filha, mesma mãe) só quando o conjunto inteiro de campos dela
cabe nele; uma FK que casa só em parte não marca nada. No fim, mostra a
cobertura: pares lógicos cobertos inteiros, em parte e sem constraint, e
FKs físicas aplicadas, casadas só em parte, entre tabelas da base mas
ausentes do dicionário e fora das tabelas da base.

**Ligações do dicionário do sistema.** Quando o dicionário traz uma linha
por ligação (campos em lista), `python3 satelites/york.py enriquecer
--dicionario <pasta>` grava o número de cada ligação nas linhas da base (só
UPDATE; cada linha serve a uma ligação só; ligação que não casa inteira não
marca nada). O `detalhar` usa essa prova abaixo da constraint: constraint e
dicionário em conflito (comparados por conjunto de campos do par) não
valem nenhum dos dois; entre dicionário e chave da mãe, vence o dicionário.

Sem constraint, o `detalhar` ainda prova o agrupamento pela PK da mãe
quando só existe uma forma de montá-lo: campos da mãe exatamente iguais à
PK, sem repetição (`ligação única + chave da mãe`), ou repetições que a PK
separa numa forma só (`chave da mãe`). Medido contra os pares com
constraint declarada (nome escondido): zero erros. O resto fica sem JOIN
pronto, com aviso e o `motivo` de cada linha; nenhum agrupamento é palpite.

A extração do dicionário de um ERP específico (descrições, relacionamentos
lógicos, módulos) não fica aqui: é conteúdo do pacote privado da instância.

---

## Como a skill Vegapunk usa isto

A skill não lê o `.db` diretamente — ela chama a **Stella** (`stella.py`),
que despacha para o motor. Ver `fluxo-schema.md` para o passo a passo
completo. Resumo:

1. `python3 stella.py buscar --dominio schema "<pedido em pt-br>"` → tabelas candidatas (críticas + relacionadas via FK)
2. `python3 stella.py detalhar --dominio schema TAB1 TAB2 ...` → colunas exatas + FKs dessas tabelas
3. Só então o T-SQL é escrito, usando exclusivamente os nomes retornados pelo motor — nunca por memória/suposição.
4. `python3 stella.py confirmar --dominio schema "<pedido>" TABELA [TABELA ...]` fecha o laço de feedback.

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

### Pesos e constantes da fórmula (em `dominios/schema/config.py`)

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

A avaliação do domínio schema é feita pelo **Pythagoras**
(`satelites/pythagoras.py avaliar --dominio schema`; até a fase 1 da v3 era
a `stella.py`). Ela roda pedidos rotulados manualmente (pedido em PT-BR →
tabela(s) esperada(s), em `casos/consultas_fixture.json`) contra o motor e
reporta passou/falhou por caso. Por padrão, **gera uma fixture fictícia
temporária** (`casos/fixture_schema.py`: as 5 tabelas, dados inventados)
para rodar contra — nada é escrito em `egghead/`, e a fixture some ao final
da execução:

```bash
python3 satelites/pythagoras.py avaliar --dominio schema           # fixture fictícia
python3 satelites/pythagoras.py avaliar --dominio schema -v        # ranking completo por caso
python3 satelites/pythagoras.py avaliar --dominio schema --db egghead/punk_records.db   # banco importado
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
- **Calibração** (13 casos): usados para ajustar pesos/constantes da fórmula.
  Passar aqui não é evidência forte — é o mínimo esperado.
- **Held-out** (10 casos): cobrem os mesmos tipos de caso-limite (tabela
  hub, tabela órfã, termo genérico, ordinal por extenso) sem terem sido
  usados para calibrar os pesos atuais.
- **Validação cega** (8 casos): criados por último, sem uso nenhum na
  calibração. É o número mais confiável de "o motor generaliza ou só
  decorou os exemplos".

Misturar os três últimos grupos ao calibrar a fórmula invalida a validação.

**Resultado de referência:** fica em `egghead/linha_de_base_v3.json`, na instância
(fonte única dos números de qualidade; não é repetido aqui). A fixture
inclui um caso dedicado que reproduz o incidente real do
`PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL` — uma tabela de staging
fictícia sem lastro estrutural, mas com colunas ricas, competindo contra
as tabelas reais. O resultado na fixture não é uma garantia para o seu
schema real (maior, com distribuição de termos diferente).
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
5. **Tabelas com pouco lastro estrutural podem PERDER *ou* GANHAR posição
   indevidamente — nas duas direções.** Tabelas com poucas conexões e
   baixo `score_relevancia` podem ficar fora do top-3/5 quando a
   consulta usa também termos genéricos que batem em tabelas maiores
   (sensível ao tamanho e à distribuição estatística do schema
   importado) — mas o oposto também acontece: uma tabela sem NENHUMA
   conexão via FK, se tiver colunas bem descritas, pode GANHAR o 1º
   lugar, porque o eixo semântico (IDF de coluna) entra em escala
   absoluta e não é achatado quando o eixo estrutural é zero. Caso real
   (auditoria de setembro/2026): uma tabela de staging vazia venceu a
   tabela realmente persistida por vocabulário, apesar de zero sinal
   estrutural (nomes de tabela e de fornecedor específicos não são
   repetidos aqui — ver `AVISO.md`, "Marcas e nomes de terceiros").
   Mitigado por `PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL` (só dispara
   quando a tabela não tem NENHUMA conexão via FK — ver comentário da
   constante em `dominios/schema/config.py`), mas o risco de fundo (eixo
   semântico ilimitado vs. eixo estrutural limitado) continua existindo
   em grau menor para tabelas com lastro parcial. **Atualização (v1.4,
   auditoria de privacidade, setembro/2026):** a condição da penalidade
   usava dois sinais (0 FKs *e* 0 registros); o motor deixou de ler
   contagem de linha de tabela nenhuma (dado sensível de volume de
   negócio, removido — ver `calcular_metricas_e_scores`), então por um
   tempo só restou o sinal de FK — uma tabela pequena mas legítima, sem
   nenhuma FK modelada, ficava indistinguível de uma tabela de staging
   vazia. **Atualização (v1.5):** o segundo eixo voltou, mas como
   booleano em vez de contagem — `tabelas.tem_dados` (0/1, "a tabela tem
   alguma linha?", nunca "quantas"). A condição da penalidade é hoje
   `conexoes_totais == 0 AND NOT tem_dados`: só dispara quando a tabela
   não tem NEM FK NEM dado nenhum. Isso restaura a precisão de dois eixos
   sem reintroduzir volume exato de negócio no motor. Enquanto
   `tem_dados` não for reimportado com valor real para uma tabela (fica
   `0` por padrão), o comportamento dela continua igual ao da v1.4.
   Na instância onde o incidente foi observado, aplicar `tem_dados` tirou
   da penalidade cerca de metade das tabelas que só tinham
   `conexoes_totais == 0` (as que tinham dado); as demais seguem
   penalizadas, sem FK e sem dado. As contagens da sua base saem de
   `python3 stella.py status`. Uma tabela nova de um export mais recente do
   schema só entra com um `york.py importar --forcar` completo.
6. **Ambiguidade lexical:** palavras polissêmicas (ex.: "portaria" =
   recepção OU decreto administrativo) podem puxar tabelas erradas — é
   uma limitação inerente de matching léxico, não um bug pontual
   corrigível sem busca semântica (embeddings).
7. **Idioma:** português (BR) apenas.
8. **Amostra de calibração pequena:** os pesos da fórmula foram
   calibrados contra 31 casos rotulados manualmente — suficiente para
   pegar erros grosseiros, mas pequeno para calibração fina por módulo.
9. **Snapshot:** a base Punk Records é uma foto do schema no momento do
   import; se o schema real mudar, rode `importar` de novo.
10. **Penalidades multiplicativas fixas, não calibradas:**
    `PENALIDADE_MODULO_NAO_CADASTRADO` (0.6) e
    `PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL` (0.5) foram escolhidas por
    analogia/julgamento, não por grid search nem pelos casos de
    `casos/consultas_fixture.json` — ao contrário dos demais pesos da fórmula (`estrutura`/
    `conceitos`, `ESCALA_CONCEITOS`, `ALPHA_TERMOS_EXTRA`), que são
    todos calibrados. `pythagoras.py` ainda não recalibra nenhuma das
    duas; use `confirmar` para acumular casos reais e revisite o valor
    quando houver massa suficiente.

---

## Licença e propriedade

O motor **Nomi Nomi no Mi** é deste repositório. Na versão **Vegapunk**
não há base: só o motor e o comando de importação. Na versão **Vegapunk
com Punk Records**, `egghead/punk_records.db` traz só a estrutura de 5
tabelas de metadados (nome de tabela/coluna, descrição de negócio, módulo,
sinônimo — nunca dados de cliente), preenchida localmente por você (ver
["Como importar seus dados"](#como-importar-seus-dados)) a partir de um
ambiente ao qual já tem acesso legítimo. Essa versão é sempre privada:
mantenha `egghead/` **fora do controle de versão** e não a publique.
