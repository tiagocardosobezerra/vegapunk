# Changelog — motor Nomi Nomi no Mi / skill Vegapunk

> Histórico de versões extraído do `SKILL.md` (antes vivia dentro das
> instruções operacionais, lidas a cada invocação da skill — movido para
> cá para reduzir o que é carregado por invocação e evitar que fatos
> versionados fiquem desatualizados no resumo operacional). Ver
> `SKILL.md`, seção "Recursos e manutenção contínua", para o estado
> ATUAL (o que importa no dia a dia); este arquivo é só histórico/porquê.
>
> As seções anteriores à fase 1 da v3 citam os caminhos e nomes da época
> (`scripts/`, `contextos/`, `egghead.py`, `nomi_nomi_no_mi.py` e outros).
> Não foram reescritas: valem como registro. O mapa entre os nomes antigos e
> os atuais está em [nomes.md](nomes.md).

## Melhorias de assertividade (v1.1)

O motor ganhou 4 recursos automáticos, que não exigem nenhum trabalho manual de CSV/sinônimo para começar a funcionar:

- **Correção aproximada (fuzzy):** se um termo do pedido não bate literalmente em nada do vocabulário do schema (nem por sinônimo, nem por radical), o motor tenta uma correção por distância de edição contra o vocabulário real antes de desistir. Aparece em `resultado['fuzzy_aplicado']` e como aviso — sempre confira antes de confiar.
- **Sinalização de ambiguidade:** quando o 1º e o 2º colocado da busca crítica ficam com score muito próximo (`resultado['ambiguidade'] == True`, `margem_top1_top2`), o motor avisa em vez de escolher em silêncio — pare e confirme com o usuário qual sentido é o pretendido antes de escrever o SQL.
- **Log de uso + `confirmar`:** toda chamada de `buscar` grava uma linha em `contextos/punk_records_log.jsonl` (ao lado do `--db` em uso). Depois de escrever o SQL final, rode `python3 scripts/nomi_nomi_no_mi.py confirmar "<pedido>" <TABELA_USADA>` para registrar qual foi a tabela certa — isso vira dado real para recalibração (ver abaixo), sem que ninguém precise escrever um caso de teste à mão.
- **`sugerir-sinonimos`:** `python3 scripts/nomi_nomi_no_mi.py sugerir-sinonimos` minera candidatos a par sinônimo comparando os tokens já indexados, descartando automaticamente o padrão sistemático particípio×agente (`aprovado`/`aprovador`, `avaliado`/`avaliador` etc. — sentidos diferentes, não sinônimos). Não aplica nada sozinho — só lista candidatos pra revisão antes de colocar em `sinonimos.csv` (ou usar `edison.py`, abaixo). Performance: a comparação par-a-par usa uma poda por janela de tamanho (cota superior matemática do próprio `SequenceMatcher.ratio()`, não uma aproximação) — medida contra o schema real do usuário, isso deu 4x de ganho (28s → 6,7s num teste com ~2.100 tabelas) sem perder nenhum candidato (conjunto de resultado idêntico, verificado bit a bit).

Dois scripts complementares (rodar sob demanda, não fazem parte do fluxo de busca em si):

- **`scripts/lilith.py --db <db> --saida <arquivo.jsonl>`** — gera casos de teste (pedido → tabela esperada) a partir das descrições de negócio já existentes no schema importado, descartando descrições que se repetem em mais de uma tabela (não é sobre generalização de linguagem, é smoke test em escala e insumo para a calibração por módulo abaixo).
- **`scripts/pythagoras.py --db <db> [--sinteticos <arquivo.jsonl>]`** — grid-search de pesos (estrutura/conceitos) por módulo, usando os casos manuais do `stella.py` + sintéticos + confirmações reais (`punk_records_log.jsonl`). Só recalibra um módulo com casos suficientes (padrão: 5+); grava em `contextos/punk_records_pesos.json`, que o motor já carrega sozinho na próxima execução — não precisa reiniciar nada além de rodar `buscar` de novo. Módulos com mais de `--max-casos-por-modulo` (padrão 100) casos usam amostra determinística em vez de rodar o grid contra todos — medido contra o schema real do usuário (~2.100 tabelas), isso é o que mantém a recalibração num tempo de minuto(s) em vez de vários minutos, sem perder poder de decisão entre os 9 pontos do grid. **Só considera um caso manual do `stella.py` se a tabela esperada existir de fato no `--db` informado** — rodando contra um schema real (não a fixture fictícia), os casos fictícios são ignorados em vez de contados como erro (achado e corrigido nesta auditoria: antes, isso derrubava silenciosamente a taxa de acerto de qualquer módulo real).

## Melhorias pós-auditoria de inovação (v1.2)

Descoberto na auditoria: um prefixo de tabela real do schema não estava cadastrado em `sistemas` e ficava **totalmente invisível** em qualquer busca — achado por acidente, não por processo (detalhes concretos do caso ficam no histórico da conversa, não repetidos aqui para manter esta especificação livre de termos/números específicos de um schema). Corrigido em duas frentes:

- **`checar-modulos`:** `python3 scripts/nomi_nomi_no_mi.py checar-modulos` compara os prefixos que existem de fato no schema contra os cadastrados em `sistemas` e avisa sobre qualquer lacuna — roda também automaticamente ao final de todo `importar`, para não depender de ninguém lembrar de checar.
- **Despriorização em vez de exclusão:** uma tabela de módulo não cadastrado nunca mais é excluída da busca — só recebe uma penalidade de score (`PENALIDADE_MODULO_NAO_CADASTRADO = 0.6`), continuando visível (com `modulo_cadastrado: false`) quando for de fato a melhor resposta. A expansão de vizinhos via FK também parou de filtrar por módulo — uma FK real já é prova suficiente de relação, independente de cadastro.
- **`scripts/edison.py`:** aplica pares de sinônimo já revisados por humano na tabela `sinonimos` (grava as duas direções). Usado nesta auditoria para aplicar os pares de digitação/variação morfológica minerados do schema real do usuário — ver histórico da conversa para os exemplos concretos; não repetidos aqui para manter esta especificação livre de termos específicos de um schema.

**O que ficou de fora, de propósito:** recalibrar o limiar de ambiguidade (12%) e o cutoff do fuzzy (0,82) contra dado real, e expandir a validação cega com pedidos genuinamente seus — os dois dependem de volume de uso real (via `confirmar`) que ainda não existe. Fazer isso agora seria calibrar contra 1 exemplo, não contra evidência.

**Manutenção contínua (responsabilidade de quem estiver rodando esta skill, não do usuário):** de tempos em tempos — por exemplo, quando o usuário mencionar um problema de negócio novo, ou a cada punhado de sessões —, rode `sugerir-sinonimos` de novo e traga candidatos novos pro usuário decidir, em vez de esperar ele lembrar de pedir. O schema real cresce e muda; a lista de candidatos de hoje não é definitiva.

