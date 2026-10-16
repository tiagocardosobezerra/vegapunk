# Aviso sobre dados de terceiros

O Vegapunk existe em duas versões, geradas da mesma fonte. O motor é
idêntico nas duas; muda só o que vai junto.

| Versão | O que leva | Pode publicar? |
|---|---|---|
| **Vegapunk** | o motor (`stella.py`, `satelites/`, `nomi_nomi_no_mi/`, `dominios/`, `punk_records/` sem a camada privada), os pacotes públicos de conhecimento (só `fonte.json`, `dialeto.json`, `casos/`, documentação e, se houver, um `mapa/` fictício), casos fictícios, testes e referências. **Sem `egghead/`.** | sim |
| **Vegapunk com Punk Records** | o mesmo motor mais a instância local `egghead/` (a estrutura do banco do usuário, logs, confirmações, goldens reais) e a camada `punk_records/pacotes/privado/` | **nunca**: só para uso no próprio ambiente |

## O que nunca entra

**Nunca importar dados, só estrutura.** Do banco do usuário entram apenas
nomes de tabela e de coluna, descrições, tipos e ligações. Nenhuma linha de
conteúdo: nem cadastros, nem fórmulas existentes, nem consultas cadastradas.
São dois motivos: evitar risco legal e evitar aprender com o que pode estar
errado no sistema de origem.

O motor **não contém, nunca conteve e nunca vai conter** metadados de schema
de nenhum sistema real de terceiros. Ele traz o comando de importação
(`satelites/york.py importar`) para que **cada pessoa que já tem acesso
legítimo/licenciado** a um sistema preencha a própria cópia local.

## Responsabilidade pelo uso

Ao importar metadados de um sistema real para `egghead/punk_records.db` (ou
qualquer banco apontado por `--db`):

1. Você confirma que já possui acesso legítimo/licenciado a esse sistema.
2. Os dados importados são de sua responsabilidade — este projeto não os
   recebe, não os processa e não tem visibilidade sobre eles.
3. **Não publique, faça commit ou compartilhe** `egghead/` (nem os CSVs de
   origem) em nenhum repositório público, issue, pull request ou canal de
   suporte. O `.gitignore` do plugin já mantém `egghead/`, os CSVs e a
   camada privada fora do controle de versão; `satelites/atlas.py
   isolamento` confere que nada da instância aparece no que é distribuível.
4. Ao contribuir (código, documentação, casos de teste), qualquer exemplo
   ou fixture deve usar dados 100% fictícios — nunca copiados ou derivados
   de um schema real.

O texto da documentação de um fornecedor (a camada Linguagem dos pacotes)
também fica local: num pacote público, só `fonte.json`, `pacote.json`,
`dialeto.json`, `*.md`, `mapa/` e `casos/` são distribuíveis, e um `mapa/`
só se for fictício. O mapa de um sistema real cita tabelas reais: é da
instância, no pacote privado (`punk_records/pacotes/privado/`), e o
`atlas.py isolamento` recusa qualquer mapa real na superfície distribuível.

O que é publicável sai só pela distribuição (`python3 satelites/atlas.py
distribuir --destino <pasta fora do repositório>`): uma pasta separada, sem
`.git`, com exatamente a superfície distribuível.

## Marcas e nomes de terceiros

Os nomes internos deste projeto ("Vegapunk", "Punk Records", "Nomi Nomi no
Mi", "Egghead" e os satélites) são referências de tom criativo e não
indicam afiliação, endosso ou associação com nenhum detentor de marca ou
propriedade intelectual de terceiros. Nomes de fornecedor aparecem só
dentro do próprio pacote de conhecimento, nunca na especificação da skill.

## Isenção

Este aviso é uma declaração de política do projeto, não aconselhamento
jurídico. Se você pretende importar dados de um sistema comercial
licenciado, revise os termos de licença/uso desse sistema antes de extrair
e armazenar metadados de schema, e consulte um advogado se tiver dúvidas
sobre o que seu contrato de licença permite.
