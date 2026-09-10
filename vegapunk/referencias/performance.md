# Referência de Tuning de Performance T-SQL

Análise de plano de execução, estratégias de indexação e técnicas de otimização de performance.

## Sumário

- [Lendo Planos de Execução](#lendo-planos-de-execução)
- [Identificando Problemas de Performance](#identificando-problemas-de-performance)
- [Parameter Sniffing](#parameter-sniffing)
- [Análise do Query Store](#análise-do-query-store)
- [Gerenciamento de Estatísticas](#gerenciamento-de-estatísticas)
- [Otimização do Tempdb](#otimização-do-tempdb)
- [Estatísticas de Espera (Wait Statistics)](#estatísticas-de-espera-wait-statistics)

## Lendo Planos de Execução

### Principais Operadores a Observar

| Operador | Nível de Atenção | O que Significa |
|----------|-------------------|------------------|
| Table Scan | Alto (tabelas grandes) | Nenhum índice útil, lê a tabela inteira |
| Clustered Index Scan | Médio | Lê a maioria/todas as linhas via índice clusterizado |
| Index Scan | Médio | Lê a maioria/todas as linhas do índice |
| Key Lookup | Alto (muitas linhas) | Índice não cobre todas as colunas, I/O extra |
| RID Lookup | Alto | Lookup em heap, considere adicionar índice clusterizado |
| Hash Match | Depende do contexto | Joins/agregações grandes, uso intenso de memória |
| Sort | Médio | Ordenação de dados, pode transbordar (spill) para o tempdb |
| Spool (Eager/Lazy) | Médio-Alto | Cacheia resultados intermediários, geralmente indica plano subótimo |

### Sinais de Alerta nos Planos

```
⚠️ Avisos de triângulo amarelo:
- Estatísticas ausentes
- Conversões implícitas
- Nenhum predicado de join (produto cartesiano)
- Avisos de memory grant

⚠️ Setas grossas:
- Estimativas de linha grandes fluindo entre operadores
- Verifique se as estimativas batem com as linhas reais (parameter sniffing?)

⚠️ Custo dos operadores:
- Operadores com percentual alto são alvos de otimização
- Mas o custo é estimado - confirme com estatísticas de execução reais
```

## Identificando Problemas de Performance

### Capturar Estatísticas Reais

```sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

-- Sua query aqui

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
```

Métricas-chave:
- **Logical reads**: páginas lidas do buffer cache (quanto menor, melhor)
- **Physical reads**: páginas lidas do disco (deve ser 0 em execuções repetidas)
- **CPU time**: tempo de processamento
- **Elapsed time**: tempo total decorrido (relógio de parede)

### Encontrar Índices Ausentes

```sql
-- Sugestões de índice ausente a partir das DMVs
SELECT
    CONVERT(DECIMAL(18,2), migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans)) AS improvement_measure,
    'CREATE INDEX [IX_' + OBJECT_NAME(mid.object_id) + '_'
        + REPLACE(REPLACE(REPLACE(ISNULL(mid.equality_columns,''), ', ', '_'), '[', ''), ']', '') + ']'
        + ' ON ' + mid.statement
        + ' (' + ISNULL(mid.equality_columns, '')
        + CASE WHEN mid.equality_columns IS NOT NULL AND mid.inequality_columns IS NOT NULL THEN ', ' ELSE '' END
        + ISNULL(mid.inequality_columns, '') + ')'
        + ISNULL(' INCLUDE (' + mid.included_columns + ')', '') AS create_index_statement
FROM sys.dm_db_missing_index_groups mig
JOIN sys.dm_db_missing_index_group_stats migs ON migs.group_handle = mig.index_group_handle
JOIN sys.dm_db_missing_index_details mid ON mig.index_handle = mid.index_handle
WHERE mid.database_id = DB_ID()
ORDER BY improvement_measure DESC;
```

### Encontrar Índices Não Utilizados

```sql
SELECT
    OBJECT_NAME(i.object_id) AS table_name,
    i.name AS index_name,
    i.type_desc,
    ius.user_seeks,
    ius.user_scans,
    ius.user_lookups,
    ius.user_updates
FROM sys.indexes i
LEFT JOIN sys.dm_db_index_usage_stats ius
    ON i.object_id = ius.object_id AND i.index_id = ius.index_id
WHERE OBJECTPROPERTY(i.object_id, 'IsUserTable') = 1
    AND i.type_desc = 'NONCLUSTERED'
    AND (ius.user_seeks + ius.user_scans + ius.user_lookups) < ius.user_updates
ORDER BY ius.user_updates DESC;
```

## Parameter Sniffing

### Detectando o Problema

```sql
-- Compare linhas estimadas vs reais no plano de execução
-- Discrepância grande = provável parameter sniffing

-- Verifique o cache de planos por múltiplos planos
SELECT
    qs.plan_handle,
    qs.execution_count,
    qs.total_worker_time,
    qs.total_logical_reads,
    SUBSTRING(st.text, (qs.statement_start_offset/2)+1,
        ((CASE qs.statement_end_offset
            WHEN -1 THEN DATALENGTH(st.text)
            ELSE qs.statement_end_offset
        END - qs.statement_start_offset)/2) + 1) AS query_text
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
WHERE st.text LIKE '%your_procedure_name%'
ORDER BY qs.total_logical_reads DESC;
```

### Soluções

```sql
-- Opção 1: RECOMPILE (melhor para distribuições de dados variáveis)
CREATE PROCEDURE GetOrders @Status VARCHAR(20)
AS
BEGIN
    SELECT * FROM Orders WHERE Status = @Status
    OPTION (RECOMPILE);
END

-- Opção 2: OPTIMIZE FOR um valor específico
SELECT * FROM Orders WHERE Status = @Status
OPTION (OPTIMIZE FOR (@Status = 'Pending'));

-- Opção 3: OPTIMIZE FOR UNKNOWN (usa estatísticas médias)
SELECT * FROM Orders WHERE Status = @Status
OPTION (OPTIMIZE FOR UNKNOWN);

-- Opção 4: Variáveis locais (esconde o parâmetro do otimizador)
CREATE PROCEDURE GetOrders @Status VARCHAR(20)
AS
BEGIN
    DECLARE @LocalStatus VARCHAR(20) = @Status;
    SELECT * FROM Orders WHERE Status = @LocalStatus;
END
```

## Análise do Query Store

### Habilitar o Query Store

```sql
ALTER DATABASE YourDatabase
SET QUERY_STORE = ON (
    OPERATION_MODE = READ_WRITE,
    CLEANUP_POLICY = (STALE_QUERY_THRESHOLD_DAYS = 30),
    DATA_FLUSH_INTERVAL_SECONDS = 900,
    MAX_STORAGE_SIZE_MB = 1000,
    INTERVAL_LENGTH_MINUTES = 60
);
```

### Encontrar Queries com Regressão

```sql
-- Queries com regressão de performance
SELECT
    q.query_id,
    qt.query_sql_text,
    rs1.avg_duration AS recent_avg_duration,
    rs2.avg_duration AS historical_avg_duration,
    (rs1.avg_duration - rs2.avg_duration) / rs2.avg_duration * 100 AS pct_regression
FROM sys.query_store_query q
JOIN sys.query_store_query_text qt ON q.query_text_id = qt.query_text_id
JOIN sys.query_store_plan p ON q.query_id = p.query_id
JOIN sys.query_store_runtime_stats rs1 ON p.plan_id = rs1.plan_id
JOIN sys.query_store_runtime_stats rs2 ON p.plan_id = rs2.plan_id
JOIN sys.query_store_runtime_stats_interval rsi1 ON rs1.runtime_stats_interval_id = rsi1.runtime_stats_interval_id
JOIN sys.query_store_runtime_stats_interval rsi2 ON rs2.runtime_stats_interval_id = rsi2.runtime_stats_interval_id
WHERE rsi1.start_time > DATEADD(DAY, -1, GETUTCDATE())  -- Recente
    AND rsi2.start_time < DATEADD(DAY, -7, GETUTCDATE()) -- Histórico
    AND rs1.avg_duration > rs2.avg_duration * 1.5  -- 50% mais lento
ORDER BY pct_regression DESC;
```

### Forçar um Plano Conhecido como Bom

```sql
-- Força um plano específico para uma query
EXEC sp_query_store_force_plan @query_id = 123, @plan_id = 456;

-- Remove o plano forçado
EXEC sp_query_store_unforce_plan @query_id = 123, @plan_id = 456;
```

## Gerenciamento de Estatísticas

### Verificar Atualidade das Estatísticas

```sql
SELECT
    OBJECT_NAME(s.object_id) AS table_name,
    s.name AS stats_name,
    STATS_DATE(s.object_id, s.stats_id) AS last_updated,
    sp.rows,
    sp.rows_sampled,
    sp.modification_counter
FROM sys.stats s
CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1
ORDER BY sp.modification_counter DESC;

-- Exibindo a data da última atualização no padrão dd/MM/aaaa
SELECT
    OBJECT_NAME(s.object_id) AS table_name,
    s.name AS stats_name,
    CONVERT(VARCHAR(10), STATS_DATE(s.object_id, s.stats_id), 103) AS last_updated_ptbr
FROM sys.stats s
WHERE OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1;
```

### Atualizar Estatísticas

```sql
-- Atualiza todas as estatísticas de uma tabela com full scan
UPDATE STATISTICS dbo.YourTable WITH FULLSCAN;

-- Atualiza uma estatística específica
UPDATE STATISTICS dbo.YourTable IX_YourIndex WITH FULLSCAN;

-- Atualiza todas as estatísticas do banco
EXEC sp_updatestats;
```

## Otimização do Tempdb

### Identificar Pressão no Tempdb

```sql
-- Verificar uso dos arquivos de tempdb
SELECT
    name,
    size * 8 / 1024 AS size_mb,
    FILEPROPERTY(name, 'SpaceUsed') * 8 / 1024 AS used_mb
FROM tempdb.sys.database_files;

-- Encontrar sessões usando tempdb
SELECT
    session_id,
    user_objects_alloc_page_count * 8 / 1024 AS user_objects_mb,
    internal_objects_alloc_page_count * 8 / 1024 AS internal_objects_mb
FROM sys.dm_db_session_space_usage
WHERE user_objects_alloc_page_count + internal_objects_alloc_page_count > 0
ORDER BY user_objects_alloc_page_count + internal_objects_alloc_page_count DESC;
```

### Reduzir o Uso do Tempdb

```sql
-- Evite SELECT INTO para grandes volumes de dados, use INSERT INTO em tabela existente
-- Reduza memory grants de sort com índices adequados
-- Use processamento em lote para operações grandes

-- Verifique spills nos planos de execução reais:
-- Sort spills, Hash spills, Exchange spills
```

## Estatísticas de Espera (Wait Statistics)

### Análise das Esperas Atuais

```sql
SELECT TOP 20
    wait_type,
    waiting_tasks_count,
    wait_time_ms,
    max_wait_time_ms,
    signal_wait_time_ms
FROM sys.dm_os_wait_stats
WHERE wait_type NOT IN (
    'CLR_SEMAPHORE', 'LAZYWRITER_SLEEP', 'RESOURCE_QUEUE',
    'SLEEP_TASK', 'SLEEP_SYSTEMTASK', 'SQLTRACE_BUFFER_FLUSH',
    'WAITFOR', 'LOGMGR_QUEUE', 'CHECKPOINT_QUEUE',
    'REQUEST_FOR_DEADLOCK_SEARCH', 'XE_TIMER_EVENT',
    'BROKER_TO_FLUSH', 'BROKER_TASK_STOP', 'CLR_MANUAL_EVENT',
    'DISPATCHER_QUEUE_SEMAPHORE', 'FT_IFTS_SCHEDULER_IDLE_WAIT',
    'XE_DISPATCHER_WAIT', 'XE_DISPATCHER_JOIN'
)
ORDER BY wait_time_ms DESC;
```

### Tipos de Espera Comuns e Soluções

| Tipo de Espera | Causa Típica | Solução |
|-----------------|--------------|---------|
| CXPACKET | Desequilíbrio de paralelismo | Verifique MAXDOP, cost threshold |
| PAGEIOLATCH_* | I/O de disco | Adicione memória, storage mais rápido, melhores índices |
| LCK_M_* | Bloqueio | Otimize queries, reduza o escopo da transação |
| ASYNC_NETWORK_IO | Processamento lento do cliente | Otimização no lado do cliente |
| SOS_SCHEDULER_YIELD | Pressão de CPU | Otimize queries, adicione CPU |
| WRITELOG | I/O do log de transação | Disco de log mais rápido, commits em lote |
