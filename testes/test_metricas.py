"""Métricas de ranking (fase 5): ligação só conta com as duas pontas na base;
o recálculo no lugar grava a fórmula atual com cópia de segurança e não
toca nas ligações. Nomes fictícios."""

import os
import sqlite3
import tempfile
import unittest

import _comum  # noqa: F401
from casos.fixture_schema import gerar_fixture_db
from punk_records import migracoes
from punk_records.metricas import COLUNAS, calcular, recalcular
from punk_records.schema import calcular_metricas_e_scores


class TestDuasPontas(unittest.TestCase):
    def test_ligacao_para_tabela_fora_da_base_nao_conta(self):
        m = calcular_metricas_e_scores({'A', 'B'}, [('B', 'A'), ('X_FORA', 'A'), ('B', 'Y_FORA')])
        self.assertEqual((m['A']['tabelas_filhas'], m['A']['tabelas_pais'], m['A']['conexoes_totais']), (1, 0, 1))
        self.assertEqual((m['B']['tabelas_filhas'], m['B']['tabelas_pais'], m['B']['conexoes_totais']), (0, 1, 1))
        self.assertNotIn('X_FORA', m)

    def test_pesos_explicitos(self):
        pares = [('B', 'A'), ('C', 'A'), ('C', 'B')]
        so_filhas = calcular_metricas_e_scores({'A', 'B', 'C'}, pares, (1, 0, 0))
        so_pais = calcular_metricas_e_scores({'A', 'B', 'C'}, pares, (0, 0, 1))
        self.assertEqual(so_filhas['A']['ranking'], 1)
        self.assertEqual(so_pais['C']['ranking'], 1)


class TestRecalcular(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, 'f.db')
        gerar_fixture_db(self.db)
        migracoes.aplicar(self.db, destino_backup=os.path.join(self._tmp.name, 'bk'))
        conn = sqlite3.connect(self.db)
        conn.execute("INSERT INTO relacionamentos (tabela_filha, campo_filho, tabela_mae, campo_mae) "
                     "VALUES ('X_FORA_DA_BASE', 'CODEMPRESA', 'N_EMPRESA', 'CODEMPRESA')")
        conn.execute("UPDATE tabelas SET score_relevancia = 0, ranking = 0")
        conn.commit()
        conn.close()

    def tearDown(self):
        self._tmp.cleanup()

    def _ligacoes(self):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute('SELECT * FROM relacionamentos ORDER BY rowid').fetchall()
        finally:
            conn.close()

    def test_grava_formula_atual_e_preserva_ligacoes(self):
        antes = self._ligacoes()
        r = recalcular(self.db, destino_backup=os.path.join(self._tmp.name, 'bk2'))
        self.assertTrue(os.path.exists(r['copia']))
        self.assertGreater(r['tabelas_com_metrica_alterada'], 0)
        self.assertEqual(self._ligacoes(), antes)
        conn = sqlite3.connect(self.db)
        try:
            esperado, gravado = calcular(conn)
            self.assertEqual({t: tuple(m[c] for c in COLUNAS) for t, m in esperado.items()}, gravado)
            self.assertIn('duas pontas', conn.execute(
                "SELECT valor FROM meta WHERE chave = 'metricas:recalculadas'").fetchone()[0])
        finally:
            conn.close()
        self.assertEqual(migracoes._sobras(self.db), [])

    def test_idempotente(self):
        recalcular(self.db, destino_backup=os.path.join(self._tmp.name, 'bk2'))
        r = recalcular(self.db, destino_backup=os.path.join(self._tmp.name, 'bk3'))
        self.assertEqual(r['tabelas_com_metrica_alterada'], 0)


if __name__ == '__main__':
    unittest.main()
