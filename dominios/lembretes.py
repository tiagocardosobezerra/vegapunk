"""
Lembretes do fluxo: o próximo passo que o Claude não pode esquecer, escrito
pelo próprio motor no fim da saída, em vez de depender só da instrução do
SKILL.md (o `confirmar` no fim do fluxo, por exemplo, ficou esquecido na
maioria das buscas antes de virar lembrete).

Saem em stderr, com o prefixo `LEMBRETE:`, para não misturar com a saída
em JSON nem mudar o que o Atlas compara. Só biblioteca padrão: os dois
domínios usam este módulo sem depender um do outro.
"""

import os
import sys

_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lembrar(texto):
    print(f'LEMBRETE: {texto}', file=sys.stderr)


def cartao_configurado():
    """True se esta instância tem um Memory Card configurado (o lembrete do
    cartão só aparece para quem criou um)."""
    if os.environ.get('MEMORY_CARD_REPO'):
        return True
    pasta = os.environ.get('VEGAPUNK_EGGHEAD') or os.path.join(_SKILL, 'egghead')
    return os.path.exists(os.path.join(pasta, 'memory_card.json'))


def lembrar_buscar_no_cartao(pedido):
    if cartao_configurado():
        lembrar(f'antes de escrever um relatório novo, veja se o Memory Card já tem um: '
                f'satelites/memory_card.py buscar "{pedido}"')


def lembrar_confirmar(dominio):
    alvo = 'TABELA' if dominio == 'schema' else 'FUNCAO [FUNCAO ...] --contexto CTX'
    lembrar(f'no fim do fluxo, com o SQL ou a fórmula escrita, rode `stella.py confirmar --dominio {dominio} '
            f'"<pedido>" {alvo}` com o que foi de fato usado. Não pergunte: é o que alimenta a calibração.')


def lembrar_salvar_no_cartao():
    if cartao_configurado():
        lembrar('relatório entregue e aprovado? Ofereça salvar no Memory Card '
                '(satelites/memory_card.py enviar: prévia primeiro, `--confirmar` só com o "sim").')


def lembrar_conferir_cartao():
    if cartao_configurado():
        lembrar('a base mudou: rode `satelites/memory_card.py conferir` para ver se algum relatório salvo '
                'usa tabela ou coluna que sumiu.')
