"""Bloco 4d: tipo de retorno inferido pelo uso (só fontes limpas, evidência
que concorda, mínimo de exemplos distintos) e checagem de tipo em expressão,
sempre como aviso. Tudo fictício."""

import json
import os
import shutil
import tempfile
import unittest

from _comum import FIXTURE_FORMULAS
from dominios.formulas import conhecimento as kb
from dominios.formulas.tipos import inferir
from dominios.formulas.validador import validar

NOMEDE = {'nome': 'NOMEDE', 'contexto': 'BASE', 'descricao': 'Nome fictício de um cadastro.',
          'assinaturas': [{'texto': 'NOMEDE("CODIGO")', 'tem_parenteses': True, 'argumentos': ['"CODIGO"']}],
          'aridades_documentadas': [1],
          'parametros': [{'posicao': 1, 'rotulo_documentado': 'CODIGO', 'tipo': 'texto',
                          'entre_aspas_na_documentacao': True}],
          'exemplos': [{'codigo': 'NOMEDE("01") == "ANA"'}, {'codigo': 'IF NOMEDE("02") == "RUI" THEN 1 END'}],
          'origens': [{'pacote': 'ficticio'}], 'confianca_extracao': 'alta'}
CONTA = {'nome': 'CONTA', 'contexto': 'BASE', 'descricao': 'Contagem fictícia.', 'assinaturas': [{'texto': 'CONTA'}],
         'aridades_documentadas': [0], 'parametros': [],
         'exemplos': [{'codigo': 'CONTA + 1'}, {'codigo': 'CONTA == "X"'}], 'origens': [{'pacote': 'ficticio'}],
         'confianca_extracao': 'alta'}
UMA = {'nome': 'UMAVEZ', 'contexto': 'BASE', 'descricao': 'Só um exemplo.', 'assinaturas': [{'texto': 'UMAVEZ'}],
       'aridades_documentadas': [0], 'parametros': [], 'exemplos': [{'codigo': 'UMAVEZ * 2'}],
       'origens': [{'pacote': 'ficticio'}], 'confianca_extracao': 'alta'}


class TestTipos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        pac = os.path.join(cls._tmp.name, 'pacotes')
        shutil.copytree(FIXTURE_FORMULAS, pac)
        arq = os.path.join(pac, 'publico', 'ficticio', 'funcoes.json')
        with open(arq, encoding='utf-8') as f:
            fs = json.load(f)
        with open(arq, 'w', encoding='utf-8') as f:
            json.dump(fs + [NOMEDE, CONTA, UMA], f, ensure_ascii=False)
        cls.base = kb.carregar(pac, somente_publico=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_inferido_so_com_evidencia_que_concorda_e_minimo(self):
        r = inferir(self.base)
        self.assertEqual(r['inferidos']['NOMEDE']['tipo'], 'texto')
        self.assertEqual(r['inferidos']['NOMEDE']['ocorrencias'], 2)
        self.assertEqual(r['sugestoes']['CONTA']['motivo'], 'evidência em conflito')
        self.assertIn('abaixo do mínimo', r['sugestoes']['UMAVEZ']['motivo'])
        f = self.base.por_nome['NOMEDE'][0]
        self.assertEqual(f['tipo_retorno_inferido'], {'tipo': 'texto', 'evidencia': 'inferido_de_uso', 'ocorrencias': 2})
        self.assertEqual(f['tipo_retorno'], 'nao_documentado')          # o documentado não muda
        self.assertNotIn('tipo_retorno_inferido', self.base.por_nome['CONTA'][0])

    def test_documentado_vence_a_inferencia(self):
        self.assertNotIn('HOJE', inferir(self.base)['inferidos'])
        self.assertNotIn('tipo_retorno_inferido', self.base.por_nome['HOJE'][0])

    def test_tipo_em_expressao_e_so_aviso(self):
        v = validar('SOMA2(NOMEDE("01"), 1)', self.base, 'BASE')
        self.assertTrue(v['valida'])
        av = [a for a in v['avisos'] if a['codigo'] == 'tipo_expressao']
        self.assertEqual(len(av), 1)
        self.assertIn('inferido pelo uso em 2 exemplo(s)', av[0]['mensagem'])
        self.assertEqual([a for a in validar('SOMA2(SOMA2(1, 2), 1)', self.base, 'BASE')['avisos']
                          if a['codigo'] == 'tipo_expressao'], [])


if __name__ == '__main__':
    unittest.main()
