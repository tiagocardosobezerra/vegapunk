"""Cobertura de intenções (fase 4): o avaliador com um motor falso e os
casos fictícios públicos."""

import json
import os
import unittest

from _comum import SKILL
from dominios.cobertura import avaliar


class MotorFalso:
    def __init__(self, formulas=None, schema=None, ligacoes=None):
        self._f, self._s, self._l = formulas or {}, schema or {}, ligacoes or {}

    def formulas(self, texto, contexto, essencial=None):
        return self._f.get(texto, [])

    def schema(self, texto):
        return self._s.get(texto, [])

    def ligacao(self, funcao, contexto, posicao=None):
        return self._l.get((funcao, posicao)) or self._l.get((funcao, None))


CASOS = [{'id': 'X1', 'contexto': 'C', 'nivel': 2, 'intencoes': [
    {'id': 'X1.1', 'texto': 'somar', 'dominio': 'formulas', 'esperado': ['SOMA'], 'lacuna': False},
    {'id': 'X1.2', 'texto': 'cargos', 'dominio': 'schema', 'esperado': ['T_CARGO'], 'lacuna': False},
    {'id': 'X1.3', 'texto': 'código', 'dominio': 'cadastro', 'funcao': 'F', 'posicao': 2, 'esperado': ['cargo'],
     'lacuna': False},
    {'id': 'X1.4', 'texto': 'enviar e-mail', 'dominio': 'formulas', 'esperado': [], 'lacuna': True}]}]


class TestCobertura(unittest.TestCase):
    def test_media_por_caso_e_lacuna_so_com_resposta_vazia(self):
        m = MotorFalso({'somar': ['A', 'B', 'SOMA', 'D'], 'enviar e-mail': []}, {'cargos': ['T_CARGO']},
                       {('F', 1): 'evento', ('F', 2): 'cargo'})
        r = avaliar(CASOS, m)
        self.assertEqual(r['cobertura'], 1.0)
        m = MotorFalso({'somar': ['A', 'B', 'C', 'SOMA'], 'enviar e-mail': ['X']}, {}, {('F', 1): 'evento'})
        r = avaliar(CASOS, m)
        self.assertEqual(r['cobertura'], 0.0)                 # fora do top-3, lacuna com resposta, posição errada

    def test_proibido_no_top3_e_proibido_ligado(self):
        casos = [{'id': 'Y', 'contexto': 'C', 'nivel': 3, 'intencoes': [
            {'id': 'Y.1', 'texto': 'avançar', 'dominio': 'formulas', 'esperado': ['BOA'], 'lacuna': False,
             'proibido_no_top3': ['RUIM']},
            {'id': 'Y.2', 'texto': 'código', 'dominio': 'cadastro', 'funcao': 'EXEC', 'esperado': ['consulta'],
             'lacuna': False, 'proibido_ligado': {'RUIM': 'consulta'}}]}]
        m = MotorFalso({'avançar': ['BOA', 'RUIM']}, {}, {('EXEC', None): 'consulta', ('RUIM', None): 'consulta'})
        self.assertEqual(avaliar(casos, m)['cobertura'], 0.0)

    def test_casos_ficticios_publicos_sao_validos(self):
        with open(os.path.join(SKILL, 'casos', 'casos_solucao_ficticios.json'), encoding='utf-8') as f:
            casos = json.load(f)['casos']
        self.assertEqual(len(casos), 8)
        for c in casos:
            for it in c['intencoes']:
                self.assertIn(it['dominio'], ('formulas', 'schema', 'cadastro'))
                self.assertTrue(it['esperado'] or it['lacuna'], it['id'])


if __name__ == '__main__':
    unittest.main()
