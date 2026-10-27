# Fluxo de descoberta de schema (passo a passo)

Carregado sob demanda pelo `SKILL.md`. Vale sempre antes de escrever SQL
contra uma base cadastrada. Comandos rodados da pasta da skill.

Nunca leia `egghead/punk_records.db` diretamente nem escreva nomes de
tabela/coluna de memória: sempre passe pela Stella. Arquitetura do motor,
estrutura da base e limitações: [schema.md](schema.md).

## Passo 0 — Conferir a base (e importar, se for o caso)

```bash
python3 stella.py status
```

Mostra se o domínio schema está instalado, a versão da base e as contagens
atuais. Se aparecer "modo básico — base não instalada", avise o usuário e
aponte para [schema.md](schema.md), seção "Como importar seus dados", em
vez de inventar nomes. A importação (só na primeira vez ou quando o schema
mudar) é do York:

```bash
python3 satelites/york.py importar --dir ./meus_csvs/
```

Tipos, PK e nomes de constraint entram depois, pelo `york.py enriquecer`
(ver [schema.md](schema.md), seção "Estrutura física").

## Passo 1 — Buscar tabelas candidatas

```bash
python3 stella.py buscar --dominio schema "<pedido do usuário, em português>"
```

Retorna tabelas críticas (rankeadas por relevância) e expandidas (vizinhas
via FK, candidatas a JOIN). Se vier vazio ou com poucos resultados, tente
de novo com termos mais genéricos antes de concluir que a tabela não existe.

Leia sempre os avisos no fim da saída:

- **Vizinhos via FK cortados:** nem toda tabela ligada às críticas entrou em
  `expandidas`. Não conclua que duas tabelas não se ligam: rode `detalhar`
  com as duas e veja o caminho.
- **Corte em empate:** a última vaga de crítica caiu num empate de score;
  parte das empatadas ficou de fora só por ordem de nome. Se a tabela certa
  pode estar entre elas, refine o pedido.

### Passo 1.5 — Desconfiar de tabela crítica nº 1 sem conexão nem dado

Antes de aceitar a 1ª colocada sem checar, olhe a linha dela: mostra
`conexoes=` e, quando aplicável, `⚠ SEM LASTRO ESTRUTURAL` (no `--json`:
`conexoes`, `tem_dados` e `sem_lastro_estrutural`). Se a nº 1 tiver
`conexoes=0` e `tem_dados=não`, ela pode ser uma tabela de
staging/temporária vazia que só venceu por ter colunas bem descritas.

1. Olhe a 2ª e a 3ª colocadas: se alguma tiver `conexoes` maior que zero ou
   `tem_dados=sim`, com vocabulário parecido, ela é candidata mais forte.
2. Rode `detalhar` nas 2–3 primeiras e compare. "TEMP"/"STAGING"/"LOG" no
   nome, com poucas ou nenhuma FK, é sinal de alerta.
3. Se restar dúvida, pergunte ao usuário qual é a fonte de dados real.

O motor já aplica `PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL` (despriorização,
não exclusão); o Passo 1.5 é a checagem humana complementar.

## Passo 2 — Detalhar as tabelas escolhidas

```bash
python3 stella.py detalhar --dominio schema TABELA1 TABELA2 ...
```

A saída em texto começa pelo essencial: o caminho entre as tabelas pedidas,
com o JOIN pronto, e os avisos. Depois vêm as colunas de cada tabela. As FKs
para tabelas FORA do pedido saem numa linha só, sem o JOIN (numa tabela
muito ligada elas eram a maior parte da saída); para o JOIN de uma delas,
detalhe as duas juntas ou use `--completo`. O `--json` traz tudo, sempre.

Por tabela:

- **Colunas:** descrição de negócio em português e, quando a base foi
  enriquecida, tipo, tamanho, precisão/escala, nulo e posição na PK.
  A PK da tabela também sai em `metadados.pk`.
- **FKs com agrupamento provado** (`fks`): cada FK, simples ou composta,
  vem com todos os seus campos e com o `JOIN` pronto (`join` e `on`). Use
  esse texto como está. A `origem` diz o que prova o agrupamento:
  `constraint` (FK física com nome), `dicionário` (a ligação do dicionário
  do sistema), `ligação única + chave da mãe` (os campos da mãe são
  exatamente a PK dela, sem repetição) ou `chave da mãe` (a PK da mãe
  permite uma única forma de separar as ligações).
  `confirmado_pelo_dicionario` diz se o dicionário traz a mesma ligação.
  Se `cobre_chave_da_mae` for falso, o JOIN não usa a PK inteira da mãe e
  pode trazer mais de uma linha dela por linha da filha: confirme com o
  usuário antes de somar ou contar.
- **Ligações sem agrupamento provado** (`fks_sem_constraint`): nada prova
  quais campos andam juntos; o `motivo` de cada linha diz por quê
  (`chave_incompleta`: os campos não cobrem a PK inteira da mãe, e o JOIN
  pode multiplicar linhas; `agrupamento_ambiguo`; `mae_sem_pk`;
  `ligacao_simples`; `resto_de_constraint_parcial`;
  `resto_de_ligacao_do_dicionario`; `conflito_constraint_dicionario`: a
  constraint e o dicionário agrupam diferente, e nenhum vale sozinho).
  Monte uma condição `ON` por campo e confirme com o usuário.
