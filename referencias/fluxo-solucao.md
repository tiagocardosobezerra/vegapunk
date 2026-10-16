# Fluxo de solução: pedido com várias intenções

Use este fluxo quando o pedido tem mais de um ingrediente: uma conta, um
código de cadastro, uma tabela, uma consulta. A Stella devolve a solução
agrupada por intenção, valida a fórmula e aponta cada lacuna. Os exemplos
abaixo são fictícios.

## Passo 0: qual caminho?

Alguns pedidos admitem dois caminhos. "Listar os funcionários de uma unidade
e somar um valor" pode ser:

- **um relatório só**: o SQL lista e soma; roda no gerador de relatórios ou
  como consulta SQL cadastrada;
- **um cálculo no sistema**: uma fórmula cadastrada que roda no cálculo,
  por funcionário, com o SQL só para conferir ou listar.

Pergunte ao usuário qual dos dois ele quer ANTES de montar as intenções. Se
for relatório e o valor vier de uma tabela de movimento que o mapa não
prova, ela entra como intenção de schema normal (com JOIN provado) ou sai
como lacuna; nunca como palpite.

## Passo 1: quebrar o pedido em intenções

Quem quebra o pedido é você (o Claude), não o código. Uma intenção é um
ingrediente que se busca sozinho:

| `dominio` | quando | campos extras |
|---|---|---|
| `formulas` | uma função do dicionário faz a conta ou a ação | `essencial` (só para capacidade, ver abaixo) |
| `schema` | o pedido precisa de uma tabela da base | `filtrar` (nome do argumento, quando o usuário escolhe uma linha: "de uma seção") |
| `cadastro` | um argumento de função é o código de um cadastro | `funcao` e, se a função tem mais de um código, `posicao` |

Escreva o `texto` da intenção com as palavras do pedido, nunca com o nome de
uma função ou tabela.

**`essencial`, só para capacidade que pode não existir:** efeito externo
(enviar e-mail), formato especial (por extenso), ação sobre registro (excluir
registro), consulta (executar consulta). Conta comum (limitar, somar,
comparar, arredondar, média, idade) não leva `essencial`. Com o `essencial`,
só entra função cuja documentação contém o termo; sem nenhuma, a intenção
sai como lacuna "nenhuma função documentada faz ...". Nunca troque o termo
para forçar um acerto.

## Passo 2: chamar a Stella

```bash
python3 stella.py solucionar --intencoes contrato.json
```

```json
{"pedido": "salário base do cargo, arredondado em duas casas",
 "contexto": "BASE",
 "intencoes": [
   {"id": "1", "texto": "salário base do cargo", "dominio": "formulas"},
   {"id": "2", "texto": "código do cargo", "dominio": "cadastro", "funcao": "CARGODE"},
   {"id": "3", "texto": "arredondar um número", "dominio": "formulas"}]}
```

A saída tem uma entrada por intenção, na ordem do contrato: os candidatos
(função com sintaxe e ligação do parâmetro de código; tabela com a prova;
cadastro com tabela, coluna, chave e SQL de apoio) ou a `LACUNA` com o
motivo. Nenhuma intenção some. No schema, quando a intenção nomeia um
cadastro do mapa, a tabela do mapa vem primeiro (`prova: mapa`).

**Padrões antes de funções.** O pedido inteiro é olhado como um padrão:
- uma função que aparece junto com o 1º candidato de outra intenção em
  exemplos da documentação (pelo menos 2 exemplos distintos) sobe para o
  topo da sua intenção quando o 1º candidato dela não aparece junto de
  nenhum ("subiu pelo padrão do pedido", com a prova);
- receitas documentadas que cobrem duas ou mais intenções saem como
  "Padrão documentado", com a fórmula da documentação: use como modelo;
- quando o padrão lê campos de uma consulta, as tabelas que têm todos esses
  campos sobem na intenção de schema que cita um deles (`prova: padrao`).

## Passo 3: montar e validar a fórmula

Monte a fórmula só com o que a Stella devolveu e mande de volta no mesmo
contrato, em `"formula"` (texto) ou `"plano"` (o plano do `compor`). O
argumento que só o usuário conhece (o código no banco dele) vai MARCADO:

```json
"formula": "ARREDONDE(CARGODE(<<CÓDIGO DO CARGO>>), 2)"
```

No plano, o nó é `{"marcador": "CÓDIGO DO CARGO"}`. Regras:

- fórmula marcada nunca sai pronta para cadastrar: a saída diz "NÃO está
  pronta para cadastrar" e lista cada argumento a preencher, com o cadastro,
  a coluna e o SQL de apoio quando o mapa liga o parâmetro;
- nunca preencha o código de memória nem invente um valor: o usuário roda
  o SQL de apoio no banco dele e preenche;
- se a marca `<< >>` colide com a sintaxe do dialeto, a fórmula marcada é
  recusada (`marcador_colide`);
- fórmula com erro de validação não é entregue.

## Passo 3a: a escada (nível 1, 2 ou 3)

