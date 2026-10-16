"""Estrutura de coluna e constraint (fase 2 da v3): migração 002, CSVs com e
sem as colunas novas, e `enriquecer`, que só faz UPDATE em linhas que já
existem. Tudo com dados FICTÍCIOS em pasta temporária."""

import hashlib
import os
import sqlite3
import tempfile
import unittest

import _comum  # noqa: F401
from punk_records import migracoes
from punk_records.enriquecimento import enriquecer
from punk_records.schema import importar_csvs

_ESTRUTURA_ANTIGA = """
    CREATE TABLE tabelas (tabela TEXT PRIMARY KEY, descricao TEXT, score_relevancia REAL, ranking INTEGER,
                          tabelas_filhas INTEGER, tabelas_pais INTEGER, conexoes_totais INTEGER, tem_dados INTEGER);
    CREATE TABLE colunas (tabela TEXT, coluna TEXT, descricao TEXT);
    CREATE TABLE relacionamentos (tabela_filha TEXT, campo_filho TEXT, tabela_mae TEXT, campo_mae TEXT);
    CREATE TABLE sistemas (codigo_sistema TEXT PRIMARY KEY, nome_sistema TEXT, descricao TEXT);
    CREATE TABLE sinonimos (termo TEXT, sinonimo TEXT);
"""
_CSV_ANTIGO = {
    'tabelas.csv': 'tabela,descricao,tem_dados\nX_PAI,Pai de teste,1\nX_FILHA,Filha de teste,0\n',
    'colunas.csv': ('tabela,coluna,descricao\nX_PAI,CODEMP,Empresa\nX_PAI,CODPAI,Codigo do pai\n'
                    'X_FILHA,CODEMP,Empresa\nX_FILHA,CODPAI,Pai\nX_FILHA,CODPAI2,Outro pai\nX_FILHA,CODFILHA,Codigo\n'),
    'relacionamentos.csv': ('tabela_filha,campo_filho,tabela_mae,campo_mae\n'
                            'X_FILHA,CODEMP,X_PAI,CODEMP\nX_FILHA,CODPAI,X_PAI,CODPAI\n'
                            'X_FILHA,CODEMP,X_PAI,CODEMP\nX_FILHA,CODPAI2,X_PAI,CODPAI\n'),
}
# Mesma estrutura, vinda do tabelas.sql: duas FKs compostas da filha para o
# pai que repetem CODEMP (o caso que só o nome da constraint desambigua).
_CSV_ESTRUTURA = {
    'colunas.csv': ('tabela,coluna,descricao,tipo,tamanho,precisao,escala,nulo,ordem,pk_ordem\n'
                    'X_PAI,CODEMP,Empresa,SMALLINT,2,5,0,0,1,1\nX_PAI,CODPAI,Codigo do pai,varchar,10,0,0,0,2,2\n'
                    'X_FILHA,CODEMP,Empresa,smallint,2,5,0,0,1,1\nX_FILHA,CODPAI,Pai,varchar,10,0,0,1,2,\n'
                    'X_FILHA,CODPAI2,Outro pai,varchar,10,0,0,1,3,\nX_FILHA,CODFILHA,Codigo,int,4,10,0,0,4,2\n'
                    'X_NOVA,COLX,Tabela que não está na base,int,4,10,0,0,1,\n'),
    'relacionamentos.csv': ('tabela_filha,campo_filho,tabela_mae,campo_mae,constraint,ordem\n'
                            'X_FILHA,CODEMP,X_PAI,CODEMP,FK_FILHA_PAI,1\nX_FILHA,CODPAI,X_PAI,CODPAI,FK_FILHA_PAI,2\n'
                            'X_FILHA,CODEMP,X_PAI,CODEMP,FK_FILHA_PAI2,1\nX_FILHA,CODPAI2,X_PAI,CODPAI,FK_FILHA_PAI2,2\n'
                            'X_NOVA,COLX,X_PAI,CODPAI,FK_NOVA,1\n'),
}


