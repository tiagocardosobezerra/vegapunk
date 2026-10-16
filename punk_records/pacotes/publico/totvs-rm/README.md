# Pacote público `totvs-rm` — fórmulas da TOTVS Linha RM

Dicionário de fórmulas gerado pelo York a partir da documentação pública do
TDN (TOTVS Developer Network). Tudo o que é específico deste fornecedor fica
neste diretório; o motor (Shaka) e a documentação da skill são genéricos.

## Origem

| Semente (pageId) | Página | Contexto |
|---|---|---|
| 381051703 | Funções Globais | `GLOBAL` (válidas em qualquer módulo) |
| 452718597 | Fórmulas - FOP | `FOP` — Folha de Pagamento (Labore), herda `GLOBAL` |
| 452719330 | Fórmulas - PTO | `PTO` — Ponto (Chronus), herda `GLOBAL` |

Cobertura (ingestão de 15/10/2026): 58 referências descobertas, 53 páginas
processadas (45 da árvore + 8 por link relevante), 1 fora de escopo, 4 links
irresolvíveis (404, wiki legado e títulos bloqueados pelo anti-bot do TDN — o
conteúdo deles já está coberto por outras páginas). Resultado: 456 funções
(GLOBAL 53, FOP 269, PTO 134), 20 receitas documentadas, 20 duplicidades
consolidadas, 0 conflitos. Detalhe página a página: [MAPA.md](MAPA.md);
números atualizados: `python3 satelites/york.py status --pacote <este diretório>`.

## Particularidades da fonte

* O TDN recusa user-agent que não seja de navegador e bloqueia a busca por
  título da API REST (Cloudflare) — por isso o conector resolve títulos
  citados em links contra títulos já vistos.
* A linguagem (`dialeto.json`) foi montada só com o que aparece em exemplos
  documentados: `SE/ENTAO/SENAO/FIMSE`, `REPITA/ATE`, `DECL`, `SETVAR`
  (variável declarada ou chave texto), comentários `/* */`, `VERDADE/FALSO`,
  operadores lógicos `OR` e `E` (AND/OU/NAO não aparecem em nenhuma fórmula
  documentada), até 50 constantes, sem distinção de maiúsculas.
* Restrição documentada aplicada pelo validador (`--uso selecao`): variáveis
  de movimentação não devem ser usadas em fórmula de seleção.

## Qualidade medida

* Exemplos da própria documentação: 358 passam no parser; 329 (92%) passam
  no validador. Os demais usam nomes sem ficha na documentação (`MES`,
  `VLRVALE`, `TRUNCAVALOR`…) ou omitem a declaração — o validador está certo
  em não aceitá-los.
* Busca (`python3 satelites/pythagoras.py avaliar --dominio formulas`, casos em `casos/busca.json`, top-3):
  calibração 15/16, held-out 12/12, validação cega 11/12.
* 64 fichas com confiança baixa — quase todas variáveis que a documentação
  lista sem linha de sintaxe (`CHAPA`, `D`, `H`): aceitas só com aviso.

## Licença do conteúdo

O texto em `bruto/`, `funcoes.json`, `documentos.json` e `receitas.json` é
derivado da documentação pública da TOTVS, e o texto pertence à TOTVS. Para
redistribuir, distribua só `fonte.json`, `dialeto.json`, este README e
`casos/` (pelo `atlas.py distribuir`), e deixe quem instala regenerar o restante com
`python3 satelites/york.py ingerir --pacote <este diretório>` (o `.gitignore`
do plugin já deixa o resto fora do controle de versão).

## Mapa estrutural

O mapa deste fornecedor (onde moram os cadastros, as fórmulas e as consultas
no banco) cita tabelas de um sistema real: ele é da instância e fica no
pacote privado (`punk_records/pacotes/privado/<id>/mapa/`), nunca aqui.
