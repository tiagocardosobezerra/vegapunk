SELECT
    TABELA,
    COLUNA,
    DESCRICAO
FROM GDIC
WHERE UPPER(LEFT(TABELA, 1)) IN
(
    'A',
    'G',
    'P',
    'V',
    'Z'
)