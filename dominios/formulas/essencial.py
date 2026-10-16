"""
Termo essencial de uma intenção (fase 4 da v3).

O Claude que usa a skill pode pôr no JSON da intenção um campo `essencial`:
o conceito que a solução PRECISA ter ("e-mail", "excluir registro", "por
extenso"). Um candidato só é aceito se o texto DOCUMENTADO dele (nome,
descrição, descrições alternativas, sintaxe, parâmetros, exemplos,
observações e o texto original da documentação) contém o essencial ou um
sinônimo cadastrado. Sem nenhum candidato assim, a intenção é LACUNA:
"nenhuma função documentada faz <essencial>".

O essencial só existe para CAPACIDADE que pode não existir: efeito externo
(e-mail), formato especial (por extenso), ação sobre registro (excluir),
consulta (executar consulta). Conta comum (limitar, somar, comparar,
arredondar) não leva essencial.

Sinônimos: os do pacote de conhecimento mais os pares PRÓPRIOS da regra: na
Punk Records, `sinonimos` com `uso = 'essencial'` (migração 008, gravados
por `york.py gravar-sinonimos --uso essencial`, lidos pela ponte `dominios/solucao.py`), que nenhuma busca lê; numa
instância ainda sem a migração, o arquivo `egghead/sinonimos_essencial.json`.

Não há limiar de score aqui: a medição do bloco 4a mostrou que o score não
separa acerto de lacuna. Comparação por frase normalizada (sem acento, sem
caixa, pontuação vira espaço), nunca por radical solto: "exclu" casaria com
"exclusivamente".
"""

import json
import os
import re

from dominios.formulas.texto import normalizar


def _frase(texto):
    return ' ' + ' '.join(re.sub(r'[^a-z0-9]+', ' ', normalizar(texto or '')).split()) + ' '


def texto_documentado(ficha):
    partes = [ficha.get('nome'), ficha.get('descricao')]
    partes += ficha.get('descricoes_alternativas') or []
    partes += [a.get('texto') for a in ficha.get('assinaturas') or []]
    partes += [p.get('rotulo_documentado') for p in ficha.get('parametros') or []]
    partes += [p.get('descricao') for p in ficha.get('parametros') or []]
    partes += [e.get('codigo') for e in ficha.get('exemplos') or [] if isinstance(e, dict)]
    partes += [o.get('texto') for o in ficha.get('observacoes') or [] if isinstance(o, dict)]
    original = ficha.get('texto_original') or []
    partes += [original] if isinstance(original, str) else original
    return _frase(' '.join(str(p) for p in partes if p))


ARQUIVO_PROPRIO = 'sinonimos_essencial.json'


def carregar_sinonimos(instancia=None):
    """Pares próprios da regra no ARQUIVO da instância (instância ainda sem a
    migração 008): {"termo do pedido": {"termo documentado", ...}}. Sem
    arquivo, vazio. Os pares da Punk Records (`uso = 'essencial'`) chegam pela
    ponte entre os domínios (`dominios/solucao.py`): o núcleo de fórmulas não
    abre a base de schema."""
    pasta = instancia or os.environ.get('VEGAPUNK_EGGHEAD') or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', '..', 'egghead')
    try:
        with open(os.path.join(pasta, ARQUIVO_PROPRIO), encoding='utf-8') as f:
            dados = json.load(f)
    except FileNotFoundError:
        return {}
    return {normalizar(k): {normalizar(a) for a in v} for k, v in dados.items() if not k.startswith('_')}


def juntar(*dicionarios):
    out = {}
    for d in dicionarios:
        for k, v in (d or {}).items():
            out.setdefault(k, set()).update(v)
    return out


def variantes(essencial, sinonimos=None):
    """O essencial e os sinônimos cadastrados dele, já normalizados como frase."""
    out = set()
    for termo in [essencial] + sorted((sinonimos or {}).get(normalizar(essencial), ())):
        f = _frase(termo).strip()
        out.add(f)
        if '-' in termo:                           # "e-mail" também casa com "email"
            out.add(f.replace(' ', ''))
    return {v for v in out if v}


def atende(ficha, essencial, sinonimos=None):
    texto = texto_documentado(ficha)
    return any(f' {v} ' in texto for v in variantes(essencial, sinonimos))


def filtrar(fichas, essencial, sinonimos=None):
    """(aceitas, lacuna). `lacuna` é o motivo quando nenhuma ficha atende."""
    if not essencial:
        return list(fichas), None
    aceitas = [f for f in fichas if atende(f, essencial, sinonimos)]
    return aceitas, (None if aceitas else f'nenhuma função documentada faz "{essencial}"')
