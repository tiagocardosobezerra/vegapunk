"""
Enriquecimento da estrutura de uma base já importada (fase 2 da v3).

Grava tipo, tamanho, precisão, escala, nulo, ordem e posição na PK de cada
coluna, e o nome da constraint e a ordem de cada linha de FK, a partir dos
CSVs da extração física (`punk_records/extracao/*.sql`, só catálogo). Só faz
UPDATE em linhas que JÁ EXISTEM na base, e nunca toca em descrição, em par de
FK, em `tem_dados` nem nas métricas de ranking: a busca continua igual por
construção. Nomes são comparados sem diferenciar maiúsculas de minúsculas.

Colunas casam por (tabela, coluna).

Relacionamentos: a base guarda os relacionamentos LÓGICOS do dicionário do
sistema, uma linha por campo, sem identificador de relacionamento. O
catálogo traz as FKs FÍSICAS, com nome de constraint. Uma FK física só é
aplicada quando ela inteira cabe nas linhas lógicas: mesma tabela filha,
mesma tabela mãe e o CONJUNTO completo de campos (filho -> mãe) presente
entre as linhas daquele par ainda sem constraint. Aí cada linha usada recebe
o nome da constraint e a ordem do campo nela. FK física que casa só em parte
não marca nada. Linha lógica que nenhuma FK física cobre fica sem constraint
(o detalhar avisa; nunca há palpite).

Ligações do dicionário (fase 3-0b, `--dicionario`): o relacionamentos.csv
do dicionário do sistema traz UMA linha por ligação, com os campos em lista.
Cada ligação recebe um número e cada linha da base que a compõe recebe esse
número em `ligacao`, só quando TODOS os campos dela casam com linhas da base
ainda livres (cada linha da base serve a uma ligação só). Ligação que não
casa inteira não marca nada e entra no relatório. O relatório também conta
os conflitos: constraint x dicionário (agrupam diferente; o detalhar não usa
nenhum dos dois) e dicionário x chave da mãe (vence o dicionário).

O texto literal NULL de exportação vira vazio (contado no relatório).

Tudo numa transação, com cópia de segurança antes (a mesma das migrações).
Usado só pelo York (`york.py enriquecer`).
"""

import os
import shutil
import sqlite3
from collections import defaultdict

from punk_records import migracoes
from punk_records.schema import (COLUNAS_ESTRUTURA, CsvVazioError, estrutura_da_coluna,  # noqa: F401
                                 estrutura_do_relacionamento, expandir_ligacoes, ler_csv_extracao, limpar_nulos)

VERSAO_MINIMA = 2              # migração 002 criou as colunas de estrutura
VERSAO_MINIMA_DICIONARIO = 3   # migração 003 criou relacionamentos.ligacao


def _ler(caminho, nulos=None):
    """Linhas do CSV; [] se o arquivo não existe. CSV vazio ou só com
    cabeçalho levanta CsvVazioError (nunca passa em silêncio). O texto NULL
    vira vazio; a contagem vai para `nulos[nome do arquivo]`."""
    if not os.path.exists(caminho):
        return []
    regs = ler_csv_extracao(caminho)[1]
    n = limpar_nulos(regs)
    if nulos is not None:
        nulos[os.path.basename(caminho)] = n
    return regs


def _chave(*nomes):
    return tuple((n or '').strip().upper() for n in nomes)


def _aplicar_colunas(conn, colunas_csv):
    por_chave = defaultdict(list)
    for rowid, t, c in conn.execute('SELECT rowid, tabela, coluna FROM colunas'):
        por_chave[_chave(t, c)].append(rowid)
    sets = ', '.join(f'{c} = ?' for c in COLUNAS_ESTRUTURA)
    casadas = sem_par = 0
    for row in colunas_csv:
        rowids = por_chave.get(_chave(row['tabela'], row['coluna']))
        if not rowids:
            sem_par += 1
            continue
        for rowid in rowids:
            conn.execute(f'UPDATE colunas SET {sets} WHERE rowid = ?', estrutura_da_coluna(row) + (rowid,))
        casadas += 1
    return {'no_csv': len(colunas_csv), 'enriquecidas': casadas, 'sem_correspondente_na_base': sem_par,
            'na_base': sum(len(v) for v in por_chave.values())}


