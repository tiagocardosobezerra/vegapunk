"""
Lembretes do fluxo: o próximo passo que o Claude não pode esquecer, escrito
pelo próprio motor no fim da saída, em vez de depender só da instrução do
SKILL.md (o `confirmar` no fim do fluxo, por exemplo, ficou esquecido na
maioria das buscas antes de virar lembrete).

Saem em stderr, com o prefixo `LEMBRETE:`, para não misturar com a saída
em JSON nem mudar o que o Atlas compara. Só biblioteca padrão: os dois
domínios usam este módulo sem depender um do outro.
"""

import json
import os
import re
import shutil
import sys

_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lembrar(texto):
    print(f'LEMBRETE: {texto}', file=sys.stderr)


def _config_do_cartao():
    """A configuração do Memory Card desta instância ({} se não há)."""
    pasta = os.environ.get('VEGAPUNK_EGGHEAD') or os.path.join(_SKILL, 'egghead')
    c = {}
    try:
        with open(os.path.join(pasta, 'memory_card.json'), encoding='utf-8') as f:
            c = json.load(f)
    except (OSError, ValueError):
        pass
    if os.environ.get('MEMORY_CARD_REPO'):
        c['repo'] = os.environ['MEMORY_CARD_REPO']
    if os.environ.get('MEMORY_CARD_DIR'):
        c['pasta'] = os.environ['MEMORY_CARD_DIR']
    return c if c.get('repo') else {}


def cartao_configurado():
    """True se esta instância tem um Memory Card E ele funciona aqui: a pasta
    do cartão existe nesta máquina e o `gh` está instalado. A configuração vem
    junto quando a skill é copiada (para o claude.ai, por exemplo), mas lá o
    cartão não funciona: o lembrete de salvar viraria uma promessa falsa."""
    c = _config_do_cartao()
    if not c:
        return False
    pasta = c.get('pasta') or os.path.join(os.path.expanduser('~'), c['repo'].split('/')[-1])
    if re.match(r'^[A-Za-z]:[\\/]', pasta) and os.name != 'nt':
        return False
    return os.path.isdir(os.path.join(pasta, '.git')) and shutil.which('gh') is not None


def cartao_em_outra_maquina():
    """True se há um cartão configurado que não funciona aqui."""
    return bool(_config_do_cartao()) and not cartao_configurado()


def lembrar_buscar_no_cartao(pedido):
    if cartao_configurado():
        lembrar(f'antes de escrever um relatório novo, veja se o Memory Card já tem um: '
                f'stella.py cartao buscar "{pedido}"')


def lembrar_confirmar(dominio):
    alvo = 'TABELA [TABELA ...]' if dominio == 'schema' else 'FUNCAO [FUNCAO ...] --contexto CTX'
    lembrar(f'no fim do fluxo, com o SQL ou a fórmula escrita, rode `stella.py confirmar --dominio {dominio} '
            f'"<pedido>" {alvo}` com o que foi de fato usado. Não pergunte: é o que alimenta a calibração.')


def lembrar_salvar_no_cartao():
    if cartao_configurado():
        lembrar('relatório entregue e aprovado? Ofereça salvar no Memory Card '
                '(stella.py cartao enviar: prévia primeiro, `--confirmar` só com o "sim"; salvar também '
                'confirma as tabelas do relatório).')
    elif cartao_em_outra_maquina():
        lembrar('o Memory Card desta instância não funciona aqui (falta a pasta do cartão ou o `gh`: é outra '
                'máquina, como o claude.ai). Não tente enviar nem configurar (`iniciar`): entregue o SQL e diga '
                'que salvar é pelo Claude Code na máquina do cartão.')


def lembrar_conferir_cartao():
    if cartao_configurado():
        lembrar('a base mudou: rode `stella.py cartao conferir` para ver se algum relatório salvo '
                'usa tabela ou coluna que sumiu.')
