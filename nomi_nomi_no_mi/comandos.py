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

from nomi_nomi_no_mi.busca import NomiNomiNoMi
from nomi_nomi_no_mi.historico import registrar_uso
from nomi_nomi_no_mi.manutencao import checar_cobertura_modulos
from nomi_nomi_no_mi.saida import formatar_busca_texto, formatar_detalhar_texto

def executar(args):
    """`args`: comando ('buscar', 'detalhar', 'confirmar', 'checar-modulos'), db,
    pedido, limite, tabelas, tabela, json — os mesmos nomes da CLI antiga."""
    if args.comando == 'confirmar':
        tabela_confirmada = args.tabela.strip().upper()
        # Achado em auditoria: sem esta checagem, um erro de digitação no
        # nome da tabela entra silenciosamente no histórico e pode poluir
        # uma futura calibração do pythagoras.py sem que ninguém perceba.
        # Não bloqueia (a tabela pode existir no schema real mesmo sem
        # ainda ter sido reimportada para o Punk Records) — só avisa.
        if os.path.exists(args.db):
            conn_check = sqlite3.connect(args.db)
            existe = conn_check.execute(
                "SELECT 1 FROM tabelas WHERE UPPER(tabela) = ?", (tabela_confirmada,)
            ).fetchone() is not None
            conn_check.close()
            if not existe:
                print(
                    f"AVISO: \"{tabela_confirmada}\" não foi encontrada em `tabelas` neste banco "
                    f"({args.db}) — confira se não é erro de digitação. Registrando mesmo assim, "
                    f"pois a tabela pode existir no schema real e ainda não ter sido importada.",
                    file=sys.stderr
                )
        registrar_uso(args.db, {
            'tipo': 'confirmacao',
            'pedido': args.pedido,
            'tabela_confirmada': tabela_confirmada,
        })
        print(f"Registrado: \"{args.pedido}\" -> {tabela_confirmada}")
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
        elif args.comando == 'detalhar':
            resultado = engine.detalhar(args.tabelas)
            if args.json:
                print(json.dumps(resultado, indent=2, ensure_ascii=False))
            else:
                print(formatar_detalhar_texto(resultado))
    finally:
        engine.fechar()

