#!/usr/bin/env python3
"""
================================================================================
 MIGRAÇÕES — versão da base Punk Records e migrações numeradas
================================================================================
A Punk Records guarda a versão do próprio schema na tabela `meta`
(chave/valor), em vez de depender de `ALTER TABLE` avulso. Cada migração
tem um número, um nome e uma lista de comandos SQL; uma base sem a tabela
`meta` está na versão 0.

Regras (PLANO-V3.md, "Migração de uma base já instalada"):
- antes de aplicar qualquer migração, faz uma cópia de segurança da base
  em `egghead/backups/` (fora do controle de versão);
- cada migração roda numa transação: entra inteira ou não entra;
- se uma migração falhar, a cópia volta para o lugar da base;
- nada do que o usuário curou é apagado: migração só acrescenta estrutura.
- só estrutura: nenhuma migração lê, grava ou copia linha de conteúdo do
  sistema de origem.

O motor de busca NÃO aplica migração sozinho ao abrir a base; aplicar é
sempre uma ação explícita.

Uso (pelo York, a única porta de escrita na base):
    python3 satelites/york.py migrar status
    python3 satelites/york.py migrar aplicar
    python3 satelites/york.py migrar status --db outro.db

Saída 0 = ok; 1 = falha (a base foi restaurada da cópia).
================================================================================
"""

import datetime
import os
import shutil
import sqlite3
import sys


# (número, nome, comandos). Nunca renumere nem altere uma migração já
# publicada: acrescente uma nova no fim.
def _adicionar_colunas(tabela, colunas):
    """Passo idempotente: ALTER TABLE ADD COLUMN só para o que ainda não existe
    (uma base criada pelo `importar` da fase 2 já nasce com as colunas)."""
    def passo(conn):
        existentes = {r[1] for r in conn.execute(f'PRAGMA table_info({tabela})')}
        for nome, tipo in colunas:
            if nome not in existentes:
                conn.execute(f'ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}')
    return passo