## Melhorias pós-auditoria de inovação (v1.3)

Incidente real (setembro/2026): um relatório de lote contábil analítico
pediu a tabela onde o lote fica persistido; a 1ª colocada do `buscar` foi
uma tabela de staging/temporária **vazia** (0 conexões, 0 registros), que
só venceu por ter colunas bem descritas — a tabela realmente persistida
ficou atrás dela no ranking, apesar de ter FKs e uso real. Auditado em
duas frentes:

- **Causa raiz identificada:** o eixo semântico da fórmula (IDF de coluna,
  peso padrão 0,70) entra em escala absoluta e não é achatado quando o
  eixo estrutural (peso 0,30 sobre uma escala 0-100 normalizada — no
  máximo 30 pontos) está zerado — uma tabela sem nenhum lastro
  estrutural, mas bem documentada, pode vencer uma tabela real com pouco
  vocabulário batendo. Achado adicional da auditoria: `total_registros`
  estava zerado em 100% das tabelas importadas neste ambiente (não é um
  dado específico de nenhuma tabela) — o componente de volume de dados
  da fórmula estava, na prática, sem poder de discriminar nada.
  `importar` passou a avisar automaticamente quando isso acontecesse em
  escala — esse aviso específico não existe mais na v1.4 (abaixo), porque
  o próprio dado que ele checava foi removido do motor.
- **`PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL = 0.5`:** mesma filosofia de
  `PENALIDADE_MODULO_NAO_CADASTRADO` (despriorizar, nunca excluir) — só
  dispara quando a tabela não tem NENHUM lastro (0 conexões *e* 0
  registros); uma tabela nova com FKs declaradas mas ainda sem uso real
  não é penalizada. Coberto por um caso dedicado em `stella.py`
  (`CASOS_CALIBRACAO`) que reproduz o incidente com uma tabela fictícia de
  staging competindo contra as tabelas reais — falha sem a penalidade,
  passa com ela.
- **Passo 1.5** (acima) — checagem humana complementar, porque a
  penalidade reduz o risco mas não o elimina, e a saída de texto do
  `buscar` agora mostra `conexoes=` e um aviso explícito para isso.
- **Outros reforços da mesma auditoria:** `confirmar` avisa (sem travar)
  quando a tabela informada não existe no banco, para erro de digitação
  não poluir silenciosamente uma futura recalibração;
  `contextos/punk_records_log.jsonl` agora tem rotação automática (não
  cresce sem limite); `edison.py` avisa quando um par novo entra em
  conflito com um sinônimo já cadastrado para o mesmo termo.
- **O que fica de fora, de propósito, e por quê:** o valor `0.5` da nova
  penalidade não foi calibrado por grid search nem por casos reais
  confirmados — foi escolhido por analogia ao `0.6` já existente, do
  mesmo jeito que aquele também não foi. Recalibrar os dois exige volume
  de uso real (via `confirmar`) que ainda não existe neste ambiente.
  (A pendência de reimportar `total_registros` real, citada aqui numa
  versão anterior desta seção, foi resolvida na v1.4 — não pela correção
  planejada, mas pela remoção do próprio dado. Ver abaixo.)

## Melhorias pós-auditoria de privacidade (v1.4)

O usuário pediu a remoção da coluna `total_registros` (contagem de linhas
por tabela) de **ambas** as cópias desta skill — o Vegapunk genérico e
esta cópia com Punk Records —, porque volume de dado por tabela é, ele
próprio, informação sensível sobre o negócio da empresa, e o motor não
precisa desse dado para cumprir seu papel (achar a tabela certa por
nome/coluna/FK, nunca por popularidade de dado). Mudanças:

- **Coluna removida do schema:** `tabelas.total_registros` não existe
  mais em `punk_records.db` (nem nesta cópia, já reimportada, nem no
  schema vazio publicado do Vegapunk genérico). `importar`/`detalhar`/
  `buscar` não leem nem gravam mais esse dado — `tabelas.csv` não aceita
  mais essa coluna (se vier no CSV, é ignorada).
- **Fórmula de score_relevancia recalculada, não só truncada:** a
  fórmula antiga (40% filhas + 30% conexões + 15% pais + 15% log do
  volume de registros) perdeu o 4º componente; os 3 pesos restantes
  foram renormalizados para somar 1.0 (mantendo a MESMA proporção
  relativa 40:30:15 entre eles), em vez de simplesmente zerar o peso do
  4º e deixar a soma em 85%. Como o `score_relevancia` só é usado depois
  de normalização min-max por busca (ver `_buscar_criticas`), o ranking
  final é matematicamente idêntico com ou sem essa renormalização — ela
  só mantém a escala 0-100 coerente com a documentação. Ver
  `calcular_metricas_e_scores` em `nomi_nomi_no_mi.py`.
- **`PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL` redefinida:** a condição
  passa de "0 conexões **e** 0 registros" para só "0 conexões" — é o
  único sinal estrutural que resta. Efeito colateral real, encontrado
  rodando a suíte de regressão depois da mudança: uma tabela real mas
  legitimamente órfã de FK (sem nenhuma tabela "mãe"/"filha" modelada)
  agora recebe a mesma penalidade que uma tabela de staging vazia —
  antes, ter registros > 0 evitava essa confusão. Ou seja, a heurística
  ficou **mais grosseira** (perdeu um dos dois eixos que a tornavam
  precisa), não só mais privada. Isso não foi só teorizado: o caso de
  teste "visitante registrado na portaria" (`stella.py`) passou a falhar
  depois da mudança, exatamente por esse motivo, até a fixture ser
  corrigida para modelar a FK que faltava.
- **`checar-modulos` e `sugerir-sinonimos` inalterados** — nenhum dos
  dois lia `total_registros`.
- **Saída de texto:** `registros≈...` some de `buscar`/`detalhar`; o
  aviso `⚠ SEM LASTRO ESTRUTURAL` continua aparecendo, só sem mencionar
  "registros" no texto.
- **Suíte de regressão:** 31/31 (100%) depois da mudança (mesmo número de
  antes) — mas isso exigiu ajustar a fixture fictícia (`T_VISITANTE`
  ganhou uma FK que não tinha, para não ser confundida com staging vazio
  por um acaso de modelagem da fixture, não do motor real). Ver nota
  acima sobre a heurística ter ficado mais grosseira: o schema real pode
  ter tabelas órfãs de FK legítimas que agora ficam despriorizadas sem
  essa mesma correção manual — vale revisar com `checar-modulos`/`buscar`
  se alguma tabela conhecida como "pequena mas real" começar a sumir do
  topo do ranking.

