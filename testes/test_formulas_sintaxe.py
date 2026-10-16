"""Parser genérico guiado por dialeto — com dois dialetos FICTÍCIOS distintos
(inglês e português), provando que nada é fixo no código. Casos de sintaxe
de dialetos reais ficam no próprio pacote (casos/validacao.json)."""

import os
import unittest

from _comum import _ler_json, FIXTURE_FORMULAS, TESTES, SKILL
from dominios.formulas.sintaxe import analisar, percorrer

D_FIC = _ler_json(os.path.join(FIXTURE_FORMULAS, 'publico', 'ficticio', 'dialeto.json'))
D_PT = _ler_json(os.path.join(SKILL, 'casos', 'fixtures', 'dialeto_pt_ficticio.json'))


def tipos(ast):
    return [n['tipo'] for n in percorrer(ast)]


class TestDialetoFicticio(unittest.TestCase):
    def test_condicional_com_palavras_do_dialeto(self):
        ast, erros, _ = analisar('IF SOMA2(1, 2) > 2 THEN 1 ELSE 0 END', D_FIC)
        self.assertEqual(erros, [])
        self.assertIn('condicional', tipos(ast))

    def test_palavras_de_outro_dialeto_nao_sao_estrutura(self):
        _, erros, _ = analisar('SE X > 1 ENTAO 1 FIMSE', D_FIC)
        self.assertTrue(erros)

    def test_comentario_e_texto_do_dialeto(self):
        ast, erros, _ = analisar('{comentário} ANODE("01/01/2020")', D_FIC)
        self.assertEqual(erros, [])
        self.assertEqual([n for n in percorrer(ast) if n['tipo'] == 'texto'][0]['valor'], '01/01/2020')

    def test_aspas_simples_nao_sao_texto_no_ficticio(self):
        _, erros, _ = analisar("ANODE('01/01/2020')", D_FIC)
        self.assertEqual(erros[0]['codigo'], 'lexico')

    def test_repeticao_e_declaracao(self):
        ast, erros, _ = analisar('VAR I; LET(I, 0); LOOP LET(I, I + 1) UNTIL I == 3; I', D_FIC)
        self.assertEqual(erros, [])
        self.assertIn('repeticao', tipos(ast))
        self.assertIn('declaracao', tipos(ast))

    def test_caixa_insensivel(self):
        _, erros, _ = analisar('if 1 > 0 then soma2(1,1) end', D_FIC)
        self.assertEqual(erros, [])


class TestDialetoPortugues(unittest.TestCase):
    def test_estruturas_aninhadas(self):
        f = ("DECL A, B; SETVAR(A, 1); SETVAR(B, 0); REPITA SE X(A) = 1 ENTAO SE Y(A) <= 18 ENTAO "
             "SETVAR(B, B + 1) SENAO 0 FIMSE FIMSE; SETVAR(A, A + 1) ATE A = 10; B")
        _, erros, _ = analisar(f, D_PT)
        self.assertEqual(erros, [])

    def test_decl_com_parenteses(self):
        self.assertEqual(analisar('DECL (T); SETVAR(T, 1); T', D_PT)[1], [])

    def test_fimse_faltando(self):
        _, erros, _ = analisar('SE V > 1\nENTAO 1\nSENAO 0', D_PT)
        self.assertIn('FIMSE', erros[0]['mensagem'])

    def test_parentese_desbalanceado(self):
        self.assertIn(')', analisar('F(V * 2, 2', D_PT)[1][0]['mensagem'])

    def test_aspas_tipograficas_rejeitadas(self):
        self.assertEqual(analisar('F(‘01’)', D_PT)[1][0]['codigo'], 'lexico')

    def test_texto_e_comentario_sem_fechamento(self):
        self.assertIn('sem fechamento', analisar("F('01)", D_PT)[1][0]['mensagem'])
        self.assertIn('comentário', analisar('/* x V', D_PT)[1][0]['mensagem'])

    def test_booleano_documentado_como_funcao(self):
        ast, erros, _ = analisar('VERDADE()', D_PT)
        self.assertEqual((erros, tipos(ast)[-1]), ([], 'chamada'))

    def test_operador_logico(self):
        self.assertEqual(analisar('SE V > 1 E V < 9 ENTAO 1 FIMSE', D_PT)[1], [])
        self.assertTrue(analisar('SE V > 1 AND V < 9 ENTAO 1 FIMSE', D_PT)[1])


if __name__ == '__main__':
    unittest.main()
