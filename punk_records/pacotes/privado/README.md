# Camada privada de conhecimento de fórmulas

Tudo o que for específico da SUA instalação (funções/variáveis internas,
padrões de fórmula da empresa, anotações, sinônimos do seu time, nomes que
não podem vazar) fica aqui, um diretório por pacote, cada um com
`pacote.json` (`"visibilidade": "privado"`, `"estende": "<id do pacote público>"`).

* Nada aqui é exigido pelo motor: `python3 stella.py --somente-publico ...`
  roda sem esta pasta.
* O `.gitignore` desta pasta ignora tudo (exceto este README) — não remova.
* Também é possível manter pacotes privados FORA da skill:
  `VEGAPUNK_FORMULAS_PRIVADO=/caminho/pacote1:/caminho/pacote2` ou `--privado DIR`.
* Depois de criar/alterar um pacote: `python3 satelites/atlas.py isolamento`.
* Avisos de merge com a camada pública: `python3 stella.py status`.
* O log de uso das fórmulas não fica aqui: fica na instância, em `egghead/shaka_log.jsonl`.

Modelo comentado: `punk_records/pacotes/modelo-privado/`. Regras de merge e campos:
`referencias/formulas.md`, seções 3 e 5.
