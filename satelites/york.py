#!/usr/bin/env python3
"""
================================================================================
 YORK — a única porta de escrita da Punk Records
================================================================================
Nome de referência: York é o satélite da "ganância", o que devora tudo.
Aqui ele é o único componente que escreve no conhecimento do Vegapunk:

- schema: `importar` (CSV de introspecção -> punk_records.db), `gravar-sinonimos`
  (pares já revisados por humano) e `migrar` (versão da base, migrações
  numeradas com cópia de segurança);
- linguagem de fórmulas: `ingerir` / `normalizar` / `status` de um pacote de
  documentação. É o ÚNICO componente que acessa a rede. Tudo o que é
  específico de uma fonte (URLs, sementes, regras de relevância e de
  restrição) mora no `fonte.json` do pacote: nova fonte = novo pacote, sem
  mudar código.

    nova fonte -> fonte.json -> york ingerir -> bruto/ + paginas.json
               -> york normalizar -> funcoes.json + documentos.json
               -> shaka (mesmo motor)

Só estrutura entra na base: nomes de tabela e coluna, descrições, tipos e
ligações. Nenhuma linha de conteúdo do sistema de origem.

Uso:
    python3 york.py importar --dir ./meus_csvs/ [--forcar] [--db BANCO]
    python3 york.py gravar-sinonimos --par TERMO_A TERMO_B [--par ...] [--arquivo pares.json] [--db BANCO]
    python3 york.py enriquecer --dir egghead/extracao [--db BANCO]   # estrutura nas linhas existentes
    python3 york.py enriquecer --dicionario egghead/extracao/dicionario   # ligações do dicionário do sistema
    python3 york.py corrigir-direcao --dir egghead/extracao [--db BANCO]   # direção do dicionário x catálogo
    python3 york.py recalcular-metricas [--db BANCO]   # filhas/pais/conexões/score pela fórmula atual
    python3 york.py atualizar --dicionario egghead/extracao/dicionario --catalogo egghead/extracao [--aplicar]
    python3 york.py compilar-mapa --mapa punk_records/pacotes/privado/<pacote>/mapa/mapa.json   # camada Mapa
    python3 york.py migrar status|aplicar [--db BANCO]
    python3 york.py ingerir    --pacote ../punk_records/pacotes/publico/<pacote>
    python3 york.py normalizar --pacote ../punk_records/pacotes/publico/<pacote>   # offline, a partir de bruto/
    python3 york.py status     --pacote ../punk_records/pacotes/publico/<pacote>

`ingerir` é incremental: página cuja versão não mudou não é baixada de novo.
Depois de qualquer escrita, rode `python3 atlas.py verificar` e a suíte de
testes: atualizar a base ou a documentação não pode mudar o comportamento
das consultas sem decisão explícita.

Cada domínio é importado só quando usado: a ingestão de fórmulas roda sem o
motor de schema e vice-versa.
================================================================================
"""

import argparse
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))   # raiz da skill: pacote `punk_records`

# Mesmo padrão do motor de consultas (dominios/schema/config.py, DEFAULT_DB_PATH).
DB_PADRAO = os.path.join(os.environ.get('VEGAPUNK_EGGHEAD') or os.path.join(AQUI, '..', 'egghead'), 'punk_records.db')


def _conector(nome):
    if nome == 'confluence':
        from punk_records.ingestao.confluence import Rastreador
        return Rastreador
    if nome == 'pdf':
        from punk_records.ingestao.pdf import Rastreador
        return Rastreador
    raise SystemExit(f'conector "{nome}" não suportado (disponíveis: confluence, pdf). '
                     f'Para uma fonte nova, implemente um Rastreador em punk_records/ingestao/.')


