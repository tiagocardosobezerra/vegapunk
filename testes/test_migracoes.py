"""Migrações numeradas da Punk Records (tabela `meta`), sempre contra a
fixture fictícia (casos/fixture_schema.py) numa pasta temporária: nunca toca no banco
real."""

import hashlib
import os
import sqlite3
import tempfile
import unittest

import _comum  # noqa: F401  (põe a raiz da skill e satelites/ no sys.path)
from punk_records import migracoes
from casos.fixture_schema import gerar_fixture_db


def _ler(caminho):
    with open(caminho, 'rb') as f:
        return f.read()


# Colunas que existiam antes de qualquer migração: a migração não pode mudá-las.
_COLUNAS_ORIGINAIS = {
    'tabelas': 'tabela, descricao, score_relevancia, ranking, tabelas_filhas, tabelas_pais, conexoes_totais, tem_dados',
    'colunas': 'tabela, coluna, descricao',
    'relacionamentos': 'tabela_filha, campo_filho, tabela_mae, campo_mae',
    'sistemas': 'codigo_sistema, nome_sistema, descricao',
    'sinonimos': 'termo, sinonimo',
}


def _conteudo(db):
    """Hash das colunas originais das 5 tabelas, para provar que a migração não mexe nelas."""
    conn = sqlite3.connect(db)
    try:
        h = hashlib.sha256()
        for t, cols in _COLUNAS_ORIGINAIS.items():
            for row in conn.execute(f'SELECT {cols} FROM {t} ORDER BY rowid'):
                h.update(repr(row).encode('utf-8'))
        return h.hexdigest()
    finally:
        conn.close()


class TestMigracoes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, 'punk_records.db')
        gerar_fixture_db(self.db)
        self.backups = os.path.join(self._tmp.name, 'backups')

    def tearDown(self):
        self._tmp.cleanup()

    def test_base_sem_meta_esta_na_versao_zero(self):
        s = migracoes.status(self.db)
        self.assertEqual(s['versao'], 0)
        self.assertEqual(s['pendentes'], [f'{n:03d} {nome}' for n, nome, _ in migracoes.MIGRACOES])
        self.assertEqual(s['pendentes'][:4], ['001 criar_meta', '002 estrutura_colunas_e_constraints',
                                              '003 ligacao_do_dicionario', '004 camada_mapa'])

    def test_aplicar_cria_meta_preserva_conteudo_e_faz_copia(self):
        antes = _conteudo(self.db)
        r = migracoes.aplicar(self.db, destino_backup=self.backups)
        self.assertEqual((r['antes'], r['depois']), (0, len(migracoes.MIGRACOES)))
        self.assertEqual(r['aplicadas'], [f'{n:03d} {nome}' for n, nome, _ in migracoes.MIGRACOES])
        self.assertTrue(os.path.exists(r['copia']))
        self.assertEqual(_conteudo(r['copia']), antes)
        self.assertEqual(_conteudo(self.db), antes)
        s = migracoes.status(self.db)
        self.assertEqual(s['versao'], len(migracoes.MIGRACOES))
        self.assertEqual(s['pendentes'], [])
        for n in ('001', '002', '003', '004'):
            self.assertIn(f'migracao:{n}', s['aplicadas'])
        self.assertEqual(migracoes._sobras(self.db), [])

    def test_duas_copias_no_mesmo_segundo_nao_se_sobrescrevem(self):
        a = migracoes.copiar_seguranca(self.db, self.backups)
        b = migracoes.copiar_seguranca(self.db, self.backups)
        c = migracoes.copiar_seguranca(self.db, self.backups)
        self.assertEqual(len({a, b, c}), 3)
        self.assertTrue(all(os.path.exists(x) for x in (a, b, c)))

    def test_aplicar_de_novo_nao_faz_nada(self):
        migracoes.aplicar(self.db, destino_backup=self.backups)
        r = migracoes.aplicar(self.db, destino_backup=self.backups)
        self.assertEqual(r['aplicadas'], [])
        self.assertIsNone(r['copia'])
        self.assertEqual(len(os.listdir(self.backups)), 1)

    def test_falha_restaura_a_copia(self):
        antes_bytes = _ler(self.db)
        quebradas = migracoes.MIGRACOES + [(3, 'quebrada', ['CREATE TABLE x (a)', 'SELECT * FROM nao_existe'])]
        with self.assertRaises(sqlite3.OperationalError):
            migracoes.aplicar(self.db, migracoes=quebradas, destino_backup=self.backups)
        self.assertEqual(_ler(self.db), antes_bytes)
        self.assertEqual(migracoes.status(self.db)['versao'], 0)
        self.assertEqual(migracoes._sobras(self.db), [])

    def test_recusa_base_com_journal_pendente(self):
        open(self.db + '-journal', 'wb').close()
        with self.assertRaises(RuntimeError):
            migracoes.aplicar(self.db, destino_backup=self.backups)


if __name__ == '__main__':
    unittest.main()
