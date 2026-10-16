"""
Normalização e tokenização de texto PT-BR para o motor de fórmulas.

`normalizar` e `formatar_numero_ptbr` vêm do núcleo comum
(`nomi_nomi_no_mi/texto_comum.py`), porque são idênticas nos dois domínios.
O resto continua próprio de propósito: radical, tokenização e stop words
têm regras diferentes das do schema, e compartilhá-las mudaria o ranking de
um domínio a cada ajuste no outro (ver `referencias/historico.md`).
"""

import re

from nomi_nomi_no_mi.texto_comum import formatar_numero_ptbr, normalizar  # noqa: F401  (núcleo comum)

STOP_WORDS = {
    'de', 'da', 'do', 'das', 'dos', 'em', 'para', 'por', 'com', 'sem',
    'no', 'na', 'nos', 'nas', 'ao', 'aos', 'pelo', 'pela', 'pelos', 'pelas',
    'a', 'o', 'e', 'ou', 'um', 'uma', 'os', 'as', 'uns', 'umas',
    'que', 'se', 'qual', 'quais', 'como', 'quando', 'onde', 'seu', 'sua',
    'preciso', 'quero', 'gostaria', 'fazer', 'faca', 'faz', 'criar', 'crie',
    'montar', 'monte', 'gerar', 'gere', 'escrever', 'escreva', 'retornar',
    'formula', 'formulas', 'funcao', 'funcoes', 'valor', 'usando', 'utilizando',
    'retorne', 'retorna', 'calcular', 'calcule', 'obter', 'pegar', 'pegue',
    'me', 'eu', 'isso', 'este', 'esta', 'esse', 'essa', 'ele', 'ela',
}


_SUFIXOS = ('coes', 'soes', 'oes', 'aes', 'ais', 'eis', 'ois', 'res', 'is', 'ns', 's')


def radical(termo):
    """Stemming leve de plural (conservador)."""
    if len(termo) <= 4:
        return termo
    for suf in _SUFIXOS:
        if termo.endswith(suf) and len(termo) - len(suf) >= 4:
            base = termo[:-len(suf)]
            if suf in ('coes', 'soes', 'oes'):
                base += 'o'           # funcoes -> funcao ~ 'funca'+'o'
            return base
    return termo


def tokens(texto, minimo=3):
    """Tokens normalizados (>= `minimo` caracteres, sem stop words), em ordem."""
    out = []
    for t in re.findall(r'[a-z0-9]+', normalizar(texto)):
        if len(t) >= minimo and t not in STOP_WORDS:
            out.append(t)
    return out


def radicais(texto, minimo=3):
    return [radical(t) for t in tokens(texto, minimo)]


