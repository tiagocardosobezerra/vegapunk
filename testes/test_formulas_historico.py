"""Laço de feedback e linha de comando de fórmulas (pela Stella) nos mesmos moldes do motor de consultas:
log próprio (nunca o de consultas), `confirmar`, `--json` em qualquer
posição, saída pt-BR. Tudo contra a fixture fictícia e um log temporário."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from _comum import SKILL, FIXTURE_FORMULAS

STELLA = os.path.join(SKILL, 'stella.py')
# comandos que existem nos dois domínios pedem --dominio
_COM_DOMINIO = ('buscar', 'detalhar', 'confirmar')


class TestCliEHistorico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, 'log.jsonl')
        self.env = dict(os.environ, PYTHONIOENCODING='utf-8', VEGAPUNK_SHAKA_LOG=self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def shaka(self, *args):
        """Comando de fórmulas pela Stella (antes: CLI do Shaka)."""
        if args and args[0] in _COM_DOMINIO:
            args = (args[0], '--dominio', 'formulas') + args[1:]
        return subprocess.run([sys.executable, STELLA, '--pacotes', FIXTURE_FORMULAS, *args],
                              capture_output=True, text=True, encoding='utf-8', env=self.env)

    def linhas_log(self):
        with open(self.log, encoding='utf-8') as f:
            return [json.loads(x) for x in f]

    def test_json_antes_ou_depois_do_comando(self):
        depois = self.shaka('buscar', 'ano de uma data', '--contexto', 'BASE', '--json')
        antes = subprocess.run([sys.executable, STELLA, '--json', '--pacotes', FIXTURE_FORMULAS,
                                'buscar', '--dominio', 'formulas', 'ano de uma data', '--contexto', 'BASE'],
                               capture_output=True, text=True, encoding='utf-8', env=self.env)
        self.assertEqual(depois.returncode, 0, depois.stderr)
        self.assertEqual(json.loads(depois.stdout)['resultados'][0]['nome'], 'ANODE')
        self.assertEqual(json.loads(antes.stdout)['resultados'][0]['nome'], 'ANODE')

    def test_saida_texto_pt_br(self):
        r = self.shaka('buscar', 'ano de uma data', '--contexto', 'BASE')
        linha = next(l for l in r.stdout.splitlines() if 'ANODE' in l)
        score = linha.split('score=')[1].split()[0]
        self.assertRegex(score, r'^\d{1,3}(\.\d{3})*,\d{2}$')   # 1.234,56 — nunca 1,234.56

    def test_detalhar_texto_por_padrao(self):
        r = self.shaka('detalhar', 'SOMA2', '--contexto', 'BASE')
        self.assertTrue(r.stdout.startswith('=== SOMA2'), r.stdout[:80])
        self.assertIn('fonte:', r.stdout)
        self.assertEqual(json.loads(self.shaka('detalhar', 'SOMA2', '--json').stdout)[0]['nome'], 'SOMA2')

    def test_buscar_registra_e_confirmar_fecha_o_laco(self):
        self.shaka('buscar', 'ano de uma data', '--contexto', 'BASE')
        r = self.shaka('confirmar', 'ano de uma data', 'anode', '--contexto', 'BASE')
        self.assertEqual(r.returncode, 0, r.stderr)
        log = self.linhas_log()
        self.assertEqual([x['tipo'] for x in log], ['buscar', 'confirmacao'])
        self.assertEqual(log[1]['funcao'], 'ANODE')
        self.assertEqual(log[0]['top5'][0], 'ANODE')

    def test_confirmar_funcao_inexistente_avisa_mas_registra(self):
        r = self.shaka('confirmar', 'algo', 'NAO_EXISTE', '--contexto', 'BASE')
        self.assertIn('AVISO', r.stderr)
        self.assertEqual(self.linhas_log()[0]['funcao'], 'NAO_EXISTE')

    def test_confirmacoes_viram_uso_real_no_pythagoras(self):
        import pythagoras
        pythagoras._carregar_formulas()
        from dominios.formulas import historico
        from _comum import base_ficticia
        self.shaka('confirmar', 'ano de uma data', 'ANODE', '--contexto', 'BASE')
        self.shaka('confirmar', 'algo', 'NAO_EXISTE', '--contexto', 'BASE')
        os.environ[historico.VAR_AMBIENTE_LOG] = self.log
        try:
            casos = pythagoras.casos_uso_real(base_ficticia(True))
        finally:
            del os.environ[historico.VAR_AMBIENTE_LOG]
        # só confirmações cuja função existe no dicionário viram caso
        self.assertEqual([(c['pedido'], c['esperadas'], c['grupo']) for c in casos],
                         [('ano de uma data', ['ANODE'], 'uso_real')])


class TestBuscaRecursosAutomaticos(unittest.TestCase):
    """Fuzzy e ambiguidade — mesma semântica do motor de consultas."""

    @classmethod
    def setUpClass(cls):
        from _comum import base_ficticia
        cls.b = base_ficticia(somente_publico=True)

    def test_fuzzy_so_para_termo_sem_match(self):
        r = self.b.buscar('arredonnde numero', 'BASE')
        self.assertTrue(r['fuzzy_aplicado'])
        self.assertEqual(r['resultados'][0]['nome'], 'ARREDONDE')
        self.assertTrue(any('fuzzy' in a for a in r['avisos']))
        self.assertIsNone(self.b.buscar('ano de uma data', 'BASE')['fuzzy_aplicado'])

    def test_ambiguidade_entre_nomes_distintos(self):
        r = self.b.buscar('número', 'BASE')          # SOMA2 × ARREDONDE, scores a ~6%
        self.assertTrue(r['ambiguidade'])
        self.assertLess(r['margem_top1_top2'], 0.12)
        self.assertTrue(any('Ambiguidade' in a for a in r['avisos']))
        self.assertFalse(self.b.buscar('arredonnde numero', 'BASE')['ambiguidade'])

    def test_mesma_funcao_em_dois_contextos_nao_e_ambiguidade(self):
        from dominios.formulas.conhecimento import BaseConhecimento
        b = BaseConhecimento(self.b.pacotes)
        f = dict(b.funcoes['ficticio:BASE:ANODE'], id='ficticio:MOD1:ANODE', contexto='MOD1')
        b.funcoes[f['id']] = f
        b.por_nome['ANODE'].append(f)
        b._indexar()
        r = b.buscar('ano de uma data informada', 'MOD1')
        self.assertEqual([x['nome'] for x in r['resultados'][:2]], ['ANODE', 'ANODE'])
        self.assertFalse(r['ambiguidade'])


if __name__ == '__main__':
    unittest.main()