## Melhorias pós-auditoria de privacidade (v1.5)

A v1.4 removeu `total_registros` mas, como nota o próprio texto acima,
deixou a heurística de "sem lastro estrutural" mais grosseira: sem o
segundo eixo (registros), uma tabela real órfã de FK passou a levar a
mesma penalidade que uma tabela de staging vazia — só distinguíveis, na
prática, corrigindo a fixture de teste à mão caso a caso. O usuário
perguntou diretamente se um sinal de volume ajudaria a assertividade do
motor e, confirmando que sim, escolheu explicitamente a opção que
reintroduz o mínimo de informação necessária:

- **`tabelas.tem_dados` (INTEGER 0/1), não uma contagem:** diferente de
  `total_registros`, este campo não expõe *quantas* linhas uma tabela
  tem — só *se* tem alguma. Não dá para inferir volume de negócio, porte
  de operação ou tendência a partir de um booleano; dá só para saber que
  a tabela não está vazia. Essa é a diferença central em relação ao que
  foi removido na v1.4.
- **`PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL` recupera o 2º eixo:** a
  condição volta a ser composta — `conexoes_totais == 0 AND NOT
  tem_dados` — em vez de só `conexoes_totais == 0`. Uma tabela sem FK mas
  com dados reais (ex.: um cadastro legitimamente isolado) deixa de levar
  a mesma penalidade que uma tabela de staging vazia; a distinção que a
  v1.4 tinha perdido volta, sem reabrir a exposição de volume exato.
- **`importar_csvs`:** `tabelas.csv` aceita uma coluna opcional
  `tem_dados`, interpretada como verdadeira para
  `{1, true, sim, s, yes, y}` (case-insensitive) e falsa/ausente em
  qualquer outro caso — mesmo default conservador de antes (tabela sem
  informação = tratada como sem lastro, nunca o contrário). Ver
  `tem_dados_por_tabela` em `nomi_nomi_no_mi.py`.
- **Extração SQL correspondente:** `tabelas.sql` (nos artefatos entregues
  ao usuário) ganhou uma CTE `Volumetria` que consulta `sys.partitions`
  mas só expõe `CASE WHEN SUM(p.rows) > 0 THEN 1 ELSE 0 END` — o `SUM`
  nunca aparece no `SELECT` final, só na comparação. Mesmo princípio do
  booleano, aplicado já na origem do dado.
- **`buscar`/`detalhar`:** o texto de saída ganhou `tem_dados=sim/não`;
  o aviso `⚠ SEM LASTRO ESTRUTURAL` passou a dizer "0 conexões e sem
  dados" para refletir a condição composta.
- **`punk_records.db` (esta cópia):** migrado via `ALTER TABLE tabelas
  ADD COLUMN tem_dados INTEGER NOT NULL DEFAULT 0` — as 2.080 tabelas já
  importadas ficam com `tem_dados=0` até o usuário rodar o `tabelas.sql`
  atualizado e reimportar (`importar --forcar`). Até lá, o comportamento
  é idêntico ao da v1.4 (toda tabela sem conexão é penalizada), porque
  `NOT tem_dados` é sempre verdadeiro com o default 0 — nada piora, só
  deixa de melhorar até o reimport.
- **Vegapunk genérico (sem Punk Records): não recebeu esta mudança.**
  Decisão de escopo, não descuido — a cópia genérica nunca teve
  `PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL` (o mecanismo nasceu de um
  incidente real desta base, documentado na v1.3), então não há
  penalidade para `tem_dados` refinar. Adicionar a coluna lá seria dado
  morto sem consumidor.
- **Suíte de regressão:** 31/31 (100%) depois da mudança — a fixture
  fictícia (`stella.py`) ganhou `tem_dados=1` em todas as tabelas exceto
  `F_DESLIGAMENTO_STAGING_TEMP` (que continua simulando o caso de staging
  vazio, agora com `tem_dados=0` também, não só 0 conexões).
- **O que fica de fora, de propósito:** `tem_dados` não é recalculado
  automaticamente a partir de dado nenhum já existente em
  `punk_records.db` — não há como derivar "a tabela tem linhas" de
  `conexoes_totais`/`tabelas_filhas`/`tabelas_pais`, que são estruturais,
  não de volume. O valor real só chega reimportando com o `tabelas.sql`
  atualizado.


## Motor de fórmulas — Shaka + York (v2.0, 15/10/2026)

Nova funcionalidade: **composição, validação e explicação de fórmulas**, com
motor próprio e conhecimento em pacotes. Detalhes em
[docs/FORMULAS.md](docs/FORMULAS.md).

- **Motor de consultas intocado.** Nenhum arquivo de `scripts/` existente
  mudou (hash congelado em `testes/baseline_consultas_sha256.json`);
  `stella.py` segue 31/31; `punk_records.db` e `punk_records_log.jsonl`
  com hash idêntico. Novo `scripts/atlas.py` grava um golden de
  `buscar()`/`detalhar()` (fixture: 36 pedidos; banco real: 42, incluindo
  os pedidos reais do log) e confirmou comportamento idêntico depois da
  introdução das fórmulas.
- **Achado (pré-existente):** entre tabelas empatadas no score, a ordem do
  `buscar` varia com `PYTHONHASHSEED` (iteração de `set`). Não afeta
  qualidade; o Atlas fixa a semente para comparar. Não corrigido no motor
  de propósito (sem mudança no fluxo de consultas nesta entrega).
- **`scripts/shaka.py` + `scripts/formulas/`:** busca no dicionário,
  detalhe com origem, compositor determinístico (plano JSON → fórmula no
  dialeto), validador em 9 etapas (inclui função inexistente, fora do
  contexto, aridade, uso proibido documentado), explicação rastreável e
  verificação de isolamento core × público × privado.
- **`scripts/york.py`:** ingestão incremental de documentação Confluence
  (página pai → filhas → links relevantes) com manifesto de cobertura e
  normalização para o dicionário. Primeiro pacote público em
  `conhecimento/formulas/publico/` (3 sementes, 53 páginas, 456 funções,
  20 receitas documentadas — detalhes no README do pacote).
- **Camada privada:** `conhecimento/formulas/privado/` (protegida por
  `.gitignore`), `VEGAPUNK_FORMULAS_PRIVADO` ou `--privado` — enriquece,
  nunca sobrescreve a documentação pública.
- **Testes:** `python3 -m unittest discover -s testes` (69 testes) cobre a
  regressão das consultas e o motor de fórmulas, com fixtures 100% fictícias.
- **`SKILL.md`:** só acréscimos (seção "Fluxo de Fórmulas", estrutura,
  convenção de nomes, uma frase na `description`).

