"""Bloco 4f: aceite e aprendizado. Só comando explícito aceita; a solução é
guardada como foi entregue (argumentos marcados, nunca valores), vira caso de
validação próprio e exemplo limpo para o grafo; confirmar aceita várias
funções. Tudo fictício."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from _comum import FIXTURE_FORMULAS, SKILL
from casos.fixture_schema import gerar_fixture_db
from dominios import aceite, solucao
from dominios.formulas import conhecimento as kb
from punk_records import migracoes

sys.path.insert(0, SKILL)
import stella  # noqa: E402


class TestAceite(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = self._tmp.name
        self.db = os.path.join(self.pasta, 'punk_records.db')
        gerar_fixture_db(self.db)
        migracoes.aplicar(self.db, destino_backup=os.path.join(self.pasta, 'bk'))
        self.base = kb.carregar(FIXTURE_FORMULAS, somente_publico=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _candidata(self, formula):
        cam = solucao.Camadas(self.base, self.db, instancia=self.pasta)
        try:
            s = solucao.solucionar({'pedido': 'somar e arredondar', 'contexto': 'BASE', 'formula': formula,
                                    'intencoes': [{'id': '1', 'texto': 'somar dois números', 'dominio': 'formulas'},
                                                  {'id': '2', 'texto': 'enviar e-mail', 'dominio': 'formulas',
                                                   'essencial': 'e-mail'}]}, cam)
        finally:
            cam.fechar()
        return solucao.registrar_candidata(s, solucao.caminho_candidatas(self.db))

    def test_aceita_como_entregue_e_vira_caso_e_exemplo(self):
        cid = self._candidata('ARREDONDE(SOMA2(<<VALOR A>>, 1), 2)')
        reg, motivo = aceite.aceitar(self.pasta, cid)
        self.assertIsNone(motivo)
        self.assertEqual(reg['formula'], 'ARREDONDE(SOMA2(<<VALOR A>>, 1), 2)')        # marca, nunca valor
        self.assertEqual(aceite.formulas_aceitas(self.pasta), [reg['formula']])
        with open(os.path.join(self.pasta, aceite.ARQUIVO_CASOS), encoding='utf-8') as f:
            caso = json.load(f)['casos'][0]
        self.assertEqual([(i['esperado'], i['lacuna']) for i in caso['intencoes']], [(['SOMA2'], False), ([], True)])
        cam = solucao.Camadas(self.base, self.db, instancia=self.pasta)
        try:
            self.assertGreaterEqual(cam.grafo['n_exemplos'], 2)       # a receita fictícia + a solução aceita
            self.assertIn(('ARREDONDE', 'SOMA2'), cam.grafo['conhecimento'])
        finally:
            cam.fechar()
        self.assertEqual(aceite.aceitar(self.pasta, cid)[1], f'candidata {cid} já foi aceita')

    def _candidata_sql(self, sql=None, formula=None):
        cam = solucao.Camadas(self.base, self.db, instancia=self.pasta)
        try:
            c = {'pedido': 'funcionários de um cargo', 'contexto': 'BASE', 'intencoes': [
                {'id': '1', 'texto': 'funcionário', 'dominio': 'schema'},
                {'id': '2', 'texto': 'cargo', 'dominio': 'schema', 'filtrar': 'CÓDIGO DO CARGO'}]}
            if sql:
                c['sql'] = sql
            if formula:
                c['formula'] = formula
                c['intencoes'].append({'id': '3', 'texto': 'somar dois números', 'dominio': 'formulas'})
            s = solucao.solucionar(c, cam)
        finally:
            cam.fechar()
        return s, solucao.registrar_candidata(s, solucao.caminho_candidatas(self.db))

    def test_aceita_so_sql_e_misto_com_filtro_marcado(self):
        s, cid = self._candidata_sql()
        reg, motivo = aceite.aceitar(self.pasta, cid)
        self.assertIsNone(motivo, motivo)
        self.assertIn('<<CÓDIGO DO CARGO>>', reg['sql'])
        s, cid = self._candidata_sql(formula='SOMA2(1, 2)')
        self.assertIsNone(aceite.aceitar(self.pasta, cid)[1])

    def test_recusa_sql_com_valor_literal_ou_join_sem_prova(self):
        _, cid = self._candidata_sql(sql="SELECT F.MATRICULA FROM F_FUNCIONARIO F INNER JOIN F_CARGO C "
                                         "ON F.CODCARGO = C.CODCARGO WHERE C.CODCARGO = '01'")
        self.assertIn('valor literal', aceite.aceitar(self.pasta, cid)[1])
        _, cid = self._candidata_sql(sql='SELECT F.MATRICULA FROM F_FUNCIONARIO F JOIN F_CARGO C '
                                         'ON F.MATRICULA = C.CODCARGO')
        self.assertIn('JOIN sem prova', aceite.aceitar(self.pasta, cid)[1])
        _, cid = self._candidata_sql(sql='SELECT F.XPTO FROM F_FUNCIONARIO F')
        self.assertIn('conferência de nomes', aceite.aceitar(self.pasta, cid)[1])

    def test_recusa_formula_invalida_e_id_desconhecido(self):
        cid = self._candidata('NAOEXISTE(1)')
        self.assertIn('não passou na validação', aceite.aceitar(self.pasta, cid)[1])
        self.assertIn('não encontrada', aceite.aceitar(self.pasta, 'zzz')[1])
        self.assertFalse(os.path.exists(os.path.join(self.pasta, aceite.ARQUIVO_ACEITAS)))

    def test_comando_aceitar_e_confirmar_com_varias_funcoes(self):
        cid = self._candidata('SOMA2(1, 2)')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(stella.main(['--db', self.db, 'aceitar', cid]), 0)
        log = os.path.join(self.pasta, 'shaka.jsonl')
        os.environ['VEGAPUNK_SHAKA_LOG'] = log
        try:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(stella.main(['--pacotes', FIXTURE_FORMULAS, '--somente-publico', 'confirmar',
                                              '--dominio', 'formulas', 'somar e arredondar', 'SOMA2', 'ARREDONDE',
                                              '--contexto', 'BASE']), 0)
        finally:
            del os.environ['VEGAPUNK_SHAKA_LOG']
        with open(log, encoding='utf-8') as f:
            r = json.loads(f.readline())
        self.assertEqual((r['funcao'], r['funcoes']), ('SOMA2', ['SOMA2', 'ARREDONDE']))


if __name__ == '__main__':
    unittest.main()
