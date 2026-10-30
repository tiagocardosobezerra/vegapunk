#!/usr/bin/env python3
"""
================================================================================
 PYTHAGORAS — avaliação e calibração dos dois domínios
================================================================================
Nome: Pythagoras é o satélite da Sabedoria, o cálculo. Aqui ele mede a
qualidade da busca nos dois domínios e calibra os pesos da fórmula de score.
Na fase 1 da v3 absorveu as duas suítes que tinham nome próprio: a da
`stella.py` (schema) e a do `egghead.py` (fórmulas). O código foi movido
sem mudança de algoritmo.

Uso:
    python3 satelites/pythagoras.py avaliar --dominio schema [--db BANCO] [--top N] [-v]
        Suíte do schema: integridade (importar -> detalhar/buscar -> JSON) e
        os casos rotulados de `casos/consultas_fixture.json`, por grupo
        (calibração, held-out, validação cega). Sem --db, gera a fixture
        fictícia (`casos/fixture_schema.py`) numa pasta temporária.
        Critério por caso: uma das tabelas esperadas no top-N das críticas.

    python3 satelites/pythagoras.py avaliar --dominio formulas [--grupo G] [--top N] [-v] [--json] [--pacote DIR]
        Qualidade da busca de fórmulas contra os `casos/busca.json` de cada
        pacote público (camada pública só, para o número não depender da
        instalação), mais o grupo `uso_real` (confirmações do log do Shaka,
        só medição). Métricas: acerto@N, acerto@1 e MRR.

    python3 satelites/pythagoras.py avaliar --dominio solucoes [--db BANCO --casos ARQ] [--pacotes DIR] [--json]
        Cobertura de intenções (fase 4) pelo caminho da Stella orquestradora
        (`dominios/cobertura.py`). Sem --db: fixture fictícia temporária (com
        o mapa fictício) e `casos/casos_solucao_ficticios.json`. Com --db: os
        casos da instância (`casos_solucao.json` ao lado do banco, mais os
        casos das soluções aceitas, `casos_solucao_aceitos.json`; ou só --casos).
        Só leitura: rode contra uma CÓPIA da base.

    python3 satelites/pythagoras.py calibrar --dominio schema --db BANCO [--sinteticos JSONL]
            [--min-casos 5] [--max-casos-por-modulo 100] [--saida ARQ]
        Grid search de um par de pesos (estrutura/conceitos) POR MÓDULO,
        usando os casos de calibração + held-out (nunca a validação cega),
        casos sintéticos da Lilith (--sinteticos) e as confirmações reais do
        log ao lado do --db. Só recalibra módulo com --min-casos casos.
        Grava `punk_records_pesos.json` ao lado do --db; o motor carrega
        esse arquivo sozinho.

Grupos por papel metodológico (não misturar ao calibrar):
- calibracao: pode ser usado para ajustar pesos/constantes;
- heldout: também consultado ao escolher os pesos — generalização com ressalva;
- validacao_cega: NUNCA usado para ajustar nada. É o número honesto.
Se um caso de heldout ou validacao_cega for usado para calibrar, ele perde
o valor de medida de generalização: mova-o para calibracao e crie outro.

Cada domínio é importado só quando usado: a avaliação de fórmulas roda sem
o motor de schema, e a de schema roda sem o dicionário de fórmulas.
================================================================================
"""

import argparse
import json
import os
import random
import sqlite3
import sys
import tempfile
from typing import Set

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_SKILL = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, RAIZ_SKILL)

from casos import casos_consultas  # noqa: E402

# Motor de schema e dicionário de fórmulas: importados sob demanda
# (`_carregar_schema` / `_carregar_formulas`), para um domínio rodar sem o outro.
NomiNomiNoMi = PESOS_POR_MODULO = ler_historico_confirmado = importar_csvs = None
historico = kb = formatar_numero_ptbr = None


def _carregar_schema():
    global NomiNomiNoMi, PESOS_POR_MODULO, ler_historico_confirmado, importar_csvs
    from nomi_nomi_no_mi import NomiNomiNoMi, PESOS_POR_MODULO, ler_historico_confirmado
    from punk_records.schema import importar_csvs