A solução sai com o `nivel`: 1 = só funções; 2 = funções com código de
cadastro; 3 = fórmula que executa uma consulta cadastrada. Sempre a menor
que resolve: numa intenção que uma função resolve, as funções de consulta
saem da lista. No nível 3 a Stella entrega, nesta ordem:

1. **reaproveitar**: o SQL de apoio do cadastro de consultas, para o usuário
   procurar uma consulta já cadastrada, sem parâmetro, que devolva os campos;
2. a capacidade do dialeto: a consulta não recebe parâmetro na chamada; o
   filtro vai no próprio SQL ou na comparação dentro do laço;
3. se nenhuma servir, a **consulta nova**: o SQL escrito pela descoberta (só
   JOIN provado), o modelo do laço documentado (executar, ler dentro do laço,
   avançar na condição de saída), validado contra o SELECT, e a instrução de
   cadastro manual. O motor nunca grava no sistema de origem.
   Se a tabela da consulta nova veio só do ranking da busca (sem prova do mapa
   nem da documentação), ela sai marcada "escolhida pela busca, sem prova",
   com as alternativas (o resto do top-3 e as candidatas com prova) e a
   consulta nova sai "NÃO está pronta: confirme a tabela antes de cadastrar a
   consulta". Pergunte ao usuário qual tabela guarda o dado antes de entregar.

O Shaka confere toda fórmula que executa consulta: a leitura e o avanço
exigem a execução da MESMA consulta antes (erro); avanço fora da saída do
laço e leitura fora do laço são avisos; campo fora do SELECT de uma consulta
nova é erro; numa consulta já cadastrada, os campos lidos saem como aviso
para conferir (nunca como pergunta).

**Capacidade que não existe.** Se a intenção pede uma capacidade que o
dialeto declara como inexistente (ex.: passar parâmetro à consulta), ponha
`"capacidade": "parametros_na_chamada"` na intenção: ela sai como lacuna,
com a evidência.

## Passo 3b: o SQL

Com intenções de schema, a Stella **monta** o SQL: a 1ª tabela de cada
intenção, ligadas só por JOIN provado (constraint do catálogo ou ligação do
dicionário); a saída diz a origem de cada JOIN. Sem caminho provado entre
duas tabelas, sai LACUNA, nunca um JOIN palpitado. Com `filtrar`, o WHERE
sai marcado na chave completa da tabela, com o SQL de apoio:

```sql
SELECT F_FUNCIONARIO.MATRICULA, F_CARGO.CODCARGO, F_CARGO.DESCRICAOCARGO
FROM F_FUNCIONARIO
INNER JOIN F_CARGO ON F_FUNCIONARIO.CODCARGO = F_CARGO.CODCARGO
WHERE F_CARGO.CODCARGO = <<CÓDIGO DO CARGO>>
```

O SELECT traz só as chaves e a descrição dos cadastros: acrescente as
colunas que o usuário pediu, com `detalhar`. Se você mesmo escrever o SQL,
mande-o em `"sql"` no contrato: a Stella confere cada tabela e coluna
(nome que não existe é erro, e o SQL não é entregue) e cada JOIN contra as
ligações provadas (JOIN por colunas sem prova, ou só com parte delas, é
aviso). SQL com marca nunca sai pronto para rodar. O motor nunca executa
SQL.

## Passo 4: entregar ao usuário

Fale em linguagem simples, nesta ordem:

1. **o que a solução faz**, em uma frase;
2. **a fórmula e/ou o SQL, e onde cada um é usado**: o SQL roda como
   relatório ou consulta (gerador de relatórios, consulta SQL cadastrada); a
   fórmula é cadastrada no sistema e roda no cálculo (por funcionário). Se
   as peças não se encaixam num uso só, diga isso;
3. **o que o usuário precisa preencher**: cada argumento marcado, com o SQL
   de apoio para achar o valor no banco dele e a chave completa em palavras
   ("o código do evento só é único junto com a coligada: pegue os dois da
   mesma linha");
4. **as lacunas**, com o motivo ("não há função documentada que envie
   e-mail");
5. **só os avisos que pedem ação do usuário** (escolher entre dois sentidos,
   conferir um JOIN que pode multiplicar linhas).

Os candidatos alternativos e os avisos técnicos ficam com você: só mostre
se o usuário perguntar, ou se houver uma ambiguidade que ele precise
decidir.

Cada solução fica registrada como candidata a confirmação
(`solucoes_candidatas.jsonl`, na instância), como foi entregue: com os
argumentos marcados, nunca com os valores. `--sem-registro` desliga o
registro.

## Passo 5: o aceite

No fim, pergunte se o usuário aceita a solução. Só com o "sim" explícito
dele, rode `stella.py aceitar ID` (o ID sai no fim do `solucionar`). A
solução aceita é guardada como foi entregue, com os argumentos marcados
(nunca com os valores que ele preencheu), vira caso de validação
(`casos_solucao_aceitos.json`) e exemplo limpo para o grafo de funções
(`solucoes_aceitas.jsonl`), os dois na instância. Só fórmula validada pelo
Shaka pode ser aceita. Confirme também as funções usadas:
`stella.py confirmar --dominio formulas "<pedido>" F1 F2 ...`.
