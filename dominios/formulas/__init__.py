"""
Shaka — motor de fórmulas do Vegapunk.

Pacote independente do motor de schema (`nomi_nomi_no_mi/`): não
importa nada dele e não é importado por ele. As duas engines evoluem
separadas; o que é "comum" (normalização de texto pt-BR) é reimplementado
aqui de propósito, para que uma mudança de tokenização em uma nunca altere
o ranking da outra (ver referencias/formulas.md, seção 4).

Camadas:
    texto        — normalização/tokenização (sem conhecimento de domínio)
    modelo       — dataclasses do dicionário (Funcao, Parametro, Origem...)
    conhecimento — providers de conhecimento (pacotes públicos/privados), merge, índice
    sintaxe      — lexer/parser genérico guiado por um DIALETO (dado, não código)
    validador    — checagens de existência/aridade/sintaxe/combinações
    compositor   — pedido em linguagem natural -> plano -> fórmula + explicação
    ingestao     — conectores de fonte (ex.: Confluence) e extratores de conteúdo
"""

VERSAO = '1.0.0'
