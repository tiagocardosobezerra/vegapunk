# Como instalar o Vegapunk

A skill é a pasta inteira. Substitua a pasta que você já tem por esta; não
precisa rodar nada para começar a usar. Depois, para ver o que está
instalado nesta cópia:

```bash
python3 stella.py status
```

## As duas versões

- **Vegapunk** (distribuível): só o motor. A pasta `egghead/` não existe e o
  domínio schema roda em modo básico até você importar a estrutura do seu
  banco. Crie a pasta `egghead/extracao/`, extraia o catálogo com as
  consultas de `punk_records/extracao/` (troque `SERVIDOR` e `SEU_BANCO`;
  precisam só de `VIEW DEFINITION`) e importe:

  ```bash
  sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000 -i punk_records\extracao\tabelas.sql -o egghead\extracao\tabelas.csv
  sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000 -i punk_records\extracao\colunas.sql -o egghead\extracao\colunas.csv
  sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000 -i punk_records\extracao\relacionamentos.sql -o egghead\extracao\relacionamentos.csv
  python3 satelites/york.py importar --dir egghead/extracao
  python3 satelites/york.py migrar aplicar
  python3 satelites/york.py enriquecer --dir egghead/extracao
  ```

  Com o dicionário de dados do ERP (precisa de `SELECT` nas tabelas dele),
  importe pelos CSVs do dicionário e enriqueça com os do catálogo; ver o
  `README.md`. Formato dos CSVs: [referencias/schema.md](referencias/schema.md),
  seção "Formato dos CSVs de import". O texto da documentação de fórmulas do
  fornecedor é regenerado com
  `python3 satelites/york.py ingerir --pacote punk_records/pacotes/publico/<pacote>`.
- **Vegapunk com Punk Records** (privado): o mesmo motor com a instância
  local já preenchida em `egghead/`. Use só no seu ambiente; ver `AVISO.md`.

A versão **Vegapunk** é gerada a partir do repositório de trabalho só por
este comando, numa pasta nova fora do repositório:

```bash
python3 satelites/atlas.py distribuir --destino ../vegapunk-distribuivel
```

Ele roda o isolamento, copia só a superfície distribuível (allowlist por
regra: nada de `egghead/`, pacote privado, texto do fornecedor nem `.git`)
e confere a pasta gerada; se aparecer `.git` ou qualquer arquivo fora da
allowlist, a distribuição falha e a pasta é apagada. O repositório de
trabalho nunca vai para um remoto: rode `python3 ferramentas/instalar_hooks.py`
(da raiz do repositório) para instalar o hook que recusa qualquer push.

## Mais de um banco

Cada banco tem a sua instância: `egghead/` (a padrão) e `egghead-<nome>/`,
todas fora do git e da distribuição. Para um banco novo, crie a pasta
`egghead-<nome>/extracao/`, extraia o catálogo dele como acima e importe com
`--instancia <nome>`:

```bash
python3 satelites/york.py --instancia <nome> importar --dir egghead-<nome>/extracao
python3 satelites/york.py --instancia <nome> migrar aplicar
python3 satelites/york.py --instancia <nome> enriquecer --dir egghead-<nome>/extracao
python3 stella.py instancias
```

Um `instancia.json` na pasta descreve o banco (`descricao` e `assuntos`).
Para cada pedido, `python3 stella.py instancias --pedido "<pedido>"` mostra
quantos termos dele cada base cobre e qual instância é a mais provável (só
leitura). Todo comando da Stella e dos satélites (York, Edison, Atlas,
Memory Card) aceita `--instancia <nome>`. O Memory Card é um só: sem
`memory_card.json` na instância, vale o de `egghead/`. Banco com vários
schemas e nomes de tabela repetidos entre eles: uma instância por schema.
Detalhes em [referencias/schema.md](referencias/schema.md).

## Zip pessoal (skill no claude.ai)

Para usar a skill com as suas instâncias na sua conta do Claude, gere o zip
da raiz do repositório, sempre fora dele:

```bash
python3 ferramentas/empacotar_privado.py --destino ~/Downloads/vegapunk-privado.zip
```

Ele leva o motor e as instâncias, sem `.git`, testes, cópias de segurança e
CSVs de extração (limite do claude.ai: 200 arquivos), e grava um
`VERSAO.json`: o `stella.py status` da cópia instalada mostra a versão e
avisa quando o repositório está à frente. O zip tem a estrutura dos seus
bancos: nunca o compartilhe.

## Memory Card (opcional)

Para salvar e versionar os seus relatórios num repositório seu no GitHub,
instale o [GitHub CLI](https://cli.github.com/), autentique (`gh auth login`)
e crie o cartão uma vez:

```bash
python3 stella.py cartao iniciar --repo SEU_USUARIO/memory-card
```

O cartão é criado privado e a configuração fica em `egghead/memory_card.json`,
fora do git e da distribuição. Guia em
[referencias/memory-card.md](referencias/memory-card.md).

## Conferir a instalação

```bash
python3 -m unittest discover -s testes
python3 satelites/atlas.py verificar
python3 satelites/atlas.py isolamento
```

Na versão com Punk Records, o Atlas também confere a instância real:
`python3 satelites/atlas.py verificar --db egghead/punk_records.db`.

Os números de referência da qualidade (testes, busca de fórmulas, avaliação
do schema, isolamento) ficam num lugar só, na instância (fora do controle de
versão): `egghead/linha_de_base_v3.json`.
Os números da sua instância saem do `stella.py status`.

## Atualizar uma base já instalada

A estrutura da base muda só por migrações numeradas, com cópia de
segurança automática em `egghead/backups/`:

```bash
python3 satelites/york.py migrar status
python3 satelites/york.py migrar aplicar
```

Se a pasta estiver num serviço de sincronização (OneDrive e parecidos),
pause a sincronização antes de importar ou migrar.