# ------------------------------------------------------------------ fórmulas
def _pacote(a):
    from punk_records.ingestao.normalizador import normalizar_pacote

    dirp = os.path.abspath(a.pacote)
    fonte_p = os.path.join(dirp, 'fonte.json')
    if not os.path.exists(fonte_p):
        raise SystemExit(f'{fonte_p} não existe')
    fonte = json.load(open(fonte_p, encoding='utf-8'))

    if a.acao == 'ingerir':
        rast = _conector(fonte.get('conector', 'confluence'))(fonte, dirp)
        manifesto = rast.executar()
        with open(os.path.join(dirp, 'paginas.json'), 'w', encoding='utf-8') as f:
            json.dump(manifesto, f, ensure_ascii=False, indent=1)
        print(f'{len(manifesto)} referências no manifesto ({rast.cli.requisicoes} requisições)')
    if a.acao in ('ingerir', 'normalizar'):
        rel = normalizar_pacote(dirp)
        novas = rel.get('novas_na_arvore', [])
        if novas:
            print(f'{len(novas)} página(s) NOVA(S) na árvore das sementes, NÃO ingerida(s): só entram com o seu '
                  'aceite (paginas_aprovadas no fonte.json) — ou exclua (excluir_page_ids):')
            for x in novas:
                print(f"  - {x['ref']}: {x.get('titulo')} (semente {x.get('semente')}, contexto {x.get('contexto')})")
        nao = rel['paginas_nao_processadas']
        if nao:
            print(f'{len(nao)} referência(s) descoberta(s) e NÃO processada(s) — ver relatorio_ingestao.json:')
            for x in nao:
                print(f"  - {x['ref']}: {x.get('status')} — {x.get('motivo')}")
    if a.acao == 'status':
        rel = json.load(open(os.path.join(dirp, 'relatorio_ingestao.json'), encoding='utf-8'))
        for k in ('gerado_em', 'paginas_no_manifesto', 'paginas_por_status', 'funcoes_total',
                  'funcoes_por_contexto', 'funcoes_por_confianca'):
            print(f'{k}: {rel[k]}')
        print(f"duplicidades consolidadas: {len(rel['duplicidades_consolidadas'])}")
        print(f"conflitos entre origens: {len(rel['conflitos_entre_origens'])}")
        print(f"exemplos da documentação que não passam no parser: "
              f"{len(rel['exemplos_documentados_que_nao_passam_no_parser'])}")
    return 0


# ------------------------------------------------------------------ schema
def _importar(args):
    from punk_records.schema import importar_csvs
    from nomi_nomi_no_mi import checar_cobertura_modulos

    if os.path.exists(args.db) and not args.forcar:
        print(
            f"ERRO: {args.db} já existe. Use --forcar para sobrescrever "
            f"(cuidado: isso apaga o conteúdo atual do banco).",
            file=sys.stderr
        )
        return 1
    try:
        contagens = importar_csvs(args.dir, args.db, sobrescrever=True)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERRO ao importar: {e}", file=sys.stderr)
        return 1
    avisos = contagens.pop('avisos', [])
    print(f"Importação concluída em: {args.db}")
    for nome, n in contagens.items():
        print(f"  {nome}: {n}")
    if avisos:
        print(f"\nAvisos ({len(avisos)}) — revise os CSVs de origem, o import NÃO foi bloqueado por isso:")
        for a in avisos:
            print(f"  ! {a}")
    # Item 1 — checa cobertura de módulo automaticamente após todo
    # import, em vez de depender de alguém lembrar de rodar isso à
    # parte (foi assim que o módulo 'Z' passou despercebido antes).
    faltando = checar_cobertura_modulos(args.db)
    if faltando:
        print(f"\nAVISO — {len(faltando)} prefixo(s) de tabela sem módulo cadastrado em `sistemas`:")
        for f in faltando:
            print(f"  Prefixo \"{f['prefixo']}\": {f['tabelas']} tabela(s) — ex.: {', '.join(f['exemplos'])}")
        print("  Rode `checar-modulos` a qualquer momento para ver isso de novo.")
    return 0


def _gravar_sinonimos(args):
    from punk_records.sinonimos import aplicar

    if not os.path.exists(args.db):
        print(f"ERRO: banco não encontrado: {args.db}", file=sys.stderr)
        return 1

    pares = list(args.par)
    if args.arquivo:
        with open(args.arquivo, 'r', encoding='utf-8') as f:
            pares.extend(tuple(p) for p in json.load(f))

    if not pares:
        print("Nenhum par informado (use --par A B, repetível, ou --arquivo).", file=sys.stderr)
        return 1

    from punk_records.migracoes import copiar_seguranca
    copia = copiar_seguranca(args.db)
    try:
        n = aplicar(args.db, pares, uso=args.uso)
    except (ValueError, RuntimeError) as e:
        print(f'ERRO: {e}', file=sys.stderr)
        return 1
    print(f"{n} linha(s) nova(s) inserida(s) em `sinonimos` (bidirecional, uso {args.uso or 'busca'}) a partir de "
          f"{len(pares)} par(es). Cópia de segurança: {copia}")
    return 0


