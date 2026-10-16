"""Utilidades compartilhadas pelos testes (caminhos, carga da fixture fictícia)."""

import hashlib
import json
import os
import sys

TESTES = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(TESTES)
SCRIPTS = os.path.join(SKILL, 'satelites')
FIXTURE_FORMULAS = os.path.join(SKILL, 'casos', 'fixtures', 'formulas')
DB_REAL = os.path.join(SKILL, 'egghead', 'punk_records.db')
LOG_REAL = os.path.join(SKILL, 'egghead', 'punk_records_log.jsonl')

for _p in (SCRIPTS, SKILL):   # SKILL: pacotes da raiz (dominios, nomi_nomi_no_mi, punk_records, casos)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 16), b''):
            h.update(bloco)
    return h.hexdigest()


def base_ficticia(somente_publico=False):
    from dominios.formulas.conhecimento import carregar
    return carregar(FIXTURE_FORMULAS, somente_publico=somente_publico)


def _ler_json(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def _gravar_json(caminho, dados):
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False)
