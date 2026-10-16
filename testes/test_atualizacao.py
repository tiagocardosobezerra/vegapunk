"""Bloco 5a: atualização NO LUGAR a partir de um export novo do dicionário.
Sem --aplicar só lista; com --aplicar muda só descrições, tem_dados, tabela e
coluna novas e coluna removida (nunca a usada por FK ou mapa); sistemas e
ligações não mudam. Tudo fictício."""

import csv
import os
import sqlite3
import tempfile
import unittest

import _comum  # noqa: F401
from casos.fixture_schema import gerar_fixture_db
from punk_records import migracoes
from punk_records.atualizacao import aplicar, planejar


def _q(db, sql):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


class TestAtualizacao(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = self._tmp.name
        self.db = os.path.join(t, 'f.db')
        gerar_fixture_db(self.db)
        migracoes.aplicar(self.db, destino_backup=os.path.join(t, 'bk'))
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE tabelas SET descricao = 'NULL' WHERE tabela = 'F_AUX001'")
        conn.commit()
        conn.close()
        tabs = _q(self.db, 'SELECT tabela, descricao, tem_dados FROM tabelas')
        cols = _q(self.db, 'SELECT tabela, coluna, descricao FROM colunas')
        self.dic = os.path.join(t, 'dic')
        os.makedirs(self.dic)
        with open(os.path.join(self.dic, 'tabelas.csv'), 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['tabela', 'descricao', 'tem_dados'])
            for tb, d, td in tabs:
                w.writerow([tb, '' if tb == 'F_AUX001' else (d or ''), 0 if tb == 'F_CARGO' else td])
            w.writerow(['F_NOVA', 'Tabela nova fictícia', 1])
        self.removida = next((tb, c) for tb, c, _ in cols if tb == 'F_AUX002' and c != '#')
        with open(os.path.join(self.dic, 'colunas.csv'), 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['tabela', 'coluna', 'descricao'])
            for tb, c, d in cols:
                if (tb, c) != self.removida and not (tb == 'F_FUNCIONARIO' and c == 'CODCARGO'):
                    w.writerow([tb, c, d or ''])
            w.writerow(['F_NOVA', 'CODIGO', 'Código fictício'])
            w.writerow(['F_CARGO', 'NOVACOL', 'Coluna nova fictícia'])
        self.sistemas = _q(self.db, 'SELECT * FROM sistemas')

    def tearDown(self):
        self._tmp.cleanup()

    def test_planejar_so_lista(self):
        antes = _q(self.db, 'SELECT COUNT(*) FROM colunas')
        p = planejar(self.db, self.dic)
        self.assertEqual([x['tabela'] for x in p['tabelas_novas']], ['F_NOVA'])
        self.assertEqual(p['tabelas_descricao'], [{'tabela': 'F_AUX001', 'de': 'NULL', 'para': None}])
        self.assertEqual([x['tabela'] for x in p['tabelas_tem_dados']], ['F_CARGO'])
        self.assertIn({'tabela': 'F_CARGO', 'coluna': 'NOVACOL', 'descricao': 'Coluna nova fictícia', 'estrutura': None},
                      p['colunas_novas'])
        self.assertEqual([(x['tabela'], x['coluna']) for x in p['colunas_removidas']], [self.removida])
        self.assertEqual([(x['tabela'], x['coluna']) for x in p['colunas_removidas_recusadas']],
                         [('F_FUNCIONARIO', 'CODCARGO')])               # usada por FK: não sai
        self.assertEqual(_q(self.db, 'SELECT COUNT(*) FROM colunas'), antes)

    def test_aplicar_muda_so_a_lista(self):
        rel = _q(self.db, 'SELECT * FROM relacionamentos ORDER BY rowid')
        aplicar(self.db, self.dic, destino_backup=os.path.join(self._tmp.name, 'bk'))
        self.assertEqual(_q(self.db, "SELECT descricao FROM tabelas WHERE tabela = 'F_AUX001'"), [(None,)])
        self.assertEqual(_q(self.db, "SELECT tem_dados FROM tabelas WHERE tabela = 'F_CARGO'"), [(0,)])
        self.assertEqual(_q(self.db, "SELECT COUNT(*) FROM tabelas WHERE tabela = 'F_NOVA'"), [(1,)])
        self.assertEqual(_q(self.db, "SELECT COUNT(*) FROM colunas WHERE tabela = ? AND coluna = ?"
                            .replace('?', "'%s'") % self.removida), [(0,)])
        self.assertEqual(_q(self.db, "SELECT COUNT(*) FROM colunas WHERE tabela = 'F_FUNCIONARIO' "
                                     "AND coluna = 'CODCARGO'"), [(1,)])
        self.assertEqual(_q(self.db, 'SELECT * FROM relacionamentos ORDER BY rowid'), rel)
        self.assertEqual(_q(self.db, 'SELECT * FROM sistemas'), self.sistemas)
        self.assertEqual([s for s in os.listdir(self._tmp.name) if s.endswith(('-journal', '-wal'))], [])


if __name__ == '__main__':
    unittest.main()
