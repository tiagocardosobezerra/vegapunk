"""
Atualização NO LUGAR da base a partir de um export novo do dicionário do
sistema (fase 5 da v3, bloco 5a). Alternativa ao `importar --forcar`, que
recria a base do zero e perderia o que veio depois do import (migrações,
ligações do dicionário, direção corrigida, mapa, papéis confirmados,
sinônimos).

O que muda, e só isto:
- tabelas: descrição (o texto literal NULL vira vazio, como no import),
  `tem_dados`, tabela nova (com as métricas de ranking recalculadas pela
  mesma função do `importar`, sobre a leitura corrigida das FKs);
- colunas: descrição, coluna nova (com tipo, tamanho, nulo, ordem e posição
  na PK do catálogo, quando ele traz a coluna) e coluna removida (só se nada
  da base a usa: FK, mapa);
- nada mais: `sistemas` (cadastros do usuário, como o módulo Z), ligações,
  direção, mapa, papéis e sinônimos não são tocados. Diferenças fora dessa
  lista (ligações, tabela removida) só aparecem no relatório.

`planejar` só lê e devolve a lista do que muda; `aplicar` faz a mesma lista
numa transação, com cópia de segurança antes. Só o York chama.
"""

import os
import shutil
import sqlite3

from punk_records import migracoes
from punk_records.schema import (COLUNAS_ESTRUTURA, calcular_metricas_e_scores, estrutura_da_coluna,
                                 expandir_ligacoes, ler_csv_extracao, limpar_nulos)

VERDADEIROS = {'1', 'true', 'sim', 's', 'yes', 'y'}


def _ler(caminho):
    if not os.path.exists(caminho):
        return []
    regs = ler_csv_extracao(caminho)[1]
    limpar_nulos(regs)
    return regs


def _u(s):
    return (s or '').strip()


def planejar(db_path, dir_dicionario, dir_catalogo=None):
    """Lista do que muda (só leitura)."""
    tab_csv = {_u(r['tabela']): r for r in _ler(os.path.join(dir_dicionario, 'tabelas.csv'))}
    col_csv = {(_u(r['tabela']), _u(r['coluna'])): r for r in _ler(os.path.join(dir_dicionario, 'colunas.csv'))}
    if not tab_csv or not col_csv:
        raise FileNotFoundError(f'tabelas.csv e colunas.csv do dicionário são obrigatórios em {dir_dicionario}')
    cat = {}
    if dir_catalogo:
        for r in _ler(os.path.join(dir_catalogo, 'colunas.csv')):
            cat[(_u(r['tabela']).upper(), _u(r['coluna']).upper())] = r
    conn = sqlite3.connect(f'file:{os.path.abspath(db_path)}?mode=ro', uri=True)
    try:
        tab_db = {t: (d, td) for t, d, td in conn.execute('SELECT tabela, descricao, tem_dados FROM tabelas')}
        col_db = {(t, c): d for t, c, d in conn.execute('SELECT tabela, coluna, descricao FROM colunas')}
        usadas = {(f.upper(), cf.upper()) for f, cf, m, cm in
                  conn.execute('SELECT tabela_filha, campo_filho, tabela_mae, campo_mae FROM relacionamentos')}
        usadas |= {(m.upper(), cm.upper()) for f, cf, m, cm in
                   conn.execute('SELECT tabela_filha, campo_filho, tabela_mae, campo_mae FROM relacionamentos')}
        for tabela in ('mapa_papeis', 'mapa_cadastros'):
            try:
                if tabela == 'mapa_papeis':
                    usadas |= {(t.upper(), c.upper()) for t, c in conn.execute('SELECT tabela, coluna FROM mapa_papeis')}
                else:
                    for t, cod, desc in conn.execute('SELECT tabela, coluna_codigo, coluna_descricao FROM mapa_cadastros'):
                        usadas |= {(t.upper(), (cod or '').upper()), (t.upper(), (desc or '').upper())}
            except sqlite3.OperationalError:
                pass
        rel_db = {tuple(x.upper() for x in r) for r in
                  conn.execute('SELECT tabela_filha, campo_filho, tabela_mae, campo_mae FROM relacionamentos')}
    finally:
        conn.close()
    p = {'tabelas_novas': [], 'tabelas_descricao': [], 'tabelas_tem_dados': [], 'colunas_novas': [],
         'colunas_removidas': [], 'colunas_removidas_recusadas': [], 'colunas_descricao': [],
         'fora_da_lista': {'tabelas_removidas': sorted(set(tab_db) - set(tab_csv)), 'ligacoes_so_no_dicionario': []}}
    for t, r in sorted(tab_csv.items()):
        # mesma normalização do `importar`: descrição de TABELA vazia é NULL
        desc = _u(r.get('descricao')) or None
        td = 1 if _u(r.get('tem_dados')).lower() in VERDADEIROS else 0
        if t not in tab_db:
            p['tabelas_novas'].append({'tabela': t, 'descricao': desc, 'tem_dados': td})
            continue
        if tab_db[t][0] != desc:
            p['tabelas_descricao'].append({'tabela': t, 'de': tab_db[t][0], 'para': desc})
        if tab_db[t][1] != td:
            p['tabelas_tem_dados'].append({'tabela': t, 'de': tab_db[t][1], 'para': td})
    for (t, c), r in sorted(col_csv.items()):
        desc = _u(r.get('descricao'))
        if (t, c) not in col_db:
            est = cat.get((t.upper(), c.upper()))
            p['colunas_novas'].append({'tabela': t, 'coluna': c, 'descricao': desc,
                                       'estrutura': dict(zip(COLUNAS_ESTRUTURA, estrutura_da_coluna(est)))
                                       if est else None})
        elif (col_db[(t, c)] or '') != desc:
            p['colunas_descricao'].append({'tabela': t, 'coluna': c, 'de': col_db[(t, c)], 'para': desc})
    for (t, c) in sorted(set(col_db) - set(col_csv)):
        if t not in tab_csv:
            continue                                   # tabela fora do export: não é remoção de coluna
        alvo = p['colunas_removidas_recusadas'] if (t.upper(), c.upper()) in usadas else p['colunas_removidas']
        alvo.append({'tabela': t, 'coluna': c, 'descricao': col_db[(t, c)]})
    lig = _ler(os.path.join(dir_dicionario, 'relacionamentos.csv'))
    if lig:
        linhas, _ = expandir_ligacoes(lig) if any(',' in (r.get('campo_filho') or '') for r in lig) else (lig, 0)
        csv = {tuple(_u(x[k]).upper() for k in ('tabela_filha', 'campo_filho', 'tabela_mae', 'campo_mae'))
               for x in linhas}
        p['fora_da_lista']['ligacoes_so_no_dicionario'] = sorted(csv - rel_db)
    return p


