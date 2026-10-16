"""Ligações do dicionário do sistema (fase 3-0b da v3): o relacionamentos.csv
do dicionário traz uma linha por ligação, com os campos em lista. O York grava
o número da ligação nas linhas da base; o detalhar usa esse agrupamento
(origem "dicionário"), abaixo da constraint e acima da chave da mãe. Também:
texto NULL de exportação vira vazio. Tudo com nomes fictícios."""

import os
import sqlite3
import tempfile
import unittest

import _comum  # noqa: F401
from nomi_nomi_no_mi.busca import NomiNomiNoMi
from nomi_nomi_no_mi.grafo import agrupar_fks
from punk_records import migracoes
from punk_records.enriquecimento import enriquecer
from punk_records.schema import importar_csvs
from test_estrutura_schema import _gravar

_TABELAS = 'tabela,descricao\nX_PAI,Pai\nX_FILHA,Filha\nX_OUTRA,NULL\n'
_COLUNAS = ('tabela,coluna,descricao,tipo,tamanho,precisao,escala,nulo,ordem,pk_ordem\n'
            'X_PAI,CODEMP,Empresa,int,4,10,0,0,1,1\nX_PAI,CODPAI,Pai,int,4,10,0,0,2,2\n'
            'X_PAI,CODALT,Alternativo,int,4,10,0,0,3,\n'
            'X_FILHA,CODEMP,Empresa,int,4,10,0,0,1,1\nX_FILHA,CODPAI,Pai,int,4,10,0,1,2,\n'
            'X_FILHA,CODPAI2,Outro pai,int,4,10,0,1,3,\nX_FILHA,CODALT,Alt,int,4,10,0,1,4,\n'
            'X_OUTRA,ID,NULL,int,4,10,0,0,1,1\n')
# uma linha por campo (como a base da v1): CODEMP aparece nas duas ligações para X_PAI
_RELS_POR_CAMPO = ('tabela_filha,campo_filho,tabela_mae,campo_mae\n'
                   'X_FILHA,CODEMP,X_PAI,CODEMP\nX_FILHA,CODPAI,X_PAI,CODPAI\n'
                   'X_FILHA,CODEMP,X_PAI,CODEMP\nX_FILHA,CODPAI2,X_PAI,CODPAI\n')
# o mesmo, no formato do dicionário: uma linha por ligação
_RELS_EM_LISTA = ('tabela_filha,campo_filho,tabela_mae,campo_mae\n'
                  'X_FILHA,"CODEMP,CODPAI",X_PAI,"CODEMP,CODPAI"\n'
                  'X_FILHA,"CODEMP,CODPAI2",X_PAI,"CODEMP,CODPAI"\n')


def _base(tmp, rels=_RELS_POR_CAMPO, migrar=True):
    _gravar(os.path.join(tmp, 'csv'), {'tabelas.csv': _TABELAS, 'colunas.csv': _COLUNAS, 'relacionamentos.csv': rels})
    db = os.path.join(tmp, 'b.db')
    r = importar_csvs(os.path.join(tmp, 'csv'), db)
    if migrar:
        migracoes.aplicar(db, destino_backup=os.path.join(tmp, 'bk'))
    return db, r


def _linhas(db, sql):
    c = sqlite3.connect(db)
    try:
        return c.execute(sql).fetchall()
    finally:
        c.close()


def _detalhar(db, *tabelas):
    motor = NomiNomiNoMi(db)
    try:
        return motor.detalhar(list(tabelas))
    finally:
        motor.fechar()


