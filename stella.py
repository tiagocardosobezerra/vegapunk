#!/usr/bin/env python3
"""
================================================================================
 STELLA — entrada única do fluxo do Vegapunk
================================================================================
Nome: Stella é o corpo original do Vegapunk, o que coordena os satélites.
Aqui ela recebe o pedido e despacha para o domínio certo:

- `--dominio schema`: descoberta de schema (Nomi Nomi no Mi);
- `--dominio formulas`: dicionário de funções e compositor (Shaka).

Os comandos de cada domínio continuam em `nomi_nomi_no_mi/comandos.py` e em
`satelites/shaka.py`, com a mesma saída de antes. Desde a fase 4 a Stella
também ORQUESTRA: `solucionar` recebe o pedido já quebrado em intenções pelo
Claude (contrato JSON, ver `dominios/solucao.py` e
referencias/fluxo-solucao.md), busca cada intenção no domínio certo, junta,
valida a fórmula e aponta as lacunas.

Uso:
    python3 stella.py buscar    --dominio schema   "<pedido>" [--limite 30] [--json]
    python3 stella.py detalhar  --dominio schema   TABELA [TABELA ...] [--completo] [--json]
    python3 stella.py confirmar --dominio schema   "<pedido>" TABELA [TABELA ...]
    python3 stella.py checar-modulos [--json]

    python3 stella.py buscar    --dominio formulas "<pedido>" [--contexto CTX] [--limite 10] [--json]
    python3 stella.py detalhar  --dominio formulas FUNCAO [FUNCAO ...] [--contexto CTX] [--completo]
    python3 stella.py confirmar --dominio formulas "<pedido>" FUNCAO [FUNCAO ...] [--contexto CTX]
    python3 stella.py aceitar   ID_DA_CANDIDATA [--observacao TEXTO]
    python3 stella.py validar   "<fórmula>" | --arquivo ARQ  [--contexto CTX] [--uso USO]
    python3 stella.py explicar  "<fórmula>" | --arquivo ARQ  [--contexto CTX] [--uso USO]
    python3 stella.py compor    --plano ARQ | --plano-json JSON [--contexto CTX] [--uso USO]
    python3 stella.py formatar  "<fórmula>"
    python3 stella.py contextos | pacotes

    python3 stella.py solucionar --intencoes ARQ | --intencoes-json JSON [--uso USO] [--limite 5]
                                 [--sem-registro] [--json]
        solução agrupada por intenção, com lacunas explícitas; registrada
        como candidata a confirmação na instância.

    python3 stella.py cartao COMANDO [...]
        Memory Card (satelites/memory_card.py): iniciar, catalogo, buscar,
        enviar, marcar, conferir e migrar. Ver referencias/memory-card.md.

    python3 stella.py status [--json]
        camadas presentes, versão e tamanho da base, pacotes de fórmulas e os
        avisos de merge entre camadas (que antes saíam em todo comando).

    python3 stella.py instancias [--json]
        instâncias locais (egghead/ e egghead-<nome>/) e qual está ativa.

Flags gerais (antes ou depois do comando): --json e --instancia NOME
(usa egghead-NOME/; egghead = a padrão; o mesmo vale no york.py). Antes do
comando: --db BANCO (schema), --pacotes DIR, --privado DIR,
--somente-publico e --pacote ID (fórmulas).

Manutenção fica nos satélites: York (escrita), Edison (análise),
Pythagoras (avaliação e calibração), Lilith (casos sintéticos) e Atlas
(golden e isolamento), em `satelites/`.
================================================================================
"""

import argparse
import json
import os
import sqlite3
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
SATELITES = os.path.join(RAIZ, 'satelites')
sys.path.insert(0, RAIZ)
sys.path.insert(0, SATELITES)

TABELAS_SCHEMA = ('tabelas', 'colunas', 'relacionamentos', 'sistemas', 'sinonimos')


def _db_padrao():
    from dominios.schema.config import DEFAULT_DB_PATH
    return DEFAULT_DB_PATH