def _gravar(pasta, arquivos):
    os.makedirs(pasta, exist_ok=True)
    for nome, texto in arquivos.items():
        with open(os.path.join(pasta, nome), 'w', encoding='utf-8', newline='') as f:
            f.write(texto)


def _linhas(db, sql):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def _hash_intocavel(db):
    """Tudo o que o enriquecimento NÃO pode mudar (descrições, pares de FK, métricas)."""
    h = hashlib.sha256()
    for sql in ('SELECT * FROM tabelas ORDER BY tabela',
                'SELECT tabela, coluna, descricao FROM colunas ORDER BY rowid',
                'SELECT tabela_filha, campo_filho, tabela_mae, campo_mae FROM relacionamentos ORDER BY rowid',
                'SELECT * FROM sistemas', 'SELECT * FROM sinonimos'):
        h.update(repr(_linhas(db, sql)).encode('utf-8'))
    return h.hexdigest()


class TestMigracao002(unittest.TestCase):
    def test_base_antiga_ganha_as_colunas_sem_mudar_conteudo(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'antiga.db')
            conn = sqlite3.connect(db)
            conn.executescript(_ESTRUTURA_ANTIGA)
            conn.execute("INSERT INTO colunas VALUES ('T', 'C', 'desc')")
            conn.execute("INSERT INTO relacionamentos VALUES ('A', 'X', 'B', 'X')")
            conn.commit()
            conn.close()
            r = migracoes.aplicar(db, destino_backup=os.path.join(tmp, 'bk'))
            self.assertEqual((r['antes'], r['depois']), (0, len(migracoes.MIGRACOES)))
            cols = [c[1] for c in _linhas(db, 'PRAGMA table_info(colunas)')]
            self.assertEqual(cols, ['tabela', 'coluna', 'descricao', 'tipo', 'tamanho', 'precisao', 'escala',
                                    'nulo', 'ordem', 'pk_ordem'])
            rels = [c[1] for c in _linhas(db, 'PRAGMA table_info(relacionamentos)')]
            self.assertEqual(rels[-5:], ['constraint_nome', 'ordem', 'ligacao', 'direcao', 'direcao_prova'])
            self.assertEqual(_linhas(db, 'SELECT * FROM relacionamentos_corrigidos'),
                             [('A', 'X', 'B', 'X', None, None, None, None, None)])     # 007: view sem marcação
            self.assertEqual(_linhas(db, 'SELECT * FROM colunas'), [('T', 'C', 'desc', None, None, None, None, None, None, None)])

    def test_base_nova_ja_nasce_com_as_colunas(self):
        with tempfile.TemporaryDirectory() as tmp:
            _gravar(os.path.join(tmp, 'csv'), _CSV_ANTIGO)
            db = os.path.join(tmp, 'nova.db')
            importar_csvs(os.path.join(tmp, 'csv'), db)
            r = migracoes.aplicar(db, destino_backup=os.path.join(tmp, 'bk'))
            self.assertEqual(r['depois'], len(migracoes.MIGRACOES))   # 002 e 003 são idempotentes: as colunas já existiam


