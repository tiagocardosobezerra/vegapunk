# Vegapunk
 
**Não adivinha. Sabe.**
 
## Visão geral
 
O Vegapunk é uma skill do Claude Code para desenvolvimento em T-SQL no Microsoft SQL Server. O diferencial dela é um motor de descoberta de schema por linguagem natural, plugável em qualquer banco de dados: você pergunta em português e recebe a query certa, já com os nomes reais de tabela e coluna do seu ambiente.
 
Em vez de o Claude tentar adivinhar como um ERP nomeou as próprias tabelas, o Vegapunk consulta uma base de metadados local chamada **Punk Records**, através de um motor chamado **Nomi Nomi no Mi**. Essa base é populada por você, a partir do seu próprio ambiente.
 
## Antes vs. depois
 
<img width="100%" height="842" alt="vegapunk-poster" src="https://github.com/user-attachments/assets/d95619a4-0e70-47d7-9db4-6d35e1f4bbb7" />
 
## Recursos
 
* **Descoberta de schema por linguagem natural.** Você descreve o que precisa em português e o motor Nomi Nomi no Mi busca as tabelas e colunas correspondentes, já trazendo os relacionamentos de chave estrangeira prontos para montar os JOINs. Isso elimina boa parte da adivinhação de nomenclatura.
* **Comando de importação embutido.** Basta exportar 5 CSVs do seu ambiente (formato abaixo); o motor calcula sozinho os campos derivados, como contagem de relacionamentos, score de relevância e ranking. Você não precisa calcular nada na mão.
* **Verificação de documentação ao vivo.** A skill valida a sintaxe T-SQL contra a documentação oficial da Microsoft usando WebFetch, com fallback para WebSearch quando o recurso é específico de versão (SQL Server 2016 a 2022).
* **Fluxos de trabalho estruturados.** Guias para desenvolvimento de queries, otimização de procedures e gerenciamento de transações, com padrões de tratamento de erro já definidos.
* **Detecção de anti-padrões de performance.** Identifica predicados não SARGable, conversões implícitas, índices faltando e outras ineficiências no plano de execução.
* **Boas práticas de segurança.** Prevenção de SQL injection, queries parametrizadas, cuidado com SQL dinâmico e gerenciamento de permissões.
* **Referências abrangentes.** Cinco documentos cobrindo padrões de query, otimização de performance, segurança, tipos de dados e transações.
* **Suíte de testes de regressão.** Gera sozinha uma fixture fictícia e valida que mudanças no motor não pioram casos que já funcionavam.
## Instalação
 
Clone este repositório e copie a pasta `skills/vegapunk-community` para o seu diretório de skills.
 
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
 
> Se você já tiver uma skill privada chamada só `vegapunk`, pode instalar esta tranquilamente ao lado dela. O identificador aqui é `vegapunk-community`, escolhido de propósito para não colidir.
 
## Importando seus dados (obrigatório)
 
O `punk_records.db` publicado neste repositório vem **vazio**. Para a skill funcionar, é **obrigatório** importar as 5 tabelas de metadados (**Tabelas**, **Colunas**, **Relacionamentos**, **Sistemas** e **Sinônimos**) a partir do seu próprio ambiente.
 
### Passo a passo
 
1. **Extraia os metadados do seu ambiente.** Você precisa já ter acesso legítimo ou licenciado a ele. Rode consultas de introspecção contra o dicionário de dados e o catálogo de relacionamentos do seu sistema (nunca contra dados de negócio ou de cliente) para obter: lista de tabelas, colunas com descrição de negócio, relacionamentos (chaves estrangeiras), módulos/sistemas e, se fizer sentido, um dicionário de sinônimos (vocabulário coloquial → vocabulário do schema).
2. **Exporte cada conjunto para um CSV**, no formato abaixo, dentro de uma pasta (por exemplo, `./meus_csvs/`).
3. **Rode o importador:**
```bash
   python3 skills/vegapunk-community/scripts/nomi_nomi_no_mi.py importar --dir ./meus_csvs/
```
   O comando cria e recalcula tudo sozinho (contagem de relacionamentos por tabela, score de relevância, ranking) a partir só do que está nos CSVs. Se `contextos/punk_records.db` já existir, use `--forcar` para sobrescrever.
4. **Teste:**
```bash
   python3 skills/vegapunk-community/scripts/nomi_nomi_no_mi.py buscar "seu pedido em português aqui"
```
5. **Mantenha o banco importado fora do controle de versão.** Depois de importar, `contextos/punk_records.db` passa a conter metadados do seu sistema. Adicione-o ao `.gitignore` do seu projeto e nunca faça commit ou push dele para um repositório público.
### Formato dos 5 CSVs
 
