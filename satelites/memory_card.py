#!/usr/bin/env python3
"""
================================================================================
 MEMORY CARD — o cartão de memória dos seus relatórios
================================================================================
Nome: como o memory card de um videogame, cada relatório pronto fica salvo
(um "save"), com versão e histórico, para ser carregado de novo quando
precisar. Foge da regra de nomes por personagem de propósito: o nome é o da
ideia, não de um papel do motor.

A FUNCIONALIDADE é do motor; o CARTÃO é de cada usuário. O cartão é um
repositório git do próprio usuário no GitHub (privado por padrão), e qual é
o cartão fica só na instância (`egghead/memory_card.json`, fora do git e da
distribuição). Nada do cartão vem junto com o Vegapunk.

Antes de qualquer push a visibilidade do cartão é conferida no GitHub: se
não for PRIVATE, o envio é recusado (a não ser que o próprio usuário tenha
criado o cartão público com `iniciar --publico`).

Organização do cartão (nomes de exibição ficam na ficha; pastas sem acento):

    saves/<categoria>/<secao>/<artigo>/relatorio.sql
    saves/<categoria>/<secao>/<artigo>/README.md    o artigo (o GitHub mostra ao abrir a pasta)
    saves/<categoria>/<secao>/<artigo>/ficha.json   metadado: versão, status, histórico...
    CATALOGO.md   (gerado: por categoria e seção, e por tabela)

Um artigo é citado por REF = `<categoria>/<secao>/<artigo>` (as pastas).
Guia completo: referencias/memory-card.md.

Uso (da pasta da skill; precisa do `gh` instalado e autenticado):
    python3 satelites/memory_card.py iniciar --repo DONO/NOME [--pasta DIR] [--publico]
        cria o cartão no GitHub (privado, a não ser com --publico) ou usa um
        que já existe, clona e grava a configuração na instância.
    python3 satelites/memory_card.py catalogo [--json]
    python3 satelites/memory_card.py buscar TERMO [TERMO ...] [--limite 10]
    python3 satelites/memory_card.py enviar ARQ.sql --categoria C --secao S --artigo A
                                        [--descricao D] [--texto ARTIGO.md] [--motivo M]
                                        [--status rascunho|em-uso] [--relacionado REF ...]
                                        [--confirmar]
        sem --confirmar: só mostra a prévia (versão, ficha, conferência no
        schema, diff do SQL e do artigo); nada é gravado. --texto é
        obrigatório num artigo novo; --motivo é obrigatório num reenvio.
    python3 satelites/memory_card.py marcar REF --status em-uso|rascunho [--confirmar]
    python3 satelites/memory_card.py conferir [REF ...] [--registrar]
        confere tabelas e colunas de cada relatório na Punk Records atual
        (só leitura; não grava no log de uso). --registrar guarda o resultado
        nas fichas e envia.

Configuração: `memory_card.json` na instância (VEGAPUNK_EGGHEAD ou
egghead/), gravado pelo `iniciar`; MEMORY_CARD_REPO e MEMORY_CARD_DIR têm
precedência. Base conferida: VEGAPUNK_EGGHEAD_DB ou egghead/punk_records.db.
================================================================================
"""

import argparse
import datetime
import difflib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVES = 'saves'
_REPO = re.compile(r'^[\w.-]+/[\w.-]+$')
README_DO_CARTAO = """# Memory Card

Cartão de memória de relatórios T-SQL criados com o Vegapunk: cada relatório
pronto fica salvo aqui, com versão e histórico.

Cada relatório fica em `saves/<categoria>/<secao>/<artigo>/`:

- `README.md`: o artigo (o que faz, quando usar, como funciona, colunas,
  parâmetros, regras de negócio, limitações, relacionados e histórico).
- `relatorio.sql`: o relatório.
- `ficha.json`: versão, status (`rascunho` ou `em-uso`), tabelas e colunas
  usadas, relacionados, histórico e a última conferência no schema.

O [CATALOGO.md](CATALOGO.md) lista os saves por categoria e seção, e também
por tabela. É gerado a cada envio: não edite à mão.

Cada mudança num artigo sobe a versão e exige um motivo, que entra no
histórico do artigo e na mensagem do commit. Envio só pelo Vegapunk
(`satelites/memory_card.py`): primeiro a prévia, depois `--confirmar`.
"""
STATUS = ('rascunho', 'em-uso')
CORPO_INI, CORPO_FIM = '<!-- corpo -->', '<!-- /corpo -->'

