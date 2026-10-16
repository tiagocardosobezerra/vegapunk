"""
Validação do SQL de apoio (fase 3 da v3), do lado do Shaka.

O SQL de apoio é escrito pela descoberta (`nomi_nomi_no_mi/apoio.py`) para
o usuário achar, no próprio banco, o código que vai no argumento de uma
função. O Shaka confere a FORMA (só um SELECT de colunas de uma tabela, com
ORDER BY) e os NOMES de tabela e coluna contra a lista que recebe. Não abre
a base e não executa nada.
"""

import re

_FORMA = re.compile(
    r'^\s*SELECT\s+(?P<cols>[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)\s+'
    r'FROM\s+(?P<tabela>[A-Za-z_][A-Za-z0-9_]*)'
    r'(?:\s+ORDER\s+BY\s+(?P<ordem>[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*))?\s*;?\s*$',
    re.I)


def validar_sql_de_apoio(sql, nomes):
    """Lista de erros (vazia = válido). `nomes`: {TABELA: {COLUNA, ...}}."""
    m = _FORMA.match(sql or '')
    if not m:
        return ['fora da forma do SQL de apoio: só SELECT de colunas de uma tabela, com ORDER BY opcional']
    tabela = m.group('tabela').upper()
    if tabela not in nomes:
        return [f'tabela {tabela} não está no schema']
    erros = []
    for grupo in ('cols', 'ordem'):
        for c in re.split(r'\s*,\s*', m.group(grupo) or ''):
            if c and c.upper() not in nomes[tabela]:
                erros.append(f'coluna {c.upper()} não está na tabela {tabela}')
    return erros
