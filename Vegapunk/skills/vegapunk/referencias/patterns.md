# Referência de Padrões T-SQL

Templates e padrões detalhados de query para cenários comuns.

## Sumário

- [Paginação](#paginação)
- [Totais Acumulados](#totais-acumulados)
- [Detecção de Lacunas (Gaps)](#detecção-de-lacunas-gaps)
- [Percorrendo Hierarquias (CTE Recursiva)](#percorrendo-hierarquias-cte-recursiva)
- [Deduplicação](#deduplicação)
- [Pivot Dinâmico](#pivot-dinâmico)
- [Estratégias de Indexação](#estratégias-de-indexação)
- [Comando MERGE](#comando-merge)
- [Operadores APPLY](#operadores-apply)
- [Processamento de JSON](#processamento-de-json)
- [Exemplos de Window Functions](#exemplos-de-window-functions)
- [Formatação de saída em pt-BR](#formatação-de-saída-em-pt-br)

## Paginação

```sql
-- Offset-fetch (SQL Server 2012+)
SELECT columns
FROM table
ORDER BY sort_column
OFFSET @PageSize * (@PageNumber - 1) ROWS
FETCH NEXT @PageSize ROWS ONLY;

-- Paginação por keyset (melhor para grandes volumes de dados)
SELECT TOP (@PageSize) columns
FROM table
WHERE sort_column > @LastValue
ORDER BY sort_column;
```

## Totais Acumulados

```sql
SELECT
    column,
    amount,
    SUM(amount) OVER (ORDER BY date_column ROWS UNBOUNDED PRECEDING) AS running_total
FROM table;

-- Exibindo o total formatado no padrão pt-BR (milhar '.', decimal ',')
SELECT
    column,
    FORMAT(amount, 'N2', 'pt-BR') AS amount_fmt,
    FORMAT(SUM(amount) OVER (ORDER BY date_column ROWS UNBOUNDED PRECEDING), 'N2', 'pt-BR') AS running_total_fmt
FROM table;
```

## Detecção de Lacunas (Gaps)

```sql
WITH numbered AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn
    FROM table
)
SELECT
    curr.id + 1 AS gap_start,
    next.id - 1 AS gap_end
FROM numbered curr
JOIN numbered next ON next.rn = curr.rn + 1
WHERE next.id - curr.id > 1;
```

## Percorrendo Hierarquias (CTE Recursiva)

```sql
WITH hierarchy AS (
    -- Âncora (ex.: 'Punk Records' como nó raiz de uma árvore organizacional)
    SELECT id, parent_id, name, 0 AS level
    FROM table
    WHERE parent_id IS NULL

    UNION ALL

    -- Recursivo
    SELECT t.id, t.parent_id, t.name, h.level + 1
    FROM table t
    JOIN hierarchy h ON t.parent_id = h.id
)
SELECT * FROM hierarchy
OPTION (MAXRECURSION 100);
```

## Deduplicação

```sql
WITH ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY duplicate_key_columns
            ORDER BY preference_column DESC
        ) AS rn
    FROM table
)
DELETE FROM ranked WHERE rn > 1;
```

## Pivot Dinâmico

```sql
DECLARE @columns NVARCHAR(MAX), @sql NVARCHAR(MAX);

SELECT @columns = STRING_AGG(QUOTENAME(pivot_value), ', ')
FROM (SELECT DISTINCT pivot_column AS pivot_value FROM source_table) AS vals;

SET @sql = N'
SELECT *
FROM (SELECT row_id, pivot_column, value_column FROM source_table) AS src
PIVOT (SUM(value_column) FOR pivot_column IN (' + @columns + N')) AS pvt';

EXEC sp_executesql @sql;
```

## Estratégias de Indexação

### Índice de Cobertura (Covering Index)

```sql
CREATE NONCLUSTERED INDEX IX_table_column
ON table(filter_column, sort_column)
INCLUDE (selected_column1, selected_column2);
```

### Índice Filtrado

```sql
CREATE NONCLUSTERED INDEX IX_table_active
ON table(date_column)
WHERE status = 'Active';
```

### Diretrizes de Columnstore

- Columnstore clusterizado: cargas analíticas com grandes varreduras
- Columnstore não-clusterizado: híbrido OLTP/analítico
- Evite em tabelas com atualizações frequentes de linha única

## Comando MERGE

```sql
MERGE target_table AS t
USING source_table AS s
ON t.key = s.key
WHEN MATCHED THEN
    UPDATE SET t.column = s.column
WHEN NOT MATCHED BY TARGET THEN
    INSERT (key, column) VALUES (s.key, s.column)
WHEN NOT MATCHED BY SOURCE THEN
    DELETE
OUTPUT $action, inserted.*, deleted.*;
```

## Operadores APPLY

```sql
-- CROSS APPLY (comportamento de inner join)
SELECT o.order_id, top_items.*
FROM orders o
CROSS APPLY (
    SELECT TOP 3 * FROM order_items oi
    WHERE oi.order_id = o.order_id
    ORDER BY oi.amount DESC
) AS top_items;

-- OUTER APPLY (comportamento de left join)
SELECT c.customer_id, latest_order.*
FROM customers c
OUTER APPLY (
    SELECT TOP 1 * FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC
) AS latest_order;
```

## Processamento de JSON

```sql
-- Parsear JSON
SELECT *
FROM OPENJSON(@json)
WITH (
    id INT '$.id',
    name NVARCHAR(100) '$.name',
    tags NVARCHAR(MAX) '$.tags' AS JSON
);

-- Gerar JSON
SELECT id, name
FROM table
FOR JSON PATH, ROOT('items');
```

## Exemplos de Window Functions

```sql
-- Ranking
SELECT *,
    ROW_NUMBER() OVER (PARTITION BY category ORDER BY sales DESC) AS rank_in_category,
    RANK() OVER (ORDER BY sales DESC) AS overall_rank
FROM products;

-- LAG/LEAD para comparações
SELECT
    date,
    value,
    LAG(value) OVER (ORDER BY date) AS prev_value,
    value - LAG(value) OVER (ORDER BY date) AS change
FROM metrics;

-- Cálculos acumulados
SELECT
    date,
    amount,
    SUM(amount) OVER (ORDER BY date ROWS UNBOUNDED PRECEDING) AS cumulative,
    AVG(amount) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS moving_avg_7d
FROM daily_sales;
```

## Formatação de saída em pt-BR

Ao apresentar resultado de qualquer um destes padrões ao usuário, formate
datas e números no padrão brasileiro (ver também `SKILL.md`, seção
"Convenção de formatação pt-BR"):

```sql
-- Data no formato dd/MM/aaaa
SELECT CONVERT(VARCHAR(10), OrderDate, 103) AS OrderDate_ptbr FROM Orders;
-- ou, com FORMAT (mais legível, ligeiramente mais lento)
SELECT FORMAT(OrderDate, 'dd/MM/yyyy') AS OrderDate_ptbr FROM Orders;

-- Número com separador de milhar '.' e decimal ','
SELECT FORMAT(TotalAmount, 'N2', 'pt-BR') AS TotalAmount_ptbr FROM Orders;
-- Resultado: 1.234.567,89 (nunca 1,234,567.89)
```
