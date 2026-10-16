"""Classificação do diff do Atlas contra o golden: campos novos, avisos
novos, mudança de corpus (mesma ordem, só score) e outras mudanças."""

import os
import sys
import unittest

from _comum import SKILL

sys.path.insert(0, os.path.join(SKILL, 'satelites'))
from atlas import classificar_diferencas  # noqa: E402

GOLDEN = {'buscar': {'p': {'resultados': [{'nome': 'A', 'score': 9.5}, {'nome': 'B', 'score': 4.0}],
                           'margem_top1_top2': 0.5, 'avisos': ['x']}}}


def _com(**mudar):
    import copy
    g = copy.deepcopy(GOLDEN)
    r = g['buscar']['p']
    for k, v in mudar.items():
        r[k] = v
    return g


class TestClassificacao(unittest.TestCase):
    def test_so_score_na_mesma_ordem_e_mudanca_de_corpus(self):
        acc = classificar_diferencas(GOLDEN, _com(resultados=[{'nome': 'A', 'score': 9.9}, {'nome': 'B', 'score': 3.1}],
                                                  margem_top1_top2=0.69))
        self.assertEqual((len(acc['mudanca_de_corpus']), acc['outras']), (3, []))

    def test_ordem_trocada_e_outra_mudanca(self):
        acc = classificar_diferencas(GOLDEN, _com(resultados=[{'nome': 'B', 'score': 9.5}, {'nome': 'A', 'score': 4.0}]))
        self.assertEqual(len(acc['outras']), 2)
        self.assertEqual(acc['mudanca_de_corpus'], [])

    def test_campo_e_aviso_novos(self):
        acc = classificar_diferencas(GOLDEN, _com(avisos=['x', 'y'], vizinhas=[]))
        self.assertEqual((len(acc['campos_novos']), len(acc['avisos_novos']), acc['outras']), (1, 1, []))

    def test_valor_que_nao_e_score_continua_outra(self):
        acc = classificar_diferencas(GOLDEN, _com(resultados=[{'nome': 'A', 'score': 9.5}, {'nome': 'B', 'score': '4'}]))
        self.assertEqual(len(acc['outras']), 1)


if __name__ == '__main__':
    unittest.main()