class TestImportarCsv(unittest.TestCase):
    def test_csv_antigo_continua_aceito(self):
        with tempfile.TemporaryDirectory() as tmp:
            _gravar(os.path.join(tmp, 'csv'), _CSV_ANTIGO)
            db = os.path.join(tmp, 'b.db')
            importar_csvs(os.path.join(tmp, 'csv'), db)
            self.assertEqual(_linhas(db, 'SELECT DISTINCT tipo, nulo, pk_ordem FROM colunas'), [(None, None, None)])
            self.assertEqual(_linhas(db, 'SELECT DISTINCT constraint_nome FROM relacionamentos'), [(None,)])

    def test_csv_com_estrutura(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivos = dict(_CSV_ANTIGO)
            arquivos.update(_CSV_ESTRUTURA)
            arquivos['colunas.csv'] = '\n'.join(l for l in arquivos['colunas.csv'].split('\n') if 'X_NOVA' not in l)
            arquivos['relacionamentos.csv'] = '\n'.join(l for l in arquivos['relacionamentos.csv'].split('\n')
                                                        if 'X_NOVA' not in l)
            _gravar(os.path.join(tmp, 'csv'), arquivos)
            db = os.path.join(tmp, 'b.db')
            importar_csvs(os.path.join(tmp, 'csv'), db)
            self.assertEqual(_linhas(db, "SELECT tipo, tamanho, precisao, escala, nulo, ordem, pk_ordem FROM colunas "
                                         "WHERE tabela = 'X_PAI' AND coluna = 'CODEMP'"),
                             [('smallint', 2, 5, 0, 0, 1, 1)])
            self.assertEqual(_linhas(db, "SELECT pk_ordem FROM colunas WHERE coluna = 'CODPAI2'"), [(None,)])
            self.assertEqual(_linhas(db, 'SELECT constraint_nome, ordem FROM relacionamentos ORDER BY rowid'),
                             [('FK_FILHA_PAI', 1), ('FK_FILHA_PAI', 2), ('FK_FILHA_PAI2', 1), ('FK_FILHA_PAI2', 2)])


class TestEnriquecer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        _gravar(os.path.join(self.tmp, 'antigo'), _CSV_ANTIGO)
        _gravar(os.path.join(self.tmp, 'extracao'), _CSV_ESTRUTURA)
        self.db = os.path.join(self.tmp, 'b.db')
        importar_csvs(os.path.join(self.tmp, 'antigo'), self.db)
        self.bk = os.path.join(self.tmp, 'bk')

    def tearDown(self):
        self._tmp.cleanup()

    def test_recusa_base_sem_migracao_002(self):
        with self.assertRaises(RuntimeError):
            enriquecer(os.path.join(self.tmp, 'extracao'), self.db, self.bk)

    def test_so_atualiza_linhas_existentes_e_preserva_o_resto(self):
        migracoes.aplicar(self.db, destino_backup=self.bk)
        antes = _hash_intocavel(self.db)
        n_col = _linhas(self.db, 'SELECT COUNT(*) FROM colunas')[0][0]
        r = enriquecer(os.path.join(self.tmp, 'extracao'), self.db, self.bk)
        self.assertEqual(_hash_intocavel(self.db), antes)
        self.assertEqual(_linhas(self.db, 'SELECT COUNT(*) FROM colunas')[0][0], n_col)   # nada inserido
        self.assertEqual(r['colunas'], {'no_csv': 7, 'enriquecidas': 6, 'sem_correspondente_na_base': 1, 'na_base': 6})
        rel = r['relacionamentos']
        self.assertEqual((rel['linhas_logicas'], rel['linhas_logicas_com_constraint'], rel['linhas_logicas_sem_constraint']),
                         (4, 4, 0))
        self.assertEqual((rel['pares_logicos'], rel['pares_cobertos_inteiros'], rel['pares_compostos_cobertos_inteiros'],
                          rel['pares_ambiguos'], rel['pares_ambiguos_resolvidos']), (1, 1, 1, 1, 1))
        self.assertEqual((rel['fks_fisicas_no_csv'], rel['fks_fisicas_aplicadas'],
                          rel['fks_fisicas_fora_das_tabelas_da_base']), (3, 2, 1))
        # as duas linhas repetidas (X_FILHA.CODEMP -> X_PAI.CODEMP) recebem uma constraint cada
        self.assertEqual(sorted(_linhas(self.db, "SELECT constraint_nome FROM relacionamentos WHERE campo_filho = 'CODEMP'")),
                         [('FK_FILHA_PAI',), ('FK_FILHA_PAI2',)])
        self.assertEqual(_linhas(self.db, "SELECT tipo, nulo, pk_ordem FROM colunas WHERE tabela = 'X_FILHA' "
                                          "AND coluna = 'CODFILHA'"), [('int', 0, 2)])
        self.assertEqual(migracoes._sobras(self.db), [])

    def test_falha_devolve_a_copia(self):
        migracoes.aplicar(self.db, destino_backup=self.bk)
        with open(self.db, 'rb') as f:
            antes = f.read()
        with open(os.path.join(self.tmp, 'extracao', 'colunas.csv'), 'w', encoding='utf-8') as f:
            f.write('coluna_errada\nx\n')   # sem 'tabela': KeyError no meio da transação
        with self.assertRaises(KeyError):
            enriquecer(os.path.join(self.tmp, 'extracao'), self.db, self.bk)
        with open(self.db, 'rb') as f:
            self.assertEqual(f.read(), antes)


class TestEnriquecerPorConstraintInteira(unittest.TestCase):
    """Relacionamento lógico (dicionário, sem identificador) x FK física
    (catálogo, com nome): só aplica a FK que cabe inteira no par."""

    def _rodar(self, rels_fisicas, colunas=None):
        with tempfile.TemporaryDirectory() as tmp:
            _gravar(os.path.join(tmp, 'antigo'), _CSV_ANTIGO)
            db = os.path.join(tmp, 'b.db')
            importar_csvs(os.path.join(tmp, 'antigo'), db)
            migracoes.aplicar(db, destino_backup=os.path.join(tmp, 'bk'))
            arquivos = {'relacionamentos.csv': 'tabela_filha,campo_filho,tabela_mae,campo_mae,constraint,ordem\n' + rels_fisicas}
            if colunas:
                arquivos['colunas.csv'] = colunas
            _gravar(os.path.join(tmp, 'extracao'), arquivos)
            r = enriquecer(os.path.join(tmp, 'extracao'), db, os.path.join(tmp, 'bk'))
            return r, _linhas(db, 'SELECT campo_filho, constraint_nome FROM relacionamentos ORDER BY rowid')

    def test_fk_fisica_casada_so_em_parte_nao_marca_nada(self):
        r, linhas = self._rodar('X_FILHA,CODEMP,X_PAI,CODEMP,FK_TRES,1\nX_FILHA,CODPAI,X_PAI,CODPAI,FK_TRES,2\n'
                                'X_FILHA,CODFILHA,X_PAI,CODPAI,FK_TRES,3\n')
        self.assertEqual({c for _, c in linhas}, {None})
        self.assertEqual(r['relacionamentos']['fks_fisicas_casadas_so_em_parte_nao_aplicadas'], 1)
        self.assertEqual(r['relacionamentos']['pares_sem_constraint'], 1)

    def test_caixa_dos_nomes_nao_importa(self):
        r, linhas = self._rodar('x_filha,codemp,x_pai,codemp,FK_A,1\nx_filha,codpai,x_pai,codpai,FK_A,2\n',
                                colunas='tabela,coluna,descricao,tipo\nx_filha,codpai,,varchar\n')
        self.assertEqual([c for _, c in linhas].count('FK_A'), 2)
        self.assertEqual(r['colunas']['enriquecidas'], 1)
        # o par só ficou em parte (CODEMP repetido e CODPAI2 sem FK física): cobertura em parte, com aviso no detalhar
        self.assertEqual(r['relacionamentos']['pares_cobertos_em_parte'], 1)
        self.assertEqual(r['relacionamentos']['linhas_logicas_sem_constraint'], 2)

    def test_fk_fisica_ausente_do_dicionario_e_contada(self):
        r, _ = self._rodar('X_PAI,CODPAI,X_FILHA,CODFILHA,FK_INVERTIDA,1\n')
        self.assertEqual(r['relacionamentos']['fks_fisicas_entre_tabelas_da_base_ausentes_do_dicionario'], 1)


class TestLeitorDeExtracao(unittest.TestCase):
    def test_utf16_do_ssms_com_rodape_e_espacos(self):
        from punk_records.schema import ler_csv_extracao
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'colunas.csv')
            texto = ('tabela,coluna,descricao   \r\n"X_PAI","CODPAI","Código do pai, com vírgula"   \r\n\r\n'
                     'Completion time: 2026-10-15T23:59:00.0000000-03:00\r\n')
            with open(p, 'wb') as f:
                f.write(texto.encode('utf-16'))
            cab, linhas = ler_csv_extracao(p)
            self.assertEqual(cab, ['tabela', 'coluna', 'descricao'])
            self.assertEqual(linhas, [{'tabela': 'X_PAI', 'coluna': 'CODPAI', 'descricao': 'Código do pai, com vírgula'}])

    def test_grade_do_ssms_linha_inteira_entre_aspas(self):
        """'Save Results As' da grade: cada linha de dados vira um campo só,
        entre aspas, com as aspas internas duplicadas. O leitor desembrulha."""
        from punk_records.schema import ler_csv_extracao
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'relacionamentos.csv')
            linhas = ['tabela_filha,campo_filho,tabela_mae,campo_mae,constraint,ordem',
                      '"""X_FILHA"",""CODEMP"",""X_PAI"",""CODEMP"",""FK_A"",1"',
                      '"""X_FILHA"",""COD,COM VIRGULA"",""X_PAI"",""CODPAI"",""FK_A"",2"']
            with open(p, 'w', encoding='utf-8-sig', newline='') as f:
                f.write('\r\n'.join(linhas) + '\r\n')
            _, regs = ler_csv_extracao(p)
            self.assertEqual([(r['campo_filho'], r['constraint'], r['ordem']) for r in regs],
                             [('CODEMP', 'FK_A', '1'), ('COD,COM VIRGULA', 'FK_A', '2')])

    def test_csv_normal_nao_e_desembrulhado(self):
        from punk_records.schema import ler_csv_extracao
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'colunas.csv')
            with open(p, 'w', encoding='utf-8', newline='') as f:
                f.write('tabela,coluna,descricao\n"X","Y","texto, com virgula"\n')
            _, regs = ler_csv_extracao(p)
            self.assertEqual(regs, [{'tabela': 'X', 'coluna': 'Y', 'descricao': 'texto, com virgula'}])

    def test_csv_so_com_cabecalho_e_recusado(self):
        from punk_records.schema import CsvVazioError
        with tempfile.TemporaryDirectory() as tmp:
            arquivos = dict(_CSV_ANTIGO)
            arquivos['colunas.csv'] = 'tabela,coluna,descricao\n'
            _gravar(os.path.join(tmp, 'csv'), arquivos)
            with self.assertRaises(CsvVazioError) as ctx:
                importar_csvs(os.path.join(tmp, 'csv'), os.path.join(tmp, 'b.db'))
            self.assertIn('só com cabeçalho', str(ctx.exception))
            self.assertFalse(os.path.exists(os.path.join(tmp, 'b.db')))   # nada gravado

    def test_enriquecer_recusa_csv_vazio_sem_mexer_na_base(self):
        from punk_records.schema import CsvVazioError
        with tempfile.TemporaryDirectory() as tmp:
            _gravar(os.path.join(tmp, 'antigo'), _CSV_ANTIGO)
            db = os.path.join(tmp, 'b.db')
            importar_csvs(os.path.join(tmp, 'antigo'), db)
            migracoes.aplicar(db, destino_backup=os.path.join(tmp, 'bk'))
            with open(db, 'rb') as f:
                antes = f.read()
            _gravar(os.path.join(tmp, 'extracao'), {'relacionamentos.csv': ''})
            with self.assertRaises(CsvVazioError):
                enriquecer(os.path.join(tmp, 'extracao'), db, os.path.join(tmp, 'bk'))
            with open(db, 'rb') as f:
                self.assertEqual(f.read(), antes)


if __name__ == '__main__':
    unittest.main()