# ------------------------------------------------------------------ status
def _status_schema(db):
    """Só estrutura e contagens; abre a base em modo leitura."""
    if not os.path.exists(db):
        return {'instalado': False, 'db': db}
    from punk_records.migracoes import versao_atual, MIGRACOES
    from punk_records.instancias import abrir_leitura
    conn = abrir_leitura(db)
    try:
        contagens = {}
        for t in TABELAS_SCHEMA:
            try:
                contagens[t] = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            except sqlite3.OperationalError:
                contagens[t] = None
        versao = versao_atual(conn)
        mapa = _status_mapa(conn)
    finally:
        conn.close()
    log = os.path.join(os.path.dirname(os.path.abspath(db)), 'punk_records_log.jsonl')
    confirmacoes = 0
    if os.path.exists(log):
        with open(log, encoding='utf-8') as f:
            confirmacoes = sum(1 for linha in f if '"tipo": "confirmacao"' in linha)
    return {'instalado': True, 'db': db, 'versao_schema': versao,
            'versao_alvo': max(m[0] for m in MIGRACOES), 'contagens': contagens,
            'confirmacoes_no_log': confirmacoes, 'mapa': mapa}


def _status_mapa(conn):
    """Camada Mapa (fase 3): contagens e papéis divergentes, ou None."""
    try:
        n = conn.execute('SELECT COUNT(*) FROM mapa_cadastros').fetchone()[0]
    except sqlite3.OperationalError:
        return None
    if not n:
        return {'compilado': False}
    divergentes = [{'tabela': t, 'coluna': c, 'papel': p, 'parte': parte, 'dono': dono, 'descricao': d}
                   for t, c, p, parte, dono, d in conn.execute(
                       'SELECT m.tabela, m.coluna, m.papel, m.parte, m.dono, c.descricao FROM mapa_papeis m '
                       'LEFT JOIN colunas c ON c.tabela = m.tabela AND c.coluna = m.coluna '
                       'WHERE m.papel_divergente = 1 ORDER BY m.tabela, m.coluna')]
    try:
        resolvidos = [{'tabela': t, 'coluna': c, 'papel': p, 'confirmado_em': em, 'fonte': f, 'descricao_errada': bool(e)}
                      for t, c, p, em, f, e in conn.execute(
                          "SELECT tabela, coluna, papel, confirmado_em, fonte_do_papel, descricao_errada FROM mapa_papeis "
                          "WHERE prova_do_papel = 'usuario' ORDER BY tabela, coluna")]
    except sqlite3.OperationalError:     # base antes da migração 006
        resolvidos = []
    ficticio = conn.execute("SELECT valor FROM meta WHERE chave = 'mapa:ficticio'").fetchone()
    return {'compilado': True, 'ficticio': bool(ficticio and ficticio[0] == '1'), 'cadastros': n,
            'funcoes': conn.execute('SELECT COUNT(*) FROM mapa_funcoes').fetchone()[0],
            'papeis': conn.execute('SELECT COUNT(*) FROM mapa_papeis').fetchone()[0],
            'papeis_divergentes': divergentes, 'papeis_resolvidos_pelo_usuario': resolvidos}


def _status_formulas(a):
    from dominios.formulas import conhecimento as kb
    base = kb.carregar(a.raiz_pacotes, somente_publico=a.somente_publico, extras=a.privado)
    return {'instalado': bool(base.pacotes),
            'pacotes': [{'id': p.id, 'camada': p.camada, 'funcoes': len(p.funcoes)} for p in base.pacotes],
            'funcoes': len(base.funcoes), 'contextos': len(base.contextos),
            'avisos_de_merge': list(base.avisos)}


def _status_cartao():
    """Memory Card: configurado nesta instância? Só lê a configuração e a
    cópia local do cartão (sem rede, sem `gh`)."""
    try:
        import memory_card
    except ImportError:
        return {'configurado': False}
    try:
        c = memory_card.config()
    except memory_card.EnvioRecusado:
        return {'configurado': False}
    tem_copia = os.path.isdir(c['pasta'])
    fichas = memory_card.ler_catalogo(c['pasta']) if tem_copia else []
    ok, motivo = memory_card.disponivel()
    return {'configurado': True, 'disponivel': ok, 'motivo': motivo, 'repo': c['repo'], 'pasta': c['pasta'],
            'copia_local': tem_copia,
            'saves': len(fichas), 'com_algo_faltando': sum((f.get('conferencia') or {}).get('ok') is False
                                                          for f in fichas)}


