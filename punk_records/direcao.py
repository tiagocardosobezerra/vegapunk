"""
Direção das ligações do dicionário, provada pelo catálogo (fase 4 da v3).

O dicionário do sistema registra muitas ligações na direção oposta à da FK
física: a "filha" do dicionário é a mãe da constraint. O gabarito é o
catálogo (`relacionamentos.csv` da extração física, só estrutura). Para cada
ligação do dicionário ainda sem constraint (linhas com o mesmo `ligacao` no
mesmo par):

- se existe FK física no par oposto com exatamente os mesmos campos
  trocados de lado, a ligação é a FK física registrada ao contrário:
  * 'duplicata_inversa' quando a base já tem essa FK física na direção
    certa (linhas com a constraint): a ligação não acrescenta nada;
  * 'invertida' quando não tem: a leitura corrigida troca filha e mãe;
- senão, nada muda (sem prova não há correção).

A linha original nunca é alterada: só ganha `direcao` e `direcao_prova`
(nome da constraint física). A leitura dirigida corrigida é a view
`relacionamentos_corrigidos` (migração 007). As métricas de ranking
(filhas, pais, conexões, score) são recalculadas com os pares corrigidos,
pela mesma função do `importar`.

Idempotente: refaz a marcação do zero a cada execução. Tudo numa transação,
com cópia de segurança antes. Só o York chama (`york.py corrigir-direcao`).
"""

import os
import shutil
import sqlite3
from collections import Counter, defaultdict

from punk_records import migracoes
from punk_records.enriquecimento import _chave, _ler
from punk_records.schema import calcular_metricas_e_scores, estrutura_do_relacionamento

VERSAO_MINIMA = 7


def classificar(linhas, rels_csv):
    """{rowid: (direcao, constraint)} para as linhas a marcar, e a contagem.
    `linhas`: dicts com rowid, tabela_filha, campo_filho, tabela_mae,
    campo_mae, constraint_nome, ligacao."""
    fisicas = defaultdict(set)                     # (constraint, FILHA, MAE) -> {(CF, CM)}
    for row in rels_csv:
        nome, _ordem = estrutura_do_relacionamento(row)
        if nome:
            fisicas[(nome, *_chave(row['tabela_filha'], row['tabela_mae']))].add(
                _chave(row['campo_filho'], row['campo_mae']))
    fis_par = defaultdict(list)                    # (FILHA, MAE) -> [(campos, constraint)]
    for (nome, f, m), campos in fisicas.items():
        fis_par[(f, m)].append((frozenset(campos), nome))
    na_base = defaultdict(set)                     # constraints presentes na base, por par
    for l in linhas:
        if l.get('constraint_nome'):
            na_base[_chave(l['tabela_filha'], l['tabela_mae'])].add(l['constraint_nome'])
    ligacoes = defaultdict(list)
    for l in linhas:
        if not l.get('constraint_nome') and l.get('ligacao') is not None:
            ligacoes[(*_chave(l['tabela_filha'], l['tabela_mae']), l['ligacao'])].append(l)
    marcas, contagem = {}, Counter()
    for (f, m, _lig), ls in ligacoes.items():
        trocados = frozenset((cm, cf) for cf, cm in (_chave(x['campo_filho'], x['campo_mae']) for x in ls))
        prova = next((nome for campos, nome in fis_par.get((m, f), []) if campos == trocados), None)
        if prova is None or f == m:
            contagem['sem_prova_de_inversao'] += 1
            continue
        direcao = 'duplicata_inversa' if prova in na_base.get((m, f), ()) else 'invertida'
        contagem[direcao] += 1
        for x in ls:
            marcas[x['rowid']] = (direcao, prova)
    return marcas, dict(contagem)


def corrigir(dir_csvs, db_path, destino_backup=None):
    rels_csv = _ler(os.path.join(dir_csvs, 'relacionamentos.csv'))
    if not rels_csv:
        raise FileNotFoundError(f'relacionamentos.csv (catálogo) não encontrado em {dir_csvs}')
    conn = sqlite3.connect(db_path)
    try:
        versao = migracoes.versao_atual(conn)
    finally:
        conn.close()
    if versao < VERSAO_MINIMA:
        raise RuntimeError(f'base na versão {versao}; rode `york.py migrar aplicar` antes '
                           f'(a correção precisa da versão {VERSAO_MINIMA})')
    if migracoes._sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite presentes: {migracoes._sobras(db_path)}')

    copia = migracoes.copiar_seguranca(db_path, destino_backup)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN IMMEDIATE')
        linhas = [dict(r) for r in conn.execute(
            'SELECT rowid, tabela_filha, campo_filho, tabela_mae, campo_mae, constraint_nome, ligacao '
            'FROM relacionamentos ORDER BY rowid')]
        marcas, contagem = classificar(linhas, rels_csv)
        conn.execute('UPDATE relacionamentos SET direcao = NULL, direcao_prova = NULL')
        conn.executemany('UPDATE relacionamentos SET direcao = ?, direcao_prova = ? WHERE rowid = ?',
                         [(d, p, rid) for rid, (d, p) in sorted(marcas.items())])
        tabelas = [r[0] for r in conn.execute('SELECT tabela FROM tabelas')]
        antes = {r[0]: tuple(r[1:]) for r in conn.execute(
            'SELECT tabela, score_relevancia, ranking, tabelas_filhas, tabelas_pais, conexoes_totais FROM tabelas')}
        pares = [(f, m) for f, m in conn.execute('SELECT tabela_filha, tabela_mae FROM relacionamentos_corrigidos')]
        metricas = calcular_metricas_e_scores(tabelas, pares)
        mudaram = 0
        for t, mm in metricas.items():
            novo = (mm['score_relevancia'], mm['ranking'], mm['tabelas_filhas'], mm['tabelas_pais'],
                    mm['conexoes_totais'])
            if antes.get(t) != novo:
                mudaram += 1
            conn.execute('UPDATE tabelas SET score_relevancia = ?, ranking = ?, tabelas_filhas = ?, tabelas_pais = ?, '
                         'conexoes_totais = ? WHERE tabela = ?', novo + (t,))
        conn.execute("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('direcao:corrigida', ?)",
                     (f"{migracoes._agora()} | invertidas {contagem.get('invertida', 0)} | duplicatas inversas "
                      f"{contagem.get('duplicata_inversa', 0)} | sem prova {contagem.get('sem_prova_de_inversao', 0)}",))
        conn.execute('COMMIT')
        ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise RuntimeError(f'integrity_check depois da correção: {ok}')
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except sqlite3.OperationalError:
            pass
        conn.close()
        shutil.copy2(copia, db_path)
        raise
    conn.close()
    if migracoes._sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite ficaram para trás: {migracoes._sobras(db_path)}')
    return {'copia': copia, 'ligacoes': contagem, 'linhas_marcadas': len(marcas),
            'tabelas_com_metrica_alterada': mudaram}
