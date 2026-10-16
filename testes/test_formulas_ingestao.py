"""Ingestão (York) sem rede: crawler contra uma wiki Confluence FALSA em
memória, extrator contra HTML fictício de cada layout, normalizador
(duplicidade, conflito, rastreabilidade)."""

import json
import os
import shutil
import tempfile
import unittest

from _comum import _ler_json, _gravar_json, TESTES, SKILL
from punk_records.ingestao import confluence
from punk_records.ingestao.confluence import Rastreador, extrair_links, chave_titulo
from punk_records.ingestao.html_linhas import converter
from punk_records.ingestao.extrator_funcoes import extrair_pagina, analisar_sintaxe
from punk_records.ingestao.normalizador import normalizar_pacote

DIALETO_ARQ = os.path.join(SKILL, 'casos', 'fixtures', 'dialeto_pt_ficticio.json')
DIALETO = _ler_json(DIALETO_ARQ)

# ------------------------------------------------------------- wiki falsa
PAGINAS = {
    '1': ('Raiz Fórmulas', 'ESP', '<p>Índice</p><p><a href="/pages/viewpage.action?pageId=9">ver anexo</a></p>'),
    '2': ('Funções A', 'ESP', '<p><strong>Função ALFA</strong> = Retorna alfa.</p><p><strong>Sintaxe</strong> = ALFA(VALOR)</p>'
                              '<p><ac:link><ri:page ri:space-key="ESP" ri:content-title="Funções B" /></ac:link></p>'),
    '3': ('Funções B', 'ESP', '<p><strong>Função BETA</strong> = Retorna beta.</p><p><strong>Sintaxe</strong> = BETA</p>'
                              '<p><a href="https://externo.invalid/x">externo</a></p>'),
    '4': ('Sub de B', 'ESP', '<p>Texto sem relação com o tema.</p>'),
    '9': ('Anexo de fórmula', 'ESP', '<p>Sintaxe: GAMA(DATA)</p><p><a href="/pages/viewpage.action?pageId=10">mais</a></p>'),
    '10': ('Página de outro produto', 'OUTRO', '<p>Sintaxe Função qualquer</p>'),
}
FILHAS = {'1': ['2', '3'], '3': ['4']}


class ClienteFalso:
    def __init__(self, *a, **k):
        self.requisicoes = 0

    def pagina(self, pid, com_corpo=True):
        self.requisicoes += 1
        if pid not in PAGINAS:
            return {'_erro': 404}
        titulo, esp, corpo = PAGINAS[pid]
        d = {'id': pid, 'title': titulo, 'space': {'key': esp}, 'version': {'number': 1, 'when': '2026-01-01'},
             'ancestors': []}
        if com_corpo:
            d['body'] = {'storage': {'value': corpo}}
        return d

    def filhas(self, pid):
        return [{'id': f, 'title': PAGINAS[f][0]} for f in FILHAS.get(pid, [])]

    def por_titulo(self, esp, titulo):
        return None


FONTE = {'id': 'teste', 'base_url': 'https://wiki.invalid', 'sementes': [{'page_id': '1', 'contexto': 'CTX'}],
         'relevancia': {'espacos_permitidos': ['ESP'], 'padroes_titulo': ['F[óo]rmula'],
                        'padroes_conteudo': ['Sintaxe'], 'minimo_padroes': 1, 'profundidade_links': 2},
         'dialeto': 'dialeto.json', 'contextos': {'CTX': {'herda': []}}}


