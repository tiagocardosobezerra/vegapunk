"""Várias instâncias locais (egghead/ e egghead-<nome>/): `--instancia`
aponta a pasta antes do motor carregar, e quem confere SQL ou nomes reais
usa a instância ativa, não sempre egghead/. Tudo em pastas temporárias."""

import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from _comum import SKILL  # noqa: F401  (põe a skill no sys.path)
import memory_card
from dominios import nomes_reais
from punk_records import instancias


def _base(pasta, tabelas=()):
    os.makedirs(pasta, exist_ok=True)
    conn = sqlite3.connect(os.path.join(pasta, 'punk_records.db'))
    conn.execute('CREATE TABLE tabelas (tabela TEXT)')
    conn.execute('CREATE TABLE colunas (tabela TEXT, coluna TEXT)')
    conn.executemany('INSERT INTO tabelas VALUES (?)', [(t,) for t in tabelas])
    conn.commit()
    conn.close()


class TestInstancias(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = self._tmp.name
        _base(os.path.join(self.raiz, 'egghead'), ['QZA'])
        _base(os.path.join(self.raiz, 'egghead-outra'), ['QZB', 'QZC'])
        os.makedirs(os.path.join(self.raiz, 'egghead-vazia'))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for v in ('VEGAPUNK_EGGHEAD', 'VEGAPUNK_EGGHEAD_DB'):
            os.environ.pop(v, None)
        self._raiz = mock.patch.object(instancias, 'RAIZ_SKILL', self.raiz)
        self._raiz.start()

    def tearDown(self):
        self._raiz.stop()
        self._env.stop()
        self._tmp.cleanup()

    def test_ativar_tira_a_flag_e_aponta_a_pasta(self):
        resto = instancias.ativar(['buscar', '--instancia', 'outra', '--dominio', 'schema', 'x'])
        self.assertEqual(resto, ['buscar', '--dominio', 'schema', 'x'])
        self.assertEqual(os.environ['VEGAPUNK_EGGHEAD'], os.path.join(self.raiz, 'egghead-outra'))
        self.assertEqual(instancias.caminho_base(), os.path.join(self.raiz, 'egghead-outra', 'punk_records.db'))

    def test_ativar_aceita_igual_e_o_nome_da_padrao(self):
        self.assertEqual(instancias.ativar(['status', '--instancia=egghead']), ['status'])
        self.assertEqual(os.environ['VEGAPUNK_EGGHEAD'], os.path.join(self.raiz, 'egghead'))

    def test_sem_flag_nao_mexe_no_ambiente(self):
        self.assertEqual(instancias.ativar(['status']), ['status'])
        self.assertNotIn('VEGAPUNK_EGGHEAD', os.environ)
        self.assertEqual(instancias.caminho_base(), os.path.join(self.raiz, 'egghead', 'punk_records.db'))

    def test_instancia_inexistente_recusa_e_lista_as_que_existem(self):
        with self.assertRaises(ValueError) as ctx:
            instancias.ativar(['status', '--instancia', 'nao'])
        self.assertIn('outra', str(ctx.exception))
        self.assertNotIn('VEGAPUNK_EGGHEAD', os.environ)

    def test_flag_sem_nome_recusa(self):
        with self.assertRaises(ValueError):
            instancias.ativar(['status', '--instancia'])

    def test_nome_invalido_ou_vazio_recusa(self):
        for nome in ('', '../egghead', 'a b', 'x/y'):
            with self.assertRaises(ValueError, msg=nome):
                instancias.ativar(['status', '--instancia=' + nome])
        self.assertNotIn('VEGAPUNK_EGGHEAD', os.environ)

    def test_listar_aguenta_base_corrompida_e_caminho_com_caracteres_especiais(self):
        estranha = os.path.join(self.raiz, 'egghead-qz#1')
        _base(estranha, ['QZE'])
        with open(os.path.join(self.raiz, 'egghead-vazia', 'punk_records.db'), 'wb') as f:
            f.write(b'isto nao e sqlite')
        itens = {i['nome']: i for i in instancias.listar()}
        self.assertEqual(itens['qz#1']['tabelas'], 1)
        self.assertTrue(itens['vazia']['existe'])
        self.assertIsNone(itens['vazia']['tabelas'])

    def test_base_explicita_no_ambiente_conflita_com_a_flag(self):
        os.environ['VEGAPUNK_EGGHEAD_DB'] = os.path.join(self.raiz, 'x.db')
        with self.assertRaises(ValueError):
            instancias.ativar(['status', '--instancia', 'outra'])

    def test_listar_marca_a_ativa_e_conta_tabelas(self):
        instancias.ativar(['--instancia', 'outra'])
        itens = {i['nome']: i for i in instancias.listar()}
        self.assertEqual(set(itens), {'egghead', 'outra', 'vazia'})
        self.assertTrue(itens['outra']['ativa'])
        self.assertFalse(itens['egghead']['ativa'])
        self.assertEqual(itens['outra']['tabelas'], 2)
        self.assertFalse(itens['vazia']['existe'])

    def test_listar_le_descricao_e_assuntos(self):
        with open(os.path.join(self.raiz, 'egghead-outra', 'instancia.json'), 'w', encoding='utf-8') as f:
            f.write('{"descricao": "banco de teste", "assuntos": ["qzum", "qzdois"]}')
        itens = {i['nome']: i for i in instancias.listar()}
        self.assertEqual(itens['outra']['descricao'], 'banco de teste')
        self.assertEqual(itens['outra']['assuntos'], ['qzum', 'qzdois'])
        self.assertEqual(itens['egghead']['assuntos'], [])

    def test_memory_card_confere_na_instancia_ativa(self):
        instancias.ativar(['--instancia', 'outra'])
        self.assertEqual(memory_card.caminho_base(), os.path.join(self.raiz, 'egghead-outra', 'punk_records.db'))
        self.assertEqual(memory_card.pasta_instancia(), os.path.join(self.raiz, 'egghead-outra'))

    def test_cartao_da_padrao_vale_nas_outras_instancias(self):
        with open(os.path.join(self.raiz, 'egghead', 'memory_card.json'), 'w', encoding='utf-8') as f:
            f.write('{"repo": "qzdono/qzcartao", "pasta": "' + self.raiz.replace('\\', '/') + '/qzcartao"}')
        instancias.ativar(['--instancia', 'outra'])
        self.assertEqual(memory_card.config()['repo'], 'qzdono/qzcartao')
        with open(os.path.join(self.raiz, 'egghead-outra', 'memory_card.json'), 'w', encoding='utf-8') as f:
            f.write('{"repo": "qzdono/qzproprio"}')
        self.assertEqual(memory_card.config()['repo'], 'qzdono/qzproprio')   # a da instância ativa vence

    def test_memory_card_respeita_base_explicita(self):
        os.environ['VEGAPUNK_EGGHEAD_DB'] = os.path.join(self.raiz, 'x.db')
        self.assertEqual(memory_card.caminho_base(), os.path.join(self.raiz, 'x.db'))

    def test_confirmacao_na_instancia_errada_aponta_a_certa(self):
        from nomi_nomi_no_mi.comandos import _instancias_com_a_tabela
        db_padrao = os.path.join(self.raiz, 'egghead', 'punk_records.db')
        self.assertEqual(_instancias_com_a_tabela('QZB', db_padrao), ['outra'])
        self.assertEqual(_instancias_com_a_tabela('QZA', db_padrao), [])      # só na própria: não avisa
        self.assertEqual(_instancias_com_a_tabela('QZNADA', db_padrao), [])

    def test_roteamento_mede_cobertura_sem_gravar_log(self):
        from casos.fixture_schema import gerar_fixture_db
        from nomi_nomi_no_mi.roteamento import assuntos_no_pedido, cobertura
        pasta = os.path.join(self.raiz, 'egghead-fixture')
        os.makedirs(pasta)
        db = os.path.join(pasta, 'punk_records.db')
        gerar_fixture_db(db)
        c = cobertura(db, 'funcionário qzpalavrainexistente')
        self.assertIn('qzpalavrainexistente', c['faltando'])
        self.assertTrue(c['cobertos'])
        self.assertTrue(set(c['em_nome_de_tabela']) <= set(c['cobertos']))
        self.assertFalse(os.path.exists(os.path.join(pasta, 'punk_records_log.jsonl')))
        self.assertEqual(assuntos_no_pedido(['crachá', 'folha'], 'Crachá do visitante'), ['crachá'])

    def test_nenhuma_instancia_entra_na_distribuicao(self):
        from dominios.distribuicao import lista_distribuivel
        irma = os.path.join(SKILL, 'egghead-qzdistrib')
        try:
            os.makedirs(os.path.join(irma, 'sub'))
            for rel in ('instancia.json', 'LEIA.md', os.path.join('sub', 'x.json')):
                with open(os.path.join(irma, rel), 'w', encoding='utf-8') as f:
                    f.write('{}')
            self.assertEqual([x for x in lista_distribuivel(SKILL) if x.startswith('egghead')], [])
        finally:
            import shutil
            shutil.rmtree(irma, ignore_errors=True)

    def test_versao_da_copia_instalada_e_aviso_de_atraso(self):
        import stella
        with mock.patch.object(stella, 'RAIZ', self.raiz):
            self.assertEqual(stella._status_versao(), {})                  # sem VERSAO.json: repositório ou distribuição
            raiz_git = os.path.dirname(os.path.dirname(SKILL))
            with open(os.path.join(self.raiz, 'VERSAO.json'), 'w', encoding='utf-8') as f:
                f.write('{"commit": "0000000", "data": "2026-01-01", "repositorio": "' + raiz_git.replace('\\', '/') + '"}')
            v = stella._status_versao()
            self.assertEqual(v['commit'], '0000000')
            if os.path.isdir(os.path.join(raiz_git, '.git')):
                self.assertIn('à frente desta cópia', v.get('aviso', ''))

    def test_nomes_reais_olha_todas_as_instancias(self):
        bases = nomes_reais._bases_da_skill(self.raiz)
        self.assertEqual([os.path.basename(os.path.dirname(b)) for b in bases], ['egghead', 'egghead-outra'])


if __name__ == '__main__':
    unittest.main()