## Qualidade da busca de fórmulas (Shaka)

- **Suíte rotulada:** 40 pedidos de analista de folha/ponto → função
  esperada, contra o pacote público, e um medidor no estilo `stella` (
  calibração / held-out / validação cega; acerto@3, acerto@1, MRR).
- **Ranking calibrado** (constantes no topo de `scripts/formulas/conhecimento.py`):
  cobertura do pedido ponderada por IDF (antes: contagem de termos),
  infinitivo ~ 3ª pessoa no radical (`arredondar` ~ `Arredonda`) e bônus de
  cobertura da descrição 2 → 6. Escolhidas olhando só calibração + held-out.
- **Números (acertos no top-3):** calibração 13/16 → 15/16, held-out
  12/12 → 12/12, validação cega 11/12 → 11/12 (sem ganho nem perda
  na cega). Total 36/40 → 38/40.
- **Teste:** `test_formulas_busca_qualidade.py` fixa esses acertos como
  patamar mínimo. Motor de consultas intocado (hash + `atlas` idêntico).

## Revisão de aderência aos pilares (v2.1, 15/10/2026)

Revisão do motor de fórmulas contra o padrão do motor de consultas. Motor de
consultas segue intocado (hash + `atlas` idêntico).

- **CLI igual à de consultas:** `--json` aceito depois do comando
  (`shaka.py buscar "..." --json`), `detalhar` em texto por padrão, toda
  saída numérica em pt-BR (`17,66`).
- **Busca com os mesmos recursos automáticos das consultas:** correção
  aproximada (`fuzzy_aplicado`, cutoff 0,82, só para termo sem nenhum match)
  e sinalização de `ambiguidade` (1º × próximo NOME distinto a < 12%).
  Valores herdados das consultas, declarados como NÃO calibrados para
  fórmulas. Suíte de busca inalterada (38/40).
- **Laço de feedback:** `shaka.py confirmar "<pedido>" FUNCAO`; `buscar`
  registra uso. Log PRÓPRIO em `conhecimento/formulas/privado/shaka_log.jsonl`
  (camada privada; nunca o `punk_records_log.jsonl`). Testes apontam o log
  para um arquivo temporário (`VEGAPUNK_SHAKA_LOG`).
- **Satélite novo — `scripts/egghead.py`:** a suíte de qualidade da busca
  saiu de `testes/` e virou script nomeado (Egghead, o laboratório onde os
  experimentos são medidos). Inclui o grupo `uso_real` (confirmações), só
  para medição, como o `pythagoras.py` faz nas consultas.
- **Marcas de terceiros só dentro do pacote:** casos de teste, README,
  mapa e números específicos da fonte foram para
  `conhecimento/formulas/publico/<pacote>/` (`README.md`, `MAPA.md`,
  `casos/`). Testes do core usam só dialetos fictícios; pacotes reais são
  testados por `testes/test_pacotes_publicos.py`, dirigido por dados.
  `verificar-isolamento` ganhou a checagem 6 (`"marcas"` declaradas no
  `fonte.json` não podem aparecer no core, SKILL.md, CHANGELOG, docs ou testes).
- **Código morto removido:** `_fonte` (compositor) e `CONECTORES` (york).

## Fonte em PDF e complemento privado de fórmulas (v2.2, 15/10/2026)

Motivação: uma fórmula real do usuário usava duas funções sem ficha no
dicionário público (uma delas já aparecia em exemplos da própria
documentação pública, sem ficha). O usuário tinha o manual de treinamento
do fornecedor em PDF, com as duas documentadas.

- **Conector novo `formulas/ingestao/pdf.py`** (York, `"conector": "pdf"`):
  arquivo local, sem rede, via `pdftotext -layout`. Remove cabeçalho/rodapé
  por regex do `fonte.json`, junta prosa quebrada pelo layout, segmenta em
  SEÇÕES (`padrao_secao`/`ignorar_secao`) para um bloco de função não ser
  cortado na quebra de página, troca aspas tipográficas pelas retas
  (`normalizar_aspas_tipograficas`; o texto como saiu do PDF fica em
  `texto_extraido`). URL de origem: `arquivo://<nome>#page=N`.
- **Normalizador entende `estende`:** pacote que estende outro gera fichas no
  namespace do pacote-base (o merge por id funciona) e usa o dialeto do base
  (sem copiar — o motor continua com um dialeto só). Documentos e receitas
  mantêm o id próprio.
- **Merge privado preenche lacuna de sintaxe:** se a ficha pública não tem
  sintaxe nenhuma (aridade vazia), a sintaxe do complemento privado entra,
  marcada em `sintaxe_complementada_por`. Sintaxe pública documentada
  continua NUNCA sendo trocada (divergência = aviso + `variantes_privadas`).
- **`funcoes_sensiveis: false`** no manifesto de um pacote privado: os nomes de
  função dele (do próprio fornecedor, não segredos da instalação) não entram
  na checagem 5 do `verificar-isolamento`; `termos_sensiveis.json` continua
  valendo.
- **Por que privado e não público:** o manual traz aviso explícito de
  direitos reservados (reprodução e armazenagem proibidas sem autorização) —
  o conteúdo fica só na instalação, protegido pelo `.gitignore` da camada.
- Testes: `testes/test_formulas_ingestao_pdf.py` (PDF fictício gerado no
  teste). Suíte 83/83, `atlas` idêntico, Egghead inalterado (38/40).

## Fundação da v3 — fase 0 (15/10/2026)

- **Desempate determinístico nas consultas:** entre tabelas com score
  idêntico, o `buscar` desempata pelo nome da tabela (e o corte em 30
  críticas também). Mesmo critério no `ranking` calculado pelo `importar`,
  no `sugerir-sinonimos` e no `checar-modulos`. A saída passa a ser a mesma
  com qualquer `PYTHONHASHSEED`; o `atlas.py` não fixa mais a semente.
  Nenhum score mudou. Mudaram só a ordem entre empatados e o que deriva
  dela (tabelas empatadas no corte, módulo inferido, vizinhos expandidos,
  avisos de ambiguidade), valores que antes já variavam de uma execução
  para outra. Stella 31/31 e Egghead 38/40, inalterados.
- **Atlas cobre fórmulas:** golden do Shaka (busca, detalhe,
  validação/explicação e composição), na fixture fictícia e na instalação
  real (camada privada).
- **`verificar-isolamento` verifica de verdade a camada privada:** antes, um
  pacote privado com `"funcoes_sensiveis": false` e sem
  `termos_sensiveis.json` fazia a checagem de termos rodar com 0 termos,
  sem verificar nada. Agora há mais duas checagens. A primeira compara
  trechos de 12 palavras do texto privado com a superfície distribuível; o
  texto que o fornecedor também publica não conta. A segunda falha fechada
  quando um pacote privado não contribui com nenhum termo nem trecho. A
  saída nunca repete termo ou trecho privado, só aponta arquivo e linha.