def _carregar_formulas():
    global historico, kb, formatar_numero_ptbr
    from dominios.formulas import historico
    from dominios.formulas import conhecimento as kb
    from dominios.formulas.texto import formatar_numero_ptbr


# ==============================================================================
# CALIBRAÇÃO (schema) — antes era o pythagoras.py inteiro
# ==============================================================================

GRID_ESTRUTURA = [round(0.1 * i, 1) for i in range(1, 10)]  # 0.1 .. 0.9


def _tabelas_existentes(db_path: str) -> Set[str]:
    """Lista as tabelas que EXISTEM de fato no --db informado. Usado para
    filtrar os casos manuais fictícios, que só fazem
    sentido quando --db é a própria fixture fictícia (gerada por
    casos.fixture_schema.gerar_fixture_db) — rodando contra um schema real, tabelas
    como 'F_FUNCIONARIO' não existem, e contá-las como caso rotulado
    daria 0% de acerto sempre, contaminando a calibração em silêncio
    (achado revisando esta própria auditoria)."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT tabela FROM tabelas")
    tabelas = {row[0] for row in cur.fetchall()}
    conn.close()
    return tabelas


def _modulo_de(tabelas_esperadas):
    if not tabelas_esperadas:
        return None
    # usa o módulo da primeira tabela esperada (heurística simples,
    # suficiente aqui: casos multi-tabela normalmente são do mesmo módulo)
    return sorted(tabelas_esperadas)[0][0].upper()


def _maiusc(nomes):
    """Nomes de tabela comparáveis sem caixa (o log de uso grava em maiúsculas)."""
    return {n.upper() for n in nomes}


def carregar_casos(db_path: str, caminho_sinteticos: str = None):
    casos_por_modulo = {}
    tabelas_existentes = _tabelas_existentes(db_path)
    casos_fixture_ignorados = 0

    for pedido, esperadas, top_n, _comentario in (casos_consultas()['calibracao'] + casos_consultas()['heldout']):
        # Só usa um caso manual se PELO MENOS UMA das
        # tabelas esperadas existir de fato no --db em uso. Contra a
        # fixture fictícia, isso mantém todos os
        # casos (as tabelas existem lá). Contra um schema real, isso
        # descarta os casos fictícios em vez de contá-los como erro.
        if esperadas and not (_maiusc(esperadas) & _maiusc(tabelas_existentes)):
            casos_fixture_ignorados += 1
            continue
        modulo = _modulo_de(esperadas)
        if modulo:
            casos_por_modulo.setdefault(modulo, []).append((pedido, esperadas, top_n))

    if casos_fixture_ignorados:
        print(f"(info: {casos_fixture_ignorados} caso(s) manual(is) de casos/consultas_fixture.json ignorado(s) — "
              f"tabelas fictícias que não existem em {db_path})")

    if caminho_sinteticos and os.path.exists(caminho_sinteticos):
        with open(caminho_sinteticos, 'r', encoding='utf-8') as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                c = json.loads(linha)
                esperadas = set(c['esperadas'])
                modulo = _modulo_de(esperadas)
                if modulo:
                    casos_por_modulo.setdefault(modulo, []).append((c['pedido'], esperadas, c.get('top_n', 5)))

    for reg in ler_historico_confirmado(db_path):
        # confirmação com várias tabelas (relatório com JOIN, ou salvo no Memory Card): vale qualquer uma no topo
        esperadas = set(reg.get('tabelas_confirmadas') or [reg['tabela_confirmada']])
        modulo = _modulo_de({reg['tabela_confirmada']})       # o módulo é o da tabela principal
        if modulo:
            casos_por_modulo.setdefault(modulo, []).append((reg['pedido'], esperadas, 5))

    return casos_por_modulo


def _taxa_acerto(engine, casos, estrutura):
    from nomi_nomi_no_mi import PESOS_POR_MODULO as _pesos_global  # valor default só p/ módulos fora do grid
    engine._pesos_por_modulo = dict(engine._pesos_por_modulo)
    for k in list(engine._pesos_por_modulo.keys()):
        engine._pesos_por_modulo[k] = {'estrutura': estrutura, 'conceitos': round(1 - estrutura, 2)}
    engine._pesos_por_modulo['DEFAULT'] = {'estrutura': estrutura, 'conceitos': round(1 - estrutura, 2)}

    acertos = 0
    for pedido, esperadas, top_n in casos:
        resultado = engine.buscar(pedido, limite_criticas=30)
        top = [t['tabela'] for t in resultado['criticas'][:top_n]]
        if _maiusc(esperadas) & _maiusc(top):     # log grava em maiúsculas; a base pode ter caixa mista
            acertos += 1
    return acertos / len(casos) if casos else 0.0


def calibrar(db_path: str, caminho_sinteticos: str = None, min_casos: int = 5, max_casos_por_modulo: int = 100):
    """max_casos_por_modulo: acima disso, amostra em vez de usar todos.
    Medido contra o schema real do usuário: usar TODOS os casos
    sintéticos de um módulo grande (~700+ casos) roda o grid inteiro
    (9 pontos) e levava vários minutos — e sem ganho real de decisão,
    porque escolher entre 9 valores discretos de peso não precisa de
    centenas de casos por módulo pra estabilizar. A amostra é
    determinística (seed fixa) para o resultado ser reprodutível entre
    execuções, não uma escolha aleatória a cada vez."""
    casos_por_modulo = carregar_casos(db_path, caminho_sinteticos)
    engine = NomiNomiNoMi(db_path)
    pesos_calibrados = {}
    relatorio = []
    rng = random.Random(42)

    try:
        for modulo, casos in sorted(casos_por_modulo.items()):
            n_total = len(casos)
            if n_total < min_casos:
                relatorio.append((modulo, n_total, None, None, 'DEFAULT (poucos casos)'))
                continue
            casos_usados = casos if n_total <= max_casos_por_modulo else rng.sample(casos, max_casos_por_modulo)
            melhor_estrutura, melhor_taxa = 0.30, -1.0
            for estrutura in GRID_ESTRUTURA:
                taxa = _taxa_acerto(engine, casos_usados, estrutura)
                # empate: prefere ficar mais perto do DEFAULT atual (0.30),
                # em vez de deixar a última combinação testada vencer por acaso
                if taxa > melhor_taxa or (
                    taxa == melhor_taxa and abs(estrutura - 0.30) < abs(melhor_estrutura - 0.30)
                ):
                    melhor_taxa, melhor_estrutura = taxa, estrutura
            pesos_calibrados[modulo] = {'estrutura': melhor_estrutura, 'conceitos': round(1 - melhor_estrutura, 2)}
            status = 'calibrado' if n_total <= max_casos_por_modulo else f'calibrado (amostra de {max_casos_por_modulo}/{n_total})'
            relatorio.append((modulo, n_total, melhor_estrutura, melhor_taxa, status))
    finally:
        engine.fechar()

    return pesos_calibrados, relatorio


# ==============================================================================
# AVALIAÇÃO DO SCHEMA — antes era a suíte da stella.py
# ==============================================================================

def _rodar_integridade(verbose: bool) -> bool:
    """Smoke test do caminho importar -> detalhar/buscar -> JSON — os
    grupos de CALIBRAÇÃO/HELD-OUT/VALIDAÇÃO CEGA não cobrem isso, porque
    chamam `engine.buscar()` direto em memória contra uma fixture que já
    nasce pronta, nunca passando pelo parsing de CSV nem pelo `detalhar`.

    Faz um round-trip real e pequeno: escreve 3 CSVs num diretório
    temporário — com uma FK válida e uma FK com um campo_filho digitado
    errado de propósito — roda `importar_csvs` de verdade e confirma que:
    1) a validação de integridade referencial (ver
       `validar_integridade_relacionamentos` em punk_records/schema.py) pega
       exatamente a FK com o typo, sem travar o import;
    2) `detalhar()` devolve as colunas e as FKs esperadas;
    3) tanto `detalhar()` quanto `buscar()` são serializáveis em JSON
       (o que a flag `--json` da CLI depende)."""
    print("--- INTEGRIDADE (importar / detalhar / --json) ---\n")
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        csv_dir = os.path.join(tmp, 'csvs')
        os.makedirs(csv_dir)
        with open(os.path.join(csv_dir, 'tabelas.csv'), 'w', encoding='utf-8', newline='') as f:
            f.write(
                "tabela,descricao\n"
                "X_PAI,Tabela pai de teste\n"
                "X_FILHA,Tabela filha de teste\n"
            )
        with open(os.path.join(csv_dir, 'colunas.csv'), 'w', encoding='utf-8', newline='') as f:
            f.write(
                "tabela,coluna,descricao\n"
                "X_PAI,CODPAI,Codigo do pai\n"
                "X_FILHA,CODPAI_FK,FK para o pai\n"
                "X_FILHA,CODFILHA,Codigo da filha\n"
            )
        with open(os.path.join(csv_dir, 'relacionamentos.csv'), 'w', encoding='utf-8', newline='') as f:
            f.write(
                "tabela_filha,campo_filho,tabela_mae,campo_mae\n"
                "X_FILHA,CODPAI_FK,X_PAI,CODPAI\n"       # FK válida
                "X_FILHA,CODINEXISTENTE,X_PAI,CODPAI\n"  # FK com typo proposital
            )
        db_path = os.path.join(tmp, 'integridade.db')

        contagens = importar_csvs(csv_dir, db_path, sobrescrever=True)
        avisos = contagens.get('avisos', [])
        if len(avisos) == 1 and 'CODINEXISTENTE' in avisos[0]:
            print("[PASSOU] importar detecta a FK com campo_filho inexistente e avisa (sem travar o import)")
        else:
            ok = False
            print(f"[FALHOU] esperava 1 aviso citando CODINEXISTENTE, obteve: {avisos}")

        engine = NomiNomiNoMi(db_path)
        try:
            det = engine.detalhar(['X_FILHA'])
            colunas_filha = {c['coluna'] for c in det['tabelas']['X_FILHA']['colunas']}
            fks = det['tabelas']['X_FILHA']['relacionamentos']
            if {'CODPAI_FK', 'CODFILHA'} <= colunas_filha and len(fks) == 2:
                print("[PASSOU] detalhar retorna as colunas e as 2 FKs de X_FILHA (inclusive a inválida — "
                      "detalhar não filtra, só expõe; quem decide o que fazer com o aviso é quem chama)")
            else:
                ok = False
                print(f"[FALHOU] detalhar inesperado: colunas={colunas_filha} fks={fks}")

            json.dumps(det, ensure_ascii=False)
            resultado_busca = engine.buscar("codigo da filha", limite_criticas=5)
            json.dumps(resultado_busca, ensure_ascii=False)
            print("[PASSOU] detalhar() e buscar() são serializáveis em JSON (--json não quebra)")
            if verbose:
                print(f"         avisos do import: {avisos}")
        except Exception as e:
            ok = False
            print(f"[FALHOU] erro rodando detalhar/buscar/json: {e!r}")
        finally:
            engine.fechar()

    print(f"\nINTEGRIDADE: {'PASSOU' if ok else 'FALHOU'}\n")
    return ok


def _rodar_grupo(engine, nome_grupo, casos, top_n_override, verbose):
    total = len(casos)
    if total == 0:
        print(f"--- {nome_grupo} (0 casos, grupo vazio — pulando) ---\n")
        return 0, 0, []
    passou = 0
    falhas = []
    print(f"--- {nome_grupo} ({total} casos) ---\n")
    for pedido, esperadas, top_n, comentario in casos:
        n = top_n_override or top_n
        resultado = engine.buscar(pedido, limite_criticas=30)
        tabelas_no_topo = [t['tabela'] for t in resultado['criticas'][:n]] if n else \
            [t['tabela'] for t in resultado['criticas']]

        acertou = (len(resultado['criticas']) == 0) if not esperadas else \
            bool(_maiusc(esperadas) & _maiusc(tabelas_no_topo))
        status = "PASSOU" if acertou else "FALHOU"
        if acertou:
            passou += 1
        else:
            falhas.append((pedido, esperadas, tabelas_no_topo))

        print(f"[{status}] \"{pedido}\"")
        print(f"         esperado (top-{n}): {sorted(esperadas) or '(vazio)'}")
        print(f"         obtido   (top-{n}): {tabelas_no_topo}")
        if verbose:
            print(f"         módulo inferido: {resultado['modulo']}")
            for t in resultado['criticas'][:n or 5]:
                print(f"           - {t['tabela']:<20} score={t['score_dinamico']}")
        print(f"         nota: {comentario}\n")

    print(f"{nome_grupo}: {passou}/{total} ({passou/total*100:.0f}%)\n")
    return passou, total, falhas


def rodar(db_path: str, top_n_override: int = None, verbose: bool = False) -> bool:
    print(f"Rodando suite de testes contra: {db_path}\n")
    print("=" * 70)
    ok_integridade = _rodar_integridade(verbose)
    print("=" * 70)

    casos = casos_consultas()
    # Caso desenhado para a fixture (tabela esperada que não existe nesta base)
    # não se aplica aqui: antes contava como falha e uma base real dava 0/31.
    existentes = _maiusc(_tabelas_existentes(db_path))
    fora = 0
    for g in ('calibracao', 'heldout', 'validacao_cega'):
        aplicaveis = [c for c in casos[g] if not c[1] or _maiusc(c[1]) & existentes]
        fora += len(casos[g]) - len(aplicaveis)
        casos[g] = aplicaveis
    if fora:
        print(f"(info: {fora} caso(s) desenhado(s) para a fixture não se aplicam a esta base — tabelas esperadas "
              f"ausentes; fora da conta)\n")
    engine = NomiNomiNoMi(db_path)
    p1, t1, f1 = _rodar_grupo(engine, "CALIBRAÇÃO", casos['calibracao'], top_n_override, verbose)
    print("=" * 70)
    p2, t2, f2 = _rodar_grupo(engine, "HELD-OUT", casos['heldout'], top_n_override, verbose)
    print("=" * 70)
    p3, t3, f3 = _rodar_grupo(engine, "VALIDAÇÃO CEGA", casos['validacao_cega'], top_n_override, verbose)
    print("=" * 70)
    sintetico = _generalizacao_sintetica(engine, db_path)
    engine.fechar()

    passou_total, total = p1 + p2 + p3, t1 + t2 + t3
    todas_falhas = f1 + f2 + f3

    def _linha(nome, p, t):
        return f"  {nome}: (grupo vazio)" if t == 0 else f"  {nome}: {p}/{t} ({p/t*100:.0f}%)"

    print(f"INTEGRIDADE: {'PASSOU' if ok_integridade else 'FALHOU'}")
    if total:
        print(f"RESULTADO FINAL (grupos de calibração): {passou_total}/{total} ({passou_total/total*100:.0f}%)")
    else:
        print("RESULTADO FINAL (grupos de calibração): nenhum caso definido")
    print(_linha("Calibração", p1, t1))
    print(_linha("Held-out", p2, t2))
    print(_linha("Validação cega", p3, t3) + ("  <- número mais confiável de generalização" if t3 else ""))
    if sintetico:
        n = sintetico['n']
        print(f"  Generalização (sintético, informativo): {n} pedidos tirados das descrições da base: "
              f"1º lugar {sintetico['top1']}/{n} ({sintetico['top1']/n*100:.0f}%), "
              f"top 3 {sintetico['top3']}/{n} ({sintetico['top3']/n*100:.0f}%), "
              f"top 10 {sintetico['top10']}/{n} ({sintetico['top10']/n*100:.0f}%)")
        if total and passou_total == total and sintetico['top1'] / n < 0.6:
            print("  AVISO: 100% nos casos desenhados não é o desempenho geral da busca: veja a linha de "
                  "generalização (casos de outra natureza, não entram no portão).")
    if todas_falhas:
        print("\nCasos que falharam:")
        for pedido, esperadas, obtido in todas_falhas:
            print(f"  - \"{pedido}\" | esperava {sorted(esperadas) or '(vazio)'} | obteve {obtido}")
    print("=" * 70)
    return ok_integridade and passou_total == total


AMOSTRA_SINTETICA = 80


def _generalizacao_sintetica(engine, db_path, n=AMOSTRA_SINTETICA, semente=7):
    """Recall em pedidos que o Lilith tira das descrições da própria base
    (amostra fixa por semente): uma medida de generalização ao lado dos
    casos desenhados, que são poucos e escolhidos. Informativo: não entra no
    resultado (os pedidos sintéticos são frases de descrição, não perguntas
    reais). Só leitura; nada é gravado. None sem casos."""
    try:
        from lilith import gerar
    except ImportError:
        return None
    casos = gerar(db_path)
    if not casos:
        return None
    amostra = random.Random(semente).sample(casos, min(n, len(casos)))
    r = {'n': len(amostra), 'top1': 0, 'top3': 0, 'top10': 0}
    for c in amostra:
        esperadas = _maiusc(c['esperadas'])
        nomes = [t['tabela'].upper() for t in engine.buscar(c['pedido'], limite_criticas=10)['criticas']]
        pos = min((nomes.index(e) + 1 for e in esperadas if e in nomes), default=None)
        if pos:
            r['top10'] += 1
            r['top3'] += pos <= 3
            r['top1'] += pos == 1
    return r


# ==============================================================================
# AVALIAÇÃO DE FÓRMULAS — antes era o egghead.py
# ==============================================================================

GRUPOS_FORMULAS = ('calibracao', 'heldout', 'validacao_cega')
GRUPO_USO_REAL = 'uso_real'
PROFUNDIDADE = 10


def arquivos_de_casos(pacote=None):
    """`casos/busca.json` de um pacote, ou de todos os pacotes públicos que tiverem."""
    if pacote:
        dirs = [pacote]
    else:
        dirs = [p.dir for p in kb.descobrir_pacotes(somente_publico=True)]
    return [c for c in (os.path.join(d, 'casos', 'busca.json') for d in dirs) if os.path.exists(c)]


def carregar_casos_formulas(caminho):
    with open(caminho, encoding='utf-8') as f:
        dados = json.load(f)
    return dados['casos'], dados.get('top_n', 3), dados.get('patamar_minimo', {})


def casos_uso_real(base):
    """Confirmações do log privado cuja função existe no dicionário carregado."""
    out = []
    for r in historico.ler_confirmacoes():
        dentro, _ = base.resolver(r['funcao'], r.get('contexto'))
        if dentro:
            out.append({'pedido': r['pedido'], 'contexto': r.get('contexto'),
                        'esperadas': r.get('funcoes') or [r['funcao']], 'grupo': GRUPO_USO_REAL})
    return out


def avaliar_formulas(base, casos, top_n):
    """Roda cada caso e devolve a lista de resultados (posição 1-based ou None)."""
    out = []
    for c in casos:
        r = base.buscar(c['pedido'], c.get('contexto'), limite=PROFUNDIDADE)
        nomes = [x['nome'] for x in r['resultados']]
        pos = next((i + 1 for i, n in enumerate(nomes) if n in c['esperadas']), None)
        out.append(dict(c, posicao=pos, acerto=pos is not None and pos <= top_n, ranking=nomes))
    return out


def resumir_formulas(resultados, top_n):
    resumo = {}
    for g in GRUPOS_FORMULAS + (GRUPO_USO_REAL, 'total'):
        rs = [r for r in resultados if (g == 'total' and r['grupo'] in GRUPOS_FORMULAS) or r['grupo'] == g]
        if not rs:
            continue
        n = len(rs)
        resumo[g] = {
            'casos': n,
            'acertos': sum(r['acerto'] for r in rs),
            f'acerto@{top_n}': round(sum(r['acerto'] for r in rs) / n, 3),
            'acerto@1': round(sum(r['posicao'] == 1 for r in rs) / n, 3),
            'mrr': round(sum(1 / r['posicao'] for r in rs if r['posicao']) / n, 3),
        }
    return resumo


# ==============================================================================
# CLI
# ==============================================================================

def _avaliar_schema(args):
    _carregar_schema()
    from casos.fixture_schema import gerar_fixture_db
    if args.db:
        if not os.path.exists(args.db):
            print(f"ERRO: banco não encontrado em {args.db}", file=sys.stderr)
            return 1
        ok = rodar(args.db, top_n_override=args.top, verbose=args.verbose)
        return 0 if ok else 1

    with tempfile.TemporaryDirectory() as tmp:
        db_fixture = os.path.join(tmp, 'fixture_aurora.db')
        gerar_fixture_db(db_fixture)
        ok = rodar(db_fixture, top_n_override=args.top, verbose=args.verbose)
    return 0 if ok else 1


def _avaliar_formulas(a):
    _carregar_formulas()
    base = kb.carregar(somente_publico=True)
    casos, top_n = [], 3
    for arq in arquivos_de_casos(a.pacote):
        cs, top_n, _ = carregar_casos_formulas(arq)
        casos += cs
    if not casos:
        print('Nenhum pacote público com casos/busca.json.')
        return 1
    casos += casos_uso_real(base)
    top_n = a.top or top_n
    if a.grupo:
        casos = [c for c in casos if c['grupo'] in a.grupo]
    resultados = avaliar_formulas(base, casos, top_n)
    resumo = resumir_formulas(resultados, top_n)

    if a.json:
        print(json.dumps({'top_n': top_n, 'resumo': resumo,
                          'casos': resultados if a.verbose else None}, ensure_ascii=False, indent=2))
        return 0
    for r in resultados:
        if a.verbose or not r['acerto']:
            marca = 'OK ' if r['acerto'] else 'XX '
            pos = r['posicao'] or '-'
            print(f"{marca}[{r['grupo']}] {r['contexto'] or '-':6} \"{r['pedido']}\" esperado {r['esperadas']} "
                  f"pos={pos} top={r['ranking'][:5]}")
    print()
    for g, m in resumo.items():
        print(f"{g:15} {m['acertos']:2}/{m['casos']:<2}  "
              f"acerto@{top_n}={formatar_numero_ptbr(m[f'acerto@{top_n}'], 3)}  "
              f"acerto@1={formatar_numero_ptbr(m['acerto@1'], 3)}  mrr={formatar_numero_ptbr(m['mrr'], 3)}")
    return 0


def _calibrar(args):
    _carregar_schema()
    if not os.path.exists(args.db):
        print(f"ERRO: banco não encontrado: {args.db}", file=sys.stderr)
        return 1

    pesos, relatorio = calibrar(args.db, args.sinteticos, args.min_casos, args.max_casos_por_modulo)

    print("Módulo | casos | estrutura escolhida | acerto no grid | status")
    for modulo, n, estrutura, taxa, status in relatorio:
        estrutura_fmt = f"{estrutura:.1f}" if estrutura is not None else "-"
        taxa_fmt = f"{taxa*100:.0f}%" if taxa is not None else "-"
        print(f"  {modulo:<6} | {n:<5} | {estrutura_fmt:<20} | {taxa_fmt:<14} | {status}")

    saida = args.saida or os.path.join(os.path.dirname(os.path.abspath(args.db)), 'punk_records_pesos.json')
    if pesos:
        with open(saida, 'w', encoding='utf-8') as f:
            json.dump(pesos, f, indent=2, ensure_ascii=False)
        print(f"\n{len(pesos)} módulo(s) recalibrado(s) e gravado(s) em {saida}")
    else:
        print(f"\nNenhum módulo teve casos suficientes (min {args.min_casos}) — nada foi gravado, "
              f"motor continua no DEFAULT global.")
    return 0


def _avaliar_solucoes(a):
    from dominios import solucao
    from dominios.cobertura import avaliar
    from dominios.formulas import conhecimento as kb_
    raiz = os.path.join(AQUI, '..')
    aceitos_arq = None
    with tempfile.TemporaryDirectory() as tmp:
        if a.db:
            if not os.path.exists(a.db):
                print(f'ERRO: banco não encontrado em {a.db}', file=sys.stderr)
                return 1
            db = a.db
            casos_arq = a.casos or os.path.join(os.path.dirname(os.path.abspath(db)), 'casos_solucao.json')
            if not a.casos:
                # os casos que vieram das soluções aceitas pelo usuário (stella aceitar) entram juntos
                from dominios.aceite import ARQUIVO_CASOS
                aceitos_arq = os.path.join(os.path.dirname(os.path.abspath(db)), ARQUIVO_CASOS)
            base = kb_.carregar(a.pacotes)
        else:
            from casos.fixture_schema import gerar_fixture_db
            from punk_records import migracoes
            from punk_records.mapa import compilar
            db = os.path.join(tmp, 'fixture.db')
            gerar_fixture_db(db)
            migracoes.aplicar(db, destino_backup=os.path.join(tmp, 'bk'))
            compilar(os.path.join(raiz, 'casos', 'mapa_ficticio.json'), db, os.path.join(tmp, 'bk'))
            casos_arq = a.casos or os.path.join(raiz, 'casos', 'casos_solucao_ficticios.json')
            # funções de consulta fictícias (nível 3) num pacote extra: a fixture
            # de fórmulas do Atlas não muda
            extra = [] if a.pacotes else [os.path.join(raiz, 'casos', 'fixtures', 'formulas_consulta',
                                                       'ficticio-consulta')]
            base = kb_.carregar(a.pacotes or os.path.join(raiz, 'casos', 'fixtures', 'formulas'), extras=extra)
        casos = []
        if os.path.exists(casos_arq) or not aceitos_arq:
            with open(casos_arq, encoding='utf-8') as f:
                casos = json.load(f)['casos']
        n_aceitos = 0
        if aceitos_arq and os.path.exists(aceitos_arq):
            with open(aceitos_arq, encoding='utf-8') as f:
                aceitos = [c for c in json.load(f)['casos'] if c.get('intencoes')]
            n_aceitos = len(aceitos)
            casos += aceitos
        if not casos:
            print(f'ERRO: nenhum caso em {casos_arq}' + (f' nem em {aceitos_arq}' if aceitos_arq else ''),
                  file=sys.stderr)
            return 1
        cam = solucao.Camadas(base, db)
        try:
            r = avaliar(casos, solucao.MotorDeCobertura(cam))
        finally:
            cam.fechar()
    if a.json:
        print(json.dumps(r if a.verbose else {k: v for k, v in r.items() if k != 'casos'}, ensure_ascii=False,
                         indent=1))
        return 0
    print(f"cobertura de intenções: {r['cobertura']:.4f} ({len(casos)} casos, {os.path.basename(casos_arq)}"
          + (f" + {n_aceitos} aceito(s) pelo usuário" if n_aceitos else '') + ')')
    for d, x in r['por_dominio'].items():
        print(f"  {d:9} {x['acertos']}/{x['intencoes']}")
    for c in r['casos']:
        for i in c['intencoes']:
            if not i['acertou']:
                print(f"  ERRO {i['id']} ({i['dominio']}): {str(i['resposta'])[:100]}")
    return 0


def main(argv=None):
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description='Pythagoras — avaliação e calibração dos dois domínios')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('avaliar', help='mede a qualidade da busca de um domínio')
    p.add_argument('--dominio', required=True, choices=['schema', 'formulas', 'solucoes'])
    p.add_argument('--top', type=int, default=None, help='sobrescreve o top-N de todos os casos')
    p.add_argument('-v', '--verbose', action='store_true', help='mostra o ranking de cada caso')
    p.add_argument('--db', default=None,
                   help='schema: banco já importado a testar; omitido = fixture fictícia temporária')
    p.add_argument('--grupo', action='append', choices=GRUPOS_FORMULAS + (GRUPO_USO_REAL,),
                   help='fórmulas: restringe a um ou mais grupos')
    p.add_argument('--json', action='store_true', help='fórmulas: saída em JSON')
    p.add_argument('--pacote', help='fórmulas: diretório de um pacote público (padrão: todos com casos/busca.json)')
    p.add_argument('--casos', help='soluções: arquivo de casos de solução')
    p.add_argument('--pacotes', help='soluções: raiz dos pacotes de conhecimento')

    p = sub.add_parser('calibrar', help='grid search de pesos por módulo')
    p.add_argument('--dominio', required=True, choices=['schema'])
    p.add_argument('--db', required=True)
    p.add_argument('--sinteticos', default=None, help='JSONL gerado por lilith.py')
    p.add_argument('--min-casos', type=int, default=5)
    p.add_argument('--max-casos-por-modulo', type=int, default=100,
                   help='Acima disso, amostra (determinística) em vez de rodar o grid inteiro contra todos os casos')
    p.add_argument('--saida', default=None, help='Padrão: punk_records_pesos.json ao lado do --db')

    a = ap.parse_args(argv)
    if a.cmd == 'calibrar':
        return _calibrar(a)
    if a.dominio == 'solucoes':
        return _avaliar_solucoes(a)
    if a.dominio == 'schema':
        if a.grupo or a.json or a.pacote:
            ap.error('--grupo, --json e --pacote valem só para --dominio formulas')
        return _avaliar_schema(a)
    if a.db:
        ap.error('--db vale só para --dominio schema')
    return _avaliar_formulas(a)


if __name__ == '__main__':
    sys.exit(main())
