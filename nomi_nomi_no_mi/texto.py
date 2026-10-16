"""
Texto do domínio schema: normalização, ordinais por extenso, radical,
tokenização, extração de termos do pedido (com expansão de sinônimos) e
formatação numérica pt-BR.

Parte do Nomi Nomi no Mi, movida sem mudança de algoritmo do antigo
`scripts/nomi_nomi_no_mi.py` (fase 1 da v3).
"""

import re
import unicodedata
from typing import Dict, List, Set

from dominios.schema import config
from nomi_nomi_no_mi.texto_comum import formatar_numero_ptbr, normalizar  # noqa: F401  (núcleo comum)

# ==============================================================================
# STOP WORDS
# ==============================================================================

STOP_WORDS = set([
    'de', 'da', 'do', 'das', 'dos', 'em', 'para', 'por', 'com',
    'no', 'na', 'nos', 'nas', 'ao', 'aos', 'pelo', 'pela',
    'a', 'o', 'e', 'ou', 'um', 'uma', 'os', 'as',
    'é', 'são', 'ser', 'foi', 'foram', 'sendo', 'devem',
    'que', 'se', 'qual', 'como', 'caso', 'quando', 'onde',
    'preciso', 'quero', 'gostaria', 'traga', 'trazer', 'mostre', 'mostrar',
    'tabela', 'tabelas', 'dados', 'informacao', 'informacoes'
])


# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================

_ORDINAIS_POR_EXTENSO = {
    'decimo terceiro': '13', 'décimo terceiro': '13',
    'decimo quarto': '14', 'décimo quarto': '14',
}


def _substituir_ordinais_por_extenso(texto_normalizado: str) -> str:
    """Muitos schemas de negócio escrevem '13º Salário', nunca 'décimo
    terceiro salário' — então converte a forma por extenso pro numeral
    ANTES de tokenizar, senão o número (só 2 dígitos) nunca passaria no
    filtro de 4+ caracteres e a busca nunca bateria em tabelas como
    (hipoteticamente) 'FPROVISAODECIMOTERCEIRO'. Não há dataset nenhum
    embutido neste pacote — este é só um nome ilustrativo do tipo de
    tabela que esse tratamento resolve; ver casos/fixture_schema.py, que
    gera sua própria fixture fictícia sob demanda para exercitar isso."""
    for extenso, numero in _ORDINAIS_POR_EXTENSO.items():
        texto_normalizado = texto_normalizado.replace(normalizar(extenso), numero)
    return texto_normalizado


_SUFIXOS_PLURAL = ('oes', 'aes', 'ais', 'eis', 'is', 'ns', 's')


def radical(termo: str) -> str:
    """Stemming bem leve: reduz plurais comuns em PT-BR a uma forma
    aproximada, só para permitir comparação tolerante a plural/singular
    (ex.: 'funcionarios' ~ 'funcionario'). Não é um stemmer linguístico
    completo — é deliberadamente conservador para não gerar colisões
    falsas entre palavras diferentes.
    """
    if len(termo) <= 4:
        return termo
    for suf in _SUFIXOS_PLURAL:
        if termo.endswith(suf) and len(termo) - len(suf) >= 4:
            return termo[:-len(suf)]
    return termo


def tokenizar(texto: str) -> Set[str]:
    """Extrai o conjunto de tokens normalizados (4+ caracteres, ou
    números isolados de 2-3 dígitos como '13' em '13º Salário') de um
    texto."""
    return set(re.findall(r'\w{4,}|(?<!\d)\d{2,3}(?!\d)', normalizar(texto)))


def extrair_termos(pedido: str) -> List[str]:
    """Extrai termos relevantes (4+ caracteres, sem stop words) de um
    pedido, e EXPANDE com sinônimos de domínio conhecidos (solução 4).
    A ordem é preservada e sem duplicatas.
    """
    texto_norm = _substituir_ordinais_por_extenso(normalizar(pedido))
    termos_norm = re.findall(r'\w{4,}|(?<!\d)\d{2,3}(?!\d)', texto_norm)
    termos = [t for t in termos_norm if t not in STOP_WORDS]

    # Expande sinônimos EM CADEIA (ponto fixo), não só uma passada: um
    # sinônimo pode por sua vez ter outro sinônimo (ex.: "desligamento"
    # -> "rescisao" -> "recisao", o typo real do banco). Limitado a 5
    # iterações como trava de segurança contra ciclos no dicionário.
    expandidos = list(termos)
    for _ in range(5):
        novos = []
        for t in expandidos:
            for sinonimo in config.SINONIMOS.get(t, []):
                if sinonimo not in expandidos and sinonimo not in novos:
                    novos.append(sinonimo)
        if not novos:
            break
        expandidos.extend(novos)
    return expandidos
