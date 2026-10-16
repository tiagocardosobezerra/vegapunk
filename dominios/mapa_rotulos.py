"""
Rótulos de parâmetro e descrições de coluna, para o mapa (fase 3 da v3).

Funções puras de texto, sem base e sem domínio: usadas pelo Edison (que
sugere ligações) e por quem mostra a ligação de cada parâmetro.

A "entidade" de um rótulo de código é o que vem depois de CÓDIGO/CÓD.,
sem conectivos e colada: "CÓD. DO EVENTO", "CODEVENTO" e "Código
Identificador do Evento" têm a mesma entidade, EVENTO. Um rótulo que é só
"CÓDIGO" não tem entidade: sozinho, não diz de que cadastro é o código.
"""

import re
import unicodedata

_CONECTIVOS = {'DO', 'DA', 'DE', 'DOS', 'DAS', 'D'}
_CODIGO = ('CODIGO', 'COD', 'CD')
_QUALIFICADORES = {'IDENTIFICADOR', 'IDENT', 'INTERNO'}


def tokens(texto):
    t = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode().upper()
    return re.sub(r'[^A-Z0-9]+', ' ', t).split()


def entidade_de_codigo(texto):
    """Entidade de um rótulo/descrição de código ('EVENTO', 'UNIDADENEGOCIO'),
    '' para um código sem entidade, ou None se o texto não é de código."""
    ts = tokens(texto)
    if not ts:
        return None
    primeiro = ts[0]
    if primeiro in _CODIGO:
        resto = ts[1:]
    else:
        colado = next((c for c in _CODIGO if primeiro.startswith(c) and len(primeiro) > len(c) + 2), None)
        if not colado:
            return None
        resto = [primeiro[len(colado):]] + ts[1:]
    resto = [t for t in resto if t not in _CONECTIVOS and t not in _QUALIFICADORES]
    return ''.join(resto)


def entidade_de_descricao(texto):
    """Entidade de uma descrição de coluna de descrição ('Descrição do
    Evento', 'Nome da Função') ou None."""
    ts = tokens(texto)
    if not ts or ts[0] not in ('DESCRICAO', 'NOME', 'TITULO'):
        return None
    return ''.join(t for t in ts[1:] if t not in _CONECTIVOS)


def ligar_parametro(funcao, rotulo, cadastros):
    """Cadastro do mapa a que o parâmetro está ligado, ou None.

    `cadastros`: dicts com 'cadastro', 'funcoes' (set, maiúsculas) e
    'entidades' (set de `entidade_de_codigo` dos rótulos do cadastro). A
    ligação exige a função declarada no cadastro E o rótulo dizendo a mesma
    entidade; um rótulo que é só "código" liga quando a função está num único
    cadastro. Nunca escolhe entre dois cadastros."""
    e = entidade_de_codigo(rotulo)
    if e is None:
        return None
    donos = [c for c in cadastros if funcao.upper() in c['funcoes']]
    if e:
        donos = [c for c in donos if e in c['entidades']]
    return donos[0]['cadastro'] if len(donos) == 1 else None