def _instancias(a):
    """Só leitura: pasta, base e contagens de cada instância local."""
    from punk_records.instancias import listar
    itens = listar()
    if getattr(a, 'pedido', None):
        from nomi_nomi_no_mi.roteamento import assuntos_no_pedido, cobertura
        for i in itens:
            i['cobertura'] = cobertura(i['base'], a.pedido) if i['tabelas'] is not None else None
            i['assuntos_no_pedido'] = assuntos_no_pedido(i['assuntos'], a.pedido)
        itens.sort(key=lambda i: (-len((i['cobertura'] or {}).get('cobertos', [])),
                                  -len((i['cobertura'] or {}).get('em_nome_de_tabela', [])),
                                  -len(i['assuntos_no_pedido']), i['nome']))
    if a.json:
        print(json.dumps(itens, ensure_ascii=False, indent=1))
        return 0
    if not itens:
        print('Nenhuma instância local (egghead/ ou egghead-<nome>/).')
        return 0
    for i in itens:
        marca = '*' if i['ativa'] else ' '
        base = (f"{i['tabelas']} tabelas, {i['colunas']} colunas" if i['tabelas'] is not None
                else 'base instalada' if i['existe'] else 'sem base')
        print(f"{marca} {i['nome']:<12} {base}  ({i['pasta']})")
        if i['descricao']:
            print(f"               {i['descricao']}")
        if i['assuntos']:
            print(f"               assuntos: {', '.join(i['assuntos'])}")
        if i.get('cobertura'):
            c = i['cobertura']
            print(f"               pedido: cobre {len(c['cobertos'])}/{len(c['termos'])} termo(s)"
                  + (f", {len(c['em_nome_de_tabela'])} em nome de tabela" if c['em_nome_de_tabela'] else '')
                  + (f"; não acha: {', '.join(c['faltando'])}" if c['faltando'] else '')
                  + (f"; assuntos citados: {', '.join(i['assuntos_no_pedido'])}" if i['assuntos_no_pedido'] else ''))
    com = [i for i in itens if i.get('cobertura')]
    if len(com) > 1:
        chave = lambda i: (len(i['cobertura']['cobertos']), len(i['cobertura']['em_nome_de_tabela']),  # noqa: E731
                           len(i['assuntos_no_pedido']))
        a, b = chave(com[0]), chave(com[1])
        if a == b:
            print('\nEMPATE entre as primeiras: pergunte ao usuário qual banco ele quer.')
        elif (a[0], a[2]) == (b[0], b[2]):
            # só o nome de tabela desempata: evidência fraca, o pedido ainda serve às duas
            print(f"\nProvável {com[0]['nome']} (só pelo nome das tabelas): confirme com o usuário antes de seguir.")
        else:
            print(f"\nMais provável para o pedido: {com[0]['nome']} (`--instancia {com[0]['nome']}`).")
    print('\n* = ativa. Troque com `--instancia NOME` no stella.py e no york.py (egghead = a padrão).'
          '\nDescrição e assuntos: `instancia.json` na pasta de cada instância.')
    return 0


def _status_versao():
    """Versão da cópia instalada (`VERSAO.json`, gravado pelo empacotador do
    zip pessoal) e, se o repositório de onde ela saiu existe nesta máquina,
    se ele já está à frente. Sem o arquivo (o próprio repositório ou uma
    distribuição), devolve {}."""
    caminho = os.path.join(RAIZ, 'VERSAO.json')
    try:
        with open(caminho, encoding='utf-8') as f:
            v = json.load(f)
    except (OSError, ValueError):
        return {}
    repo = v.get('repositorio')
    if repo and os.path.isdir(os.path.join(repo, '.git')):
        import subprocess
        try:
            atual = subprocess.run(['git', '-C', repo, 'rev-parse', '--short', 'HEAD'], capture_output=True,
                                   text=True, timeout=10).stdout.strip()
            if atual and v.get('commit') and not atual.startswith(v['commit']) and not v['commit'].startswith(atual):
                n = subprocess.run(['git', '-C', repo, 'rev-list', '--count', f"{v['commit']}..HEAD"],
                                   capture_output=True, text=True, timeout=10).stdout.strip()
                v['aviso'] = (f'o repositório está à frente desta cópia ({n or "?"} commit(s), agora em {atual}): '
                              f'gere o zip de novo com ferramentas/empacotar_privado.py e reinstale a skill')
        except (OSError, subprocess.SubprocessError):
            pass
    return v


