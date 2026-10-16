"""Conector de PDF local (York, sem rede) e pacote que ESTENDE outro:
limpeza de cabeçalho/rodapé, junção de prosa quebrada, segmentação em seções
(bloco de função atravessando quebra de página), aspas tipográficas,
normalização no namespace do pacote-base com o dialeto dele, merge privado
que preenche sintaxe ausente (sem trocar a documentada) e o opt-out
`funcoes_sensiveis` do verificar-isolamento. Tudo com dados FICTÍCIOS."""

import json
import os
import re
import shutil
import tempfile
import unittest

from _comum import _gravar_json, TESTES, SKILL
from punk_records.ingestao.pdf import linhas_limpas, reunir_quebras, segmentar, Rastreador
from punk_records.ingestao.normalizador import normalizar_pacote
from dominios.formulas.conhecimento import carregar
from dominios.isolamento import verificar_isolamento

DIALETO_ARQ = os.path.join(SKILL, 'casos', 'fixtures', 'dialeto_pt_ficticio.json')

# cada item = uma página do PDF fictício; ALFA atravessa a quebra de página
PAGINAS = [
    ['Manual Ficticio ZZ', '1. Funcoes do modulo',
     "Funcao ALFA = Retorna o alfa do cadastro.",
     "ALFA (STRING)",
     "Exemplo: ALFA(\u201801\u2019)",
     'Versao 9.9 1'],
    ['Manual Ficticio ZZ',
     'A variavel retorna o alfa cadastrado com o codigo informado.',
     'Funcao GAMA = Retorna o gama do mes corrente.',
     'GAMA',
     '2. Exercicios',
     'SE GAMA = 11 ENTAO 1 SENAO 0 FIMSE',
     'Versao 9.9 2'],
]
REMOVER = [r'^Manual Ficticio ZZ$', r'^Versao 9\.9 \d+$']


def _gerar_pdf(caminho):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(caminho, pagesize=A4)
    for linhas in PAGINAS:
        y = 800
        for t in linhas:
            c.drawString(40, y, t)
            y -= 18
        c.showPage()
    c.save()


class TestPdfFuncoesPuras(unittest.TestCase):
    def test_linhas_limpas_remove_cabecalho_e_marcador(self):
        rx = [re.compile(p) for p in REMOVER]
        out = linhas_limpas('  Manual Ficticio ZZ\n\uf0b7   item um\n\n   Versao 9.9 3\n', rx)
        self.assertEqual([t for t in out if t], ['item um'])

    def test_reunir_quebras_so_prosa_longa(self):
        longa = 'x' * 100
        self.assertEqual(reunir_quebras([longa, 'continua aqui']), [longa + ' continua aqui'])
        self.assertEqual(reunir_quebras(['curta', 'continua']), ['curta', 'continua'])
        self.assertEqual(reunir_quebras([longa, 'ALFA (STRING)']), [longa, 'ALFA (STRING)'])

    def test_segmentar_atravessa_paginas_e_ignora_sumario(self):
        pags = [(1, ['1. Intro ........ 3', '1. Intro', 'a']), (2, ['b', '2. Fim', 'c'])]
        s = segmentar(pags, r'^\d+\.\s+\S', r'\.{5,}')
        self.assertEqual([x['titulo'] for x in s], ['(preâmbulo)', '1. Intro', '2. Fim'])
        self.assertEqual((s[1]['pagina_inicial'], s[1]['pagina_final'], s[1]['linhas']), (1, 2, ['a', 'b']))


