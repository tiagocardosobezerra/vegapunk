# Aviso sobre dados de terceiros

Este projeto (motor **Nomi Nomi no Mi** + skill **Vegapunk**)
**não contém, nunca conteve e nunca vai conter** metadados de schema de
nenhum sistema real de terceiros — incluindo, mas não se limitando a,
qualquer ERP comercial.

O que este repositório distribui:

- Um **algoritmo genérico** de busca/ranking de tabelas a partir de um
  pedido em linguagem natural (PT-BR), que não é específico de nenhum
  sistema.
- Um banco de dados (`contextos/punk_records.db`) contendo **apenas o
  schema vazio** de 5 tabelas de metadados (`tabelas`, `colunas`,
  `relacionamentos`, `sistemas`, `sinonimos` — nomes de tabela/coluna
  genéricos), sem nenhuma linha de dado.
- Documentação e um comando de importação (`importar`) para que **cada
  pessoa que já tem acesso legítimo/licenciado** a um sistema popule sua
  própria cópia local com os metadados desse sistema.

## Responsabilidade pelo uso

Ao rodar `importar` e preencher `contextos/punk_records.db` (ou qualquer
banco apontado por `--db`) com metadados de um sistema real:

1. Você confirma que já possui acesso legítimo/licenciado a esse sistema.
2. Os dados importados são de sua responsabilidade — este projeto não os
   recebe, não os processa e não tem visibilidade sobre eles.
3. **Não publique, faça commit ou compartilhe** o banco preenchido (nem
   os CSVs de origem) em nenhum repositório público, issue, pull
   request ou canal de suporte deste projeto. Mantenha-os fora do
   controle de versão (`.gitignore`) depois de importar.
4. Se for contribuir com este repositório (código, documentação, casos
   de teste), qualquer exemplo ou fixture deve usar dados 100%
   fictícios — nunca copiados ou derivados de um schema real.

## Marcas e nomes de terceiros

Os nomes internos deste projeto ("Vegapunk", "Punk Records", "Nomi Nomi
no Mi") são referências de tom criativo e não indicam afiliação,
endosso ou associação com nenhum detentor de marca ou propriedade
intelectual de terceiros. Nenhum logotipo, marca registrada ou material
protegido de terceiros é distribuído neste repositório.

## Isenção

Este aviso é uma declaração de política do projeto, não aconselhamento
jurídico. Se você pretende importar dados de um sistema comercial
licenciado, revise os termos de licença/uso desse sistema antes de
extrair e armazenar metadados de schema, e consulte um advogado se tiver
dúvidas sobre o que seu contrato de licença permite.
