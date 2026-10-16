"""O gabarito do schema real da fase 5 (calibração × cego) está congelado: o
sha256 do arquivo tem de ser o registrado no ESTADO-V3.md. Só roda quando a
instância existe."""

import hashlib
import json
import os
import re
import unittest

from _comum import SKILL

GABARITO = os.path.join(SKILL, 'egghead', 'gabarito_schema_real_fase5.json')
ESTADO = os.path.join(SKILL, 'egghead', 'ESTADO-V3.md')


@unittest.skipUnless(os.path.exists(GABARITO) and os.path.exists(ESTADO), 'instância sem o gabarito do schema real')
class TestGabaritoSchemaRealCongelado(unittest.TestCase):
    def test_hash_igual_ao_registrado(self):
        with open(ESTADO, encoding='utf-8') as f:
            m = re.search(r'GABARITO DO SCHEMA REAL DA FASE 5:.*?sha256 \**([0-9a-f]{64})', f.read(), re.S)
        self.assertIsNotNone(m, 'sha256 do gabarito do schema real não registrado no ESTADO-V3.md')
        with open(GABARITO, 'rb') as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), m.group(1),
                             'o gabarito do schema real mudou depois de congelado')

    def test_cego_e_calibracao_disjuntos(self):
        with open(GABARITO, encoding='utf-8') as f:
            g = json.load(f)
        cal = {c['id'] for c in g['calibracao_casos']}
        cego = {c['id'] for c in g['cego_casos']}
        self.assertFalse(cal & cego)
        self.assertEqual(sorted(cego), g['cego'])


if __name__ == '__main__':
    unittest.main()
