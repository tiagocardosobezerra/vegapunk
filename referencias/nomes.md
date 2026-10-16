# Estrutura da skill e nomes por papel

Carregado sob demanda pelo `SKILL.md`. **Regra: um nome por papel, nunca por
domínio.** Cada personagem tem um papel único que vale para schema e
fórmulas. Um domínio novo (relatórios, integrações) entra como `--dominio`,
sem ganhar nome próprio. Lugares e objetos nomeiam estrutura; satélites
nomeiam ação.

## Estrutura

```
<skill>/
├── SKILL.md                  roteador curto
├── stella.py                 entrada única do fluxo
├── satelites/                york, edison, shaka, pythagoras, lilith, atlas
├── nomi_nomi_no_mi/          núcleo do schema: texto, índice, busca, grafo, saída, manutenção, histórico
├── dominios/
│   ├── schema/               configuração e regras do domínio SQL
│   ├── formulas/             sintaxe, validador, compositor, dicionário (genéricos)
│   ├── isolamento.py         checagens estáticas entre camadas e domínios
│   └── separacao.py          cada domínio roda sem o outro
├── punk_records/
│   ├── schema.py, sinonimos.py, migracoes.py   escrita na base (só pelo York)
│   ├── ingestao/             conectores de documentação (só pelo York)
│   └── pacotes/              pacotes de conhecimento: publico/, privado/, modelo-privado/
├── casos/                    só públicos e fictícios: casos do schema, fixtures, goldens fictícios
├── referencias/              T-SQL, schema, fórmulas, fluxos, nomes, histórico
├── testes/                   unittest, linha de base, hash do código do schema
└── egghead/                  instância local, fora do controle de versão
```

## Papéis

| Nome | Papel | Onde |
|---|---|---|
| **Vegapunk** | a skill inteira: o motor genérico, igual em toda instalação | a pasta da skill |
| **Egghead** | a instância local: base estrutural preenchida, logs, confirmações, goldens reais, cópias de segurança | `egghead/` |
| **Punk Records** | a base única: schema (hoje), linguagem e mapa (fases seguintes) | `egghead/punk_records.db` + `punk_records/` |
| **Nomi Nomi no Mi** | o núcleo de busca | `nomi_nomi_no_mi/` |
| **Stella** | a entrada única: recebe o pedido e despacha para o domínio | `stella.py` |
| **York** | a única porta de escrita: importar schema, gravar sinônimos aprovados, migrar, ingerir documentação | `satelites/york.py` |
| **Edison** | o analisador: sugere conhecimento novo a partir de fontes limpas (hoje, sinônimos) | `satelites/edison.py` |
| **Shaka** | compor, validar e explicar fórmulas | `satelites/shaka.py` |
| **Pythagoras** | avaliação e calibração dos dois domínios | `satelites/pythagoras.py` |
| **Lilith** | casos sintéticos, nunca casos de validação | `satelites/lilith.py` |
| **Atlas** | golden de regressão e isolamento: o portão de cada fase | `satelites/atlas.py` |

## Comandos de manutenção (satélites)

```bash
python3 satelites/york.py importar --dir ./meus_csvs/ [--forcar]
python3 satelites/york.py gravar-sinonimos --par TERMO_A TERMO_B
python3 satelites/york.py migrar status|aplicar
python3 satelites/york.py ingerir|normalizar|status --pacote punk_records/pacotes/publico/<pacote>
python3 satelites/edison.py sugerir-sinonimos
python3 satelites/pythagoras.py avaliar --dominio schema|formulas
python3 satelites/pythagoras.py calibrar --dominio schema --db egghead/punk_records.db
python3 satelites/lilith.py gerar --db egghead/punk_records.db --saida egghead/casos_sinteticos.jsonl
python3 satelites/atlas.py verificar [--db egghead/punk_records.db] [--dominio schema|formulas]
python3 satelites/atlas.py isolamento [--rapido]
```

Ao criar um script novo, escolha o nome pelo papel (traço do personagem ↔
natureza da ação), nunca pelo domínio.
