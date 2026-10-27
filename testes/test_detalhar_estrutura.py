"""detalhar com estrutura (fase 2 da v3): tipo/nulo/PK por coluna, FKs
agrupadas pela constraint e JOIN pronto com a chave completa. Base fictícia
em pasta temporária, com duas FKs compostas que repetem o mesmo campo (o
caso que só o nome da constraint desambigua)."""

import os
import sqlite3
import tempfile
import unittest

import _comum  # noqa: F401
from nomi_nomi_no_mi.busca import NomiNomiNoMi
from punk_records.schema import importar_csvs
from test_estrutura_schema import _CSV_ANTIGO, _CSV_ESTRUTURA, _ESTRUTURA_ANTIGA, _gravar


def _base(tmp, arquivos):
    _gravar(os.path.join(tmp, 'csv'), arquivos)
    db = os.path.join(tmp, 'b.db')
    importar_csvs(os.path.join(tmp, 'csv'), db)
    return db


def _detalhar(db, *tabelas):
    motor = NomiNomiNoMi(db)
    try:
        return motor.detalhar(list(tabelas))
    finally:
        motor.fechar()


def _com_estrutura():
    arquivos = dict(_CSV_ANTIGO)
    arquivos.update(_CSV_ESTRUTURA)
    for nome in ('colunas.csv', 'relacionamentos.csv'):
        arquivos[nome] = '\n'.join(l for l in arquivos[nome].split('\n') if 'X_NOVA' not in l)
    return arquivos


