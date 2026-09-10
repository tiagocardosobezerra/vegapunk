---
name: vegapunk
description: 'Especialista em T-SQL para Microsoft SQL Server, com um motor de descoberta de schema por linguagem natural plugável em qualquer base de metadados (ver contextos/README.md) — schema de dados vem VAZIO por padrão (você importa o seu com o comando `importar`, ver contextos/README.md), pensado para bases com tabelas nomeadas por código interno em vez de nomes descritivos (ex.: `R034FUN`, não `FUNCIONARIOS`). Use sempre que o pedido envolver descoberta de schema por nome de domínio de negócio (funcionários, folha de pagamento, ponto eletrônico, cadastros gerais), e também para qualquer trabalho geral de T-SQL/SQL Server: escrever, otimizar ou depurar queries, CTEs, window functions, PIVOT/MERGE/APPLY, análise de plano de execução, indexação, stored procedures, ou arquivos .sql. Para consultas contra uma base de metadados própria (importada localmente, ver contextos/README.md), use esta skill para descobrir as tabelas/colunas reais antes de escrever SQL — nunca adivinhe nomes de tabela ou coluna de memória.'
---

# Vegapunk

> ⚠️ Se você já tem, no mesmo ambiente, outra skill/plugin chamado
> `vegapunk` apontando para um schema real de terceiros (sistema licenciado,
> já com dados importados), **não instale este pacote por cima dela**.
> Este é o motor genérico e público: base vazia, nenhum conhecimento de
> sistema real embutido. Mantenha os dois em nomes/pastas distintos se
> ambos precisarem coexistir no seu ambiente.

Especialista em Microsoft SQL Server / T-SQL. Quando o trabalho envolve
descoberta de schema por domínio de negócio, a skill consulta o motor
**Nomi Nomi no Mi** contra uma base de metadados (**Punk Records**) antes
de escrever qualquer SQL, em vez de depender de conhecimento genérico ou
"chutar" nomenclatura de um sistema proprietário. Para T-SQL genérico e para
qualquer coisa que mude com a versão do SQL Server, a skill busca a
documentação ao vivo em vez de confiar em conhecimento de treinamento —
ver "Verificação ao vivo" abaixo.

**Sobre a base incluída:** o `contextos/punk_records.db` publicado neste
repositório vem **vazio** — só as 5 tabelas de metadados
(`tabelas`/`colunas`/`relacionamentos`/`sistemas`/`sinonimos`), sem
nenhuma linha. Importe os metadados do seu próprio schema com o comando
`importar` antes de usar (nunca publique um schema de terceiros depois
de importado). Ver [contextos/README.md](contextos/README.md), seção
"Como importar seus dados".

## Sumário