def _recalcular_metricas(args):
    from punk_records.metricas import recalcular

    db = os.path.abspath(args.db)
    if not os.path.exists(db):
        print(f'ERRO: banco não encontrado: {db}', file=sys.stderr)
        return 1
    try:
        r = recalcular(db)
    except Exception as e:  # noqa: BLE001
        print(f'FALHA no recálculo das métricas: {e}. A base foi restaurada da cópia de segurança (se ela chegou a '
              'ser feita).')
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    print(f'Métricas de ranking recalculadas em {db} (ligações intactas; só contam as com as duas pontas na base).')
    print(f"  pesos filhas/conexões/pais: {'/'.join(str(x) for x in r['pesos'])}")
    print(f"  tabelas com métrica alterada: {r['tabelas_com_metrica_alterada']}")
    print(f"  cópia de segurança: {r['copia']}")
    return 0


def _corrigir_direcao(args):
    from punk_records.direcao import corrigir

    db = os.path.abspath(args.db)
    if not os.path.exists(db):
        print(f'ERRO: banco não encontrado: {db}', file=sys.stderr)
        return 1
    try:
        r = corrigir(args.dir, db)
    except Exception as e:  # noqa: BLE001
        print(f'FALHA na correção da direção: {e}. A base foi restaurada da cópia de segurança (se ela chegou a ser '
              'feita).')
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    lg = r['ligacoes']
    print(f'Direção das ligações do dicionário conferida contra o catálogo em {db} (linhas originais intactas).')
    print(f"  invertidas (leitura corrigida troca filha e mãe): {lg.get('invertida', 0)}")
    print(f"  duplicatas inversas de FK física já na base (fora da leitura corrigida): {lg.get('duplicata_inversa', 0)}")
    print(f"  sem prova de inversão (nada muda): {lg.get('sem_prova_de_inversao', 0)}")
    print(f"  métricas de ranking recalculadas: {r['tabelas_com_metrica_alterada']} tabela(s) mudaram")
    print(f"  cópia de segurança: {r['copia']}")
    print('  Rode `atlas.py verificar --classificar` e a avaliação antes de aceitar.')
    return 0


def _atualizar(args):
    from punk_records.atualizacao import aplicar, planejar

    db = os.path.abspath(args.db)
    if not os.path.exists(db):
        print(f'ERRO: banco não encontrado: {db}', file=sys.stderr)
        return 1
    try:
        r = aplicar(db, args.dicionario, args.catalogo) if args.aplicar else planejar(db, args.dicionario, args.catalogo)
    except Exception as e:  # noqa: BLE001
        print(f'FALHA na atualização: {e}. A base foi restaurada da cópia de segurança (se ela chegou a ser feita).')
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    print(('Atualização APLICADA em ' if args.aplicar else 'O que MUDA (nada foi gravado; use --aplicar) em ') + db)
    for x in r['tabelas_novas']:
        print(f"  tabela nova: {x['tabela']} ({x['descricao']}), tem_dados {x['tem_dados']}")
    for x in r['tabelas_descricao']:
        print(f"  descrição de tabela: {x['tabela']}: {x['de']!r} -> {x['para']!r}")
    for x in r['tabelas_tem_dados']:
        print(f"  tem_dados: {x['tabela']}: {x['de']} -> {x['para']}")
    for x in r['colunas_novas']:
        e = x['estrutura']
        print(f"  coluna nova: {x['tabela']}.{x['coluna']} ({x['descricao']})"
              + (f", {e['tipo']}, pk_ordem {e['pk_ordem']}" if e else ', sem estrutura no catálogo'))
    for x in r['colunas_removidas']:
        print(f"  coluna removida: {x['tabela']}.{x['coluna']} ({x['descricao']})")
    for x in r['colunas_removidas_recusadas']:
        print(f"  coluna removida RECUSADA (usada por FK ou mapa): {x['tabela']}.{x['coluna']}")
    for x in r['colunas_descricao']:
        print(f"  descrição de coluna: {x['tabela']}.{x['coluna']}: {x['de']!r} -> {x['para']!r}")
    f = r['fora_da_lista']
    print(f"  fora da lista (não muda): {len(f['tabelas_removidas'])} tabela(s) que o export não traz; "
          f"{len(f['ligacoes_so_no_dicionario'])} ligação(ões) só no dicionário")
    for x in f['ligacoes_so_no_dicionario'][:10]:
        print(f"    {x[0]}.{x[1]} -> {x[2]}.{x[3]}")
    print('  sistemas, ligações, direção, mapa, papéis e sinônimos: não mudam')
    if args.aplicar:
        print(f"  cópia de segurança: {r['copia']}")
        print('  Rode `atlas.py verificar --classificar` e a avaliação antes de aceitar.')
    return 0


