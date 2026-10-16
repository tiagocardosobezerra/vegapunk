"""Fase 3c: Edison sugere ligações de parâmetro -> cadastro só com prova
(documentação ou estrutura) e deixa de fora empate e falta de evidência.
Nomes fictícios (fixture)."""

import json
import os
import shutil
import sys
import tempfile
import unittest

from _comum import FIXTURE_FORMULAS, SKILL, _gravar_json, _ler_json
from casos.fixture_schema import gerar_fixture_db
from dominios.mapa_rotulos import entidade_de_codigo, entidade_de_descricao
from punk_records import migracoes
from punk_records.mapa import compilar

sys.path.insert(0, os.path.join(SKILL, 'satelites'))
import edison  # noqa: E402


class TestEntidade(unittest.TestCase):
    def test_variantes_do_mesmo_rotulo(self):
        for r in ('CÓDIGO DO EVENTO', 'CÓD. DO EVENTO', 'COD.EVENTO', 'CODEVENTO', 'Cod Evento',
                  'Código Identificador do Evento'):
            self.assertEqual(entidade_de_codigo(r), 'EVENTO', r)
        self.assertEqual(entidade_de_codigo('COD.UNIDADENEGOCIO'), entidade_de_codigo('Código da Unidade de Negócio'))
        self.assertEqual(entidade_de_codigo('CÓDIGO'), '')
        self.assertIsNone(entidade_de_codigo('DATA'))
        self.assertIsNone(entidade_de_codigo('CODA'))      # palavra que só começa com COD
        self.assertEqual(entidade_de_descricao('Descrição do Evento'), 'EVENTO')


def _funcao(nome, rotulo):
    return {'nome': nome, 'contexto': 'BASE', 'descricao': f'Função fictícia {nome}.',
            'assinaturas': [{'texto': f'{nome}("{rotulo}")', 'tem_parenteses': True, 'argumentos': [rotulo]}],
            'aridades_documentadas': [1], 'tipo_retorno': 'numero',
            'parametros': [{'posicao': 1, 'rotulo_documentado': rotulo, 'tipo': 'numero', 'obrigatorio': 'sim'}],
            'origens': [{'pacote': 'ficticio', 'url': 'https://exemplo.invalid/x'}], 'confianca_extracao': 'alta'}


class TestSugerirMapa(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = self._tmp.name
        self.db = os.path.join(tmp, 'f.db')
        gerar_fixture_db(self.db)
        migracoes.aplicar(self.db, destino_backup=os.path.join(tmp, 'bk'))
        compilar(os.path.join(SKILL, 'casos', 'mapa_ficticio.json'), self.db, os.path.join(tmp, 'bk'))
        self.pacotes = os.path.join(tmp, 'pacotes')
        shutil.copytree(FIXTURE_FORMULAS, self.pacotes)
        arq = os.path.join(self.pacotes, 'publico', 'ficticio', 'funcoes.json')
        funcoes = _ler_json(arq)
        funcoes += [_funcao('CARGODE', 'CÓDIGO DO CARGO'),      # já ligada pelo mapa fictício
                    _funcao('SALCARGO', 'CÓD. DO CARGO'),       # mesma entidade, função fora do cadastro
                    _funcao('NADA', 'CÓDIGO DO PLANETA'),       # nenhuma evidência
                    _funcao('SOCOD', 'CÓDIGO')]                 # sem entidade
        _gravar_json(arq, funcoes)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sugere_so_o_que_a_prova_sustenta(self):
        r = edison.sugerir_mapa(self.db, self.pacotes)
        self.assertEqual([(x['funcao'], x['cadastro']) for x in r['ligados']], [('CARGODE', 'cargo')])
        self.assertEqual([(s['funcao'], s['tipo'], s['cadastro']) for s in r['sugestoes']],
                         [('SALCARGO', 'ligar_a_cadastro', 'cargo')])
        motivos = {x['funcao']: x['motivo'] for x in r['fica_de_fora']}
        self.assertIn('nenhuma coluna da PK', motivos['NADA'])
        self.assertIn('sem entidade', motivos['SOCOD'])

    def test_novo_cadastro_pela_pk_e_empate_fica_de_fora(self):
        arq = os.path.join(self.pacotes, 'publico', 'ficticio', 'funcoes.json')
        funcoes = _ler_json(arq) + [_funcao('MATRDE', 'CÓDIGO DO ENDEREÇO')]
        _gravar_json(arq, funcoes)
        r = edison.sugerir_mapa(self.db, self.pacotes)
        novo = [s for s in r['sugestoes'] if s['funcao'] == 'MATRDE']
        self.assertEqual([(s['tipo'], s['tabela'], s['coluna_codigo'], s['chave']) for s in novo],
                         [('novo_cadastro', 'N_ENDERECO', 'CODENDERECO', ['CODENDERECO'])])

    def test_descricao_conhecida_como_errada_nao_e_evidencia(self):
        import sqlite3
        arq = os.path.join(self.pacotes, 'publico', 'ficticio', 'funcoes.json')
        _gravar_json(arq, _ler_json(arq) + [_funcao('MATRDE', 'CÓDIGO DO ENDEREÇO')])
        self.assertTrue(any(s['funcao'] == 'MATRDE' for s in edison.sugerir_mapa(self.db, self.pacotes)['sugestoes']))
        c = sqlite3.connect(self.db)      # base temporária do teste: marca a descrição como errada na origem
        c.execute("INSERT INTO mapa_papeis (parte, dono, papel, tabela, coluna, papel_divergente, prova, "
                  "prova_do_papel, descricao_errada) VALUES ('cadastro', 'x', 'codigo', 'N_ENDERECO', 'CODENDERECO', "
                  "0, 'descricao', 'usuario', 1)")
        c.commit()
        c.close()
        r = edison.sugerir_mapa(self.db, self.pacotes)
        self.assertFalse(any(s['funcao'] == 'MATRDE' for s in r['sugestoes']))
        self.assertTrue(any(x['funcao'] == 'MATRDE' for x in r['fica_de_fora']))

    def test_nao_grava_nada(self):
        with open(self.db, 'rb') as f:
            antes = f.read()
        edison.sugerir_mapa(self.db, self.pacotes)
        with open(self.db, 'rb') as f:
            self.assertEqual(f.read(), antes)


if __name__ == '__main__':
    unittest.main()
