;WITH GDIC_Filtrada AS
(
    SELECT DISTINCT
        UPPER(TABELA) AS TABELA
    FROM GDIC WITH (NOLOCK)
    WHERE TABELA IS NOT NULL
      AND (
            TABELA LIKE 'A%'
         OR TABELA LIKE 'G%'
         OR TABELA LIKE 'P%'
         OR TABELA LIKE 'V%'
         OR TABELA LIKE 'Z%'

      )
),

DescricaoTabela AS
(
    SELECT
        UPPER(TABELA) AS TABELA,
        DESCRICAO
    FROM GDIC WITH (NOLOCK)
    WHERE COLUNA = '#'
),

ContagemFilhos AS
(
    SELECT
        UPPER(MASTERTABLE) AS TABELA,
        COUNT(DISTINCT CHILDTABLE) AS QT_FILHOS
    FROM GLINKSREL WITH (NOLOCK)
    GROUP BY UPPER(MASTERTABLE)
),

ContagemPais AS
(
    SELECT
        UPPER(CHILDTABLE) AS TABELA,
        COUNT(DISTINCT MASTERTABLE) AS QT_PAIS
    FROM GLINKSREL WITH (NOLOCK)
    GROUP BY UPPER(CHILDTABLE)
),

Volumetria AS
(
    SELECT
        UPPER(t.name) AS TABELA,
        SUM(p.rows) AS QT_REGISTROS
    FROM sys.tables t
    INNER JOIN sys.partitions p
        ON t.object_id = p.object_id
    WHERE p.index_id IN (0,1)
      AND t.schema_id = SCHEMA_ID('dbo')
    GROUP BY UPPER(t.name)
),

EstatisticasBrutas AS
(
    SELECT
        f.TABELA,
        d.DESCRICAO AS DESCRICAO_TABELA,
        ISNULL(v.QT_REGISTROS,0) AS QT_REGISTROS,
        LOG10(ISNULL(v.QT_REGISTROS,0) + 1) AS LOG_REGISTROS,
        ISNULL(cf.QT_FILHOS,0) AS QT_FILHOS,
        ISNULL(cp.QT_PAIS,0) AS QT_PAIS,
        ISNULL(cf.QT_FILHOS,0) + ISNULL(cp.QT_PAIS,0) AS TOTAL_CONEXOES
    FROM GDIC_Filtrada f
    LEFT JOIN DescricaoTabela d
        ON f.TABELA = d.TABELA
    LEFT JOIN ContagemFilhos cf
        ON f.TABELA = cf.TABELA
    LEFT JOIN ContagemPais cp
        ON f.TABELA = cp.TABELA
    LEFT JOIN Volumetria v
        ON f.TABELA = v.TABELA
),

Maximos AS
(
    SELECT
        NULLIF(MAX(QT_FILHOS),0)      AS MAX_FILHOS,
        NULLIF(MAX(TOTAL_CONEXOES),0) AS MAX_CONEXOES,
        NULLIF(MAX(QT_PAIS),0)        AS MAX_PAIS,
        NULLIF(MAX(LOG_REGISTROS),0)  AS MAX_VOLUMETRIA
    FROM EstatisticasBrutas
)

SELECT
    e.TABELA,
    e.DESCRICAO_TABELA AS DESCRICAO,

    ROW_NUMBER() OVER
    (
        ORDER BY
            SCORE_RELEVANCIA DESC,
            e.TABELA
    ) AS RANKING,

    SCORE_RELEVANCIA,

    e.QT_FILHOS       AS TABELAS_FILHAS,
    e.QT_PAIS         AS TABELAS_PAIS,
    e.TOTAL_CONEXOES  AS CONEXOES_TOTAIS

FROM
(
    SELECT
        e.*,

        CAST
        (
            ROUND
            (
                  ISNULL((100.0 * e.QT_FILHOS      / NULLIF(m.MAX_FILHOS,0))      * 0.40,0)
                + ISNULL((100.0 * e.TOTAL_CONEXOES / NULLIF(m.MAX_CONEXOES,0))    * 0.30,0)
                + ISNULL((100.0 * e.QT_PAIS        / NULLIF(m.MAX_PAIS,0))        * 0.15,0)
                + ISNULL((100.0 * e.LOG_REGISTROS  / NULLIF(m.MAX_VOLUMETRIA,0))  * 0.15,0)
            ,2)
        AS DECIMAL(10,2)
        ) AS SCORE_RELEVANCIA

    FROM EstatisticasBrutas e
    CROSS JOIN Maximos m
) e

ORDER BY
    RANKING;