- **Caminhos** (`caminhos`, com 2+ tabelas pedidas): o menor caminho de FK
  entre cada par, até 4 saltos, já como `FROM ... INNER JOIN ...`. Se não
  houver caminho, o aviso lista os 10 primeiros pares (a lista completa
  fica em `caminhos`): não invente a ligação, pergunte ao usuário.

`--json` em `buscar`/`detalhar` dá saída parseável.

## Passo 3 — Escrever o T-SQL

Só depois dos passos 1 e 2, usando exclusivamente os nomes retornados. Se
uma coluna necessária não aparecer no `detalhar`, não a invente: avise o
usuário e pergunte como prosseguir.

- **Chave composta:** muitas FKs usam campos compostos (ex.: `CODEMPRESA,CODUNIDADE`).
  Use o `JOIN` pronto do `detalhar`, que já traz todos os campos da FK.
  Sem agrupamento provado, uma condição `ON` por campo, conferida com o
  usuário.
- **Regra de negócio, tela ou processo do sistema de origem:** o motor só
  retorna metadados estruturais, nunca regras de negócio. Para isso,
  consulte a documentação oficial do sistema.
- **Tipo de coluna:** use o tipo que o `detalhar` mostra (literal do tipo
  certo, sem conversão implícita na coluna) e prefira predicados SARGable
  (ver [data-types.md](data-types.md)). Se a coluna veio sem tipo (base não
  enriquecida), infira pelo nome e pela descrição e diga isso ao usuário.
  Para enriquecer a base, ver [schema.md](schema.md), seção "Estrutura
  física".

## Passo 4 — Confirmar as tabelas usadas (sempre, não é opcional)

```bash
python3 stella.py confirmar --dominio schema "<pedido original do usuário>" TABELA_PRINCIPAL [OUTRA ...]
```

Passe todas as tabelas do SQL entregue; a primeira é a principal (é ela que
decide o módulo na calibração). Salvar o relatório no Memory Card
(`stella.py cartao enviar ... --confirmar`) já grava essa confirmação.

Fecha o laço de feedback: sem isso, o histórico de uso real nunca acumula e
a recalibração por módulo nunca sai do zero. Não pergunte ao usuário se ele
quer isso. Se a tabela usada não foi a 1ª colocada (ou se veio
`ambiguidade: true`), a confirmação vale ainda mais.

**Verificação periódica** (a cada nova sessão que usar este fluxo): o
`stella.py status` mostra quantas confirmações há no log. Se o número
cresceu bastante desde a última recalibração (ordem de grandeza: +20–30),
avise o usuário que dá para rodar `satelites/lilith.py gerar` +
`satelites/pythagoras.py calibrar --dominio schema` de novo.

## Recursos automáticos (sem configuração)

- **Correção aproximada (fuzzy):** termo sem match literal tenta uma
  correção por distância de edição contra o vocabulário do schema. Aparece
  em `fuzzy_aplicado` — sempre confira.
- **Ambiguidade:** 1º e 2º colocados com score muito próximo
  (`ambiguidade`): confirme com o usuário antes de escrever o SQL.
- **`checar-modulos`:** roda ao final de todo `importar` e pode ser chamado a
  qualquer momento (`python3 stella.py checar-modulos`). Compara os
  prefixos de tabela do schema com os cadastrados em `sistemas`.
- **Log de uso:** todo `buscar` grava uma linha em
  `egghead/punk_records_log.jsonl`; rotaciona sozinho acima de ~10 MB.

## Manutenção sob demanda

- **`satelites/edison.py sugerir-sinonimos`:** minera candidatos a par
  sinônimo no vocabulário indexado (descarta o padrão particípio × agente).
  Não aplica nada: depois de revisados por humano, grave com
  `satelites/york.py gravar-sinonimos --par A B`.
- **`satelites/lilith.py gerar`:** casos sintéticos (pedido → tabela) a
  partir das descrições do schema. Só dá volume para a calibração; não é
  evidência de qualidade e nunca substitui os casos manuais.
- **`satelites/pythagoras.py calibrar --dominio schema`:** grid search de
  pesos por módulo (casos manuais de calibração + held-out, sintéticos e
  confirmações reais). Só recalibra módulo com 5+ casos; grava
  `egghead/punk_records_pesos.json`, que o motor carrega sozinho.

**Penalidades ativas hoje** (escolhidas por analogia, não calibradas;
revisitar quando houver confirmações reais suficientes):

- `PENALIDADE_MODULO_NAO_CADASTRADO = 0.6`: tabela de módulo fora de
  `sistemas`, nunca excluída, só despriorizada.
- `PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL = 0.5`: `conexoes_totais == 0`
  e `tem_dados` falso. `tem_dados` é um booleano ("a tabela tem alguma
  linha?", nunca "quantas"), vindo do `tabelas.csv` no `importar`.