def _enriquecer(args):
    from punk_records.enriquecimento import enriquecer

    db = os.path.abspath(args.db)
    if not os.path.exists(db):
        print(f'ERRO: banco não encontrado: {db}', file=sys.stderr)
        return 1
    if not args.dir and not args.dicionario:
        print('ERRO: informe --dir (catálogo), --dicionario (ligações do dicionário) ou os dois.', file=sys.stderr)
        return 1
    try:
        r = enriquecer(args.dir, db, dir_dicionario=args.dicionario)
    except Exception as e:  # noqa: BLE001
        print(f'FALHA no enriquecimento: {e}. A base foi restaurada da cópia de segurança (se ela chegou a ser feita).')
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    print(f'Estrutura gravada em {db} (só UPDATE em linhas existentes; descrições, FKs e métricas intactas).')
    print(f"  texto NULL de exportação convertido em vazio: {r['nulos_convertidos']} campo(s)")
    if 'dicionario' in r:
        d = r['dicionario']
        print(f"  ligações do dicionário: {d['ligacoes_aplicadas']} de {d['ligacoes_no_csv']} aplicadas; "
              f"{d['ligacoes_nao_casadas_inteiras']} não casam inteiras com a base; "
              f"{d['ligacoes_sem_par_na_base']} sem o par (filha, mãe) na base")
        print(f"    linhas de FK com ligação: {d['linhas_com_ligacao']}; sem: {d['linhas_sem_ligacao']}")
        print(f"    pares compostos agrupados pelo dicionário: {d['pares_compostos_agrupados_pelo_dicionario']} "
              f"de {d['pares_compostos']}")
        print(f"    conflitos constraint x dicionário (nenhum vale, aviso no detalhar): "
              f"{d['pares_em_conflito_constraint_x_dicionario']}")
        print(f"    conflitos dicionário x chave da mãe (vence o dicionário): "
              f"{d['pares_em_conflito_dicionario_x_chave_da_mae_vence_dicionario']}")
    if 'colunas' not in r:
        print(f"Cópia de segurança: {r['copia']}")
        return 0
    c, rel = r['colunas'], r['relacionamentos']
    print(f"  colunas: {c['enriquecidas']} de {c['na_base']} da base enriquecidas; "
          f"{c['sem_correspondente_na_base']} do CSV sem correspondente na base")
    print('  Cobertura dos relacionamentos lógicos (dicionário) pelas FKs físicas (catálogo):')
    print(f"    linhas lógicas: {rel['linhas_logicas_com_constraint']} de {rel['linhas_logicas']} com constraint; "
          f"{rel['linhas_logicas_sem_constraint']} sem (ficam com aviso no detalhar, nunca palpite)")
    print(f"    pares filha->mãe: {rel['pares_cobertos_inteiros']} cobertos inteiros, "
          f"{rel['pares_cobertos_em_parte']} em parte, {rel['pares_sem_constraint']} sem constraint "
          f"(de {rel['pares_logicos']})")
    print(f"    pares compostos: {rel['pares_compostos_cobertos_inteiros']} de {rel['pares_compostos']} agrupados; "
          f"ambíguos resolvidos: {rel['pares_ambiguos_resolvidos']} de {rel['pares_ambiguos']}")
    print(f"    FKs físicas: {rel['fks_fisicas_aplicadas']} de {rel['fks_fisicas_no_csv']} aplicadas; "
          f"{rel['fks_fisicas_entre_tabelas_da_base_ausentes_do_dicionario']} entre tabelas da base que não estão "
          f"no dicionário; {rel['fks_fisicas_casadas_so_em_parte_nao_aplicadas']} casadas só em parte (não "
          f"aplicadas); {rel['fks_fisicas_fora_das_tabelas_da_base']} fora das tabelas da base")
    print(f"Cópia de segurança: {r['copia']}")
    return 0