## Reorganização da v3 — fase 1 (15/10/2026)

Nenhum resultado mudou: os goldens do Atlas da tag `v3-fase0` são a
referência da fase inteira e continuaram idênticos nos dois domínios e nos
dois modos (fixture e instância real).

- **Estrutura por papel:** `stella.py` (entrada única), `satelites/`
  (York, Edison, Shaka, Pythagoras, Lilith, Atlas), `nomi_nomi_no_mi/`
  (núcleo do schema, antes um arquivo só), `dominios/` (schema, fórmulas,
  isolamento e separação), `punk_records/` (escrita na base, ingestão e
  pacotes de conhecimento), `casos/` (casos, fixtures e goldens
  fictícios), `referencias/` e `egghead/` (instância local).
- **Nomes:** a suíte da antiga `stella.py` e o `egghead.py` viraram parte
  do Pythagoras (`avaliar --dominio schema|formulas`); só depois o nome
  Egghead passou a designar a instância local e a Stella virou a entrada
  única.
- **York, única porta de escrita:** `importar`, `gravar-sinonimos` e
  `migrar`, além da ingestão de documentação. O Edison ficou só com a
  análise (`sugerir-sinonimos`).
- **Sem atalhos para os comandos antigos:** a CLI do motor de schema e a do
  Shaka saíram; os comandos de fluxo entram por `stella.py`.
- **Avisos de merge** entre camadas saíram da saída normal e foram para
  `stella.py status`, que também mostra as camadas presentes e os números
  da instância (fonte única desses números).
- **Isolamento:** superfície distribuível definida por regra; nova checagem
  dinâmica prova que cada domínio roda sem o outro (`atlas.py isolamento`).
- **Documentação:** `SKILL.md` virou um roteador curto; o detalhe foi para
  `referencias/` (fluxos, T-SQL, nomes). `AVISO.md`, `COMO-INSTALAR.md` e os
  READMEs cobrem as duas versões (Vegapunk e Vegapunk com Punk Records).

### Núcleo de texto compartilhado (bloco B8 da fase 1)

Regra da fase: unificar só se os goldens dos dois domínios continuassem
idênticos; se a unificação mudasse qualquer resultado, manter a duplicação
e registrar o motivo.

- **Unificado** em `nomi_nomi_no_mi/texto_comum.py`: `normalizar` e
  `formatar_numero_ptbr`, idênticas nos dois domínios. Prova: 66.621 textos
  (descrições do schema real e strings dos pacotes) e 400.024 formatações
  com zero diferenças; Atlas idêntico nos dois domínios e modos. O
  `__init__` do pacote resolve os nomes sob demanda, então o domínio de
  fórmulas usa o núcleo comum sem carregar o schema (a checagem dinâmica de
  separação continua verde e pega acoplamento pela fachada do pacote).
- **Mantido duplicado, de propósito:** `radical` (o schema corta
  `oes/aes/ais/eis/is/ns/s`; fórmulas também `coes/soes/ois/res` e repõe o
  "o" de `funcoes -> funcao`), a tokenização (schema: tokens de 4+
  caracteres e números de 2–3 dígitos, em conjunto; fórmulas: tokens de 3+
  caracteres, em ordem) e as stop words (listas diferentes, cada uma
  calibrada pelo seu domínio). Unificar qualquer um deles mudaria o ranking
  de pelo menos um domínio e o golden. Fica para uma fase com calibração
  própria (fase 5), sob decisão explícita.

## Schema completo da v3 — fase 2 (16/10/2026)

Regra da fase: o ranking do `buscar` não muda; só entram avisos novos. O
`detalhar` pode ganhar campos. Os goldens de schema foram recapturados só
depois do diff classificado contra a v3-fase0 (campos novos, avisos novos,
outras mudanças) e do aceite, com o grupo "outras" vazio. Na instância
real: 15.476 campos novos, 57 avisos novos, 0 outras; o `buscar` ficou
idêntico pedido a pedido. Os goldens de fórmulas não mudaram.

- **Migração 002:** `colunas` ganha `tipo`, `tamanho`, `precisao`,
  `escala`, `nulo`, `ordem` e `pk_ordem`; `relacionamentos` ganha
  `constraint_nome` e `ordem`. Todas anuláveis; nenhuma linha muda.
- **Extração só de catálogo:** `punk_records/extracao/` tem uma consulta
  por CSV (`tabelas.sql`, `colunas.sql`, `relacionamentos.sql`), só sobre
  `sys.*`, sem modo SQLCMD e sem nome de banco; o schema é `@esquema`
  (padrão `dbo`) e um schema vazio faz a consulta falhar listando os que
  existem. O tipo gravado é o tipo base (um tipo de usuário vira o de
  origem). A extração do dicionário de um ERP específico fica no pacote
  privado.
- **`york.py enriquecer`:** grava a estrutura física nas linhas que já
  existem, com cópia de segurança e transação, sem tocar em descrição, FK,
  `tem_dados` ou métricas. Casa cada FK física com um relacionamento
  lógico só quando a constraint inteira cabe nele e mostra a cobertura.
- **Leitor de CSV do York:** aceita UTF-16 e o rodapé do SSMS, desembrulha
  a exportação da grade e recusa CSV vazio ou só com cabeçalho antes de
  escrever qualquer coisa.
- **`detalhar`:** tipo e PK das colunas, FKs agrupadas pela constraint com
  o `JOIN` pronto, FKs sem constraint à parte (com aviso) e o menor caminho
  de JOIN entre as tabelas pedidas (até 4 saltos; desempate por grau e
  depois por nome).
- **Avisos novos no `buscar`:** vizinhos via FK cortados (nem toda tabela
  ligada entrou em `expandidas`) e corte das 30 críticas no meio de um
  empate de score (registrado na fase 0).

### Agrupamento provado pela PK da mãe (bloco F2b, 16/10/2026)

Dos 5.346 pares compostos (filha, mãe) da instância real, 3.280 não tinham
constraint física inteira. Antes de mudar o `detalhar`, cada critério foi
medido contra o gabarito físico: os 2.066 pares com constraint declarada,
com o nome escondido. O critério "ligação única" sozinho (todos os campos
juntos quando nenhum se repete) erra 2 vezes; o critério implementado erra
0 (acerta 2.026 e se abstém em 40). Índice único da mãe como chave também
foi medido e ficou de fora: não provaria nenhum par novo.

- **`ligação única + chave da mãe`:** nenhum campo da filha nem da mãe se
  repete e os campos da mãe são exatamente a PK dela.
