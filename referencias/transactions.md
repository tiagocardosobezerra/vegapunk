# Referência de Transações T-SQL

Níveis de isolamento, prevenção de deadlock e padrões de transação distribuída.

## Sumário

- [Fundamentos de Transação](#fundamentos-de-transação)
- [Níveis de Isolamento](#níveis-de-isolamento)
- [Prevenção de Deadlock](#prevenção-de-deadlock)
- [Tipos de Lock e Hints](#tipos-de-lock-e-hints)
- [Transações Distribuídas](#transações-distribuídas)
- [Boas Práticas de Transação](#boas-práticas-de-transação)

## Fundamentos de Transação

### Estrutura Básica de Transação

```sql
BEGIN TRY
    BEGIN TRANSACTION;

    -- Operações aqui
    UPDATE Accounts SET Balance = Balance - 100 WHERE AccountId = 1;
    UPDATE Accounts SET Balance = Balance + 100 WHERE AccountId = 2;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    -- Trate ou relance o erro
    THROW;
END CATCH;
```

### Transações Nomeadas e Savepoints

```sql
BEGIN TRANSACTION MainTran;

    -- Primeira operação
    INSERT INTO Orders (CustomerId, OrderDate) VALUES (1, GETDATE());
    DECLARE @OrderId INT = SCOPE_IDENTITY();

    SAVE TRANSACTION BeforeItems;

    BEGIN TRY
        -- Pode falhar de forma independente
        INSERT INTO OrderItems (OrderId, ProductId, Quantity) VALUES (@OrderId, 1, 5);
        INSERT INTO OrderItems (OrderId, ProductId, Quantity) VALUES (@OrderId, 2, 3);
    END TRY
    BEGIN CATCH
        -- Desfaz apenas os itens, mantém o pedido
        ROLLBACK TRANSACTION BeforeItems;
        -- Registra o problema mas continua
    END CATCH;

COMMIT TRANSACTION MainTran;
```

### Verificação de Estado da Transação

```sql
-- Verifica se está em uma transação
SELECT @@TRANCOUNT;  -- 0 = sem transação, > 0 = em transação

-- Verifica o estado da transação
SELECT XACT_STATE();
-- 1 = ativa, pode ser commitada
-- 0 = nenhuma transação ativa
-- -1 = não pode ser commitada (deve fazer rollback)

-- Use XACT_STATE no bloco CATCH
BEGIN CATCH
    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;  -- Deve fazer rollback
    ELSE IF XACT_STATE() = 1
        COMMIT TRANSACTION;    -- Ainda pode commitar

    THROW;
END CATCH;
```

## Níveis de Isolamento

### Visão Geral

| Nível | Dirty Reads | Non-Repeatable Reads | Phantoms | Concorrência |
|-------|-------------|----------------------|----------|--------------|
| READ UNCOMMITTED | Sim | Sim | Sim | Máxima |
| READ COMMITTED | Não | Sim | Sim | Alta |
| REPEATABLE READ | Não | Não | Sim | Média |
| SERIALIZABLE | Não | Não | Não | Mínima |
| SNAPSHOT | Não | Não | Não | Alta |
| READ COMMITTED SNAPSHOT | Não | Sim | Sim | Alta |

### Definindo Níveis de Isolamento

```sql
-- Nível de sessão
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

-- Nível de hint na query
SELECT * FROM Orders WITH (NOLOCK);    -- Equivalente a READ UNCOMMITTED
SELECT * FROM Orders WITH (HOLDLOCK);  -- Equivalente a SERIALIZABLE

-- Verifica o nível atual
SELECT CASE transaction_isolation_level
    WHEN 0 THEN 'Não especificado'
    WHEN 1 THEN 'ReadUncommitted'
    WHEN 2 THEN 'ReadCommitted'
    WHEN 3 THEN 'RepeatableRead'
    WHEN 4 THEN 'Serializable'
    WHEN 5 THEN 'Snapshot'
END
FROM sys.dm_exec_sessions
WHERE session_id = @@SPID;
```

### READ UNCOMMITTED

```sql
-- Permite dirty reads (ler alterações ainda não commitadas)
-- Use para: estimativas aproximadas, queries de monitoramento, relatórios não-críticos

SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
SELECT COUNT(*) FROM LargeTable;  -- Rápido, mas pode incluir dados não commitados

-- Ou use o hint NOLOCK
SELECT COUNT(*) FROM LargeTable WITH (NOLOCK);

-- ATENÇÃO: pode ler dados que serão desfeitos (rollback)!
```

### READ COMMITTED (Padrão)

```sql
-- Previne dirty reads, permite non-repeatable reads
-- A mesma linha pode retornar valores diferentes se consultada duas vezes

SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN TRANSACTION;
    SELECT Balance FROM Accounts WHERE AccountId = 1;  -- Retorna 100
    -- Outra transação atualiza Balance para 150 e commita
    SELECT Balance FROM Accounts WHERE AccountId = 1;  -- Retorna 150 (mudou!)
COMMIT;
```

### REPEATABLE READ

```sql
-- Previne dirty reads e non-repeatable reads
-- Linhas lidas ficam bloqueadas até o fim da transação

SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
BEGIN TRANSACTION;
    SELECT Balance FROM Accounts WHERE AccountId = 1;  -- Retorna 100
    -- Outra transação tenta atualizar, fica BLOQUEADA até nosso commit
    SELECT Balance FROM Accounts WHERE AccountId = 1;  -- Ainda 100
COMMIT;

-- ATENÇÃO: ainda pode ver linhas fantasma (novos inserts)
```

### SERIALIZABLE

```sql
-- Isolamento mais alto, previne todas as anomalias
-- Usa range locks, pode causar bloqueio significativo

SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;
    SELECT * FROM Orders WHERE OrderDate = '20260908';
    -- Bloqueia o intervalo, impede inserts nesse intervalo também
    -- Nenhum fantasma é possível
COMMIT;

-- Use com moderação devido ao impacto de bloqueio
```

### Isolamento SNAPSHOT

```sql
-- Habilita no nível do banco (configuração única)
ALTER DATABASE YourDatabase SET ALLOW_SNAPSHOT_ISOLATION ON;

-- Usa isolamento snapshot
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;
    SELECT Balance FROM Accounts WHERE AccountId = 1;  -- Retorna 100
    -- Outra transação atualiza para 150 e commita
    SELECT Balance FROM Accounts WHERE AccountId = 1;  -- Ainda 100 (vê o snapshot)
COMMIT;

-- Benefícios: sem bloqueio para leitores, visão consistente
-- Custo: usa tempdb para versionamento de linhas, mais storage
```

### READ COMMITTED SNAPSHOT

```sql
-- Habilita no nível do banco (muda o comportamento padrão)
ALTER DATABASE YourDatabase SET READ_COMMITTED_SNAPSHOT ON;

-- Todas as queries READ COMMITTED passam a usar versionamento de linha
-- Não precisa mudar código, reduz bloqueio significativamente
-- Recomendado para a maioria das aplicações OLTP

-- Verifica se está habilitado
SELECT is_read_committed_snapshot_on FROM sys.databases WHERE name = DB_NAME();
```

## Prevenção de Deadlock

### Entendendo Deadlocks

```sql
-- Cenário de deadlock:
-- Transação A: bloqueia a Linha 1, quer a Linha 2
-- Transação B: bloqueia a Linha 2, quer a Linha 1
-- Nenhuma consegue prosseguir → Deadlock

-- O SQL Server escolhe uma vítima (geralmente a transação de menor custo)
```

### Estratégias de Prevenção

```sql
-- 1. Acesse objetos em ordem consistente
-- Sempre acesse tabelas/linhas na mesma ordem em todo o código

-- RUIM: ordem inconsistente
-- Proc1: UPDATE TableA... UPDATE TableB...
-- Proc2: UPDATE TableB... UPDATE TableA...

-- BOM: ordem consistente
-- Proc1: UPDATE TableA... UPDATE TableB...
-- Proc2: UPDATE TableA... UPDATE TableB...


-- 2. Mantenha as transações curtas
BEGIN TRANSACTION;
    -- Faça o mínimo de trabalho possível dentro da transação
    -- Mova cálculos e validações para fora
COMMIT;


-- 3. Use o nível de isolamento apropriado
-- O isolamento SNAPSHOT elimina deadlocks entre leitor e escritor


-- 4. Use o hint UPDLOCK quando for atualizar após ler
SELECT * FROM Orders WITH (UPDLOCK, ROWLOCK)
WHERE OrderId = @OrderId;
-- Agora mantém um lock de atualização, evitando deadlocks por escalonamento de lock


-- 5. Use ROWLOCK para evitar escalonamento de lock
UPDATE Orders WITH (ROWLOCK)
SET Status = 'Shipped'
WHERE OrderId = @OrderId;
```

### Detecção e Tratamento de Deadlock

```sql
-- Habilita a trace flag de deadlock (para debug)
DBCC TRACEON(1222, -1);  -- Envia detalhes do deadlock ao log de erros

-- Extended Events para monitoramento de deadlock
CREATE EVENT SESSION DeadlockCapture ON SERVER
ADD EVENT sqlserver.xml_deadlock_report
ADD TARGET package0.event_file(SET filename=N'Deadlocks.xel');
ALTER EVENT SESSION DeadlockCapture ON SERVER STATE = START;

-- Tratamento de deadlock em código (padrão de retry)
DECLARE @RetryCount INT = 3;
DECLARE @Success BIT = 0;

WHILE @RetryCount > 0 AND @Success = 0
BEGIN
    BEGIN TRY
        BEGIN TRANSACTION;

        -- Suas operações

        COMMIT;
        SET @Success = 1;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;

        IF ERROR_NUMBER() = 1205  -- Deadlock
        BEGIN
            SET @RetryCount -= 1;
            IF @RetryCount > 0
                WAITFOR DELAY '00:00:00.100';  -- Pequena pausa antes de tentar de novo
            ELSE
                THROW;  -- Sem mais tentativas
        END
        ELSE
            THROW;  -- Não é deadlock, relança imediatamente
    END CATCH
END
```

## Tipos de Lock e Hints

### Tipos de Lock

| Lock | Abreviação | Descrição |
|------|------------|-----------|
| Shared | S | Leitura, permite outras leituras |
| Update | U | Vai atualizar, previne deadlocks |
| Exclusive | X | Escrita, bloqueia tudo |
| Intent | IS, IX, IU | Indicação em nível de tabela de locks de linha |
| Schema | Sch-S, Sch-M | Operações DDL |

### Hints de Lock

```sql
-- NOLOCK: não adquire locks (dirty reads possíveis)
SELECT * FROM Orders WITH (NOLOCK);

-- HOLDLOCK: mantém os locks até o fim da transação (como SERIALIZABLE)
SELECT * FROM Orders WITH (HOLDLOCK);

-- UPDLOCK: adquire lock de atualização imediatamente
SELECT * FROM Orders WITH (UPDLOCK) WHERE OrderId = @Id;

-- ROWLOCK: usa locks em nível de linha
UPDATE Orders WITH (ROWLOCK) SET Status = 'Done' WHERE OrderId = @Id;

-- TABLOCK: bloqueia a tabela inteira
SELECT * FROM SmallTable WITH (TABLOCK);

-- TABLOCKX: lock exclusivo de tabela
TRUNCATE TABLE StagingData;  -- Usa TABLOCKX implicitamente

-- READPAST: pula linhas já bloqueadas
SELECT TOP 10 * FROM JobQueue WITH (READPAST, UPDLOCK)
WHERE Status = 'Pending';  -- Padrão de processamento de fila
```

### Padrão de Processamento de Fila

```sql
-- Processamento seguro de fila com READPAST
CREATE PROCEDURE ProcessNextJob
AS
BEGIN
    DECLARE @JobId INT;

    BEGIN TRANSACTION;

    -- Pega o próximo job disponível, pulando os já bloqueados
    SELECT TOP 1 @JobId = JobId
    FROM JobQueue WITH (UPDLOCK, READPAST)
    WHERE Status = 'Pending'
    ORDER BY CreatedAt;

    IF @JobId IS NOT NULL
    BEGIN
        UPDATE JobQueue SET Status = 'Processing' WHERE JobId = @JobId;
        COMMIT;

        -- Processa fora da transação
        EXEC ProcessJob @JobId;
    END
    ELSE
        COMMIT;
END
```

## Transações Distribuídas

### Transações com Linked Server

```sql
-- Habilita transações distribuídas
EXEC sp_configure 'show advanced options', 1;
RECONFIGURE;
EXEC sp_configure 'ad hoc distributed queries', 1;
RECONFIGURE;

-- Transação distribuída entre linked servers
BEGIN DISTRIBUTED TRANSACTION;

    UPDATE LocalServer.dbo.Accounts SET Balance = Balance - 100 WHERE Id = 1;
    UPDATE LinkedServer.RemoteDB.dbo.Accounts SET Balance = Balance + 100 WHERE Id = 2;

COMMIT;

-- Requer o MS DTC (Distributed Transaction Coordinator)
```

### Simulação de Two-Phase Commit

```sql
-- Quando não é possível usar o MSDTC, use compensação em nível de aplicação

-- Fase 1: Preparar (marca como pendente)
BEGIN TRANSACTION;
    UPDATE Accounts SET Balance = Balance - 100, PendingTransfer = @TransferId
    WHERE AccountId = 1;

    -- Chama o sistema remoto para reservar os fundos
    EXEC @Success = RemoteSystem.ReserveFunds @Amount = 100, @TransferId = @TransferId;

    IF @Success = 0
    BEGIN
        ROLLBACK;
        RETURN;
    END
COMMIT;

-- Fase 2: Commitar (finaliza)
BEGIN TRANSACTION;
    UPDATE Accounts SET PendingTransfer = NULL WHERE AccountId = 1;
    EXEC RemoteSystem.ConfirmTransfer @TransferId = @TransferId;
COMMIT;

-- Compensação se a Fase 2 falhar
-- Desfaz as mudanças locais e chama RemoteSystem.CancelReservation
```

### Padrão Saga para Transações de Longa Duração

```sql
-- Em vez de transação distribuída, use saga com ações compensatórias
-- (cada "step" abaixo é como um arco de uma longa saga: se um capítulo
-- não fecha, os anteriores são compensados em ordem reversa)

CREATE TABLE SagaLog (
    SagaId UNIQUEIDENTIFIER PRIMARY KEY,
    Step INT,
    StepName VARCHAR(100),
    Status VARCHAR(20),  -- Completed, Failed, Compensated
    CompensatingAction VARCHAR(MAX),
    CreatedAt DATETIME2 DEFAULT SYSDATETIME()
);

-- Executa um passo da saga
CREATE PROCEDURE ExecuteSagaStep
    @SagaId UNIQUEIDENTIFIER,
    @StepNumber INT,
    @StepName VARCHAR(100),
    @ActionSql NVARCHAR(MAX),
    @CompensatingSql NVARCHAR(MAX)
AS
BEGIN
    BEGIN TRY
        -- Registra o início do passo
        INSERT INTO SagaLog (SagaId, Step, StepName, Status, CompensatingAction)
        VALUES (@SagaId, @StepNumber, @StepName, 'Running', @CompensatingSql);

        -- Executa a ação
        EXEC sp_executesql @ActionSql;

        -- Marca como completo
        UPDATE SagaLog SET Status = 'Completed'
        WHERE SagaId = @SagaId AND Step = @StepNumber;
    END TRY
    BEGIN CATCH
        -- Marca como falho e dispara a compensação
        UPDATE SagaLog SET Status = 'Failed'
        WHERE SagaId = @SagaId AND Step = @StepNumber;

        EXEC CompensateSaga @SagaId;
        THROW;
    END CATCH
END

-- Compensa todos os passos completos, em ordem reversa
CREATE PROCEDURE CompensateSaga @SagaId UNIQUEIDENTIFIER
AS
BEGIN
    DECLARE @CompensatingSql NVARCHAR(MAX);

    DECLARE compensation_cursor CURSOR FOR
        SELECT CompensatingAction FROM SagaLog
        WHERE SagaId = @SagaId AND Status = 'Completed'
        ORDER BY Step DESC;

    OPEN compensation_cursor;
    FETCH NEXT FROM compensation_cursor INTO @CompensatingSql;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC sp_executesql @CompensatingSql;
        FETCH NEXT FROM compensation_cursor INTO @CompensatingSql;
    END

    CLOSE compensation_cursor;
    DEALLOCATE compensation_cursor;

    UPDATE SagaLog SET Status = 'Compensated'
    WHERE SagaId = @SagaId AND Status = 'Completed';
END
```

## Boas Práticas de Transação

```sql
-- 1. Mantenha as transações o mais curtas possível
-- Faça validações e cálculos antes do BEGIN TRANSACTION

-- 2. Evite interação com o usuário durante transações
-- Nunca use WAITFOR ou chame serviços externos dentro de uma transação

-- 3. Trate os erros corretamente
BEGIN TRY
    BEGIN TRANSACTION;
    -- trabalho
    COMMIT;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK;
    THROW;
END CATCH;

-- 4. Use SET XACT_ABORT ON para comportamento consistente
SET XACT_ABORT ON;  -- Rollback automático em qualquer erro

-- 5. Considere isolamento SNAPSHOT para cargas de leitura intensiva

-- 6. Monitore bloqueios
SELECT * FROM sys.dm_exec_requests WHERE blocking_session_id <> 0;

-- 7. Defina um lock timeout apropriado
SET LOCK_TIMEOUT 5000;  -- Timeout de 5 segundos, retorna erro em vez de esperar para sempre
```