def _compilar_mapa(args):
    from punk_records.mapa import MapaRecusado, compilar

    db = os.path.abspath(args.db)
    if not os.path.exists(db):
        print(f'ERRO: banco não encontrado: {db}', file=sys.stderr)
        return 1
    try:
        r = compilar(args.mapa, db)
    except MapaRecusado as e:
        print(f'MAPA RECUSADO ({len(e.erros)} problema(s)); nada foi gravado:', file=sys.stderr)
        for erro in e.erros:
            print(f'  ! {erro}', file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f'FALHA na compilação do mapa: {e}. A base foi restaurada da cópia de segurança (se ela chegou a ser feita).')
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    print(f'Mapa compilado em {db} (só nomes de tabela, coluna e função; o mapa anterior foi substituído).')
    print(f"  cadastros: {r['mapa_cadastros']}; rótulos de parâmetro: {r['mapa_rotulos']}; funções ligadas: "
          f"{r['mapa_funcoes']}; estruturas: {r['mapa_estruturas']}; papéis de coluna: {r['mapa_papeis']}")
    print(f"  papéis divergentes pendentes (a descrição da coluna não fala do papel declarado): {len(r['divergencias'])}")
    for d in r['divergencias']:
        print(f"    ! {d['tabela']}.{d['coluna']}: declarado como '{d['papel']}' ({d['parte']} {d['dono']}); "
              f"ligação provada por {d['prova']}")
    for d in r['resolvidos_pelo_usuario']:
        print(f"  resolvido pelo usuário em {d['confirmado_em']}: {d['tabela']}.{d['coluna']} = '{d['papel']}' "
              f"({d['fonte_do_papel']})" + ('; descrição da origem registrada como errada' if d['descricao_errada'] else ''))
    print(f"Cópia de segurança: {r['copia']}")
    return 0


def _migrar(args):
    from punk_records import migracoes

    db = os.path.abspath(args.db)
    if not os.path.exists(db):
        print(f'Base não encontrada: {db}')
        return 1

    if args.acao_migrar == 'status':
        s = migracoes.status(db)
        print(f"versão da base: {s['versao']} (alvo: {s['versao_alvo']})")
        for chave, valor in s['aplicadas'].items():
            print(f'  aplicada  {chave}: {valor}')
        for p in s['pendentes']:
            print(f'  pendente  {p}')
        return 0

    try:
        r = migracoes.aplicar(db)
    except Exception as e:  # noqa: BLE001
        print(f'FALHA na migração: {e}. A base foi restaurada da cópia de segurança (se havia migração pendente).')
        return 1
    if not r['aplicadas']:
        print(f"Nada a aplicar: base já na versão {r['antes']}.")
        return 0
    print(f"Base migrada da versão {r['antes']} para {r['depois']}: {', '.join(r['aplicadas'])}")
    print(f"Cópia de segurança: {r['copia']}")
    return 0