def _status(a):
    """Cada domínio é opcional: sem o código ou sem os dados de um deles, o
    status diz que ele roda em modo básico em vez de falhar."""
    try:
        schema = _status_schema(os.path.normpath(a.db or _db_padrao()))
    except ImportError:
        schema = {'instalado': False, 'db': a.db or '(domínio schema não instalado)'}
    try:
        formulas = _status_formulas(a)
    except ImportError:
        formulas = {'instalado': False, 'pacotes': [], 'funcoes': 0, 'contextos': 0, 'avisos_de_merge': []}
    s = {'schema': schema, 'formulas': formulas, 'cartao': _status_cartao(), 'versao': _status_versao()}
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    sc, fo = s['schema'], s['formulas']
    print('Vegapunk — status da instalação')
    v = s['versao']
    if v.get('commit'):
        print(f"  versão:   {v['commit']} de {v.get('data', '?')} (cópia instalada)")
        if v.get('aviso'):
            print(f"  AVISO:    {v['aviso']}")
    from punk_records.instancias import nome_da_pasta, pasta_ativa
    print(f"  instância: {nome_da_pasta(pasta_ativa())} (outras: `stella.py instancias`)")
    if sc['instalado']:
        c = sc['contagens']
        print(f"  schema:   instalado ({sc['db']})")
        print(f"            versão da base {sc['versao_schema']} (alvo {sc['versao_alvo']})")
        print('            ' + ', '.join(f'{n} {t}' for t, n in c.items() if n is not None))
        print(f"            {sc['confirmacoes_no_log']} confirmações no log de uso")
        m = sc.get('mapa')
        if m and m.get('compilado'):
            print(f"  mapa:     compilado{' (fictício)' if m['ficticio'] else ''}: {m['cadastros']} cadastros, "
                  f"{m['funcoes']} funções ligadas, {m['papeis']} papéis de coluna")
            print(f"            {len(m['papeis_divergentes'])} papel(éis) divergente(s) pendente(s) (o papel vem da descrição)")
            for d in m['papeis_divergentes']:
                print(f"              AVISO (mapa): {d['tabela']}.{d['coluna']} declarada como '{d['papel']}' "
                      f"({d['parte']} {d['dono'] or ''}), mas a descrição diz: {d['descricao']!r}")
            for d in m['papeis_resolvidos_pelo_usuario']:
                print(f"              resolvido pelo usuário em {d['confirmado_em']}: {d['tabela']}.{d['coluna']} = "
                      f"'{d['papel']}'" + (' (descrição da origem conhecida como errada)' if d['descricao_errada'] else ''))
        elif m is not None:
            print('  mapa:     camada criada, nenhum mapa compilado (`york.py compilar-mapa`)')
    else:
        print(f"  schema:   modo básico — base não instalada ({sc['db']}); importe com `york.py importar`")
    if fo['instalado']:
        print(f"  fórmulas: {len(fo['pacotes'])} pacote(s), {fo['funcoes']} funções, {fo['contextos']} contextos")
        for p in fo['pacotes']:
            print(f"            {p['id']} ({p['camada']}, {p['funcoes']} funções)")
        print(f"            {len(fo['avisos_de_merge'])} aviso(s) de merge entre camadas")
        for av in fo['avisos_de_merge']:
            print('              AVISO (conhecimento): ' + av)
    else:
        print('  fórmulas: modo básico — nenhum pacote de conhecimento instalado')
    ca = s['cartao']
    if not ca['configurado']:
        print('  cartão:   nenhum Memory Card configurado (`stella.py cartao iniciar --repo DONO/NOME`)')
    elif not ca['disponivel']:
        print(f"  cartão:   {ca['repo']} configurado, mas NÃO funciona aqui: {ca['motivo']}")
    else:
        print(f"  cartão:   {ca['repo']}: {ca['saves']} save(s)"
              + (f", {ca['com_algo_faltando']} com algo faltando no schema" if ca['com_algo_faltando'] else '')
              + f" (cópia local em {ca['pasta']})")
    return 0


