"""Lembretes do fluxo e cópias só de leitura: o motor escreve o próximo passo
(`LEMBRETE:` em stderr, sem tocar a saída em JSON), o lembrete do Memory Card
só aparece com cartão configurado, as gravações na instância nunca derrubam
o fluxo, e o Memory Card explica onde funciona quando falta o `gh`.
Tudo com a fixture fictícia e pastas temporárias."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from _comum import SKILL
from casos.fixture_schema import gerar_fixture_db
from dominios import lembretes


def _stderr(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        fn(*args)
    return buf.getvalue()


class TestLembretes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {'VEGAPUNK_EGGHEAD': self._tmp.name})
        self._env.start()
        os.environ.pop('MEMORY_CARD_REPO', None)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_confirmar_sempre_lembra_com_o_dominio(self):
        self.assertIn('LEMBRETE: no fim do fluxo', _stderr(lembretes.lembrar_confirmar, 'schema'))
        self.assertIn('--dominio formulas', _stderr(lembretes.lembrar_confirmar, 'formulas'))

    def test_cartao_so_lembra_quando_configurado(self):
        self.assertEqual(_stderr(lembretes.lembrar_salvar_no_cartao), '')
        self.assertEqual(_stderr(lembretes.lembrar_buscar_no_cartao, 'x'), '')
        self.assertEqual(_stderr(lembretes.lembrar_conferir_cartao), '')
        with open(os.path.join(self._tmp.name, 'memory_card.json'), 'w', encoding='utf-8') as f:
            json.dump({'repo': 'qzdono/qzcartao'}, f)
        self.assertIn('Memory Card', _stderr(lembretes.lembrar_salvar_no_cartao))
        self.assertIn('stella.py cartao buscar "folha"', _stderr(lembretes.lembrar_buscar_no_cartao, 'folha'))
        self.assertIn('stella.py cartao conferir', _stderr(lembretes.lembrar_conferir_cartao))

    def test_cli_detalhar_lembra_em_stderr_sem_sujar_o_json(self):
        db = os.path.join(self._tmp.name, 'fixture.db')
        gerar_fixture_db(db)
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        r = subprocess.run([sys.executable, os.path.join(SKILL, 'stella.py'), '--db', db, 'detalhar', '--dominio',
                            'schema', 'N_EMPRESA', '--json'], capture_output=True, text=True, encoding='utf-8', env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        json.loads(r.stdout)
        self.assertIn('LEMBRETE:', r.stderr)
        self.assertIn('confirmar --dominio schema', r.stderr)


class TestInstanciaSoDeLeitura(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # um ARQUIVO no lugar da pasta: qualquer gravação dentro dele falha com OSError
        self.bloqueio = os.path.join(self._tmp.name, 'arquivo')
        open(self.bloqueio, 'w').close()

    def tearDown(self):
        self._tmp.cleanup()

    def test_log_do_schema_devolve_false(self):
        from nomi_nomi_no_mi.historico import registrar_uso
        self.assertFalse(registrar_uso(os.path.join(self.bloqueio, 'b.db'), {'tipo': 'buscar'}))

    def test_log_de_formulas_devolve_false(self):
        from dominios.formulas import historico
        with mock.patch.dict(os.environ, {historico.VAR_AMBIENTE_LOG: os.path.join(self.bloqueio, 'log.jsonl')}):
            self.assertFalse(historico.registrar({'tipo': 'buscar'}))

    def test_candidata_devolve_none(self):
        from dominios import solucao
        s = {'pedido': 'x', 'intencoes': [], 'lacunas': []}
        self.assertIsNone(solucao.registrar_candidata(s, os.path.join(self.bloqueio, 'c.jsonl')))


class TestMemoryCardSemGh(unittest.TestCase):
    def test_sem_gh_explica_onde_funciona(self):
        import memory_card
        with mock.patch.object(memory_card.shutil, 'which', return_value=None):
            with self.assertRaises(memory_card.EnvioRecusado) as ctx:
                memory_card._exigir_gh()
        self.assertIn('claude.ai', str(ctx.exception))
        self.assertIn('`gh`', str(ctx.exception))

    def test_comando_ausente_vira_recusa_clara(self):
        import memory_card
        with self.assertRaises(memory_card.EnvioRecusado) as ctx:
            memory_card._rodar(['qz-comando-que-nao-existe'])
        self.assertIn('só funciona', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