| Arquivo | Colunas obrigatórias | Colunas opcionais | Observação | Exemplo de consulta |
|---|---|---|---|---|
| `tabelas.csv` | `tabela` | `total_registros`, `descricao` | Uma linha por tabela. Não inclua score, ranking ou contagens: são calculados pelo import. | [![baixar tabelas.sql](https://img.shields.io/badge/baixar-Tabelas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](sql/tabelas.sql) |
| `colunas.csv` | `tabela`, `coluna` | `descricao` | Uma linha por coluna. A `descricao` (negócio, em PT-BR) é o que o motor usa pra casar com o pedido do usuário. | [![baixar colunas.sql](https://img.shields.io/badge/baixar-Colunas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](sql/colunas.sql) |
| `relacionamentos.csv` | `tabela_filha`, `campo_filho`, `tabela_mae`, `campo_mae` | — | Uma linha por FK; chave composta = uma linha por campo. | [![baixar relacionamentos.sql](https://img.shields.io/badge/baixar-Relacionamentos.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](sql/relacionamentos.sql) |
| `sistemas.csv` | `codsistema`, `nomesistema` | `descricao` | Uma linha por módulo. `codsistema` deve bater com o prefixo de 1 letra das tabelas desse módulo. | [![baixar sistemas.sql](https://img.shields.io/badge/baixar-Sistemas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](sql/sistemas.sql) |
| `sinonimos.csv` | `termo`, `sinonimo` | — | Uma linha por par (um termo com 3 sinônimos = 3 linhas). Cadeias funcionam. | Sem consulta associada. É vocabulário definido por você. |
 
As 4 consultas de exemplo ficam na raiz deste repositório, fora da pasta `skills/`. Elas servem só como referência de como extrair os dados de um ambiente real; adapte a lista de prefixos de tabela (`'A', 'G', 'P', 'V', 'Z'` nos exemplos) para os módulos do seu ambiente.
 
Documentação completa, com o formato de cada CSV e a explicação de como o motor usa cada tabela, em [`skills/vegapunk-community/contextos/README.md`](skills/vegapunk-community/contextos/README.md).
 
## Estrutura do Repositório
 
```
vegapunk-community/
├── README.md                        # Este arquivo
├── Tabelas.sql                      # Exemplo de consulta para gerar tabelas.csv
├── Colunas.sql                      # Exemplo de consulta para gerar colunas.csv
├── Relacionamentos.sql              # Exemplo de consulta para gerar relacionamentos.csv
├── Sistemas.sql                     # Exemplo de consulta para gerar sistemas.csv
└── skills/
    └── vegapunk-community/
        ├── SKILL.md                 # Definição principal e fluxos de trabalho
        ├── AVISO.md                 # Aviso sobre dados de terceiros
        ├── contextos/
        │   ├── punk_records.db      # Base de metadados (SQLite), vazia até você importar
        │   └── README.md            # Arquitetura do motor, formato de import, limitações
        ├── referencias/
        │   ├── patterns.md          # Padrões de query: CTEs, paginação, PIVOT, MERGE, window functions
        │   ├── performance.md       # Planos de execução, indexação, estatísticas de espera
        │   ├── security.md          # Prevenção SQL injection, SQL dinâmico, permissões
        │   ├── data-types.md        # Seleção de tipos, collation, otimização de armazenamento
        │   └── transactions.md      # Níveis de isolamento, deadlocks, transações distribuídas
        └── scripts/
            ├── nomi_nomi_no_mi.py       # Motor de descoberta de schema + comando `importar`
            └── testes_regressao.py     # Suíte de testes (gera fixture fictícia própria)
```
 
## Uso
 
Uma vez instalada e com os dados importados, o Claude Code invoca automaticamente esta skill quando você pergunta sobre:
 
* Escrita ou otimização de queries T-SQL
* Descoberta de tabelas/colunas do seu schema importado
* Procedures SQL Server e planos de execução
* Otimização de performance de banco de dados e indexação
* Segurança SQL e prevenção de injection
* Gerenciamento de transações e tratamento de erros
### Fluxo de Descoberta de Schema
 
Ao trabalhar com uma base cadastrada (depois de importada), a skill usa o motor Nomi Nomi no Mi:
 
1. **Buscar Tabelas:** identifica tabelas relevantes por domínio de negócio, a partir de um pedido em português.
2. **Detalhar Tabelas:** recupera colunas, descrições e relacionamentos de chave estrangeira.
3. **Escrever Query:** compõe T-SQL usando exclusivamente os nomes de schema descobertos, nunca por suposição.
Exemplo (nomes ilustrativos, os reais dependem do que você importou):
```bash
python3 scripts/nomi_nomi_no_mi.py buscar "colaboradores com dados de folha de pagamento"
python3 scripts/nomi_nomi_no_mi.py detalhar FCOLABORADOR FDADOSFOLHA
```

<img width="1260" height="820" alt="radar-descoberta-de-schema" src="https://github.com/user-attachments/assets/09e25475-f1c8-4473-81fc-c08ecf363b93" />![Uploading radar-

## Suporte a Versões SQL Server
 
Vegapunk cobre recursos de SQL Server 2016 até 2022, com anotações de versão quando aplicável.
 
## Créditos
 
**Criador:** Tiago Cardoso Bezerra
**E-mail:** tiagocardosobezerra@gmail.com
**GitHub:** [@tiagocardosobezerra](https://github.com/tiagocardosobezerra)
 
Batizado em homenagem a Vegapunk, o engenheiro gênio de *One Piece*, personagem conhecido por dominar sistemas complexos e destilar conhecimento.
 
## Agradecimentos
 
* **Bruna Cardoso Bezerra**, por me ensinar tudo o que sei sobre o Claude Code.
* **Hatem Mohamed** | https://github.com/hmohamed01, por compartilhar as boas práticas de T-SQL que aplico no Vegapunk.
* **Você**, por usar Vegapunk!
## Aviso sobre dados de terceiros
 
Este repositório **não contém, e nunca vai conter**, metadados de schema de nenhum sistema real. O que é distribuído aqui é só o motor (código genérico) e um banco de metadados **vazio**. Ao importar dados do seu próprio ambiente, você confirma que já tem acesso legítimo ou licenciado a ele, e manter esses dados fora de repositórios públicos é responsabilidade sua. Detalhes completos em [`skills/vegapunk-community/AVISO.md`](skills/vegapunk-community/AVISO.md).
 
## Licença
 
MIT License, veja [LICENSE](LICENSE) para detalhes.
 
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
