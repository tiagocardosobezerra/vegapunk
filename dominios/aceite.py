"""
Aceite e aprendizado (fase 4 da v3, bloco 4f).

No fim do fluxo, a Stella pede o aceite do usuário. Só um comando EXPLÍCITO
(`stella.py aceitar ID`) aceita uma solução, e ela é guardada exatamente como
o motor a entregou: o registro vem da candidata (`solucoes_candidatas.jsonl`,
gravada no `solucionar`), com os argumentos MARCADOS. O comando não recebe a
fórmula nem valores: não há como um código real do usuário entrar.

A solução aceita vira duas coisas, na instância (ao lado da base):
- `solucoes_aceitas.jsonl`: exemplo limpo para o Edison (grafo de
  coocorrência e tipos inferidos leem a fórmula aceita, com as marcas);
- `casos_solucao_aceitos.json`: caso de validação, com o esperado = o que o
  usuário aceitou em cada intenção (numa intenção de fórmulas, a função que a
  fórmula aceita usa, não o 1º lugar da busca). É um conjunto próprio: não
  mistura com o de desenvolvimento nem com o cego, e o `pythagoras avaliar
  --dominio solucoes --db` o mede ao lado dos casos da instância.

Só aceita candidata cuja fórmula (quando houver) foi validada pelo Shaka e
cujo SQL (quando houver: solução só com SQL ou mista) passou na conferência
de nomes, não tem JOIN sem prova nem lacuna, e não tem valor literal: o
filtro fica marcado (<<ARGUMENTO>>), nunca com valor.
"""

import datetime
import json
import os
import re

ARQUIVO_ACEITAS = 'solucoes_aceitas.jsonl'
ARQUIVO_CASOS = 'casos_solucao_aceitos.json'


def _ler_jsonl(caminho):
    if not os.path.exists(caminho):
        return []
    out = []
    with open(caminho, encoding='utf-8') as f:
        for linha in f:
            try:
                out.append(json.loads(linha))
            except json.JSONDecodeError:
                continue
    return out


def aceitas(pasta):
    """Soluções aceitas da instância (mais recente por id)."""
    por_id = {}
    for r in _ler_jsonl(os.path.join(pasta, ARQUIVO_ACEITAS)):
        por_id[r.get('id')] = r
    return list(por_id.values())


def formulas_aceitas(pasta):
    """Textos de fórmula das soluções aceitas (com as marcas), para o Edison."""
    return [r['formula'] for r in aceitas(pasta) if r.get('formula')]


def aceitar(pasta, cid, observacao=None):
    """Aceita a candidata `cid`. Devolve (registro, None) ou (None, motivo)."""
    cands = [r for r in _ler_jsonl(os.path.join(pasta, 'solucoes_candidatas.jsonl')) if r.get('id') == cid]
    if not cands:
        return None, f'candidata {cid} não encontrada em {os.path.join(pasta, "solucoes_candidatas.jsonl")}'
    c = cands[-1]
    if c.get('formula') and not c.get('valida'):
        return None, 'a fórmula desta candidata não passou na validação do Shaka: não pode ser aceita'
    if c.get('sql'):
        if 'sql_erros' not in c:
            return None, 'candidata sem o registro da conferência do SQL: rode o solucionar de novo'
        if c['sql_erros']:
            return None, 'o SQL não passou na conferência de nomes: ' + '; '.join(c['sql_erros'])
        if c['sql_lacunas']:
            return None, 'o SQL tem lacuna (sem JOIN provado): ' + '; '.join(c['sql_lacunas'])
        if c['sql_joins_sem_prova']:
            return None, 'o SQL tem JOIN sem prova: ' + '; '.join(c['sql_joins_sem_prova'])
        if c.get('sql_literais'):
            return None, ('o SQL tem valor literal (' + ', '.join(c['sql_literais'][:5]) + '): o filtro tem de '
                          'estar marcado (<<ARGUMENTO>>), nunca com valor')
    if any(r.get('id') == cid for r in aceitas(pasta)):
        return None, f'candidata {cid} já foi aceita'
    reg = dict(c, tipo='aceita', aceita_em=datetime.datetime.now().isoformat(timespec='seconds'))
    if observacao:
        reg['observacao_do_usuario'] = observacao
    try:
        with open(os.path.join(pasta, ARQUIVO_ACEITAS), 'a', encoding='utf-8') as f:
            f.write(json.dumps(reg, ensure_ascii=False) + '\n')
        _virar_caso(pasta, reg)
    except OSError as e:
        return None, f'não foi possível gravar na instância ({e.strerror}): a pasta não aceita gravação nesta cópia'
    return reg, None


_RE_CHAMADA = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(')


def _esperados(reg):
    """{id da intenção de fórmulas: [funções]}: o esperado é o que a fórmula
    ACEITA usa, não o 1º lugar da busca. Uma intenção cujos candidatos não
    aparecem na fórmula fica com a função da fórmula que nenhuma outra
    intenção explica, se for a única intenção nessa situação; senão None (sem
    rótulo, para não ensinar a resposta errada)."""
    if not reg.get('formula'):
        return {}
    usadas = {f.upper() for f in _RE_CHAMADA.findall(reg['formula'])}
    form = [it for it in reg.get('intencoes') or [] if it.get('dominio') == 'formulas' and it.get('status') != 'lacuna']
    out, sem = {}, []
    for it in form:
        achou = [c for c in it.get('candidatos') or [] if c.upper() in usadas]
        if achou:
            out[it['id']] = achou[:1]
        else:
            sem.append(it)
    explicadas = {f[0].upper() for f in out.values()}
    sobra = sorted(usadas - explicadas)
    for it in sem:
        out[it['id']] = sobra if len(sem) == 1 and sobra else None
    return out


def _virar_caso(pasta, reg):
    arq = os.path.join(pasta, ARQUIVO_CASOS)
    dados = {'_estado': 'Casos de validação vindos das soluções ACEITAS pelo usuário (4f). Conjunto próprio: não '
                        'mistura com o de desenvolvimento nem com o cego.', 'casos': []}
    if os.path.exists(arq):
        with open(arq, encoding='utf-8') as f:
            dados = json.load(f)
    n = len(dados['casos']) + 1
    esperados = _esperados(reg)
    intencoes = []
    for i, it in enumerate(reg.get('intencoes') or [], 1):
        lacuna = it.get('status') == 'lacuna'
        esperado = [] if lacuna else esperados.get(it.get('id'), (it.get('candidatos') or [])[:1])
        if esperado is None:
            continue                  # não dá para saber o que o usuário usou nesta intenção: sem rótulo
        x = {'id': f'A{n:03d}.{i}', 'texto': it['texto'], 'dominio': it['dominio'],
             'esperado': esperado, 'lacuna': lacuna}
        for k in ('essencial', 'funcao', 'posicao', 'capacidade'):
            if it.get(k) is not None:
                x[k] = it[k]
        intencoes.append(x)
    dados['casos'].append({'id': f'A{n:03d}', 'pedido': reg['pedido'], 'contexto': reg.get('contexto'),
                           'fonte': f'solução {reg["id"]} aceita pelo usuário em {reg["aceita_em"]}',
                           'intencoes': intencoes})
    with open(arq, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
