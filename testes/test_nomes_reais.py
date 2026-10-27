"""Checagem 10 do isolamento: nenhum nome do schema real (da instância) na
superfície distribuível. A "instância" aqui é uma base temporária com nomes
inventados; a saída nunca repete o nome."""

import os
import tempfile
import unittest

from _comum import SKILL
from dominios.nomes_reais import verificar_nomes_reais
from punk_records.schema import importar_csvs
from test_estrutura_schema import _gravar

INSTANCIA = {
    'tabelas.csv': 'tabela,descricao\nQZTABREAL,Tabela inventada da instância\n',
    'colunas.csv': ('tabela,coluna,descricao\nQZTABREAL,CODQZREAL,Código inventado\n'
                    'QZTABREAL,IDENTIDADE,Identidade do registro\nQZTABREAL,AVISO,Aviso\n'),
}


class TestNomesReais(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        _gravar(os.path.join(self._tmp.name, 'csv'), INSTANCIA)
        self.db = os.path.join(self._tmp.name, 'b.db')
        importar_csvs(os.path.join(self._tmp.name, 'csv'), self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def _doc(self, texto):
        p = os.path.join(self._tmp.name, 'doc.md')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(texto)
        return p

    def test_tabela_e_coluna_tecnica_da_instancia_sao_recusadas_sem_repetir_o_nome(self):
        r = verificar_nomes_reais(SKILL, [self._doc('Linha 1\nUse QZTABREAL e CODQZREAL aqui.\n')], self.db)
        self.assertFalse(r['ok'])
        self.assertIn('doc.md:2 (2)', r['detalhe'])
        self.assertNotIn('QZTABREAL', r['detalhe'])
        self.assertNotIn('CODQZREAL', r['detalhe'])

    def test_palavra_comum_e_coluna_da_fixture_nao_contam(self):
        # IDENTIDADE é palavra das descrições; AVISO não é técnica; CODCARGO é coluna da fixture
        r = verificar_nomes_reais(SKILL, [self._doc('IDENTIDADE, AVISO e CODCARGO.\n')], self.db)
        self.assertTrue(r['ok'], r)

    def test_termo_da_lista_da_instancia_e_recusado(self):
        lista = os.path.join(self._tmp.name, 'termos_proibidos.json')
        with open(lista, 'w', encoding='utf-8') as f:
            f.write('{"termos": ["QZSEMPREFIXO"]}')
        doc = self._doc('Texto com QZSEMPREFIXO no meio.\n')
        self.assertTrue(verificar_nomes_reais(SKILL, [doc], self.db, termos_path=os.path.join(self._tmp.name, 'x.json'))['ok'])
        r = verificar_nomes_reais(SKILL, [doc], self.db)        # lista ao lado da base: lida sozinha
        self.assertFalse(r['ok'])
        self.assertIn('1 termos da lista da instância', r['detalhe'])
        self.assertNotIn('QZSEMPREFIXO', r['detalhe'])

    def test_palavra_da_lista_da_instancia_e_recusada_em_qualquer_caixa(self):
        lista = os.path.join(self._tmp.name, 'termos_proibidos.json')
        with open(lista, 'w', encoding='utf-8') as f:
            f.write('{"palavras": ["qzpessoal"]}')
        r = verificar_nomes_reais(SKILL, [self._doc('Linha 1\nVeja a Qzpessoal e a qzpessoal.\n')], self.db)
        self.assertFalse(r['ok'])
        self.assertIn('doc.md:2 (2)', r['detalhe'])
        self.assertNotIn('qzpessoal', r['detalhe'].lower())
        self.assertTrue(verificar_nomes_reais(SKILL, [self._doc('Qzpessoalx não é a palavra.\n')], self.db)['ok'])

    def test_expressao_da_lista_vale_com_qualquer_separador_e_a_parte_sozinha_nao(self):
        lista = os.path.join(self._tmp.name, 'termos_proibidos.json')
        with open(lista, 'w', encoding='utf-8') as f:
            f.write('{"palavras": ["qzmeu cartao"]}')
        r = verificar_nomes_reais(SKILL, [self._doc('QZMEU CARTAO, qzmeu-cartao, qzmeu_cartao e qzmeucartao.\n')],
                                  self.db)
        self.assertIn('doc.md:1 (4)', r['detalhe'])
        self.assertTrue(verificar_nomes_reais(SKILL, [self._doc('qzmeu sozinho; cartao sozinho.\n')], self.db)['ok'])

    def test_sem_instancia_nao_ha_o_que_comparar(self):
        r = verificar_nomes_reais(SKILL, [self._doc('QZTABREAL\n')], os.path.join(self._tmp.name, 'nao.db'))
        self.assertTrue(r['ok'])
        self.assertIn('sem instância', r['detalhe'])


if __name__ == '__main__':
    unittest.main()
