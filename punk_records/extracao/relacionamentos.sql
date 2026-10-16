/*
================================================================================
 relacionamentos.sql — extração da ESTRUTURA para a Punk Records (relacionamentos.csv)
================================================================================
Lê SOMENTE o catálogo do SQL Server (sys.*). Nenhum SELECT em tabela de
usuário: do banco sai só estrutura, nunca linha de conteúdo.
Traz cada FK declarada no banco com o nome da constraint e a ordem da
coluna dentro dela. Filha e mãe no mesmo @esquema (cópias de auditoria em
outro schema ficam de fora).

Roda igual no SSMS (sem modo SQLCMD) e no sqlcmd. Não cita nome de banco:
rode com o banco do ERP selecionado. O schema é a variável @esquema logo
abaixo (padrão dbo). Se o schema não tiver tabelas, a consulta falha e
lista os schemas que existem, com quantas tabelas cada um tem.

Saída: uma coluna; a 1ª linha é o cabeçalho do CSV. Grave o resultado em
<pasta da skill>\egghead\extracao\relacionamentos.csv (fora do controle de versão).
  SSMS:   Query > Results To > Results to File; em Tools > Options > Query
          Results > SQL Server > Results to Text, desmarque "Include column
          headers" e use 8192 em "Maximum number of characters".
  sqlcmd: sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000
          -i punk_records\extracao\relacionamentos.sql -o egghead\extracao\relacionamentos.csv
Depois: python3 satelites/york.py enriquecer --dir egghead/extracao
================================================================================
*/
SET NOCOUNT ON;
DECLARE @esquema sysname = N'dbo';   -- schema das tabelas do ERP

IF NOT EXISTS (SELECT 1 FROM sys.tables AS t JOIN sys.schemas AS s ON s.schema_id = t.schema_id
               WHERE s.name = @esquema AND t.is_ms_shipped = 0)
BEGIN
    DECLARE @lista nvarchar(2000) = STUFF((
        SELECT N', ' + s.name + N' (' + CAST(COUNT(*) AS nvarchar(10)) + N')'
        FROM sys.tables AS t JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE t.is_ms_shipped = 0
        GROUP BY s.name ORDER BY COUNT(*) DESC
        FOR XML PATH(''), TYPE).value('.', 'nvarchar(2000)'), 1, 2, N'');
    RAISERROR(N'O esquema %s não tem tabelas neste banco. Esquemas com tabelas: %s', 16, 1, @esquema, @lista);
END
ELSE
SELECT x.linha
FROM (
    SELECT 0 AS ordem, N'' AS tabela, N'' AS fk, 0 AS posicao,
           CAST(N'tabela_filha,campo_filho,tabela_mae,campo_mae,constraint,ordem' AS nvarchar(max)) AS linha
    UNION ALL
    SELECT 1, tf.name, fk.name, fkc.constraint_column_id,
           CONCAT(
               N'"', REPLACE(tf.name, N'"', N'""'), N'",',
               N'"', REPLACE(cf.name, N'"', N'""'), N'",',
               N'"', REPLACE(tm.name, N'"', N'""'), N'",',
               N'"', REPLACE(cm.name, N'"', N'""'), N'",',
               N'"', REPLACE(fk.name, N'"', N'""'), N'",',
               fkc.constraint_column_id)
    FROM sys.foreign_keys AS fk
    JOIN sys.foreign_key_columns AS fkc ON fkc.constraint_object_id = fk.object_id
    JOIN sys.tables AS tf ON tf.object_id = fkc.parent_object_id
    JOIN sys.schemas AS sf ON sf.schema_id = tf.schema_id
    JOIN sys.columns AS cf ON cf.object_id = fkc.parent_object_id AND cf.column_id = fkc.parent_column_id
    JOIN sys.tables AS tm ON tm.object_id = fkc.referenced_object_id
    JOIN sys.schemas AS sm ON sm.schema_id = tm.schema_id
    JOIN sys.columns AS cm ON cm.object_id = fkc.referenced_object_id AND cm.column_id = fkc.referenced_column_id
    WHERE tf.is_ms_shipped = 0 AND sf.name = @esquema AND sm.name = @esquema
) AS x
ORDER BY x.ordem, x.tabela, x.fk, x.posicao;