def _aplicar_relacionamentos(conn, rels_csv):
    tabelas_base = {_chave(t)[0] for (t,) in conn.execute('SELECT tabela FROM tabelas')}
    # linhas lógicas por par (FILHA, MÃE): [(rowid, CAMPO_FILHO, CAMPO_MAE)]
    por_par = defaultdict(list)
    for rowid, f, cf, m, cm in conn.execute(
            'SELECT rowid, tabela_filha, campo_filho, tabela_mae, campo_mae FROM relacionamentos ORDER BY rowid'):
        por_par[_chave(f, m)].append((rowid, *_chave(cf, cm)))
    total_linhas = sum(len(v) for v in por_par.values())

    # FKs físicas: constraint -> par e campos em ordem
    fisicas = defaultdict(list)
    for row in rels_csv:
        nome, ordem = estrutura_do_relacionamento(row)
        par = _chave(row['tabela_filha'], row['tabela_mae'])
        fisicas[(nome or '', *par)].append((ordem or 0, *_chave(row['campo_filho'], row['campo_mae'])))

    usadas = set()
    contagem = {'aplicadas': 0, 'parciais_nao_aplicadas': 0, 'ausentes_do_dicionario': 0,
                'fora_das_tabelas_da_base': 0, 'sem_nome': 0}
    for (nome, filha, mae), campos in sorted(fisicas.items()):
        if not nome:
            contagem['sem_nome'] += 1
            continue
        if filha not in tabelas_base or mae not in tabelas_base:
            contagem['fora_das_tabelas_da_base'] += 1
            continue
        livres = [l for l in por_par.get((filha, mae), []) if l[0] not in usadas]
        escolhidas = []
        for ordem, cf, cm in sorted(campos):
            linha = next((l for l in livres if l[1] == cf and l[2] == cm and l not in escolhidas), None)
            if linha is None:
                break
            escolhidas.append(linha)
        if len(escolhidas) == len(campos):
            for (ordem, _cf, _cm), (rowid, _a, _b) in zip(sorted(campos), escolhidas):
                conn.execute('UPDATE relacionamentos SET constraint_nome = ?, ordem = ? WHERE rowid = ?',
                             (nome, ordem or None, rowid))
                usadas.add(rowid)
            contagem['aplicadas'] += 1
        elif escolhidas or any(l[1:] == (cf, cm) for l in por_par.get((filha, mae), []) for _o, cf, cm in campos):
            contagem['parciais_nao_aplicadas'] += 1
        else:
            contagem['ausentes_do_dicionario'] += 1

    pares_total = len(por_par)
    cobertos = sum(1 for linhas in por_par.values() if all(l[0] in usadas for l in linhas))
    parciais = sum(1 for linhas in por_par.values()
                   if any(l[0] in usadas for l in linhas) and not all(l[0] in usadas for l in linhas))
    ambiguos = [linhas for linhas in por_par.values()
                if len({l[1] for l in linhas}) < len(linhas) or len({l[2] for l in linhas}) < len(linhas)]
    compostos = [linhas for linhas in por_par.values() if len(linhas) > 1]
    return {
        'linhas_logicas': total_linhas,
        'linhas_logicas_com_constraint': len(usadas),
        'linhas_logicas_sem_constraint': total_linhas - len(usadas),
        'pares_logicos': pares_total,
        'pares_cobertos_inteiros': cobertos,
        'pares_cobertos_em_parte': parciais,
        'pares_sem_constraint': pares_total - cobertos - parciais,
        'pares_compostos': len(compostos),
        'pares_compostos_cobertos_inteiros': sum(1 for ls in compostos if all(l[0] in usadas for l in ls)),
        'pares_ambiguos': len(ambiguos),
        'pares_ambiguos_resolvidos': sum(1 for ls in ambiguos if all(l[0] in usadas for l in ls)),
        'fks_fisicas_no_csv': len(fisicas),
        'fks_fisicas_aplicadas': contagem['aplicadas'],
        'fks_fisicas_casadas_so_em_parte_nao_aplicadas': contagem['parciais_nao_aplicadas'],
        'fks_fisicas_entre_tabelas_da_base_ausentes_do_dicionario': contagem['ausentes_do_dicionario'],
        'fks_fisicas_fora_das_tabelas_da_base': contagem['fora_das_tabelas_da_base'],
        'fks_fisicas_sem_nome': contagem['sem_nome'],
    }


