"""Termo essencial da intenção (fase 4): candidato só é aceito se o texto
documentado contém o essencial ou um sinônimo cadastrado; sem nenhum, lacuna."""

import json
import os
import tempfile
import unittest

import _comum  # noqa: F401
from dominios.formulas.essencial import atende, carregar_sinonimos, filtrar, juntar

ENVIA = {'nome': 'ENVIAMSG', 'descricao': 'Envia um e-mail ao gestor.', 'assinaturas': [{'texto': 'ENVIAMSG(TEXTO)'}]}
LOG = {'nome': 'ESCREVELOG', 'descricao': 'Escreve uma mensagem no log.'}
EXCL = {'nome': 'LIQPROV', 'descricao': 'Deverá ser utilizada exclusivamente no processo de provisão.'}


class TestEssencial(unittest.TestCase):
    def test_aceita_quem_documenta_o_essencial(self):
        self.assertTrue(atende(ENVIA, 'e-mail'))
        self.assertTrue(atende({'descricao': 'manda email'}, 'e-mail'))     # "e-mail" também casa com "email"
        self.assertFalse(atende(LOG, 'e-mail'))

    def test_frase_inteira_nunca_radical_solto(self):
        self.assertFalse(atende(EXCL, 'excluir registro'))

    def test_sinonimo_cadastrado_conta(self):
        self.assertTrue(atende(LOG, 'registrar ocorrencia', {'registrar ocorrencia': {'escreve uma mensagem'}}))

    def test_sem_candidato_vira_lacuna_com_motivo(self):
        aceitas, lacuna = filtrar([LOG, EXCL], 'e-mail')
        self.assertEqual(aceitas, [])
        self.assertEqual(lacuna, 'nenhuma função documentada faz "e-mail"')
        self.assertEqual(filtrar([LOG], None), ([LOG], None))

    def test_texto_original_conta(self):
        f = {'nome': 'EXTRA', 'descricao': 'Extras autorizadas.', 'texto_original': ['Retorna as horas extras do dia.']}
        self.assertTrue(atende(f, 'horas extras'))
        self.assertTrue(atende(dict(f, texto_original='horas extras'), 'horas extras'))

    def test_lista_propria_da_instancia(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(carregar_sinonimos(d), {})
            with open(os.path.join(d, 'sinonimos_essencial.json'), 'w', encoding='utf-8') as f:
                json.dump({'_nota': 'x', 'Sem Centavos': ['sem casas decimais']}, f)
            s = carregar_sinonimos(d)
        self.assertEqual(s, {'sem centavos': {'sem casas decimais'}})
        self.assertTrue(atende({'descricao': 'Arredonda sem casas decimais.'}, 'sem centavos', juntar({}, s)))


if __name__ == '__main__':
    unittest.main()
