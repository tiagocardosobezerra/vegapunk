"""
Laço de feedback: log de uso (`buscar` e `confirmar`) ao lado da base, com
rotação por tamanho, e leitura das confirmações reais.

Parte do Nomi Nomi no Mi, movida sem mudança de algoritmo do antigo
`scripts/nomi_nomi_no_mi.py` (fase 1 da v3).
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List

# ==============================================================================
# ITEM 1 — LOOP DE FEEDBACK (histórico de uso real, sem depender de
# ninguém escrever caso de teste à mão)
# ==============================================================================

def _caminho_historico(db_path: str) -> str:
    """Log fica ao lado do banco em uso (mesmo diretório de --db), não
    dentro do motor — assim cada cópia/ambiente acumula seu próprio
    histórico, do mesmo jeito que punk_records_pesos.json (item 6)."""
    return os.path.join(os.path.dirname(os.path.abspath(db_path)), 'punk_records_log.jsonl')


# Achado em auditoria: sem limite, punk_records_log.jsonl cresce
# indefinidamente em uso de longo prazo. Rotação simples: quando o
# arquivo passa de ~10MB, mantém só as últimas N linhas (as mais
# recentes são as mais úteis para pythagoras.py e para depuração).
# Checagem por tamanho de arquivo (barata) em vez de contar linhas a
# cada chamada.
LIMITE_HISTORICO_BYTES = 10 * 1024 * 1024
LINHAS_MANTIDAS_APOS_ROTACAO = 20_000


def _rotacionar_historico_se_necessario(caminho: str) -> None:
    try:
        if not os.path.exists(caminho) or os.path.getsize(caminho) <= LIMITE_HISTORICO_BYTES:
            return
        with open(caminho, 'r', encoding='utf-8') as f:
            linhas = f.readlines()
        if len(linhas) <= LINHAS_MANTIDAS_APOS_ROTACAO:
            return
        with open(caminho, 'w', encoding='utf-8') as f:
            f.writelines(linhas[-LINHAS_MANTIDAS_APOS_ROTACAO:])
    except OSError:
        pass  # best-effort — ver registrar_uso


def registrar_uso(db_path: str, registro: Dict) -> bool:
    """Grava uma linha de log (JSONL) por chamada de `buscar` ou
    `confirmar`. Best-effort: uma falha aqui (disco cheio, permissão)
    nunca deve derrubar o fluxo principal da skill, por isso o
    try/except silencioso — perder uma linha de telemetria é aceitável,
    quebrar uma consulta do usuário por causa dela não é. Faz rotação
    (ver `_rotacionar_historico_se_necessario`) antes de gravar, para o
    arquivo não crescer sem limite. Devolve False se não conseguiu gravar."""
    registro = dict(registro)
    registro['timestamp'] = datetime.now(timezone.utc).isoformat()
    caminho = _caminho_historico(db_path)
    try:
        _rotacionar_historico_se_necessario(caminho)
        with open(caminho, 'a', encoding='utf-8') as f:
            f.write(json.dumps(registro, ensure_ascii=False) + '\n')
    except OSError:
        return False
    return True


def confirmar(db_path: str, pedido: str, tabelas: List[str], **extra) -> bool:
    """Grava a confirmação de um pedido: `tabela_confirmada` é a principal
    (a primeira; é o que as leituras antigas usam) e `tabelas_confirmadas`,
    todas as do relatório. Usado pelo `confirmar` da Stella e pelo envio do
    Memory Card."""
    tabelas = list(dict.fromkeys(t.strip().upper() for t in tabelas if t and t.strip()))
    if not tabelas:
        return False
    reg = {'tipo': 'confirmacao', 'pedido': pedido, 'tabela_confirmada': tabelas[0]}
    if len(tabelas) > 1:
        reg['tabelas_confirmadas'] = tabelas
    reg.update(extra)
    return registrar_uso(db_path, reg)


def ler_historico_confirmado(db_path: str) -> List[Dict]:
    """Lê apenas as entradas de `confirmar` (pedido -> tabela realmente
    usada) do histórico — é isto que vira caso de teste rotulado real,
    sem que ninguém tenha escrito um caso à mão (ver
    satelites/pythagoras.py)."""
    caminho = _caminho_historico(db_path)
    if not os.path.exists(caminho):
        return []
    confirmados = []
    with open(caminho, 'r', encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                reg = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if reg.get('tipo') == 'confirmacao' and reg.get('pedido') and reg.get('tabela_confirmada'):
                confirmados.append(reg)
    return confirmados
