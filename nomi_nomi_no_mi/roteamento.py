"""
Roteamento entre instâncias: quanto do pedido cada base cobre.

Só leitura e sem log de uso (não chama `buscar`): para cada termo do
pedido, olha se ele, um radical ou um sinônimo da própria base aparece
como palavra de alguma descrição de coluna ou dentro de algum nome de
tabela (5+ letras, a mesma regra da busca). É evidência para escolher a
instância de um pedido; a escolha final continua do Claude e do usuário.
"""

from typing import Dict

from dominios.schema import config
from nomi_nomi_no_mi.busca import NomiNomiNoMi
from nomi_nomi_no_mi.texto import extrair_termos, normalizar, radical


def cobertura(db_path: str, pedido: str) -> Dict:
    """{'termos': [...], 'cobertos': [...], 'faltando': [...]} do pedido nesta base."""
    motor = NomiNomiNoMi(db_path)          # carrega os sinônimos desta base em config.SINONIMOS
    try:
        motor._carregar_indice()
        if any(len(t) < 4 and not t.isdigit() for t in extrair_termos(pedido)):
            motor._carregar_siglas()
        sinonimos = config.SINONIMOS
        config.SINONIMOS = {}
        try:
            originais = extrair_termos(pedido)  # sem expansão: os termos que o usuário escreveu
        finally:
            config.SINONIMOS = sinonimos
        vocabulario, nomes = set(), []
        for item in motor._indice:
            vocabulario |= item['_tokens_desc']
            nomes.append(item['_norm_tabela'])
        nomes = list(dict.fromkeys(nomes))
        cobertos, faltando, em_nome = [], [], []
        for t in originais:
            grupo, fila = {t}, [t]
            while fila:                    # sinônimos em cadeia, como na busca
                for s in sinonimos.get(fila.pop(), []):
                    if s not in grupo:
                        grupo.add(s)
                        fila.append(s)
            grupo |= {radical(g) for g in grupo}
            no_nome = any(len(g) >= 5 and any(g in n for n in nomes) for g in grupo)
            achou = no_nome or bool(grupo & vocabulario)
            (cobertos if achou else faltando).append(t)
            if no_nome:
                em_nome.append(t)    # o termo dá nome a tabela nesta base: evidência mais forte que descrição
        return {'termos': originais, 'cobertos': cobertos, 'faltando': faltando, 'em_nome_de_tabela': em_nome}
    finally:
        motor.fechar()


def assuntos_no_pedido(assuntos, pedido: str):
    """Assuntos do `instancia.json` que aparecem no pedido (sem acento e caixa)."""
    p = f' {normalizar(pedido)} '
    return [a for a in assuntos if f' {normalizar(a)} ' in p]
