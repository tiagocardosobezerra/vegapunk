"""
Ligação de parâmetros pelo mapa e SQL de apoio (fase 3 da v3).

Lado da DESCOBERTA: lê a camada Mapa já compilada na Punk Records (tabelas
`mapa_*`, que só o York escreve) e, para cada parâmetro de função, diz a que
cadastro, tabela e coluna o código aponta. Para os parâmetros ligados,
escreve um SQL de apoio com a CHAVE COMPLETA do cadastro, para o próprio
usuário achar o código certo no banco dele. O motor NUNCA executa esse SQL
nem vê o resultado. O SQL é validado pelo Shaka quanto a nomes de tabela e
coluna (`dominios/formulas/sql_apoio.py`), na ponte da Stella.

Não importa o motor de fórmulas: recebe a ficha da função como dicionário.
Sem camada Mapa na base, `carregar_mapa` devolve None e nada muda.
"""

import json
import os
import sqlite3

from dominios.mapa_rotulos import entidade_de_codigo, ligar_parametro


def carregar_mapa(db_path):
    """Mapa compilado (dict) ou None se a base não tem a camada Mapa preenchida."""
    if not db_path or not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(f'file:{os.path.abspath(db_path)}?mode=ro', uri=True)
    try:
        tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if 'mapa_cadastros' not in tabelas:
            return None
        cadastros = {}
        for c, t, chave, cod, desc in conn.execute(
                'SELECT cadastro, tabela, chave, coluna_codigo, coluna_descricao FROM mapa_cadastros'):
            cadastros[c] = {'cadastro': c, 'tabela': t, 'chave': json.loads(chave), 'coluna_codigo': cod,
                            'coluna_descricao': desc, 'funcoes': set(), 'entidades': set(), 'avisos': []}
        if not cadastros:
            return None
        for c, fn in conn.execute('SELECT cadastro, funcao FROM mapa_funcoes'):
            cadastros[c]['funcoes'].add(fn.upper())
        for c, r in conn.execute('SELECT cadastro, rotulo FROM mapa_rotulos'):
            e = entidade_de_codigo(r)
            if e:
                cadastros[c]['entidades'].add(e)
        desc = {}
        for t, col, d in conn.execute('SELECT tabela, coluna, descricao FROM colunas'):
            if col != '#':
                desc.setdefault(t.upper(), {})[col.upper()] = d or ''
        # Só os papéis que a ligação de parâmetro USA (código e descrição do
        # cadastro). Um papel divergente da ligação cadastro -> fórmula não entra
        # aqui: aparece quando a resposta usa essa ligação, no `compilar-mapa` e
        # no `stella.py status`.
        for dono, papel, t, col, parte in conn.execute(
                "SELECT dono, papel, tabela, coluna, parte FROM mapa_papeis WHERE papel_divergente = 1 "
                "AND parte = 'cadastro'"):
            if dono in cadastros:
                cadastros[dono]['avisos'].append(
                    f"{t}.{col} está declarada no mapa com o papel '{papel}' ({parte}), mas a descrição da coluna "
                    f"diz: {desc.get(t, {}).get(col, '')!r}. O papel vem da descrição: confira com o usuário.")
        referidas = {c['tabela'] for c in cadastros.values()}
        nomes = {t: set(desc.get(t, {})) for t in referidas}
    finally:
        conn.close()
    return {'cadastros': cadastros, 'nomes': nomes}


def sql_de_apoio(cad):
    """SELECT da chave completa (+ descrição) do cadastro, ordenado pela chave."""
    colunas = list(cad['chave'])
    if cad['coluna_codigo'] not in colunas:
        colunas.append(cad['coluna_codigo'])
    if cad.get('coluna_descricao') and cad['coluna_descricao'] not in colunas:
        colunas.append(cad['coluna_descricao'])
    return f"SELECT {', '.join(colunas)} FROM {cad['tabela']} ORDER BY {', '.join(cad['chave'])}"


def ligacoes(mapa, ficha):
    """Uma entrada por parâmetro de código da ficha: ligado (com cadastro,
    coluna, chave e SQL de apoio) ou só rótulo."""
    out = []
    cadastros = list(mapa['cadastros'].values())
    for p in ficha.get('parametros') or []:
        rotulo = p.get('rotulo_documentado') or ''
        e = entidade_de_codigo(rotulo)
        if e is None:
            continue
        c = ligar_parametro(ficha['nome'], rotulo, cadastros)
        if not c:
            out.append({'posicao': p.get('posicao'), 'rotulo': rotulo, 'ligado': False,
                        'motivo': 'sem ligação provada no mapa: o parâmetro continua só um rótulo'})
            continue
        cad = mapa['cadastros'][c]
        item = {'posicao': p.get('posicao'), 'rotulo': rotulo, 'ligado': True, 'cadastro': c,
                'tabela': cad['tabela'], 'coluna_codigo': cad['coluna_codigo'],
                'coluna_descricao': cad.get('coluna_descricao'), 'chave': cad['chave'],
                'sql_apoio': sql_de_apoio(cad)}
        if len(cad['chave']) > 1:
            item['chave_completa'] = ('o código só é único junto com ' +
                                      ', '.join(k for k in cad['chave'] if k != cad['coluna_codigo']) +
                                      ': o argumento é o valor de ' + cad['coluna_codigo'] + ' da linha certa')
        if cad['avisos']:
            item['avisos'] = list(cad['avisos'])
        out.append(item)
    return out
