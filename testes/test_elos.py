"""Elos entre funções (auditoria de 27/10/2026): o aceite rotula pelo que a
fórmula aceita usa, os casos aceitos entram na avaliação de soluções, o
`confirmar` do schema aceita várias tabelas e a calibração as lê, a Stella
despacha o Memory Card. Tudo com a fixture fictícia e pastas temporárias."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from _comum import FIXTURE_FORMULAS, SCRIPTS, SKILL
from casos.fixture_schema import gerar_fixture_db
from dominios import aceite

_ENV = dict(os.environ, PYTHONIOENCODING='utf-8')


def _rodar(*args, env=None):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, encoding='utf-8',
                          env=env or _ENV)


class TestEsperadoDoAceite(unittest.TestCase):
    def _reg(self, formula, cand1, cand2=('ARREDONDA',)):
        return {'formula': formula, 'intencoes': [
            {'id': '1', 'dominio': 'formulas', 'status': 'resolvida', 'candidatos': list(cand1)},
            {'id': '2', 'dominio': 'cadastro', 'status': 'resolvida', 'candidatos': ['evento'], 'funcao': 'C'},
            {'id': '3', 'dominio': 'formulas', 'status': 'resolvida', 'candidatos': list(cand2)}]}

    def test_esperado_e_a_funcao_da_formula_nao_o_primeiro_da_busca(self):
        e = aceite._esperados(self._reg('ARREDONDA(C(<<CÓDIGO DO EVENTO>>), 2)', ['EXISTEEP', 'C']))
        self.assertEqual(e, {'1': ['C'], '3': ['ARREDONDA']})

    def test_sem_candidato_na_formula_fica_com_a_funcao_que_sobra(self):
        e = aceite._esperados(self._reg('ARREDONDA(C(<<CÓDIGO DO EVENTO>>), 2)', ['EXISTEEP', 'N']))
        self.assertEqual(e['1'], ['C'])

    def test_ambiguo_fica_sem_rotulo(self):
        e = aceite._esperados(self._reg('SOMA(C(<<A>>), D(<<B>>))', ['X'], ['Y']))
        self.assertEqual((e['1'], e['3']), (None, None))


class _ComBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, 'punk_records.db')
        gerar_fixture_db(self.db)

    def tearDown(self):
        self._tmp.cleanup()


class TestCasosAceitosNaAvaliacao(_ComBase):
    def test_avaliar_solucoes_mede_os_aceitos_junto(self):
        caso = {'id': 'X1', 'pedido': 'somar', 'contexto': 'BASE', 'intencoes': [
            {'id': 'X1.1', 'texto': 'somar dois números', 'dominio': 'formulas', 'esperado': ['SOMA2'],
             'lacuna': False}]}
        with open(os.path.join(self._tmp.name, 'casos_solucao.json'), 'w', encoding='utf-8') as f:
            json.dump({'casos': [caso]}, f)
        with open(os.path.join(self._tmp.name, aceite.ARQUIVO_CASOS), 'w', encoding='utf-8') as f:
            json.dump({'casos': [dict(caso, id='A001')]}, f)
        r = _rodar(os.path.join(SCRIPTS, 'pythagoras.py'), 'avaliar', '--dominio', 'solucoes', '--db', self.db,
                   '--pacotes', FIXTURE_FORMULAS)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('2 casos, casos_solucao.json + 1 aceito(s) pelo usuário', r.stdout)


class TestConfirmarVariasTabelas(_ComBase):
    def test_confirmar_grava_todas_e_a_calibracao_le(self):
        r = _rodar(os.path.join(SKILL, 'stella.py'), '--db', self.db, 'confirmar', '--dominio', 'schema',
                   'funcionários por cargo', 'F_FUNCIONARIO', 'F_CARGO')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('F_FUNCIONARIO, F_CARGO', r.stdout)
        from nomi_nomi_no_mi.historico import ler_historico_confirmado
        reg = ler_historico_confirmado(self.db)[-1]
        self.assertEqual((reg['tabela_confirmada'], reg['tabelas_confirmadas']),
                         ('F_FUNCIONARIO', ['F_FUNCIONARIO', 'F_CARGO']))
        import pythagoras
        pythagoras._carregar_schema()
        casos = pythagoras.carregar_casos(self.db)
        self.assertIn(('funcionários por cargo', {'F_FUNCIONARIO', 'F_CARGO'}, 5),
                      [c for cs in casos.values() for c in cs])


class TestStellaCartao(unittest.TestCase):
    def test_cartao_vai_para_o_memory_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(_ENV, VEGAPUNK_EGGHEAD=tmp)
            env.pop('MEMORY_CARD_REPO', None)
            r = _rodar(os.path.join(SKILL, 'stella.py'), 'cartao', 'catalogo', env=env)
        self.assertEqual(r.returncode, 1)
        self.assertIn('nenhum Memory Card configurado', r.stderr)

    def test_pedido_com_a_palavra_cartao_nao_desvia(self):
        import stella
        self.assertEqual(stella._posicao_do_comando(['--db', 'x.db', 'buscar', '--dominio', 'schema', 'cartao']), 2)


class TestApelidoPorEscopo(unittest.TestCase):
    def test_mesmo_apelido_em_duas_ctes_sao_dois_nomes(self):
        from nomi_nomi_no_mi import montagem
        sql = (';WITH A AS (SELECT M.CODCARGO FROM F_CARGO M),\n'
               'B AS (SELECT M.CODEMPRESA FROM N_EMPRESA M)\n'
               'SELECT X.CODCARGO FROM A X')
        r = montagem.referencias(sql)
        self.assertEqual(r['colunas'], ['F_CARGO.CODCARGO', 'N_EMPRESA.CODEMPRESA'])
        self.assertEqual(r['tabelas'], ['F_CARGO', 'N_EMPRESA'])


if __name__ == '__main__':
    unittest.main()
