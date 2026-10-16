"""
Núcleo de texto comum aos dois domínios (schema e fórmulas).

Só entra aqui o que é IDÊNTICO nos dois: `normalizar` (minúsculas, sem
acento) e `formatar_numero_ptbr`. Antes da fase 1 da v3 cada domínio tinha a
sua cópia; a prova de que as duas eram iguais (66.621 textos reais e de
pacotes, 400.024 formatações, zero diferenças) e os goldens do Atlas
idênticos nos dois domínios estão em `referencias/historico.md`.

O resto do texto continua separado de propósito: radical, tokenização e
stop words são diferentes em cada domínio, e unificá-los mudaria o ranking
(ver `referencias/historico.md`, "Núcleo de texto compartilhado").

Não importa nada de nenhum domínio: os dois podem importar este módulo sem
depender um do outro.
"""

import unicodedata


def normalizar(texto: str) -> str:
    """Lowercase + remove acentuação, para comparação tolerante a acentos/caixa."""
    if not texto:
        return ''
    nfkd = unicodedata.normalize('NFKD', texto)
    sem_acento = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


def formatar_numero_ptbr(valor: float, casas: int = 2) -> str:
    """Formata número no padrão pt-BR: '.' como separador de milhar e ',' como decimal.

    Ex.: 12345.6 -> '12.345,60'. Usado em toda a saída textual do motor
    (nunca o padrão en-US de vírgula-milhar/ponto-decimal).
    """
    texto = f"{valor:,.{casas}f}"
    texto = texto.replace(',', '§').replace('.', ',').replace('§', '.')
    return texto