# Literais que parecem dado pessoal: só aviso na prévia (o cartão é privado por padrão).
_AVISOS = [
    (re.compile(r"'\d{3}\.?\d{3}\.?\d{3}-?\d{2}'"), 'literal com cara de CPF'),
    (re.compile(r"'[^'@\s]+@[^'@\s]+\.[^'\s]+'"), 'literal com cara de e-mail'),
    (re.compile(r'^\s*USE\s+\S+', re.I | re.M), '`USE` com nome de banco'),
]
_PALAVRAS_SQL = ('ON', 'WHERE', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS', 'OUTER', 'JOIN', 'GROUP', 'ORDER',
                 'WITH', 'UNION', 'HAVING', 'APPLY', 'PIVOT', 'UNPIVOT', 'OPTION', 'SELECT', 'SET', 'EXCEPT',
                 'INTERSECT')
_ORIGEM = re.compile(r'\b(?:FROM|JOIN)\s+([\[\]\w.@#]+)(?:\s+(?:AS\s+)?(?!(?:' + '|'.join(_PALAVRAS_SQL) +
                     r')\b)(\w+))?', re.I)
_QUALIFICADA = re.compile(r'\b(\w+)\.\[?(\w+)\]?')
_CTE = re.compile(r'\b(\w+)\s+AS\s*\(', re.I)


class EnvioRecusado(RuntimeError):
    """O envio não pode seguir."""


def pasta_instancia():
    return os.environ.get('VEGAPUNK_EGGHEAD') or os.path.join(SKILL, 'egghead')


def caminho_config():
    return os.path.join(pasta_instancia(), 'memory_card.json')


def config():
    """{'repo', 'pasta', 'publico'} do cartão. Sem cartão configurado, recusa
    explicando como criar um."""
    texto = _ler(caminho_config())
    c = json.loads(texto) if texto else {}
    repo = os.environ.get('MEMORY_CARD_REPO') or c.get('repo')
    if not repo:
        raise EnvioRecusado('nenhum Memory Card configurado nesta instância. Crie um com: '
                            'python3 satelites/memory_card.py iniciar --repo SEU_USUARIO/memory-card')
    pasta = os.environ.get('MEMORY_CARD_DIR') or c.get('pasta') or \
        os.path.join(os.path.expanduser('~'), repo.split('/')[1])
    return {'repo': repo, 'pasta': os.path.abspath(pasta), 'publico': bool(c.get('publico'))}


def slug(texto):
    t = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    if not t:
        raise EnvioRecusado(f'nome vazio depois de normalizar: {texto!r}')
    return t


def _agora():
    return datetime.datetime.now().isoformat(timespec='seconds')


ONDE_FUNCIONA = ('o Memory Card só funciona onde há o GitHub CLI (`gh`) autenticado e a pasta do cartão: '
                 'o Claude Code (ou um terminal) na máquina do usuário. Numa sandbox, como a do claude.ai, '
                 'ele não está disponível.')


def _exigir_gh():
    """Recusa com explicação clara se o `gh` não existe ou não está autenticado."""
    if shutil.which('gh') is None:
        raise EnvioRecusado('GitHub CLI (`gh`) não encontrado. ' + ONDE_FUNCIONA)
    if subprocess.run(['gh', 'auth', 'status'], capture_output=True).returncode != 0:
        raise EnvioRecusado('o `gh` não está autenticado (rode `gh auth login`). ' + ONDE_FUNCIONA)


def _rodar(args, cwd=None):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8')
    except FileNotFoundError:
        raise EnvioRecusado(f'`{args[0]}` não encontrado. ' + ONDE_FUNCIONA)
    if r.returncode != 0:
        raise EnvioRecusado(f'{" ".join(args[:3])} falhou: {(r.stderr or r.stdout).strip()}')
    return r.stdout


def _visibilidade(repo):
    return json.loads(_rodar(['gh', 'repo', 'view', repo, '--json', 'visibility']))['visibility']


