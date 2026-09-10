# Referência de Segurança T-SQL

Prevenção de SQL injection, segurança de SQL dinâmico e padrões de permissão.

## Sumário

- [Prevenção de SQL Injection](#prevenção-de-sql-injection)
- [Padrões Seguros de SQL Dinâmico](#padrões-seguros-de-sql-dinâmico)
- [Padrões de Permissão](#padrões-de-permissão)
- [Mascaramento de Dados](#mascaramento-de-dados)
- [Log de Auditoria](#log-de-auditoria)
- [Checklist de Vulnerabilidades Comuns](#checklist-de-vulnerabilidades-comuns)

## Prevenção de SQL Injection

### O Problema Central

```sql
-- VULNERÁVEL: concatenação de string com input do usuário
DECLARE @sql NVARCHAR(MAX) = N'SELECT * FROM Users WHERE Name = ''' + @UserInput + '''';
EXEC(@sql);

-- Se @UserInput = "'; DROP TABLE Users; --"
-- Executado: SELECT * FROM Users WHERE Name = ''; DROP TABLE Users; --'
```

### Solução: Queries Parametrizadas

```sql
-- SEGURO: usando sp_executesql com parâmetros
DECLARE @sql NVARCHAR(MAX) = N'SELECT * FROM Users WHERE Name = @Name';
EXEC sp_executesql @sql, N'@Name NVARCHAR(100)', @Name = @UserInput;  -- ex.: @UserInput = 'Monkey D. Luffy'
```

### Quando Você Precisa Usar SQL Dinâmico

```sql
-- Cenário: nomes de coluna ou tabela dinâmicos (não podem ser parametrizados)

-- INSEGURO
SET @sql = N'SELECT * FROM ' + @TableName;

-- MAIS SEGURO: valide contra uma whitelist
IF @TableName NOT IN ('Orders', 'Products', 'Customers')
BEGIN
    RAISERROR('Nome de tabela inválido', 16, 1);
    RETURN;
END

-- MAIS SEGURO: use QUOTENAME para escapar identificadores
SET @sql = N'SELECT * FROM ' + QUOTENAME(@TableName);

-- MAIS SEGURO AINDA: mapeie para valores conhecidos
DECLARE @ActualTable NVARCHAR(128) = CASE @TableName
    WHEN 'orders' THEN 'dbo.Orders'
    WHEN 'products' THEN 'dbo.Products'
    ELSE NULL
END;

IF @ActualTable IS NULL
BEGIN
    RAISERROR('Nome de tabela inválido', 16, 1);
    RETURN;
END

SET @sql = N'SELECT * FROM ' + @ActualTable;
```

## Padrões Seguros de SQL Dinâmico

### Busca Dinâmica com Filtros Opcionais

```sql
CREATE PROCEDURE SearchProducts
    @Name NVARCHAR(100) = NULL,
    @CategoryId INT = NULL,
    @MinPrice DECIMAL(10,2) = NULL,
    @MaxPrice DECIMAL(10,2) = NULL
AS
BEGIN
    DECLARE @sql NVARCHAR(MAX) = N'
        SELECT ProductId, Name, Price, CategoryId
        FROM Products
        WHERE 1=1';

    DECLARE @params NVARCHAR(MAX) = N'
        @Name NVARCHAR(100),
        @CategoryId INT,
        @MinPrice DECIMAL(10,2),
        @MaxPrice DECIMAL(10,2)';

    -- Monte a cláusula WHERE com parâmetros (não concatenação)
    IF @Name IS NOT NULL
        SET @sql += N' AND Name LIKE @Name + ''%''';

    IF @CategoryId IS NOT NULL
        SET @sql += N' AND CategoryId = @CategoryId';

    IF @MinPrice IS NOT NULL
        SET @sql += N' AND Price >= @MinPrice';

    IF @MaxPrice IS NOT NULL
        SET @sql += N' AND Price <= @MaxPrice';

    EXEC sp_executesql @sql, @params,
        @Name = @Name,
        @CategoryId = @CategoryId,
        @MinPrice = @MinPrice,
        @MaxPrice = @MaxPrice;
END
```

### ORDER BY Dinâmico

```sql
-- Não é possível parametrizar colunas do ORDER BY, mas dá para validar
CREATE PROCEDURE GetProducts
    @SortColumn NVARCHAR(50) = 'Name',
    @SortDirection NVARCHAR(4) = 'ASC'
AS
BEGIN
    -- Validação por whitelist
    IF @SortColumn NOT IN ('Name', 'Price', 'CreatedDate', 'CategoryId')
        SET @SortColumn = 'Name';

    IF @SortDirection NOT IN ('ASC', 'DESC')
        SET @SortDirection = 'ASC';

    DECLARE @sql NVARCHAR(MAX) = N'
        SELECT ProductId, Name, Price, CreatedDate
        FROM Products
        ORDER BY ' + QUOTENAME(@SortColumn) + N' ' + @SortDirection;

    EXEC sp_executesql @sql;
END
```

### Pivot Dinâmico com Segurança

```sql
CREATE PROCEDURE GetSalesPivot
    @Year INT
AS
BEGIN
    -- Valida o intervalo do ano
    IF @Year < 2000 OR @Year > YEAR(GETDATE()) + 1
    BEGIN
        RAISERROR('Ano inválido', 16, 1);
        RETURN;
    END

    DECLARE @columns NVARCHAR(MAX);

    -- Monta a lista de colunas a partir dos dados reais (não de input do usuário)
    SELECT @columns = STRING_AGG(QUOTENAME(MonthName), ', ')
    FROM (
        SELECT DISTINCT DATENAME(MONTH, SaleDate) AS MonthName
        FROM Sales
        WHERE YEAR(SaleDate) = @Year
    ) AS months;

    DECLARE @sql NVARCHAR(MAX) = N'
        SELECT *
        FROM (
            SELECT
                ProductId,
                DATENAME(MONTH, SaleDate) AS MonthName,
                Amount
            FROM Sales
            WHERE YEAR(SaleDate) = @Year
        ) AS src
        PIVOT (SUM(Amount) FOR MonthName IN (' + @columns + N')) AS pvt';

    EXEC sp_executesql @sql, N'@Year INT', @Year = @Year;
END
```

## Padrões de Permissão

### Princípio do Privilégio Mínimo

```sql
-- Cria uma role para a aplicação
CREATE ROLE AppReadWrite;

-- Concede apenas as permissões necessárias
GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.Orders TO AppReadWrite;
GRANT SELECT ON dbo.Products TO AppReadWrite;
GRANT EXECUTE ON dbo.ProcessOrder TO AppReadWrite;

-- Nega operações perigosas
DENY ALTER, DROP TO AppReadWrite;

-- Adiciona o usuário à role
ALTER ROLE AppReadWrite ADD MEMBER AppServiceAccount;
```

### Segurança Baseada em Schema

```sql
-- Cria schemas para diferentes níveis de acesso
CREATE SCHEMA reporting;
CREATE SCHEMA sensitive;

-- Cria views no schema de relatório para acesso seguro
CREATE VIEW reporting.OrderSummary AS
SELECT
    OrderId,
    OrderDate,
    TotalAmount
    -- Nota: nenhum dado pessoal (PII) de cliente exposto
FROM dbo.Orders;

-- Concede acesso apenas ao schema de relatório
GRANT SELECT ON SCHEMA::reporting TO ReportingRole;
```

### Row-Level Security

```sql
-- Cria a função de predicado de segurança
CREATE FUNCTION dbo.fn_SecurityPredicate(@TenantId INT)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN SELECT 1 AS result
WHERE @TenantId = CAST(SESSION_CONTEXT(N'TenantId') AS INT);

-- Cria a política de segurança
CREATE SECURITY POLICY TenantFilter
ADD FILTER PREDICATE dbo.fn_SecurityPredicate(TenantId) ON dbo.Orders,
ADD BLOCK PREDICATE dbo.fn_SecurityPredicate(TenantId) ON dbo.Orders
WITH (STATE = ON);

-- Define o contexto do tenant na aplicação
EXEC sp_set_session_context @key = N'TenantId', @value = 42;
```

### Segurança de Stored Procedures

```sql
-- Executa como owner para permissões elevadas
CREATE PROCEDURE dbo.AdminOperation
WITH EXECUTE AS OWNER
AS
BEGIN
    -- Isto executa com as permissões do owner, não do chamador
    -- Use com cuidado e valide os inputs cuidadosamente
END

-- Elevação de permissão baseada em assinatura
CREATE CERTIFICATE ProcCert WITH SUBJECT = 'Procedure signing';
CREATE USER ProcCertUser FROM CERTIFICATE ProcCert;
GRANT INSERT ON dbo.AuditLog TO ProcCertUser;

ADD SIGNATURE TO dbo.MyProcedure BY CERTIFICATE ProcCert;
-- Agora MyProcedure pode fazer INSERT em AuditLog mesmo que o chamador não possa
```

## Mascaramento de Dados

### Dynamic Data Masking

```sql
-- Mascara CPF/SSN mostrando apenas os últimos 4 dígitos
ALTER TABLE Customers
ALTER COLUMN SSN ADD MASKED WITH (FUNCTION = 'partial(0,"XXX-XX-",4)');

-- Mascara e-mail
ALTER TABLE Customers
ALTER COLUMN Email ADD MASKED WITH (FUNCTION = 'email()');

-- Máscara aleatória para números
ALTER TABLE Employees
ALTER COLUMN Salary ADD MASKED WITH (FUNCTION = 'random(1000, 5000)');

-- Concede permissão de desmascaramento a uma role específica
GRANT UNMASK TO HRManager;
```

### Criptografia em Nível de Coluna

```sql
-- Cria a chave mestra e o certificado
CREATE MASTER KEY ENCRYPTION BY PASSWORD = 'SenhaForte123!';
CREATE CERTIFICATE SSNCert WITH SUBJECT = 'SSN Encryption';
CREATE SYMMETRIC KEY SSNKey WITH ALGORITHM = AES_256
    ENCRYPTION BY CERTIFICATE SSNCert;

-- Criptografa os dados
OPEN SYMMETRIC KEY SSNKey DECRYPTION BY CERTIFICATE SSNCert;

UPDATE Customers
SET SSN_Encrypted = ENCRYPTBYKEY(KEY_GUID('SSNKey'), SSN);

CLOSE SYMMETRIC KEY SSNKey;

-- Descriptografa os dados
OPEN SYMMETRIC KEY SSNKey DECRYPTION BY CERTIFICATE SSNCert;

SELECT
    CustomerId,
    CONVERT(VARCHAR(11), DECRYPTBYKEY(SSN_Encrypted)) AS SSN
FROM Customers;

CLOSE SYMMETRIC KEY SSNKey;
```

## Log de Auditoria

### SQL Server Audit

```sql
-- Cria a auditoria de servidor
CREATE SERVER AUDIT SecurityAudit
TO FILE (FILEPATH = 'C:\Audits\', MAXSIZE = 100MB);

-- Cria a especificação de auditoria do banco
CREATE DATABASE AUDIT SPECIFICATION SensitiveDataAudit
FOR SERVER AUDIT SecurityAudit
ADD (SELECT, INSERT, UPDATE, DELETE ON dbo.Customers BY public),
ADD (EXECUTE ON dbo.ProcessPayment BY public)
WITH (STATE = ON);

ALTER SERVER AUDIT SecurityAudit WITH (STATE = ON);
```

### Tabela de Auditoria Customizada

```sql
CREATE TABLE dbo.AuditLog (
    AuditId BIGINT IDENTITY PRIMARY KEY,
    TableName NVARCHAR(128),
    Operation CHAR(1), -- I, U, D
    PrimaryKeyValue NVARCHAR(MAX),
    OldValues NVARCHAR(MAX),
    NewValues NVARCHAR(MAX),
    ModifiedBy NVARCHAR(128) DEFAULT SUSER_SNAME(),
    ModifiedAt DATETIME2 DEFAULT SYSDATETIME()
);

-- Exemplo de trigger de auditoria
CREATE TRIGGER trg_Customers_Audit ON dbo.Customers
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Operation CHAR(1) =
        CASE
            WHEN EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) THEN 'U'
            WHEN EXISTS(SELECT 1 FROM inserted) THEN 'I'
            ELSE 'D'
        END;

    INSERT INTO dbo.AuditLog (TableName, Operation, PrimaryKeyValue, OldValues, NewValues)
    SELECT
        'Customers',
        @Operation,
        COALESCE(i.CustomerId, d.CustomerId),
        (SELECT d.* FOR JSON PATH, WITHOUT_ARRAY_WRAPPER),
        (SELECT i.* FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)
    FROM inserted i
    FULL OUTER JOIN deleted d ON i.CustomerId = d.CustomerId;
END
```

## Checklist de Vulnerabilidades Comuns

| Vulnerabilidade | Detecção | Mitigação |
|------------------|----------|-----------|
| Concatenação de string em SQL dinâmico | Busque por `+ @` ou `+ '''` | Use sp_executesql com parâmetros |
| EXEC com input do usuário | Busque por `EXEC(@` | Valide/whitelist, use sp_executesql |
| QUOTENAME ausente | Nomes de objeto dinâmicos sem escape | Sempre use QUOTENAME() |
| xp_cmdshell habilitado | Verifique sys.configurations | Desabilite a menos que absolutamente necessário |
| Conta sa em uso | Verifique connection strings | Use contas de privilégio mínimo |
| Senhas em texto plano | Busque por 'password' no código | Use Always Encrypted ou hashing |
| TRUSTWORTHY ON | Verifique sys.databases | Defina como OFF a menos que necessário |
| Permissões excessivas | Revise memberships de role | Implemente privilégio mínimo |
