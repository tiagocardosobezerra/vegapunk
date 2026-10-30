"""
Checagem 10 do isolamento (fase 3 da v3): nenhum NOME do schema real na
superfície distribuível.

A régua vem de cada instância (`egghead/` e `egghead-<nome>/`, cada uma com
a sua `punk_records.db` e a sua lista extra): todas as tabelas, mais
as colunas "técnicas" (começam por COD, ID, NRO, NUM, DT, VLR, QTD ou CD, ou
têm dígito ou `_`). Ficam fora da régua as colunas do schema fictício da
fixture e o vocabulário que o próprio fornecedor publica na documentação
pública (texto do pacote público) e as palavras que as próprias descrições
da instância usam como palavra (IDENTIDADE). Palavras comuns que por acaso
são nome de coluna (AVISO, SERVER...) não entram.

Lista extra da instância (`egghead/termos_proibidos.json`, fora do git):
nomes reais que a régua automática não pega (coluna sem prefixo técnico,
nome achado à mão). Cada termo vale como proibido em qualquer lugar da
superfície. A chave `palavras` do mesmo arquivo lista palavras ou expressões
que só existem na instância (extensões pessoais): valem em qualquer caixa e,
numa expressão, com qualquer separador entre as partes. A chave `permitidos`
tira da régua nomes reais que só coincidem com vocabulário do motor.

A saída diz só arquivo, linha e contagem, nunca o nome. Sem instância (uma
cópia distribuída), não há o que comparar: a checagem passa com essa nota.
Fica fora do núcleo de fórmulas porque precisa abrir a base; o Atlas e a
distribuição a acrescentam às checagens do `verificar_isolamento`.
"""

import glob
import os
import re
import sqlite3
import tempfile
import unicodedata

_TECNICA = re.compile(r'^(?:COD|ID|NRO|NUM|DT|VLR|QTD|CD)[A-Z0-9_]{2,}$|[0-9_]')
_TOKEN = re.compile(r'\b[A-Z][A-Z0-9_]{3,}\b')
# Nome em caixa mista com maiúscula no meio (`QzCadastro`): o _TOKEN só pega o
# nome todo em maiúsculas e deixava passar o nome real de uma base assim.
_CAMEL = re.compile(r'\b[A-Za-z][a-z0-9]*[A-Z][A-Za-z0-9_]*\b')
NOME = 'nenhum nome do schema real na superfície distribuível'


def _colunas_ficticias():
    from casos.fixture_schema import gerar_fixture_db
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'f.db')
        gerar_fixture_db(db)
        c = sqlite3.connect(db)
        try:
            return ({x.upper() for (x,) in c.execute('SELECT DISTINCT coluna FROM colunas')},
                    {x.upper() for (x,) in c.execute('SELECT tabela FROM tabelas')})
        finally:
            c.close()


def _vocabulario_publico(raiz_skill):
    voc = set()
    for arq in glob.glob(os.path.join(raiz_skill, 'punk_records', 'pacotes', 'publico', '*', '*.json')):
        if os.path.basename(arq) in ('funcoes.json', 'documentos.json', 'receitas.json'):
            with open(arq, encoding='utf-8', errors='replace') as f:
                voc |= set(_TOKEN.findall(f.read().upper()))
    return voc


def _palavras(texto):
    t = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode().upper()
    return re.findall(r'[A-Z]{4,}', t)


def regua(db_path, raiz_skill):
    """(tabelas, colunas técnicas) da instância, sem fixture nem vocabulário público."""
    c = sqlite3.connect(f'file:{os.path.abspath(db_path)}?mode=ro', uri=True)
    try:
        tabelas = {t.upper() for (t,) in c.execute('SELECT tabela FROM tabelas')}
        colunas = {x.upper() for (x,) in c.execute('SELECT DISTINCT coluna FROM colunas') if x != '#'}
        # palavras do português que as próprias descrições da instância usam
        # (IDENTIDADE, CODIFICACAO...): não são nome técnico, mesmo com prefixo
        palavras = set()
        for (d,) in c.execute('SELECT descricao FROM colunas UNION SELECT descricao FROM tabelas'):
            palavras |= set(_palavras(d))
    finally:
        c.close()
    col_fic, tab_fic = _colunas_ficticias()
    publico = _vocabulario_publico(raiz_skill)
    colunas = {x for x in colunas - col_fic - publico - palavras if _TECNICA.search(x) and len(x) >= 4}
    return tabelas - tab_fic, colunas


def termos_proibidos(caminho):
    """Termos da lista extra da instância (maiúsculas), ou set() se não houver."""
    import json
    if not caminho or not os.path.exists(caminho):
        return set()
    with open(caminho, encoding='utf-8') as f:
        return {t.strip().upper() for t in json.load(f).get('termos', []) if len(t.strip()) >= 3}


