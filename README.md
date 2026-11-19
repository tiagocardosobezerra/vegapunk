<a href="https://tiagocardosobezerra.github.io/vegapunk/"><img width="100%" alt="Vegapunk: pergunte em português e receba o T-SQL com os nomes reais do seu banco: as tabelas, as colunas e os JOINs reais do seu SQL Server. Na animação, o pedido 'funcionários ativos com o nome da seção' encontra as tabelas T001042 e T000318, prova o JOIN pela chave composta e vira a consulta." src="assets/readme/hero.svg" /></a>

<p align="center">
  <a href="https://tiagocardosobezerra.github.io/vegapunk/"><strong>Site do projeto</strong></a> ·
  <a href="https://tiagocardosobezerra.github.io/vegapunk/#demo"><strong>Ver a demonstração</strong></a> ·
  <a href="#comece-em-3-passos"><strong>Instalar</strong></a> ·
  <a href="#resultados"><strong>Resultados</strong></a>
</p>

<p align="center">
  <strong>Português</strong> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <img alt="Skill do Claude Code" src="https://img.shields.io/badge/Claude%20Code-skill-d97757?style=flat-square" />
  <img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img alt="Sem dependências" src="https://img.shields.io/badge/depend%C3%AAncias-nenhuma-2ea44f?style=flat-square" />
  <img alt="SQL Server 2016 a 2022" src="https://img.shields.io/badge/SQL%20Server-2016%E2%80%932022-CC2927?style=flat-square&logo=microsoftsqlserver&logoColor=white" />
  <img alt="346 testes" src="https://img.shields.io/badge/testes-346-2ea44f?style=flat-square" />
  <img alt="Licença MIT" src="https://img.shields.io/badge/licen%C3%A7a-MIT-blue?style=flat-square" />
</p>