def conferir_privado():
    """Recusa se o cartão não for privado no GitHub (a não ser que o usuário
    o tenha criado público de propósito, com `iniciar --publico`)."""
    c = config()
    _exigir_gh()
    vis = _visibilidade(c['repo'])
    if vis != 'PRIVATE' and not c['publico']:
        raise EnvioRecusado(f'{c["repo"]} está {vis}: o Memory Card só aceita envio com o repositório PRIVATE')


def preparar_pasta(atualizar=True):
    c = config()
    pasta = c['pasta']
    if not os.path.isdir(os.path.join(pasta, '.git')):
        _exigir_gh()
        _rodar(['gh', 'repo', 'clone', c['repo'], pasta])
    elif atualizar:
        try:
            _rodar(['git', 'pull', '--ff-only', '--quiet'], cwd=pasta)
        except EnvioRecusado as e:
            # sem rede ainda dá para ler a cópia local; o envio confere tudo de novo antes do push
            print(f'AVISO: não consegui atualizar o cartão ({e}); usando a cópia local.', file=sys.stderr)
    return pasta


def publicar(pasta, mensagem):
    """Grava o catálogo, faz o commit e o push (com o repositório PRIVATE antes e depois)."""
    conferir_privado()
    _gravar(os.path.join(pasta, 'CATALOGO.md'), gerar_catalogo_md(ler_catalogo(pasta)))
    _rodar(['git', 'add', '-A', '.'], cwd=pasta)
    _rodar(['git', 'commit', '-q', '-m', mensagem], cwd=pasta)
    conferir_privado()
    _rodar(['git', 'push', '-q'], cwd=pasta)


def iniciar(repo, pasta=None, publico=False):
    """Cria o cartão (ou usa um que já existe), clona e grava a configuração
    na instância. Devolve a configuração."""
    if not _REPO.match(repo or ''):
        raise EnvioRecusado(f'repositório inválido: {repo!r} (use DONO/NOME)')
    _exigir_gh()
    existe = subprocess.run(['gh', 'repo', 'view', repo, '--json', 'name'], capture_output=True).returncode == 0
    if not existe:
        _rodar(['gh', 'repo', 'create', repo, '--public' if publico else '--private',
                '--description', 'Memory Card: relatórios T-SQL salvos pelo Vegapunk'])
    vis = _visibilidade(repo)
    if vis != 'PRIVATE' and not publico:
        raise EnvioRecusado(f'{repo} já existe e está {vis}: use um repositório privado (ou --publico, se for de propósito)')
    pasta = os.path.abspath(pasta or os.path.join(os.path.expanduser('~'), repo.split('/')[1]))
    if not os.path.isdir(os.path.join(pasta, '.git')):
        if os.path.exists(pasta) and os.listdir(pasta):
            raise EnvioRecusado(f'a pasta já existe e não está vazia: {pasta}')
        _rodar(['gh', 'repo', 'clone', repo, pasta])
    os.makedirs(pasta_instancia(), exist_ok=True)
    _gravar(caminho_config(), json.dumps({'repo': repo, 'pasta': pasta, 'publico': publico},
                                         ensure_ascii=False, indent=2))
    if not os.path.exists(os.path.join(pasta, 'README.md')):
        _gravar(os.path.join(pasta, 'README.md'), README_DO_CARTAO)
        _gravar(os.path.join(pasta, 'CATALOGO.md'), gerar_catalogo_md([]))
        _rodar(['git', 'add', 'README.md', 'CATALOGO.md'], cwd=pasta)
        _rodar(['git', 'commit', '-q', '-m', 'Memory Card'], cwd=pasta)
        _rodar(['git', 'branch', '-M', 'main'], cwd=pasta)
        _rodar(['git', 'push', '-q', '-u', 'origin', 'main'], cwd=pasta)
    return {'repo': repo, 'pasta': pasta, 'publico': publico}


