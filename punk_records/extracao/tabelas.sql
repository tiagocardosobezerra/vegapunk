/*
================================================================================
 tabelas.sql — extração da ESTRUTURA para a Punk Records (tabelas.csv)
================================================================================
Lê SOMENTE o catálogo do SQL Server (sys.*). Nenhum SELECT em tabela de
usuário: do banco sai só estrutura, nunca linha de conteúdo.
`tem_dados` é um booleano tirado de sys.partitions ("a tabela tem alguma
linha?"), nunca a contagem.

Roda igual no SSMS (sem modo SQLCMD) e no sqlcmd. Não cita nome de banco:
rode com o banco do ERP selecionado. O schema é a variável @esquema logo
abaixo (padrão dbo). Se o schema não tiver tabelas, a consulta falha e
lista os schemas que existem, com quantas tabelas cada um tem.

Saída: uma coluna; a 1ª linha é o cabeçalho do CSV. Grave o resultado em
<pasta da skill>\egghead\extracao\tabelas.csv (fora do controle de versão).
  SSMS:   Query > Results To > Results to File; em Tools > Options > Query
          Results > SQL Server > Results to Text, desmarque "Include column
          headers" e use 8192 em "Maximum number of characters".
  sqlcmd: sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000
          -i punk_records\extracao\tabelas.sql -o egghead\extracao\tabelas.csv
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
    SELECT 0 AS ordem, N'' AS chave, CAST(N'tabela,descricao,tem_dados' AS nvarchar(max)) AS linha
    UNION ALL
    SELECT 1, t.name,
           CONCAT(
               N'"', REPLACE(t.name, N'"', N'""'), N'",',
               N'"', REPLACE(REPLACE(REPLACE(CAST(ep.value AS nvarchar(max)), N'"', N'""'), CHAR(13), N' '), CHAR(10), N' '), N'",',
               CASE WHEN EXISTS (SELECT 1 FROM sys.partitions AS p
                                 WHERE p.object_id = t.object_id AND p.index_id IN (0, 1) AND p.rows > 0)
                    THEN N'1' ELSE N'0' END)
    FROM sys.tables AS t
    JOIN sys.schemas AS s ON s.schema_id = t.schema_id
    LEFT JOIN sys.extended_properties AS ep
           ON ep.class = 1 AND ep.major_id = t.object_id AND ep.minor_id = 0 AND ep.name = N'MS_Description'
    WHERE t.is_ms_shipped = 0 AND s.name = @esquema
) AS x
ORDER BY x.ordem, x.chave;
