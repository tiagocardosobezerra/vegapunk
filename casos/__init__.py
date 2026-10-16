"""
Casos públicos e fictícios do Vegapunk (distribuíveis).

- `consultas_fixture.json`: casos rotulados do domínio schema contra a
  fixture fictícia;
- `fixture_schema.py`: gerador da fixture fictícia do schema ("Sistema Aurora").

Os casos de fórmulas de cada fornecedor ficam no próprio pacote de
conhecimento (`casos/` dentro do pacote).
"""

import json
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
GRUPOS_CONSULTAS = ('calibracao', 'heldout', 'validacao_cega')


def casos_consultas(caminho=None):
    """{grupo: [(pedido, {tabelas esperadas}, top_n, comentário), ...]}, na
    ordem do arquivo."""
    with open(caminho or os.path.join(AQUI, 'consultas_fixture.json'), encoding='utf-8') as f:
        dados = json.load(f)
    return {g: [(c['pedido'], set(c['esperadas']), c['top'], c['comentario']) for c in dados[g]]
            for g in GRUPOS_CONSULTAS}