def _aplicar_ligacoes(conn, ligacoes_csv):
    """Grava o número da ligação do dicionário nas linhas da base (só UPDATE).
    Casa com as linhas de `relacionamentos` (uma ponta pode estar fora de
    `tabelas`: a ligação vale do mesmo jeito para a outra ponta)."""
    conn.execute('UPDATE relacionamentos SET ligacao = NULL')
    por_par = defaultdict(list)
    for rowid, f, cf, m, cm in conn.execute(
            'SELECT rowid, tabela_filha, campo_filho, tabela_mae, campo_mae FROM relacionamentos ORDER BY rowid'):
        por_par[_chave(f, m)].append((rowid, *_chave(cf, cm)))
    linhas, n_ligacoes = expandir_ligacoes(ligacoes_csv)
    if ligacoes_csv and not n_ligacoes:
        n_ligacoes = len(linhas)    # todas com um campo só: uma ligação por linha
        for i, r in enumerate(sorted(linhas, key=lambda r: _chave(r['tabela_filha'], r['tabela_mae'],
                                                                 r['campo_filho'], r['campo_mae'])), 1):
            r['ligacao'] = str(i)
    por_ligacao = defaultdict(list)
    for r in linhas:
        por_ligacao[int(r['ligacao'])].append(r)
    usadas = set()
    cont = {'aplicadas': 0, 'nao_casadas': 0, 'sem_par_na_base': 0}
    for n, campos in sorted(por_ligacao.items()):
        par = _chave(campos[0]['tabela_filha'], campos[0]['tabela_mae'])
        if par not in por_par:
            cont['sem_par_na_base'] += 1
            continue
        livres = [l for l in por_par.get(par, []) if l[0] not in usadas]
        escolhidas = []
        for c in campos:
            alvo = _chave(c['campo_filho'], c['campo_mae'])
            linha = next((l for l in livres if l[1:] == alvo and l not in escolhidas), None)
            if linha is None:
                break
            escolhidas.append(linha)
        if len(escolhidas) < len(campos):
            cont['nao_casadas'] += 1
            continue
        for rowid, _a, _b in escolhidas:
            conn.execute('UPDATE relacionamentos SET ligacao = ? WHERE rowid = ?', (n, rowid))
            usadas.add(rowid)
        cont['aplicadas'] += 1
    total = sum(len(v) for v in por_par.values())
    compostos = [ls for ls in por_par.values() if len(ls) > 1]
    return {'ligacoes_no_csv': n_ligacoes, 'ligacoes_aplicadas': cont['aplicadas'],
            'ligacoes_nao_casadas_inteiras': cont['nao_casadas'],
            'ligacoes_sem_par_na_base': cont['sem_par_na_base'],
            'linhas_com_ligacao': len(usadas), 'linhas_sem_ligacao': total - len(usadas),
            'pares_compostos': len(compostos),
            'pares_compostos_agrupados_pelo_dicionario': sum(1 for ls in compostos if all(l[0] in usadas for l in ls))}


def _conflitos(conn):
    """Constraint x dicionário e dicionário x chave da mãe, por par (filha, mãe),
    contados pelo próprio agrupamento do detalhar (`agrupar_fks`)."""
    from collections import Counter
    from nomi_nomi_no_mi.grafo import agrupar_fks
    pk = defaultdict(dict)
    for t, c, o in conn.execute('SELECT tabela, coluna, pk_ordem FROM colunas WHERE pk_ordem IS NOT NULL'):
        pk[t][c.strip().upper()] = o
    cols = ('tabela_filha', 'campo_filho', 'tabela_mae', 'campo_mae', 'constraint_nome', 'ordem', 'ligacao')
    linhas = [dict(zip(cols, row)) for row in conn.execute(f'SELECT {", ".join(cols)} FROM relacionamentos ORDER BY rowid')]
    conta = Counter()
    agrupar_fks(linhas, None, lambda t: pk.get(t, {}), conta)
    return {'pares_em_conflito_constraint_x_dicionario': conta['conflito_constraint_dicionario'],
            'pares_em_conflito_dicionario_x_chave_da_mae_vence_dicionario': conta['dicionario_vence_chave_da_mae']}

def enriquecer(dir_csvs, db_path, destino_backup=None, dir_dicionario=None):
    nulos = {}
    colunas_csv = _ler(os.path.join(dir_csvs, 'colunas.csv'), nulos) if dir_csvs else []
    rels_csv = _ler(os.path.join(dir_csvs, 'relacionamentos.csv'), nulos) if dir_csvs else []
    nulos_dic = {}
    ligacoes_csv = _ler(os.path.join(dir_dicionario, 'relacionamentos.csv'), nulos_dic) if dir_dicionario else []
    if dir_dicionario and not ligacoes_csv:
        raise FileNotFoundError(f'relacionamentos.csv não encontrado em {dir_dicionario}')
    if not colunas_csv and not rels_csv and not ligacoes_csv:
        raise FileNotFoundError(f'nem colunas.csv nem relacionamentos.csv em {dir_csvs}')

    conn = sqlite3.connect(db_path)
    try:
        versao = migracoes.versao_atual(conn)
    finally:
        conn.close()
    minima = VERSAO_MINIMA_DICIONARIO if ligacoes_csv else VERSAO_MINIMA
    if versao < minima:
        raise RuntimeError(f'base na versão {versao}; rode `york.py migrar aplicar` antes '
                           f'(o enriquecimento precisa da versão {minima})')
    if migracoes._sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite presentes: {migracoes._sobras(db_path)}')

    copia = migracoes.copiar_seguranca(db_path, destino_backup)
    relatorio = {'copia': copia, 'nulos_convertidos': sum(nulos.values()) + sum(nulos_dic.values())}
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute('BEGIN IMMEDIATE')
        if colunas_csv:
            relatorio['colunas'] = _aplicar_colunas(conn, colunas_csv)
        if rels_csv:
            relatorio['relacionamentos'] = _aplicar_relacionamentos(conn, rels_csv)
        if ligacoes_csv:
            relatorio['dicionario'] = _aplicar_ligacoes(conn, ligacoes_csv)
            relatorio['dicionario'].update(_conflitos(conn))
        conn.execute('COMMIT')
        ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise RuntimeError(f'integrity_check depois do enriquecimento: {ok}')
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
    return relatorio
