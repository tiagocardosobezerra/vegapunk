"""
Testes de INTEGRAÇÃO de cada pacote público, dirigidos por dados.

O teste é genérico: não conhece nenhum fornecedor, nenhuma função, nenhum
contexto. Cada pacote em `punk_records/pacotes/publico/<id>/casos/` traz:

    integracao.json   patamares do dicionário (nº de funções, contextos,
                      prefixo das URLs de origem, exemplos documentados que validam)
    validacao.json    [{formula, contexto, uso?, erros: [códigos esperados]}]
    composicao.json   [{contexto, plano, formula, componentes}]
    busca.json        casos rotulados da busca (`pythagoras.py avaliar --dominio formulas`) + patamar_minimo

Pacote novo = novos arquivos de casos; este teste não muda.
"""

import json
import os
import unittest

from _comum import _ler_json
from dominios.formulas import conhecimento as kb
from dominios.formulas.validador import validar
from dominios.formulas.compositor import compor, formatar
import pythagoras

pythagoras._carregar_formulas()

PACOTES = [p for p in kb.descobrir_pacotes(somente_publico=True) if os.path.isdir(os.path.join(p.dir, 'casos'))]
# Só pacote com a documentação ingerida (`funcoes.json`) é testado contra os
# casos: na versão distribuível o texto do fornecedor não sai, e o pacote chega
# sem funções até o `york.py ingerir`.
INGERIDOS = [p for p in PACOTES if p.funcoes]
SEM_TEXTO = ('nenhum pacote público com a documentação ingerida (versão distribuível: '
             'rode york.py ingerir --pacote <pacote>)')


def _casos(pacote, nome, padrao=None):
    arq = os.path.join(pacote.dir, 'casos', nome)
    return _ler_json(arq) if os.path.exists(arq) else padrao


def codigos(v):
    return [e['codigo'] for e in v['erros']]


class TestPacotesPublicos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = kb.carregar(somente_publico=True)

    def test_existe_pacote_com_casos(self):
        self.assertTrue(PACOTES, 'nenhum pacote público com casos/ — o motor ficaria sem teste de integração')

    @unittest.skipUnless(INGERIDOS, SEM_TEXTO)
    def test_integracao(self):
        for p in INGERIDOS:
            cfg = _casos(p, 'integracao.json')
            if not cfg:
                continue
            funcs = [f for f in self.base.funcoes.values() if f['pacote'] == p.id]
            with self.subTest(pacote=p.id, verificacao='tamanho'):
                self.assertGreaterEqual(len(funcs), cfg['funcoes_minimo'])
                self.assertEqual({f['contexto'] for f in funcs}, set(cfg['contextos']))
            with self.subTest(pacote=p.id, verificacao='rastreabilidade'):
                for f in funcs:
                    self.assertTrue(f['origens'], f['id'])
                    for o in f['origens']:
                        self.assertTrue(o['url'].startswith(cfg['prefixo_url_origem']), f['id'])
                        self.assertTrue(o['page_id'] and o['sha256_bruto'] and o['versao_pagina'], f['id'])
            rel = _casos(p, os.path.join('..', 'relatorio_ingestao.json'))
            if rel:
                with self.subTest(pacote=p.id, verificacao='cobertura'):
                    self.assertEqual(rel['paginas_por_status'].get('nao_processada', 0), 0)
            with self.subTest(pacote=p.id, verificacao='exemplos documentados'):
                # termômetro da INGESTÃO: exemplos da própria documentação que validam
                total = ok = 0
                for f in funcs:
                    for e in f['exemplos']:
                        if e.get('valido_no_dialeto'):
                            total += 1
                            ok += validar(e['codigo'], self.base, f['contexto'], p.id)['valida']
                self.assertGreaterEqual(total, cfg['exemplos_documentados_minimo'])
                self.assertGreaterEqual(ok / total, cfg['exemplos_documentados_taxa_validos_minima'], f'{ok}/{total}')

    @unittest.skipUnless(INGERIDOS, SEM_TEXTO)
    def test_validacao(self):
        for p in INGERIDOS:
            for c in _casos(p, 'validacao.json', []):
                with self.subTest(pacote=p.id, formula=c['formula'][:60], contexto=c['contexto']):
                    v = validar(c['formula'], self.base, c['contexto'], p.id, c.get('uso'))
                    self.assertEqual(codigos(v), c['erros'])

    @unittest.skipUnless(INGERIDOS, SEM_TEXTO)
    def test_composicao(self):
        for p in INGERIDOS:
            for c in _casos(p, 'composicao.json', []):
                with self.subTest(pacote=p.id, formula=c['formula'][:60]):
                    r = compor(c['plano'], self.base, c['contexto'], p.id)
                    self.assertEqual(r['formula'], c['formula'])
                    self.assertEqual({x['nome'] for x in r['explicacao']['componentes']}, set(c['componentes']))

    @unittest.skipUnless(INGERIDOS, SEM_TEXTO)
    def test_formatar_idempotente_e_preserva_validade(self):
        for p in INGERIDOS:
            for f in (f for f in self.base.funcoes.values() if f['pacote'] == p.id):
                for e in f['exemplos']:
                    if not e.get('valido_no_dialeto'):
                        continue
                    with self.subTest(pacote=p.id, exemplo=e['codigo'][:60]):
                        um, erros = formatar(e['codigo'], self.base, p.id)
                        self.assertEqual(erros, [])
                        self.assertEqual(formatar(um, self.base, p.id)[0], um)
                        self.assertEqual(validar(um, self.base, f['contexto'], p.id)['valida'],
                                         validar(e['codigo'], self.base, f['contexto'], p.id)['valida'])

    @unittest.skipUnless(INGERIDOS, SEM_TEXTO)
    def test_qualidade_da_busca(self):
        """Patamar da suíte Egghead por grupo (o grupo validacao_cega nunca
        calibra nada). Subir é bem-vindo: atualize o patamar no busca.json."""
        for p in INGERIDOS:
            arq = os.path.join(p.dir, 'casos', 'busca.json')
            if not os.path.exists(arq):
                continue
            casos, top_n, patamar = pythagoras.carregar_casos_formulas(arq)
            with self.subTest(pacote=p.id, verificacao='rótulos existem'):
                for c in casos:
                    self.assertIn(c['grupo'], pythagoras.GRUPOS_FORMULAS)
                    for nome in c['esperadas']:
                        self.assertTrue(self.base.resolver(nome, c['contexto'], p.id)[0],
                                        f'{nome} não existe em {c["contexto"]} — rótulo não pode inventar nome')
            resumo = pythagoras.resumir_formulas(pythagoras.avaliar_formulas(self.base, casos, top_n), top_n)
            for grupo, minimo in patamar.items():
                with self.subTest(pacote=p.id, grupo=grupo):
                    self.assertGreaterEqual(resumo[grupo]['acertos'], minimo, json.dumps(resumo[grupo]))


if __name__ == '__main__':
    unittest.main()