- **`chave da mãe`:** há repetição, mas a PK separa as ligações numa forma
  só (colunas fixas + uma coluna com variantes). O mesmo campo da filha em
  duas colunas da mãe fica de fora: nenhuma FK física tem essa forma.
- **Resultado:** 2.066 pares com constraint, 1.076 provados pela chave e
  2.204 com aviso. As linhas sem prova ganham `motivo`; o aviso conta as que
  não cobrem a PK inteira da mãe (o JOIN pode multiplicar linhas).
- **Avisos do `detalhar`:** o de FK sem agrupamento aponta para
  `punk_records/extracao/relacionamentos.sql`; o "Sem caminho" lista só os
  10 primeiros pares e diz quantos faltam (lista completa em `caminhos`).
- **Portão:** ranking e avisos do `buscar` idênticos; diff do `detalhar`
  com as mudanças combinadas conferidas item a item e 0 outras mudanças.
- **Dicionário do ERP:** as consultas de descrições, relacionamentos
  lógicos e módulos ficam no pacote privado da instância (nunca no git).
  Uma reimportação só pelo catálogo apagaria as descrições, que são a base
  da busca; por isso o catálogo só enriquece (`york.py enriquecer`).

### Ligações do dicionário do sistema (bloco F3-0b, 16/10/2026)

Ao validar as consultas do dicionário do ERP contra a base da v1, achou-se
que o dicionário de relacionamentos traz UMA linha por ligação, com os
campos em lista. A v1 quebrou essas listas em uma linha por campo e perdeu
o agrupamento. Expandidas, as 9.506 ligações dão exatamente as 17.083
linhas da base (mais 3 ligações novas no ERP). Agrupadas pelo dicionário,
batem com as constraints declaradas em 2.066 de 2.066 pares compostos.

- **Migração 003:** `relacionamentos.ligacao`. `york.py enriquecer
  --dicionario` grava o número da ligação (só UPDATE); o `importar` aceita
  o formato em lista.
- **Ordem de prova no `detalhar`:** constraint, dicionário, chave da mãe.
  Constraint x dicionário são comparados por conjunto de campos do par
  (linhas idênticas são intercambiáveis); em conflito, nenhum vale.
  Dicionário x chave da mãe: vence o dicionário.
- **Erro do F2b corrigido:** num par, duas ligações que se cruzavam na PK
  da mãe, com uma linha repetida igual, tinham virado um JOIN só. Linha
  repetida igual agora é ambígua para a chave da mãe; o dicionário desmentiu
  esse JOIN e pôs as duas ligações certas.
- **Resultado na instância:** 5.346 de 5.346 pares compostos com
  agrupamento provado (2.066 constraint, 2.206 dicionário, 1.074 chave da
  mãe confirmada pelo dicionário); 0 conflitos. Toda FK ganha
  `cobre_chave_da_mae`, e um aviso conta as que não usam a PK inteira.
- **Texto NULL:** o `importar` e o `enriquecer` tratam o texto literal NULL
  como vazio e contam quantos converteram.
- **Cópia de segurança:** duas cópias no mesmo segundo não se sobrescrevem
  mais (a da migração 003 foi sobrescrita pela do `enriquecer`; a que ficou
  é a base na versão 3 sem nenhuma ligação, igual à anterior a menos da
  coluna vazia).
- **Filtro da consulta privada:** continua só na tabela mãe, como a v1 (a
  base da v1 tem ligações com a filha em outro módulo).
- **Pendente, com portão próprio de ranking (`importar --forcar`):** 46
  tabelas com a descrição gravada como o texto NULL, 2 descrições com aspas
  perdidas na v1, 1 tabela nova e 10 colunas, 1 coluna nova, 1 coluna que
  saiu, 4 tabelas com `tem_dados` diferente e o módulo cadastrado à mão só
  na base.

## Mapa — fase 3 da v3 (16/10/2026)

### Mapa real fora da superfície distribuível (bloco 3a)

- **Decisão:** o mapa de um sistema real cita tabelas reais, então é da
  instância (pacote privado), nunca distribuível. Só um mapa fictício,
  coerente com a fixture, vai para o público.
- **Registro:** o mapa real esteve versionado no pacote público, no
  histórico LOCAL do repositório, do primeiro commit até o commit do bloco
  3a, quando saiu do índice e foi para
  o pacote privado da instância (`punk_records/pacotes/privado/<pacote>-mapa/`). O repositório nunca teve
  remoto: o mapa nunca saiu da máquina. O histórico não foi reescrito, por
  decisão do usuário.
- **Repositório sem remoto:** o hook pre-push recusa qualquer push e
  explica por quê; ele é instalado por `ferramentas/instalar_hooks.py`
  (hooks não vão no git; o script vai).
- **Distribuição:** `atlas.py distribuir --destino <pasta>` é a única
  saída. Pasta separada, fora do repositório, sem `.git`, com exatamente a
  superfície distribuível (allowlist por regra), só depois de o isolamento
  passar. Falha e apaga a pasta gerada se encontrar `.git` ou arquivo fora
  da allowlist.
- **Isolamento, checagem 9:** todo mapa na superfície distribuível (arquivo
  `mapa*.json`, arquivo numa pasta `mapa/` ou JSON com as partes do
  contrato) precisa declarar `"ficticio": true` e citar só tabelas do
  schema fictício (`casos/tabelas_ficticias.json`, conferida contra a
  fixture por teste). A saída nunca repete o nome da tabela.

### Contrato, compilação, sugestões e ligações (blocos 3b, 3c e 3d)

- **Contrato v2 e York `compilar-mapa`** (migrações 004 e 005): o York
  confere o mapa contra o contrato e o schema e recusa o arquivo inteiro
  quando algo parece conteúdo de registro (12 recusas plantadas nos testes,
  com a base intacta). Na instância: 7 cadastros, 31 papéis de coluna, todas
  as tabelas e colunas existem no schema, e as consultas ganharam a chave
  completa (a "chave" antiga dos campos e parâmetros era a ligação com a
  consulta).
- **Papel pela descrição:** 1 papel divergente na instância (a coluna da
  fórmula "crítica" do cadastro de eventos, cuja descrição fala de
  crédito). A ligação continua, porque é provada; o aviso aparece no
  `compilar-mapa` e no `stella.py status`, não no `detalhar` de um código que
  não usa esse papel.
- **Edison `sugerir-mapa`:** 3 sugestões aprovadas pelo usuário (a mesma
  entidade de um cadastro já declarado). Um rótulo novo entrou com prova
  documental: exemplos e descrições do fornecedor mostram o mesmo código
  passado à função que executa a consulta e às que leem e avançam o
  resultado. Uma variante de contexto da função de avanço ficou de fora: a
  documentação não a liga à execução da consulta (pendência para a fase 4).