def aplicar(db_path, dir_dicionario, dir_catalogo=None, destino_backup=None):
    p = planejar(db_path, dir_dicionario, dir_catalogo)
    if migracoes._sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite presentes: {migracoes._sobras(db_path)}')
    copia = migracoes.copiar_seguranca(db_path, destino_backup)
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute('BEGIN IMMEDIATE')
        for x in p['tabelas_descricao']:
            conn.execute('UPDATE tabelas SET descricao = ? WHERE tabela = ?', (x['para'], x['tabela']))
        for x in p['tabelas_tem_dados']:
            conn.execute('UPDATE tabelas SET tem_dados = ? WHERE tabela = ?', (x['para'], x['tabela']))
        for x in p['tabelas_novas']:
            conn.execute('INSERT INTO tabelas (tabela, descricao, score_relevancia, ranking, tabelas_filhas, '
                         'tabelas_pais, conexoes_totais, tem_dados) VALUES (?, ?, 0, 0, 0, 0, 0, ?)',
                         (x['tabela'], x['descricao'], x['tem_dados']))
        for x in p['colunas_descricao']:
            conn.execute('UPDATE colunas SET descricao = ? WHERE tabela = ? AND coluna = ?',
                         (x['para'], x['tabela'], x['coluna']))
        cols = {r[1] for r in conn.execute('PRAGMA table_info(colunas)')}
        for x in p['colunas_novas']:
            est = {k: v for k, v in (x['estrutura'] or {}).items() if k in cols}
            nomes = ['tabela', 'coluna', 'descricao'] + list(est)
            conn.execute(f'INSERT INTO colunas ({", ".join(nomes)}) VALUES ({", ".join("?" for _ in nomes)})',
                         [x['tabela'], x['coluna'], x['descricao']] + list(est.values()))
        for x in p['colunas_removidas']:
            conn.execute('DELETE FROM colunas WHERE tabela = ? AND coluna = ?', (x['tabela'], x['coluna']))
        if p['tabelas_novas']:
            fonte = 'relacionamentos_corrigidos' if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'view' AND name = 'relacionamentos_corrigidos'"
            ).fetchone() else 'relacionamentos'
            tabelas = [r[0] for r in conn.execute('SELECT tabela FROM tabelas')]
            pares = conn.execute(f'SELECT tabela_filha, tabela_mae FROM {fonte}').fetchall()
            for t, m in calcular_metricas_e_scores(tabelas, pares).items():
                conn.execute('UPDATE tabelas SET score_relevancia = ?, ranking = ?, tabelas_filhas = ?, tabelas_pais = ?, '
                             'conexoes_totais = ? WHERE tabela = ?',
                             (m['score_relevancia'], m['ranking'], m['tabelas_filhas'], m['tabelas_pais'],
                              m['conexoes_totais'], t))
        conn.execute("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('atualizacao:dicionario', ?)",
                     (f"{migracoes._agora()} | tabelas novas {len(p['tabelas_novas'])} | descrições de tabela "
                      f"{len(p['tabelas_descricao'])} | tem_dados {len(p['tabelas_tem_dados'])} | colunas novas "
                      f"{len(p['colunas_novas'])} | colunas removidas {len(p['colunas_removidas'])} | descrições de "
                      f"coluna {len(p['colunas_descricao'])}",))
        conn.execute('COMMIT')
        ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise RuntimeError(f'integrity_check depois da atualização: {ok}')
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
    return dict(p, copia=copia)
