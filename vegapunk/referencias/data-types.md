# Referência de Tipos de Dados T-SQL

Diretrizes de seleção de tipo, tratamento de collation e considerações de precisão/escala.

## Sumário

- [Tipos Numéricos](#tipos-numéricos)
- [Tipos de String](#tipos-de-string)
- [Tipos de Data e Hora](#tipos-de-data-e-hora)
- [Collation](#collation)
- [Tipos Binários](#tipos-binários)
- [GUID / UNIQUEIDENTIFIER](#guid--uniqueidentifier)
- [Conversão de Tipo](#conversão-de-tipo)
- [Dicas de Otimização de Storage](#dicas-de-otimização-de-storage)

## Tipos Numéricos

### Guia de Seleção de Inteiros

| Tipo | Intervalo | Storage | Caso de Uso |
|------|-----------|---------|-------------|
| TINYINT | 0 a 255 | 1 byte | Códigos de status, contadores pequenos |
| SMALLINT | -32.768 a 32.767 | 2 bytes | Inteiros de intervalo limitado |
| INT | ±2,1 bilhões | 4 bytes | Padrão para a maioria de IDs e contadores |
| BIGINT | ±9,2 quintilhões | 8 bytes | Sequências grandes, timestamps |

```sql
-- Erro comum: usar BIGINT para tudo
-- Melhor: casar o tipo com o intervalo real dos dados

-- IDs auto-incrementais
CREATE TABLE Orders (
    OrderId INT IDENTITY(1,1) PRIMARY KEY,  -- INT, a menos que espere > 2 bi de linhas
    ...
);

-- Quando usar BIGINT
CREATE TABLE EventLog (
    EventId BIGINT IDENTITY(1,1) PRIMARY KEY,  -- Logging de alto volume
    ...
);
```

### DECIMAL vs FLOAT

```sql
-- DECIMAL(p,s): numérico exato, use para valores monetários/financeiros
-- p = total de dígitos (1-38), s = casas decimais

DECIMAL(10,2)  -- 99.999.999,99 (moeda)
DECIMAL(18,4)  -- 99.999.999.999.999,9999 (cálculos precisos)
DECIMAL(5,4)   -- 9,9999 (taxas, percentuais como decimais)

-- FLOAT/REAL: numérico aproximado, use para dados científicos
FLOAT          -- 8 bytes, precisão de 15 dígitos
REAL           -- 4 bytes, precisão de 7 dígitos

-- ATENÇÃO: nunca use FLOAT para valores monetários
DECLARE @f FLOAT = 0.1 + 0.1 + 0.1;
SELECT @f;  -- 0.30000000000000004 (erro de ponto flutuante!)

-- MONEY/SMALLMONEY: 4 casas decimais fixas
MONEY          -- 8 bytes, ±922 trilhões
SMALLMONEY     -- 4 bytes, ±214.748,3647

-- Prefira DECIMAL a MONEY para controle explícito de precisão
```

### Exemplos de Precisão e Escala

```sql
-- Padrões comuns
DECIMAL(19,4)  -- Financeiro padrão (até 999 trilhões com 4 decimais)
DECIMAL(10,2)  -- Preços/valores típicos
DECIMAL(5,2)   -- Percentuais (0,00 a 999,99)
DECIMAL(9,6)   -- Coordenadas GPS (latitude/longitude)
DECIMAL(38,18) -- Valores de criptomoeda (alta precisão necessária)

-- A escala determina o arredondamento
DECLARE @d DECIMAL(5,2) = 123.456;
SELECT @d;  -- Retorna 123.46 (arredondado)

-- Overflow gera erro
DECLARE @d2 DECIMAL(5,2) = 1234.56;  -- Erro: arithmetic overflow
```

## Tipos de String

### VARCHAR vs NVARCHAR

```sql
-- VARCHAR: 1 byte por caractere, ASCII/ASCII estendido
-- NVARCHAR: 2 bytes por caractere, Unicode (suporta todos os idiomas)

-- Use VARCHAR quando:
-- - O dado é garantidamente ASCII (códigos, identificadores, somente inglês)
-- - Otimização de storage é crítica
VARCHAR(50)    -- Até 50 caracteres
VARCHAR(MAX)   -- Até 2GB

-- Use NVARCHAR quando:
-- - For preciso suportar caracteres internacionais (acentos, "ç", etc. do português)
-- - For conteúdo gerado pelo usuário
-- - Nomes, endereços, descrições
NVARCHAR(100)  -- Até 100 caracteres (200 bytes)
NVARCHAR(MAX)  -- Até 2GB

-- Erro comum: conversão implícita
DECLARE @v VARCHAR(50) = 'test';
SELECT * FROM Users WHERE Name = @v;  -- Se Name for NVARCHAR, causa conversão implícita!
```

### Diretrizes de Tamanho de String

```sql
-- Case com os requisitos reais do dado
VARCHAR(50)    -- Primeiro/último nome
VARCHAR(100)   -- Endereços de e-mail (spec máxima é 254, mas 100 cobre 99%)
VARCHAR(255)   -- URLs, caminhos de arquivo
NVARCHAR(MAX)  -- Texto livre, descrições

-- Evite tamanhos grandes arbitrários
VARCHAR(4000)  -- Se o dado sempre tem < 100 caracteres, desperdiça estimativas de memória

-- Tipos MAX: comportamento de storage diferente
-- Abaixo de 8KB: armazenado in-row
-- Acima de 8KB: armazenado como LOB
```

### CHAR vs VARCHAR

```sql
-- CHAR: comprimento fixo, preenchido com espaços
-- VARCHAR: comprimento variável, sem preenchimento

-- Use CHAR para:
CHAR(2)   -- Sigla de estado ('SP', 'RJ')
CHAR(3)   -- Códigos de moeda ('BRL', 'USD')
CHAR(9)   -- CEP sem hífen
CHAR(11)  -- CPF (formato fixo)

-- Use VARCHAR para:
-- Tudo o mais em que o comprimento varia

-- Pegadinha do CHAR: comparação com espaço à direita
DECLARE @c CHAR(10) = 'test';
DECLARE @v VARCHAR(10) = 'test';
SELECT DATALENGTH(@c), DATALENGTH(@v);  -- 10, 4
SELECT CASE WHEN @c = @v THEN 'Igual' ELSE 'Diferente' END;  -- Igual (espaços ignorados)
SELECT CASE WHEN @c = 'test' THEN 'Confere' END;  -- Confere (padding tratado)
```

## Tipos de Data e Hora

### Seleção de Tipo

| Tipo | Intervalo | Precisão | Storage | Caso de Uso |
|------|-----------|----------|---------|-------------|
| DATE | 0001-01-01 a 9999-12-31 | 1 dia | 3 bytes | Data de nascimento, datas de calendário |
| TIME | 00:00:00 a 23:59:59,9999999 | 100ns | 3-5 bytes | Somente hora do dia |
| DATETIME | 1753 a 9999 | 3,33ms | 8 bytes | Legado, evite em código novo |
| DATETIME2 | 0001 a 9999 | 100ns | 6-8 bytes | Padrão para timestamps |
| DATETIMEOFFSET | 0001 a 9999 | 100ns + fuso | 8-10 bytes | Com fuso horário |
| SMALLDATETIME | 1900 a 2079 | 1 minuto | 4 bytes | Storage restrito, precisão de minuto OK |

```sql
-- Boa prática moderna: use DATETIME2
CREATE TABLE Events (
    EventId INT PRIMARY KEY,
    CreatedAt DATETIME2(3) DEFAULT SYSDATETIME(),  -- Precisão de milissegundo
    ScheduledDate DATE,  -- Quando a hora não importa
    Duration TIME(0)     -- Quando a data não importa
);

-- Com fuso horário (para aplicações globais)
CREATE TABLE AuditLog (
    LogId BIGINT PRIMARY KEY,
    Timestamp DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET()
);

-- A precisão afeta o storage
DATETIME2(0)  -- Segundos, 6 bytes
DATETIME2(3)  -- Milissegundos, 7 bytes
DATETIME2(7)  -- 100 nanossegundos, 8 bytes (padrão)
```

### Aritmética de Datas

```sql
-- Use DATEADD/DATEDIFF, não aritmética direta
SELECT DATEADD(DAY, 7, GETDATE());           -- Adiciona 7 dias
SELECT DATEADD(MONTH, -1, GETDATE());        -- Subtrai 1 mês
SELECT DATEDIFF(DAY, StartDate, EndDate);    -- Dias entre as datas

-- Padrões de truncamento de data
SELECT CAST(GETDATE() AS DATE);                                    -- Remove a hora
SELECT DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0);          -- Primeiro dia do mês
SELECT EOMONTH(GETDATE());                                         -- Último dia do mês
SELECT DATEADD(QUARTER, DATEDIFF(QUARTER, 0, GETDATE()), 0);      -- Primeiro dia do trimestre

-- SQL Server 2022+
SELECT DATETRUNC(MONTH, GETDATE());  -- Truncamento mais direto
```

### Exibindo datas no padrão pt-BR (dd/MM/aaaa)

```sql
-- CONVERT com style 103 = dd/mm/yyyy
SELECT CONVERT(VARCHAR(10), GETDATE(), 103);    -- 08/09/2026

-- FORMAT com cultura pt-BR (mais legível, ligeiramente mais lento)
SELECT FORMAT(GETDATE(), 'dd/MM/yyyy', 'pt-BR');           -- 08/09/2026
SELECT FORMAT(GETDATE(), 'dd/MM/yyyy HH:mm:ss', 'pt-BR');  -- 08/09/2026 14:32:07

-- NUNCA use style 101 (MM/DD/YYYY, padrão en-US) ao exibir para o usuário
-- SELECT CONVERT(VARCHAR(10), GETDATE(), 101);  -- 09/08/2026 <- ERRADO para pt-BR (mês/dia trocados)

-- String para data: aceite explicitamente o formato dd/MM/aaaa (não confie na conversão implícita)
SELECT CONVERT(DATE, '08/09/2026', 103);   -- 2026-09-08 (interpretado como dd/mm/yyyy)
SELECT TRY_CONVERT(DATE, '08/09/2026', 103); -- NULL em vez de erro, se inválido
```

## Collation

### Entendendo Collation

```sql
-- Collation afeta: ordenação, comparação, sensibilidade a maiúsculas/minúsculas

-- Verifique a collation atual
SELECT DATABASEPROPERTYEX(DB_NAME(), 'Collation');
SELECT name, collation_name FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Users');

-- Collations comuns para dados em português
-- Latin1_General_100_CI_AI       -- Case & Accent Insensitive (bom para busca tolerante a acento)
-- SQL_Latin1_General_CP1_CI_AS   -- Case Insensitive, Accent Sensitive (padrão comum)
-- Latin1_General_CS_AS           -- Case Sensitive

-- CI = Case Insensitive (não diferencia maiúsc./minúsc.), CS = Case Sensitive (diferencia)
-- AI = Accent Insensitive (não diferencia acento), AS = Accent Sensitive (diferencia)
-- BIN = Binário (comparação exata de bytes)
```

### Conflitos de Collation

```sql
-- Problema: comparar colunas com collations diferentes
SELECT * FROM TableA a
JOIN TableB b ON a.Name = b.Name;  -- Erro se as collations forem diferentes!

-- Solução: COLLATE explícito
SELECT * FROM TableA a
JOIN TableB b ON a.Name = b.Name COLLATE Latin1_General_CI_AS;

-- Ou crie com collation compatível
CREATE TABLE Example (
    Name NVARCHAR(100) COLLATE Latin1_General_CI_AS
);
```

### Operações Sensíveis a Maiúsculas/Minúsculas

```sql
-- Força comparação sensível a maiúsculas (mesmo em banco CI)
SELECT * FROM Users
WHERE Name COLLATE Latin1_General_CS_AS = 'Smith';

-- Força comparação insensível a maiúsculas (mesmo em banco CS)
SELECT * FROM Users
WHERE Name COLLATE Latin1_General_CI_AS = 'SMITH';

-- Índice case-sensitive para performance
CREATE INDEX IX_Users_Name_CS ON Users(Name)
WHERE Name = Name COLLATE Latin1_General_CS_AS;
```

## Tipos Binários

```sql
-- BINARY: comprimento fixo
BINARY(16)     -- Storage de UUID/GUID (UNIQUEIDENTIFIER usa 16 bytes)
BINARY(32)     -- Hash SHA-256

-- VARBINARY: comprimento variável
VARBINARY(MAX) -- Arquivos, imagens, documentos
VARBINARY(256) -- Chaves de criptografia, hashes

-- Converter de/para hexadecimal
SELECT CONVERT(VARBINARY(32), 0x48656C6C6F);  -- A partir de literal hex
SELECT CONVERT(VARCHAR(100), @binary, 2);     -- Para string hex (sem prefixo 0x)
SELECT CONVERT(VARCHAR(100), @binary, 1);     -- Para string hex (com prefixo 0x)

-- Exemplo de hash
SELECT HASHBYTES('SHA2_256', 'senha123');  -- Retorna VARBINARY(32)
```

## GUID / UNIQUEIDENTIFIER

```sql
-- Identificador global único de 16 bytes
CREATE TABLE Documents (
    DocumentId UNIQUEIDENTIFIER DEFAULT NEWID() PRIMARY KEY,
    ...
);

-- NEWID() vs NEWSEQUENTIALID()
NEWID()           -- Aleatório, causa page splits em índice clusterizado
NEWSEQUENTIALID() -- Sequencial por reinício do servidor, melhor para clustering

-- Boa prática: não clusterizar em GUID aleatório
CREATE TABLE Documents (
    Id INT IDENTITY(1,1) PRIMARY KEY CLUSTERED,  -- Clusterizado em INT
    DocumentId UNIQUEIDENTIFIER DEFAULT NEWID() UNIQUE NONCLUSTERED
);
```

## Conversão de Tipo

### Implícita vs Explícita

```sql
-- Precedência de tipo de dado (o maior vence na conversão implícita)
-- 1. DATETIMEOFFSET > DATETIME2 > DATETIME > DATE/TIME
-- 2. FLOAT > REAL
-- 3. DECIMAL > MONEY > INT > SMALLINT > TINYINT
-- 4. NVARCHAR > VARCHAR > NCHAR > CHAR

-- Conversão implícita perigosa (causa index scan)
DECLARE @v VARCHAR(50) = 'test';
SELECT * FROM Users WHERE Name = @v;  -- Se Name for NVARCHAR!

-- Seguro: tipos compatíveis
DECLARE @n NVARCHAR(50) = N'test';
SELECT * FROM Users WHERE Name = @n;

-- Conversão explícita
CAST(expression AS target_type)    -- Padrão ANSI
CONVERT(target_type, expression)   -- SQL Server, com opções de estilo
TRY_CAST(expression AS type)       -- Retorna NULL em caso de falha
TRY_CONVERT(type, expression)      -- Retorna NULL em caso de falha
```

### Conversões Comuns

```sql
-- Data para string (padrão pt-BR)
SELECT CONVERT(VARCHAR(10), GETDATE(), 103);    -- 08/09/2026 (dd/mm/yyyy)
SELECT FORMAT(GETDATE(), 'dd/MM/yyyy', 'pt-BR'); -- 08/09/2026

-- Data para string (padrão ISO, útil para armazenamento/ordenação, não para exibição)
SELECT CONVERT(VARCHAR(10), GETDATE(), 120);    -- 2026-09-08

-- String para data (assumindo formato dd/MM/aaaa)
SELECT CONVERT(DATE, '08/09/2026', 103);
SELECT TRY_CONVERT(DATE, 'invalido', 103);  -- NULL em vez de erro

-- Formatação de número no padrão pt-BR (milhar '.', decimal ',')
SELECT FORMAT(1234567.89, 'N2', 'pt-BR');     -- 1.234.567,89
SELECT FORMAT(0.156, 'P1', 'pt-BR');          -- 15,6%

-- NUNCA use FORMAT sem cultura (ou com 'en-US') ao exibir para o usuário
-- SELECT FORMAT(1234567.89, 'N2');  -- 1,234,567.89 <- ERRADO para pt-BR

-- Conversão de JSON (2016+)
SELECT * FROM OpenJson(@json);
SELECT (SELECT * FROM table FOR JSON PATH);
```

## Dicas de Otimização de Storage

```sql
-- A ordem das colunas afeta o storage (colunas de tamanho variável no final)
CREATE TABLE Optimized (
    Id INT NOT NULL,              -- Fixo: 4 bytes
    Status TINYINT NOT NULL,      -- Fixo: 1 byte
    Amount DECIMAL(10,2) NOT NULL,-- Fixo: 5 bytes
    Name NVARCHAR(100) NULL,      -- Variável
    Description NVARCHAR(MAX) NULL -- Variável (possivelmente LOB)
);

-- Colunas computadas (sem storage, calculadas na leitura)
CREATE TABLE Orders (
    Quantity INT,
    UnitPrice DECIMAL(10,2),
    TotalPrice AS (Quantity * UnitPrice)  -- Coluna virtual
);

-- Colunas computadas persistidas (armazenadas, podem ser indexadas)
CREATE TABLE Orders (
    OrderDate DATETIME2,
    OrderYear AS YEAR(OrderDate) PERSISTED  -- Armazenada, indexável
);

-- Colunas esparsas (sparse), para colunas com muitos NULLs
CREATE TABLE SparseExample (
    Id INT PRIMARY KEY,
    RareValue1 INT SPARSE NULL,
    RareValue2 NVARCHAR(100) SPARSE NULL
);
```
