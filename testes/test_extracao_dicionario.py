"""A extração do dicionário do pacote privado (relacionamentos.sql) exige as
DUAS pontas da ligação, filha e mãe, nos @prefixos da instância (fase 5a; a
v1 filtrava só a mãe e trazia filhas de módulos que não estão na base). Só
roda quando o pacote privado do dicionário existe na instância."""

import glob
import os
import re
import unittest

from _comum import SKILL

# o pacote privado do dicionário é o que traz a extração com @prefixos
SQLS = [p for p in glob.glob(os.path.join(SKILL, 'punk_records', 'pacotes', 'privado', '*', 'extracao',
                                          'relacionamentos.sql'))
        if '@prefixos' in open(p, encoding='utf-8').read()]


@unittest.skipUnless(SQLS, 'pacote privado do dicionário ausente (cópia distribuível)')
class TestDicionarioDuasPontas(unittest.TestCase):
    def test_filtra_filha_e_mae_pelos_prefixos(self):
        with open(SQLS[0], encoding='utf-8') as f:
            sql = re.sub(r'/\*.*?\*/', ' ', f.read(), flags=re.S)
        sql = re.sub(r'--[^\n]*', ' ', sql)
        where = re.search(r'\bWHERE\b(.*?)\)\s*AS\s+x', sql, re.S | re.I).group(1)
        for ponta in ('MASTERTABLE', 'CHILDTABLE'):
            self.assertRegex(where, rf'UPPER\(LEFT\(r\.{ponta},\s*1\)\)\s+IN\s+\(', f'{ponta} sem o filtro de prefixo')
        self.assertRegex(where, r'\bAND\b')


if __name__ == '__main__':
    unittest.main()
