# Vegapunk
 
## Visão geral
 
O Vegapunk é uma skill do Claude Code para desenvolvimento em T-SQL no Microsoft SQL Server. O diferencial dela é um motor de descoberta de schema por linguagem natural, plugável em qualquer banco de dados: você pergunta em português e recebe a query certa, já com os nomes reais de tabela e coluna do seu ambiente.
 
Em vez de o Claude tentar adivinhar como um sistema nomeou as próprias tabelas, o Vegapunk consulta uma base de metadados local chamada **Punk Records**, através de um motor chamado **Nomi Nomi no Mi**. Essa base é populada por você, a partir do seu próprio ambiente.
  
<img width="100%" height="842" alt="vegapunk-poster" src="https://github.com/user-attachments/assets/d95619a4-0e70-47d7-9db4-6d35e1f4bbb7" />
 
## Recursos
 
* **Descoberta de schema por linguagem natural.** Você descreve o que precisa em português e o motor Nomi Nomi no Mi busca as tabelas e colunas correspondentes, já trazendo os relacionamentos de chave estrangeira prontos para montar os JOINs. Isso elimina boa parte da adivinhação de nomenclatura.
* **Comando de importação embutido.** Basta exportar 5 CSVs do seu ambiente (formato abaixo); o motor calcula sozinho os campos derivados, como contagem de relacionamentos, score de relevância e ranking, e avisa (sem travar o import) se alguma FK do `relacionamentos.csv` apontar para uma tabela ou coluna que não existe. Você não precisa calcular nada na mão.
* **Verificação de documentação ao vivo.** A skill valida a sintaxe T-SQL contra a documentação oficial da Microsoft usando WebFetch, com fallback para WebSearch quando o recurso é específico de versão (SQL Server 2016 a 2022).
* **Fluxos de trabalho estruturados.** Guias para desenvolvimento de queries, otimização de procedures e gerenciamento de transações, com padrões de tratamento de erro já definidos.
* **Detecção de anti-padrões de performance.** Identifica predicados não SARGable, conversões implícitas, índices faltando e outras ineficiências no plano de execução.
* **Boas práticas de segurança.** Prevenção de SQL injection, queries parametrizadas, cuidado com SQL dinâmico e gerenciamento de permissões.
* **Referências abrangentes.** Cinco documentos cobrindo padrões de query, otimização de performance, segurança, tipos de dados e transações.
* **Suíte de regressão própria (Stella).** Gera sozinha uma fixture fictícia e valida, a cada mudança, que casos que já funcionavam continuam funcionando, cobrindo tanto o score/ranking do motor quanto o caminho `importar` → `detalhar` → JSON.
## Instalação
 
Clone este repositório e copie a pasta `skills/vegapunk` para o seu diretório de skills.
 
### Nível de usuário (todos os projetos)
 
macOS/Linux:
```bash
cp -r skills/vegapunk ~/.claude/skills/
```
 
Windows (PowerShell):
```powershell
Copy-Item -Recurse skills/vegapunk $HOME\.claude\skills\
```
 
### Nível de projeto (projeto atual apenas)
 
macOS/Linux:
```bash
cp -r skills/vegapunk .claude/skills/
```
 
Windows (PowerShell):
```powershell
Copy-Item -Recurse skills/vegapunk .claude\skills\
```
 
> ⚠️ Se você já tiver, no mesmo ambiente, outra skill/plugin chamado `vegapunk` apontando para um schema real de terceiros (sistema licenciado, já com dados importados), **não instale este pacote por cima dela**, copie esta pasta com outro nome (ex.: `vegapunk-publico`) antes de continuar. Este pacote é o motor genérico e público: base vazia, nenhum conhecimento de sistema real embutido.
 
## Importando seus dados (obrigatório)
 
O `punk_records.db` publicado neste repositório vem **vazio**. Para a skill funcionar, é **obrigatório** importar as 5 tabelas de metadados (**Tabelas**, **Colunas**, **Relacionamentos**, **Sistemas** e **Sinônimos**) a partir do seu próprio ambiente.
 
### Passo a passo
 
1. **Extraia os metadados do seu ambiente.** Você precisa já ter acesso legítimo ou licenciado a ele. Rode consultas de introspecção contra o dicionário de dados e o catálogo de relacionamentos do seu sistema (nunca contra dados de negócio ou de cliente) para obter: lista de tabelas, colunas com descrição de negócio, relacionamentos (chaves estrangeiras), módulos/sistemas e, se fizer sentido, um dicionário de sinônimos (vocabulário coloquial → vocabulário do schema).
2. **Exporte cada conjunto para um CSV**, no formato abaixo, dentro de uma pasta (por exemplo, `./meus_csvs/`).
3. **Rode o importador:**
```bash
   python3 skills/vegapunk/scripts/nomi_nomi_no_mi.py importar --dir ./meus_csvs/
```
   O comando cria e recalcula tudo sozinho (contagem de relacionamentos por tabela, score de relevância, ranking) a partir só do que está nos CSVs, e avisa no final, sem travar o import, se alguma FK de `relacionamentos.csv` apontar para uma tabela ou coluna que não existe em `tabelas.csv`/`colunas.csv`. Se `contextos/punk_records.db` já existir, use `--forcar` para sobrescrever.
4. **Teste:**
```bash
   python3 skills/vegapunk/scripts/nomi_nomi_no_mi.py buscar "seu pedido em português aqui"
```
5. **Mantenha o banco importado fora do controle de versão.** Depois de importar, `contextos/punk_records.db` passa a conter metadados do seu sistema. Adicione-o ao `.gitignore` do seu projeto e nunca faça commit ou push dele para um repositório público.
### Formato dos 5 CSVs
 
