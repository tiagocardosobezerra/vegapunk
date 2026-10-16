# Fluxo de fórmulas (passo a passo)

Carregado sob demanda pelo `SKILL.md`. Vale sempre antes de entregar uma
fórmula. Comandos rodados da pasta da skill.

O conhecimento vem de pacotes em `punk_records/pacotes/` (camada `publico/`,
distribuível, mais a camada `privado/` opcional desta instalação).
Arquitetura, modelo do dicionário e limitações: [formulas.md](formulas.md).

**Regra de ouro: só use função, sintaxe e operador que o dicionário
retornar.** Se `buscar` não achar suporte, diga ao usuário que não há
suporte documentado. Nunca entregue uma fórmula "parecida com válida".

## Passo 1 — Identificar o contexto e buscar

Contexto = família de fórmulas (`python3 stella.py contextos`; ex.: um
módulo específico, que herda as funções globais). Se o pedido não deixar
claro o contexto, pergunte.

```bash
python3 stella.py buscar --dominio formulas "<necessidade do usuário, em português>" --contexto <CTX>
```

Retorna funções ranqueadas (sintaxe, contexto, camada pública/privada,
confiança da extração e usos proibidos) e receitas documentadas parecidas.
Como no schema: `fuzzy_aplicado` (termo corrigido por aproximação —
confira) e `ambiguidade` (1º e 2º colocados próximos demais — pergunte
antes de compor). `--json` em qualquer comando dá saída parseável.

## Passo 2 — Detalhar as funções escolhidas

```bash
python3 stella.py detalhar --dominio formulas FUNCAO1 FUNCAO2 --contexto <CTX>
```

Ficha completa: assinaturas, parâmetros documentados, retorno, exemplos,
observações, restrições e URL de origem. O campo `nao_documentado` diz o
que a documentação não traz — não preencha de memória.

**Parâmetro que recebe um código de cadastro** (com a base de schema e o
mapa compilados): a ficha traz `ligacoes_parametros`. Para cada parâmetro de
código, `ligado` diz se o mapa prova a que cadastro ele aponta:

- **Ligado:** tabela, coluna do código e a `chave` completa do cadastro, e
  um `sql_apoio` (validado quanto a nomes) para o USUÁRIO rodar no banco
  dele e achar o código certo. Entregue esse SQL junto com a fórmula. Se a
  chave tem mais de uma coluna, o código só é único junto com as outras
  (`chave_completa`): diga isso ao usuário. O motor nunca executa o SQL nem
  vê o resultado: nunca invente o código.
- **Só rótulo:** o mapa não prova a ligação. Deixe o argumento marcado (o
  rótulo da documentação) e pergunte ao usuário qual código usar.

Um papel de coluna divergente no mapa (declarado num papel que a descrição
da coluna não confirma) aparece no `stella.py status`; quando a resposta
usar essa coluna, confirme o papel com o usuário.

## Passo 3 — Compor (plano) e validar

Monte um plano JSON (formato em [formulas.md](formulas.md), seção 7) usando
só o que veio dos passos 1–2:

```bash
python3 stella.py compor --plano-json '<plano>' --contexto <CTX> [--uso selecao]
```

O compositor gera a fórmula na sintaxe do dialeto e a VALIDA; com erro, não
entrega a fórmula. Para fórmula escrita à mão ou trazida pelo usuário:

```bash
python3 stella.py validar "<fórmula>" --contexto <CTX> [--uso <uso>]
```

Erros (`funcao_inexistente`, `fora_do_contexto`, `aridade`, `uso_proibido`,
`sintaxe`...) bloqueiam a entrega. Avisos (`sintaxe_nao_documentada`,
`baixa_confianca`, `aridade_so_em_exemplo`, `tipo_argumento`) devem ser
repassados ao usuário com a URL de origem.

## Passo 4 — Explicar

```bash
python3 stella.py explicar "<fórmula>" --contexto <CTX>
```

Use a saída (componentes, parâmetros, retorno e fontes) para explicar a
composição quando o usuário pedir ou quando houver aviso.

## Passo 5 — Confirmar a função usada (sempre, não é opcional)

```bash
python3 stella.py confirmar --dominio formulas "<pedido original do usuário>" FUNCAO_PRINCIPAL --contexto <CTX>
```

Grava em `egghead/shaka_log.jsonl` (instância local, nunca no log do
schema). Se o `buscar` sinalizou `ambiguidade` ou `fuzzy_aplicado`, ou se a
função usada não foi a 1ª colocada, a confirmação vale ainda mais. Quando
as confirmações crescerem (ordem de +20–30), avise o usuário que dá para
medir com `python3 satelites/pythagoras.py avaliar --dominio formulas`
(grupo `uso_real`) e, com massa suficiente, criar um lote novo de validação
cega.

## Manutenção

- **Atualizar a documentação:** `python3 satelites/york.py ingerir --pacote
  punk_records/pacotes/publico/<id>` e depois
  `python3 -m unittest discover -s testes`.
- **Conhecimento específico da instalação:** em `punk_records/pacotes/privado/`
  (modelo em `punk_records/pacotes/modelo-privado/`). Confira com
  `python3 satelites/atlas.py isolamento`.
- **Avisos de merge entre camadas** (aridade privada divergente etc.):
  `python3 stella.py status`.
