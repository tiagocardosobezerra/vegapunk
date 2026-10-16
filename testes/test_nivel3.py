"""Bloco 4e: nível 3 (fórmula que executa consulta). Regras do Shaka vindas do
dialeto, escada (menor solução), consulta nova com SQL e instrução de
cadastro manual, lacuna por capacidade declarada e a contagem do avaliador
(nivel_maximo, consulta_nova). Tudo fictício."""

import os
import tempfile
import unittest

from _comum import FIXTURE_FORMULAS, SKILL
from casos.fixture_schema import gerar_fixture_db
from dominios import solucao
from dominios.cobertura import avaliar
from dominios.formulas import conhecimento as kb
from dominios.formulas.validador import validar
from punk_records import migracoes
from punk_records.mapa import compilar

EXTRA = os.path.join(SKILL, 'casos', 'fixtures', 'formulas_consulta', 'ficticio-consulta')
LACO = ('VAR V; LET(V, 0); IF EXECUTA("Q1") == TRUE THEN LOOP LET(V, CAMPO("Q1", "DIAS")) '
        'UNTIL PROXIMO("Q1") == FALSE END; V')


class TestNivel3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        t = cls._tmp.name
        cls.db = os.path.join(t, 'f.db')
        gerar_fixture_db(cls.db)
        migracoes.aplicar(cls.db, destino_backup=os.path.join(t, 'bk'))
        compilar(os.path.join(SKILL, 'casos', 'mapa_ficticio.json'), cls.db, os.path.join(t, 'bk'))
        cls.base = kb.carregar(FIXTURE_FORMULAS, extras=[EXTRA])
        cls.cam = solucao.Camadas(cls.base, cls.db, instancia=t)

    @classmethod
    def tearDownClass(cls):
        cls.cam.fechar()
        cls._tmp.cleanup()

    def _cod(self, texto, **k):
        return [e['codigo'] for e in validar(texto, self.base, 'BASE', **k)['erros']]

    def test_regras_do_shaka(self):
        v = validar(LACO, self.base, 'BASE')
        self.assertTrue(v['valida'], v['erros'])
        self.assertEqual(v['consulta'], {'campos_lidos': ['DIAS'], 'consultas': ['Q1']})
        self.assertIn('campos_da_consulta_cadastrada', [a['codigo'] for a in v['avisos']])   # aviso, não pergunta
        self.assertEqual(self._cod('CAMPO("Q1", "DIAS")'), ['leitura_sem_execucao'])
        self.assertEqual(self._cod('EXECUTA("Q1"); CAMPO("Q2", "DIAS")'), ['leitura_sem_execucao'])
        self.assertEqual(self._cod(LACO, campos_consulta=['OUTRO']), ['campo_fora_do_select'])
        av = [a['codigo'] for a in validar('EXECUTA("Q1"); PROXIMO("Q1")', self.base, 'BASE')['avisos']]
        self.assertIn('avanco_fora_da_saida_do_laco', av)
        self.assertNotIn('consulta', validar('SOMA2(1, 2)', self.base, 'BASE'))           # sem consulta, nada muda

    def test_consulta_nova_com_sql_modelo_e_instrucao(self):
        s = solucao.solucionar({'pedido': 'percorrer o saldo de férias por período', 'contexto': 'BASE',
                                'intencoes': [
                                    {'id': '1', 'texto': 'saldo de férias por período', 'dominio': 'schema'},
                                    {'id': '2', 'texto': 'executar a consulta cadastrada', 'dominio': 'formulas'},
                                    {'id': '3', 'texto': 'ler um campo da consulta', 'dominio': 'formulas'}]}, self.cam)
        self.assertEqual(s['nivel'], 3)
        b = s['nivel_3']['consulta_nova']
        self.assertTrue(b['sql'].startswith('SELECT '))
        self.assertTrue(b['modelo']['valida'], b['modelo'])
        self.assertFalse(b['modelo']['pronta_para_cadastrar'])
        self.assertIn('<<CÓDIGO DA CONSULTA NOVA>>', b['modelo']['formula'])
        self.assertIn('não grava no sistema de origem', b['instrucao'])
        self.assertFalse(s['nivel_3']['parametros_na_chamada']['valor'])

    def _nova(self, texto_schema):
        return solucao.solucionar({'pedido': 'percorrer', 'contexto': 'BASE', 'intencoes': [
            {'id': '1', 'texto': texto_schema, 'dominio': 'schema'},
            {'id': '2', 'texto': 'executar a consulta cadastrada', 'dominio': 'formulas'},
            {'id': '3', 'texto': 'ler um campo da consulta', 'dominio': 'formulas'}]}, self.cam)['nivel_3']['consulta_nova']

    def test_tabela_so_da_busca_sai_marcada_com_alternativas_e_nao_pronta(self):
        b = self._nova('saldo de férias por período')
        t = b['tabelas_sem_prova'][0]
        self.assertEqual(t['prova'], 'escolhida pela busca, sem prova')
        self.assertTrue(1 <= len(t['alternativas']))
        self.assertFalse(b['pronta'])
        self.assertEqual(b['motivo_nao_pronta'], 'NÃO está pronta: confirme a tabela antes de cadastrar a consulta')

    def test_tabela_provada_pelo_mapa_nao_e_marcada(self):
        b = self._nova('cadastro de cargos')
        self.assertNotIn('tabelas_sem_prova', b)
        self.assertTrue(b['pronta'])

    def test_escada_tira_consulta_de_intencao_que_uma_funcao_resolve(self):
        s = solucao.solucionar({'pedido': 'x', 'contexto': 'MOD1', 'intencoes': [
            {'id': '1', 'texto': 'valor de uma tabela de cálculo pelo código', 'dominio': 'formulas'}]}, self.cam)
        nomes = [c['nome'] for c in s['intencoes'][0]['candidatos']]
        self.assertEqual(nomes[0], 'VALOR_TABELA')
        self.assertFalse({'EXECUTA', 'CAMPO', 'PROXIMO'} & set(nomes))
        self.assertEqual(s['nivel'], 1)

    def test_lacuna_por_capacidade_declarada(self):
        s = solucao.solucionar({'pedido': 'x', 'contexto': 'BASE', 'intencoes': [
            {'id': '1', 'texto': 'passar um parâmetro à consulta', 'dominio': 'formulas',
             'capacidade': 'parametros_na_chamada'}]}, self.cam)
        self.assertEqual(s['intencoes'][0]['status'], 'lacuna')
        self.assertIn('parametros_na_chamada', s['intencoes'][0]['lacuna'])

    def test_avaliador_conta_nivel_maximo_e_consulta_nova(self):
        casos = [{'id': 'E', 'contexto': 'MOD1', 'nivel_maximo': 1, 'intencoes': [
            {'id': 'E.1', 'texto': 'valor de uma tabela de cálculo pelo código', 'dominio': 'formulas',
             'esperado': ['VALOR_TABELA'], 'lacuna': False}]},
                 {'id': 'N', 'contexto': 'BASE', 'nivel_maximo': 1, 'intencoes': [
                     {'id': 'N.1', 'texto': 'executar a consulta cadastrada', 'dominio': 'formulas',
                      'esperado': ['EXECUTA'], 'lacuna': False}]}]
        r = avaliar(casos, solucao.MotorDeCobertura(self.cam))
        res = {i['id']: i['acertou'] for c in r['casos'] for i in c['intencoes']}
        self.assertTrue(res['E.nivel'])
        self.assertFalse(res['N.nivel'])               # subiu para o nível 3: erro da escada
        self.assertEqual(r['por_dominio']['nivel'], {'acertos': 1, 'intencoes': 2})


if __name__ == '__main__':
    unittest.main()
