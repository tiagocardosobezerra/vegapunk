"""Validação, composição e explicação.

Usa só o pacote FICTÍCIO (comportamento do motor, independente de qualquer
fornecedor). A integração com pacotes públicos reais é dirigida por dados:
ver test_pacotes_publicos.py."""

import unittest

from _comum import base_ficticia
from dominios.formulas.validador import validar
from dominios.formulas.compositor import compor, explicar, formatar


def codigos(v):
    return [e['codigo'] for e in v['erros']]


class TestValidadorFicticio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = base_ficticia(somente_publico=True)

    def v(self, f, ctx='MOD1', uso=None):
        return validar(f, self.b, ctx, uso=uso)

    def test_valida(self):
        r = self.v('IF SOMA2(1, 2) > 2 THEN ANODE("01/01/2020") ELSE 0 END')
        self.assertTrue(r['valida'], r['erros'])
        self.assertEqual({u['nome'] for u in r['funcoes_usadas']}, {'SOMA2', 'ANODE'})

    def test_funcao_alucinada(self):
        r = self.v('SOMA3(1, 2)')
        self.assertEqual(codigos(r), ['funcao_inexistente'])
        self.assertIn('SOMA2', r['erros'][0]['sugestoes'])

    def test_fora_do_contexto(self):
        self.assertEqual(codigos(self.v('SALDO_MOD2')), ['fora_do_contexto'])

    def test_aridade(self):
        self.assertEqual(codigos(self.v('SOMA2(1)')), ['aridade'])

    def test_parametro_opcional_documentado(self):
        self.assertTrue(self.v('ARREDONDE(1.5)')['valida'])
        self.assertTrue(self.v('ARREDONDE(1.5, 1)')['valida'])
        self.assertEqual(codigos(self.v('ARREDONDE()')), ['aridade'])

    def test_sem_parenteses(self):
        self.assertTrue(self.v('HOJE')['valida'])
        self.assertEqual(codigos(self.v('HOJE(1)')), ['forma_de_chamada'])
        self.assertEqual(codigos(self.v('SOMA2')), ['aridade'])

    def test_sintaxe_nao_documentada_e_aviso_nao_aprovacao_silenciosa(self):
        r = self.v('SEM_SINTAXE(1, 2, 3)')
        self.assertTrue(r['valida'])
        self.assertIn('sintaxe_nao_documentada', [a['codigo'] for a in r['avisos']])

    def test_tipo_de_literal(self):
        r = self.v('ANODE("ontem")')
        self.assertIn('tipo_argumento', [a['codigo'] for a in r['avisos']])
        r = self.v('SOMA2("1", 2)')
        self.assertIn('tipo_argumento', [a['codigo'] for a in r['avisos']])

    def test_uso_proibido(self):
        self.assertTrue(self.v('VALOR_TABELA("A1")')['valida'])
        self.assertEqual(codigos(self.v('VALOR_TABELA("A1")', uso='selecao')), ['uso_proibido'])

    def test_variavel(self):
        self.assertTrue(self.v('VAR X; LET(X, SOMA2(1, 1)); X')['valida'])
        self.assertIn('variavel_nao_declarada', codigos(self.v('LET(X, 1); X')))

    def test_limite_de_constantes(self):
        self.assertIn('limite_constantes', codigos(self.v('SOMA2(1, SOMA2(2, SOMA2(3, SOMA2(4, SOMA2(5, 6)))))')))

    def test_operador_nao_documentado(self):
        r = self.v('IF 1 > 0 OR 2 > 1 THEN 1 END')
        self.assertFalse(r['valida'])
        self.assertIn('não é operador documentado', r['erros'][0]['mensagem'])


class TestCompositorFicticio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = base_ficticia(somente_publico=True)

    def test_compoe_com_palavras_do_dialeto(self):
        plano = {'se': {'op': '>', 'esq': {'chamar': 'SOMA2', 'args': [{'numero': 1}, {'numero': 2}]},
                        'dir': {'numero': 2}},
                 'entao': {'chamar': 'ANODE', 'args': [{'data': '01/01/2020'}]},
                 'senao': {'numero': 0}}
        r = compor(plano, self.b, 'MOD1')
        self.assertTrue(r['valida'], r['erros'])
        self.assertEqual(r['formula'], 'IF SOMA2(1, 2) > 2 THEN\n  ANODE("01/01/2020")\nELSE\n  0\nEND')
        self.assertTrue(r['explicacao']['passo_a_passo'])

    def test_recusa_funcao_inexistente(self):
        r = compor({'chamar': 'INVENTADA', 'args': []}, self.b, 'MOD1')
        self.assertIsNone(r['formula'])
        self.assertEqual(r['rascunho_rejeitado'], 'INVENTADA()')

    def test_recusa_operador_fora_do_dialeto(self):
        r = compor({'op': 'XOR', 'esq': {'numero': 1}, 'dir': {'numero': 2}}, self.b, 'MOD1')
        self.assertIsNone(r['formula'])
        self.assertEqual(r['erros'][0]['codigo'], 'plano')

    def test_explicacao_rastreia_fonte(self):
        e = explicar('SOMA2(1, 2)', self.b, 'BASE')
        self.assertEqual(e['componentes'][0]['fontes'], ['https://exemplo.invalid/soma2'])


if __name__ == '__main__':
    unittest.main()
