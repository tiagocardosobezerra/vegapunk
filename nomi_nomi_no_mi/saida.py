"""
Saída em texto para o terminal (pt-BR).

Parte do Nomi Nomi no Mi, movida sem mudança de algoritmo do antigo
`scripts/nomi_nomi_no_mi.py` (fase 1 da v3).
"""

from typing import Dict

from nomi_nomi_no_mi.texto import formatar_numero_ptbr

# ==============================================================================
# FORMATAÇÃO PARA TERMINAL (saída padrão, legível por humanos/pela skill)
# ==============================================================================

def formatar_busca_texto(r: Dict) -> str:
    linhas = []
    linhas.append(f"Pedido: {r['pedido']}")
    linhas.append(f"Termos considerados: {', '.join(r['termos']) or '(nenhum)'}")
    linhas.append(f"Módulo provável: {r['modulo']} - {r.get('modulo_nome', '')}")
    linhas.append(f"Método: {r['metodo']}")
    linhas.append("")

    if r['criticas']:
        linhas.append(f"TABELAS CRÍTICAS ({len(r['criticas'])}) — prioridade para o SQL:")
        for t in r['criticas']:
            aviso_lastro = "  ⚠ SEM LASTRO ESTRUTURAL (0 conexões e sem dados — penalizada)" if t.get('sem_lastro_estrutural') else ""
            linhas.append(
                f"  • {t['tabela']:<28} score={formatar_numero_ptbr(t['score_dinamico']):>10}  "
                f"colunas_batidas={t['n_colunas_batidas']:<3} "
                f"conexoes={t['conexoes']:<3}"
                f"{aviso_lastro} "
                f"| colunas relevantes: {', '.join(t['colunas_relevantes'])}"
            )
    else:
        linhas.append("Nenhuma tabela crítica encontrada.")

    if r['expandidas']:
        nomes = [t['tabela'] for t in r['expandidas']]
        linhas.append("")
        linhas.append(f"TABELAS RELACIONADAS VIA FK ({len(nomes)}) — candidatas a JOIN:")
        linhas.append("  " + ', '.join(nomes[:40]) + (" ..." if len(nomes) > 40 else ""))

    if r['aviso']:
        linhas.append("")
        linhas.append("Avisos:")
        for a in r['aviso']:
            linhas.append(f"  ! {a}")

    linhas.append("")
    linhas.append(
        "Próximo passo: rode `stella.py detalhar --dominio schema <TABELA1> <TABELA2> ...` "
        "com as tabelas críticas (e as relacionadas que fizerem sentido) para obter "
        "as colunas exatas e os relacionamentos antes de escrever o T-SQL."
    )
    return '\n'.join(linhas)


def _tipo_texto(c: Dict) -> str:
    """'varchar(10)', 'decimal(15,2)', 'int', 'nvarchar(max)', '... NULL' — ou '' se a base não tem o tipo."""
    tipo = c.get('tipo')
    if not tipo:
        return ''
    if tipo in ('varchar', 'nvarchar', 'char', 'nchar', 'varbinary', 'binary'):
        tipo += '(max)' if c.get('tamanho') == -1 else (f"({c['tamanho']})" if c.get('tamanho') else '')
    elif tipo in ('decimal', 'numeric') and c.get('precisao'):
        tipo += f"({c['precisao']},{c.get('escala') or 0})"
    if c.get('nulo') is not None:
        tipo += ' NULL' if c['nulo'] else ' NOT NULL'
    return tipo


def formatar_detalhar_texto(r: Dict) -> str:
    linhas = []
    for tabela, info in r['tabelas'].items():
        m = info['metadados']
        linhas.append(f"### {tabela}")
        linhas.append(
            f"  conexoes_totais={m['conexoes_totais']}  "
            f"tabelas_filhas={m['tabelas_filhas']}  tabelas_pais={m['tabelas_pais']}  "
            f"tem_dados={'sim' if m['tem_dados'] else 'não'}  "
            f"ranking={m['ranking']}"
        )
        if m.get('pk'):
            linhas.append(f"  PK: {', '.join(m['pk'])}")
        linhas.append(f"  Colunas ({info['total_colunas']}):")
        for c in info['colunas']:
            desc = f" — {c['descricao']}" if c['descricao'] else ""
            tipo = _tipo_texto(c)
            linhas.append(f"    - {c['coluna']}{f' [{tipo}]' if tipo else ''}{desc}")

        if info.get('fks'):
            linhas.append(f"  FKs com agrupamento provado e JOIN pronto ({len(info['fks'])}):")
            for fk in info['fks']:
                prova = fk['constraint'] or f"[{fk['origem']}]"
                linhas.append(f"    - {prova} ({fk['tabela_filha']} -> {fk['tabela_mae']}"
                              f"{', composta' if fk['composta'] else ''}): {fk['join']}")
        sem = info.get('fks_sem_constraint', info['relacionamentos'])
        if sem:
            titulo = 'Relacionamentos (FKs)' if not info.get('fks') and len(sem) == len(info['relacionamentos'])                 else 'Ligações sem agrupamento provado'
            linhas.append(f"  {titulo} ({len(sem)}):")
            for rel in sem:
                linhas.append(
                    f"    - {rel['tabela_filha']}({rel['campo_filho']}) -> "
                    f"{rel['tabela_mae']}({rel['campo_mae']})"
                )
        linhas.append("")

    for c in r.get('caminhos', []):
        if c['tabelas'] is None:
            linhas.append(f"Caminho {c['de']} -> {c['para']}: nenhum (ver avisos)")
            continue
        linhas.append(f"Caminho {c['de']} -> {c['para']}: {' -> '.join(c['tabelas'])}")
        if c.get('join'):
            linhas.extend(f"    {l}" for l in c['join'].split('\n'))
        else:
            linhas.append("    (sem JOIN pronto: algum salto não tem constraint conhecida; uma condição ON por campo)")
    if r.get('caminhos'):
        linhas.append("")

    if r['aviso']:
        linhas.append("Avisos:")
        for a in r['aviso']:
            linhas.append(f"  ! {a}")

    return '\n'.join(linhas)