class TestNuloLiteral(unittest.TestCase):
    def test_importar_converte_texto_null_e_conta(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, r = _base(tmp, migrar=False)
            self.assertEqual(r['nulos_convertidos'], 2)
            self.assertEqual(_linhas(db, "SELECT descricao FROM tabelas WHERE tabela = 'X_OUTRA'"), [(None,)])
            self.assertEqual(_linhas(db, "SELECT descricao FROM colunas WHERE tabela = 'X_OUTRA'"), [('',)])

    def test_enriquecer_converte_texto_null_e_conta(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, _ = _base(tmp)
            _gravar(os.path.join(tmp, 'ext'), {'colunas.csv': 'tabela,coluna,descricao,tipo\nX_PAI,CODALT,,NULL\n'})
            r = enriquecer(os.path.join(tmp, 'ext'), db, os.path.join(tmp, 'bk'))
            self.assertEqual(r['nulos_convertidos'], 1)
            self.assertEqual(_linhas(db, "SELECT tipo FROM colunas WHERE coluna = 'CODALT' AND tabela = 'X_PAI'"),
                             [(None,)])


class TestImportarEmLista(unittest.TestCase):
    def test_lista_vira_uma_linha_por_campo_com_numero_da_ligacao(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, r = _base(tmp, rels=_RELS_EM_LISTA)
            self.assertEqual(r['ligacoes_do_dicionario'], 2)
            self.assertEqual(r['relacionamentos'], 4)
            self.assertEqual(_linhas(db, 'SELECT campo_filho, ligacao FROM relacionamentos ORDER BY rowid'),
                             [('CODEMP', 1), ('CODPAI', 1), ('CODEMP', 2), ('CODPAI2', 2)])

    def test_metricas_iguais_ao_formato_por_campo(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            sql = 'SELECT * FROM tabelas ORDER BY tabela'
            self.assertEqual(_linhas(_base(a)[0], sql), _linhas(_base(b, rels=_RELS_EM_LISTA)[0], sql))

    def test_listas_de_tamanho_diferente_sao_recusadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                _base(tmp, rels='tabela_filha,campo_filho,tabela_mae,campo_mae\nX_FILHA,"A,B",X_PAI,CODEMP\n')
            self.assertFalse(os.path.exists(os.path.join(tmp, 'b.db')))


class TestEnriquecerDicionario(unittest.TestCase):
    def _rodar(self, dicionario, rels=_RELS_POR_CAMPO):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(tmp))
        db, _ = _base(tmp, rels=rels)
        _gravar(os.path.join(tmp, 'dic'), {'relacionamentos.csv': dicionario})
        r = enriquecer(None, db, os.path.join(tmp, 'bk'), dir_dicionario=os.path.join(tmp, 'dic'))
        return db, r['dicionario']

    def test_cada_linha_da_base_serve_a_uma_ligacao_so(self):
        db, d = self._rodar(_RELS_EM_LISTA)
        self.assertEqual((d['ligacoes_no_csv'], d['ligacoes_aplicadas'], d['linhas_com_ligacao']), (2, 2, 4))
        self.assertEqual(sorted(_linhas(db, 'SELECT campo_filho, ligacao FROM relacionamentos')),
                         [('CODEMP', 1), ('CODEMP', 2), ('CODPAI', 1), ('CODPAI2', 2)])
        self.assertEqual(d['pares_compostos_agrupados_pelo_dicionario'], 1)

    def test_ligacao_que_nao_casa_inteira_nao_marca_nada(self):
        _, d = self._rodar(_RELS_EM_LISTA + 'X_FILHA,"CODEMP,CODALT",X_PAI,"CODEMP,CODALT"\n'
                           'X_FORA,"A,B",X_PAI,"CODEMP,CODPAI"\n')
        self.assertEqual((d['ligacoes_aplicadas'], d['ligacoes_nao_casadas_inteiras'],
                          d['ligacoes_sem_par_na_base']), (2, 1, 1))

    def test_versao_3_e_exigida(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, _ = _base(tmp, migrar=False)
            _gravar(os.path.join(tmp, 'dic'), {'relacionamentos.csv': _RELS_EM_LISTA})
            with self.assertRaises(RuntimeError):
                enriquecer(None, db, os.path.join(tmp, 'bk'), dir_dicionario=os.path.join(tmp, 'dic'))


def _rel(cf, cm, nome=None, lig=None, f='F', m='M'):
    return {'tabela_filha': f, 'campo_filho': cf, 'tabela_mae': m, 'campo_mae': cm,
            'constraint_nome': nome, 'ordem': None, 'ligacao': lig}


PK = {'K1': 1, 'K2': 2, 'K3': 3}


class TestDetalharComDicionario(unittest.TestCase):
    def _agrupar(self, linhas, pk=PK):
        return agrupar_fks(linhas, 'F', lambda t: pk if t == 'M' else {})

    def test_dicionario_promove_o_que_a_chave_nao_prova(self):
        fks, sem = self._agrupar([_rel('A', 'K1', lig=1), _rel('B', 'Z', lig=1)])
        self.assertEqual(sem, [])
        self.assertEqual([(f['origem'], f['cobre_chave_da_mae'], f['confirmado_pelo_dicionario']) for f in fks],
                         [('dicionário', False, True)])

    def test_dicionario_vence_a_chave_da_mae(self):
        # o caso real do F2b: duas ligações que se cruzam na PK da mãe, com C_B repetido
        linhas = [_rel('B', 'K1', lig=1), _rel('C', 'K3', lig=1), _rel('A', 'K2', lig=2), _rel('B', 'K1', lig=2)]
        fks, sem = self._agrupar(linhas)
        self.assertEqual(sem, [])
        self.assertEqual(sorted(f['on'] for f in fks), ['F.B = M.K1 AND F.A = M.K2', 'F.B = M.K1 AND F.C = M.K3'])
        self.assertEqual({f['origem'] for f in fks}, {'dicionário'})

    def test_sem_dicionario_a_linha_repetida_e_ambigua(self):
        linhas = [_rel('B', 'K1'), _rel('C', 'K3'), _rel('A', 'K2'), _rel('B', 'K1')]
        fks, sem = self._agrupar(linhas)
        self.assertEqual(fks, [])
        self.assertEqual({s['motivo'] for s in sem}, {'agrupamento_ambiguo'})

    def test_chave_da_mae_e_dicionario_concordam_mantem_a_fk(self):
        fks, _ = self._agrupar([_rel('A', 'K1', lig=7), _rel('B', 'K2', lig=7), _rel('C', 'K3', lig=7)])
        self.assertEqual([(f['origem'], f['confirmado_pelo_dicionario']) for f in fks],
                         [('ligação única + chave da mãe', True)])

    def test_constraint_x_dicionario_em_conflito_nenhum_vale(self):
        linhas = [_rel('A', 'K1', 'FK_X', 1), _rel('B', 'K2', 'FK_X', 2), _rel('C', 'K3', 'FK_X', 2)]
        fks, sem = self._agrupar(linhas)
        self.assertEqual(fks, [])
        self.assertEqual({s['motivo'] for s in sem}, {'conflito_constraint_dicionario'})

    def test_constraint_e_dicionario_concordam(self):
        linhas = [_rel('A', 'K1', 'FK_X', 4), _rel('B', 'K2', 'FK_X', 4), _rel('C', 'K3', 'FK_X', 4)]
        fks, sem = self._agrupar(linhas)
        self.assertEqual(sem, [])
        self.assertEqual([(f['origem'], f['confirmado_pelo_dicionario'], f['cobre_chave_da_mae']) for f in fks],
                         [('constraint', True, True)])

    def test_detalhar_na_base_com_avisos(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, _ = _base(tmp, rels=_RELS_EM_LISTA)
            r = _detalhar(db, 'X_FILHA')
            fks = r['tabelas']['X_FILHA']['fks']
            # chave da mãe e dicionário concordam: a FK de antes fica, confirmada pelo dicionário
            self.assertEqual([(f['origem'], f['cobre_chave_da_mae'], f['confirmado_pelo_dicionario']) for f in fks],
                             [('chave da mãe', True, True), ('chave da mãe', True, True)])
            self.assertEqual(r['tabelas']['X_FILHA']['fks_sem_constraint'], [])
            self.assertFalse(any('não usam exatamente a chave' in a for a in r['aviso']))


if __name__ == '__main__':
    unittest.main()
