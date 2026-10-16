"""Stella orquestradora (fase 4, bloco 4b): contrato de intenções, saída
agrupada por intenção com lacunas explícitas, prova pelo mapa no schema,
argumento marcado e registro da candidata. Tudo fictício (fixture)."""

import json
import os
import shutil
import tempfile
import unittest

from _comum import FIXTURE_FORMULAS, SKILL
from casos.fixture_schema import gerar_fixture_db
from dominios import solucao
from dominios.formulas import conhecimento as kb
from dominios.formulas.compositor import compor
from dominios.formulas.sintaxe import Dialeto, analisar, marcadores
from punk_records import migracoes
from punk_records.mapa import compilar

CARGODE = {'nome': 'CARGODE', 'contexto': 'BASE', 'descricao': 'Salário base do cargo pelo código do cargo.',
           'assinaturas': [{'texto': 'CARGODE("CÓDIGO DO CARGO")', 'tem_parenteses': True,
                            'argumentos': ['"CÓDIGO DO CARGO"']}],
           'aridades_documentadas': [1], 'tipo_retorno': 'numero',
           'parametros': [{'posicao': 1, 'rotulo_documentado': 'CÓDIGO DO CARGO', 'tipo': 'texto',
                           'entre_aspas_na_documentacao': True}],
           'origens': [{'pacote': 'ficticio', 'url': 'https://exemplo.invalid/cargode'}], 'confianca_extracao': 'alta'}