- [Quando usar o fluxo de descoberta de schema](#quando-usar-o-fluxo-de-descoberta-de-schema)
- [Fluxo de Descoberta de Schema](#fluxo-de-descoberta-de-schema--sempre-antes-de-escrever-sql-contra-uma-base-cadastrada)
- [Instruções gerais (T-SQL)](#instruções-gerais-t-sql)
- [Convenção de formatação pt-BR (sempre)](#convenção-de-formatação-pt-br-sempre)
- [Fluxo de Trabalho](#fluxo-de-trabalho)
- [Verificação ao vivo](#verificação-ao-vivo)
- [Estrutura da skill](#estrutura-da-skill)
- [Referências](#referências)

## Quando usar o fluxo de descoberta de schema

Rode o fluxo de descoberta (abaixo) sempre que o pedido:
- mencionar um sistema com tabelas nomeadas por código interno em vez de nomes descritivos (ex.: `R034FUN`, não `FUNCIONARIOS`);
- pedir dados de domínios típicos de RH/folha de pagamento: funcionários, folha de pagamento, ponto eletrônico, cadastros gerais (empresa/unidade), usuários do sistema, recrutamento;
- pedir para "escrever uma consulta" contra uma base cadastrada mesmo sem citar tabelas específicas.

Se o pedido for T-SQL genérico sem qualquer relação com descoberta de schema, pule direto para [Fluxo de Trabalho](#fluxo-de-trabalho).

Se `contextos/punk_records.db` ainda estiver vazio (nenhum import foi
feito), avise o usuário e aponte para
[contextos/README.md](contextos/README.md), seção "Como importar seus
dados", em vez de inventar nomes de tabela/coluna.

---

## Fluxo de Descoberta de Schema — SEMPRE antes de escrever SQL contra uma base cadastrada

Nunca leia `contextos/punk_records.db` diretamente nem escreva nomes de
tabela/coluna de memória — sempre passe pelo motor
`scripts/nomi_nomi_no_mi.py`. Detalhes de arquitetura, estrutura da base e
limitações do motor estão em [contextos/README.md](contextos/README.md).

### Passo 0 — Importar (só na primeira vez / quando o schema mudar)

```bash
python3 scripts/nomi_nomi_no_mi.py importar --dir ./meus_csvs/
```

Lê `tabelas.csv`/`colunas.csv`/`relacionamentos.csv`/`sistemas.csv`/`sinonimos.csv`
e (re)gera `contextos/punk_records.db`, calculando os campos derivados
automaticamente. Formato exato dos CSVs em
[contextos/README.md](contextos/README.md), seção "Formato dos CSVs de import".

### Passo 1 — Buscar tabelas candidatas

```bash
python3 scripts/nomi_nomi_no_mi.py buscar "<pedido do usuário, em português>"
```

Retorna tabelas críticas (rankeadas por relevância) e expandidas (vizinhas via FK, candidatas a JOIN). Se vier vazio ou com poucos resultados, tente de novo com termos mais genéricos antes de concluir que a tabela não existe.

### Passo 2 — Detalhar as tabelas escolhidas

```bash
python3 scripts/nomi_nomi_no_mi.py detalhar R034FUN <TABELA2> <TABELA3> ...
```

Retorna, por tabela, todas as colunas (com descrição de negócio em português) e todas as FKs, já formatadas como `TABELA_FILHA(campo) -> TABELA_MAE(campo)`, prontas para virar `JOIN ... ON`.

Use `--json` em qualquer um dos comandos `buscar`/`detalhar` para saída parseável.

### Passo 3 — Escrever o T-SQL

Só depois dos passos 1 e 2, escreva a query, usando exclusivamente os nomes retornados pelo motor. Se uma coluna necessária não aparecer no `detalhar`, não a invente — avise o usuário e pergunte como prosseguir.

**Nomenclatura de sistemas com tabelas em código:** muitas FKs usam campos compostos (ex: `CODFILIAL,CODFUNC`) — trate como chave composta no JOIN, uma condição `ON` por campo.

**Regra de negócio, tela ou processo do sistema de origem:** o motor só retorna metadados estruturais (tabela/coluna/FK), nunca regras de negócio — para isso, consulte a documentação oficial do seu próprio sistema.

---

## Instruções gerais (T-SQL)

1. **Reúna contexto primeiro** — estrutura de tabelas, relacionamentos, volume de dados, versão do SQL Server (para bases cadastradas, isso vem do fluxo de descoberta acima).
2. **Escreva pensando em performance** — evite anti-padrões desde o início (ver [referencias/performance.md](referencias/performance.md)).
3. **Explique o raciocínio** — por que uma técnica foi escolhida, não só como funciona.
4. **Apresente alternativas** — quando houver mais de uma abordagem, explique os trade-offs.
5. **Trate casos extremos** — NULLs, result sets vazios, condições de borda.
6. **Aponte requisitos de versão** — sinalize recursos que exigem versão específica do SQL Server (ver [Verificação ao vivo](#verificação-ao-vivo)).

## Convenção de formatação pt-BR (sempre)

Toda saída apresentada ao usuário — resultado de query, texto explicativo com números ou datas — segue o padrão brasileiro, nunca o en-US:

- **Datas:** `dd/MM/aaaa`, nunca `MM/DD/YYYY` nem `YYYY-MM-DD` ao exibir. No T-SQL: `CONVERT(..., 103)` ou `FORMAT(coluna, 'dd/MM/yyyy', 'pt-BR')`.
- **Números:** `.` como separador de milhar e `,` como decimal (ex.: `1.234.567,89`). No T-SQL: `FORMAT(coluna, 'N2', 'pt-BR')`.

Vale para qualquer SQL executado ou explicado na conversa. O motor Nomi Nomi no Mi já segue esta convenção em sua própria saída.

## Fluxo de Trabalho

Cada área abaixo tem uma referência dedicada — consulte-a em vez de reconstruir o padrão de memória.

### 1. Desenvolvimento de Query

Queries parametrizadas (`sp_executesql`), tipos de dado batendo com a coluna (ver [referencias/data-types.md](referencias/data-types.md) — para bases cadastradas via este motor, infira o tipo pelo nome/descrição, já que o `detalhar` não traz tipo de coluna), predicados SARGable, `TRY...CATCH` com transação tratada.

Veja [referencias/patterns.md](referencias/patterns.md) para templates de query (paginação, CTEs, PIVOT, MERGE, APPLY, window functions).

### 2. Otimização de Performance

Análise de plano de execução, recomendação de índices via DMVs, parameter sniffing, Query Store.

Veja [referencias/performance.md](referencias/performance.md).

### 3. Segurança

SQL dinâmico seguro com `sp_executesql`, `QUOTENAME`, row-level security, dynamic data masking.

Veja [referencias/security.md](referencias/security.md).

### 4. Transações e Concorrência

Níveis de isolamento, prevenção de deadlock, transações distribuídas, padrão saga.

Veja [referencias/transactions.md](referencias/transactions.md).

## Verificação ao vivo

Não confie só em dados de treinamento para sintaxe exata do T-SQL, listas de parâmetros ou comportamento específico de versão — use WebFetch/WebSearch. (Independente do fluxo de descoberta de schema, que é a fonte de verdade para nomes de tabela/coluna da base cadastrada.)

**Sempre verificar:** assinatura exata de função, parâmetros, tipo de retorno, versão de introdução.
**Pode pular:** sintaxe fundamental de SQL (SELECT/JOIN/WHERE), padrões já cobertos nas referências inclusas.

**Fluxo:** WebFetch na URL bruta do GitHub (padrão abaixo) → se falhar, WebSearch por `{function-name} T-SQL site:learn.microsoft.com/en-us/sql` e WebFetch no resultado → se nenhum dos dois esclarecer, declare incerteza e aponte a URL de referência para o usuário confirmar.

| Fonte | Padrão de URL |
|---|---|
| T-SQL (funções, statements, tipos, elementos de linguagem) | `https://raw.githubusercontent.com/MicrosoftDocs/sql-docs/live/docs/t-sql/{categoria}/{nome}-transact-sql.md` |

## Estrutura da skill

```
vegapunk/
├── SKILL.md
├── scripts/
│   ├── nomi_nomi_no_mi.py        # motor de descoberta de schema, agnóstico de domínio
│   └── stella.py                 # suite de regressão (gera fixture fictícia própria — ver contextos/README.md)
├── contextos/
│   ├── punk_records.db           # schema VAZIO (5 tabelas, 0 linhas) — importe seus dados
│   └── README.md                 # arquitetura do motor, histórico de versões, limitações, formato de import
└── referencias/
    ├── patterns.md
    ├── performance.md
    ├── security.md
    ├── data-types.md
    └── transactions.md
```

## Referências

- **[contextos/README.md](contextos/README.md)** — como o motor Nomi Nomi no Mi funciona, estrutura da base Punk Records, limitações, como importar seus dados
- **[referencias/patterns.md](referencias/patterns.md)** — CTEs, paginação, PIVOT, MERGE, window functions, APPLY
- **[referencias/performance.md](referencias/performance.md)** — plano de execução, parameter sniffing, Query Store, wait stats
- **[referencias/security.md](referencias/security.md)** — prevenção de SQL injection, SQL dinâmico seguro, permissões, masking
- **[referencias/data-types.md](referencias/data-types.md)** — seleção de tipo, collation, precisão/escala, storage
- **[referencias/transactions.md](referencias/transactions.md)** — níveis de isolamento, deadlocks, transações distribuídas, sagas
- **[SQL Server Docs](https://learn.microsoft.com/en-us/sql/)** / **[T-SQL Reference](https://learn.microsoft.com/en-us/sql/t-sql/language-reference)**
