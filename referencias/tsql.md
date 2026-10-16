# T-SQL: instruções gerais, convenções e verificação ao vivo

Carregado sob demanda pelo `SKILL.md` para qualquer trabalho de T-SQL / SQL
Server. Para nomes de tabela e coluna de uma base cadastrada, a fonte da
verdade é sempre o fluxo de descoberta ([fluxo-schema.md](fluxo-schema.md)).

## Instruções gerais

1. **Reúna contexto primeiro**: estrutura de tabelas, relacionamentos,
   volume de dados, versão do SQL Server (para bases cadastradas, isso vem
   do fluxo de descoberta).
2. **Escreva pensando em performance**: evite anti-padrões desde o início
   (ver [performance.md](performance.md)).
3. **Explique o raciocínio**: por que uma técnica foi escolhida, não só como
   funciona.
4. **Apresente alternativas**: quando houver mais de uma abordagem, explique
   os trade-offs.
5. **Trate casos extremos**: NULLs, result sets vazios, condições de borda.
6. **Aponte requisitos de versão**: sinalize recursos que exigem versão
   específica do SQL Server (ver "Verificação ao vivo").

## Convenção de formatação pt-BR (sempre)

Toda saída apresentada ao usuário — resultado de query, texto explicativo
com números ou datas — segue o padrão brasileiro, nunca o en-US:

- **Datas:** `dd/MM/aaaa`, nunca `MM/DD/YYYY` nem `YYYY-MM-DD` ao exibir. No
  T-SQL: `CONVERT(..., 103)` ou `FORMAT(coluna, 'dd/MM/yyyy', 'pt-BR')`.
- **Números:** `.` como separador de milhar e `,` como decimal (ex.:
  `1.234.567,89`). No T-SQL: `FORMAT(coluna, 'N2', 'pt-BR')`.

O motor já segue esta convenção na própria saída.

## Fluxo de trabalho por área

| Área | O que cobre | Referência |
|---|---|---|
| Desenvolvimento de query | queries parametrizadas (`sp_executesql`), tipo de dado batendo com a coluna, predicados SARGable, `TRY...CATCH` com transação tratada, templates (paginação, CTE, PIVOT, MERGE, APPLY, window functions) e o padrão ad-hoc `DECLARE`+`SELECT` para quem só tem acesso de consulta | [patterns.md](patterns.md), [data-types.md](data-types.md) |
| Performance | plano de execução, índices via DMVs, parameter sniffing, Query Store, wait stats | [performance.md](performance.md) |
| Segurança | SQL dinâmico seguro (`sp_executesql`, `QUOTENAME`), row-level security, dynamic data masking, permissões | [security.md](security.md) |
| Transações e concorrência | níveis de isolamento, deadlocks, transações distribuídas, saga | [transactions.md](transactions.md) |

Para bases cadastradas por este motor, a base ainda não guarda o tipo de
coluna: infira pelo nome e pela descrição (ver
[data-types.md](data-types.md)).

## Verificação ao vivo

Não confie só em conhecimento de treinamento para sintaxe exata do T-SQL,
listas de parâmetros ou comportamento específico de versão: use
WebFetch/WebSearch. (Independente do fluxo de descoberta, que é a fonte de
verdade para nomes de tabela/coluna da base cadastrada.)

- **Sempre verificar:** assinatura exata de função, parâmetros, tipo de
  retorno, versão de introdução.
- **Pode pular:** sintaxe fundamental de SQL (SELECT/JOIN/WHERE), padrões
  já cobertos nas referências inclusas.

**Fluxo:** WebFetch na URL bruta do GitHub (padrão abaixo) → se falhar,
WebSearch por `{function-name} T-SQL site:learn.microsoft.com/en-us/sql` e
WebFetch no resultado → se nenhum dos dois esclarecer, declare incerteza e
aponte a URL de referência para o usuário confirmar.

| Fonte | Padrão de URL |
|---|---|
| T-SQL (funções, statements, tipos, elementos de linguagem) | `https://raw.githubusercontent.com/MicrosoftDocs/sql-docs/live/docs/t-sql/{categoria}/{nome}-transact-sql.md` |

Documentação oficial: [SQL Server Docs](https://learn.microsoft.com/en-us/sql/) ·
[T-SQL Reference](https://learn.microsoft.com/en-us/sql/t-sql/language-reference).
