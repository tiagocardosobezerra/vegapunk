"""Providers de conhecimento: camadas público × privado, merge, busca e
isolamento — tudo com pacotes fictícios."""

import json
import os
import shutil
import tempfile
import unittest

from _comum import _ler_json, _gravar_json, FIXTURE_FORMULAS, base_ficticia, SKILL
from dominios.formulas import conhecimento as kb
from dominios.isolamento import verificar_isolamento
from dominios.formulas.validador import validar


class TestCamadas(unittest.TestCase):
    def test_somente_publico_ignora_privado(self):
        b = base_ficticia(somente_publico=True)
        self.assertNotIn('ficticio:MOD1:BONUS_INTERNO_XPTO', b.funcoes)
        self.assertEqual({f['camada'] for f in b.funcoes.values()}, {'publico'})

    def test_privado_acrescenta_funcao(self):
        b = base_ficticia()
        f = b.funcoes['ficticio:MOD1:BONUS_INTERNO_XPTO']
        self.assertEqual(f['camada'], 'privado')
        self.assertTrue(validar('BONUS_INTERNO_XPTO(10)', b, 'MOD1')['valida'])
        self.assertFalse(validar('BONUS_INTERNO_XPTO(10)', base_ficticia(True), 'MOD1')['valida'])

    def test_privado_nao_sobrescreve_assinatura_publica(self):
        b = base_ficticia()
        f = b.funcoes['ficticio:BASE:SOMA2']
        self.assertEqual(f['aridades_documentadas'], [2])
        self.assertEqual(len(f['variantes_privadas']), 1)
        self.assertTrue(any('aridade' in a for a in b.avisos))
        self.assertFalse(validar('SOMA2(1, 2, 3)', b, 'BASE')['valida'])
        # mas o exemplo privado foi agregado, marcado como privado
        self.assertTrue(any(e.get('camada') == 'privado' for e in f['exemplos']))

    def test_anotacao_privada_e_orfa(self):
        b = base_ficticia()
        f = b.funcoes['ficticio:MOD1:VALOR_TABELA']
        self.assertEqual(f['anotacoes'][0]['camada'], 'privado')
        self.assertTrue(any('NAO_EXISTE' in a for a in b.avisos))

    def test_sinonimo_privado_melhora_busca(self):
        com = base_ficticia().buscar('comissao', 'MOD1')
        sem = base_ficticia(True).buscar('comissao', 'MOD1')
        self.assertEqual(com['resultados'][0]['nome'], 'VALOR_TABELA')
        self.assertEqual(sem['resultados'], [])
        self.assertIsNotNone(sem['aviso'])

    def test_variavel_de_ambiente_privada(self):
        os.environ[kb.VAR_AMBIENTE_PRIVADO] = os.path.join(FIXTURE_FORMULAS, 'privado', 'empresa-ficticia')
        try:
            with tempfile.TemporaryDirectory() as tmp:
                shutil.copytree(os.path.join(FIXTURE_FORMULAS, 'publico'), os.path.join(tmp, 'publico'))
                b = kb.carregar(tmp)
                self.assertIn('ficticio:MOD1:BONUS_INTERNO_XPTO', b.funcoes)
        finally:
            del os.environ[kb.VAR_AMBIENTE_PRIVADO]


class TestContextos(unittest.TestCase):
    def test_heranca(self):
        b = base_ficticia()
        self.assertEqual(b.contextos_visiveis('MOD1'), ['MOD1', 'BASE'])

    def test_resolver_fora_do_contexto(self):
        b = base_ficticia()
        dentro, fora = b.resolver('SALDO_MOD2', 'MOD1')
        self.assertEqual(dentro, [])
        self.assertEqual(fora[0]['contexto'], 'MOD2')


class TestBusca(unittest.TestCase):
    def test_busca_ranqueia_pela_descricao(self):
        r = base_ficticia(True).buscar('ano de uma data', 'BASE')
        self.assertEqual(r['resultados'][0]['nome'], 'ANODE')

    def test_busca_nao_inventa(self):
        r = base_ficticia(True).buscar('calcular imposto progressivo', 'BASE')
        self.assertEqual(r['resultados'], [])
        self.assertIn('Não invente', r['aviso'])

    def test_receitas(self):
        r = base_ficticia(True).buscar('arredondar soma', 'BASE')
        self.assertEqual(r['receitas'][0]['id'], 'ficticio:receita:001')


