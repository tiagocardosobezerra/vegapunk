"""punk_records/extracao/{tabelas,colunas,relacionamentos}.sql leem SÓ o
catálogo do SQL Server.

As consultas não podem ser executadas aqui (não há SQL Server); estes
testes garantem por análise estática a regra de ouro e o que torna a
extração confiável: nenhum SELECT em tabela de usuário, nenhuma escrita,
nenhuma sintaxe de SQLCMD (roda igual no SSMS), nenhum nome de banco,
schema explícito por @esquema, falha ruidosa quando o schema não tem
tabelas, e cabeçalhos que o York sabe importar."""

import os
import re
import unittest

from _comum import SKILL

PASTA = os.path.join(SKILL, 'punk_records', 'extracao')
ARQUIVOS = {'tabelas.sql': 'tabelas.csv', 'colunas.sql': 'colunas.csv', 'relacionamentos.sql': 'relacionamentos.csv'}


def _sem_comentarios_e_literais(sql):
    sql = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.S)
    sql = re.sub(r'--[^\n]*', ' ', sql)
    return re.sub(r"N?'(?:[^']|'')*'", "''", sql)


class TestExtracaoSoCatalogo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brutos, cls.sqls = {}, {}
        for nome in ARQUIVOS:
            with open(os.path.join(PASTA, nome), encoding='utf-8') as f:
                cls.brutos[nome] = f.read()
            cls.sqls[nome] = _sem_comentarios_e_literais(cls.brutos[nome])

    def test_so_os_tres_arquivos(self):
        self.assertEqual(sorted(a for a in os.listdir(PASTA) if a.endswith('.sql')), sorted(ARQUIVOS))

    def test_from_e_join_so_no_catalogo(self):
        for nome, sql in self.sqls.items():
            alvos = re.findall(r'\b(?:FROM|JOIN)\s+([^\s,;]+)', sql, flags=re.I)
            self.assertTrue(alvos, nome)
            fora = [a for a in alvos if not (a.startswith('(') or re.match(r'(?i)(sys|INFORMATION_SCHEMA)\.', a))]
            self.assertEqual(fora, [], f'{nome}: objeto fora do catálogo do SQL Server')

    def test_sem_escrita_nem_execucao(self):
        for nome, sql in self.sqls.items():
            proibidos = re.findall(r'\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|CREATE|ALTER|EXEC|EXECUTE|'
                                   r'OPENROWSET|OPENQUERY|BULK|GRANT|DENY|REVOKE|INTO|USE)\b', sql, flags=re.I)
            self.assertEqual(proibidos, [], nome)
            self.assertNotRegex(sql, r'SELECT\s+\*', nome)

    def test_sem_sqlcmd_e_sem_nome_de_banco(self):
        for nome, bruto in self.brutos.items():
            self.assertEqual(re.findall(r'^\s*:\w+', bruto, flags=re.M), [], f'{nome}: comando de SQLCMD')
            self.assertNotIn('$(', self.sqls[nome], f'{nome}: variável de SQLCMD')
            self.assertNotRegex(self.sqls[nome], r'\b\w+\.\w+\.\w+\b', f'{nome}: nome de três partes (banco.schema.objeto)')

    def test_schema_explicito_e_falha_quando_vazio(self):
        for nome, sql in self.sqls.items():
            self.assertRegex(self.brutos[nome], r"DECLARE @esquema sysname = N'dbo';", nome)
            self.assertIn('s.name = @esquema', sql + self.brutos[nome], nome)
            self.assertRegex(sql, r'IF NOT EXISTS \(SELECT 1 FROM sys\.(tables|objects)', nome)
            self.assertIn('RAISERROR', sql, nome)

    def test_tabelas_e_colunas_trazem_views_com_a_variavel(self):
        for nome in ('tabelas.sql', 'colunas.sql'):
            self.assertIn("DECLARE @objeto  char(1) = 'U';", self.brutos[nome], nome)
            self.assertEqual(self.sqls[nome].count('t.type = @objeto'), 2, nome)
            self.assertNotIn('FROM sys.tables AS t\n', self.sqls[nome], nome)

    def test_relacionamento_com_os_dois_lados_no_schema(self):
        sql = self.sqls['relacionamentos.sql']
        self.assertIn('sf.name = @esquema', sql)
        self.assertIn('sm.name = @esquema', sql)

    def test_cabecalhos_aceitos_pelo_york(self):
        from punk_records.schema import COLUNAS_OBRIGATORIAS_CSV
        for nome, csv in ARQUIVOS.items():
            cab = re.findall(r"CAST\(N'([a-z_,]+)' AS nvarchar\(max\)\)", self.brutos[nome])
            self.assertEqual(len(cab), 1, nome)
            self.assertLessEqual(COLUNAS_OBRIGATORIAS_CSV[csv], set(cab[0].split(',')), nome)
            self.assertNotIn('total_registros', cab[0])   # nunca contagem de linhas


if __name__ == '__main__':
    unittest.main()
