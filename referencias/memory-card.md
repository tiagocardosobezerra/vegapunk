# Memory Card: o cartão de memória dos seus relatórios

Carregado sob demanda pelo `SKILL.md`. Como o memory card de um videogame:
cada relatório T-SQL pronto fica salvo (um "save"), com versão e histórico,
para ser carregado de novo quando precisar.

**A funcionalidade é do motor; o cartão é seu.** O cartão é um repositório
git seu no GitHub, privado por padrão. Qual é o seu cartão fica só na
instância (`egghead/memory_card.json`, fora do git e da distribuição): nada
do seu cartão vem junto com o Vegapunk, e nada dele sai quando o Vegapunk é
distribuído.

## O que é preciso

- O [GitHub CLI](https://cli.github.com/) (`gh`) instalado e autenticado
  (`gh auth login`). O envio usa a sua autenticação: nenhum token fica na skill.
- O `git`.
- Para a conferência no schema: a Punk Records importada
  (`egghead/punk_records.db`). Sem ela, o resto funciona e a conferência
  avisa que não pôde rodar.

## Onde funciona

O cartão é lido e gravado com o `gh` e o `git` na sua máquina. Funciona no
Claude Code (ou num terminal) da máquina onde o cartão foi criado. Numa
sandbox, como a do claude.ai, não há o `gh` autenticado nem a pasta do
cartão. A configuração (`egghead/memory_card.json`) vai junto quando a skill
é copiada, mas lá:

- os comandos recusam dizendo que o cartão é de outra máquina, sem tentar
  clonar nem criar pasta;
- o lembrete de salvar não aparece; no lugar dele, um lembrete diz ao Claude
  para entregar o SQL e o texto do artigo e deixar o envio para o Claude Code;
- o `stella.py status` mostra o cartão como "configurado, mas NÃO funciona
  aqui";
- o `iniciar` recusa numa instância que já tem cartão (só com
  `--substituir`, a pedido do usuário). Sem rede, `catalogo` e `buscar` usam a cópia
local do cartão (com um aviso); o envio sempre precisa da rede.

## Criar o cartão (uma vez)

```bash
python3 stella.py cartao iniciar --repo SEU_USUARIO/memory-card
```

Todo comando do cartão roda pela Stella (`stella.py cartao ...`) ou direto
(`satelites/memory_card.py ...`): é o mesmo programa.

- Se o repositório não existe, ele é criado **privado**. Se já existe, é
  usado (e recusado se estiver público).
- O cartão é clonado em `~/memory-card` (ou em `--pasta DIR`).
- A configuração é gravada em `egghead/memory_card.json`.
- `--publico` cria (ou aceita) um cartão público. Use só se for de
  propósito: um relatório leva nomes de tabela e coluna do seu banco.
- Numa instância que já tem cartão, `iniciar` recusa; `--substituir` troca
  o cartão (só quando você pede).

As variáveis `MEMORY_CARD_REPO` e `MEMORY_CARD_DIR` têm precedência sobre a
configuração.

## Como o cartão é organizado

```
<cartão>/
├── README.md                      o que é o cartão
├── CATALOGO.md                    gerado a cada envio: por solução, categoria e seção, e por tabela
└── saves/
    └── <solucao>/<categoria>/<secao>/<artigo>/
        ├── README.md              o artigo (o GitHub mostra ao abrir a pasta)
        ├── relatorio.sql          o relatório
        └── ficha.json             versão, status, tabelas, colunas, histórico, conferência
```

- **Solução** é a ferramenta que gerou o relatório: `Vegapunk` por padrão,
  ou outra com `--solucao` (um relatório feito à mão, outra ferramenta).
- **Categoria** é a área (ex.: `Recursos Humanos`), **seção** é o assunto
  dentro dela (ex.: `Funcionários`) e **artigo** é o relatório (ex.:
  `Pessoas acima de 75 anos`). Os nomes de exibição ficam na ficha; as
  pastas usam o nome sem acento e com hífen.
- Um artigo é citado por **REF** = `<solucao>/<categoria>/<secao>/<artigo>`, com
  os nomes das pastas (ex.: `vegapunk/recursos-humanos/funcionarios/pessoas-acima-de-75-anos`).
- **Status**: `rascunho` (padrão) ou `em-uso` (roda em produção).

### O artigo

O `README.md` de cada save é montado assim:

1. Título, solução, categoria, seção, versão e status.
2. A descrição de uma linha.
3. O texto do artigo, que você (ou o Claude) escreve, com as seções:
   `O que faz`, `Quando usar`, `Como funciona` (tabelas, joins com a prova e
   filtros), `Colunas de saída`, `Parâmetros`, `Regras de negócio` e
   `Limitações`.
4. O relatório: link para o `relatorio.sql`, tabelas usadas e a última
   conferência no schema.
5. Relacionados: links para os artigos ligados.
6. Histórico: versão, data e motivo de cada mudança.

As partes 1, 2, 4, 5 e 6 são geradas pela ferramenta. Só a parte 3 é
escrita à mão, e fica entre os marcadores `<!-- corpo -->` e
`<!-- /corpo -->`, que não devem ser apagados.

## Comandos

Todos rodam da pasta da skill. Os que gravam mostram uma **prévia** primeiro
e só gravam com `--confirmar`.

| Comando | O que faz |
|---|---|
| `iniciar --repo DONO/NOME [--pasta DIR] [--publico]` | cria ou liga o cartão e grava a configuração |
| `catalogo [--json]` | mostra o catálogo |
| `buscar TERMO [TERMO ...] [--limite N]` | procura nos saves com a normalização do `buscar` do schema (sem acento, sem caixa, sem stop words, plural e os sinônimos de busca da Punk Records). Título e descrição pesam mais, depois solução, categoria, seção e tabelas, depois o texto do artigo e o SQL. Só aparece o save que cobre pelo menos metade dos termos do pedido |
| `enviar ARQ.sql --categoria C --secao S --artigo A [...]` | salva um relatório novo ou uma versão nova (detalhe abaixo) |
| `marcar REF --status em-uso\|rascunho` | muda o status, sem mudar a versão |
| `conferir [REF ...] [--registrar]` | confere tabelas, colunas e JOINs de cada relatório na Punk Records atual |
| `migrar [--solucao SOL] [--confirmar]` | move os saves de um cartão antigo (sem o nível da solução) para `saves/<solucao>/...`, com as ligações entre artigos |

### Salvar um relatório novo

```bash
python3 stella.py cartao enviar relatorio.sql \
    --categoria "Recursos Humanos" --secao "Funcionários" --artigo "Pessoas acima de 75 anos" \
    --descricao "Funcionários com mais de 75 anos, com a idade calculada" \
    --texto artigo.md --pedido "pessoas com idade acima de 75 anos"
```

- `--texto` é obrigatório num artigo novo: é o corpo do artigo (parte 3).
- `--relacionado REF` (pode repetir) liga o artigo a outro. A ligação vale
  nos dois sentidos: o outro artigo ganha o link de volta.
- `--status em-uso` já salva como em uso.
- `--solucao` muda a solução (padrão: `Vegapunk`).
- A prévia mostra o destino, a versão, a conferência no schema, os avisos,
  a ficha e o artigo inteiro. Repita com `--confirmar` para enviar.
- Um relatório que cita tabela ou coluna que não existe na base é recusado
  no `--confirmar`. Corrija o SQL; se o nome existe no banco real e só falta
  na Punk Records (uma view ainda não extraída, por exemplo), repita com
  `--mesmo-assim`.
- **Salvar também confirma.** Depois do envio, as tabelas do relatório que
  existem na base vão para o log de uso, como no `stella.py confirmar
  --dominio schema` (a principal é a primeira do SQL). O pedido registrado
  é o `--pedido` ou, sem ele, a descrição. É o que alimenta a calibração.

### Mudar um relatório (versão nova)

Use o mesmo `enviar`, com a mesma solução, categoria, seção e artigo, e diga o motivo:

```bash
python3 stella.py cartao enviar relatorio.sql \
    --categoria "Recursos Humanos" --secao "Funcionários" --artigo "Pessoas acima de 75 anos" \
    --motivo "inclui a data de admissão"
```

- `--motivo` é obrigatório: entra no histórico do artigo e na mensagem do commit.
- A versão sobe (1, 2, 3...). A data de criação é mantida.
- Sem `--texto`, o corpo do artigo é mantido; sem `--descricao`, também.
- A prévia mostra o **diff** do SQL e do artigo. Confira antes de confirmar.
- O histórico completo também fica no git do cartão.

### Conferir no schema

```bash
python3 stella.py cartao conferir
```

Rode depois de atualizar a Punk Records (por exemplo, numa versão nova do
seu sistema). O conferidor é o mesmo do `stella.py solucionar`
(`nomi_nomi_no_mi/montagem.py`): para cada save, ele lê as tabelas de
`FROM`/`JOIN` e as colunas qualificadas (`TABELA.COLUNA` ou
`APELIDO.COLUNA`) e diz o que não existe mais. CTE, tabela temporária e
subconsulta não são da base e não são conferidas. Cada JOIN entre tabelas
da base é comparado com as ligações provadas (constraint ou dicionário): um
JOIN por colunas sem prova, ou só por parte de uma chave composta (o que
multiplica linhas), sai como aviso. Não grava no log de uso. Com
`--registrar`, guarda o resultado nas fichas e marca no catálogo os saves
com algo faltando ("conferir: schema mudou").

A mesma conferência roda em toda prévia de `enviar`.

Limite: colunas sem prefixo de tabela ou apelido não são conferidas, e um
JOIN com uma CTE ou subconsulta sai como "ligação não conferida".

## Cartão antigo (sem o nível da solução)

Um cartão criado antes do nível da solução tem os saves em
`saves/<categoria>/<secao>/<artigo>/`. Ele continua sendo lido, e um envio
novo já vai para `saves/vegapunk/...`. Para mover os antigos:

```bash
python3 stella.py cartao migrar              # prévia: de onde para onde
python3 stella.py cartao migrar --confirmar  # move, refaz as ligações e envia
```

## Proteções

- **Privado por padrão.** Antes e depois de cada commit, a visibilidade do
  cartão é conferida no GitHub; se não for privado (e o cartão não foi criado
  com `--publico`), o envio é recusado.
- **Só `.sql`.** Nada de base, CSV, log ou pacote privado.
- **Avisos na prévia** quando o SQL tem literal com cara de CPF ou de e-mail,
  ou um `USE` com nome de banco.
- **Nada do cartão na distribuição.** A configuração fica em `egghead/`,
  que nunca sai. Para garantir também que o nome do seu repositório não
  apareça em nenhum arquivo público, ponha-o na chave `palavras` de
  `egghead/termos_proibidos.json` (ex.: `["seu-usuario/memory-card"]`): a
  checagem de nomes do isolamento e a distribuição recusam qualquer arquivo
  que o cite, em qualquer caixa e com qualquer separador.
- **Nada solto na skill.** Um relatório salvo no cartão não precisa ficar na
  pasta da skill. Um `.sql` solto lá entra na superfície distribuível, e a
  checagem de nomes reprova se ele citar o schema real.

## Como o Claude usa

O `stella.py status` mostra o cartão: quantos saves e quantos com algo
faltando no schema (só a cópia local, sem rede).

Com um cartão configurado, os comandos da Stella e do York lembram o Claude
do próximo passo, com uma linha `LEMBRETE:` em stderr: o `buscar` do schema
lembra de procurar no cartão, o `confirmar` e o `solucionar` com SQL lembram
de oferecer salvar, e o `importar`, o `enriquecer` e o `atualizar --aplicar`
do York lembram de rodar o `conferir`.

- **Antes de escrever um relatório novo**, procura no cartão (`buscar`). Se
  algo servir, oferece reaproveitar ou fazer uma variação. É a escada: a
  menor solução que resolve.
- **Quando um relatório fica pronto e aprovado**, oferece salvar. Mostra a
  prévia e só envia com o seu "sim".
- **Numa mudança**, pede o motivo e mostra o diff antes do "sim".
