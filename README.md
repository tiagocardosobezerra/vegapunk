# Vegapunk
 
**Não adivinha. Sabe.**
 
Uma skill do Claude Code para desenvolvimento em Microsoft SQL Server, com um motor de descoberta de schema por linguagem natural plugável em **qualquer** banco de dados nomeado por código (ERPs com tabelas no padrão prefixo de letra + nome). Peça, e receba o T-SQL certo.
 
> 📦 Esta é a edição **community**: o motor e a estrutura são genéricos e não vêm com nenhum schema pré-carregado. Você importa os metadados do **seu próprio** ambiente (ao qual já precisa ter acesso legítimo) antes de usar — ver [Instalação](#instalação) e [Importando seus dados](#importando-seus-dados-obrigatório) abaixo.
 
<img width="100%" alt="produtividade-vegapunk_3" src="https://github.com/user-attachments/assets/5a00b2d7-a25f-479d-aecd-31862ca2f0dc" />
 
## Visão Geral
 
Vegapunk não adivinha nomes de tabela e coluna de um ERP com nomenclatura em código — sabe. Em vez de o Claude tatear até acertar, a skill consulta uma base de metadados local (**Punk Records**) através do motor **Nomi Nomi no Mi**, que você mesmo popula a partir do seu ambiente.
 
### Antes vs. depois
 
| | Sem descoberta de database schema | Com Vegapunk |
|---|---|---|
| 1 | Adivinhar a tabela | Perguntar, em português |
| 2 | Relacionamento errado | Receber tabela e colunas certas |
| 3 | Consulta quebrada | Escrever o SQL de primeira |
| 4 | Corrigir e repetir | — |
| **Resultado** | **~20–30 min perdidos** | **~2–3 min** |
 
## Recursos
 
* **Descoberta de Schema por Linguagem Natural** — busca automatizada de tabelas e colunas a partir de um pedido em português, via motor Nomi Nomi no Mi. Retorna relacionamentos de chave estrangeira pré-formatados para construção de JOINs, eliminando adivinhação de nomenclatura.
* **Comando de importação embutido** — leia 5 CSVs (ver abaixo) e o motor calcula sozinho os campos derivados (contagem de relacionamentos, score de relevância, ranking); você não precisa calcular nada na mão.
* **Verificação de Documentação ao Vivo** — valida sintaxe T-SQL contra documentação oficial Microsoft usando WebFetch com fallback WebSearch para recursos específicos de versão (SQL Server 2016–2022).
* **Fluxos de Trabalho Estruturados** — guias para desenvolvimento de queries, otimização de procedures e gerenciamento de transações, com padrões de tratamento de erros.
* **Detecção de Anti-Padrões de Performance** — identifica predicados não-SARGable, conversões implícitas, índices faltantes e ineficiências em planos de execução.
* **Boas Práticas de Segurança** — prevenção de SQL injection, queries parametrizadas, segurança de SQL dinâmico e gerenciamento de permissões.
* **Referências Abrangentes** — cinco documentos de referência cobrindo padrões de query, otimização de performance, segurança, tipos de dados e transações.
* **Suíte de testes de regressão** — valida, com uma fixture fictícia autogerada, que mudanças no motor não pioram casos que já funcionavam.
## Instalação
 
Clone este repositório e copie a pasta `skills/vegapunk-community` para seu diretório de skills:
 
### Nível de usuário (todos os projetos)
 
macOS/Linux:
```bash
cp -r skills/vegapunk-community ~/.claude/skills/
```
 
Windows (PowerShell):
```powershell
Copy-Item -Recurse skills/vegapunk-community $HOME\.claude\skills\
```
 
### Nível de projeto (projeto atual apenas)
 
macOS/Linux:
```bash
cp -r skills/vegapunk-community .claude/skills/
```
 
Windows (PowerShell):
```powershell
Copy-Item -Recurse skills/vegapunk-community .claude\skills\
```
 
> Se você já tiver uma skill privada chamada apenas `vegapunk`, esta convive tranquilamente ao lado — o identificador é `vegapunk-community`, escolhido de propósito para não colidir.
 
## Importando seus dados (obrigatório)
 
O `punk_records.db` publicado neste repositório vem **vazio**. Para a skill funcionar, é **obrigatório** importar as 5 tabelas de metadados — **Tabelas**, **Colunas**, **Relacionamentos**, **Sistemas** e **Sinônimos** — a partir do seu próprio ambiente.
 
### Passo a passo
 
1. **Extraia os metadados do seu ambiente.** Você precisa já ter acesso legítimo/licenciado a ele. Rode consultas de introspecção contra o dicionário de dados e o catálogo de relacionamentos do seu sistema (nunca contra dados de negócio/cliente) para obter: lista de tabelas, colunas com descrição de negócio, relacionamentos (FKs), módulos/sistemas e um dicionário de sinônimos coloquial → vocabulário do schema.
2. **Exporte cada conjunto para um CSV**, no formato abaixo, dentro de uma pasta (ex.: `./meus_csvs/`).
3. **Rode o importador:**
```bash
   python3 skills/vegapunk-community/scripts/nomi_nomi_no_mi.py importar --dir ./meus_csvs/
```
   O comando cria/recalcula tudo sozinho — contagem de relacionamentos por tabela, score de relevância e ranking — a partir só do que está nos CSVs. Se `contextos/punk_records.db` já existir, use `--forcar` para sobrescrever.
4. **Teste:**
```bash
   python3 skills/vegapunk-community/scripts/nomi_nomi_no_mi.py buscar "seu pedido em português aqui"
```
5. **Mantenha o banco importado fora do controle de versão.** Depois de importar, `contextos/punk_records.db` passa a conter metadados do seu sistema — adicione-o ao `.gitignore` do seu projeto e nunca faça commit/push dele para um repositório público.
### Formato dos 5 CSVs
 
| Arquivo | Colunas obrigatórias | Colunas opcionais | Observação |
|---|---|---|---|
| `tabelas.csv` | `tabela` | `total_registros`, `descricao` | Uma linha por tabela. Não inclua score/ranking/contagens — são calculados pelo import. |
| `colunas.csv` | `tabela`, `coluna` | `descricao` | Uma linha por coluna. A `descricao` (negócio, em PT-BR) é o que o motor usa pra casar com o pedido do usuário. |
| `relacionamentos.csv` | `tabela_filha`, `campo_filho`, `tabela_mae`, `campo_mae` | — | Uma linha por FK; chave composta = uma linha por campo. |
| `sistemas.csv` | `codsistema`, `nomesistema` | `descricao` | Uma linha por módulo. `codsistema` deve bater com o prefixo de 1 letra das tabelas desse módulo. |
| `sinonimos.csv` | `termo`, `sinonimo` | — | Uma linha por par (um termo com 3 sinônimos = 3 linhas). Cadeias funcionam. |
 
Documentação completa, com exemplos de cada CSV e a explicação de como o motor usa cada tabela, em [`skills/vegapunk-community/contextos/README.md`](skills/vegapunk-community/contextos/README.md).
 
## Estrutura do Repositório
 
```
vegapunk-community/
├── README.md                        # Este arquivo
└── skills/
    └── vegapunk-community/
        ├── SKILL.md                 # Definição principal e fluxos de trabalho
        ├── contextos/
        │   ├── punk_records.db      # Base de metadados (SQLite) — vazia até você importar
        │   └── README.md            # Arquitetura do motor, formato de import, limitações
        ├── referencias/
        │   ├── patterns.md          # Padrões de query: CTEs, paginação, PIVOT, MERGE, window functions
        │   ├── performance.md       # Planos de execução, indexação, estatísticas de espera
        │   ├── security.md         # Prevenção SQL injection, SQL dinâmico, permissões
        │   ├── data-types.md       # Seleção de tipos, collation, otimização de armazenamento
        │   └── transactions.md     # Níveis de isolamento, deadlocks, transações distribuídas
        └── scripts/
            ├── nomi_nomi_no_mi.py       # Motor de descoberta de schema + comando `importar`
            └── testes_regressao.py     # Suíte de testes (gera fixture fictícia própria)
```
 
## Uso
 
Uma vez instalada e com os dados importados, o Claude Code invocará automaticamente esta skill quando você perguntar sobre:
 
* Escrita ou otimização de queries T-SQL
* Descoberta de tabelas/colunas do seu schema importado
* Procedures SQL Server e planos de execução
* Otimização de performance de banco de dados e indexação
* Segurança SQL e prevenção de injection
* Gerenciamento de transações e tratamento de erros
### Fluxo de Descoberta de Schema
 
Ao trabalhar com uma base cadastrada (depois de importada), a skill usa o motor Nomi Nomi no Mi:
 
1. **Buscar Tabelas** — identifica tabelas relevantes por domínio de negócio, a partir de um pedido em português.
2. **Detalhar Tabelas** — recupera colunas, descrições e relacionamentos de chave estrangeira.
3. **Escrever Query** — compõe T-SQL usando exclusivamente os nomes de schema descobertos (nunca por suposição).
Exemplo (nomes ilustrativos — os reais dependem do que você importou):
```bash
python3 scripts/nomi_nomi_no_mi.py buscar "colaboradores com dados de folha de pagamento"
python3 scripts/nomi_nomi_no_mi.py detalhar FCOLABORADOR FDADOSFOLHA
```
 
## Suporte a Versões SQL Server
 
Vegapunk cobre recursos de SQL Server 2016 até 2022, com anotações de versão quando aplicável.
 
## Créditos
 
**Criador:** Tiago Cardoso Bezerra
**E-mail:** tiagocardosobezerra@gmail.com
**GitHub:** [@tiagocardosobezerra](https://github.com/tiagocardosobezerra)
 
Nomeado em homenagem a Vegapunk, o engenheiro gênio de *One Piece* — personagem definido pelo domínio de sistemas complexos e destilação de conhecimento.
 
## Agradecimentos
 
* **Bruna Cardoso Bezerra**, por me ensinar tudo o que sei sobre o Claude Code.
* **Hatem Mohamed** | https://github.com/hmohamed01, por compartilhar as boas práticas de T-SQL que aplico no Vegapunk.
* **Você**, por usar Vegapunk!

## Aviso sobre dados de terceiros
 
Este repositório **não contém e nunca vai conter** metadados de schema de nenhum sistema real. O que é distribuído aqui é só o motor (código genérico) e um banco de metadados **vazio**. Ao importar dados do seu próprio ambiente, você confirma que já tem acesso legítimo/licenciado a ele, e a responsabilidade por manter esses dados fora de repositórios públicos é sua. Detalhes completos em [`skills/vegapunk-community/AVISO.md`](skills/vegapunk-community/AVISO.md).
 
## Licença
 
MIT License — veja [LICENSE](LICENSE) para detalhes.
 
---
 
<p align="center"><strong>Vegapunk</strong>, não adivinha. sabe.</p>
 
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