@unittest.skipUnless(shutil.which('pdftotext'), 'pdftotext (poppler) indisponível')
class TestPdfPacoteQueEstende(unittest.TestCase):
    def setUp(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest('reportlab indisponível para gerar o PDF fictício')
        self.tmp = tempfile.mkdtemp()
        self.raiz = os.path.join(self.tmp, 'conhecimento')
        base = os.path.join(self.raiz, 'publico', 'base-ficticia')
        os.makedirs(base)
        shutil.copy(DIALETO_ARQ, os.path.join(base, 'dialeto.json'))
        _gravar_json(os.path.join(base, 'pacote.json'), {
            'id': 'base-ficticia', 'visibilidade': 'publico', 'dialeto': 'dialeto.json',
            'contextos': {'CTX': {'herda': []}}})
        _gravar_json(os.path.join(base, 'funcoes.json'), [
            # GAMA documentada SEM sintaxe; ALFA documentada com outra aridade
            {'nome': 'GAMA', 'contexto': 'CTX', 'descricao': 'Gama.', 'assinaturas': [],
             'aridades_documentadas': [], 'origens': [{'url': 'https://exemplo.invalid/gama'}]},
            {'nome': 'ALFA', 'contexto': 'CTX', 'descricao': 'Alfa.',
             'assinaturas': [{'texto': 'ALFA', 'tem_parenteses': False, 'argumentos': []}],
             'aridades_documentadas': [0], 'origens': [{'url': 'https://exemplo.invalid/alfa'}]}])
        os.makedirs(os.path.join(self.raiz, 'privado'))
        with open(os.path.join(self.raiz, 'privado', '.gitignore'), 'w') as f:
            f.write('*\n')
        self.priv = os.path.join(self.raiz, 'privado', 'manual-ficticio')
        os.makedirs(os.path.join(self.priv, 'origem'))
        _gerar_pdf(os.path.join(self.priv, 'origem', 'manual.pdf'))
        self.fonte = {
            'id': 'manual-ficticio', 'visibilidade': 'privado', 'estende': 'base-ficticia',
            'conector': 'pdf', 'arquivos': [{'id': 'man', 'caminho': 'origem/manual.pdf', 'contexto': 'CTX'}],
            'remover_linhas': REMOVER, 'padrao_secao': r'^\d+\.\s+\S',
            'normalizar_aspas_tipograficas': True, 'contextos': {'CTX': {'herda': []}}}
        _gravar_json(os.path.join(self.priv, 'fonte.json'), self.fonte)
        manifesto = Rastreador(self.fonte, self.priv, log=lambda *_: None).executar()
        _gravar_json(os.path.join(self.priv, 'paginas.json'), manifesto)
        normalizar_pacote(self.priv, log=lambda *_: None)
        with open(os.path.join(self.priv, 'funcoes.json'), encoding='utf-8') as f:
            self.fichas = {x['nome']: x for x in json.load(f)}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fichas_no_namespace_do_base_com_rastreabilidade(self):
        self.assertEqual(set(self.fichas), {'ALFA', 'GAMA'})
        alfa = self.fichas['ALFA']
        self.assertEqual(alfa['id'], 'base-ficticia:CTX:ALFA')
        self.assertEqual(alfa['origens'][0]['pacote'], 'manual-ficticio')
        self.assertEqual(alfa['origens'][0]['url'], 'arquivo://manual.pdf#page=1')
        self.assertEqual(alfa['aridades_documentadas'], [1])

    def test_bloco_atravessa_quebra_de_pagina_e_aspas_normalizadas(self):
        ex = self.fichas['ALFA']['exemplos'][0]
        self.assertEqual(ex['codigo'], "ALFA('01')")
        self.assertTrue(ex['valido_no_dialeto'])          # parseado com o dialeto do pacote-base
        self.assertIn('codigo informado', ' '.join(ex.get('explicacao', [])))
        txt = json.dumps(self.fichas, ensure_ascii=False)
        self.assertNotIn('Manual Ficticio ZZ', txt)       # cabeçalho removido

    def test_merge_preenche_lacuna_e_preserva_documentado(self):
        base = carregar(self.raiz)
        self.assertEqual(len(base.dialetos), 1)            # complemento não traz dialeto próprio
        gama = base.funcoes['base-ficticia:CTX:GAMA']
        self.assertEqual(gama['aridades_documentadas'], [0])
        self.assertEqual(gama['sintaxe_complementada_por'], 'manual-ficticio')
        alfa = base.funcoes['base-ficticia:CTX:ALFA']
        self.assertEqual(alfa['aridades_documentadas'], [0])   # pública mantida
        self.assertTrue(alfa.get('variantes_privadas'))
        self.assertTrue(any('ALFA' in a for a in base.avisos))

    def test_funcoes_sensiveis_opt_out(self):
        # nome só-privado citado num pacote público: vazamento, salvo opt-out explícito
        _gravar_json(os.path.join(self.raiz, 'publico', 'base-ficticia', 'documentos.json'),
                     [{'texto': 'exemplo usa NOVAFUNCZZ'}])
        _gravar_json(os.path.join(self.priv, 'funcoes.json'),
                     list(self.fichas.values()) + [{'nome': 'NOVAFUNCZZ', 'contexto': 'CTX'}])
        self.assertFalse(verificar_isolamento(SKILL, self.raiz)['ok'])
        _gravar_json(os.path.join(self.priv, 'fonte.json'), dict(self.fonte, funcoes_sensiveis=False))
        self.assertTrue(verificar_isolamento(SKILL, self.raiz)['ok'])


if __name__ == '__main__':
    unittest.main()