| Arquivo | Colunas obrigatórias | Colunas opcionais | Observação | Exemplo de consulta |
|---|---|---|---|---|
| `tabelas.csv` | `tabela` | `total_registros`, `descricao` | Uma linha por tabela. Não inclua score, ranking ou contagens: são calculados pelo import. | [![baixar tabelas.sql](https://img.shields.io/badge/baixar-tabelas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](sql/tabelas.sql) |
| `colunas.csv` | `tabela`, `coluna` | `descricao` | Uma linha por coluna. A `descricao` (negócio, em PT-BR) é o que o motor usa pra casar com o pedido do usuário. | [![baixar colunas.sql](https://img.shields.io/badge/baixar-colunas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](sql/colunas.sql) |
| `relacionamentos.csv` | `tabela_filha`, `campo_filho`, `tabela_mae`, `campo_mae` | — | Uma linha por FK; chave composta = uma linha por campo. O `importar` confere se essas tabelas/colunas existem e avisa (sem travar) se alguma FK estiver com typo. | [![baixar relacionamentos.sql](https://img.shields.io/badge/baixar-relacionamentos.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](sql/relacionamentos.sql) |
| `sistemas.csv` | `codigo_sistema`, `nome_sistema` | `descricao` | Uma linha por módulo. `codigo_sistema` deve bater com o prefixo de 1 letra das tabelas desse módulo, quando esse padrão fizer sentido no seu ambiente. | [![baixar sistemas.sql](https://img.shields.io/badge/baixar-sistemas.sql-2ea44f?style=flat-square&logo=download&logoColor=white)](sql/sistemas.sql) |
| `sinonimos.csv` | `termo`, `sinonimo` | — | Uma linha por par (um termo com 3 sinônimos = 3 linhas). Cadeias funcionam. | Sem consulta associada. É vocabulário definido por você. |
 
As 4 consultas de exemplo ficam na pasta `sql/`, na raiz deste repositório, fora da pasta `skills/`. Elas servem só como referência de como extrair os dados de um ambiente real; adapte a lista de prefixos de tabela (`'A', 'G', 'P', 'V', 'Z'` nos exemplos) para os módulos do seu ambiente.
 
Documentação completa, com o formato de cada CSV e a explicação de como o motor usa cada tabela, em [`skills/vegapunk/contextos/README.md`](skills/vegapunk/contextos/README.md).
 
## Estrutura do Repositório
 
```
vegapunk/
├── README.md                        # Este arquivo
├── LICENSE                          # MIT License
├── sql/
│   ├── tabelas.sql                  # Exemplo de consulta para gerar tabelas.csv
│   ├── colunas.sql                  # Exemplo de consulta para gerar colunas.csv
│   ├── relacionamentos.sql          # Exemplo de consulta para gerar relacionamentos.csv
│   └── sistemas.sql                 # Exemplo de consulta para gerar sistemas.csv
├── SKILL.md                         # Definição principal e fluxos de trabalho
├── AVISO.md                         # Aviso sobre dados de terceiros
├── contextos/
│   ├── punk_records.db              # Base de metadados (SQLite), vazia até você importar
│   └── README.md                    # Arquitetura do motor, formato de import, limitações
├── referencias/
│   ├── patterns.md                  # Padrões de query: CTEs, paginação, PIVOT, MERGE, window functions
│   ├── performance.md               # Planos de execução, indexação, estatísticas de espera
│   ├── security.md                  # Prevenção SQL injection, SQL dinâmico, permissões
│   ├── data-types.md                # Seleção de tipos, collation, otimização de armazenamento
│   └── transactions.md              # Níveis de isolamento, deadlocks, transações distribuídas
└── scripts/
    ├── nomi_nomi_no_mi.py           # Motor de descoberta de schema + comando `importar`
    └── stella.py                    # Suíte de regressão (gera fixture fictícia própria)
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
python3 scripts/nomi_nomi_no_mi.py buscar "quais funcionários bateram ponto ontem"
python3 scripts/nomi_nomi_no_mi.py detalhar R034FUN R038PON
```
 
<img width="1260" height="820" alt="radar-descoberta-de-schema" src="https://github.com/user-attachments/assets/09e25475-f1c8-4473-81fc-c08ecf363b93" />

## Suporte a Versões SQL Server
 
Vegapunk cobre recursos de SQL Server 2016 até 2022, com anotações de versão quando aplicável.
 
## Créditos
 
**Criador:** Tiago Cardoso Bezerra | [tiagocardosobezerra](https://github.com/tiagocardosobezerra)
 
Batizado em homenagem a Vegapunk, o engenheiro genial de One Piece, personagem reconhecido por dominar sistemas complexos e compartilhar conhecimento de forma clara e acessível.
 
## Agradecimentos

* Minha esposa **Júlia** e meus filhos **Arthur** e **Aurora**, o porto seguro onde encontro paz, inspiração e a leveza de que preciso todos os dias. 
* **Bruna Cardoso Bezerra** | [brunacbezerra](https://github.com/brunacbezerra), por me ensinar tudo o que sei sobre o Claude Code.
* **Hatem Mohamed** | [hmohamed01](https://github.com/hmohamed01), por compartilhar as boas práticas de T-SQL que aplico no Vegapunk.
* **Você**, por usar Vegapunk!
## Aviso sobre dados de terceiros
 
Este repositório **não contém, e nunca vai conter**, metadados de schema de nenhum sistema real. O que é distribuído aqui é só o motor (código genérico) e um banco de metadados **vazio**. Ao importar dados do seu próprio ambiente, você confirma que já tem acesso legítimo ou licenciado a ele, e manter esses dados fora de repositórios públicos é responsabilidade sua. Detalhes completos em [`skills/vegapunk/AVISO.md`](skills/vegapunk/AVISO.md).
 
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
