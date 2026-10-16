"""Fase 3d: o detalhar de função mostra a ligação de cada parâmetro de
código e o SQL de apoio (chave completa, nomes validados pelo Shaka; o motor
nunca executa). Sem schema ou sem mapa, nada muda. Nomes fictícios."""

import os
import sys
import tempfile
import unittest

from _comum import SKILL
from casos.fixture_schema import gerar_fixture_db
from dominios.formulas.sql_apoio import validar_sql_de_apoio
from dominios.integracao import enriquecedor_de_detalhe
from punk_records import migracoes
from punk_records.mapa import compilar

sys.path.insert(0, os.path.join(SKILL, 'satelites'))
import shaka  # noqa: E402


def _ficha(nome, rotulo):
    return {'nome': nome, 'contexto': 'BASE', 'camada': 'publico', 'descricao': 'Função fictícia.',
            'assinaturas': [{'texto': f'{nome}("{rotulo}")'}],
            'parametros': [{'posicao': 1, 'rotulo_documentado': rotulo, 'tipo': 'numero'}],
            'origens': [{'pacote': 'ficticio'}]}


class TestDetalharComMapa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls._tmp.name, 'f.db')
        gerar_fixture_db(cls.db)
        migracoes.aplicar(cls.db, destino_backup=os.path.join(cls._tmp.name, 'bk'))
        compilar(os.path.join(SKILL, 'casos', 'mapa_ficticio.json'), cls.db, os.path.join(cls._tmp.name, 'bk'))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_argumento_aponta_para_a_coluna_certa_com_sql_de_apoio(self):
        f = enriquecedor_de_detalhe(self.db)([_ficha('CARGODE', 'CÓDIGO DO CARGO')])[0]
        lg = f['ligacoes_parametros'][0]
        self.assertEqual((lg['ligado'], lg['cadastro'], lg['tabela'], lg['coluna_codigo'], lg['chave']),
                         (True, 'cargo', 'F_CARGO', 'CODCARGO', ['CODCARGO']))
        self.assertEqual(lg['sql_apoio'], 'SELECT CODCARGO, DESCRICAOCARGO FROM F_CARGO ORDER BY CODCARGO')
        self.assertTrue(lg['sql_apoio_validado'])

    def test_funcao_fora_do_cadastro_continua_so_rotulo(self):
        f = enriquecedor_de_detalhe(self.db)([_ficha('OUTRAFUNC', 'CÓDIGO DO CARGO')])[0]
        lg = f['ligacoes_parametros'][0]
        self.assertFalse(lg['ligado'])
        self.assertNotIn('sql_apoio', lg)

    def test_parametro_que_nao_e_codigo_nao_ganha_ligacao(self):
        f = enriquecedor_de_detalhe(self.db)([_ficha('CARGODE', 'DATA')])[0]
        self.assertNotIn('ligacoes_parametros', f)

    def test_texto_do_detalhar_mostra_ligacao_e_sql(self):
        f = enriquecedor_de_detalhe(self.db)([_ficha('CARGODE', 'CÓDIGO DO CARGO')])[0]
        f.update({'confianca_extracao': 'alta', 'tipo_retorno_documentado': 'numero'})
        texto = shaka._texto_detalhe(f)
        self.assertIn('ligado pelo mapa: cadastro cargo -> F_CARGO.CODCARGO', texto)
        self.assertIn('SQL de apoio', texto)
        self.assertIn('o motor não executa', texto)

    def test_papel_divergente_da_ligacao_com_formula_nao_aparece_na_ligacao_do_codigo(self):
        from test_mapa_compilacao import _MAPA, _compilar
        with tempfile.TemporaryDirectory() as tmp:
            db, r = _compilar(tmp, _MAPA)
            self.assertEqual([d['coluna'] for d in r['divergencias']], ['FORMCRIT'])   # o York mostra
            f = enriquecedor_de_detalhe(db)([_ficha('EVT', 'CÓDIGO DO EVENTO')])[0]
            lg = f['ligacoes_parametros'][0]
            self.assertTrue(lg['ligado'])
            self.assertNotIn('avisos', lg)                                            # o código não usa esse papel

    def test_sem_base_ou_sem_mapa_nada_muda(self):
        self.assertIsNone(enriquecedor_de_detalhe(None))
        self.assertIsNone(enriquecedor_de_detalhe(os.path.join(self._tmp.name, 'nao_existe.db')))
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'sem_mapa.db')
            gerar_fixture_db(db)
            self.assertIsNone(enriquecedor_de_detalhe(db))


class TestValidarSqlDeApoio(unittest.TestCase):
    NOMES = {'F_CARGO': {'CODCARGO', 'DESCRICAOCARGO'}}

    def test_valido(self):
        self.assertEqual(validar_sql_de_apoio('SELECT CODCARGO, DESCRICAOCARGO FROM F_CARGO ORDER BY CODCARGO',
                                              self.NOMES), [])

    def test_nome_inventado(self):
        self.assertEqual(validar_sql_de_apoio('SELECT CODCARGO, SALARIO FROM F_CARGO', self.NOMES),
                         ['coluna SALARIO não está na tabela F_CARGO'])
        self.assertEqual(validar_sql_de_apoio('SELECT A FROM X_INVENTADA', self.NOMES),
                         ['tabela X_INVENTADA não está no schema'])

    def test_fora_da_forma(self):
        for sql in ('SELECT * FROM F_CARGO', 'DELETE FROM F_CARGO', 'SELECT CODCARGO FROM F_CARGO WHERE 1 = 1',
                    'SELECT CODCARGO FROM F_CARGO; DROP TABLE F_CARGO'):
            self.assertTrue(validar_sql_de_apoio(sql, self.NOMES), sql)


if __name__ == '__main__':
    unittest.main()
