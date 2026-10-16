"""
Recálculo das métricas de ranking no lugar (fase 5 da v3).

Filhas, pais, conexões, `score_relevancia` e `ranking` de cada tabela são
recalculados pela MESMA função do `importar` (`calcular_metricas_e_scores`),
com os pares da leitura dirigida corrigida (`relacionamentos_corrigidos`,
quando existe). Usado quando a fórmula muda (ligação só com as duas pontas
na base, pesos estruturais recalibrados): nenhuma linha de ligação é
alterada, só as colunas derivadas da tabela `tabelas`.

Tudo numa transação, com cópia de segurança antes. Só o York chama
(`york.py recalcular-metricas`).
"""

import shutil
import sqlite3

from punk_records import migracoes
from punk_records.schema import PESO_CONEXOES, PESO_FILHAS, PESO_PAIS, calcular_metricas_e_scores

COLUNAS = ('score_relevancia', 'ranking', 'tabelas_filhas', 'tabelas_pais', 'conexoes_totais')


def _fonte(conn):
    tem_view = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'view' AND name = 'relacionamentos_corrigidos'").fetchone()
    return 'relacionamentos_corrigidos' if tem_view else 'relacionamentos'


def calcular(conn, pesos=None):
    """({tabela: métricas novas}, {tabela: métricas atuais}) sem gravar."""
    tabelas = [r[0] for r in conn.execute('SELECT tabela FROM tabelas')]
    pares = conn.execute(f'SELECT tabela_filha, tabela_mae FROM {_fonte(conn)}').fetchall()
    antes = {r[0]: tuple(r[1:]) for r in conn.execute(f'SELECT tabela, {", ".join(COLUNAS)} FROM tabelas')}
    return calcular_metricas_e_scores(tabelas, pares, pesos), antes


def recalcular(db_path, destino_backup=None, pesos=None):
    if migracoes._sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite presentes: {migracoes._sobras(db_path)}')
    copia = migracoes.copiar_seguranca(db_path, destino_backup)
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute('BEGIN IMMEDIATE')
        metricas, antes = calcular(conn, pesos)
        mudaram = 0
        for t, m in metricas.items():
            novo = tuple(m[c] for c in COLUNAS)
            if antes.get(t) != novo:
                mudaram += 1
                conn.execute(f'UPDATE tabelas SET {", ".join(c + " = ?" for c in COLUNAS)} WHERE tabela = ?',
                             novo + (t,))
        p = pesos or (PESO_FILHAS, PESO_CONEXOES, PESO_PAIS)
        conn.execute("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('metricas:recalculadas', ?)",
                     (f'{migracoes._agora()} | só ligações com as duas pontas na base | pesos filhas/conexões/pais '
                      f'{p[0]}/{p[1]}/{p[2]} | tabelas alteradas {mudaram}',))
        conn.execute('COMMIT')
        ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise RuntimeError(f'integrity_check depois do recálculo: {ok}')
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except sqlite3.OperationalError:
            pass
        conn.close()
        shutil.copy2(copia, db_path)
        raise
    conn.close()
    if migracoes._sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite ficaram para trás: {migracoes._sobras(db_path)}')
    return {'copia': copia, 'tabelas_com_metrica_alterada': mudaram, 'pesos': list(p)}
