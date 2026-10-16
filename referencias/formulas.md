# Motor de fórmulas do Vegapunk (Shaka + York)

> Referência técnica do domínio de **fórmulas**: geração, composição,
> validação e explicação de fórmulas a partir de um dicionário de funções.
> Carregada sob demanda a partir do `SKILL.md`.
>
> Este documento descreve o MOTOR, que é genérico. Tudo o que é específico de
> uma fonte (fornecedor, URLs, contextos, números de cobertura, mapa das
> páginas, licença do texto) fica no `README.md` do próprio pacote, em
> `punk_records/pacotes/publico/<pacote>/`. É a mesma regra do `AVISO.md`:
> nomes de terceiros não se repetem na especificação da skill, e
> `atlas.py isolamento` confere isso automaticamente.

## Sumário

1. [Pilares herdados do domínio schema](#1-pilares-herdados-do-domínio-schema)
2. [Mapa da documentação](#2-mapa-da-documentação)
3. [Modelo do dicionário de fórmulas](#3-modelo-do-dicionário-de-fórmulas)
4. [Arquitetura](#4-arquitetura)
5. [Isolamento público × privado](#5-isolamento-público--privado)
6. [Ingestão e atualização da documentação](#6-ingestão-e-atualização-da-documentação)
7. [Motor de composição](#7-motor-de-composição)
8. [Motor de validação](#8-motor-de-validação)
9. [Testes e regressão](#9-testes-e-regressão)
10. [Uso, limitações e próximos passos](#10-uso-limitações-e-próximos-passos)

---

## 1. Pilares herdados do domínio schema

| Pilar | Schema | Fórmulas |
|---|---|---|
| motor genérico, conhecimento como dado | `punk_records.db` | pacotes JSON + `dialeto.json` |
| nunca inventar nome | "use só o que o motor retornou" | validador rejeita o que o dicionário não sustenta |
| fluxo buscar → detalhar → escrever → confirmar | `stella.py ... --dominio schema` | `stella.py ... --dominio formulas` (mesmos comandos, mesmo `--json`) |
| correção aproximada sinalizada | `fuzzy_aplicado` | `fuzzy_aplicado` (mesmo cutoff 0,82) |
| ambiguidade sinalizada, nunca escolha silenciosa | `ambiguidade` (< 12%) | `ambiguidade` (< 12%, entre nomes distintos) |
| laço de feedback | `confirmar` + `egghead/punk_records_log.jsonl` | `confirmar` + `egghead/shaka_log.jsonl` |
| qualidade por casos rotulados (calibração / held-out / cega) | `pythagoras.py avaliar --dominio schema` | `pythagoras.py avaliar --dominio formulas` |
| constantes não calibradas declaradas como tal | penalidades | `FUZZY_CUTOFF`, `LIMIAR_AMBIGUIDADE` |
| saída pt-BR (`1.234,56`) | sim | sim |
| dado da instalação fora do versionamento | `egghead/` | `egghead/` + camada `punk_records/pacotes/privado/` + `termos_sensiveis.json` |

O domínio de fórmulas não importa nada do domínio schema e vice-versa; cada
um roda sozinho (`atlas.py isolamento` prova isso rodando cada domínio com
o outro bloqueado).

## 2. Mapa da documentação

Cada pacote público traz o seu: `punk_records/pacotes/publico/<pacote>/MAPA.md`
(gerado do manifesto `paginas.json`: página, como foi descoberta, status,
motivo, funções extraídas, lacunas). O `README.md` do pacote resume sementes,
cobertura e números.

## 3. Modelo do dicionário de fórmulas

Um **pacote de conhecimento** (`punk_records/pacotes/<camada>/<id>/`):

| Arquivo | Conteúdo | Gerado por |
|---|---|---|
| `fonte.json` / `pacote.json` | manifesto: id, visibilidade, contextos e herança, sementes, regras de relevância/restrição, `marcas` | humano |
| `dialeto.json` | regras da linguagem, **cada uma com `evidencias`** (citação da página) | humano, a partir da doc |
| `README.md`, `MAPA.md` | o que o pacote cobre, de onde vem, licença, lacunas | humano / gerado |
| `bruto/<pageId>.json` | página original + versão + data + SHA-256 | York |
| `paginas.json` | manifesto de descoberta (status, motivo, via) | York |
| `funcoes.json`, `documentos.json`, `receitas.json` | fichas, textos integrais, programas de exemplo documentados | York |
| `relatorio_ingestao.json` | cobertura, duplicidades, conflitos, lacunas | York |
| `casos/` | `busca.json`, `validacao.json`, `composicao.json`, `integracao.json` — testes DO pacote | humano |
| `mapa/` | `mapa.json`: ligações de estrutura (parâmetro de função → tabela e coluna do schema). Só nomes, nunca conteúdo. O mapa de um sistema real é da instância (pacote privado); num pacote público, só mapa fictício (`"ficticio": true`, tabelas da fixture) | humano, conferido contra o schema |
| `sinonimos.json`, `anotacoes.json`, `termos_sensiveis.json` | enriquecimento (tipicamente privado) | humano |

**Ficha de função** (campos principais; exemplo fictício):

```jsonc
{
  "id": "<pacote>:<CONTEXTO>:ARREDONDE",
  "nome": "ARREDONDE", "contexto": "<CONTEXTO>", "pacote": "<pacote>",
  "categoria": "nao_documentado",           // fonte não categoriza; não inventamos
  "grupo_documentacao": ["<título da página>"],
  "descricao": "...", "descricoes_alternativas": ["..."],   // nada único se perde no merge
  "assinaturas": [{"texto": "ARREDONDE (VALOR, VALOR)", "tem_parenteses": true, "argumentos": ["VALOR","VALOR"]}],
  "aridades_documentadas": [2], "aceita_sem_parenteses": false,
  "aridades_em_exemplos": [],               // aridade vista em exemplo da doc mas ausente da sintaxe (com fonte)
  "parametros": [{"posicao":1,"rotulo_documentado":"VALOR","tipo":"numero",
                  "entre_aspas_na_documentacao":false,"descricao":null,"obrigatorio":"nao_documentado"}],
  "tipo_retorno_documentado": "Valor", "tipo_retorno": "numero",
  "exemplos": [{"codigo":"ARREDONDE(7.778,2)","texto":"...","resultado":"7,78","valido_no_dialeto":true}],
  "observacoes": [{"tipo":"Atenção","texto":"..."}], "restricoes": [...],
  "usos_proibidos": [{"uso":"selecao","evidencia":"...trecho da doc..."}],
  "relacionadas": [{"nome":"OUTRA","evidencia":["usada_em_exemplo"]}],
  "mesmo_nome_em": ["<OUTRO_CONTEXTO>"],
  "nao_documentado": ["tipo_retorno"], "avisos_extracao": [], "confianca_extracao": "alta|media|baixa",
  "origens": [{"page_id":"...","url":"https://...","titulo_pagina":"...","versao_pagina":4,
               "atualizado_em":"...","sha256_bruto":"...","relacao_com_semente":"arvore|link"}],
  "texto_original": ["bloco integral da documentação"]
}
```

Regras: atributo ausente na fonte fica `null`/`"nao_documentado"`; tipo de
parâmetro só é inferido do RÓTULO da sintaxe, pelo vocabulário do dialeto
(senão `desconhecido`); obrigatoriedade só vira `false` com evidência;
`relacionadas` só liga funções que EXISTEM; o texto original fica preservado.

**JSON + índice em memória (e não SQLite):** centenas de fichas cabem em
memória; JSON é revisável em diff a cada reingestão; e sem SQLite fica
verificável que o motor de fórmulas não toca a base Punk Records.

## 4. Arquitetura

```
skills/<skill>/
├── stella.py                      entrada única: despacha para o domínio (--dominio formulas)
├── satelites/
│   ├── shaka.py                   comandos de fórmulas (executar), sem CLI própria
│   ├── york.py                    única porta de escrita; ingestão (único que acessa a rede)
│   ├── pythagoras.py              avaliação da busca (avaliar --dominio formulas)
│   └── atlas.py                   golden de regressão e isolamento
├── dominios/
│   ├── formulas/                  NÚCLEO de fórmulas (pacote independente)
│   │   ├── texto.py               normalização pt-BR
│   │   ├── conhecimento.py        pacotes, camadas, merge, contexto, busca (fuzzy, ambiguidade)
│   │   ├── historico.py           log de uso próprio + confirmações
│   │   ├── sintaxe.py             lexer + parser genéricos guiados por DIALETO
│   │   ├── validador.py           9 etapas de validação
│   │   └── compositor.py          plano -> fórmula, explicação, formatação
│   ├── isolamento.py              checagens estáticas core × público × privado × marcas
│   └── separacao.py               cada domínio roda sem o outro (dinâmica)
├── punk_records/
│   ├── ingestao/                  confluence.py, pdf.py, html_linhas.py, extrator_funcoes.py, normalizador.py
│   └── pacotes/
│       ├── publico/<pacote>/      distribuível: fonte, dialeto, casos/, README, MAPA (mapa/ só fictício)
│       ├── privado/               camada local (.gitignore com "*")
│       └── modelo-privado/        modelo comentado de pacote privado
├── casos/fixtures/formulas/       pacotes FICTÍCIOS dos testes
├── testes/                        unittest
└── egghead/                       instância local: shaka_log.jsonl, golden real (fora do git)
```

**Código compartilhado:** a normalização de texto foi reimplementada em
`dominios/formulas/texto.py` em vez de extraída do motor de schema — compartilhar a
função faria ajuste de tokenização de fórmulas mexer no ranking calibrado
do schema (ver a decisão do núcleo de texto em `referencias/historico.md`).

**Genericidade:** o core não contém nome de função, palavra-chave ou URL de
fornecedor. Os testes do core rodam com dois dialetos fictícios (inglês:
`IF/THEN/ELSE/END`; português: `SE/ENTAO/SENAO/FIMSE`); pacotes reais são
testados pelos próprios `casos/`, por um teste dirigido por dados.

## 5. Isolamento público × privado

| Camada | Onde | Distribuível? | Pode |
|---|---|---|---|
| Core | `dominios/formulas`, `dominios/isolamento.py`, `punk_records/ingestao`, `satelites/shaka.py` | sim | — |
| Público | `punk_records/pacotes/publico/<id>` | só `fonte.json`, `pacote.json`, `dialeto.json`, `*.md`, `casos/` e `mapa/` fictício (o texto do fornecedor fica local; ver licença no README do pacote) | dialeto, funções, receitas, casos |
| Privado | `punk_records/pacotes/privado/<id>`, `VEGAPUNK_FORMULAS_PRIVADO`, `--privado DIR` | **nunca** | funções internas, exemplos, anotações, sinônimos, receitas, herança de contexto, mapa do sistema real |

Merge: o privado **enriquece, nunca substitui** conhecimento documentado —
assinatura privada divergente gera aviso e fica em `variantes_privadas`.
Toda ficha, exemplo e anotação carrega `camada` e origem.

`python3 satelites/atlas.py isolamento` (as checagens 1 a 8 também em teste):
1. core não depende do motor de consultas nem de SQLite (e vice-versa);
2. motor carrega só com o público;
3. visibilidade coerente com a pasta;
4. `privado/.gitignore` com `*`;
5. nenhum termo sensível privado (funções só-privadas + `termos_sensiveis.json`) no core nem nos pacotes públicos;
6. nenhuma `marca` declarada pelos pacotes públicos (`"marcas"` no `fonte.json`) fora do próprio pacote — core, satélites, `SKILL.md`, `AVISO.md`, `COMO-INSTALAR.md`, `referencias/`, `testes/` e `casos/`;
7. nenhum trecho de 12 palavras do texto dos JSON de um pacote privado na superfície distribuível (tudo da skill menos a instância local, o texto do fornecedor e as fixtures). Trecho que também está no texto público não conta;
8. falha fechada: todo pacote privado precisa contribuir com algum termo (item 5) ou trecho (item 7). Um pacote com `"funcoes_sensiveis": false` e sem `termos_sensiveis.json` ainda é verificado pela impressão digital do texto;
9. cada domínio roda sem o outro: testes e comandos de fórmulas com o schema bloqueado e sem base; testes e comandos do schema com fórmulas bloqueadas e sem pacotes (`--rapido` pula esta parte).

A superfície distribuível é definida por regra, não por lista: arquivos `.py`, `.md`, `.json`, `.txt` e `.sql` da skill, menos `egghead/` (só `*.md`), qualquer pasta `privado`, `fixtures`, `bruto` e `backups`, e, dentro de um pacote público, tudo fora da lista permitida acima. O `.gitignore` da raiz do plugin segue a mesma regra.

Nenhuma checagem imprime termo ou trecho privado: a saída diz só o arquivo (e a linha, no item 5) e quantos itens foram verificados.

Para publicar a versão **Vegapunk** (motor sem instância): a skill inteira
menos `egghead/` e o que o `.gitignore` deixa de fora. Quem instala
regenera o texto do fornecedor com `york.py ingerir`.

Modelo de pacote privado: `punk_records/pacotes/modelo-privado/`.

## 6. Ingestão e atualização da documentação

```
fonte.json ─► york ingerir ─► bruto/ + paginas.json ─► york normalizar ─► funcoes/documentos/receitas.json
                                                                          + relatorio_ingestao.json ─► shaka
```

* **Descoberta** (`confluence.py`): semente → descendentes (API REST
  `child/page`, paginada) → links do corpo (`pageId=`, `/display/ESPACO/Título`,
  `<ri:page>`), seguidos até `profundidade_links` se relevantes
  (`padroes_titulo` OU `padroes_conteudo`, `espacos_permitidos`). Títulos
  citados em links são resolvidos primeiro contra títulos já vistos
  (tolerante a travessão/NBSP/caixa). Toda referência vira registro no
  manifesto com status e motivo — é isso que permite verificar que nada
  relevante ficou para trás.
* **Incremental:** página com a mesma `version.number` não é baixada de novo.
* **Extração** (`extrator_funcoes.py`): reconhece padrões de LAYOUT
  ("Função X =", "Função X:", identificador em negrito, assinatura em negrito,
  tabela com título, página dedicada, "NOME(args): essa função retorna…"),
  separa campos por rótulo, junta exemplos de várias linhas usando o parser
  do dialeto, distingue prosa de código, separa "F(A) ou F(A, B)" e trata
  sintaxes com aspas corrompidas na fonte.
* **Normalização** (`normalizador.py`): consolida duplicidades, une
  informação única, registra conflitos, aplica `regras_restricao` da fonte,
  liga relacionadas, mede exemplos que não passam no parser e nomes usados
  em exemplos sem ficha (lacunas da própria documentação).
* **Fonte em arquivo PDF** (`"conector": "pdf"`, `punk_records/ingestao/pdf.py`):
  sem rede; `arquivos` (caminho, contexto, intervalo de páginas),
  `remover_linhas` (cabeçalho/rodapé), `padrao_secao`/`ignorar_secao`
  (segmentação em seções, para um bloco não ser cortado na quebra de
  página) e `normalizar_aspas_tipograficas`. Requer `pdftotext` (poppler).
* **Pacote complementar** (`"estende": "<id do base>"`, tipicamente
  privado): o normalizador gera fichas no namespace do base e usa o
  dialeto dele. No merge, o complemento privado acrescenta funções,
  exemplos e observações; preenche a sintaxe só quando a ficha pública não
  tem nenhuma (`sintaxe_complementada_por`); divergência com sintaxe
  pública documentada vira aviso + `variantes_privadas`. Um pacote privado
  cujos nomes de função não são sigilosos (vindos do próprio fornecedor)
  declara `"funcoes_sensiveis": false`.
* **Nova fonte** = novo diretório com `fonte.json` (+ `dialeto.json`,
  `README.md`, `casos/`). Outra plataforma de wiki = novo conector em
  `punk_records/ingestao/` registrado em `york.py`. O motor não muda.
* **Depois de atualizar:** `python3 -m unittest discover -s testes` e
  `python3 satelites/atlas.py verificar`.

## 7. Motor de composição

1. **Entender e escolher** — `stella.py buscar --dominio formulas "<pedido>" --contexto X`:
   funções ranqueadas (IDF sobre nome/descrição/parâmetros/observações/
   exemplos, sinônimos dos pacotes, cobertura ponderada por IDF, bônus de
   descrição), receitas documentadas, `fuzzy_aplicado` e `ambiguidade`.
   Busca vazia = aviso explícito "não invente". Cada `buscar` é registrado
   no log da instância (`egghead/shaka_log.jsonl`); depois de entregar a fórmula, `confirmar` fecha o laço.
2. **Compor** — determinístico: **plano JSON** (nós `chamar`, `numero`,
   `texto`, `data`, `variavel`, `op`, `grupo`, `negativo`, `se/entao/senao`,
   `declarar`, `atribuir`, `repita/ate`, listas = sequência) vira texto no
   dialeto. Operador ou estrutura não documentada = plano rejeitado.
3. **Validar** — com erro, a fórmula NÃO é entregue (`formula: null`,
   `rascunho_rejeitado` + motivos).
4. **Explicar** — cada componente com descrição, parâmetro documentado de
   cada argumento, retorno e URL de origem; estruturas com a evidência do dialeto.

`formatar` reescreve fórmula válida no estilo canônico (testado: idempotente
e preserva validade em todos os exemplos válidos de cada pacote).

## 8. Motor de validação

| # | Verificação | Severidade |
|---|---|---|
| 1 | léxico/sintaxe (aspas, comentários, parênteses, estruturas do dialeto, separador) com linha/coluna | erro |
| 2 | todo identificador existe (palavra-chave, literal, variável declarada, função do dicionário); senão sugere parecidas | erro (`funcao_inexistente`) |
| 3 | função existe só em outro contexto | erro (`fora_do_contexto`) |
| 4 | forma de chamada com/sem parênteses conforme sintaxe | erro/aviso |
| 5 | aridade ∈ aridades documentadas (opcionais só com evidência); aridade só vista em exemplo da doc | erro / aviso com fonte |
| 6 | tipo de literal × tipo do parâmetro | aviso |
| 7 | usos proibidos documentados (`--uso <rótulo>`) | erro com evidência |
| 8 | limites do dialeto (ex.: máximo de constantes) | erro |
| 9 | ficha de baixa confiança / sintaxe não documentada | aviso "não verificável" |

Operador fora do dialeto gera erro explicando quais operadores lógicos a
documentação usa (`operadores_nao_documentados` no dialeto só melhora a
mensagem; não habilita nada).

## 9. Testes e regressão

`python3 -m unittest discover -s testes` — stdlib, ~12 s:

| Arquivo | Protege |
|---|---|
| `test_consultas_regressao.py` | hash do código do schema; avaliação do schema 31/31; Atlas idêntico (fixture e banco real, se existir); fórmulas não escrevem em banco/log; sem import cruzado |
| `test_formulas_sintaxe.py` | parser com 2 dialetos FICTÍCIOS: estruturas, comentários, aspas, erros com posição |
| `test_formulas_conhecimento.py` | camadas, merge privado, anotações, sinônimos, herança, busca que não inventa, fuzzy, ambiguidade, verificador de isolamento (vazamento de termo e de trecho, .gitignore, pacote fora de lugar, marca fora do pacote, falha fechada) |
| `test_formulas_validador_compositor.py` | regras do validador, composição/rejeição/explicação (fictício) |
| `test_formulas_historico.py` | log próprio, `confirmar`, linha de comando (pela Stella) com `--json` em qualquer posição, saída pt-BR |
| `test_formulas_ingestao.py` | crawler contra wiki falsa, extrator por layout, normalizador |
| `test_formulas_ingestao_pdf.py` | conector PDF (fictício), pacote que estende outro, merge que preenche sintaxe ausente, opt-out `funcoes_sensiveis` |
| `test_pacotes_publicos.py` | dirigido por dados: para cada pacote público com `casos/`, integração, `validacao.json`, `composicao.json`, `formatar`, patamar da busca por grupo |
| `test_migracoes.py` | versão da base e migrações (fixture fictícia) |

Qualidade da busca: `python3 satelites/pythagoras.py avaliar --dominio formulas`
(grupos calibração / held-out / validação cega + `uso_real` vindo das
confirmações). Golden: `python3 satelites/atlas.py verificar` (fixture) e
`--db egghead/punk_records.db` (instância real). Os números de referência
ficam em `egghead/linha_de_base_v3.json` (instância).

## 10. Uso, limitações e próximos passos

```bash
python3 stella.py contextos
python3 stella.py buscar --dominio formulas "arredondar com duas casas" --contexto <CTX>
python3 stella.py detalhar --dominio formulas <FUNCAO> --contexto <CTX>
python3 stella.py compor --plano-json '{"chamar":"<FUNCAO>","args":[{"numero":2}]}' --contexto <CTX>
python3 stella.py validar "<fórmula>" --contexto <CTX> --uso <rótulo>
python3 stella.py explicar "<fórmula>" --contexto <CTX>
python3 stella.py confirmar --dominio formulas "<pedido>" <FUNCAO> --contexto <CTX>
python3 stella.py status
python3 satelites/york.py ingerir --pacote punk_records/pacotes/publico/<pacote>
python3 satelites/york.py compilar-mapa --mapa punk_records/pacotes/privado/<pacote>/mapa/mapa.json
python3 satelites/edison.py sugerir-mapa
python3 satelites/pythagoras.py avaliar --dominio formulas
```

**Limitações do motor** (as do conteúdo de cada fonte estão no README do pacote):

1. Documentação semi-estruturada gera fichas de confiança baixa — o
   validador as aceita só com aviso "não verificável".
2. Campos que a fonte não traz ficam `nao_documentado` (não inferidos).
3. Tipos de expressões não são inferidos (só literais são checados).
4. Precedência entre lógicos e comparação segue a convenção usual
   (comparação antes); se a fonte não define, use parênteses.
5. Busca léxica (IDF), como no motor de consultas; `FUZZY_CUTOFF` e
   `LIMIAR_AMBIGUIDADE` herdados das consultas, ainda não calibrados para
   fórmulas — recalibrar com o Pythagoras quando houver confirmações reais.

**Próximos passos:** acumular confirmações reais (`confirmar`) e virar um
lote novo de validação cega; curar complemento com as lacunas listadas no
MAPA de cada pacote, sempre com a URL da evidência; extrair serviços comuns
quando houver um terceiro motor.

## 11. Mapa (fase 3 da v3)

O mapa diz onde as coisas moram no banco do sistema de origem: em que tabela e
coluna fica o código que cada parâmetro de função recebe, onde ficam as
fórmulas e as consultas cadastradas e quais funções executam e leem
consultas. Só nomes de tabela, coluna e função, nunca conteúdo.

- **Onde vive:** o mapa de um sistema real cita tabelas reais e é da
  instância, no pacote privado (`punk_records/pacotes/privado/<pacote>/mapa/`).
  Só um mapa fictício (`casos/mapa_ficticio.json`) vai para a superfície
  distribuível; o `atlas.py isolamento` recusa qualquer outro.
- **Contrato v2** (`punk_records/mapa.py`): cadastros (com a chave completa),
  fórmulas, consultas (com `ligacao_com_consulta` separada da chave) e
  funções de consulta, todas opcionais. Um rótulo pode trazer a prova
  documental e a fonte (`{rotulo, prova: "documentacao", fonte}`).
- **York `compilar-mapa`:** confere e grava o mapa na base (tabelas `mapa_*`),
  com cópia de segurança e transação. Recusa o arquivo inteiro se aparecer
  campo fora do contrato, valor que pareça conteúdo de registro, tabela ou
  coluna fora do schema, chave sem a PK inteira ou ligação com fórmula sem
  prova (FK ou descrição).
- **Papel pela descrição:** o papel de cada coluna vem da descrição, nunca do
  nome; papel que a descrição não confirma fica `papel_divergente` (aviso no
  `compilar-mapa` e no `stella.py status`) até o usuário resolver: o papel
  confirmado entra em `papeis_confirmados` (prova "usuario", fonte e data) e,
  se a descrição da origem estiver errada, ela fica marcada como conhecida e
  o Edison não a usa como evidência.
- **Edison `sugerir-mapa`:** cruza o rótulo de cada parâmetro de código com o
  mapa compilado e com as descrições das colunas da PK. Só sugere o que a
  documentação ou a estrutura provam; empate e falta de evidência ficam de
  fora. Não grava nada: o usuário aprova e o mapa é recompilado.
- **`detalhar`:** cada parâmetro de código sai ligado (tabela, coluna, chave
  completa e SQL de apoio) ou só rótulo. A ponte é da Stella
  (`dominios/integracao.py`): a descoberta escreve o SQL de apoio
  (`nomi_nomi_no_mi/apoio.py`) e o Shaka valida os nomes
  (`dominios/formulas/sql_apoio.py`). Sem a base de schema ou sem o mapa, o
  `detalhar` sai como antes.
