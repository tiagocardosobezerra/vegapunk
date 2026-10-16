"""Bloco 4c: grafo de coocorrência só de fontes limpas (com mínimo de
exemplos distintos), padrões antes de funções na solução e sinônimos com
`uso` na Punk Records. Tudo fictício."""

import json
import os
import shutil
import sqlite3
import tempfile
import unittest

from _comum import FIXTURE_FORMULAS
from casos.fixture_schema import gerar_fixture_db
from dominios import padroes
from dominios.formulas import conhecimento as kb
from dominios.solucao import Camadas
from dominios.formulas.grafo import coocorrencia, vizinhas
from dominios.schema.config import carregar_dominio_do_db
from punk_records import migracoes
from punk_records.sinonimos import aplicar

LERCAMPO = {'nome': 'LERCAMPO', 'contexto': 'BASE', 'descricao': 'Lê um campo do resultado de uma consulta fictícia.',
            'assinaturas': [{'texto': "LERCAMPO('CONSULTA', 'CAMPO')", 'tem_parenteses': True,
                             'argumentos': ["'CONSULTA'", "'CAMPO'"]}],
            'aridades_documentadas': [2],
            'parametros': [{'posicao': 1, 'rotulo_documentado': 'CONSULTA', 'tipo': 'texto'},
                           {'posicao': 2, 'rotulo_documentado': 'CAMPO', 'tipo': 'texto'}],
            'exemplos': [{'codigo': 'ARREDONDE(SOMA2(3, 4), 0)'}, {'codigo': 'SOMA2(1,'}],
            'origens': [{'pacote': 'ficticio'}], 'confianca_extracao': 'alta'}
RECEITAS = [
    {'id': 'r2', 'nome': 'mesma receita em outro pacote', 'formula': '  arredonde(SOMA2(1, 2),   2) '},
    {'id': 'r3', 'nome': 'ano de hoje', 'formula': 'ANODE(HOJE)'},
    {'id': 'r4', 'nome': 'leitura', 'formula': 'SOMA2(LERCAMPO("Q1", "VALOR"), LERCAMPO("Q1", "DATA"))'}]


class TestPadroes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pacotes = os.path.join(cls._tmp.name, 'pacotes')
        shutil.copytree(FIXTURE_FORMULAS, cls.pacotes)
        d = os.path.join(cls.pacotes, 'publico', 'ficticio')
        for nome, extra in (('funcoes.json', [LERCAMPO]), ('receitas.json', RECEITAS)):
            with open(os.path.join(d, nome), encoding='utf-8') as f:
                dados = json.load(f)
            with open(os.path.join(d, nome), 'w', encoding='utf-8') as f:
                json.dump(dados + extra, f, ensure_ascii=False)
        cls.base = kb.carregar(cls.pacotes, somente_publico=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_grafo_conta_exemplos_distintos_e_separa_sugestao(self):
        g = coocorrencia(self.base)
        # receita 001 e r2 são o mesmo texto (conta uma vez); o exemplo da ficha é o 2º
        self.assertEqual(g['conhecimento'][('ARREDONDE', 'SOMA2')], 2)
        self.assertEqual(g['sugestoes'][('ANODE', 'HOJE')], 1)          # abaixo do mínimo
        self.assertNotIn(('ANODE', 'HOJE'), g['conhecimento'])
        self.assertEqual(vizinhas(g, 'SOMA2'), [('ARREDONDE', 2)])
        self.assertEqual(coocorrencia(self.base, minimo=3)['conhecimento'], {})

    def test_promove_quem_coocorre_so_quando_o_primeiro_nao_coocorre(self):
        g = coocorrencia(self.base)
        its = [{'id': '1', 'dominio': 'formulas', 'candidatos': [{'nome': 'SOMA2'}]},
               {'id': '2', 'dominio': 'formulas', 'candidatos': [{'nome': 'HOJE'}, {'nome': 'ARREDONDE'}]}]
        padroes.promover_pelo_grafo(its, g)
        self.assertEqual([c['nome'] for c in its[1]['candidatos']], ['ARREDONDE', 'HOJE'])
        self.assertIn('coocorre com SOMA2', its[1]['candidatos'][0]['prova'])
        self.assertEqual([c['nome'] for c in its[0]['candidatos']], ['SOMA2'])     # o 1º já coocorre
        sozinha = [{'id': '1', 'dominio': 'formulas', 'candidatos': [{'nome': 'HOJE'}, {'nome': 'SOMA2'}]}]
        padroes.promover_pelo_grafo(sozinha, g)
        self.assertEqual(sozinha[0]['candidatos'][0]['nome'], 'HOJE')             # sem outra intenção, nada muda

    def test_padroes_cobrem_duas_intencoes_e_campos_lidos(self):
        its = [{'id': '1', 'dominio': 'formulas', 'candidatos': [{'nome': 'SOMA2'}]},
               {'id': '2', 'dominio': 'formulas', 'candidatos': [{'nome': 'LERCAMPO'}]}]
        ps = padroes.selecionar_padroes(self.base, its)
        self.assertEqual([p['id'] for p in ps], ['r4'])
        self.assertEqual(ps[0]['intencoes_cobertas'], ['1', '2'])
        self.assertEqual(padroes.campos_lidos(self.base, ps[0]['formula'], ['LERCAMPO']), ['VALOR', 'DATA'])


class TestUsoDosSinonimos(unittest.TestCase):
    def test_par_do_essencial_fica_fora_da_busca(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'punk_records.db')
            gerar_fixture_db(db)
            migracoes.aplicar(db, destino_backup=os.path.join(tmp, 'bk'))
            self.assertEqual(aplicar(db, [('sem centavos', 'sem casas decimais')], uso='essencial'), 2)
            conn = sqlite3.connect(db)
            try:
                _m, sinonimos, _n = carregar_dominio_do_db(conn)
            finally:
                conn.close()
            self.assertNotIn('sem centavos', sinonimos)
            cam = Camadas(kb.carregar(FIXTURE_FORMULAS, somente_publico=True), db, instancia=tmp)
            cam.fechar()
            self.assertEqual(cam.sinonimos_essencial['sem centavos'], {'sem casas decimais'})
            with self.assertRaises(ValueError):
                aplicar(db, [('a', 'b')], uso='outro')


if __name__ == '__main__':
    unittest.main()
