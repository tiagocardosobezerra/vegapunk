"""
Instâncias locais da Punk Records: `egghead/` (a padrão) e `egghead-<nome>/`
(uma por banco, ex.: `egghead-outro-banco/`), todas fora do controle de versão.

A pasta ativa é `VEGAPUNK_EGGHEAD`, senão `egghead/`; a base é a
`punk_records.db` dela. `VEGAPUNK_EGGHEAD_DB` (o arquivo de uma base) só
troca a base que o Memory Card confere; a busca usa `--db`.

`--instancia NOME` (stella.py e york.py) só preenche `VEGAPUNK_EGGHEAD`
antes de qualquer módulo do motor ser importado, porque vários deles leem a
variável na importação.
"""

import json
import os
import re
import sqlite3
import sys

RAIZ_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PADRAO = 'egghead'
PREFIXO = 'egghead-'
ARQUIVO_BASE = 'punk_records.db'
ARQUIVO_DESCRICAO = 'instancia.json'     # {"descricao": "...", "assuntos": ["...", ...]}
FLAG = '--instancia'
_NOME_VALIDO = re.compile(r'^[A-Za-z0-9_-]+$')


def abrir_leitura(db):
    """Conexão só de leitura; o caminho vai como URI com `%`, `?` e `#`
    escapados (sem eles, um desses no caminho quebra a URI)."""
    caminho = os.path.abspath(db).replace('%', '%25').replace('?', '%3F').replace('#', '%23')
    return sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)


def pasta(nome=None):
    """Pasta da instância `nome` (None ou vazio = a padrão)."""
    return os.path.join(RAIZ_SKILL, PREFIXO + nome if nome else PADRAO)


def pasta_ativa():
    return os.environ.get('VEGAPUNK_EGGHEAD') or pasta()


def caminho_base():
    """A base de schema da instância ativa (regra do docstring)."""
    return os.environ.get('VEGAPUNK_EGGHEAD_DB') or os.path.join(pasta_ativa(), ARQUIVO_BASE)


def nome_da_pasta(caminho):
    base = os.path.basename(os.path.normpath(caminho))
    return base[len(PREFIXO):] if base.startswith(PREFIXO) else base


def _descricao(pasta_instancia):
    """{descricao, assuntos} do `instancia.json` da pasta (opcional, fora do
    git): o que diz ao Claude qual instância serve a cada pedido."""
    caminho = os.path.join(pasta_instancia, ARQUIVO_DESCRICAO)
    try:
        with open(caminho, encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {'descricao': '', 'assuntos': []}
    return {'descricao': str(d.get('descricao', '')), 'assuntos': [str(x) for x in d.get('assuntos', [])]}


def listar():
    """[{nome, pasta, base, existe, ativa, tabelas, colunas}] de cada instância com pasta."""
    ativa = os.path.normcase(os.path.abspath(caminho_base()))
    nomes = sorted(d for d in os.listdir(RAIZ_SKILL)
                   if os.path.isdir(os.path.join(RAIZ_SKILL, d)) and (d == PADRAO or d.startswith(PREFIXO)))
    saida = []
    for d in nomes:
        p = os.path.join(RAIZ_SKILL, d)
        db = os.path.join(p, ARQUIVO_BASE)
        item = {'nome': PADRAO if d == PADRAO else d[len(PREFIXO):], 'pasta': p, 'base': db,
                'existe': os.path.exists(db), 'ativa': os.path.normcase(os.path.abspath(db)) == ativa,
                'tabelas': None, 'colunas': None, **_descricao(p)}
        if item['existe']:
            try:
                conn = abrir_leitura(db)
                try:
                    item['tabelas'] = conn.execute('SELECT COUNT(*) FROM tabelas').fetchone()[0]
                    item['colunas'] = conn.execute('SELECT COUNT(*) FROM colunas').fetchone()[0]
                finally:
                    conn.close()
            except sqlite3.DatabaseError:      # base vazia, corrompida ou de outro formato: lista assim mesmo
                pass
        saida.append(item)
    return saida


def bases_existentes():
    return [i['base'] for i in listar() if i['existe']]


def ativar(argv):
    """Tira `--instancia NOME` (ou `--instancia=NOME`) de `argv`, aponta
    `VEGAPUNK_EGGHEAD` para a pasta e devolve o resto. Pasta inexistente ou
    `VEGAPUNK_EGGHEAD_DB` já definida: ValueError."""
    resto, nome, i = [], None, 0
    while i < len(argv):
        arg = argv[i]
        if arg == FLAG:
            if i + 1 >= len(argv):
                raise ValueError(f'{FLAG} pede o nome da instância (ex.: {FLAG} outro-banco)')
            nome, i = argv[i + 1], i + 2
            continue
        if arg.startswith(FLAG + '='):
            nome = arg.split('=', 1)[1]
        else:
            resto.append(arg)
        i += 1
    if nome is None:
        return resto
    if not _NOME_VALIDO.match(nome):
        raise ValueError(f'nome de instância inválido: {nome!r} (use letras, números, - e _; ex.: {FLAG} outro-banco)')
    nome = '' if nome == PADRAO else nome
    destino = pasta(nome)
    if not os.path.isdir(destino):
        existentes = ', '.join(i['nome'] for i in listar()) or 'nenhuma'
        raise ValueError(f'instância não encontrada: {destino} (instâncias: {existentes})')
    if os.environ.get('VEGAPUNK_EGGHEAD_DB'):
        raise ValueError(f'VEGAPUNK_EGGHEAD_DB está definida: ela tem precedência sobre {FLAG}; remova uma das duas')
    os.environ['VEGAPUNK_EGGHEAD'] = destino
    return resto


def ativar_ou_sair(argv):
    """`ativar` para a linha de comando: erro de uso sai com código 2."""
    try:
        return ativar(argv)
    except ValueError as e:
        print(f'ERRO: {e}', file=sys.stderr)
        raise SystemExit(2)