def termos_permitidos(caminho):
    """Chave `permitidos` da lista da instância (maiúsculas): nome real que
    coincide com vocabulário genérico do motor (ex.: nome de token de um
    parser) e por isso sai da régua daquela instância. Cada termo é decisão
    humana, nunca automática."""
    import json
    if not caminho or not os.path.exists(caminho):
        return set()
    with open(caminho, encoding='utf-8') as f:
        return {t.strip().upper() for t in json.load(f).get('permitidos', []) if t.strip()}


def palavras_proibidas(caminho):
    """Palavras ou expressões da chave `palavras` da lista da instância (maiúsculas), ou set()."""
    import json
    if not caminho or not os.path.exists(caminho):
        return set()
    with open(caminho, encoding='utf-8') as f:
        return {t.strip().upper() for t in json.load(f).get('palavras', []) if len(t.strip()) >= 3}


def _padrao_da_palavra(palavra):
    """Expressão em qualquer caixa e com qualquer separador entre as partes
    (`a b`, `a-b`, `a_b`, `ab`)."""
    return re.compile(r'\b' + r'[\W_]*'.join(map(re.escape, re.findall(r'[^\W_]+', palavra))) + r'\b', re.I)


def _bases_da_skill(raiz_skill):
    """Toda base de instância da skill: `egghead/` e cada `egghead-<nome>/`.
    Nome de qualquer uma delas não pode sair na distribuição."""
    bases = []
    for d in sorted(os.listdir(raiz_skill)):
        db = os.path.join(raiz_skill, d, 'punk_records.db')
        if (d == 'egghead' or d.startswith('egghead-')) and os.path.isfile(db):
            bases.append(db)
    return bases


def verificar_nomes_reais(raiz_skill, arquivos, db_path=None, termos_path=None):
    """{verificacao, ok, detalhe} no formato do verificar_isolamento. Sem
    `db_path` nem VEGAPUNK_EGGHEAD_DB, confere contra TODAS as instâncias."""
    raiz_skill = os.path.abspath(raiz_skill)
    db_path = db_path or os.environ.get('VEGAPUNK_EGGHEAD_DB')
    if db_path is None:
        bases = _bases_da_skill(raiz_skill)
        if len(bases) > 1:
            partes = [(os.path.basename(os.path.dirname(b)), verificar_nomes_reais(raiz_skill, arquivos, b, termos_path))
                      for b in bases]
            return {'verificacao': NOME, 'ok': all(r['ok'] for _, r in partes),
                    'detalhe': ' | '.join(f'{nome}: {r["detalhe"]}' for nome, r in partes)}
        db_path = bases[0] if bases else os.path.join(raiz_skill, 'egghead', 'punk_records.db')
    if not os.path.exists(db_path):
        return {'verificacao': NOME, 'ok': True, 'detalhe': 'sem instância: nada a comparar'}
    if termos_path is None:
        termos_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'termos_proibidos.json')
    extras = termos_proibidos(termos_path)
    palavras = palavras_proibidas(termos_path)
    padroes = [_padrao_da_palavra(p) for p in palavras]
    tabelas, colunas = regua(db_path, raiz_skill)
    permitidos = termos_permitidos(termos_path)
    tabelas, colunas = tabelas - permitidos, (colunas - permitidos) | extras
    achados = []
    for a in arquivos:
        try:
            with open(a, encoding='utf-8', errors='replace') as f:
                linhas = f.read().splitlines()
        except OSError:
            continue
        n, onde = 0, []
        for i, l in enumerate(linhas, 1):
            k = sum(1 for t in _TOKEN.findall(l) if t in tabelas or t in colunas)
            k += sum(1 for t in _CAMEL.findall(l)
                     if not t.isupper() and (t.upper() in tabelas or t.upper() in colunas))
            k += sum(len(p.findall(l)) for p in padroes)
            if k:
                n += k
                onde.append(i)
        if n:
            achados.append(f'{os.path.relpath(a, raiz_skill)}:{",".join(map(str, onde[:8]))} ({n})')
    return {'verificacao': NOME, 'ok': not achados,
            'detalhe': f'{len(tabelas)} tabelas, {len(colunas) - len(extras)} colunas técnicas, {len(extras)} termos da '
                       f'lista da instância e {len(palavras)} palavras dela verificados em {len(arquivos)} arquivos'
                       + ('; ' + '; '.join(achados[:20]) if achados else '')}


def verificar_na_superficie(raiz_skill, raiz_conhecimento=None, db_path=None):
    """Checagem 10 sobre a superfície distribuível inteira."""
    from dominios.formulas import conhecimento as kb
    from dominios.isolamento import _superficie_distribuivel
    raiz_skill = os.path.abspath(raiz_skill)
    raiz_con = os.path.abspath(raiz_conhecimento or kb.RAIZ_CONHECIMENTO)
    return verificar_nomes_reais(raiz_skill, list(_superficie_distribuivel(raiz_skill, raiz_con)), db_path)