class TestCrawler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = confluence.ClienteConfluence
        confluence.ClienteConfluence = ClienteFalso

    def tearDown(self):
        confluence.ClienteConfluence = self._orig
        shutil.rmtree(self.tmp)

    def test_pai_filhas_links_e_escopo(self):
        m = Rastreador(FONTE, self.tmp, log=lambda *_: None).executar()
        st = {k: v['status'] for k, v in m.items() if not k.startswith('_')}
        # árvore inteira processada, inclusive neta sem padrão de conteúdo
        for pid in ('1', '2', '3', '4'):
            self.assertEqual(st[pid], 'processada', pid)
        # link relevante fora da árvore: processado; outro espaço: fora de escopo
        self.assertEqual(st['9'], 'processada')
        self.assertEqual(st['10'], 'fora_de_escopo')
        self.assertIn('link em 2', m['3']['descoberta_via'])          # <ri:page> resolvido pelo título local
        self.assertEqual(m['_externos']['links'], [{'de': '3', 'url': 'https://externo.invalid/x'}])
        bruto = _ler_json(os.path.join(self.tmp, 'bruto', '2.json'))
        for campo in ('url', 'versao', 'sha256_storage', 'coletado_em', 'storage'):
            self.assertIn(campo, bruto)

    def test_exclusao_por_id_e_pagina_nova_na_arvore_so_com_aceite(self):
        fonte = dict(FONTE, excluir_page_ids=['3'], paginas_aprovadas=['1'])
        m = Rastreador(fonte, self.tmp, log=lambda *_: None).executar()
        st = {k: v['status'] for k, v in m.items() if not k.startswith('_')}
        self.assertEqual(st['3'], 'excluida')
        self.assertNotIn('4', st)                       # filha de excluída não é visitada
        self.assertEqual(st['2'], 'nova_na_arvore')     # nova na árvore: registrada, não baixada
        self.assertEqual(m['2']['titulo'], 'Funções A')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'bruto', '2.json')))
        m = Rastreador(dict(fonte, paginas_aprovadas=['1', '2']), self.tmp, log=lambda *_: None).executar()
        self.assertEqual(m['2']['status'], 'processada')

    def test_arvore_prevalece_sobre_link_no_contexto(self):
        # '9' é achada por link a partir da semente 1 (CTX) e também é a raiz de outra semente (OUTRO_CTX)
        fonte = dict(FONTE, sementes=[{'page_id': '1', 'contexto': 'CTX'}, {'page_id': '9', 'contexto': 'OUTRO_CTX'}])
        fonte['sementes'] = list(reversed(fonte['sementes']))[::-1]   # semente 1 primeiro: o link chega antes
        m = Rastreador(fonte, self.tmp, log=lambda *_: None).executar()
        self.assertEqual((m['9']['status'], m['9']['contexto'], m['9']['na_arvore']), ('processada', 'OUTRO_CTX', True))

    def test_links_e_titulos(self):
        refs = extrair_links('<a href="https://wiki.invalid/display/ESP/T%C3%ADtulo+X">x</a>'
                             '<a href="/pages/viewpage.action?pageId=77">y</a>', ['wiki.invalid'], 'ESP')
        self.assertEqual(refs, [{'tipo': 'titulo', 'espaco': 'ESP', 'valor': 'Título X'},
                                {'tipo': 'id', 'valor': '77'}])
        self.assertEqual(chave_titulo('esp', 'Fórmulas / Funções – C'), chave_titulo('ESP', 'fórmulas / funções - c'))