class TestIsolamento(unittest.TestCase):
    def _copia(self, tmp):
        dst = os.path.join(tmp, 'conhecimento')
        shutil.copytree(FIXTURE_FORMULAS, dst)
        return dst

    def test_fixture_isolada(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = verificar_isolamento(SKILL, self._copia(tmp))
            self.assertTrue(r['ok'], r)

    def test_detecta_vazamento_de_termo_privado(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            alvo = os.path.join(raiz, 'publico', 'ficticio', 'documentos.json')
            _gravar_json(alvo, [{'texto': 'consulta a XPTO_TABELA_SECRETA'}])
            r = verificar_isolamento(SKILL, raiz)
            self.assertFalse(r['ok'])
            vaz = [c for c in r['verificacoes'] if 'termo' in c['verificacao']][0]
            self.assertFalse(vaz['ok'])
            self.assertIn('documentos.json:1', vaz['detalhe'])
            # a saída aponta o lugar, nunca repete o termo privado
            self.assertNotIn('XPTO_TABELA_SECRETA', json.dumps(r, ensure_ascii=False))

    def _pacote_privado_com_texto(self, raiz, texto, **manifesto):
        priv = os.path.join(raiz, 'privado', 'manual-ficticio')
        os.makedirs(priv)
        _gravar_json(os.path.join(priv, 'fonte.json'),
                     dict({'id': 'manual-ficticio', 'visibilidade': 'privado', 'estende': 'ficticio'}, **manifesto))
        _gravar_json(os.path.join(priv, 'documentos.json'), [{'texto': texto}])
        return priv

    def test_detecta_trecho_de_texto_privado_na_superficie(self):
        texto = ('o manual ficticio explica que a rotina zeta calcula o adicional '
                 'somando as horas noturnas do periodo inteiro antes do fechamento')
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            self._pacote_privado_com_texto(raiz, texto, funcoes_sensiveis=False)
            skill = os.path.join(tmp, 'skill')
            os.makedirs(os.path.join(skill, 'scripts'))
            with open(os.path.join(skill, 'SKILL.md'), 'w', encoding='utf-8') as f:
                f.write('Especificação genérica.\n')
            r = verificar_isolamento(skill, raiz)
            self.assertTrue(r['ok'], r)
            with open(os.path.join(skill, 'SKILL.md'), 'a', encoding='utf-8') as f:
                f.write(texto.upper() + '\n')   # caixa diferente continua sendo o mesmo trecho
            r = verificar_isolamento(skill, raiz)
            trecho = [c for c in r['verificacoes'] if 'trecho' in c['verificacao']][0]
            self.assertFalse(trecho['ok'])
            self.assertIn('SKILL.md', trecho['detalhe'])
            self.assertNotIn('rotina zeta', json.dumps(r, ensure_ascii=False).lower())

    def test_texto_que_tambem_esta_no_publico_nao_conta(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            comum = ('a documentacao publica do fornecedor ficticio tambem traz esta frase '
                     'inteira com mais de doze palavras seguidas')
            _gravar_json(os.path.join(raiz, 'publico', 'ficticio', 'documentos.json'), [{'texto': comum}])
            self._pacote_privado_com_texto(raiz, comum, funcoes_sensiveis=False)
            skill = os.path.join(tmp, 'skill')
            os.makedirs(os.path.join(skill, 'scripts'))
            with open(os.path.join(skill, 'SKILL.md'), 'w', encoding='utf-8') as f:
                f.write(comum + '\n')
            r = verificar_isolamento(skill, raiz)
            trecho = [c for c in r['verificacoes'] if 'trecho' in c['verificacao']][0]
            self.assertTrue(trecho['ok'], trecho)

    def test_falha_fechada_quando_pacote_privado_nao_verifica_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            self._pacote_privado_com_texto(raiz, 'texto curto', funcoes_sensiveis=False)
            r = verificar_isolamento(SKILL, raiz)
            fechada = [c for c in r['verificacoes'] if 'falha fechada' in c['verificacao']][0]
            self.assertFalse(fechada['ok'])
            self.assertIn('manual-ficticio', fechada['detalhe'])
            self.assertFalse(r['ok'])

    def test_detecta_privado_sem_gitignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            os.remove(os.path.join(raiz, 'privado', '.gitignore'))
            self.assertFalse(verificar_isolamento(SKILL, raiz)['ok'])

    def test_detecta_pacote_privado_na_pasta_publica(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            shutil.move(os.path.join(raiz, 'privado', 'empresa-ficticia'),
                        os.path.join(raiz, 'publico', 'empresa-ficticia'))
            self.assertFalse(verificar_isolamento(SKILL, raiz)['ok'])

    def test_detecta_marca_fora_do_pacote(self):
        """A marca declarada pelo pacote público fictício pode aparecer dentro
        dele, mas não na especificação da skill (SKILL.md, docs, testes, core)."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            skill = os.path.join(tmp, 'skill')
            os.makedirs(os.path.join(skill, 'scripts'))
            with open(os.path.join(skill, 'SKILL.md'), 'w', encoding='utf-8') as f:
                f.write('Especificação genérica.\n')
            self.assertTrue(verificar_isolamento(skill, raiz)['ok'])
            with open(os.path.join(skill, 'SKILL.md'), 'a', encoding='utf-8') as f:
                f.write('Feito para a ' + 'MarcaFicticia' + 'ZZ.\n')   # literal partido: este arquivo não pode conter a marca
            r = verificar_isolamento(skill, raiz)
            marca = [c for c in r['verificacoes'] if 'marcas' in c['verificacao']][0]
            self.assertFalse(marca['ok'])
            self.assertIn('SKILL.md', marca['detalhe'])


if __name__ == '__main__':
    unittest.main()