MIGRACOES = [
    (1, 'criar_meta', [
        """CREATE TABLE IF NOT EXISTS meta (
               chave TEXT PRIMARY KEY,
               valor TEXT NOT NULL
           )""",
    ]),
    # Fase 2 da v3: estrutura de coluna e nome da constraint de cada FK.
    # As colunas nascem vazias; `york.py enriquecer` (ou um `importar` com os
    # CSVs do tabelas.sql) as preenche. Nenhuma linha existente muda.
    (2, 'estrutura_colunas_e_constraints', [
        _adicionar_colunas('colunas', [('tipo', 'TEXT'), ('tamanho', 'INTEGER'), ('precisao', 'INTEGER'),
                                       ('escala', 'INTEGER'), ('nulo', 'INTEGER'), ('ordem', 'INTEGER'),
                                       ('pk_ordem', 'INTEGER')]),
        _adicionar_colunas('relacionamentos', [('constraint_nome', 'TEXT'), ('ordem', 'INTEGER')]),
    ]),
    # Fase 3-0b da v3: número da ligação do dicionário do sistema em cada
    # linha de FK (o dicionário traz uma linha por ligação, com os campos em
    # lista). Nasce vazia; `york.py enriquecer --dicionario` a preenche.
    (3, 'ligacao_do_dicionario', [
        _adicionar_colunas('relacionamentos', [('ligacao', 'INTEGER')]),
    ]),    # Fase 3 da v3: camada Mapa. Tabelas novas e vazias; `york.py compilar-mapa`
    # as preenche a partir do mapa.json (contrato v2, punk_records/mapa.py).
    # Só nomes de tabela, coluna e função: nunca conteúdo.
    (4, 'camada_mapa', [
        """CREATE TABLE IF NOT EXISTS mapa_estruturas (
               parte TEXT PRIMARY KEY, tabela TEXT NOT NULL, chave TEXT NOT NULL, ligacao TEXT)""",
        """CREATE TABLE IF NOT EXISTS mapa_cadastros (
               cadastro TEXT PRIMARY KEY, tabela TEXT NOT NULL, chave TEXT NOT NULL,
               coluna_codigo TEXT NOT NULL, coluna_descricao TEXT, nota TEXT)""",
        """CREATE TABLE IF NOT EXISTS mapa_rotulos (
               cadastro TEXT NOT NULL, rotulo TEXT NOT NULL, rotulo_normalizado TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS mapa_funcoes (cadastro TEXT NOT NULL, funcao TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS mapa_papeis (
               parte TEXT NOT NULL, dono TEXT, papel TEXT NOT NULL, tabela TEXT NOT NULL, coluna TEXT NOT NULL,
               papel_divergente INTEGER NOT NULL, prova TEXT NOT NULL,
               destino TEXT, colunas_origem TEXT, chave_destino TEXT)""",
        """CREATE TABLE IF NOT EXISTS mapa_funcoes_consulta (papel TEXT PRIMARY KEY, funcao TEXT NOT NULL)""",
        'CREATE INDEX IF NOT EXISTS idx_mapa_rotulos ON mapa_rotulos(rotulo_normalizado)',
        'CREATE INDEX IF NOT EXISTS idx_mapa_funcoes ON mapa_funcoes(funcao)',
    ]),
    # Fase 3c: cada rótulo de parâmetro do mapa guarda a prova ('declarado' ou
    # 'documentacao') e a fonte da documentação que o prova.
    (5, 'prova_dos_rotulos_do_mapa', [
        _adicionar_colunas('mapa_rotulos', [('prova', "TEXT NOT NULL DEFAULT 'declarado'"), ('fonte', 'TEXT')]),
    ]),
    # Fase 3: papel de coluna confirmado pelo usuário quando a descrição não o
    # confirma, com a fonte e a data; e a descrição da origem marcada como
    # errada (o Edison não a usa como evidência).
    (6, 'papel_confirmado_pelo_usuario', [
        _adicionar_colunas('mapa_papeis', [('prova_do_papel', "TEXT NOT NULL DEFAULT 'descricao'"),
                                           ('fonte_do_papel', 'TEXT'), ('confirmado_em', 'TEXT'),
                                           ('descricao_errada', 'INTEGER NOT NULL DEFAULT 0')]),
    ]),
    # Fase 4 da v3: direção das ligações do dicionário provada pelo catálogo.
    # `direcao`: NULL (como o dicionário registrou), 'invertida' (a FK física
    # tem a direção oposta e os mesmos campos) ou 'duplicata_inversa' (idem, e
    # a FK física já está na base na direção certa). `direcao_prova`: nome da
    # constraint física. A linha original não muda; a view
    # `relacionamentos_corrigidos` é a leitura dirigida corrigida. Nasce sem
    # marcação; `york.py corrigir-direcao` a preenche.
    (7, 'direcao_do_dicionario', [
        _adicionar_colunas('relacionamentos', [('direcao', 'TEXT'), ('direcao_prova', 'TEXT')]),
        'DROP VIEW IF EXISTS relacionamentos_corrigidos',
        """CREATE VIEW relacionamentos_corrigidos AS
           SELECT CASE WHEN direcao = 'invertida' THEN tabela_mae ELSE tabela_filha END AS tabela_filha,
                  CASE WHEN direcao = 'invertida' THEN campo_mae ELSE campo_filho END AS campo_filho,
                  CASE WHEN direcao = 'invertida' THEN tabela_filha ELSE tabela_mae END AS tabela_mae,
                  CASE WHEN direcao = 'invertida' THEN campo_filho ELSE campo_mae END AS campo_mae,
                  constraint_nome, ordem, ligacao, direcao, direcao_prova
           FROM relacionamentos
           WHERE direcao IS NULL OR direcao <> 'duplicata_inversa'""",
    ]),
    # Fase 4 da v3 (4c): sinônimos unificados na Punk Records, cada par com o
    # seu `uso`: NULL ou 'busca' (a busca de schema, como sempre) ou
    # 'essencial' (só a regra do termo essencial de fórmulas; não entra em
    # busca nenhuma, então não mexe no ranking). Nenhum par existente muda.
    (8, 'uso_dos_sinonimos', [
        _adicionar_colunas('sinonimos', [('uso', 'TEXT')]),
    ]),
]