# ------------------------------------------------------------------ solucionar
def _texto_solucao(s):
    out = [f"Pedido: {s['pedido']}  | contexto: {s.get('contexto') or '(todos)'}"]
    out += [f'  {m}' for m in s['modo']]
    for e in s['intencoes']:
        out.append(f"\n[{e['id']}] {e['texto']}  ({e['dominio']}"
                   + (f", essencial: {e['essencial']}" if e.get('essencial') else '') + ')')
        if e['status'] == 'lacuna':
            out.append(f"  LACUNA: {e['lacuna']}")
        for i, c in enumerate(e['candidatos'], 1):
            if e['dominio'] == 'formulas':
                out.append(f"  {i}. {c['nome']} [{c['contexto']}/{c['camada']}] {(c['descricao'] or 'sem descrição')[:90]}")
                if c['assinaturas']:
                    out.append(f"     sintaxe: {' | '.join(c['assinaturas'])[:120]}")
                if c.get('prova'):
                    out.append(f"     subiu pelo padrão do pedido: {c['prova']}")
                for lg in c.get('ligacoes_parametros', []):
                    if lg.get('ligado'):
                        out.append(f"     param {lg['posicao']} ligado pelo mapa: cadastro {lg['cadastro']} -> "
                                   f"{lg['tabela']}.{lg['coluna_codigo']}")
            elif e['dominio'] == 'schema':
                out.append(f"  {i}. {c['tabela']}  {(c.get('descricao') or '')[:70]}"
                           + (f"  [prova: {c['prova']} — {c['motivo']}]" if c['prova'] in ('mapa', 'padrao') else ''))
            else:
                out.append(f"  cadastro {c['cadastro']} -> {c['tabela']}.{c['coluna_codigo']} (chave: {', '.join(c['chave'])})")
                if c.get('sql_apoio'):
                    out.append(f"  SQL de apoio (rode no seu banco; o motor não executa): {c['sql_apoio']}")
        out += [f'  aviso: {a}' for a in e['avisos']]
    for p in s.get('padroes', []):
        out.append(f"\nPadrão documentado que cobre as intenções {', '.join(p['intencoes_cobertas'])}: {p['nome']}"
                   + (f" ({p['url']})" if p.get('url') else ''))
        out.append('  ' + (p['formula'] or '').replace('\n', '\n  '))
        if p.get('campos_lidos'):
            out.append(f"  campos lidos: {', '.join(p['campos_lidos'])}; tabelas com todos eles: "
                       f"{', '.join(p['tabelas_com_os_campos'])}")
    f = s.get('formula')
    if f:
        out.append('\nFórmula:')
        if f['valida']:
            out.append('  ' + f['formula'].replace('\n', '\n  '))
            out.append('  PRONTA PARA CADASTRAR' if f['pronta_para_cadastrar'] else
                       '  NÃO está pronta para cadastrar: preencha os argumentos marcados')
        else:
            out.append('  REJEITADA — a fórmula não foi entregue')
        for a in f.get('argumentos_a_preencher', []):
            onde = f" ({a['funcao']}, parâmetro {a['posicao']})" if a.get('funcao') else ''
            lig = (f": código de {a['cadastro']} em {a['tabela']}.{a['coluna_codigo']}; SQL de apoio: {a['sql_apoio']}"
                   if a.get('cadastro') else (f": {a['motivo']}" if a.get('motivo') else ''))
            out.append(f"  preencher <<{a['marcador']}>>{onde}{lig}")
            if a.get('chave_completa'):
                out.append(f"    {a['chave_completa']}")
        out += [f"  ERRO [{x['codigo']}]: {x['mensagem']}" for x in f['erros']]
        out += [f"  aviso [{x['codigo']}]: {x['mensagem']}" for x in f['avisos']]
    q = s.get('sql')
    if q:
        out.append(f"\nSQL ({q.get('origem', '')}):")
        if q.get('sql') and not q['erros']:
            out.append('  ' + q['sql'].replace('\n', '\n  '))
            out.append('  PRONTO PARA RODAR' if q['pronto_para_rodar'] else
                       '  NÃO está pronto para rodar: preencha os argumentos marcados' if q['argumentos_a_preencher']
                       else '  NÃO está pronto para rodar: veja as lacunas')
        elif q['erros']:
            out.append('  REJEITADO — o SQL não foi entregue')
        for j in q.get('joins', []):
            out.append(f"  JOIN {j['de']} -> {j['para']}: provado por {j['origem']}"
                       + (f" ({j['constraint']})" if j.get('constraint') else ''))
        for a in q.get('argumentos_a_preencher', []):
            onde = f" ({a['tabela']}.{a['coluna']})" if a.get('tabela') else ''
            out.append(f"  preencher <<{a['marcador']}>>{onde}"
                       + (f"; SQL de apoio: {a['sql_apoio']}" if a.get('sql_apoio') else ''))
            if a.get('chave_completa'):
                out.append(f"    {a['chave_completa']}")
        out += [f'  LACUNA: {x}' for x in q.get('lacunas', [])]
        out += [f'  ERRO: {x}' for x in q['erros']]
        out += [f'  aviso: {x}' for x in q['avisos']]
    n3 = s.get('nivel_3')
    if s.get('nivel'):
        out.append(f"\nNível da solução: {s['nivel']}"
                   + {1: ' (só funções)', 2: ' (funções com código de cadastro)', 3: ' (fórmula que executa consulta)'}
                   .get(s['nivel'], ''))
    if n3:
        if n3.get('reaproveitar'):
            r = n3['reaproveitar']
            out.append(f"  reaproveitar antes de criar: {r['instrucao']}")
            out.append(f"    SQL de apoio (rode no seu banco; o motor não executa): {r['sql_apoio']}")
        if n3.get('parametros_na_chamada'):
            out.append(f"  {n3['parametros_na_chamada']['nota']}")
        cn = n3.get('consulta_nova')
        if cn:
            out.append('  se nenhuma servir, consulta NOVA (escrita pela descoberta, só JOIN provado):')
            for t in cn.get('tabelas_sem_prova', []):
                out.append(f"  ATENÇÃO: {t['tabela']} ({t['descricao'] or 'sem descrição'}) foi {t['prova']}; "
                           'alternativas: ' + '; '.join(f"{a['tabela']} ({a['descricao'] or 'sem descrição'}; "
                                                        f"{a['prova']})" for a in t['alternativas']))
            if cn.get('motivo_nao_pronta'):
                out.append(f"  {cn['motivo_nao_pronta']}")
            out.append('    ' + cn['sql'].replace('\n', '\n    '))
            m = cn.get('modelo') or {}
            if m.get('valida'):
                out.append('  modelo do laço documentado (NÃO está pronto para cadastrar):')
                out.append('    ' + m['formula'].replace('\n', '\n    '))
            else:
                out += [f"  modelo do laço REJEITADO: {x['mensagem']}" for x in m.get('erros', [])]
            out.append(f"  {cn['instrucao']}")
    out.append('\nLacunas: ' + (', '.join(s['lacunas']) or 'nenhuma'))
    if s.get('candidata'):
        out.append(f"Candidata a confirmação: {s['candidata']}")
        out.append(f"  Pergunte ao usuário se aceita a solução. Só com o aceite explícito dele: "
                   f"stella.py aceitar {s['candidata']}")
    return '\n'.join(out)


