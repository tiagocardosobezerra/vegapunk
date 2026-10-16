#!/usr/bin/env python3
"""
================================================================================
 LILITH — gerador de casos sintéticos (item 5 do plano de assertividade)
================================================================================
Nome: Lilith é o satélite de Vegapunk ligado ao "futuro" — uma versão
hipotética, não fato consumado. Combina com o que este script faz:
gera casos de teste (pedido -> tabela esperada) A PARTIR das descrições
de negócio que já existem no schema importado (`colunas.descricao`),
sem exigir que ninguém escreva um caso à mão. São casos SIMULADOS, não
pedidos reais de usuário — daí o nome.

IMPORTANTE — honestidade sobre o que isto mede: como o "pedido" é
derivado da própria descrição da tabela, isto testa principalmente se
o caminho de recuperação literal continua funcionando em escala (uma
espécie de smoke test amplo), não generalização para frases que o
usuário nunca usaria. NÃO substitui os casos manuais (casos/consultas_fixture.json), que
foram desenhados por alguém pensando em caso-limite (ambiguidade,
tabela órfã, ordinal por extenso etc.) — serve para AUMENTAR volume de
forma barata, o que é decisivo especificamente para o item 6
(calibração de pesos por módulo, ver pythagoras.py), que com só 30
casos manuais não tem dado suficiente por módulo para calibrar sem
overfitting.

Uso:
    python3 satelites/lilith.py gerar --db egghead/punk_records.db \
        --n-por-tabela 2 --saida egghead/casos_sinteticos.jsonl
"""
import argparse
import json
import os
import random
import sqlite3
import sys

TEMPLATES = [
    "quero saber {desc}",
    "preciso do campo {desc}",
    "consulta sobre {desc}",
    "me mostra {desc}",
    "qual {desc}",
    "buscar informacao de {desc}",
]


def gerar(db_path: str, n_por_tabela: int = 1, seed: int = 42, min_len_desc: int = 12):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT tabela, coluna, descricao FROM colunas "
        "WHERE descricao IS NOT NULL AND LENGTH(descricao) >= ?",
        (min_len_desc,)
    )
    por_tabela = {}
    tabelas_por_descricao = {}  # descricao normalizada -> {tabelas que a usam}
    for row in cur.fetchall():
        por_tabela.setdefault(row['tabela'], []).append(row['descricao'])
        chave = row['descricao'].strip().lower()
        tabelas_por_descricao.setdefault(chave, set()).add(row['tabela'])
    conn.close()

    # Descarta descrições que se repetem, verbatim, em mais de uma
    # tabela: gerar um "pedido" a partir de um texto que não é exclusivo
    # de tabela nenhuma testaria ambiguidade que o schema tem de
    # propósito, não recall/precisão do motor — não é o que este
    # gerador quer medir. Isso também descarta boilerplate genérico
    # (ex.: "código do registro") repetido entre módulos.
    for tabela in list(por_tabela.keys()):
        descs_exclusivas = [
            d for d in por_tabela[tabela]
            if len(tabelas_por_descricao.get(d.strip().lower(), set())) == 1
        ]
        if descs_exclusivas:
            por_tabela[tabela] = descs_exclusivas
        else:
            del por_tabela[tabela]  # tabela sem NENHUMA descrição exclusiva — pula

    rng = random.Random(seed)
    casos = []
    for tabela, descricoes in sorted(por_tabela.items()):
        escolhidas = rng.sample(descricoes, k=min(n_por_tabela, len(descricoes)))
        for desc in escolhidas:
            template = rng.choice(TEMPLATES)
            desc_min = desc.strip().rstrip('.').lower()
            pedido = template.format(desc=desc_min)
            casos.append({
                'pedido': pedido,
                'esperadas': [tabela],
                'top_n': 5,
                'origem': 'sintetico_autogerado',
            })
    return casos


def main():
    ap = argparse.ArgumentParser(description='Lilith — casos sintéticos a partir das descrições do schema')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('gerar', help='gera casos sintéticos (pedido -> tabela esperada)')
    p.add_argument('--db', required=True, help='Caminho do banco (schema real já importado)')
    p.add_argument('--n-por-tabela', type=int, default=1)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--min-len-desc', type=int, default=12,
                   help='Ignora descrições curtas demais para virar um pedido plausível')
    p.add_argument('--saida', default=None, help='Se informado, grava JSONL; senão imprime no stdout')
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"ERRO: banco não encontrado: {args.db}", file=sys.stderr)
        sys.exit(1)

    casos = gerar(args.db, args.n_por_tabela, args.seed, args.min_len_desc)
    linhas = [json.dumps(c, ensure_ascii=False) for c in casos]

    if args.saida:
        with open(args.saida, 'w', encoding='utf-8') as f:
            f.write('\n'.join(linhas) + ('\n' if linhas else ''))
        print(f"{len(casos)} caso(s) sintético(s) gravado(s) em {args.saida}")
    else:
        for l in linhas:
            print(l)


if __name__ == '__main__':
    main()
