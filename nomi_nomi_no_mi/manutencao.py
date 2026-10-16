"""
Manutenção (só leitura): cobertura de módulos cadastrados em `sistemas`.

Parte do Nomi Nomi no Mi, movida sem mudança de algoritmo do antigo
`scripts/nomi_nomi_no_mi.py` (fase 1 da v3).
"""

import sqlite3
from typing import Dict, List

# ==============================================================================
# ITEM 1 (auditoria de inovação) — CHECAGEM AUTOMÁTICA DE COBERTURA DE MÓDULO
# ==============================================================================

def checar_cobertura_modulos(db_path: str) -> List[Dict]:
    """Compara os prefixos de tabela que EXISTEM no schema real contra
    os módulos cadastrados em `sistemas`. Um prefixo fora de `sistemas`
    fica invisível para toda busca até a v-anterior do item 2 (agora só
    despriorizado, nunca mais excluído) — mas mesmo despriorizado, é
    melhor saber que ele existe do que descobrir por acidente (foi
    assim que o módulo 'Z', com 64 tabelas e 712 colunas reais, ficou
    sem cadastro sem que ninguém soubesse)."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT SUBSTR(tabela, 1, 1) AS prefixo, COUNT(*) FROM tabelas GROUP BY prefixo")
    prefixos_reais = {row[0]: row[1] for row in cur.fetchall()}

    cadastrados = set()
    try:
        cur.execute("SELECT codigo_sistema FROM sistemas")
        cadastrados = {row[0] for row in cur.fetchall()}
    except sqlite3.OperationalError:
        pass

    faltando = []
    for prefixo, n_tabelas in prefixos_reais.items():
        if prefixo in cadastrados:
            continue
        cur.execute("SELECT COUNT(*) FROM colunas WHERE SUBSTR(tabela, 1, 1) = ?", (prefixo,))
        n_colunas = cur.fetchone()[0]
        cur.execute("SELECT tabela FROM tabelas WHERE SUBSTR(tabela, 1, 1) = ? ORDER BY tabela LIMIT 5", (prefixo,))
        exemplos = [r[0] for r in cur.fetchall()]
        faltando.append({
            'prefixo': prefixo,
            'tabelas': n_tabelas,
            'colunas': n_colunas,
            'exemplos': exemplos,
        })
    conn.close()
    faltando.sort(key=lambda f: (-f['tabelas'], f['prefixo']))
    return faltando
