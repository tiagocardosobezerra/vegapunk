"""
Índice de colunas tokenizado, frequência de documento (IDF) e correção
aproximada (fuzzy) contra o vocabulário do schema.

Parte do Nomi Nomi no Mi, movida sem mudança de algoritmo do antigo
`scripts/nomi_nomi_no_mi.py` (fase 1 da v3).
"""

import difflib
import math
from collections import Counter
from typing import Dict, List

from dominios.schema.config import FUZZY_CUTOFF_PADRAO
from nomi_nomi_no_mi.texto import normalizar, radical, tokenizar


class IndiceMixin:
    """Índice e IDF do `NomiNomiNoMi` (ver busca.py)."""

    # ---- índice de colunas (para casar termos com descrições de negócio) ----
    def _carregar_indice(self):
        """Carrega o índice de colunas já TOKENIZADO (solução 2: matching
        por token exato, não substring) e pré-computa a frequência de
        documento (df) de cada token, para o peso IDF (solução 3).
        """
        if self._indice is not None:
            return
        self.cur.execute("SELECT tabela, coluna, descricao FROM colunas")
        indice = []
        df = Counter()
        for row in self.cur.fetchall():
            desc = row['descricao'] or ''
            tokens_desc = tokenizar(desc)
            # também indexamos o radical de cada token (tolerância a
            # plural leve), sem substituir o token original
            tokens_desc |= {radical(t) for t in tokens_desc}
            indice.append({
                'tabela': row['tabela'],
                'coluna': row['coluna'],
                'descricao': desc,
                '_tokens_desc': tokens_desc,
                '_norm_tabela': normalizar(row['tabela']),
            })
            for tk in tokens_desc:
                df[tk] += 1
        self._indice = indice
        self._df = df
        self._n_colunas = len(indice)
        # Item 3 (fuzzy fallback): vocabulário real do schema (só tokens
        # que de fato aparecem em alguma descrição), para comparar
        # termos do pedido que não bateram literalmente em nada.
        self._vocabulario = [t for t in df.keys() if len(t) >= 4]

    def _sugestoes_fuzzy(self, termos: List[str], cutoff: float = FUZZY_CUTOFF_PADRAO) -> Dict[str, str]:
        """Item 3 — fallback de correção aproximada (distância de edição
        via difflib, stdlib, sem dependência nova). SÓ é chamado pelo
        `buscar()` quando a busca literal (token exato + sinônimo +
        radical) não encontrou NADA — isto é: não compete com o match
        literal, só evita devolver vazio quando existe um termo do
        vocabulário real do schema visivelmente parecido (erro de
        digitação, abreviação, variação não coberta pelo stemmer leve).
        Nunca inventa um termo fora do vocabulário do schema."""
        self._carregar_indice()
        correcoes: Dict[str, str] = {}
        for termo in termos:
            termo_norm = normalizar(termo)
            if self._df.get(termo_norm, 0) > 0:
                continue  # já bate literalmente — fuzzy não se aplica aqui
            candidatos = difflib.get_close_matches(termo_norm, self._vocabulario, n=1, cutoff=cutoff)
            if candidatos and candidatos[0] != termo_norm:
                correcoes[termo] = candidatos[0]
        return correcoes

    def _idf(self, termo: str) -> float:
        """Peso IDF de um termo: raro no schema = peso alto, comum = peso
        baixo. `+1` no denominador evita divisão por zero para termos
        inéditos; `log` comprime a escala (mesmo racional do log nas
        conexões, solução 1)."""
        df_termo = self._df.get(termo, 0) if self._df else 0
        return math.log(self._n_colunas / (1 + df_termo)) if self._n_colunas else 1.0
