"""Memory Card (satelites/memory_card.py): a montagem do envio (artigo,
versão, histórico, diff, relacionados), a busca, a conferência no schema, o
catálogo e a configuração do cartão funcionam sem rede. Tudo com nomes
fictícios; nenhum teste fala com o GitHub.
"""

import json
import os
import sqlite3
import tempfile
import unittest

from _comum import SKILL
import memory_card as al
from dominios.distribuicao import lista_distribuivel

SQL = """-- Relatório de teste: QZFALSA.X no comentário não conta
WITH base AS (SELECT 1 AS N)
SELECT A.X, B.Y, A.DOC
FROM QZTAB A
INNER JOIN [dbo].[QZOUTRA] AS B ON A.K = B.K
CROSS JOIN base
WHERE A.DOC = '123.456.789-00'
"""


class TestInstancia(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ['VEGAPUNK_EGGHEAD'] = self._tmp.name
        for v in ('MEMORY_CARD_REPO', 'MEMORY_CARD_DIR'):
            os.environ.pop(v, None)

    def tearDown(self):
        os.environ.pop('VEGAPUNK_EGGHEAD', None)
        self._tmp.cleanup()

    def test_sem_cartao_configurado_explica_como_criar(self):
        with self.assertRaises(al.EnvioRecusado) as ctx:
            al.config()
        self.assertIn('iniciar --repo', str(ctx.exception))

    def test_configuracao_vem_da_instancia(self):
        with open(os.path.join(self._tmp.name, 'memory_card.json'), 'w', encoding='utf-8') as f:
            json.dump({'repo': 'qzdono/qzcartao', 'pasta': os.path.join(self._tmp.name, 'c')}, f)
        c = al.config()
        self.assertEqual((c['repo'], c['publico']), ('qzdono/qzcartao', False))
        self.assertEqual(c['pasta'], os.path.abspath(os.path.join(self._tmp.name, 'c')))

    def test_iniciar_recusa_repositorio_mal_escrito_sem_rede(self):
        with self.assertRaises(al.EnvioRecusado):
            al.iniciar('sem-barra')

    def test_configuracao_e_pasta_pessoal_ficam_fora_da_distribuicao(self):
        saem = lista_distribuivel(SKILL)
        self.assertFalse([p for p in saem if p.split(os.sep)[0] in ('egghead', 'pessoal')])
        self.assertFalse([p for p in saem if os.path.basename(p) == 'memory_card.json'])


class _ComMemoryCard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = os.path.join(self._tmp.name, 'bib')
        self.arq = self._arquivo('r.sql', SQL)
        self.texto = self._arquivo('artigo.md', '## O que faz\n\nLista X.\n')
        self.db = os.path.join(self._tmp.name, 'b.db')
        c = sqlite3.connect(self.db)
        c.execute('CREATE TABLE tabelas (tabela TEXT)')
        c.execute('CREATE TABLE colunas (tabela TEXT, coluna TEXT)')
        c.execute('CREATE TABLE meta (chave TEXT, valor TEXT)')
        c.executemany('INSERT INTO tabelas VALUES (?)', [('QZTAB',), ('QZOUTRA',)])
        c.executemany('INSERT INTO colunas VALUES (?, ?)', [('QZTAB', 'X'), ('QZTAB', 'K'), ('QZTAB', 'DOC'),
                                                              ('QZOUTRA', 'K')])
        c.commit()
        c.close()
        os.environ['VEGAPUNK_EGGHEAD_DB'] = self.db

    def tearDown(self):
        os.environ.pop('VEGAPUNK_EGGHEAD_DB', None)
        self._tmp.cleanup()

    def _arquivo(self, nome, texto):
        p = os.path.join(self._tmp.name, nome)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(texto)
        return p

    def _gravar_sem_rede(self, envio):
        # gravar_envio sem o publicar (git e GitHub): só os arquivos
        al._gravar(os.path.join(envio['destino'], 'relatorio.sql'), envio['sql'])
        al.gravar_ficha(self.pasta, envio['ref'], envio['ficha'])
        al._gravar(os.path.join(envio['destino'], 'README.md'), envio['readme'])


class TestMontagem(_ComMemoryCard):
    def test_slug_sem_acento(self):
        self.assertEqual(al.slug('Recursos Humanos'), 'recursos-humanos')
        self.assertEqual(al.slug('  Funcionários / Ativos '), 'funcionarios-ativos')
        with self.assertRaises(al.EnvioRecusado):
            al.slug('***')

    def test_referencias_ignoram_comentario_cte_e_schema(self):
        tabelas, colunas = al.referencias_do_sql(SQL)
        self.assertEqual(tabelas, ['QZOUTRA', 'QZTAB'])
        self.assertEqual(colunas, ['QZOUTRA.K', 'QZOUTRA.Y', 'QZTAB.DOC', 'QZTAB.K', 'QZTAB.X'])

    def test_artigo_novo_versao_1_com_texto_e_conferencia(self):
        e = al.montar_envio(self.arq, 'Recursos Humanos', 'Funcionários', 'Pessoas', 'd', self.pasta, self.texto)
        self.assertEqual(e['ref'], 'recursos-humanos/funcionarios/pessoas')
        self.assertEqual(e['ficha']['versao'], 1)
        self.assertEqual(e['ficha']['status'], 'rascunho')
        self.assertEqual(e['ficha']['historico'][0]['motivo'], 'Primeira versão')
        self.assertIn('literal com cara de CPF', e['avisos'])
        self.assertEqual(e['conferencia']['faltando'], ['QZOUTRA.Y'])
        self.assertIn('Lista X.', e['readme'])
        self.assertIn('versão 1 · rascunho', e['readme'])

    def test_artigo_novo_sem_texto_e_recusado(self):
        with self.assertRaises(al.EnvioRecusado):
            al.montar_envio(self.arq, 'C', 'S', 'A', None, self.pasta)

    def test_so_aceita_sql(self):
        with self.assertRaises(al.EnvioRecusado):
            al.montar_envio(self._arquivo('x.csv', ''), 'C', 'S', 'A', None, self.pasta, self.texto)

    def test_reenvio_exige_motivo_sobe_versao_e_mostra_diff(self):
        self._gravar_sem_rede(al.montar_envio(self.arq, 'C', 'S', 'A', 'd', self.pasta, self.texto))
        novo = self._arquivo('r2.sql', SQL.replace('B.Y, A.DOC', 'B.Y, A.DOC, B.K'))
        with self.assertRaises(al.EnvioRecusado):
            al.montar_envio(novo, 'C', 'S', 'A', None, self.pasta)
        e = al.montar_envio(novo, 'C', 'S', 'A', None, self.pasta, motivo='mais uma coluna')
        self.assertTrue(e['substitui'])
        self.assertEqual(e['ficha']['versao'], 2)
        self.assertEqual([h['versao'] for h in e['ficha']['historico']], [1, 2])
        self.assertEqual(e['ficha']['descricao'], 'd')           # mantém a descrição
        self.assertIn('Lista X.', e['readme'])                    # mantém o corpo do artigo
        self.assertIn('+SELECT A.X, B.Y, A.DOC, B.K', e['diff_sql'])
        self.assertIn('| 2 |', e['readme'])

    def test_ficha_antiga_sem_versao_vira_versao_1(self):
        f = al.normalizar_ficha({'categoria': 'C', 'secao': 'S', 'artigo': 'A', 'criado_em': '2026-10-27T10:00:00'})
        self.assertEqual((f['versao'], f['status'], f['historico'][0]['versao']), (1, 'rascunho', 1))

    def test_relacionado_precisa_existir_e_link_e_relativo(self):
        with self.assertRaises(al.EnvioRecusado):
            al.montar_envio(self.arq, 'C', 'S', 'A', None, self.pasta, self.texto, relacionados=['c/s/b'])
        self._gravar_sem_rede(al.montar_envio(self.arq, 'C', 'S', 'B', None, self.pasta, self.texto))
        e = al.montar_envio(self.arq, 'C', 'S', 'A', None, self.pasta, self.texto, relacionados=['c/s/b'])
        self.assertIn('- [B](../../../c/s/b/)', e['readme'])
        self.assertEqual(e['novos_relacionados'], ['c/s/b'])


class TestBuscaECatalogo(_ComMemoryCard):
    def test_busca_pesa_titulo_e_ignora_acento(self):
        self._gravar_sem_rede(al.montar_envio(self.arq, 'RH', 'Funcionários', 'Pessoas idosas', 'idade', self.pasta,
                                              self.texto))
        self._gravar_sem_rede(al.montar_envio(self.arq, 'RH', 'Ponto', 'Batidas', 'marcações', self.pasta, self.texto))
        achados = al.buscar(self.pasta, ['Funcionarios', 'idade'])
        self.assertEqual(achados[0][1]['ref'], 'rh/funcionarios/pessoas-idosas')
        self.assertFalse(al.buscar(self.pasta, ['inexistente']))

    def test_catalogo_por_secao_e_por_tabela(self):
        fichas = [
            al.normalizar_ficha({'categoria': 'RH', 'secao': 'Ponto', 'artigo': 'B', 'ref': 'rh/ponto/b',
                                 'tabelas': ['QZTAB'], 'conferencia': {'ok': False, 'faltando': ['QZTAB.X']}}),
            al.normalizar_ficha({'categoria': 'RH', 'secao': 'Ponto', 'artigo': 'A', 'descricao': 'd',
                                 'ref': 'rh/ponto/a', 'tabelas': ['QZTAB'], 'status': 'em-uso', 'versao': 3}),
        ]
        md = al.gerar_catalogo_md(fichas)
        self.assertEqual(md.count('## RH'), 1)
        self.assertEqual(md.count('### Ponto'), 1)
        self.assertIn('- [A](saves/rh/ponto/a/) — d · v3 · em-uso', md)
        self.assertIn('**conferir: schema mudou**', md)
        self.assertIn('- `QZTAB`: [B](saves/rh/ponto/b/), [A](saves/rh/ponto/a/)', md)


if __name__ == '__main__':
    unittest.main()