class TestSolucao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        t = cls._tmp.name
        cls.db = os.path.join(t, 'f.db')
        gerar_fixture_db(cls.db)
        migracoes.aplicar(cls.db, destino_backup=os.path.join(t, 'bk'))
        compilar(os.path.join(SKILL, 'casos', 'mapa_ficticio.json'), cls.db, os.path.join(t, 'bk'))
        cls.pacotes = os.path.join(t, 'pacotes')
        shutil.copytree(FIXTURE_FORMULAS, cls.pacotes)
        arq = os.path.join(cls.pacotes, 'publico', 'ficticio', 'funcoes.json')
        with open(arq, encoding='utf-8') as f:
            funcoes = json.load(f)
        with open(arq, 'w', encoding='utf-8') as f:
            json.dump(funcoes + [CARGODE], f, ensure_ascii=False)
        cls.base = kb.carregar(cls.pacotes, somente_publico=True)
        cls.cam = solucao.Camadas(cls.base, cls.db, instancia=t)

    @classmethod
    def tearDownClass(cls):
        cls.cam.fechar()
        cls._tmp.cleanup()

    def _sol(self, intencoes, **extra):
        return solucao.solucionar(dict({'pedido': 'pedido fictício', 'contexto': 'BASE', 'intencoes': intencoes},
                                       **extra), self.cam)

    def test_contrato_invalido_diz_o_que_falta(self):
        self.assertIn('erros_contrato', solucao.solucionar({'pedido': 'x', 'intencoes': []}, self.cam))
        erros = solucao.validar_contrato({'pedido': 'x', 'intencoes': [
            {'id': '1', 'texto': 'a', 'dominio': 'outro'}, {'id': '1', 'texto': 'b', 'dominio': 'cadastro'}]})
        self.assertEqual(len(erros), 3)          # domínio, id repetido, cadastro sem função

    def test_uma_saida_por_intencao_na_ordem_e_lacuna_explicita(self):
        s = self._sol([{'id': 'a', 'texto': 'somar dois números', 'dominio': 'formulas'},
                       {'id': 'b', 'texto': 'enviar e-mail ao gestor', 'dominio': 'formulas', 'essencial': 'e-mail'}])
        self.assertEqual([e['id'] for e in s['intencoes']], ['a', 'b'])
        self.assertEqual(s['intencoes'][0]['candidatos'][0]['nome'], 'SOMA2')
        self.assertEqual(s['intencoes'][1]['status'], 'lacuna')
        self.assertEqual(s['intencoes'][1]['lacuna'], 'nenhuma função documentada faz "e-mail"')
        self.assertEqual(s['lacunas'], ['b'])

    def test_schema_tabela_do_cadastro_vem_primeiro_pelo_mapa(self):
        s = self._sol([{'id': '1', 'texto': 'cadastro de cargos', 'dominio': 'schema'},
                       {'id': '2', 'texto': 'endereço de cada empresa', 'dominio': 'schema'}])
        c1, c2 = s['intencoes'][0]['candidatos'], s['intencoes'][1]['candidatos']
        self.assertEqual((c1[0]['tabela'], c1[0]['prova']), ('F_CARGO', 'mapa'))
        self.assertEqual([c['tabela'] for c in c2[:2]], ['N_ENDERECO', 'N_EMPRESA'])   # vizinha por FK que cobre
        self.assertEqual([c['prova'] for c in c2[:2]], ['mapa', 'mapa'])

    def test_cadastro_ligado_pelo_mapa_com_sql_de_apoio(self):
        s = self._sol([{'id': '1', 'texto': 'código do cargo', 'dominio': 'cadastro', 'funcao': 'CARGODE'},
                       {'id': '2', 'texto': 'código', 'dominio': 'cadastro', 'funcao': 'SOMA2'}])
        c = s['intencoes'][0]['candidatos'][0]
        self.assertEqual((c['cadastro'], c['tabela'], c['coluna_codigo']), ('cargo', 'F_CARGO', 'CODCARGO'))
        self.assertIn('FROM F_CARGO', c['sql_apoio'])
        self.assertEqual(s['intencoes'][1]['status'], 'lacuna')

    def test_formula_marcada_nunca_sai_pronta_e_lista_o_que_preencher(self):
        s = self._sol([{'id': '1', 'texto': 'código do cargo', 'dominio': 'cadastro', 'funcao': 'CARGODE'}],
                      formula='ARREDONDE(CARGODE(<<CÓDIGO DO CARGO>>), 2)')
        f = s['formula']
        self.assertTrue(f['valida'])
        self.assertFalse(f['pronta_para_cadastrar'])
        a = f['argumentos_a_preencher'][0]
        self.assertEqual((a['marcador'], a['funcao'], a['posicao'], a['cadastro']),
                         ('CÓDIGO DO CARGO', 'CARGODE', 1, 'cargo'))
        self.assertNotIn('tipo_argumento', [x['codigo'] for x in f['avisos']])   # a marca não é um literal
        s = self._sol([{'id': '1', 'texto': 'somar', 'dominio': 'formulas'}], formula='SOMA2(1, 2)')
        self.assertTrue(s['formula']['pronta_para_cadastrar'])

    def test_plano_com_marcador(self):
        r = compor({'chamar': 'CARGODE', 'args': [{'marcador': 'CÓDIGO DO CARGO'}]}, self.base, 'BASE')
        self.assertEqual(r['formula'], 'CARGODE(<<CÓDIGO DO CARGO>>)')
        self.assertFalse(r['pronta_para_cadastrar'])

    def test_marca_que_colide_com_o_dialeto_e_recusada(self):
        d = dict(self.base.dialeto(None))
        d['operadores'] = dict(d.get('operadores', {}), aritmeticos=['+', '-', '*', '/', '<<'])
        self.assertEqual(Dialeto(d).marcador_colide, ['<<'])
        _, erros, toks = analisar('SOMA2(<<X>>, 1)', d)
        self.assertNotIn('MARCADOR', [t.tipo for t in toks])
        original = self.base.dialeto
        self.base.dialeto = lambda pacote=None: d
        try:
            s = self._sol([{'id': '1', 'texto': 'somar', 'dominio': 'formulas'}], formula='SOMA2(<<X>>, 1)')
        finally:
            self.base.dialeto = original
        self.assertEqual(s['formula']['erros'][0]['codigo'], 'marcador_colide')
        self.assertIsNone(s['formula']['formula'])

    def test_marca_sem_fechamento_e_erro_de_sintaxe(self):
        _, erros, _ = analisar('SOMA2(<<X, 1)', self.base.dialeto(None))
        self.assertEqual(erros[0]['codigo'], 'lexico')
        ast, erros, _ = analisar('SOMA2(<<X>>, <<Y>>)', self.base.dialeto(None))
        self.assertEqual([(m['marcador'], m['posicao']) for m in marcadores(ast)], [('X', 1), ('Y', 2)])

    def test_candidata_guarda_o_que_foi_entregue_com_marcas(self):
        s = self._sol([{'id': '1', 'texto': 'código do cargo', 'dominio': 'cadastro', 'funcao': 'CARGODE'}],
                      formula='CARGODE(<<CÓDIGO DO CARGO>>)')
        arq = solucao.caminho_candidatas(self.db)
        cid = solucao.registrar_candidata(s, arq)
        with open(arq, encoding='utf-8') as f:
            reg = json.loads(f.readlines()[-1])
        self.assertEqual(reg['id'], cid)
        self.assertEqual(reg['formula'], 'CARGODE(<<CÓDIGO DO CARGO>>)')
        self.assertEqual(reg['argumentos_marcados'], ['CÓDIGO DO CARGO'])
        self.assertFalse(reg['pronta_para_cadastrar'])
        self.assertIsNone(solucao.registrar_candidata(s, os.path.join(self._tmp.name, 'nao', 'existe.jsonl')))

    def test_sql_montado_so_com_join_provado_e_filtro_marcado(self):
        s = self._sol([{'id': '1', 'texto': 'funcionário', 'dominio': 'schema'},
                       {'id': '2', 'texto': 'cadastro de cargos', 'dominio': 'schema', 'filtrar': 'CÓDIGO DO CARGO'}])
        q = s['sql']
        self.assertEqual(q['origem'], 'montado pela Stella')
        self.assertIn('INNER JOIN F_CARGO ON F_FUNCIONARIO.CODCARGO = F_CARGO.CODCARGO', q['sql'])
        self.assertIn('WHERE F_CARGO.CODCARGO = <<CÓDIGO DO CARGO>>', q['sql'])
        self.assertEqual([j['origem'] for j in q['joins']], ['constraint'])
        self.assertFalse(q['pronto_para_rodar'])
        a = q['argumentos_a_preencher'][0]
        self.assertEqual((a['marcador'], a['tabela'], a['coluna']), ('CÓDIGO DO CARGO', 'F_CARGO', 'CODCARGO'))
        self.assertIn('FROM F_CARGO', a['sql_apoio'])

    def test_sem_caminho_provado_e_lacuna_nunca_join_palpitado(self):
        from nomi_nomi_no_mi import montagem
        self.cam.schema.cur.execute('SELECT tabela FROM tabelas WHERE tabela NOT IN '
                                    '(SELECT tabela_filha FROM relacionamentos UNION SELECT tabela_mae FROM relacionamentos)')
        isolada = self.cam.schema.cur.fetchone()[0]
        r = montagem.montar(self.cam.schema, ['F_FUNCIONARIO', isolada], mapa=self.cam.mapa)
        self.assertNotIn(isolada, r['sql'])
        self.assertIn('sem caminho de JOIN provado', r['lacunas'][0])
        self.assertFalse(r['pronto_para_rodar'])

    def test_sql_do_claude_confere_nomes_e_joins(self):
        from nomi_nomi_no_mi import montagem
        ok = montagem.conferir(self.cam.schema, 'SELECT F.MATRICULA FROM F_FUNCIONARIO F INNER JOIN F_CARGO C '
                                                'ON F.CODCARGO = C.CODCARGO WHERE C.CODCARGO = <<CÓDIGO DO CARGO>>',
                               self.cam.mapa)
        self.assertEqual((ok['erros'], ok['avisos'], ok['joins'][0]['origem']), ([], [], 'constraint'))
        self.assertFalse(ok['pronto_para_rodar'])
        self.assertIn('FROM F_CARGO', ok['argumentos_a_preencher'][0]['sql_apoio'])
        ruim = montagem.conferir(self.cam.schema, 'SELECT F.XPTO FROM F_FUNCIONARIO F JOIN F_CARGO C '
                                                  'ON F.MATRICULA = C.CODCARGO')
        self.assertEqual(ruim['erros'], ['coluna XPTO não existe na tabela F_FUNCIONARIO'])
        self.assertIn('por colunas sem prova', ruim['avisos'][0])
        s = self._sol([{'id': '1', 'texto': 'funcionários', 'dominio': 'schema'}],
                      sql='SELECT F.MATRICULA FROM F_FUNCIONARIO F')
        self.assertEqual(s['sql']['origem'], 'escrito pelo Claude, conferido')
        self.assertTrue(s['sql']['pronto_para_rodar'])

    def test_lacuna_sem_avisos_de_busca(self):
        s = self._sol([{'id': '1', 'texto': 'enviar e-mail ao gestor', 'dominio': 'formulas', 'essencial': 'e-mail'}])
        self.assertEqual(s['intencoes'][0]['avisos'], [])

    def test_modo_basico_sem_schema(self):
        cam = solucao.Camadas(self.base, None, instancia=self._tmp.name)
        s = solucao.solucionar({'pedido': 'x', 'contexto': 'BASE', 'intencoes': [
            {'id': '1', 'texto': 'cadastro de cargos', 'dominio': 'schema'},
            {'id': '2', 'texto': 'código', 'dominio': 'cadastro', 'funcao': 'CARGODE'}]}, cam)
        self.assertIn('modo básico: schema não instalado', s['modo'])
        self.assertEqual([e['status'] for e in s['intencoes']], ['lacuna', 'lacuna'])


if __name__ == '__main__':
    unittest.main()
