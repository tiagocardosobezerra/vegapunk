"""Fase 3b: contrato v2 do mapa e compilação pelo York (migração 004).
O York recusa o arquivo inteiro (nada gravado) quando aparece campo fora do
contrato, valor que parece conteúdo de registro, tabela ou coluna que não
existe, chave incompleta ou ligação sem prova. O papel de cada coluna vem da
descrição, nunca do nome. Tudo com nomes fictícios."""

import copy
import json
import os
import sqlite3
import tempfile
import unittest

from _comum import SKILL
from casos.fixture_schema import gerar_fixture_db
from punk_records import migracoes
from punk_records.mapa import MapaRecusado, compilar, conferir_contrato
from punk_records.schema import importar_csvs
from test_estrutura_schema import _gravar

_CSVS = {
    'tabelas.csv': 'tabela,descricao\nX_EVENTO,Eventos\nX_FORMULA,Formulas\nX_TIPO,Tipos\n',
    'colunas.csv': ('tabela,coluna,descricao,tipo,tamanho,precisao,escala,nulo,ordem,pk_ordem\n'
                    'X_EVENTO,CODEMP,Empresa,int,4,10,0,0,1,1\nX_EVENTO,CODIGO,Código do evento,int,4,10,0,0,2,2\n'
                    'X_EVENTO,NOMEEVT,Descrição do evento,varchar,40,0,0,1,3,\n'
                    'X_EVENTO,APLIC,Aplicação,char,1,0,0,1,4,\n'
                    'X_EVENTO,FORMVALOR,Código da fórmula de valor,varchar,10,0,0,1,5,\n'
                    'X_EVENTO,FORMCRIT,Código da fórmula de crédito,varchar,10,0,0,1,6,\n'
                    'X_EVENTO,FORMHIST,Complemento do histórico,varchar,10,0,0,1,7,\n'
                    'X_EVENTO,OUTRO,Observação livre,varchar,10,0,0,1,8,\n'
                    'X_FORMULA,CODEMP,Empresa,int,4,10,0,0,1,1\nX_FORMULA,APLIC,Aplicação,char,1,0,0,0,2,2\n'
                    'X_FORMULA,CODIGO,Código da fórmula,varchar,10,0,0,0,3,3\n'
                    'X_FORMULA,TITULO,Título da fórmula,varchar,60,0,0,1,4,\n'
                    'X_TIPO,CODTIPO,Código do tipo,int,4,10,0,0,1,\n'),
    'relacionamentos.csv': ('tabela_filha,campo_filho,tabela_mae,campo_mae\n'
                            'X_EVENTO,CODEMP,X_FORMULA,CODEMP\nX_EVENTO,APLIC,X_FORMULA,APLIC\n'
                            'X_EVENTO,FORMHIST,X_FORMULA,CODIGO\n'),
}

_MAPA = {
    'versao': 2, 'ficticio': True,
    'formulas': {'tabela': 'X_FORMULA', 'chave': ['CODEMP', 'APLIC', 'CODIGO'], 'colunas': {'titulo': 'TITULO'}},
    'cadastros': [{
        'cadastro': 'evento', 'tabela': 'X_EVENTO', 'chave': ['CODEMP', 'CODIGO'], 'coluna_codigo': 'CODIGO',
        'coluna_descricao': 'NOMEEVT', 'rotulos_parametro': ['CÓDIGO DO EVENTO', 'CÓD. DO EVENTO'], 'funcoes': ['EVT'],
        'ligacoes_formula': {'tabela': 'X_FORMULA', 'chave_destino': ['CODEMP', 'APLIC', 'CODIGO'],
                             'colunas_origem_extra': ['CODEMP', 'APLIC'],
                             'colunas_por_papel': {'valor': 'FORMVALOR', 'critica': 'FORMCRIT',
                                                   'complemento_historico': 'FORMHIST'}},
    }],
}


def _base(tmp):
    _gravar(os.path.join(tmp, 'csv'), _CSVS)
    db = os.path.join(tmp, 'b.db')
    importar_csvs(os.path.join(tmp, 'csv'), db)
    migracoes.aplicar(db, destino_backup=os.path.join(tmp, 'bk'))
    return db


