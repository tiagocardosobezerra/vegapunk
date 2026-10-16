"""
Distribuição: a ÚNICA saída do Vegapunk para fora da instância.

Este repositório nunca vai para um remoto (o hook pre-push recusa qualquer
push; ver `ferramentas/instalar_hooks.py` na raiz do repositório). O que é
publicável sai daqui: uma pasta SEPARADA, fora do repositório, sem `.git`,
com exatamente a superfície distribuível (`dominios/isolamento.py`,
`_superficie_distribuivel`), que funciona como allowlist por regra. É o
"Vegapunk" do PLANO-V3.md: o motor com a Punk Records vazia.

Antes de copiar, o isolamento inteiro tem que estar verde. Depois de copiar,
a pasta gerada é conferida: qualquer `.git` ou qualquer arquivo fora da
allowlist faz a distribuição FALHAR, e a pasta gerada é apagada.

Uso: python3 satelites/atlas.py distribuir --destino <pasta nova, fora do repositório>
"""

import os
import shutil

from dominios.formulas import conhecimento as kb
from dominios.isolamento import _superficie_distribuivel, verificar_isolamento


class DistribuicaoRecusada(RuntimeError):
    """A distribuição não pode ser gerada (ou a gerada não passou na conferência)."""


def lista_distribuivel(raiz_skill, raiz_conhecimento=None):
    """Caminhos relativos à pasta da skill que podem sair (a allowlist)."""
    raiz_skill = os.path.abspath(raiz_skill)
    raiz_con = os.path.abspath(raiz_conhecimento or kb.RAIZ_CONHECIMENTO)
    return sorted(os.path.relpath(a, raiz_skill) for a in _superficie_distribuivel(raiz_skill, raiz_con)
                  if os.path.abspath(a).startswith(raiz_skill + os.sep))


def _raiz_do_repositorio(caminho):
    atual = os.path.abspath(caminho)
    while True:
        if os.path.exists(os.path.join(atual, '.git')):
            return atual
        pai = os.path.dirname(atual)
        if pai == atual:
            return None
        atual = pai


def conferir_distribuicao(destino, permitidos):
    """[problema] da pasta gerada: `.git` em qualquer nível ou arquivo fora
    da allowlist `permitidos` (caminhos relativos)."""
    permitidos = {os.path.normcase(p) for p in permitidos}
    problemas = []
    for d, subdirs, arqs in os.walk(destino):
        for nome in subdirs + arqs:
            if nome == '.git':
                problemas.append(f'{os.path.relpath(os.path.join(d, nome), destino)}: .git na distribuição')
        for a in arqs:
            rel = os.path.relpath(os.path.join(d, a), destino)
            if a != '.git' and os.path.normcase(rel) not in permitidos:
                problemas.append(f'{rel}: fora da allowlist')
    return problemas


def distribuir(raiz_skill, destino, raiz_conhecimento=None, verificar=True, _antes_de_conferir=None):
    """Gera a distribuição em `destino` (pasta nova ou vazia, fora do
    repositório). Devolve {'destino', 'arquivos'}. Levanta
    DistribuicaoRecusada sem deixar nada para trás."""
    raiz_skill = os.path.abspath(raiz_skill)
    destino = os.path.abspath(destino)
    repo = _raiz_do_repositorio(raiz_skill)
    if repo and (destino == repo or destino.startswith(repo + os.sep)):
        raise DistribuicaoRecusada(f'o destino fica dentro do repositório ({repo}); use uma pasta fora dele')
    # vale também sem .git (ex.: uma cópia distribuída): a cópia entraria nela mesma
    if destino == raiz_skill or destino.startswith(raiz_skill + os.sep):
        raise DistribuicaoRecusada(f'o destino fica dentro da pasta da skill ({raiz_skill}); use uma pasta fora dela')
    if os.path.exists(destino) and (not os.path.isdir(destino) or os.listdir(destino)):
        raise DistribuicaoRecusada(f'o destino já existe e não está vazio: {destino}')
    if verificar:
        from dominios.nomes_reais import verificar_na_superficie
        r = verificar_isolamento(raiz_skill, raiz_conhecimento)
        r['verificacoes'].append(verificar_na_superficie(raiz_skill, raiz_conhecimento))
        falhas = [c['verificacao'] for c in r['verificacoes'] if not c['ok']]
        if falhas:
            raise DistribuicaoRecusada('isolamento vermelho: ' + '; '.join(falhas))
    permitidos = lista_distribuivel(raiz_skill, raiz_conhecimento)
    criou = not os.path.exists(destino)
    os.makedirs(destino, exist_ok=True)
    try:
        for rel in permitidos:
            alvo = os.path.join(destino, rel)
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            shutil.copy2(os.path.join(raiz_skill, rel), alvo)
        if _antes_de_conferir:          # só para o teste plantar um problema
            _antes_de_conferir(destino)
        problemas = conferir_distribuicao(destino, permitidos)
        if problemas:
            raise DistribuicaoRecusada('a pasta gerada não passou na conferência: ' + '; '.join(problemas[:20]))
    except Exception:
        if criou:
            shutil.rmtree(destino, ignore_errors=True)
        else:
            for nome in os.listdir(destino):
                c = os.path.join(destino, nome)
                shutil.rmtree(c, ignore_errors=True) if os.path.isdir(c) else os.remove(c)
        raise
    return {'destino': destino, 'arquivos': len(permitidos)}
