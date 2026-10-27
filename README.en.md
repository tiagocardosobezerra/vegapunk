# Vegapunk

[Português](README.md) | **English**

**Ask in plain language. Get the right T-SQL, with the real tables, columns and JOINs from your database.**

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![No dependencies](https://img.shields.io/badge/dependencies-none-2ea44f?style=flat-square)
![SQL Server 2016–2022](https://img.shields.io/badge/SQL%20Server-2016%E2%80%932022-CC2927?style=flat-square&logo=microsoftsqlserver&logoColor=white)
![MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

<img width="100%" alt="Vegapunk: SQL with real names and formulas with nothing made up" src="assets/vegapunk-banner-en.svg" />

Vegapunk is a Claude Code skill for people who work with Microsoft SQL Server, especially on systems that give tables coded names (`T000123` instead of `EMPLOYEES`). Instead of letting Claude guess those names, Vegapunk looks them up in a map of **your** database, kept only on your computer, and answers with what actually exists.

> **Language note:** Vegapunk was built and measured on Portuguese-language requests and data dictionaries. Commands, file names and CSV column names are in Portuguese and are shown here exactly as you type them.

## What it does for you

* **Finds the right tables.** You describe what you want ("employee salary by section") and it finds the tables and columns that hold that data, using the business description of each column.
* **Hands you the JOIN, and only when it has proof.** The link between tables comes from a database constraint, from your system's data dictionary or from the parent table's key, composite keys included. Without proof, it warns you instead of guessing.
* **Writes system formulas without making things up.** It creates, fixes, validates and explains formulas using only documented functions and syntax. Anything without documented support shows up as a gap, with the reason.
* **Solves requests with several parts.** "Add up this month's overtime hours and show me which table it comes from": it splits each part, solves them one by one and tells you what you still need to fill in.
* **Never touches your data.** Only the structure comes in from the database: names, descriptions, types and links. No business rows, no values.
* **Keeps your reports on a Memory Card.** Like a video game memory card: each finished report becomes a save in your own private GitHub repository, with an article explaining what it does, a version, the reason for each change, and a schema check when the database changes.
* **Knows T-SQL for real.** Tuning, execution plans, indexes, CTEs, window functions, PIVOT/MERGE/APPLY, transactions and security, checked against Microsoft's official documentation when a feature depends on the version.

## What it looks like

> **You:** I want the list of active employees with the name of each one's section
>
> **Claude (with Vegapunk):** searches the tables, details the columns and returns the query with your database's names, the JOIN proven by the composite key, and a warning if any filter depends on a code you need to provide.

No "I think the table is called EMPLOYEE". If a name did not come from your database, it does not go into the SQL.

## Results

Measured on requests the engine had never seen, set aside before any tuning.

| What | Previous version | Now |
|---|---|---|
| Multi-part requests (formula + table + record) solved | 74% | **94%** |
| Requests with a formula that runs a query solved | 70% | **90%** |
| Composite-key JOINs delivered with proof | 0% | **100%** |
| Right table in the top 3, on a real ERP | 57% | **62%** |
| Right function in the top 3, in formula search | 95% | **95%** |

On your database, the numbers depend mostly on the quality of the descriptions in your dictionary.

## Get started in 3 steps

You need Python 3.8+ (standard library only, nothing to install) and `sqlcmd` or SSMS. Run the commands **from the skill folder**; on Windows, use `python` (or `py`) instead of `python3` if that is your setup.

### 1. Install

For all projects:

```bash
git clone https://github.com/tiagocardosobezerra/vegapunk.git ~/.claude/skills/vegapunk
```

```powershell
git clone https://github.com/tiagocardosobezerra/vegapunk.git $HOME\.claude\skills\vegapunk
```

For the current project only, change the destination to `.claude/skills/vegapunk`.

### 2. Extract your database structure

Three ready-made queries read only the SQL Server catalog (`sys.*`), never a business table. Create the folder and run them, replacing `SERVIDOR` (server) and `SEU_BANCO` (your database):

```powershell
New-Item -ItemType Directory -Force egghead\extracao
```

```bash
sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000 -i punk_records\extracao\tabelas.sql -o egghead\extracao\tabelas.csv
sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000 -i punk_records\extracao\colunas.sql -o egghead\extracao\colunas.csv
sqlcmd -S SERVIDOR -d SEU_BANCO -E -f 65001 -h -1 -y 8000 -i punk_records\extracao\relacionamentos.sql -o egghead\extracao\relacionamentos.csv
```

`-E` uses Windows authentication; with a SQL login, use `-U user` (`sqlcmd` prompts for the password). On macOS/Linux, create the folder with `mkdir -p egghead/extracao` and use `/` in the paths. Prefer SSMS? Each `.sql` file explains in its header how to save the result to a file. The default schema is `dbo`; for another one, change the `@esquema` variable at the top of each query.

### 3. Import and use

```bash
python3 satelites/york.py importar --dir egghead/extracao
python3 satelites/york.py migrar aplicar
python3 satelites/york.py enriquecer --dir egghead/extracao
```

Done. Ask Claude anything about your database, or try it directly:

```bash
python3 stella.py status
python3 stella.py buscar --dominio schema "salário dos funcionários por seção"
python3 stella.py detalhar --dominio schema TABELA1 TABELA2
```

The import works out the links, the relevance and the ranking of each table on its own, and warns you (without stopping) if any link points to a table or column that does not exist. Everything stays in `egghead/`, which `.gitignore` already keeps out of version control.

## Going further

### Database permissions

The catalog queries need only `VIEW DEFINITION`. They read names, types, keys, descriptions (`MS_Description`) and whether each table has any row, never how many.

### Does your ERP have its own data dictionary?

Many ERPs keep, in their own tables, the business description of each table and column and links that do not exist as constraints. Use it: the description is what the engine matches against your request, and search gets much better.

* **Permission:** to read the dictionary, you need `SELECT` on its tables. `VIEW DEFINITION` is enough only for the catalog queries.
* **Extraction:** dictionary queries depend on the ERP and are not included here. Write your own (metadata tables only) and save the CSVs, in the format below, to `egghead/extracao/dicionario/`.
* **Import:** the dictionary provides the descriptions and the catalog completes the structure:

  ```bash
  python3 satelites/york.py importar --dir egghead/extracao/dicionario
  python3 satelites/york.py migrar aplicar
  python3 satelites/york.py enriquecer --dir egghead/extracao
  python3 satelites/york.py enriquecer --dicionario egghead/extracao/dicionario
  python3 satelites/york.py corrigir-direcao --dir egghead/extracao
  ```

  Exported the dictionary again? `python3 satelites/york.py atualizar --dicionario egghead/extracao/dicionario --catalogo egghead/extracao` shows what changes; with `--aplicar`, it writes the changes.

<details>
<summary><strong>CSV format</strong></summary>

UTF-8 or UTF-16 (the SSMS default), header on the first line. `tabelas.csv` and `colunas.csv` are required; the others are optional.

| File | Required columns | Optional columns | Notes | Query |
|---|---|---|---|---|
| `tabelas.csv` | `tabela` | `descricao`, `tem_dados` | One row per table. Score, ranking and counts are calculated by the import. `tem_dados` says only *whether* the table has a row, never how many. | [![download tabelas.sql](https://img.shields.io/badge/download-tabelas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](punk_records/extracao/tabelas.sql) |
| `colunas.csv` | `tabela`, `coluna` | `descricao`, `tipo`, `tamanho`, `precisao`, `escala`, `nulo`, `ordem`, `pk_ordem` | One row per column. The business `descricao` is what the engine matches against the request. | [![download colunas.sql](https://img.shields.io/badge/download-colunas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](punk_records/extracao/colunas.sql) |
| `relacionamentos.csv` | `tabela_filha`, `campo_filho`, `tabela_mae`, `campo_mae` | `constraint`, `ordem` | One row per FK field; `constraint` groups the fields of a composite key. Also accepts one row per link, with the fields listed in the same order on both ends (`"CODEMP,CODPAI"`). | [![download relacionamentos.sql](https://img.shields.io/badge/download-relacionamentos.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](punk_records/extracao/relacionamentos.sql) |
| `sistemas.csv` | `codigo_sistema`, `nome_sistema` | `descricao` | One row per module; `codigo_sistema` is the 1-letter prefix of the module's tables, when your system follows that pattern. | Comes from the ERP dictionary. |
| `sinonimos.csv` | `termo`, `sinonimo` | — | One row per pair ("colaborador" → "funcionário"). Chains work. | Vocabulary you define. |

Details on each field and on how the engine uses each table: [`referencias/schema.md`](referencias/schema.md) (in Portuguese).

</details>

### System formulas

Vegapunk works with knowledge packs in `punk_records/pacotes/`. A public pack brings the dialect and the test cases; the documentation text is downloaded and processed on your machine:

```bash
python3 satelites/york.py ingerir --pacote punk_records/pacotes/publico/<pack>
```

`python3 stella.py status` lists the installed packs. Your company's internal rules and functions go in the private layer (`punk_records/pacotes/privado/`, ignored by git), starting from the commented template in `punk_records/pacotes/modelo-privado/`. Details in [`referencias/formulas.md`](referencias/formulas.md) (in Portuguese).

### Memory Card: your saved reports

A finished report should not get lost in a folder. The Memory Card saves each one in a GitHub repository of **your own** (private by default), organized by category, section and article:

```bash
gh auth login                                                         # once
python3 satelites/memory_card.py iniciar --repo YOUR_USER/memory-card    # creates the private card
```

Then just ask Claude: "save this report to the Memory Card". It shows a preview (the article, the version, the diff of a change, the check of tables and columns against the schema) and only sends it after your "yes". Before writing a new report, it searches the card for something similar. Nothing from your card ships with Vegapunk: which card is yours lives only in your instance. Full guide (in Portuguese) in [`referencias/memory-card.md`](referencias/memory-card.md).

## How it works inside

<img width="100%" alt="How Vegapunk finds the right tables and functions" src="assets/vegapunk-sonar-en.svg" />

| Piece | What it does |
|---|---|
| **Punk Records** | the local base with your database structure (`egghead/punk_records.db`) and the knowledge packs |
| **Nomi Nomi no Mi** | the search engine: matches your request against column descriptions and weighs each table's importance by its links |
| **Stella** | the front door (`stella.py`): search, detail, validate, compose, solve |
| **York** | the only write path: import, migrate, enrich, ingest documentation |
| **Shaka** | composes, validates and explains formulas |
| **Atlas** and **Pythagoras** | the guards: identical behavior on every change, measured quality and checked isolation |
| **Edison** and **Lilith** | suggest synonyms and generate synthetic cases for calibration |
| **Memory Card** | saves, versions, searches and checks your reports against the schema, in a repository of your own |

To check the installation at any time:

```bash
python3 -m unittest discover -s testes
python3 satelites/atlas.py verificar
python3 satelites/atlas.py isolamento
```

## Repository layout

```
vegapunk/
├── SKILL.md               # What Claude reads: rules and paths
├── README.md              # Portuguese README
├── README.en.md           # This file
├── COMO-INSTALAR.md       # Installation and checks
├── AVISO.md               # Notice about third-party data
├── LICENSE                # MIT License
├── stella.py              # Front door
├── satelites/             # York, Shaka, Atlas, Pythagoras, Edison, Lilith, Memory Card
├── nomi_nomi_no_mi/       # Schema discovery engine
├── dominios/              # Schema, formulas and solutions
├── punk_records/          # Import, migrations, extraction queries and packs
├── referencias/           # Flows and T-SQL guides
├── assets/                # README banners
├── casos/                 # Fictitious test cases and data
└── testes/                # Test suite
```

## Credits

**Creator:** Tiago Cardoso Bezerra | [tiagocardosobezerra](https://github.com/tiagocardosobezerra)

Named after Vegapunk, the genius engineer from One Piece, a character known for mastering complex systems and sharing knowledge in a clear, accessible way.

## Acknowledgments

* My wife **Júlia** and my children **Arthur** and **Aurora**, the safe harbor where I find peace, inspiration and the lightness I need every day.
* **Bruna Cardoso Bezerra** | [brunacbezerra](https://github.com/brunacbezerra), for teaching me everything I know about Claude Code.
* **Hatem Mohamed** | [hmohamed01](https://github.com/hmohamed01), for sharing the T-SQL best practices I apply in Vegapunk.
* **You**, for using Vegapunk!

## Notice about third-party data

This repository ships only the engine: no metadata from any real system. By importing the structure of your environment, you confirm that you have legitimate or licensed access to it and you commit to keeping that data out of public repositories. Details in [`AVISO.md`](AVISO.md) (in Portuguese).

## License

MIT License, see [LICENSE](LICENSE) for details.

---

<p align="center"><strong>Vegapunk</strong> doesn't guess. It knows.</p>

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
