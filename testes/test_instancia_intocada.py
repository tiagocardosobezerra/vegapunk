"""Guarda da instância: os comandos de MEDIÇÃO rodados contra uma CÓPIA da
base não podem mudar nenhum arquivo de egghead/ (nem criar um novo).

Cobre: atlas.py capturar e verificar (os dois domínios), pythagoras.py
avaliar (schema, fórmulas, soluções/cobertura) e o fluxo stella.py
solucionar e buscar --dominio schema, todos com --db apontando para a
cópia e SEM a variável VEGAPUNK_EGGHEAD (o caminho padrão é o que importa).
Três incidentes motivaram este teste: um comando de medição em cópia que
gravava ao lado da instância real. Só roda quando a instância existe.

O log do Shaka (`buscar --dominio formulas`) não entra: o domínio de
fórmulas não tem base para copiar e o log é da instância por definição.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _comum import SKILL

EGGHEAD = os.path.join(SKILL, 'egghead')
DB_REAL = os.path.join(EGGHEAD, 'punk_records.db')


def _retrato(pasta):
    """{arquivo: (sha256, mtime)}: o mtime pega até a regravação com os mesmos
    bytes (foi o que aconteceu no terceiro incidente)."""
    out = {}
    for raiz, _dirs, arqs in os.walk(pasta):
        for a in arqs:
            p = os.path.join(raiz, a)
            h = hashlib.sha256()
            with open(p, 'rb') as f:
                for bloco in iter(lambda: f.read(1 << 20), b''):
                    h.update(bloco)
            out[os.path.relpath(p, pasta)] = (h.hexdigest(), os.stat(p).st_mtime_ns)
    return out


class TestRetrato(unittest.TestCase):
    def test_regravar_com_os_mesmos_bytes_conta_como_mudanca(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = os.path.join(tmp, 'golden.json')
            with open(arq, 'w') as f:
                f.write('{}')
            antes = _retrato(tmp)
            os.utime(arq, ns=(os.stat(arq).st_atime_ns, os.stat(arq).st_mtime_ns + 10 ** 9))
            self.assertNotEqual(_retrato(tmp), antes)


def _retrato_das_instancias():
    """Retrato de egghead/ e de cada egghead-<nome>/ real (não as temporárias deste teste)."""
    out = {}
    for d in sorted(os.listdir(SKILL)):
        if (d == 'egghead' or d.startswith('egghead-')) and not d.startswith('egghead-qzguarda'):
            out.update({os.path.join(d, k): v for k, v in _retrato(os.path.join(SKILL, d)).items()})
    return out


@unittest.skipUnless(os.path.exists(DB_REAL), 'instância real ausente (cópia distribuível)')
class TestInstanciaIntocada(unittest.TestCase):
    def test_comando_com_instancia_temporaria_nao_toca_nas_reais(self):
        antes = _retrato_das_instancias()
        env = {k: v for k, v in os.environ.items() if k not in ('VEGAPUNK_EGGHEAD', 'VEGAPUNK_EGGHEAD_DB')}
        env['PYTHONIOENCODING'] = 'utf-8'
        irma = os.path.join(SKILL, 'egghead-qzguarda')
        try:
            os.makedirs(irma)
            shutil.copy2(DB_REAL, os.path.join(irma, 'punk_records.db'))
            for cmd in (['stella.py', '--instancia', 'qzguarda', 'buscar', '--dominio', 'schema', 'funcionários'],
                        ['stella.py', '--instancia', 'qzguarda', 'confirmar', '--dominio', 'schema', 'guarda', 'QZNAOEXISTE'],
                        ['stella.py', '--instancia', 'qzguarda', 'status'],
                        ['satelites/york.py', '--instancia', 'qzguarda', 'migrar', 'status']):
                r = subprocess.run([sys.executable, *cmd], cwd=SKILL, env=env, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace')
                self.assertIn(r.returncode, (0, 1), f'{cmd}: {r.stderr[-500:]}')
            depois = _retrato_das_instancias()
            mudou = sorted(k for k in set(antes) | set(depois) if antes.get(k) != depois.get(k))
            self.assertEqual(mudou, [], f'--instancia qzguarda mudou arquivo(s) de instância real: {mudou}')
            self.assertTrue(os.path.exists(os.path.join(irma, 'punk_records_log.jsonl')))   # o log foi para a irmã
        finally:
            shutil.rmtree(irma, ignore_errors=True)

    def test_comandos_de_medicao_em_copia_nao_tocam_em_egghead(self):
        antes = _retrato_das_instancias()
        env = {k: v for k, v in os.environ.items() if k not in ('VEGAPUNK_EGGHEAD', 'VEGAPUNK_EGGHEAD_DB')}
        env['PYTHONIOENCODING'] = 'utf-8'
        py = sys.executable
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'punk_records.db')
            shutil.copy2(DB_REAL, db)
            for nome in ('punk_records_log.jsonl', 'casos_solucao.json'):
                if os.path.exists(os.path.join(EGGHEAD, nome)):
                    shutil.copy2(os.path.join(EGGHEAD, nome), tmp)
            contrato = os.path.join(tmp, 'contrato.json')
            with open(contrato, 'w', encoding='utf-8') as f:
                json.dump({'pedido': 'guarda', 'intencoes': [
                    {'id': '1', 'texto': 'funcionários', 'dominio': 'schema'}]}, f)
            comandos = [
                ['satelites/atlas.py', 'capturar', '--db', db],
                ['satelites/atlas.py', 'verificar', '--classificar', '--db', db],
                ['satelites/pythagoras.py', 'avaliar', '--dominio', 'schema', '--db', db],
                ['satelites/pythagoras.py', 'avaliar', '--dominio', 'formulas'],
                ['satelites/pythagoras.py', 'avaliar', '--dominio', 'solucoes', '--db', db],
                ['satelites/pythagoras.py', 'avaliar', '--dominio', 'solucoes'],
                ['stella.py', '--db', db, 'solucionar', '--intencoes', contrato],
                ['stella.py', '--db', db, 'buscar', '--dominio', 'schema', 'funcionários'],
            ]
            for cmd in comandos:
                r = subprocess.run([py, *cmd], cwd=SKILL, env=env, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace')
                self.assertIn(r.returncode, (0, 1), f'{cmd}: {r.stderr[-500:]}')
                depois = _retrato_das_instancias()
                mudou = sorted(k for k in set(antes) | set(depois) if antes.get(k) != depois.get(k))
                self.assertEqual(mudou, [], f'{" ".join(cmd[:3])} mudou arquivo(s) de instância real: {mudou}')
            self.assertTrue(os.path.exists(os.path.join(tmp, 'atlas_formulas_golden.json')))  # foi para a cópia


if __name__ == '__main__':
    unittest.main()