- **`detalhar`:** 36 parâmetros de código ligados na instância, todos com o
  SQL de apoio validado; 22 continuam só rótulo (empate entre tabelas,
  nenhuma coluna da PK que prove, ou rótulo só "código").
- **Portão:** busca de fórmulas 38/40 e de schema 31/31, sem mudança; diff
  do golden real de fórmulas com 1 campo novo (as ligações) e 0 outras
  mudanças; goldens de consultas idênticos.
- **Papel divergente resolvido pelo usuário (16/10/2026):** a coluna da fórmula
  "crítica" do cadastro de eventos é mesmo de crítica (valida regras e impede
  gravação inconsistente); a descrição do dicionário da origem, que fala de
  crédito, está errada. O contrato ganhou `papeis_confirmados` (prova
  "usuario", fonte e data; migração 006). A divergência saiu de pendente,
  ficou registrada como resolvida, e a descrição errada ficou marcada como
  conhecida: o Edison não a usa como evidência. Papéis divergentes: 1 -> 0.

### Documentação de fórmulas completada (bloco F3-doc, 16/10/2026)

- A semente do contexto global passou a ser a página-mãe "Fórmulas" do
  Framework, que traz Funções Globais, Fórmulas Globais e Cadastro de
  Fórmulas. Duas páginas antigas da mesma árvore (fórmulas em outra
  linguagem e filtro de relatório) foram excluídas por id.
- O coletor ganhou `excluir_page_ids`, `paginas_aprovadas` (página nova na
  árvore fica `nova_na_arvore` e só entra com aceite) e a regra de que
  pertencer à árvore prevalece sobre ter sido achada por link, inclusive no
  contexto.
- Resultado: nenhuma função nova nem removida; as três funções de consulta
  SQL do contexto global ganharam a segunda origem, uma assinatura e um
  exemplo. Busca de fórmulas sem queda (38/40). Diff do golden real todo
  explicado (score por mudança de corpus, as três fichas e 11 pedidos com
  ordem diferente abaixo do top-1); recapturado com aceite.

### Fechamento da fase 3 (bloco F3-fim, 16/10/2026)

- A linha de base da v3 (números de referência de cada fase) saiu da
  superfície distribuível e foi para a instância (`egghead/`): ela trazia
  nomes de coluna do schema real, registrados numa medição. Esteve no
  histórico local do repositório até este bloco e nunca saiu da máquina.
- Isolamento, checagem 10: nenhum nome do schema real na superfície
  distribuível. A régua vem da instância (todas as tabelas e as colunas
  técnicas), sem as colunas da fixture, sem o vocabulário que o fornecedor
  publica e sem as palavras que as próprias descrições usam. A saída nunca
  repete o nome; sem instância, não há o que comparar. O `atlas.py
  isolamento` e o `atlas.py distribuir` rodam essa checagem.
- Exemplos com nomes reais nas docs e nos testes trocados por nomes
  fictícios; docs revistas (camada Mapa na estrutura da base, mapa só
  fictício na versão distribuível, nota sobre os caminhos antigos neste
  histórico, linha do mapa no roteador do SKILL.md).

### Atualização da base no lugar e filtro do dicionário (bloco 5a, 16/10/2026)

- `york.py atualizar --dicionario DIR [--catalogo DIR] [--aplicar]`: aplica um
  export novo do dicionário do sistema sem recriar a base (o `importar --forcar`
  perderia o que veio depois do import: migrações, ligações do dicionário,
  direção corrigida, mapa, papéis confirmados e sinônimos). Muda só descrições
  de tabela e de coluna (descrição vazia de tabela fica NULL, como no
  `importar`), `tem_dados`, tabela nova (métricas recalculadas pela mesma
  função do `importar`), colunas novas (estrutura do catálogo) e coluna
  removida, recusada se uma FK ou o mapa a usa. Cadastros do usuário em
  `sistemas` não mudam. Sem `--aplicar` só lista o que muda.
- Teste de reconstrução: uma instalação do zero (importar, migrar,
  enriquecer, corrigir-direcao, compilar-mapa e sinônimos exportados da base)
  chega à mesma base que a atualizada no lugar, a menos dos cadastros feitos à
  mão e das ligações antigas que o filtro abaixo deixou entrar.
- Correção que era do bloco F3-0b e não tinha sido feita: o
  `relacionamentos.sql` do pacote do dicionário passa a exigir as DUAS pontas
  da ligação (filha e mãe) nos prefixos da instância. A consulta herdada da v1
  filtrava só a mãe e trazia ligações de filhas de outros módulos, que não
  existem na base: ligação para tabela inexistente não prova relevância e
  infla as métricas de filhas. As ligações desse tipo que já estão na base
  são decididas na calibração (bloco 5c), com portão de ranking.

### Calibração da pontuação estrutural (fase 5 da v3, 16/10/2026)

- **Ligação só conta com as duas pontas na base.** `calcular_metricas_e_scores`
  ignora, nas contagens de filhas, pais e conexões, a ligação cuja filha ou mãe
  não está na tabela `tabelas`. As linhas continuam na base (o `detalhar` e o
  grafo não mudam); só deixam de contar como prova de relevância. Fecha a
  decisão adiada no 5a para as ligações antigas de filhas fora dos prefixos.
- **Pesos estruturais recalibrados.** Os pesos 40/30/15 (filhas, conexões,
  pais) vinham da v1, ajustados com a direção do dicionário trocada. Com a
  direção corrigida e a regra acima, uma grade de passo 0,05 rodou só no
  conjunto de calibração do gabarito do schema real da instância (sorteado e
  congelado antes de qualquer ajuste) e escolheu 0/15/85: a tabela que
  aponta para muitas mães (o fato, o movimento, o histórico) passa a pesar
  mais que a tabela que recebe muitas filhas (o cadastro central). A fixture
  fictícia segue 31/31. Conferido uma vez no conjunto cego: melhora o
  acerto@3 contra a v3-fase4.
- **`york.py recalcular-metricas`**: recalcula as métricas no lugar pela fórmula
  atual (cópia de segurança e transação; ligações intactas). Os pesos ficam
  como constantes de módulo (`PESO_FILHAS`, `PESO_CONEXOES`, `PESO_PAIS` em
  `punk_records/schema.py`).

## Memory Card (27/10/2026)

- **`satelites/memory_card.py`**: cartão de memória dos relatórios. Cada
  relatório pronto vira um save num repositório git do próprio usuário no
  GitHub (privado por padrão), em `saves/<categoria>/<secao>/<artigo>/`, com
  o artigo (`README.md`), o `relatorio.sql` e a `ficha.json`. Comandos
  `iniciar`, `catalogo`, `buscar`, `enviar` (prévia com diff e `--confirmar`;
  `--motivo` obrigatório numa versão nova), `marcar` (status `rascunho` ou
  `em-uso`) e `conferir` (tabelas e colunas na Punk Records, só leitura).
  Guia em [memory-card.md](memory-card.md).
