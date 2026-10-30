"""
Comandos do domínio schema (buscar, detalhar, confirmar, checar-modulos):
a lógica que antes ficava depois do parse da CLI do motor. A linha de
comando é montada pela Stella (`stella.py ... --dominio schema`).

Parte do Nomi Nomi no Mi, movida sem mudança de algoritmo do antigo
`scripts/nomi_nomi_no_mi.py` (fase 1 da v3).
"""

import json
import os
import sqlite3
import sys

from dominios import lembretes
from nomi_nomi_no_mi.busca import NomiNomiNoMi
from nomi_nomi_no_mi.historico import confirmar, registrar_uso
from nomi_nomi_no_mi.manutencao import checar_cobertura_modulos
from nomi_nomi_no_mi.saida import formatar_busca_texto, formatar_detalhar_texto


def _instancias_com_a_tabela(tabela, db_atual):
    """Nomes das OUTRAS instâncias locais que têm `tabela` (só leitura).
    Serve para avisar uma confirmação feita na instância errada."""
    try:
        from punk_records.instancias import abrir_leitura, listar
    except ImportError:
        return []
    atual = os.path.normcase(os.path.abspath(db_atual))
    achou = []
    for i in listar():
        if not i['existe'] or os.path.normcase(os.path.abspath(i['base'])) == atual:
            continue
        try:
            conn = abrir_leitura(i['base'])
            try:
                if conn.execute('SELECT 1 FROM tabelas WHERE UPPER(tabela) = ?', (tabela,)).fetchone():
                    achou.append(i['nome'])
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            pass
    return achou


def executar(args):
    """`args`: comando ('buscar', 'detalhar', 'confirmar', 'checar-modulos'), db,
    pedido, limite, tabelas, tabela, json — os mesmos nomes da CLI antiga."""
    if args.comando == 'confirmar':
        # uma ou mais tabelas: a primeira é a principal (módulo da calibração);
        # as outras são as do JOIN do relatório
        tabelas = list(dict.fromkeys(t.strip().upper() for t in
                                     (args.tabela if isinstance(args.tabela, list) else [args.tabela])))
        # Achado em auditoria: sem esta checagem, um erro de digitação no
        # nome da tabela entra silenciosamente no histórico e pode poluir
        # uma futura calibração do pythagoras.py sem que ninguém perceba.
        # Não bloqueia (a tabela pode existir no schema real mesmo sem
        # ainda ter sido reimportada para o Punk Records) — só avisa.
        if os.path.exists(args.db):
            conn_check = sqlite3.connect(args.db)
            for tabela_confirmada in tabelas:
                existe = conn_check.execute(
                    "SELECT 1 FROM tabelas WHERE UPPER(tabela) = ?", (tabela_confirmada,)
                ).fetchone() is not None
                if not existe:
                    print(
                        f"AVISO: \"{tabela_confirmada}\" não foi encontrada em `tabelas` neste banco "
                        f"({args.db}) — confira se não é erro de digitação. Registrando mesmo assim, "
                        f"pois a tabela pode existir no schema real e ainda não ter sido importada.",
                        file=sys.stderr
                    )
                    outras = _instancias_com_a_tabela(tabela_confirmada, args.db)
                    if outras:
                        print(f"AVISO: \"{tabela_confirmada}\" existe na instância {', '.join(outras)}: "
                              f"faltou `--instancia {outras[0]}`? (o log é da instância ativa)", file=sys.stderr)
            conn_check.close()
        gravado = confirmar(args.db, args.pedido, tabelas)
        if gravado:
            print(f"Registrado: \"{args.pedido}\" -> {', '.join(tabelas)}")
        else:
            print(f"NÃO registrado (a pasta da instância não aceita gravação nesta cópia): "
                  f"\"{args.pedido}\" -> {', '.join(tabelas)}", file=sys.stderr)
        lembretes.lembrar_salvar_no_cartao()
        return

    if args.comando == 'checar-modulos':
        if not os.path.exists(args.db):
            print(f"ERRO: banco não encontrado em: {args.db}", file=sys.stderr)
            sys.exit(1)
        faltando = checar_cobertura_modulos(args.db)
        if args.json:
            print(json.dumps(faltando, indent=2, ensure_ascii=False))
        elif not faltando:
            print("OK: todos os prefixos de tabela do schema estão cadastrados em `sistemas`.")
        else:
            print(f"{len(faltando)} prefixo(s) SEM módulo cadastrado em `sistemas` "
                  f"(despriorizados na busca, não mais invisíveis, mas sem nome/descrição de módulo):\n")
            for f in faltando:
                print(f"  Prefixo \"{f['prefixo']}\": {f['tabelas']} tabela(s), {f['colunas']} coluna(s) "
                      f"— ex.: {', '.join(f['exemplos'])}")
            print("\nPara cadastrar, insira uma linha em `sistemas` (codigo_sistema, nome_sistema, descricao) "
                  "e reimporte, ou peça pra Claude cadastrar direto no banco.")
        return

    if not os.path.exists(args.db):
        print(
            f"ERRO: banco de dados não encontrado em: {args.db}\n"
            f"Rode `york.py importar --dir <seus_csvs>` primeiro "
            f"(ver referencias/schema.md).",
            file=sys.stderr
        )
        sys.exit(1)

    engine = NomiNomiNoMi(args.db)
    try:
        if args.comando == 'buscar':
            resultado = engine.buscar(args.pedido, limite_criticas=args.limite)
            # Item 1 — loop de feedback: toda chamada real de `buscar`
            # (a que a skill Vegapunk de fato usa) fica registrada,
            # sem exigir nenhuma ação manual. `confirmar` complementa
            # depois com qual tabela foi realmente usada.
            registrar_uso(args.db, {
                'tipo': 'buscar',
                'pedido': resultado['pedido'],
                'termos': resultado['termos'],
                'modulo': resultado['modulo'],
                'ambiguidade': resultado.get('ambiguidade', False),
                'fuzzy_aplicado': resultado.get('fuzzy_aplicado'),
                'top5': [t['tabela'] for t in resultado['criticas'][:5]],
            })
            if args.json:
                print(json.dumps(resultado, indent=2, ensure_ascii=False))
            else:
                print(formatar_busca_texto(resultado))
            lembretes.lembrar_buscar_no_cartao(args.pedido)
        elif args.comando == 'detalhar':
            resultado = engine.detalhar(args.tabelas)
            lembretes.lembrar_confirmar('schema')     # antes da saída: o fim de uma saída longa pode ser cortado
            if args.json:
                print(json.dumps(resultado, indent=2, ensure_ascii=False))
            else:
                print(formatar_detalhar_texto(resultado, getattr(args, 'completo', False)))
    finally:
        engine.fechar()