def _solucionar(a):
    from dominios import solucao
    from dominios.formulas import conhecimento as kb
    try:
        if a.intencoes:
            with open(a.intencoes, encoding='utf-8') as fh:
                contrato = json.load(fh)
        else:
            contrato = json.loads(a.intencoes_json)
    except (OSError, ValueError) as e:
        print(f'contrato ilegível: {e}', file=sys.stderr)
        return 2
    db = os.path.normpath(a.db or _db_padrao())
    base = kb.carregar(a.raiz_pacotes, somente_publico=a.somente_publico, extras=a.privado)
    cam = solucao.Camadas(base, db)
    try:
        s = solucao.solucionar(contrato, cam, a.pacote, a.uso, a.limite)
    finally:
        cam.fechar()
    if 'erros_contrato' in s:
        print('CONTRATO INVÁLIDO:\n' + '\n'.join(f'  {e}' for e in s['erros_contrato']), file=sys.stderr)
        return 2
    if not a.sem_registro:
        s['candidata'] = solucao.registrar_candidata(s, solucao.caminho_candidatas(db))
        if s['candidata'] is None:
            print('AVISO: a solução não foi registrada como candidata (a pasta da instância não aceita gravação '
                  'nesta cópia); o aceite não fica disponível.', file=sys.stderr)
    print(json.dumps(s, ensure_ascii=False, indent=1)) if a.json else print(_texto_solucao(s))
    if s.get('sql'):
        from dominios import lembretes
        lembretes.lembrar_salvar_no_cartao()
    f = s.get('formula')
    q = s.get('sql')
    return 1 if (f and not f['valida']) or (q and q['erros']) else 0


