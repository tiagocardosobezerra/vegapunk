"""Direção das ligações do dicionário provada pelo catálogo (fase 4):
duplicata inversa sai da leitura corrigida, invertida troca filha e mãe,
sem prova nada muda; a linha original fica intacta e as métricas são
recalculadas. Nomes fictícios."""

import os
import sqlite3
import tempfile
import unittest

import _comum  # noqa: F401
from casos.fixture_schema import gerar_fixture_db
from nomi_nomi_no_mi.busca import NomiNomiNoMi
from punk_records import migracoes
from punk_records.direcao import corrigir

_CATALOGO = ('tabela_filha,campo_filho,tabela_mae,campo_mae,constraint,ordem\n'
             'F_FUNCIONARIO,CODCARGO,F_CARGO,CODCARGO,FK_F_FUNCIONARIO_F_CARGO_CODCARGO,1\n'
             'N_UNIDADE,CODEMPRESA,N_EMPRESA,CODEMPRESA,FK_FISICA_FORA_DA_BASE,1\n')


class TestDirecao(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = self._tmp.name
        self.db = os.path.join(t, 'f.db')
        gerar_fixture_db(self.db)
        migracoes.aplicar(self.db, destino_backup=os.path.join(t, 'bk'))
        conn = sqlite3.connect(self.db)
        conn.execute("DELETE FROM relacionamentos WHERE tabela_filha = 'N_UNIDADE' AND tabela_mae = 'N_EMPRESA'")
        conn.executemany('INSERT INTO relacionamentos (tabela_filha, campo_filho, tabela_mae, campo_mae, ligacao) '
                         'VALUES (?, ?, ?, ?, ?)', [
                             ('F_CARGO', 'CODCARGO', 'F_FUNCIONARIO', 'CODCARGO', 901),     # duplicata inversa
                             ('N_EMPRESA', 'CODEMPRESA', 'N_UNIDADE', 'CODEMPRESA', 902),   # invertida
                             ('F_CARGO', 'CODCARGO', 'N_EMPRESA', 'CODEMPRESA', 903)])      # sem prova
        conn.commit()
        conn.close()
        self.dir = os.path.join(t, 'extracao')
        os.makedirs(self.dir)
        with open(os.path.join(self.dir, 'relacionamentos.csv'), 'w', encoding='utf-8') as f:
            f.write(_CATALOGO)

    def tearDown(self):
        self._tmp.cleanup()

    def _q(self, sql):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_marca_corrige_e_preserva_a_linha_original(self):
        r = corrigir(self.dir, self.db, os.path.join(self._tmp.name, 'bk'))
        self.assertEqual(r['ligacoes'], {'duplicata_inversa': 1, 'invertida': 1, 'sem_prova_de_inversao': 1})
        self.assertEqual(self._q('SELECT direcao, direcao_prova FROM relacionamentos WHERE ligacao = 901'),
                         [('duplicata_inversa', 'FK_F_FUNCIONARIO_F_CARGO_CODCARGO')])
        self.assertEqual(self._q('SELECT tabela_filha, tabela_mae FROM relacionamentos WHERE ligacao = 902'),
                         [('N_EMPRESA', 'N_UNIDADE')])                       # original intacta
        self.assertEqual(self._q('SELECT tabela_filha, tabela_mae FROM relacionamentos_corrigidos WHERE ligacao = 902'),
                         [('N_UNIDADE', 'N_EMPRESA')])                       # leitura corrigida
        self.assertEqual(self._q('SELECT COUNT(*) FROM relacionamentos_corrigidos WHERE ligacao = 901'), [(0,)])
        self.assertEqual(self._q('SELECT direcao FROM relacionamentos WHERE ligacao = 903'), [(None,)])
        self.assertTrue(os.path.exists(r['copia']))
        self.assertEqual([s for s in os.listdir(self._tmp.name) if s.endswith(('-journal', '-wal'))], [])

    def test_idempotente_e_metricas_pelos_pares_corrigidos(self):
        corrigir(self.dir, self.db, os.path.join(self._tmp.name, 'bk'))
        uma = self._q('SELECT tabela, score_relevancia, ranking, tabelas_filhas, tabelas_pais FROM tabelas ORDER BY 1')
        r = corrigir(self.dir, self.db, os.path.join(self._tmp.name, 'bk'))
        self.assertEqual(r['tabelas_com_metrica_alterada'], 0)
        self.assertEqual(self._q('SELECT tabela, score_relevancia, ranking, tabelas_filhas, tabelas_pais '
                                 'FROM tabelas ORDER BY 1'), uma)
        pais = dict(self._q("SELECT tabela, tabelas_pais FROM tabelas WHERE tabela IN ('N_UNIDADE', 'N_EMPRESA')"))
        self.assertEqual(pais['N_UNIDADE'], 1)          # a mãe certa de N_UNIDADE é N_EMPRESA

    def test_detalhar_le_a_direcao_corrigida(self):
        corrigir(self.dir, self.db, os.path.join(self._tmp.name, 'bk'))
        m = NomiNomiNoMi(self.db)
        try:
            linhas = m._linhas_entre('N_UNIDADE', 'N_EMPRESA')
            self.assertEqual({(x['tabela_filha'], x['tabela_mae']) for x in linhas}, {('N_UNIDADE', 'N_EMPRESA')})
            self.assertEqual(len(m._linhas_entre('F_FUNCIONARIO', 'F_CARGO')), 1)   # a duplicata inversa saiu
        finally:
            m.fechar()

    def test_base_antes_da_007_e_recusada(self):
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE meta SET valor = '6' WHERE chave = 'versao_schema'")
        conn.commit()
        conn.close()
        with self.assertRaises(RuntimeError):
            corrigir(self.dir, self.db, os.path.join(self._tmp.name, 'bk'))


if __name__ == '__main__':
    unittest.main()