O **Vegapunk** é uma skill gratuita do [Claude Code](https://claude.com/claude-code) para quem trabalha com Microsoft
SQL Server, especialmente em sistemas que dão às tabelas nomes em código (`T000123` em vez de `FUNCIONARIOS`). Em vez
de o Claude adivinhar esses nomes, o Vegapunk consulta um mapa do **seu** banco, guardado só no seu computador, e
responde com o que existe de verdade.

<table>
  <tr>
    <td align="center" width="20%"><h3>0</h3><sub>linhas de dados lidas do seu banco: só a estrutura</sub></td>
    <td align="center" width="20%"><h3>3</h3><sub>consultas prontas ao catálogo, com <code>VIEW DEFINITION</code></sub></td>
    <td align="center" width="20%"><h3>100%</h3><sub>dos JOINs de chave composta entregues com prova, nos pedidos de teste</sub></td>
    <td align="center" width="20%"><h3>346</h3><sub>testes automatizados</sub></td>
    <td align="center" width="20%"><h3>0</h3><sub>dependências: Python e a biblioteca padrão</sub></td>
  </tr>
</table>

## Em 30 segundos

> **Você:** quero o salário dos colaboradores por cargo

O Vegapunk busca no mapa do seu banco, detalha as colunas e devolve o JOIN provado. O Claude escreve o SQL só com
esses nomes:

<img width="100%" alt="Saída real do Vegapunk no banco fictício dos testes. A busca encontra F_FUNCIONARIO e F_CARGO entre as tabelas críticas, o detalhar devolve as colunas e o JOIN provado pela FK, e o Claude escreve o SQL que soma a remuneração por cargo." src="assets/readme/demo.svg" />

<p align="center"><sub>Saída real da Stella (resumida) no "Sistema Aurora", o banco 100% fictício que vem nos testes. <a href="https://tiagocardosobezerra.github.io/vegapunk/#demo">Veja os quatro pedidos no site</a>, inclusive o que fica sem SQL por falta de prova.</sub></p>

## O que ele faz por você

* **Acha as tabelas certas.** Você descreve o que quer ("salário dos funcionários por seção") e ele encontra as tabelas e colunas que guardam esse dado, pela descrição de negócio de cada coluna.
* **Entrega o JOIN pronto, e só quando tem prova.** A ligação entre tabelas vem da constraint do banco, do dicionário do seu sistema ou da chave da tabela mãe, inclusive em chave composta. Sem prova, ele avisa em vez de chutar.
* **Escreve fórmulas de sistema sem inventar.** Cria, corrige, valida e explica fórmulas usando só funções e sintaxe documentadas. O que não tem suporte documentado aparece como lacuna, com o motivo.
* **Resolve pedidos com várias partes.** "Some as horas extras do mês e mostre de qual tabela vem": ele separa cada parte, resolve uma a uma e diz o que você ainda precisa preencher.
* **Nunca toca nos seus dados.** Do banco entra só a estrutura: nomes, descrições, tipos e ligações. Nenhuma linha de cadastro, nenhum valor.
* **Guarda os seus relatórios num Memory Card.** Como o cartão de memória de um videogame: cada relatório pronto vira um save no seu próprio repositório privado do GitHub, com artigo explicando o que faz, versão, motivo de cada mudança e conferência no schema quando a base muda.
* **Sabe T-SQL de verdade.** Otimização, planos de execução, índices, CTEs, window functions, PIVOT/MERGE/APPLY, transações e segurança, com conferência na documentação oficial da Microsoft quando o recurso depende da versão.

## JOIN só com prova

Uma ligação errada não dá erro: ela roda e devolve o número errado. Por isso o Vegapunk só entrega um JOIN quando
consegue mostrar de onde ele veio. Quando não consegue, não escreve o SQL e pergunta a você.

<img width="100%" alt="A regra da prova. Com prova: F_FUNCIONARIO e F_CARGO ligadas pela FK, JOIN entregue; a prova pode vir da constraint do banco, do dicionário do sistema ou da chave da tabela mãe. Sem prova: entre S_EXAME e S_CANDIDATO não existe caminho de FK, então nenhum JOIN é inventado." src="assets/readme/prova.svg" />

Nada de "acho que a tabela se chama FUNCIONARIO". Se o nome não veio do seu banco, ele não entra no SQL.

## Resultados

<img width="100%" alt="Resultados medidos com pedidos que o motor nunca tinha visto: pedidos com várias partes de 74% para 94%; com fórmula que executa consulta de 70% para 90%; JOINs de chave composta com prova de 0% para 100%; tabela certa entre as 3 primeiras num ERP real de 57% para 62%; função certa entre as 3 primeiras, 95% nas duas versões." src="assets/readme/resultados.svg" />

<details>
<summary><strong>Os números em tabela</strong></summary>

Medidos com pedidos que o motor nunca tinha visto, separados antes de qualquer ajuste.

| O quê | Versão anterior | Agora |
|---|---|---|
| Pedidos com várias partes (fórmula + tabela + cadastro) resolvidos | 74% | **94%** |
| Pedidos com fórmula que executa consulta resolvidos | 70% | **90%** |
| JOINs de chave composta entregues com prova | 0% | **100%** |
| Tabela certa entre as 3 primeiras, num ERP real | 57% | **62%** |
| Função certa entre as 3 primeiras, na busca de fórmulas | 95% | **95%** |

</details>

No seu banco, os números dependem principalmente da qualidade das descrições do seu dicionário.

## Comece em 3 passos

Você precisa de Python 3.8+ (só a biblioteca padrão, nada para instalar) e do `sqlcmd` ou do SSMS. Os comandos rodam **da pasta da skill**; no Windows, use `python` (ou `py`) no lugar de `python3`, se for o seu caso.

### 1. Instale

Para todos os projetos:

```bash
git clone https://github.com/tiagocardosobezerra/vegapunk.git ~/.claude/skills/vegapunk
```

```powershell
git clone https://github.com/tiagocardosobezerra/vegapunk.git $HOME\.claude\skills\vegapunk
```

Só para o projeto atual, troque o destino por `.claude/skills/vegapunk`.

### 2. Extraia a estrutura do seu banco

Três consultas prontas leem só o catálogo do SQL Server (`sys.*`), nunca uma tabela de negócio. Crie a pasta e rode, trocando `SERVIDOR` e `SEU_BANCO`:

```powershell
New-Item -ItemType Directory -Force egghead\extracao
```

```bash
sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000 -i punk_records\extracao\tabelas.sql -o egghead\extracao\tabelas.csv
sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000 -i punk_records\extracao\colunas.sql -o egghead\extracao\colunas.csv
sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000 -i punk_records\extracao\relacionamentos.sql -o egghead\extracao\relacionamentos.csv
```

`-E` usa a autenticação do Windows; com login SQL, use `-U usuario` (o `sqlcmd` pede a senha). No macOS/Linux, crie a pasta com `mkdir -p egghead/extracao` e use `/` nos caminhos. Prefere o SSMS? Cada `.sql` explica no cabeçalho como salvar o resultado em arquivo. O schema padrão é `dbo`; para outro, mude a variável `@esquema` no topo de cada consulta.

### 3. Importe e use

```bash
python3 satelites/york.py importar --dir egghead/extracao
python3 satelites/york.py migrar aplicar
python3 satelites/york.py enriquecer --dir egghead/extracao
```

Pronto. Peça qualquer coisa ao Claude sobre o seu banco, ou teste direto:

```bash
python3 stella.py status
python3 stella.py buscar --dominio schema "salário dos funcionários por seção"
python3 stella.py detalhar --dominio schema TABELA1 TABELA2
```

O import calcula sozinho as ligações, a relevância e o ranking de cada tabela, e avisa (sem travar) se alguma ligação apontar para tabela ou coluna que não existe. Tudo fica em `egghead/`, que o `.gitignore` já mantém fora do controle de versão.

## Para ir além

### Permissões no banco

As consultas do catálogo precisam só de `VIEW DEFINITION`. Elas leem nomes, tipos, chaves, descrições (`MS_Description`) e se cada tabela tem alguma linha, nunca quantas.

### Seu ERP tem um dicionário de dados próprio?

Muitos ERPs guardam, em tabelas próprias, a descrição de negócio de cada tabela e coluna e ligações que não existem como constraint. Use: a descrição é o que o motor casa com o seu pedido, e a busca fica muito melhor.

* **Permissão:** para ler o dicionário, é preciso `SELECT` nas tabelas dele. `VIEW DEFINITION` só basta para as consultas do catálogo.
* **Extração:** as consultas do dicionário dependem do ERP e não vêm aqui. Escreva as suas (só tabelas de metadados) e salve os CSVs, no formato abaixo, em `egghead/extracao/dicionario/`.
* **Import:** o dicionário dá as descrições e o catálogo completa a estrutura:

  ```bash
  python3 satelites/york.py importar --dir egghead/extracao/dicionario
  python3 satelites/york.py migrar aplicar
  python3 satelites/york.py enriquecer --dir egghead/extracao
  python3 satelites/york.py enriquecer --dicionario egghead/extracao/dicionario
  python3 satelites/york.py corrigir-direcao --dir egghead/extracao
  ```

  Exportou o dicionário de novo? `python3 satelites/york.py atualizar --dicionario egghead/extracao/dicionario --catalogo egghead/extracao` mostra o que muda; com `--aplicar`, grava.

<details>
<summary><strong>Formato dos CSVs</strong></summary>

UTF-8 ou UTF-16 (o padrão do SSMS), cabeçalho na primeira linha. `tabelas.csv` e `colunas.csv` são obrigatórios; os outros são opcionais.

| Arquivo | Colunas obrigatórias | Colunas opcionais | Observação | Consulta |
|---|---|---|---|---|
| `tabelas.csv` | `tabela` | `descricao`, `tem_dados` | Uma linha por tabela. Score, ranking e contagens são calculados pelo import. `tem_dados` diz só *se* a tabela tem linha, nunca quantas. | [![baixar tabelas.sql](https://img.shields.io/badge/baixar-tabelas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](punk_records/extracao/tabelas.sql) |
| `colunas.csv` | `tabela`, `coluna` | `descricao`, `tipo`, `tamanho`, `precisao`, `escala`, `nulo`, `ordem`, `pk_ordem` | Uma linha por coluna. A `descricao` de negócio é o que o motor casa com o pedido. | [![baixar colunas.sql](https://img.shields.io/badge/baixar-colunas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](punk_records/extracao/colunas.sql) |
| `relacionamentos.csv` | `tabela_filha`, `campo_filho`, `tabela_mae`, `campo_mae` | `constraint`, `ordem` | Uma linha por campo de FK; `constraint` agrupa os campos de uma chave composta. Também aceita uma linha por ligação, com os campos em lista na mesma ordem nas duas pontas (`"CODEMP,CODPAI"`). | [![baixar relacionamentos.sql](https://img.shields.io/badge/baixar-relacionamentos.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](punk_records/extracao/relacionamentos.sql) |
| `sistemas.csv` | `codigo_sistema`, `nome_sistema` | `descricao` | Uma linha por módulo; `codigo_sistema` é o prefixo de 1 letra das tabelas do módulo, quando o seu sistema segue esse padrão. | Vem do dicionário do ERP. |
| `sinonimos.csv` | `termo`, `sinonimo` | — | Uma linha por par ("colaborador" → "funcionário"). Cadeias funcionam. | Vocabulário definido por você. |

Detalhes de cada campo e de como o motor usa cada tabela: [`referencias/schema.md`](referencias/schema.md).

</details>

### Mais de um banco

Cada banco ganha a sua instância: `egghead/` é a padrão e cada outro vai em `egghead-<nome>/`, também fora do git. Importe com `--instancia <nome>` (o mesmo `york.py` de sempre) e descreva o banco num `instancia.json` (`descricao` e `assuntos`). Diante de um pedido, o Claude roda:

```bash
python3 stella.py instancias --pedido "crachás bloqueados no mês"
```

Ele mostra quantos termos do pedido cada base cobre (e quantos dão nome a tabela) e qual é a mais provável; num empate, pergunta. Um banco com vários schemas e nomes repetidos entre eles vira uma instância por schema. Todo comando da Stella e dos satélites aceita `--instancia <nome>`, os logs e as confirmações ficam na instância usada, e o Memory Card vale para todas. Passo a passo em [`COMO-INSTALAR.md`](COMO-INSTALAR.md).

### Fórmulas de sistema

O Vegapunk trabalha com pacotes de conhecimento em `punk_records/pacotes/`. Um pacote público traz o dialeto e os casos de teste; o texto da documentação é baixado e processado na sua máquina:

```bash
python3 satelites/york.py ingerir --pacote punk_records/pacotes/publico/<pacote>
```

`python3 stella.py status` lista os pacotes instalados. Regras e funções internas da sua empresa vão na camada privada (`punk_records/pacotes/privado/`, ignorada pelo git), a partir do modelo comentado em `punk_records/pacotes/modelo-privado/`. Detalhes em [`referencias/formulas.md`](referencias/formulas.md).

### Memory Card: seus relatórios salvos

Relatório pronto não precisa se perder numa pasta. O Memory Card salva cada um num repositório **seu** no GitHub (privado por padrão), organizado em solução (o Vegapunk ou outra ferramenta), categoria, seção e artigo:

```bash
gh auth login                                                         # uma vez
python3 stella.py cartao iniciar --repo SEU_USUARIO/memory-card  # cria o cartão privado
```

Depois é pedir ao Claude: "salve este relatório no Memory Card". Ele mostra a prévia (o artigo, a versão, o diff de uma mudança, a conferência das tabelas, colunas e JOINs no schema) e só envia com o seu "sim". Salvar também registra as tabelas do relatório no log de uso, o que alimenta a calibração da busca. Antes de escrever um relatório novo, ele procura no cartão se já existe algo parecido. Nada do seu cartão vem junto com o Vegapunk: qual é o cartão fica só na sua instância. Guia completo em [`referencias/memory-card.md`](referencias/memory-card.md).

## Como funciona por dentro

<img width="100%" alt="Por dentro do Vegapunk: a Stella é a porta de entrada; em volta giram Punk Records (a base local), Nomi Nomi no Mi (o motor de busca), York (a única porta de escrita), Shaka (fórmulas), Atlas e Pythagoras (os guardas), Edison e Lilith (calibração) e o Memory Card (seus relatórios)." src="assets/readme/equipe.svg" />

| Peça | O que faz |
|---|---|
| **Punk Records** | a base local com a estrutura do seu banco (`egghead/punk_records.db`) e os pacotes de conhecimento |
| **Nomi Nomi no Mi** | o motor de busca: casa o seu pedido com as descrições das colunas e pesa a importância de cada tabela pelas ligações |
| **Stella** | a porta de entrada (`stella.py`): buscar, detalhar, validar, compor, solucionar |
| **York** | a única porta de escrita: importar, migrar, enriquecer, ingerir documentação |
| **Shaka** | compõe, valida e explica fórmulas |
| **Atlas** e **Pythagoras** | os guardas: comportamento idêntico a cada mudança, qualidade medida e isolamento conferido |
| **Edison** e **Lilith** | sugerem sinônimos e geram casos sintéticos para calibrar |
| **Memory Card** | salva, versiona, busca e confere no schema os seus relatórios, num repositório seu |

Para conferir a instalação a qualquer momento:

```bash
python3 -m unittest discover -s testes
python3 satelites/atlas.py verificar
python3 satelites/atlas.py isolamento
```

## Estrutura do repositório

```
vegapunk/
├── SKILL.md               # O que o Claude lê: regras e caminhos
├── README.md              # Este arquivo
├── README.en.md           # README em inglês
├── COMO-INSTALAR.md       # Instalação e conferência
├── AVISO.md               # Aviso sobre dados de terceiros
├── LICENSE                # MIT License
├── stella.py              # Porta de entrada
├── satelites/             # York, Shaka, Atlas, Pythagoras, Edison, Lilith, Memory Card
├── nomi_nomi_no_mi/       # Motor de descoberta de schema
├── dominios/              # Schema, fórmulas e soluções
├── punk_records/          # Importação, migrações, consultas de extração e pacotes
├── referencias/           # Fluxos e guias de T-SQL
├── assets/                # Imagens animadas do README
├── docs/                  # Site do projeto (GitHub Pages)
├── casos/                 # Casos e dados fictícios de teste
└── testes/                # Suíte de testes
```

## Créditos

**Criador:** Tiago Cardoso Bezerra | [tiagocardosobezerra](https://github.com/tiagocardosobezerra)

Batizado em homenagem a Vegapunk, o engenheiro genial de One Piece, personagem reconhecido por dominar sistemas complexos e compartilhar conhecimento de forma clara e acessível.

## Agradecimentos

* Minha esposa **Júlia** e meus filhos **Arthur** e **Dante**, o porto seguro onde encontro paz, inspiração e a leveza de que preciso todos os dias.
* **Bruna Cardoso Bezerra** | [brunacbezerra](https://github.com/brunacbezerra), por me ensinar tudo o que sei sobre o Claude Code.
* **Hatem Mohamed** | [hmohamed01](https://github.com/hmohamed01), por compartilhar as boas práticas de T-SQL que aplico no Vegapunk.
* **Você**, por usar Vegapunk!

## Aviso sobre dados de terceiros

Este repositório traz só o motor: nenhum metadado de sistema real. Ao importar a estrutura do seu ambiente, você confirma que tem acesso legítimo ou licenciado a ele e se compromete a manter esses dados fora de repositórios públicos. Detalhes em [`AVISO.md`](AVISO.md).

## Licença

MIT License, veja [LICENSE](LICENSE) para detalhes.

---

<p align="center"><strong>Vegapunk</strong>, não adivinha. sabe.<br/><sub><a href="https://tiagocardosobezerra.github.io/vegapunk/">tiagocardosobezerra.github.io/vegapunk</a></sub></p>

```
                                                                 ░█▒▒▓▓▓▓█                          
                                                    █▓▓         ▓█▓▓▒▒▓▓▓░░                        
                                                 ▓▓▓▓▓▓▓▓       ▒▓██▓▓▒▒▒░            ░▒▓ ░░░      
                                          ░▒▓▒▒ ░▓▓▒▒▓▓░         ▒▓▓▓▒▒▒▓░            ░▒▓▓░▓▓      
                                        ░▓█▒▓▓░ ▓░▒▓▓▓▒          ░▓▓▓▓▒▓▓▓░        ▓▒▓ ▓▓▒░█▓░      
                                        ░██▓▓▒ ░▒▓▒░▒             ░▓█▓▒▓▒▓▓        ░▒█▓░█▓▓░█▒      
                                        ░▓█▓▓▒░░░░▒▒▒▒▒▒▒▒▒░      ░▒░░▒░░▓▓       ░█░▓▓▒░▓▒░█▓      
                                         ░▓░▒▒░░░▒▒▒▒▒▒▒▒▒▒▒░        ▒░░          ░░▒▓▒▓█▓█░█▓  ░▓▒▓
                                          ░▒░░░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒       ▒░░             ░▒▓▓░▓██▓▒▓█▓▒
                                  ░░░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░░      ░░░             ░░░░░▓█████▓▓  
                                ░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░░▓▓▓▓█▓▓      ░░░           ░▒██████░▒▓▒    
                              ░▒▒▓▓█▓▓▒▒▒▒▒▒▒▒▒▒░░▓▓▓▒░ ░░▒▓▒        ░░░           ██████████      
                             ░▒▒████▓▒▒▒▒▒▒▒▒▒▓▓▓░  ░░░▒▓░           ▒░░           ███▓▓████░      
                            ░░▒▒▓▓▓▒▒▒▒▒▒▒▓▓▓▒░░░░░░▒▒░              ▒▒░          ▓███████▓▓        
                           ░▒▒▒▒▒▒█▓▒▒▒▓█▓▒ ░░▒▒▒░▒                 ░▒▒▒▓        ░▒░█████▓▓        
                           ░░▒▒▒▒▒▒▒▒▓▓░░░░░░▒░▒▒▒░░▓▓▓▓▓▓▓▒▓░     ▒▒▓█▒░         ░░█████▓          
                           ░░▒▒▒▒▒▓▓▒░░░░░▓  ▓▒▒▓▓▒█▓▓█▒▓▓▒▓▓▓▓▒▒▓▒██▓▒▒░░ ░█▓     ░████▓          
                            ░▒▒▒▒▓▓▒▒▒▒░  ░░▒▒▒▓█▓▓▒▓█▓▓████▓▒▓▓▒████▓▓▓▒▒██▒▒     ▓████            
                             ░░▒▒▒░░     ▒▓▓▒▒▓▒▓▒▒█▓▓█▓▓██████▓▒▒██▓██▒░████     ░████░            
                                        ▓▒▒▒▒▓▓█▓▒▓▓▒▓▒▒▓▓▓▓▓█▓▓▓░▓▓▓▓████▒░ ▒▒░  ▓███▓            
                                      ▓██▓▓▒▓███▒▒▓██▓▓▓▓██▓▒▓▓▒▓▓███▓▒▓████▓▒▒  ░███▒              
                                     ▓▓█▓▓░████▓▓▓▒▒▓▓▓█████████▒▓▒██████▓▒░▓    ████              
                                   ▓▓▓█▒▓▓▓█░▒▒▓█▓██████████████▓▒░███▓██▒█████▓▓███░              
                             ░▓█░████▓█▓▓████▓▓██████▓███████████▒▒████▓██▓██▓▒▓███░                
                               █░▒░░▓██▒▓▒█░▒████████▓▒▓█████████▒▓██████▓█░▒▒░▓██▓                
                                ░███▓███▓█░▓██████████▓▓██████████▓████▓░░░▒▓▒▓▓▒▓▓                
                             ░▓█████▒▓████▓█████████████▓███████▒▓▓██░▓▓█░██▓▒██▒▓█░                
                                ░██████████▒█████████████▓██▒▓▓█▒▓▓██▓▓█████▒████░▓██              
                           ▓░▓██▒▓▒▒████████▒███████████▒▓▓█▓▓▒▓▓▓▓▓▓░▒██▒██████▓▒████░            
                            ░▒▓███▓▒▓▓█▓░███████████▓▓▓██▒░▓▓██▓▓▒▓▓▒▓▓█████▓█████░████            
                                ▒████████░█▒█████▓██▒█████▓▒▒████▓▓█▓░░▓████████▒▓█▒███░            
                               ░██▓███▒▒████▓▒▓▓█▓▓▓▓▓▓█▓█▓▒▒▒▒▓▓▓▓░▓▓▒░░█████████▒▓████            
                               ░▓▓█▓▒▒▓▒████▒▓▓▓▒█▒▒███▒▓▓▓████▒▒▓▓▒▒█▓▒▒▒███▓██▒███████▓          
                               ▒▒█████▓▒▒████▓▒▒▒▒█████▓▒▓████▓███▓▓██▓▓▒▒▓▓███████████▓░          
                              ░█████▓▓▓▓█▒▓█▓▒▒▒▒▒▓▓▓▓▓▓▓▒▒▓▓████▒██▒█▒▓▓▓▓░▓▓▒▒▓▓██████▒          
                              ░████▓▒▒▓█▓▓██▓███░▒▓█▒▒▓▓██████▓▓▒▒░░░▓▒░▒▒▒▒▒███████████            
     ░▒▒           ▓▓         ░█████████████████▒▒▓█▓█▓█████▓▒░░░░░░░███▓▓░░░▒▓▓███▓▓██▓            
      ▓▓▒      █████▒▒         ▓▓██████████▓████▓▒▒█▓▒▓▓██▒▒░▒▒▒▒▒▒▒░███▓▓▒▒▓░▒▓▓▓▓███▓            
▒▒▒▒▒░ ░▒▓░   ▓█████▒▒░░▒██▓▓██████████████▒████▓░▒▓▓███▒▒░ ░▒▒▒▒▒▒▒▒▓██▓▓▒░░░░▓▓▓██▓█▒            
 ▒▒▒▓▓█▓░██▓▓▒█▒█▓█▓████████████▒▓▓▓▓▓▒▓█▓▓▓█▒▓█▒░░░█▓▓▒██▒▓░▒▓▓▒▓▓▓▓▓██▒▒░░░░   ▓░██▒░            
▒▒▓██▓▒▒██▓▓█▓▓█▓█▓████▓▒▓██▒░░ ▓▓▓▓▓▓▒▓█████▓████▒█▓▒▓▒▒██▓▒▓▓▓▒▓▓▓▓▒▒▓▓▒░░▒       ▒░              
  ░░▒▓█▓▓▓▓▓▓█████▒█▒░           ░▒▒▒▓████▓▓█████▓█▒░▓▓██████▓▓▓▓▓▓▓▓▓▒▒▒▒░░                        
    ▒▒██▓▓█▓▒▒▓▓▒                 ░▒▒▓▓█████████▓██▒▓▒░▒▓▓▓█▓▒▓▓▓▓▓▓▓▓▓▒░▓▓                        
▒▒▒▓▓▒▓▓▓▒▒█▓▒                     ▒▒▓██████████▓▓█░▒▓▒▒▓░▓▓▒▓▓▓▓▓▓▓▓▓▓░░░                          
 ▒░░     ▒▒█▓                        ░░███████████▓▓▒▒▒▒▓▒▒░▓▓▓▓▓▓▓▓▓▓▓▒░                          
        ▒▒▓▒                          ▒▒▒░███████▒█░░░░░░░░▓▓▓▓▓▒▓▓▓█▓▓▒░                          
        ░░░                         ▒▒▒▒  ░▒███▓▓█▒     ░▓▓▓▓▓▓▓▓▓▓▓█▓▓▒░                          
                                   ░░▒▓    ▒▓███▒▒     ░▓▓▓▓▓▓▓▒▓▓▓▓▓▓▓▒                            
                               ░▒▒░▒░        █▓▓▓     ░▓▓▓▓▓▓▓▒▓▓▓▓▓▓▓▒░                            
                              ▓▓▒░▒░                  ▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒                            
                             ░▒▓░▒░                   ▓▓██▓▓▓▓▓▓▓▓▓▓▓▒░                            
                            ░▒▒▒█▒▒▒                  ▓▓██▓▓▓▓▓▓▓▓▓▒▒░                              
                           ░▒▒▓▓▓▒                    ░▓▓▓▓▓▓▓▓▓▓▓▒░                                
                           ▒▓▓▒▒▒▒                     ▒▒▓▓▓▓▓▓▒▒░                                  
                           █▒▒▒▒░                       ░░░░░░░░
```