class TestDetalharComConstraint(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = _base(self._tmp.name, _com_estrutura())

    def tearDown(self):
        self._tmp.cleanup()

    def test_fks_agrupadas_pela_constraint_com_join_pronto(self):
        t = _detalhar(self.db, 'X_FILHA')['tabelas']['X_FILHA']
        self.assertEqual([(f['constraint'], f['composta'], f['papel']) for f in t['fks']],
                         [('FK_FILHA_PAI', True, 'filha'), ('FK_FILHA_PAI2', True, 'filha')])
        self.assertEqual(t['fks'][0]['join'],
                         'INNER JOIN X_PAI ON X_FILHA.CODEMP = X_PAI.CODEMP AND X_FILHA.CODPAI = X_PAI.CODPAI')
        self.assertEqual(t['fks'][1]['on'], 'X_FILHA.CODEMP = X_PAI.CODEMP AND X_FILHA.CODPAI2 = X_PAI.CODPAI')
        self.assertEqual(t['fks_sem_constraint'], [])

    def test_join_do_ponto_de_vista_da_mae(self):
        t = _detalhar(self.db, 'X_PAI')['tabelas']['X_PAI']
        self.assertEqual(t['fks'][0]['papel'], 'mae')
        self.assertEqual(t['fks'][0]['join'],
                         'INNER JOIN X_FILHA ON X_FILHA.CODEMP = X_PAI.CODEMP AND X_FILHA.CODPAI = X_PAI.CODPAI')

    def test_campos_antigos_continuam_iguais(self):
        t = _detalhar(self.db, 'X_FILHA')['tabelas']['X_FILHA']
        self.assertEqual(len(t['relacionamentos']), 4)
        self.assertEqual(set(t['relacionamentos'][0]), {'tabela_filha', 'campo_filho', 'tabela_mae', 'campo_mae'})

    def test_tipo_nulo_e_pk(self):
        t = _detalhar(self.db, 'X_FILHA')['tabelas']['X_FILHA']
        self.assertEqual(t['metadados']['pk'], ['CODEMP', 'CODFILHA'])
        cod = next(c for c in t['colunas'] if c['coluna'] == 'CODPAI')
        self.assertEqual((cod['tipo'], cod['tamanho'], cod['nulo'], cod['pk_ordem']), ('varchar', 10, 1, None))

    def test_texto_mostra_tipo_e_join(self):
        from nomi_nomi_no_mi.saida import formatar_detalhar_texto
        txt = formatar_detalhar_texto(_detalhar(self.db, 'X_FILHA'), completo=True)
        self.assertIn('CODPAI [varchar(10) NULL]', txt)
        self.assertIn('PK: CODEMP, CODFILHA', txt)
        self.assertIn('FK_FILHA_PAI (X_FILHA -> X_PAI, composta): INNER JOIN X_PAI ON', txt)

    def test_texto_enxuto_so_traz_o_join_entre_as_tabelas_pedidas(self):
        from nomi_nomi_no_mi.saida import formatar_detalhar_texto
        so_filha = formatar_detalhar_texto(_detalhar(self.db, 'X_FILHA'))
        self.assertNotIn('INNER JOIN X_PAI', so_filha)
        self.assertIn('com tabelas fora do pedido (2, sem o JOIN): X_PAI', so_filha)
        self.assertIn('use --completo', so_filha)
        as_duas = formatar_detalhar_texto(_detalhar(self.db, 'X_FILHA', 'X_PAI'))
        self.assertIn('FK_FILHA_PAI (X_FILHA -> X_PAI, composta): INNER JOIN X_PAI ON', as_duas)
        self.assertTrue(as_duas.startswith('Caminho X_FILHA -> X_PAI'))      # o essencial vem primeiro


class TestDetalharSemConstraint(unittest.TestCase):
    def test_sem_nome_de_constraint_nao_agrupa_por_palpite(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _detalhar(_base(tmp, _CSV_ANTIGO), 'X_FILHA')
            t = r['tabelas']['X_FILHA']
            self.assertEqual(t['fks'], [])
            self.assertEqual(len(t['fks_sem_constraint']), 4)
            self.assertEqual({x['motivo'] for x in t['fks_sem_constraint']}, {'mae_sem_pk'})   # base sem PK
            aviso = next(a for a in r['aviso'] if 'sem agrupamento provado' in a)
            self.assertIn('punk_records/extracao/relacionamentos.sql', aviso)
            self.assertEqual(t['metadados']['pk'], [])

    def test_base_na_versao_1_sem_colunas_de_estrutura(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'v1.db')
            conn = sqlite3.connect(db)
            conn.executescript(_ESTRUTURA_ANTIGA)
            conn.execute("INSERT INTO tabelas (tabela) VALUES ('A')")
            conn.execute("INSERT INTO colunas VALUES ('A', 'X', 'desc')")
            conn.commit()
            conn.close()
            c = _detalhar(db, 'A')['tabelas']['A']['colunas'][0]
            self.assertEqual((c['coluna'], c['tipo'], c['pk_ordem']), ('X', None, None))

    def test_autorreferencia_usa_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivos = {
                'tabelas.csv': 'tabela,descricao\nX_NO,No de arvore\n',
                'colunas.csv': 'tabela,coluna,descricao\nX_NO,ID,Id\nX_NO,PAI,Pai\n',
                'relacionamentos.csv': 'tabela_filha,campo_filho,tabela_mae,campo_mae,constraint,ordem\n'
                                       'X_NO,PAI,X_NO,ID,FK_NO_PAI,1\n',
            }
            t = _detalhar(_base(tmp, arquivos), 'X_NO')['tabelas']['X_NO']
            self.assertEqual(t['fks'][0]['papel'], 'ambas')
            self.assertEqual(t['fks'][0]['join'], 'INNER JOIN X_NO AS X_NO_MAE ON X_NO.PAI = X_NO_MAE.ID')


def _rel(f, cf, m, cm, nome=None):
    return {'tabela_filha': f, 'campo_filho': cf, 'tabela_mae': m, 'campo_mae': cm, 'constraint_nome': nome}


PK_MAE = {'CODEMP': 1, 'CODPAI': 2}


class TestAgrupamentoProvadoPelaChave(unittest.TestCase):
    """Fase 2b: sem constraint, o agrupamento só vale quando a PK da mãe o
    prova, numa única forma. Nomes fictícios."""

    def _agrupar(self, linhas, pk=PK_MAE):
        from nomi_nomi_no_mi.grafo import agrupar_fks
        return agrupar_fks(linhas, 'F', lambda t: pk if t == 'M' else {})

    def test_ligacao_unica_que_cobre_a_pk_vira_join_na_ordem_da_pk(self):
        fks, sem = self._agrupar([_rel('F', 'PAI', 'M', 'CODPAI'), _rel('F', 'EMP', 'M', 'CODEMP')])
        self.assertEqual(sem, [])
        self.assertEqual([(f['origem'], f['constraint']) for f in fks], [('ligação única + chave da mãe', None)])
        self.assertEqual(fks[0]['join'], 'INNER JOIN M ON F.EMP = M.CODEMP AND F.PAI = M.CODPAI')

    def test_ligacao_que_nao_cobre_a_pk_fica_com_aviso(self):
        fks, sem = self._agrupar([_rel('F', 'EMP', 'M', 'CODEMP'), _rel('F', 'OUTRO', 'M', 'NAOPK')])
        self.assertEqual(fks, [])
        self.assertEqual({x['motivo'] for x in sem}, {'chave_incompleta'})

    def test_chave_da_mae_com_coluna_fixa_repetida(self):
        fks, sem = self._agrupar([_rel('F', 'EMP', 'M', 'CODEMP'), _rel('F', 'PAI', 'M', 'CODPAI'),
                                  _rel('F', 'EMP', 'M', 'CODEMP'), _rel('F', 'PAI2', 'M', 'CODPAI')])
        self.assertEqual(sem, [])
        self.assertEqual([(f['origem'], f['on']) for f in fks],
                         [('chave da mãe', 'F.EMP = M.CODEMP AND F.PAI = M.CODPAI'),
                          ('chave da mãe', 'F.EMP = M.CODEMP AND F.PAI2 = M.CODPAI')])

    def test_mesmo_campo_da_filha_em_duas_colunas_da_pk_nao_agrupa(self):
        fks, sem = self._agrupar([_rel('F', 'EMP', 'M', 'CODEMP'), _rel('F', 'EMP', 'M', 'CODPAI')])
        self.assertEqual(fks, [])
        self.assertEqual({x['motivo'] for x in sem}, {'agrupamento_ambiguo'})

    def test_duas_colunas_com_variantes_nao_agrupa(self):
        fks, sem = self._agrupar([_rel('F', 'E1', 'M', 'CODEMP'), _rel('F', 'E2', 'M', 'CODEMP'),
                                  _rel('F', 'P1', 'M', 'CODPAI'), _rel('F', 'P2', 'M', 'CODPAI')])
        self.assertEqual(fks, [])
        self.assertEqual({x['motivo'] for x in sem}, {'agrupamento_ambiguo'})

    def test_mae_sem_pk_e_ligacao_simples_nao_agrupam(self):
        fks, sem = self._agrupar([_rel('F', 'EMP', 'M', 'CODEMP'), _rel('F', 'PAI', 'M', 'CODPAI')], pk={})
        self.assertEqual((fks, {x['motivo'] for x in sem}), ([], {'mae_sem_pk'}))
        fks, sem = self._agrupar([_rel('F', 'EMP', 'M', 'CODEMP')], pk={'CODEMP': 1})
        self.assertEqual((fks, [x['motivo'] for x in sem]), ([], ['ligacao_simples']))

    def test_constraint_vem_antes_e_resto_de_constraint_parcial_nao_agrupa(self):
        fks, sem = self._agrupar([_rel('F', 'EMP', 'M', 'CODEMP', 'FK_A'), _rel('F', 'PAI', 'M', 'CODPAI', 'FK_A'),
                                  _rel('F', 'PAI3', 'M', 'CODPAI')])
        self.assertEqual([f['origem'] for f in fks], ['constraint'])
        self.assertEqual([x['motivo'] for x in sem], ['resto_de_constraint_parcial'])


class TestAvisoSemCaminhoLimitado(unittest.TestCase):
    def test_lista_so_os_primeiros_pares(self):
        from dominios.schema.config import LIMITE_PARES_SEM_CAMINHO
        nomes = [f'X_ILHA{i}' for i in range(7)]          # 7 tabelas isoladas = 21 pares sem caminho
        arquivos = {'tabelas.csv': 'tabela,descricao\n' + ''.join(f'{t},Ilha\n' for t in nomes),
                    'colunas.csv': 'tabela,coluna,descricao\n' + ''.join(f'{t},ID,Id\n' for t in nomes)}
        with tempfile.TemporaryDirectory() as tmp:
            r = _detalhar(_base(tmp, arquivos), *nomes)
        aviso = next(a for a in r['aviso'] if a.startswith('Sem caminho'))
        self.assertEqual(aviso.count(' e X_ILHA'), LIMITE_PARES_SEM_CAMINHO)
        self.assertIn(f'e mais {21 - LIMITE_PARES_SEM_CAMINHO} par(es)', aviso)
        self.assertEqual(sum(1 for c in r['caminhos'] if c['tabelas'] is None), 21)



def _grafo_ficticio():
    """A e B ligadas por dois caminhos de 2 saltos: pela tabela HUB (ligada a
    muitas outras) e por X (pouco ligada). C fica isolada."""
    tabelas = ['A', 'B', 'X', 'HUB', 'C'] + [f'H{i}' for i in range(5)]
    cols = (['tabela,coluna,descricao'] + [f'{t},ID,Id de {t}' for t in tabelas]
            + ['A,ID_HUB,x', 'A,ID_X,x', 'B,ID_HUB,x', 'B,ID_X,x'] + [f'H{i},ID_HUB,x' for i in range(5)])
    rels = (['tabela_filha,campo_filho,tabela_mae,campo_mae,constraint,ordem',
             'A,ID_HUB,HUB,ID,FK_A_HUB,1', 'B,ID_HUB,HUB,ID,FK_B_HUB,1',
             'A,ID_X,X,ID,FK_A_X,1', 'B,ID_X,X,ID,FK_B_X,1']
            + [f'H{i},ID_HUB,HUB,ID,FK_H{i}_HUB,1' for i in range(5)])
    nl = '\n'
    return {'tabelas.csv': 'tabela,descricao' + nl + nl.join(f'{t},Tabela {t}' for t in tabelas) + nl,
            'colunas.csv': nl.join(cols) + nl, 'relacionamentos.csv': nl.join(rels) + nl}


class TestCaminhoDeJoin(unittest.TestCase):
    def test_menor_caminho_desvia_da_tabela_hub(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _detalhar(_base(tmp, _grafo_ficticio()), 'A', 'B')['caminhos'][0]
            self.assertEqual(c['tabelas'], ['A', 'X', 'B'])
            self.assertEqual(c['join'].split('\n'),
                             ['FROM A', 'INNER JOIN X ON A.ID_X = X.ID', 'INNER JOIN B ON B.ID_X = X.ID'])

    def test_sem_caminho_avisa_e_nao_inventa(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _detalhar(_base(tmp, _grafo_ficticio()), 'A', 'C')
            self.assertIsNone(r['caminhos'][0]['tabelas'])
            self.assertTrue(any('Sem caminho de FK' in a for a in r['aviso']))

    def test_uma_tabela_so_nao_tem_caminho(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_detalhar(_base(tmp, _grafo_ficticio()), 'A')['caminhos'], [])

    def test_texto_mostra_o_caminho(self):
        from nomi_nomi_no_mi.saida import formatar_detalhar_texto
        with tempfile.TemporaryDirectory() as tmp:
            txt = formatar_detalhar_texto(_detalhar(_base(tmp, _grafo_ficticio()), 'A', 'B'))
            self.assertIn('Caminho A -> B: A -> X -> B', txt)
            self.assertIn('    INNER JOIN X ON A.ID_X = X.ID', txt)

    def test_menor_caminho_limita_saltos_e_e_deterministico(self):
        from nomi_nomi_no_mi.grafo import menor_caminho
        linha = {'T0': {'T1'}, 'T1': {'T0', 'T2'}, 'T2': {'T1', 'T3'}, 'T3': {'T2'}}
        self.assertEqual(menor_caminho(linha, 'T0', 'T3'), ['T0', 'T1', 'T2', 'T3'])
        self.assertIsNone(menor_caminho(linha, 'T0', 'T3', max_saltos=2))
        empate = {'A': {'P', 'Q'}, 'P': {'A', 'B'}, 'Q': {'A', 'B'}, 'B': {'P', 'Q'}}
        self.assertEqual(menor_caminho(empate, 'A', 'B'), ['A', 'P', 'B'])   # mesmo custo: ordem alfabética


class TestAvisoVizinhosCortados(unittest.TestCase):
    def test_hub_da_fixture_avisa_o_corte_sem_mudar_as_expandidas(self):
        from casos.fixture_schema import gerar_fixture_db
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'f.db')
            gerar_fixture_db(db)
            motor = NomiNomiNoMi(db)
            try:
                r = motor.buscar('empresas cadastradas no sistema')
            finally:
                motor.fechar()
            avisos = [a for a in r['aviso'] if a.startswith('Vizinhos via FK cortados')]
            self.assertEqual(len(avisos), 1)
            self.assertEqual(int(avisos[0].split(': ')[1].split()[0]), len(r['expandidas']))
            self.assertEqual([t['tabela'] for t in r['expandidas']], sorted(t['tabela'] for t in r['expandidas']))



class TestAvisoCorteEmEmpate(unittest.TestCase):
    """Na fase 0 o desempate mostrou que o corte de 30 críticas divide grupos
    de score idêntico (562 entradas e saídas na fixture). O buscar avisa."""

    def _buscar(self, pedido):
        from casos.fixture_schema import gerar_fixture_db
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'f.db')
            gerar_fixture_db(db)
            motor = NomiNomiNoMi(db)
            try:
                return motor.buscar(pedido)
            finally:
                motor.fechar()

    def test_corte_no_meio_do_empate_avisa(self):
        r = self._buscar('abono lancado para o colaborador')
        avisos = [a for a in r['aviso'] if a.startswith('O corte de 30 tabelas críticas caiu no meio de um empate')]
        self.assertEqual(len(avisos), 1)
        self.assertEqual(len(r['criticas']), 30)
        ultimo = r['criticas'][-1]['score_dinamico']
        dentro = sum(1 for t in r['criticas'] if t['score_dinamico'] == ultimo)
        self.assertIn(f'; {dentro} entraram', avisos[0])
        self.assertTrue(r['aviso'][-1] == avisos[0])   # aviso novo vai no fim: os antigos ficam na mesma ordem

    def test_sem_empate_no_corte_nao_avisa(self):
        r = self._buscar('xyzwq inexistente blablabla')
        self.assertFalse(any('caiu no meio de um empate' in a for a in r['aviso']))


if __name__ == '__main__':
    unittest.main()