def _compilar(tmp, mapa, db=None):
    db = db or _base(tmp)
    p = os.path.join(tmp, 'mapa.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(mapa, f, ensure_ascii=False)
    return db, compilar(p, db, os.path.join(tmp, 'bk'))


def _linhas(db, sql):
    c = sqlite3.connect(db)
    try:
        return c.execute(sql).fetchall()
    finally:
        c.close()


class TestCompilacao(unittest.TestCase):
    def test_compila_e_marca_o_papel_pela_descricao(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, r = _compilar(tmp, _MAPA)
            self.assertEqual((r['mapa_cadastros'], r['mapa_rotulos'], r['mapa_funcoes']), (1, 2, 1))
            # FORMCRIT foi declarada "crítica", mas a descrição diz "crédito": divergente, a ligação continua
            self.assertEqual([(d['coluna'], d['papel']) for d in r['divergencias']], [('FORMCRIT', 'critica')])
            provas = dict(_linhas(db, "SELECT coluna, prova FROM mapa_papeis WHERE parte = 'ligacao_formula'"))
            self.assertEqual(provas, {'FORMVALOR': 'descricao', 'FORMCRIT': 'descricao', 'FORMHIST': 'fk'})
            self.assertEqual(_linhas(db, "SELECT valor FROM meta WHERE chave = 'mapa:ficticio'"), [('1',)])

    def test_rotulo_com_prova_documental_guarda_a_fonte(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = copy.deepcopy(_MAPA)
            m['cadastros'][0]['rotulos_parametro'].append(
                {'rotulo': 'CÓD. EVT', 'prova': 'documentacao', 'fonte': 'exemplo da documentação fictícia'})
            db, _ = _compilar(tmp, m)
            self.assertEqual(_linhas(db, 'SELECT rotulo, prova, fonte FROM mapa_rotulos ORDER BY rowid'),
                             [('CÓDIGO DO EVENTO', 'declarado', None), ('CÓD. DO EVENTO', 'declarado', None),
                              ('CÓD. EVT', 'documentacao', 'exemplo da documentação fictícia')])

    def test_papel_confirmado_pelo_usuario_deixa_de_ser_divergente(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = copy.deepcopy(_MAPA)
            m['cadastros'][0]['ligacoes_formula']['papeis_confirmados'] = {
                'critica': {'prova': 'usuario', 'fonte': 'artigo fictício sobre fórmulas de crítica',
                            'data': '2026-10-16', 'descricao_da_origem_errada': True}}
            db, r = _compilar(tmp, m)
            self.assertEqual(r['divergencias'], [])
            self.assertEqual([(d['coluna'], d['confirmado_em'], d['descricao_errada']) for d in r['resolvidos_pelo_usuario']],
                             [('FORMCRIT', '2026-10-16', 1)])
            self.assertEqual(_linhas(db, "SELECT papel_divergente, prova_do_papel, fonte_do_papel FROM mapa_papeis "
                                         "WHERE coluna = 'FORMCRIT'"),
                             [(0, 'usuario', 'artigo fictício sobre fórmulas de crítica')])

    def test_compilar_de_novo_substitui_o_mapa(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, _ = _compilar(tmp, _MAPA)
            m = copy.deepcopy(_MAPA)
            del m['formulas']
            _compilar(tmp, m, db)
            self.assertEqual(_linhas(db, 'SELECT COUNT(*) FROM mapa_estruturas'), [(1,)])
            self.assertEqual(_linhas(db, 'SELECT COUNT(*) FROM mapa_cadastros'), [(1,)])

    def test_exige_a_versao_minima(self):
        with tempfile.TemporaryDirectory() as tmp:
            _gravar(os.path.join(tmp, 'csv'), _CSVS)
            db = os.path.join(tmp, 'b.db')
            importar_csvs(os.path.join(tmp, 'csv'), db)
            with self.assertRaises(RuntimeError):
                _compilar(tmp, _MAPA, db)

    def test_mapa_ficticio_publico_compila_contra_a_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'f.db')
            gerar_fixture_db(db)
            migracoes.aplicar(db, destino_backup=os.path.join(tmp, 'bk'))
            r = compilar(os.path.join(SKILL, 'casos', 'mapa_ficticio.json'), db, os.path.join(tmp, 'bk'))
            self.assertEqual(r['mapa_cadastros'], 3)
            self.assertEqual(r['divergencias'], [])


class TestRecusas(unittest.TestCase):
    """Recusas plantadas: o arquivo inteiro é recusado e a base não muda."""

    def _recusa(self, alterar, trecho):
        with tempfile.TemporaryDirectory() as tmp:
            db = _base(tmp)
            with open(db, 'rb') as f:
                antes = f.read()
            m = copy.deepcopy(_MAPA)
            alterar(m)
            with self.assertRaises(MapaRecusado) as ctx:
                _compilar(tmp, m, db)
            self.assertTrue(any(trecho in e for e in ctx.exception.erros), ctx.exception.erros)
            with open(db, 'rb') as f:
                self.assertEqual(f.read(), antes)

    def test_linhas_de_cadastro_num_campo_fora_do_contrato(self):
        self._recusa(lambda m: m['cadastros'][0].update(
            {'exemplos': [{'CODIGO': '0001', 'NOMEEVT': 'SALARIO BASE'}]}), "campo fora do contrato: 'exemplos'")

    def test_rotulo_com_codigo_e_descricao_de_registro(self):
        self._recusa(lambda m: m['cadastros'][0]['rotulos_parametro'].append('0001 - SALARIO BASE'), 'recusado')

    def test_rotulo_com_sql(self):
        self._recusa(lambda m: m['cadastros'][0]['rotulos_parametro'].append('SELECT CODIGO FROM X_EVENTO'),
                     'parece texto de SQL')

    def test_rotulo_com_formula(self):
        self._recusa(lambda m: m['cadastros'][0]['rotulos_parametro'].append('SOMA(A, B)'), 'parece texto de fórmula')

    def test_numero_onde_se_espera_nome(self):
        self._recusa(lambda m: m['cadastros'][0].update({'coluna_codigo': 1}), 'esperado um nome')

    def test_campo_extra_na_raiz(self):
        self._recusa(lambda m: m.update({'registros': []}), "campo fora do contrato: 'registros'")

    def test_tabela_que_nao_existe(self):
        self._recusa(lambda m: m['cadastros'][0].update({'tabela': 'X_NAO_EXISTE'}), 'tabela não existe')

    def test_coluna_que_nao_existe(self):
        self._recusa(lambda m: m['cadastros'][0].update({'coluna_descricao': 'NAOEXISTE'}), 'coluna não existe')

    def test_chave_incompleta(self):
        self._recusa(lambda m: m['cadastros'][0].update({'chave': ['CODIGO']}), 'chave incompleta')

    def test_tabela_sem_pk_conhecida(self):
        def alterar(m):
            m['cadastros'].append({'cadastro': 'tipo', 'tabela': 'X_TIPO', 'chave': ['CODTIPO'],
                                   'coluna_codigo': 'CODTIPO', 'rotulos_parametro': ['CÓDIGO DO TIPO']})
        self._recusa(alterar, 'não tem PK conhecida')

    def test_ligacao_com_formula_sem_prova(self):
        self._recusa(lambda m: m['cadastros'][0]['ligacoes_formula']['colunas_por_papel'].update({'outro': 'OUTRO'}),
                     'sem prova')

    def test_rotulo_com_prova_que_nao_e_documentacao(self):
        self._recusa(lambda m: m['cadastros'][0]['rotulos_parametro'].append(
            {'rotulo': 'CÓD. EVT', 'prova': 'dialeto', 'fonte': 'regra nossa'}), 'esperado um de')

    def _confirmacao(self, **troca):
        conf = {'prova': 'usuario', 'fonte': 'artigo fictício', 'data': '2026-10-16', **troca}
        return lambda m: m['cadastros'][0]['ligacoes_formula'].update({'papeis_confirmados': {'critica': conf}})

    def test_papel_confirmado_com_prova_que_nao_e_do_usuario(self):
        self._recusa(self._confirmacao(prova='descricao'), "esperado um de ['usuario']")

    def test_papel_confirmado_com_data_errada(self):
        self._recusa(self._confirmacao(data='ontem'), 'esperada uma data')

    def test_papel_confirmado_que_nao_existe_na_ligacao(self):
        self._recusa(lambda m: m['cadastros'][0]['ligacoes_formula'].update({'papeis_confirmados': {
            'inexistente': {'prova': 'usuario', 'fonte': 'x', 'data': '2026-10-16'}}}), 'não está em colunas_por_papel')

    def test_versao_errada(self):
        self.assertTrue(any('versao' in e for e in conferir_contrato({'versao': 1})))


if __name__ == '__main__':
    unittest.main()
