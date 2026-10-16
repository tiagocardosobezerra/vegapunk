"""O conjunto CEGO da fase 4 está congelado: o sha256 do arquivo tem de ser o
registrado no ESTADO-V3.md. Só roda quando a instância existe."""

import hashlib
import os
import re
import unittest

from _comum import SKILL

CEGO = os.path.join(SKILL, 'egghead', 'casos_solucao_cegos.json')
ESTADO = os.path.join(SKILL, 'egghead', 'ESTADO-V3.md')


@unittest.skipUnless(os.path.exists(CEGO) and os.path.exists(ESTADO), 'instância sem o conjunto cego')
class TestConjuntoCegoCongelado(unittest.TestCase):
    def test_hash_igual_ao_registrado(self):
        with open(ESTADO, encoding='utf-8') as f:
            m = re.search(r'CONJUNTO CEGO DA FASE 4:.*?sha256 ([0-9a-f]{64})', f.read(), re.S)
        self.assertIsNotNone(m, 'sha256 do conjunto cego não registrado no ESTADO-V3.md')
        with open(CEGO, 'rb') as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), m.group(1),
                             'o conjunto cego mudou depois de congelado')


if __name__ == '__main__':
    unittest.main()