def _aceitar(a):
    from dominios import aceite
    db = os.path.normpath(a.db or _db_padrao())
    reg, motivo = aceite.aceitar(os.path.dirname(os.path.abspath(db)), a.id, a.observacao)
    if reg is None:
        print(f'NÃO aceita: {motivo}', file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(reg, ensure_ascii=False, indent=1))
        return 0
    print(f"Solução {reg['id']} aceita e guardada como foi entregue (argumentos marcados, nunca valores): "
          f"{aceite.ARQUIVO_ACEITAS} e {aceite.ARQUIVO_CASOS}, na instância.")
    return 0


# ------------------------------------------------------------------ CLI
def _parser():
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument('--json', action='store_true', default=argparse.SUPPRESS, help='saída em JSON')
    ap = argparse.ArgumentParser(description='Stella — entrada única do fluxo do Vegapunk', parents=[comum])
    ap.add_argument('--db', default=None, help='base de schema (padrão: a da instância local)')
    ap.add_argument('--pacotes', dest='raiz_pacotes', help='raiz alternativa dos pacotes de conhecimento de fórmulas')
    ap.add_argument('--privado', action='append', default=[], help='diretório extra de pacote privado de fórmulas')
    ap.add_argument('--somente-publico', action='store_true', help='fórmulas: não carrega a camada privada')
    ap.add_argument('--pacote', help='fórmulas: id do pacote-base (quando houver mais de um dialeto)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    dom = argparse.ArgumentParser(add_help=False)
    dom.add_argument('--dominio', required=True, choices=['schema', 'formulas'])

    p = sub.add_parser('buscar', parents=[comum, dom], help='busca no domínio (tabelas ou funções)')
    p.add_argument('pedido', help='pedido em linguagem natural, em português')
    p.add_argument('--limite', type=int, default=None, help='máximo de resultados (schema: 30; fórmulas: 10)')
    p.add_argument('--contexto', help='fórmulas: família de fórmulas')
    p = sub.add_parser('detalhar', parents=[comum, dom], help='ficha de tabelas (schema) ou funções (fórmulas)')
    p.add_argument('nomes', nargs='+')
    p.add_argument('--contexto', help='fórmulas: família de fórmulas')
    p.add_argument('--completo', action='store_true', help='fórmulas: inclui o texto original da documentação (JSON); schema: o JOIN de toda FK, também com tabelas fora do pedido')
    p = sub.add_parser('confirmar', parents=[comum, dom],
                       help='registra o que foi de fato usado num pedido (feedback para recalibração)')
    p.add_argument('pedido', help='o mesmo pedido em PT-BR usado no `buscar`')
    p.add_argument('item', nargs='+', help='tabelas (schema; a primeira é a principal) ou funções (fórmulas) efetivamente usadas')
    p.add_argument('--contexto', help='fórmulas: família de fórmulas')
    sub.add_parser('checar-modulos', parents=[comum],
                   help='schema: prefixos de tabela sem módulo cadastrado em `sistemas`')

    for nome in ('validar', 'explicar'):
        p = sub.add_parser(nome, parents=[comum], help=f'fórmulas: {nome} uma fórmula')
        p.add_argument('formula', nargs='?')
        p.add_argument('--arquivo')
        p.add_argument('--contexto')
        p.add_argument('--uso', help='rótulo de uso (ex.: selecao) para checar restrições documentadas')
    p = sub.add_parser('compor', parents=[comum], help='fórmulas: compõe e valida a partir de um plano JSON')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--plano', help='arquivo JSON com o plano')
    g.add_argument('--plano-json', help='plano JSON inline')
    p.add_argument('--contexto')
    p.add_argument('--uso')
    p = sub.add_parser('formatar', parents=[comum], help='fórmulas: formata uma fórmula')
    p.add_argument('formula')
    for nome in ('pacotes', 'contextos'):
        sub.add_parser(nome, parents=[comum], help=f'fórmulas: lista {nome}')
    p = sub.add_parser('solucionar', parents=[comum],
                       help='solução por intenções (contrato JSON montado pelo Claude), com lacunas explícitas')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--intencoes', help='arquivo JSON com o contrato de intenções')
    g.add_argument('--intencoes-json', help='contrato de intenções inline')
    p.add_argument('--uso', help='rótulo de uso da fórmula (ex.: selecao)')
    p.add_argument('--limite', type=int, default=5, help='candidatos por intenção (padrão: 5)')
    p.add_argument('--sem-registro', action='store_true', help='não registra a solução como candidata')
    p = sub.add_parser('aceitar', parents=[comum],
                       help='aceita uma solução candidata (só com o aceite explícito do usuário)')
    p.add_argument('id', help='id da candidata (saída do solucionar)')
    p.add_argument('--observacao', help='observação do usuário sobre a solução (texto livre, sem valores do banco)')
    sub.add_parser('status', parents=[comum], help='camadas presentes, versão da base e avisos de merge')
    p = sub.add_parser('instancias', parents=[comum], help='instâncias locais (egghead/ e egghead-<nome>/) e qual está ativa')
    p.add_argument('--pedido', help='ordena as instâncias por quanto cada base cobre o pedido (só leitura, sem log)')
    p = sub.add_parser('cartao', help='Memory Card: os relatórios salvos (iniciar, catalogo, buscar, enviar, '
                                      'marcar, conferir, migrar); o resto da linha vai para satelites/memory_card.py')
    p.add_argument('args', nargs=argparse.REMAINDER)
    return ap


_GERAIS_COM_VALOR = ('--db', '--pacotes', '--privado', '--pacote')


def _posicao_do_comando(argv):
    """Índice do comando (o 1º argumento que não é flag geral), ou None."""
    i = 0
    while i < len(argv):
        if argv[i] in _GERAIS_COM_VALOR:
            i += 2
        elif argv[i].startswith('-'):
            i += 1
        else:
            return i
    return None


def main(argv=None):
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    argv = sys.argv[1:] if argv is None else list(argv)
    from punk_records.instancias import ativar_ou_sair
    argv = ativar_ou_sair(argv)      # antes de qualquer import do motor: vários leem a variável na importação
    ap = _parser()
    i = _posicao_do_comando(argv)
    if i is not None and argv[i] == 'cartao':
        # tudo depois de `cartao` é do Memory Card (inclusive --json, que lá tem outro sentido)
        import memory_card
        if '--db' in argv[:i]:
            os.environ['VEGAPUNK_EGGHEAD_DB'] = argv[argv.index('--db') + 1]
        return memory_card.main(argv[i + 1:])
    a = ap.parse_args(argv)
    a.json = getattr(a, 'json', False)

    if a.cmd == 'status':
        return _status(a)
    if a.cmd == 'instancias':
        return _instancias(a)
    if a.cmd == 'solucionar':
        return _solucionar(a)
    if a.cmd == 'aceitar':
        return _aceitar(a)

    dominio = getattr(a, 'dominio', 'schema' if a.cmd == 'checar-modulos' else 'formulas')
    if dominio == 'schema':
        a.db = a.db or _db_padrao()
        if a.cmd != 'checar-modulos' and getattr(a, 'contexto', None):
            ap.error('--contexto vale só para --dominio formulas')
        from nomi_nomi_no_mi.comandos import executar
        args = argparse.Namespace(comando=a.cmd, db=a.db, json=a.json,
                                  pedido=getattr(a, 'pedido', None),
                                  limite=a.limite if getattr(a, 'limite', None) is not None else 30,
                                  tabelas=getattr(a, 'nomes', None), tabela=getattr(a, 'item', None),
                                  completo=getattr(a, 'completo', False))
        return executar(args) or 0

    import shaka
    if a.cmd == 'detalhar':
        # Integração (fase 3): com a base de schema e a camada Mapa presentes, cada
        # parâmetro de código ganha a ligação com o cadastro e o SQL de apoio.
        # Sem o domínio schema instalado, segue no modo básico (sem ligações).
        try:
            from dominios.integracao import enriquecedor_de_detalhe
            a.enriquecer_detalhe = enriquecedor_de_detalhe(getattr(a, 'db', None) or _db_padrao())
        except ImportError:
            a.enriquecer_detalhe = None
    if a.cmd == 'buscar' and a.limite is None:
        a.limite = 10
    if a.cmd == 'confirmar':
        a.funcao = a.item
    return shaka.executar(a, ap.error)


if __name__ == '__main__':
    sys.exit(main())
