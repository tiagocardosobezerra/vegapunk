"""
Log de uso do motor de fórmulas — o mesmo laço de feedback do motor de
consultas (`buscar` registra, `confirmar` fecha o laço), mas em arquivo
PRÓPRIO: nunca escreve em `punk_records_log.jsonl`.

O log contém pedidos reais da instalação, então mora na camada PRIVADA
(`egghead/shaka_log.jsonl`, a instância local, fora do controle de versão)
e alimenta `satelites/pythagoras.py` (grupo "uso_real", só medição — nunca é
usado para calibrar sem passar pelos grupos rotulados).
"""

import json
import os
from datetime import datetime, timezone

from . import conhecimento as kb

NOME_ARQUIVO = 'shaka_log.jsonl'
# Testes e execuções de diagnóstico apontam o log para outro lugar, para não
# poluir o histórico real (o mesmo cuidado que o atlas.py tem com o log de consultas).
VAR_AMBIENTE_LOG = 'VEGAPUNK_SHAKA_LOG'
# Mesma instância local do domínio schema (VEGAPUNK_EGGHEAD), sem importar aquele domínio.
RAIZ_EGGHEAD = os.environ.get('VEGAPUNK_EGGHEAD') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'egghead')
# Mesma política de rotação do motor de consultas.
LIMITE_BYTES = 10 * 1024 * 1024
LINHAS_MANTIDAS = 20_000


def caminho(raiz_conhecimento=None):
    if os.environ.get(VAR_AMBIENTE_LOG):
        return os.path.abspath(os.environ[VAR_AMBIENTE_LOG])
    if raiz_conhecimento is None:
        # instância local (Egghead), ao lado da base e do log de consultas
        return os.path.abspath(os.path.join(RAIZ_EGGHEAD, NOME_ARQUIVO))
    return os.path.join(os.path.abspath(raiz_conhecimento), 'privado', NOME_ARQUIVO)


def _rotacionar(arq):
    if os.path.exists(arq) and os.path.getsize(arq) > LIMITE_BYTES:
        with open(arq, encoding='utf-8') as f:
            linhas = f.readlines()[-LINHAS_MANTIDAS:]
        with open(arq, 'w', encoding='utf-8') as f:
            f.writelines(linhas)


def registrar(registro, raiz_conhecimento=None):
    arq = caminho(raiz_conhecimento)
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    _rotacionar(arq)
    registro = dict(registro, timestamp=datetime.now(timezone.utc).isoformat())
    with open(arq, 'a', encoding='utf-8') as f:
        f.write(json.dumps(registro, ensure_ascii=False) + '\n')


def ler_confirmacoes(raiz_conhecimento=None):
    """Confirmações reais (pedido, contexto, função usada) — mais recente vence."""
    arq = caminho(raiz_conhecimento)
    if not os.path.exists(arq):
        return []
    por_chave = {}
    with open(arq, encoding='utf-8') as f:
        for linha in f:
            try:
                r = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if r.get('tipo') == 'confirmacao':
                por_chave[(r['pedido'], r.get('contexto'))] = r
    return list(por_chave.values())