def _gravar(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8', newline='\n') as f:
        f.write(texto if texto.endswith('\n') else texto + '\n')


def _ler(caminho):
    if not os.path.exists(caminho):
        return None
    with open(caminho, encoding='utf-8-sig') as f:
        return f.read()


# --- fichas -----------------------------------------------------------------

def normalizar_ficha(f):
    """Completa fichas antigas (antes de versão, status e histórico)."""
    f.setdefault('versao', 1)
    f.setdefault('status', 'rascunho')
    f.setdefault('relacionados', [])
    f.setdefault('colunas', [])
    f.setdefault('historico', [{'versao': 1, 'data': f.get('criado_em', ''), 'motivo': 'Primeira versão'}])
    return f


def pasta_do_artigo(pasta, ref):
    return os.path.join(pasta, SAVES, *ref.strip('/').split('/'))


def ler_ficha(pasta, ref):
    texto = _ler(os.path.join(pasta_do_artigo(pasta, ref), 'ficha.json'))
    if texto is None:
        raise EnvioRecusado(f'artigo não encontrado: {ref}')
    return normalizar_ficha(json.loads(texto))


def gravar_ficha(pasta, ref, ficha):
    f = {k: v for k, v in ficha.items() if k != 'ref'}
    _gravar(os.path.join(pasta_do_artigo(pasta, ref), 'ficha.json'), json.dumps(f, ensure_ascii=False, indent=2))


def ler_catalogo(pasta):
    """Fichas dos saves (com `ref`), ordenadas por categoria, seção e artigo."""
    fichas = []
    raiz = os.path.join(pasta, SAVES)
    for d, _, arqs in os.walk(raiz):
        if 'ficha.json' in arqs:
            ficha = normalizar_ficha(json.loads(_ler(os.path.join(d, 'ficha.json'))))
            ficha['ref'] = os.path.relpath(d, raiz).replace(os.sep, '/')
            fichas.append(ficha)
    return sorted(fichas, key=lambda x: (x['categoria'].lower(), x['secao'].lower(), x['artigo'].lower()))


# --- SQL ----------------------------------------------------------------------

def _sem_comentario(sql):
    return re.sub(r"--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'", ' ', sql, flags=re.S)


def avisos_do_sql(sql):
    return [msg for rx, msg in _AVISOS if rx.search(sql)]


def referencias_do_sql(sql):
    """(tabelas, colunas): tabelas de FROM/JOIN e colunas qualificadas
    (`TABELA.COL` ou `ALIAS.COL`), em maiúsculas, sem CTE nem variável."""
    limpo = _sem_comentario(sql)
    ctes = {c.upper() for c in _CTE.findall(limpo)}
    tabelas, apelidos = set(), {}
    for nome, apelido in _ORIGEM.findall(limpo):
        if nome.startswith(('@', '#', '(')):
            continue
        t = nome.replace('[', '').replace(']', '').split('.')[-1].upper()
        if not t or t in ctes:
            continue
        tabelas.add(t)
        apelidos[t] = t
        if apelido:
            apelidos[apelido.upper()] = t
    colunas = set()
    for prefixo, col in _QUALIFICADA.findall(limpo):
        t = apelidos.get(prefixo.upper())
        if t:
            colunas.add(f'{t}.{col.upper()}')
    return sorted(tabelas), sorted(colunas)


def caminho_base():
    return os.environ.get('VEGAPUNK_EGGHEAD_DB') or os.path.join(SKILL, 'egghead', 'punk_records.db')


def conferir_no_schema(tabelas, colunas, db=None):
    """{'ok', 'faltando': [...], 'base'}: o que o relatório usa e a Punk Records
    não tem. Abre a base só para leitura; nada vai para o log de uso."""
    db = db or caminho_base()
    if not os.path.exists(db):
        return {'ok': None, 'faltando': [], 'base': 'sem base instalada: não conferido'}
    conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        tem_t = {r[0].upper() for r in conn.execute('SELECT tabela FROM tabelas')}
        faltando = [t for t in tabelas if t not in tem_t]
        for c in colunas:
            t, col = c.split('.', 1)
            if t in tem_t and conn.execute('SELECT 1 FROM colunas WHERE UPPER(tabela)=? AND UPPER(coluna)=?',
                                           (t, col)).fetchone() is None:
                faltando.append(c)
    finally:
        conn.close()
    return {'ok': not faltando, 'faltando': faltando, 'base': f'Punk Records com {len(tem_t)} tabelas'}


# --- artigo (README.md) e catálogo ------------------------------------------------

def corpo_do_readme(texto):
    if not texto or CORPO_INI not in texto:
        return None
    return texto.split(CORPO_INI, 1)[1].split(CORPO_FIM, 1)[0].strip('\n')


def _link(de_ref, para_ref):
    return '../' * len(de_ref.split('/')) + para_ref + '/'


def gerar_readme(ficha, ref, corpo, titulos):
    """O artigo: cabeçalho e histórico vêm da ficha; o corpo, do texto enviado.
    `titulos`: {ref: artigo} para os relacionados."""
    l = [f'# {ficha["artigo"]}', '',
         f'{ficha["categoria"]} › {ficha["secao"]} · versão {ficha["versao"]} · {ficha["status"]}', '']
    if ficha.get('descricao'):
        l += [f'> {ficha["descricao"]}', '']
    l += [CORPO_INI, corpo.strip('\n'), CORPO_FIM, '', '## Relatório', '', '[relatorio.sql](relatorio.sql)']
    if ficha.get('tabelas'):
        l += ['', f'Tabelas: {", ".join(f"`{t}`" for t in ficha["tabelas"])}.']
    conf = ficha.get('conferencia')
    if conf:
        situacao = 'tudo encontrado' if conf['ok'] else f'faltando {", ".join(f"`{x}`" for x in conf["faltando"])}'
        l += ['', f'Última conferência no schema ({conf["data"][:10]}): {situacao}.']
    if ficha['relacionados']:
        l += ['', '## Relacionados', '']
        l += [f'- [{titulos.get(r, r)}]({_link(ref, r)})' for r in ficha['relacionados']]
    l += ['', '## Histórico', '', '| Versão | Data | Motivo |', '|---|---|---|']
    l += [f'| {h["versao"]} | {h["data"][:10]} | {h["motivo"]} |' for h in reversed(ficha['historico'])]
    return '\n'.join(l) + '\n'


def gerar_catalogo_md(fichas):
    linhas = ['# Catálogo', '', 'Gerado pelo envio. Não edite à mão.', '']
    cat = sec = None
    for f in fichas:
        if f['categoria'] != cat:
            cat, sec = f['categoria'], None
            linhas += [f'## {cat}', '']
        if f['secao'] != sec:
            sec = f['secao']
            linhas += [f'### {sec}', '']
        desc = f' — {f["descricao"]}' if f.get('descricao') else ''
        quebrado = ' · **conferir: schema mudou**' if (f.get('conferencia') or {}).get('ok') is False else ''
        linhas.append(f'- [{f["artigo"]}]({SAVES}/{f["ref"]}/){desc} · v{f["versao"]} · {f["status"]}{quebrado}')
    por_tabela = {}
    for f in fichas:
        for t in f.get('tabelas', []):
            por_tabela.setdefault(t, []).append(f)
    if por_tabela:
        linhas += ['', '## Por tabela', '']
        for t in sorted(por_tabela):
            linhas.append(f'- `{t}`: ' + ', '.join(f'[{f["artigo"]}]({SAVES}/{f["ref"]}/)' for f in por_tabela[t]))
    if len(linhas) > 4:
        linhas.append('')
    return '\n'.join(linhas) + '\n'


def _diff(antes, depois, nome):
    return ''.join(difflib.unified_diff((antes or '').splitlines(True), depois.splitlines(True),
                                        f'{nome} (atual)', f'{nome} (novo)'))


# --- busca ------------------------------------------------------------------

def _tokens(texto):
    t = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode('ascii').lower()
    return set(re.findall(r'[a-z0-9]+', t))


def buscar(pasta, termos, limite=10):
    """[(pontos, ficha)]: artigo e descrição valem 3, categoria, seção e
    tabelas 2, texto do artigo e SQL 1, por termo encontrado."""
    alvo = set()
    for t in termos:
        alvo |= _tokens(t)
    achados = []
    for f in ler_catalogo(pasta):
        d = pasta_do_artigo(pasta, f['ref'])
        campos = [(3, f'{f["artigo"]} {f.get("descricao", "")}'), (2, f'{f["categoria"]} {f["secao"]}'),
                  (2, ' '.join(f.get('tabelas', []))),
                  (1, corpo_do_readme(_ler(os.path.join(d, 'README.md'))) or ''),
                  (1, _ler(os.path.join(d, 'relatorio.sql')) or '')]
        pontos = sum(peso * len(alvo & _tokens(texto)) for peso, texto in campos)
        if pontos:
            achados.append((pontos, f))
    return sorted(achados, key=lambda x: (-x[0], x[1]['ref']))[:limite]


# --- envio ------------------------------------------------------------------

def montar_envio(arquivo, categoria, secao, artigo, descricao, pasta, texto=None, motivo=None,
                 status=None, relacionados=()):
    if not arquivo.lower().endswith('.sql'):
        raise EnvioRecusado('o Memory Card só recebe arquivos .sql')
    sql = _ler(arquivo) if os.path.isfile(arquivo) else None
    if sql is None:
        raise EnvioRecusado(f'arquivo não encontrado: {arquivo}')
    if status and status not in STATUS:
        raise EnvioRecusado(f'status inválido: {status} (use {" ou ".join(STATUS)})')
    ref = '/'.join(slug(x) for x in (categoria, secao, artigo))
    destino = pasta_do_artigo(pasta, ref)
    anterior = ler_ficha(pasta, ref) if os.path.exists(os.path.join(destino, 'ficha.json')) else None
    readme_antes = _ler(os.path.join(destino, 'README.md'))
    if texto is not None:
        corpo = _ler(texto) if os.path.isfile(texto) else None
        if corpo is None:
            raise EnvioRecusado(f'texto do artigo não encontrado: {texto}')
    else:
        corpo = corpo_do_readme(readme_antes)
        if corpo is None:
            raise EnvioRecusado('artigo novo precisa do texto: --texto ARTIGO.md')
    if anterior and not (motivo or '').strip():
        raise EnvioRecusado(f'{ref} já existe (versão {anterior["versao"]}): diga o motivo da mudança com --motivo')
    for r in relacionados:
        if r == ref:
            raise EnvioRecusado('um artigo não se relaciona com ele mesmo')
        ler_ficha(pasta, r)
    agora = _agora()
    versao = anterior['versao'] + 1 if anterior else 1
    tabelas, colunas = referencias_do_sql(sql)
    ficha = {
        'categoria': categoria.strip(), 'secao': secao.strip(), 'artigo': artigo.strip(),
        'descricao': (descricao if descricao is not None else (anterior or {}).get('descricao', '')).strip(),
        'status': status or (anterior or {}).get('status', 'rascunho'),
        'versao': versao, 'tabelas': tabelas, 'colunas': colunas,
        'relacionados': sorted(set((anterior or {}).get('relacionados', [])) | set(relacionados)),
        'origem': (anterior or {}).get('origem') or os.path.basename(arquivo),
        'criado_em': anterior['criado_em'] if anterior else agora, 'atualizado_em': agora,
        'historico': (anterior or {}).get('historico', []) + [
            {'versao': versao, 'data': agora, 'motivo': (motivo or 'Primeira versão').strip()}],
    }
    conf = conferir_no_schema(tabelas, colunas)
    if conf['ok'] is not None:
        ficha['conferencia'] = {'data': agora, **conf}
    titulos = {f['ref']: f['artigo'] for f in ler_catalogo(pasta)}
    readme = gerar_readme(ficha, ref, corpo, titulos)
    sql_antes = _ler(os.path.join(destino, 'relatorio.sql'))
    return {'ref': ref, 'destino': destino, 'ficha': ficha, 'sql': sql, 'readme': readme,
            'substitui': anterior is not None, 'avisos': avisos_do_sql(sql), 'conferencia': conf,
            'diff_sql': _diff(sql_antes, sql, 'relatorio.sql') if anterior else '',
            'diff_readme': _diff(readme_antes, readme, 'README.md') if anterior else '',
            'novos_relacionados': [r for r in relacionados if r not in (anterior or {}).get('relacionados', [])]}


def gravar_envio(envio, pasta):
    _gravar(os.path.join(envio['destino'], 'relatorio.sql'), envio['sql'])
    gravar_ficha(pasta, envio['ref'], envio['ficha'])
    _gravar(os.path.join(envio['destino'], 'README.md'), envio['readme'])
    # a ligação vale nos dois sentidos: o relacionado ganha o link de volta
    titulos = {f['ref']: f['artigo'] for f in ler_catalogo(pasta)}
    for r in envio['ficha']['relacionados']:
        outra = ler_ficha(pasta, r)
        if envio['ref'] not in outra['relacionados']:
            outra['relacionados'] = sorted(outra['relacionados'] + [envio['ref']])
            gravar_ficha(pasta, r, outra)
        corpo = corpo_do_readme(_ler(os.path.join(pasta_do_artigo(pasta, r), 'README.md'))) or ''
        _gravar(os.path.join(pasta_do_artigo(pasta, r), 'README.md'), gerar_readme(outra, r, corpo, titulos))
    fi = envio['ficha']
    motivo = fi['historico'][-1]['motivo']
    publicar(pasta, f'save: {fi["categoria"]} / {fi["secao"]} / {fi["artigo"]} (v{fi["versao"]}): {motivo}')


def _regravar_readme(pasta, ref, ficha):
    d = pasta_do_artigo(pasta, ref)
    corpo = corpo_do_readme(_ler(os.path.join(d, 'README.md'))) or ''
    titulos = {f['ref']: f['artigo'] for f in ler_catalogo(pasta)}
    _gravar(os.path.join(d, 'README.md'), gerar_readme(ficha, ref, corpo, titulos))


# --- comandos ----------------------------------------------------------------

def _cmd_iniciar(a):
    c = iniciar(a.repo, a.pasta, a.publico)
    print(f'cartão: {c["repo"]} ({"PÚBLICO" if c["publico"] else "privado"})')
    print(f'pasta local: {c["pasta"]}')
    print(f'configuração gravada na instância: {caminho_config()}')
    return 0


def _cmd_catalogo(a):
    fichas = ler_catalogo(preparar_pasta())
    if a.json:
        print(json.dumps(fichas, ensure_ascii=False, indent=2))
    else:
        print(gerar_catalogo_md(fichas) if fichas else 'cartão vazio')
    return 0


def _cmd_buscar(a):
    achados = buscar(preparar_pasta(), a.termos, a.limite)
    if not achados:
        print('nenhum save para esses termos')
    for pontos, f in achados:
        print(f'{pontos:3d}  {f["ref"]}  (v{f["versao"]}, {f["status"]})  {f["artigo"]} — {f.get("descricao", "")}')
    return 0


def _cmd_enviar(a):
    pasta = preparar_pasta()
    e = montar_envio(a.arquivo, a.categoria, a.secao, a.artigo, a.descricao, pasta, a.texto, a.motivo,
                     a.status, a.relacionado or ())
    fi = e['ficha']
    print(f'destino: {config()["repo"]} → {SAVES}/{e["ref"]}/  versão {fi["versao"]}'
          + (' (SUBSTITUI a anterior)' if e['substitui'] else ' (artigo novo)'))
    c = e['conferencia']
    print('schema: ' + ('não conferido (' + c['base'] + ')' if c['ok'] is None else
                        'tudo encontrado' if c['ok'] else 'FALTANDO ' + ', '.join(c['faltando'])) +
          (f' — {c["base"]}' if c['ok'] is not None else ''))
    for av in e['avisos']:
        print(f'AVISO: {av}')
    if e['novos_relacionados']:
        print('relacionados novos (ganham o link de volta): ' + ', '.join(e['novos_relacionados']))
    print('\nficha:')
    print(json.dumps(fi, ensure_ascii=False, indent=2))
    if e['substitui']:
        print('\n--- diff do SQL ---\n' + (e['diff_sql'] or '(SQL igual)'))
        print('--- diff do artigo ---\n' + (e['diff_readme'] or '(artigo igual)'))
    else:
        print('\n--- artigo ---\n' + e['readme'])
    if not a.confirmar:
        print('prévia: nada foi gravado. Repita com --confirmar para enviar.')
        return 0
    gravar_envio(e, pasta)
    print(f'\nenviado: https://github.com/{config()["repo"]}/tree/main/{SAVES}/{e["ref"]}')
    return 0


def _cmd_marcar(a):
    if a.status not in STATUS:
        raise EnvioRecusado(f'status inválido: {a.status} (use {" ou ".join(STATUS)})')
    pasta = preparar_pasta()
    ficha = ler_ficha(pasta, a.ref)
    print(f'{a.ref}: {ficha["status"]} → {a.status}')
    if ficha['status'] == a.status:
        print('nada a mudar')
        return 0
    if not a.confirmar:
        print('prévia: nada foi gravado. Repita com --confirmar.')
        return 0
    ficha['status'] = a.status
    gravar_ficha(pasta, a.ref, ficha)
    _regravar_readme(pasta, a.ref, ficha)
    publicar(pasta, f'save: {ficha["categoria"]} / {ficha["secao"]} / {ficha["artigo"]}: status {a.status}')
    print('enviado')
    return 0


def _cmd_conferir(a):
    pasta = preparar_pasta()
    fichas = [f for f in ler_catalogo(pasta) if not a.refs or f['ref'] in a.refs]
    faltam = [r for r in (a.refs or []) if r not in {f['ref'] for f in fichas}]
    if faltam:
        raise EnvioRecusado(f'artigo não encontrado: {", ".join(faltam)}')
    agora, quebrados, mudou = _agora(), 0, False
    for f in fichas:
        sql = _ler(os.path.join(pasta_do_artigo(pasta, f['ref']), 'relatorio.sql')) or ''
        tabelas, colunas = referencias_do_sql(sql)
        c = conferir_no_schema(tabelas, colunas)
        if c['ok'] is None:
            print(c['base'])
            return 1
        quebrados += not c['ok']
        print(f'{"OK   " if c["ok"] else "FALTA"} {f["ref"]}' + ('' if c['ok'] else ': ' + ', '.join(c['faltando'])))
        anterior = f.get('conferencia') or {}
        if a.registrar and (anterior.get('ok'), anterior.get('faltando')) != (c['ok'], c['faltando']):
            f['conferencia'] = {'data': agora, **c}
            gravar_ficha(pasta, f['ref'], f)
            _regravar_readme(pasta, f['ref'], f)
            mudou = True
    print(f'\n{len(fichas)} relatório(s), {quebrados} com algo faltando no schema atual')
    if a.registrar:
        if mudou:
            publicar(pasta, f'save: conferência no schema ({quebrados} com algo faltando)')
            print('conferência registrada e enviada')
        else:
            print('nada mudou desde a última conferência registrada')
    return 1 if quebrados else 0


def main(argv=None):
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog='memory_card', description='Memory Card: cartão de memória de relatórios')
    sub = p.add_subparsers(dest='cmd', required=True)
    i = sub.add_parser('iniciar')
    i.add_argument('--repo', required=True)
    i.add_argument('--pasta')
    i.add_argument('--publico', action='store_true')
    c = sub.add_parser('catalogo')
    c.add_argument('--json', action='store_true')
    b = sub.add_parser('buscar')
    b.add_argument('termos', nargs='+')
    b.add_argument('--limite', type=int, default=10)
    e = sub.add_parser('enviar')
    e.add_argument('arquivo')
    e.add_argument('--categoria', required=True)
    e.add_argument('--secao', required=True)
    e.add_argument('--artigo', required=True)
    e.add_argument('--descricao')
    e.add_argument('--texto')
    e.add_argument('--motivo')
    e.add_argument('--status', choices=STATUS)
    e.add_argument('--relacionado', action='append')
    e.add_argument('--confirmar', action='store_true')
    m = sub.add_parser('marcar')
    m.add_argument('ref')
    m.add_argument('--status', required=True, choices=STATUS)
    m.add_argument('--confirmar', action='store_true')
    k = sub.add_parser('conferir')
    k.add_argument('refs', nargs='*')
    k.add_argument('--registrar', action='store_true')
    a = p.parse_args(argv)
    try:
        return {'iniciar': _cmd_iniciar, 'catalogo': _cmd_catalogo, 'buscar': _cmd_buscar, 'enviar': _cmd_enviar,
                'marcar': _cmd_marcar, 'conferir': _cmd_conferir}[a.cmd](a)
    except EnvioRecusado as ex:
        print(f'RECUSADO: {ex}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