class TestExtrator(unittest.TestCase):
    def fichas(self, html, titulo='Página'):
        return {f['nome']: f for f in extrair_pagina({'titulo': titulo}, converter(html), DIALETO)}

    def test_layout_rotulos_com_igual(self):
        f = self.fichas('<p><strong>Função XA</strong> = Retorna xa.</p><p><strong>Sintaxe</strong> = XA (\'COD\')</p>'
                        '<p><strong>Tipo de Retorno</strong> = Valor</p><p><strong>Exemplo:</strong><br/>XA(\'01\')</p>')['XA']
        self.assertEqual(f['descricao'], 'Retorna xa.')
        self.assertEqual(f['assinaturas'][0]['argumentos'], ["'COD'"])
        self.assertEqual(f['tipo_retorno_documentado'], 'Valor')
        self.assertEqual(f['exemplos'][0]['codigo'], "XA('01')")
        self.assertEqual(f['confianca_extracao'], 'alta')

    def test_layout_tabela(self):
        html = ('<h1>ZB</h1><table><tr><th>Função</th><th><strong>ZB</strong></th></tr>'
                '<tr><td>Descrição</td><td>Faz zb.</td></tr><tr><td>Sintaxe</td><td>ZB( NUM A, NUM B )</td></tr>'
                '<tr><td>Parâmetros</td><td><ul><li>NUM A → primeiro</li><li>NUM B → segundo</li></ul></td></tr>'
                '<tr><td>Exemplo</td><td>ZB(1, 2)</td></tr><tr><td>Retorno</td><td>3</td></tr></table>')
        f = self.fichas(html)['ZB']
        self.assertEqual([p['descricao'] for p in f['parametros']], ['primeiro', 'segundo'])
        self.assertEqual(f['exemplos'][0]['resultado'], '3')

    def test_variavel_sem_parenteses_e_sem_sintaxe(self):
        fs = self.fichas('<p><strong>Função VV</strong></p><p>Retorna vv.</p><p>VV</p>'
                         '<p><strong>Função WW</strong></p><p>Retorna ww.</p>')
        self.assertFalse(fs['VV']['assinaturas'][0]['tem_parenteses'])
        self.assertEqual(fs['WW']['assinaturas'], [])
        self.assertIn('sintaxe', fs['WW']['nao_documentado'])
        self.assertEqual(fs['WW']['confianca_extracao'], 'baixa')

    def test_prosa_nao_vira_funcao(self):
        fs = self.fichas('<p>Função de fórmula que retorna algo em prosa.</p><p><strong>Funções A</strong></p>')
        self.assertEqual(fs, {})

    def test_exemplo_multilinha_vira_um_programa(self):
        html = ('<p><strong>Função PP</strong> = pp</p><p><strong>Sintaxe</strong> = PP</p><p><strong>Exemplo:</strong></p>'
                '<p>DECL X;</p><p>SETVAR(X, PP);</p><p>SE X &gt; 0</p><p>ENTAO 1</p><p>SENAO 0</p><p>FIMSE</p>')
        f = self.fichas(html)['PP']
        self.assertEqual(len(f['exemplos']), 1)
        self.assertEqual(f['exemplos'][0]['codigo'], 'DECL X;\nSETVAR(X, PP);\nSE X > 0\nENTAO 1\nSENAO 0\nFIMSE')

    def test_sintaxe_alternativa_e_aspas_quebradas(self):
        f = self.fichas("<p><strong>Função TT</strong> = t</p><p>Sintaxe: TT( A ) ou TT( A , B )</p>")['TT']
        self.assertEqual([len(a['argumentos']) for a in f['assinaturas']], [1, 2])
        a = analisar_sintaxe("TABX (DO CAMPO', DE RETORNO')", 'TABX')
        self.assertEqual(len(a['argumentos']), 2)
        self.assertIn('aspas desbalanceadas na sintaxe documentada', a['avisos'])


class TestNormalizador(unittest.TestCase):
    def test_duplicidade_conflito_e_rastreabilidade(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'bruto'))
            shutil.copy(DIALETO_ARQ, os.path.join(tmp, 'dialeto.json'))
            _gravar_json(os.path.join(tmp, 'fonte.json'), FONTE)
            paginas = {
                'p1': '<p><strong>Função DUP</strong> = primeira descrição</p><p><strong>Sintaxe</strong> = DUP(VALOR)</p>',
                'p2': '<p><strong>Função DUP</strong> = segunda descrição</p><p><strong>Sintaxe</strong> = DUP(VALOR, VALOR)</p>'
                      '<p><strong>Observação:</strong> nota única da p2</p>',
            }
            man = {}
            for pid, html in paginas.items():
                _gravar_json(os.path.join(tmp, 'bruto', pid + '.json'),
                             {'page_id': pid, 'titulo': pid, 'url': f'https://wiki.invalid/{pid}', 'espaco': 'ESP',
                              'versao': 3, 'atualizado_em': 'x', 'ancestrais': [], 'sha256_storage': 'h' + pid,
                              'storage': html})
                man[pid] = {'status': 'processada', 'contexto': 'CTX', 'na_arvore': True}
            _gravar_json(os.path.join(tmp, 'paginas.json'), man)
            rel = normalizar_pacote(tmp, log=lambda *_: None)
            fs = _ler_json(os.path.join(tmp, 'funcoes.json'))
            self.assertEqual(len(fs), 1)                                   # duplicidade consolidada
            f = fs[0]
            self.assertEqual({o['page_id'] for o in f['origens']}, {'p1', 'p2'})
            self.assertEqual(len(f['assinaturas']), 2)                     # nada único foi perdido
            self.assertEqual(len(f['descricoes_alternativas']), 1)
            self.assertTrue(any('nota única' in o['texto'] for o in f['observacoes']))
            self.assertEqual(rel['conflitos_entre_origens'][0]['campo'], 'aridade')


if __name__ == '__main__':
    unittest.main()
