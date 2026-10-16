"""
Gravação de pares de sinônimo JÁ REVISADOS por humano na tabela
`sinonimos`, nas duas direções. Nunca decide sozinho quais pares são bons:
isso é papel do Edison (`edison.py sugerir-sinonimos`) mais a revisão
humana. Movido sem alteração do antigo `edison.py` (fase 1 da v3); exposto
por `york.py gravar-sinonimos`.
"""

import sqlite3
import sys


USOS = ('busca', 'essencial')


def aplicar(db_path: str, pares, uso: str = None) -> int:
    """`uso` None = par da busca (como sempre); 'essencial' = só a regra do
    termo essencial (precisa da migração 008)."""
    if uso is not None and uso not in USOS:
        raise ValueError(f'uso desconhecido: {uso} (use {", ".join(USOS)})')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tem_uso = 'uso' in {r[1] for r in cur.execute('PRAGMA table_info(sinonimos)').fetchall()}
    if uso == 'essencial' and not tem_uso:
        conn.close()
        raise RuntimeError('a base não tem sinonimos.uso: rode `york.py migrar aplicar` (migração 008)')
    filtro_uso = '' if not tem_uso else (' AND uso IS NULL' if uso in (None, 'busca') else ' AND uso = ?')
    extra = [uso] if (tem_uso and uso == 'essencial') else []
    inseridos = 0
    for a, b in pares:
        a, b = a.strip().lower(), b.strip().lower()
        for termo, sinonimo in ((a, b), (b, a)):
            cur.execute("SELECT 1 FROM sinonimos WHERE termo = ? AND sinonimo = ?" + filtro_uso,
                        [termo, sinonimo] + extra)
            if cur.fetchone():
                continue  # já existe, não duplica
            # Achado em auditoria: isto não bloqueia (edison só aplica pares
            # já revisados por humano — não é papel dele decidir), mas avisa
            # quando `termo` já mapeia para outro sinônimo DIFERENTE de
            # `sinonimo`. Não é necessariamente um erro (uma palavra pode ter
            # mais de um sinônimo legítimo), mas pode indicar um par digitado
            # com o sentido trocado — vale uma segunda olhada humana.
            cur.execute(
                "SELECT sinonimo FROM sinonimos WHERE termo = ? AND sinonimo != ?" + filtro_uso,
                [termo, sinonimo] + extra
            )
            conflitos = [row[0] for row in cur.fetchall()]
            if conflitos:
                print(
                    f"AVISO: '{termo}' já tem sinônimo(s) diferente(s) cadastrado(s) "
                    f"({', '.join(conflitos)}) — adicionando '{sinonimo}' também. "
                    f"Confira se não é um par com o sentido trocado.",
                    file=sys.stderr
                )
            if uso == 'essencial':
                cur.execute("INSERT INTO sinonimos (termo, sinonimo, uso) VALUES (?, ?, ?)", (termo, sinonimo, uso))
            else:
                cur.execute("INSERT INTO sinonimos (termo, sinonimo) VALUES (?, ?)", (termo, sinonimo))
            inseridos += 1
    conn.commit()
    conn.close()
    return inseridos
