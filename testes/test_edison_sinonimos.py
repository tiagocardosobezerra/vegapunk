"""Edison: os candidatos a sinônimo saem separados entre variação/erro de
digitação e palavras diferentes parecidas, com os deslizes primeiro."""

import os
import sqlite3
import tempfile
import unittest

from _comum import SKILL  # noqa: F401  (põe a skill no sys.path)
from edison import TIPO_DIGITACAO, TIPO_PALAVRAS, classificar_par, sugerir_sinonimos


class TestClassificarPar(unittest.TestCase):
    def test_um_comeca_com_o_outro_e_variacao(self):
        self.assertEqual(classificar_par('calcula', 7, 'calcular', 11), TIPO_DIGITACAO)
        self.assertEqual(classificar_par('qzcodin', 150, 'qzcodins', 10), TIPO_DIGITACAO)

    def test_letra_somada_no_inicio_e_outra_palavra(self):
        self.assertEqual(classificar_par('emissao', 20, 'demissao', 37), TIPO_PALAVRAS)
        self.assertEqual(classificar_par('revisao', 5, 'previsao', 3), TIPO_PALAVRAS)

    def test_duas_palavras_frequentes_sao_palavras_diferentes(self):
        self.assertEqual(classificar_par('contato', 8, 'contrato', 23), TIPO_PALAVRAS)

    def test_um_lado_raro_e_provavel_deslize(self):
        self.assertEqual(classificar_par('hieraquia', 2, 'hierarquia', 82), TIPO_DIGITACAO)


class TestOrdem(unittest.TestCase):
    def test_deslizes_vem_antes_das_palavras_diferentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'b.db')
            c = sqlite3.connect(db)
            c.execute('CREATE TABLE colunas (tabela TEXT, coluna TEXT, descricao TEXT)')
            linhas = ['qzhierarquia'] * 9 + ['qzhieraquia'] * 2 + ['qzcontato'] * 8 + ['qzcontrato'] * 8
            c.executemany('INSERT INTO colunas VALUES (?, ?, ?)', [('T', f'C{i}', d) for i, d in enumerate(linhas)])
            c.commit()
            c.close()
            tipos = [x['tipo'] for x in sugerir_sinonimos(db)]
        self.assertEqual(tipos, sorted(tipos, key=lambda t: t != TIPO_DIGITACAO))
        self.assertIn(TIPO_PALAVRAS, tipos)
        self.assertIn(TIPO_DIGITACAO, tipos)


if __name__ == '__main__':
    unittest.main()
