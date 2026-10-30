"""Base com nomes em caixa mista (a fixture só tem maiúsculas) e JOIN por
tabela de passagem: o detalhar acha a tabela em qualquer grafia, o SQL sai
com o nome gravado, o caminho prefere a FK direta da principal e um JOIN
que passa por tabela não pedida nunca é "pronto para rodar". Nomes inventados.
"""

import os
import tempfile
import unittest

from _comum import SKILL  # noqa: F401  (põe a skill no sys.path)
from nomi_nomi_no_mi.busca import NomiNomiNoMi
from nomi_nomi_no_mi.montagem import montar
from punk_records.schema import importar_csvs

CSVS = {
    'tabelas.csv': 'tabela,descricao\nQzFunc,Funcionário inventado\nQzCol,Coligada inventada\n'
                   'QzCargo,Cargo inventado\nQzSecao,Seção inventada\n',
    'colunas.csv': ('tabela,coluna,descricao,tipo,nulo,ordem,pk_ordem\n'
                    'QzFunc,IdCol,Coligada,int,0,1,1\nQzFunc,IdFunc,Funcionário,int,0,2,2\nQzFunc,IdSecao,Seção,int,1,3,\n'
                    'QzCol,IdCol,Coligada,int,0,1,1\nQzCol,NomeCol,Nome da coligada,varchar,1,2,\n'
                    'QzCargo,IdCol,Coligada,int,0,1,1\nQzCargo,IdCargo,Cargo,int,0,2,2\n'
                    'QzSecao,IdCol,Coligada,int,0,1,1\nQzSecao,IdSecao,Seção,int,0,2,2\n'
                    'QzFunc,NumQz,Número do QZP do funcionário,varchar,1,4,\n'),
    'relacionamentos.csv': ('tabela_filha,campo_filho,tabela_mae,campo_mae,constraint,ordem\n'
                            'QzFunc,IdCol,QzCol,IdCol,FK_QZFUNC_COL,1\n'
                            'QzCargo,IdCol,QzCol,IdCol,FK_QZCARGO_COL,1\n'
                            'QzSecao,IdCol,QzCol,IdCol,FK_QZSECAO_COL,1\n'
                            'QzFunc,IdCol,QzSecao,IdCol,FK_QZFUNC_SECAO,1\n'
                            'QzFunc,IdSecao,QzSecao,IdSecao,FK_QZFUNC_SECAO,2\n'),
}


class TestCaixaMistaEJuncao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        pasta = os.path.join(cls._tmp.name, 'csv')
        os.makedirs(pasta)
        for nome, texto in CSVS.items():
            with open(os.path.join(pasta, nome), 'w', encoding='utf-8') as f:
                f.write(texto)
        cls.db = os.path.join(cls._tmp.name, 'punk_records.db')
        importar_csvs(pasta, cls.db)
        cls.motor = NomiNomiNoMi(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.motor.fechar()
        cls._tmp.cleanup()

    def test_detalhar_acha_em_qualquer_caixa_com_o_nome_gravado(self):
        for pedido in ('QzFunc', 'qzfunc', 'QZFUNC'):
            r = self.motor.detalhar([pedido])
            self.assertEqual(list(r['tabelas']), ['QzFunc'], pedido)
            self.assertFalse(r['aviso'], pedido)

    def test_nome_real_e_coluna_real(self):
        self.assertEqual(self.motor.nome_real('QZSECAO'), 'QzSecao')
        self.assertEqual(self.motor.coluna_real('qzsecao', 'IDSECAO'), 'IdSecao')
        self.assertEqual(self.motor.nome_real('qznada'), 'QZNADA')

    def test_join_direto_sai_pronto_com_os_nomes_gravados(self):
        m = montar(self.motor, ['QZFUNC', 'qzsecao'])
        self.assertTrue(m['pronto_para_rodar'], m['lacunas'])
        self.assertIn('FROM QzFunc', m['sql'])
        self.assertIn('INNER JOIN QzSecao ON', m['sql'])
        self.assertIn('QzFunc.IdSecao = QzSecao.IdSecao', m['sql'])

    def test_join_por_tabela_nao_pedida_nao_e_pronto(self):
        m = montar(self.motor, ['QzFunc', 'QzCargo'])
        self.assertFalse(m['pronto_para_rodar'])
        self.assertTrue(any('passa por QzCol' in l for l in m['lacunas']), m['lacunas'])

    def test_caminho_prefere_a_fk_direta_da_principal(self):
        # QzCargo entra pela coligada (passagem); QzSecao tem FK direta com a
        # principal e com a coligada: tem de vir da principal
        m = montar(self.motor, ['QzFunc', 'QzCargo', 'QzSecao'])
        self.assertIn('INNER JOIN QzSecao ON QzFunc.IdCol = QzSecao.IdCol AND QzFunc.IdSecao = QzSecao.IdSecao', m['sql'])
        self.assertFalse(any('QzSecao' in l and 'passa por' in l for l in m['lacunas']), m['lacunas'])

    def test_sigla_em_maiusculas_vira_termo_e_casa_com_a_descricao(self):
        from nomi_nomi_no_mi.texto import extrair_termos, siglas
        self.assertEqual(siglas('Número do QZP; de do mes'), {'qzp'})
        self.assertIn('qzp', extrair_termos('número do QZP'))
        self.assertNotIn('qzp', extrair_termos('número do qzp'))       # minúscula é palavra comum, não sigla
        r = self.motor.buscar('número do QZP', limite_criticas=5)
        self.assertEqual(r['criticas'][0]['tabela'], 'QzFunc')


if __name__ == '__main__':
    unittest.main()
