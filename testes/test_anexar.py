"""Log de uso em paralelo: vários processos gravando o mesmo JSONL ao mesmo
tempo não perdem nem misturam linha (antes, no Windows, uma linha sumia)."""

import concurrent.futures as cf
import json
import os
import subprocess
import sys
import tempfile
import unittest

from _comum import SKILL

COD = ("import sys; sys.path.insert(0, sys.argv[3]); from dominios.anexar import anexar_linha\n"
       "for i in range(100): anexar_linha(sys.argv[1], '{\"p\": \"' + sys.argv[2] + '\", \"i\": ' + str(i) + '}')")


class TestAnexarEmParalelo(unittest.TestCase):
    def test_processos_em_paralelo_nao_perdem_linha(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, 'log.jsonl')
            with cf.ThreadPoolExecutor(6) as ex:
                list(ex.map(lambda k: subprocess.run([sys.executable, '-c', COD, log, str(k), SKILL], check=True),
                            range(6)))
            linhas = open(log, encoding='utf-8').read().splitlines()
            self.assertEqual(len(linhas), 600)
            pares = {(r['p'], r['i']) for r in map(json.loads, linhas)}
            self.assertEqual(len(pares), 600)


if __name__ == '__main__':
    unittest.main()