def main(argv=None):
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description='York — a única porta de escrita da Punk Records')
    sub = ap.add_subparsers(dest='acao', required=True)

    for nome in ('ingerir', 'normalizar', 'status'):
        p = sub.add_parser(nome, help=f'{nome} um pacote de documentação de fórmulas')
        p.add_argument('--pacote', required=True, help='diretório do pacote (com fonte.json)')

    p = sub.add_parser('importar',
                       help='Importa tabelas/colunas/relacionamentos/sistemas/sinonimos a partir de CSVs e (re)gera o banco')
    p.add_argument('--dir', required=True, help='Diretório com os CSVs (ver referencias/schema.md)')
    p.add_argument('--forcar', action='store_true',
                   help='Sobrescreve --db se já existir (padrão: recusa se o arquivo já existir, para evitar apagar por engano)')
    p.add_argument('--db', default=DB_PADRAO, help='Caminho do banco de schema')

    p = sub.add_parser('gravar-sinonimos', help='grava pares de sinônimo já revisados por humano (nas duas direções)')
    p.add_argument('--par', nargs=2, action='append', default=[], metavar=('TERMO_A', 'TERMO_B'),
                   help='Repetível: --par a b --par c d ...')
    p.add_argument('--arquivo', default=None, help='JSON: lista de pares [termo_a, termo_b]')
    p.add_argument('--uso', choices=['essencial'], default=None,
                   help="'essencial': par só da regra do termo essencial de fórmulas (fora de qualquer busca)")
    p.add_argument('--db', default=DB_PADRAO, help='Caminho do banco de schema')

    p = sub.add_parser('enriquecer',
                       help='grava tipo, nulo, PK e constraint nas linhas que já existem (CSVs de punk_records/extracao/*.sql)')
    p.add_argument('--dir', help='pasta com colunas.csv e relacionamentos.csv do catálogo (ex.: egghead/extracao)')
    p.add_argument('--dicionario', help='pasta com o relacionamentos.csv do dicionário do sistema, uma linha por '
                                        'ligação (ex.: egghead/extracao/dicionario)')
    p.add_argument('--db', default=DB_PADRAO, help='Caminho do banco de schema')
    p.add_argument('--json', action='store_true')

    p = sub.add_parser('atualizar',
                       help='atualiza NO LUGAR descrições, tem_dados, tabela e colunas novas e coluna removida a '
                            'partir de um export novo do dicionário (sem --aplicar: só lista o que muda)')
    p.add_argument('--dicionario', required=True, help='pasta do export do dicionário (tabelas.csv, colunas.csv)')
    p.add_argument('--catalogo', help='pasta do catálogo físico (colunas.csv com tipo e PK das colunas novas)')
    p.add_argument('--aplicar', action='store_true', help='grava (cópia de segurança e transação)')
    p.add_argument('--db', default=DB_PADRAO, help='Caminho do banco de schema')
    p.add_argument('--json', action='store_true')

    p = sub.add_parser('corrigir-direcao',
                       help='marca as ligações do dicionário registradas ao contrário da FK física (catálogo) e '
                            'recalcula as métricas de ranking')
    p.add_argument('--dir', required=True, help='pasta com o relacionamentos.csv do catálogo (ex.: egghead/extracao)')
    p.add_argument('--db', default=DB_PADRAO, help='Caminho do banco de schema')
    p.add_argument('--json', action='store_true')

    p = sub.add_parser('recalcular-metricas',
                       help='recalcula filhas, pais, conexões, score e ranking das tabelas pela fórmula atual '
                            '(cópia de segurança e transação; ligações intactas)')
    p.add_argument('--db', default=DB_PADRAO, help='Caminho do banco de schema')
    p.add_argument('--json', action='store_true')

    p = sub.add_parser('compilar-mapa', help='confere e grava a camada Mapa (mapa.json, contrato v2) na base')
    p.add_argument('--mapa', required=True, help='arquivo mapa.json (o de um sistema real fica no pacote privado)')
    p.add_argument('--db', default=DB_PADRAO, help='Caminho do banco de schema')
    p.add_argument('--json', action='store_true')

    p = sub.add_parser('migrar', help='versão da base e migrações numeradas')
    p.add_argument('acao_migrar', choices=['status', 'aplicar'])
    p.add_argument('--db', default=DB_PADRAO, help='base a migrar (padrão: egghead/punk_records.db)')

    a = ap.parse_args(argv)
    if a.acao in ('ingerir', 'normalizar', 'status'):
        return _pacote(a)
    if a.acao == 'importar':
        return _importar(a)
    if a.acao == 'gravar-sinonimos':
        return _gravar_sinonimos(a)
    if a.acao == 'enriquecer':
        return _enriquecer(a)
    if a.acao == 'compilar-mapa':
        return _compilar_mapa(a)
    if a.acao == 'corrigir-direcao':
        return _corrigir_direcao(a)
    if a.acao == 'recalcular-metricas':
        return _recalcular_metricas(a)
    if a.acao == 'atualizar':
        return _atualizar(a)
    return _migrar(a)


if __name__ == '__main__':
    sys.exit(main())