- **A funcionalidade é do motor; o cartão é do usuário.** Qual é o cartão
  fica na instância (`egghead/memory_card.json`), fora do git e da
  distribuição. Antes e depois de cada commit a visibilidade é conferida no
  GitHub, e o envio é recusado se o cartão não for privado.
- **`pessoal/` é pasta de instância** (`_PASTAS_INSTANCIA`): extensões que só
  existem na versão pessoal nunca entram na superfície distribuível.
- **Palavras proibidas da instância**: a chave `palavras` de
  `egghead/termos_proibidos.json` lista palavras ou expressões (ex.: o
  repositório do cartão) que a checagem de nomes recusa na superfície, em
  qualquer caixa e com qualquer separador.

## Lembretes do fluxo e cópias só de leitura (27/10/2026)

- **`dominios/lembretes.py`**: o motor escreve o próximo passo que não pode
  ser esquecido, numa linha `LEMBRETE:` em stderr (a saída em JSON e o que o
  Atlas compara não mudam). O `detalhar` dos dois domínios lembra do
  `confirmar` no fim do fluxo: nos logs, só 1 de 9 buscas de schema tinha
  sido confirmada. Com um Memory Card configurado, o `buscar` do schema
  lembra de procurar no cartão, o `confirmar` do schema e o `solucionar` com
  SQL lembram de oferecer salvar, e o `importar`, o `enriquecer` e o
  `atualizar --aplicar` do York lembram do `conferir`.
- **Regras 12 e 13 do `SKILL.md`** (Memory Card; ler os `LEMBRETE:`), a
  descrição da skill cita o Memory Card e uma nota manda usar `python` onde
  `python3` não existe (Windows).
- **Instância só de leitura não derruba o fluxo.** O log de fórmulas, a
  candidata do `solucionar` e o aceite deixam de quebrar quando a pasta não
  aceita gravação: o log é perdido, a solução sai sem candidata (com aviso)
  e o aceite recusa explicando. O `confirmar` diz quando não registrou.
- **Memory Card fora do lugar**: sem `gh`, sem autenticação ou sem o
  comando, a recusa diz onde o cartão funciona; sem rede, `catalogo` e
  `buscar` usam a cópia local.


## Auditoria de integração (27/10/2026)

Auditoria função por função numa cópia isolada da instância, procurando
onde uma função não conversa com a outra. O que mudou:

- **Um conferidor de SQL só.** O Memory Card tinha um leitor próprio de SQL,
  que entendia CTE mas não conferia JOIN (um JOIN por só parte de uma chave composta passava);
  o `montagem.conferir` do `solucionar` conferia JOIN, mas acusava nome de
  CTE como "tabela não existe" (a maioria dos relatórios reais usa CTE). Agora
  `nomi_nomi_no_mi/montagem.py` tem `referencias` (lê o SQL sem base: CTE,
  temporária, subconsulta, colchetes) e `conferir` usa essa leitura; o
  Memory Card usa os dois no `enviar` e no `conferir`. JOIN com CTE,
  subconsulta ou tabela fora da base sai como "ligação não conferida".
- **Salvar no cartão confirma.** O `enviar --confirmar` grava no log de uso
  a confirmação com todas as tabelas do relatório
  (`historico.confirmar`, campo `tabelas_confirmadas`; a principal continua
  em `tabela_confirmada`). O `stella.py confirmar --dominio schema` aceita
  várias tabelas, e a calibração do Pythagoras aceita qualquer uma delas no
  topo (o módulo é o da principal). Antes, quase nenhuma busca virava
  confirmação, e nenhum relatório salvo no cartão.
- **`detalhar` enxuto.** Duas tabelas muito ligadas da base real davam 133 KB, com o JOIN
  pronto e o lembrete nas últimas linhas, depois do corte de 30 mil
  caracteres do terminal do Claude Code. Agora o caminho com o JOIN e os
  avisos vêm primeiro, o lembrete sai antes da saída, e as FKs para tabelas
  fora do pedido saem numa linha, sem o JOIN (`--completo` traz tudo): 47 KB.
  O JSON não muda.
- **Casos aceitos medidos.** O `casos_solucao_aceitos.json` era gravado e
  nunca lido; o `pythagoras avaliar --dominio solucoes --db` agora mede esses
  casos junto com os da instância. E o rótulo estava errado: o esperado de
  uma intenção de fórmulas era o 1º lugar da busca, não a função que a
  fórmula aceita usa (no caso testado, `EXISTEEP` em vez de `C`). Agora é a
  função da fórmula; quando não dá para saber, a intenção fica sem rótulo.
- **Memory Card na Stella.** `stella.py cartao ...` despacha para o
  `memory_card.py`, o `status` mostra o cartão, os lembretes apontam para a
  Stella, e a busca do cartão usa a normalização do `buscar` do schema
  (stop words, plural, sinônimos da Punk Records), com corte por cobertura
  (metade dos termos): antes, uma palavra comum ("de", "com") bastava para
  um save sem relação aparecer.
- **Nível da solução no cartão.** `saves/<solucao>/<categoria>/<secao>/<artigo>/`
  (padrão `Vegapunk`; `--solucao` para outra ferramenta). `migrar` move um
  cartão antigo, com as ligações entre artigos.
- **Views na extração.** O `tabelas.sql` e o `colunas.sql` liam só
  `sys.tables`: uma view usada num relatório nunca chegava à Punk Records.
  Agora têm `@objeto` (`'U'` tabelas, `'V'` views) e as views entram com o
  `york.py atualizar` (ver [schema.md](schema.md), "Views").
- **Atlas da instância.** Um pedido que entrou no log de uso depois da
  captura do golden não é mudança de comportamento: fica fora da comparação
  (com uma linha de informação) até o próximo `capturar`. Antes, toda busca
  real nova deixava o portão vermelho de vez.
- **`valor` continua stop word nas fórmulas (medido).** Tirar `valor` das
  stop words derrubou a avaliação de 38/40 para 36/40 e não trouxe a função
  `C` para o top 5 de "valor de um evento". Usar `valor` só no desempate
  manteve 38/40, mas na base real o 1º lugar da auto-recuperação (a descrição
  de cada função como pedido) caiu de 453 para 451 em 524, e 784 respostas do
  golden real mudaram. Nenhuma das duas mudanças entrou. Um pedido como
  "valor de um evento" pede `--contexto` e a revisão dos candidatos; a
  correção certa é um sinônimo revisado, não uma regra geral.