_SUFIXOS_TEMPORARIOS = ('-journal', '-wal', '-shm')


def _agora():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def _conectar(db_path):
    # isolation_level=None: as transações são abertas e fechadas à mão
    return sqlite3.connect(db_path, isolation_level=None)


def versao_atual(conn):
    tem_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
    if not tem_meta:
        return 0
    row = conn.execute("SELECT valor FROM meta WHERE chave = 'versao_schema'").fetchone()
    return int(row[0]) if row else 0


def pendentes(versao, migracoes=MIGRACOES):
    return [m for m in migracoes if m[0] > versao]


def status(db_path, migracoes=MIGRACOES):
    conn = _conectar(db_path)
    try:
        versao = versao_atual(conn)
        aplicadas = {}
        if versao:
            aplicadas = dict(conn.execute(
                "SELECT chave, valor FROM meta WHERE chave LIKE 'migracao:%' ORDER BY chave").fetchall())
    finally:
        conn.close()
    return {'versao': versao, 'versao_alvo': max((m[0] for m in migracoes), default=0),
            'aplicadas': aplicadas, 'pendentes': [f'{n:03d} {nome}' for n, nome, _ in pendentes(versao, migracoes)]}


def _sobras(db_path):
    return [db_path + s for s in _SUFIXOS_TEMPORARIOS if os.path.exists(db_path + s)]


def copiar_seguranca(db_path, destino_dir=None):
    """Copia a base (sem conexão aberta) e confere a cópia com integrity_check."""
    destino_dir = destino_dir or os.path.join(os.path.dirname(os.path.abspath(db_path)), 'backups')
    os.makedirs(destino_dir, exist_ok=True)
    nome = os.path.splitext(os.path.basename(db_path))[0]
    carimbo = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    copia = os.path.join(destino_dir, f'{nome}.{carimbo}.db')
    n = 1
    while os.path.exists(copia):        # duas cópias no mesmo segundo: nunca sobrescreve
        n += 1
        copia = os.path.join(destino_dir, f'{nome}.{carimbo}-{n}.db')
    shutil.copy2(db_path, copia)
    conn = sqlite3.connect(f'file:{os.path.abspath(copia)}?mode=ro', uri=True)
    try:
        ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        conn.close()
    if ok != 'ok':
        raise RuntimeError(f'cópia de segurança não passou no integrity_check: {ok}')
    return copia


def aplicar(db_path, migracoes=MIGRACOES, destino_backup=None):
    """Aplica as migrações pendentes. Devolve {'antes', 'depois', 'aplicadas', 'copia'}."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    if _sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite presentes: {_sobras(db_path)} — '
                           'feche o que estiver usando a base antes de migrar')

    conn = _conectar(db_path)
    try:
        antes = versao_atual(conn)
    finally:
        conn.close()
    fila = pendentes(antes, migracoes)
    if not fila:
        return {'antes': antes, 'depois': antes, 'aplicadas': [], 'copia': None}

    copia = copiar_seguranca(db_path, destino_backup)
    feitas = []
    conn = _conectar(db_path)
    try:
        for numero, nome, comandos in fila:
            conn.execute('BEGIN IMMEDIATE')
            try:
                for passo in comandos:
                    passo(conn) if callable(passo) else conn.execute(passo)
                conn.execute("CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
                conn.execute("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('versao_schema', ?)",
                             (str(numero),))
                conn.execute("INSERT OR REPLACE INTO meta (chave, valor) VALUES (?, ?)",
                             (f'migracao:{numero:03d}', f'{nome} | {_agora()}'))
                conn.execute('COMMIT')
            except Exception:
                conn.execute('ROLLBACK')
                raise
            feitas.append(f'{numero:03d} {nome}')
        ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise RuntimeError(f'integrity_check depois da migração: {ok}')
        depois = versao_atual(conn)
    except Exception:
        conn.close()
        shutil.copy2(copia, db_path)
        for sobra in _sobras(db_path):
            os.remove(sobra)
        raise
    conn.close()
    if _sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite ficaram para trás: {_sobras(db_path)}')
    return {'antes': antes, 'depois': depois, 'aplicadas': feitas, 'copia': copia}
