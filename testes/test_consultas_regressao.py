"""
Regressão do motor de CONSULTAS — prova de que a introdução do motor de
fórmulas não alterou nada do que já funcionava.

  1. código do motor de consultas idêntico ao baseline (hash);
  2. pythagoras.py avaliar --dominio schema (qualidade) continua 31/31 na fixture fictícia;
  3. atlas.py (identidade de comportamento) idêntico ao golden — fixture e,
     se existir nesta instalação, banco real;
  4. usar o motor de fórmulas não escreve no log nem no banco de consultas;
  5. nenhum import cruzado entre os dois motores.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from _comum import _ler_json, _gravar_json, SKILL, SCRIPTS, TESTES, DB_REAL, LOG_REAL, sha256


class TestCodigoConsultasInalterado(unittest.TestCase):
    def test_hash_do_motor_de_consultas(self):
        base = _ler_json(os.path.join(TESTES, 'baseline_consultas_sha256.json'))
        for rel, esperado in base.items():
            if rel.startswith('_'):
                continue
            with self.subTest(arquivo=rel):
                self.assertEqual(sha256(os.path.join(SKILL, rel)), esperado,
                                 f'{rel} mudou — rode pythagoras.py avaliar e atlas.py antes de aceitar e atualize o baseline')


class TestQualidadeConsultas(unittest.TestCase):
    def test_avaliacao_schema_fixture_100(self):
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'pythagoras.py'), 'avaliar', '--dominio', 'schema'],
                           capture_output=True,
                           text=True, encoding='utf-8', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertIn('31/31 (100%)', r.stdout)
        self.assertIn('INTEGRIDADE: PASSOU', r.stdout)


class TestIdentidadeConsultas(unittest.TestCase):
    def _atlas(self, *args):
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, 'atlas.py'), 'verificar', *args],
                              capture_output=True, text=True, encoding='utf-8',
                              env=dict(os.environ, PYTHONIOENCODING='utf-8'))

    def test_atlas_fixture(self):
        r = self._atlas()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    @unittest.skipUnless(os.path.exists(DB_REAL) and
                         os.path.exists(os.path.join(os.path.dirname(DB_REAL), 'punk_records_golden.json')),
                         'banco real/golden privado ausente nesta instalação (ex.: versão distribuída)')
    def test_atlas_banco_real(self):
        antes = sha256(LOG_REAL) if os.path.exists(LOG_REAL) else None
        r = self._atlas('--db', DB_REAL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(antes, sha256(LOG_REAL) if os.path.exists(LOG_REAL) else None,
                         'atlas não pode gravar no log de uso')


class TestFormulasNaoTocamConsultas(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(DB_REAL), 'sem banco real')
    def test_formulas_nao_escrevem_no_banco_nem_no_log(self):
        antes = (sha256(DB_REAL), sha256(LOG_REAL) if os.path.exists(LOG_REAL) else None)
        stella = os.path.join(SKILL, 'stella.py')
        tmp = tempfile.mkdtemp()
        env = dict(os.environ, PYTHONIOENCODING='utf-8', VEGAPUNK_SHAKA_LOG=os.path.join(tmp, 'log.jsonl'))
        for args in (['buscar', '--dominio', 'formulas', 'arredondar valor'], ['validar', 'ABS(1)', '--contexto', 'GLOBAL'],
                     ['explicar', 'ABS(-1)', '--contexto', 'GLOBAL'], ['pacotes']):
            r = subprocess.run([sys.executable, stella, *args], capture_output=True, text=True, encoding='utf-8', env=env)
            self.assertIn(r.returncode, (0, 1), r.stderr)   # 2 = erro de uso: o comando nem rodou
        depois = (sha256(DB_REAL), sha256(LOG_REAL) if os.path.exists(LOG_REAL) else None)
        self.assertEqual(antes, depois)

    def test_sem_import_cruzado(self):
        from dominios.isolamento import verificar_isolamento
        r = verificar_isolamento(SKILL)
        sep = [c for c in r['verificacoes'] if 'depende' in c['verificacao']]
        self.assertEqual(len(sep), 2)
        for c in sep:
            self.assertTrue(c['ok'], c)


if __name__ == '__main__':
    unittest.main()
