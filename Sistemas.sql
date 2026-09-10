SELECT
    CODSISTEMA,
    NOMESISTEMA,
    DESCRICAO
FROM GSISTEMA
WHERE CODSISTEMA IN
(
    'A',
    'G',
    'P',
    'V',
    'Z'
)