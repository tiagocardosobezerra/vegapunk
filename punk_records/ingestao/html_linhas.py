"""
Converte o HTML "storage" do Confluence numa lista de LINHAS lógicas, sem
perder as pistas de formatação que os extratores usam para segmentar a
documentação (negrito, item de lista, título, célula de tabela, macro de
aviso). Não interpreta conteúdo — só estrutura.
"""

import re
from html import unescape
from html.parser import HTMLParser

_QUEBRAS = {'p', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'pre', 'table', 'ul', 'ol',
            'ac:structured-macro', 'blockquote', 'hr'}
_TITULOS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
_NEGRITO = {'strong', 'b'}
_MACROS_AVISO = {'note', 'info', 'warning', 'tip', 'panel', 'expand'}


class Linha:
    __slots__ = ('texto', 'negrito', 'lista', 'titulo', 'celula', 'macro')

    def __init__(self, texto, negrito, lista, titulo, celula, macro):
        self.texto = texto          # texto limpo da linha
        self.negrito = negrito      # lista de trechos em negrito, na ordem
        self.lista = lista          # é item de lista (<li>)?
        self.titulo = titulo        # nível de título (0 = não é título)
        self.celula = celula        # veio de célula de tabela?
        self.macro = macro          # nome da macro de aviso que a contém (note/info...) ou ''

    @property
    def toda_negrito(self):
        t = re.sub(r'\W', '', self.texto)
        b = re.sub(r'\W', '', ''.join(self.negrito))
        return bool(t) and t == b

    def __repr__(self):
        return f'Linha({self.texto!r})'


class _Conversor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.linhas = []
        self.buf, self.neg_buf, self.neg_atual = [], [], None
        self.pilha_lista = 0
        self.titulo = 0
        self.celula = 0
        self.macros = []
        self.em_parametro_macro = False
        self.ignorar = 0

    # -- helpers
    def _fechar_linha(self):
        texto = re.sub(r'[ \t\xa0​]+', ' ', ''.join(self.buf)).strip()
        if self.neg_atual is not None:
            self.neg_buf.append(''.join(self.neg_atual))
            self.neg_atual = []
        negrito = [re.sub(r'\s+', ' ', n).strip() for n in self.neg_buf if n.strip()]
        if texto:
            macro = next((m for m in reversed(self.macros) if m in _MACROS_AVISO), '')
            self.linhas.append(Linha(texto, negrito, self.pilha_lista > 0, self.titulo,
                                     self.celula > 0, macro))
        self.buf, self.neg_buf = [], []
        if self.neg_atual is not None:
            self.neg_atual = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('ac:parameter', 'ri:attachment', 'ac:image') or tag == 'ac:plain-text-body':
            if tag == 'ac:parameter':
                self.ignorar += 1
            return
        if tag == 'ac:structured-macro':
            self._fechar_linha()
            self.macros.append(a.get('ac:name', ''))
            return
        if tag in ('ul', 'ol'):
            self.pilha_lista += 1
        if tag in ('td', 'th'):
            self._fechar_linha()
            self.celula += 1
        if tag == 'br':
            self._fechar_linha()
            return
        if tag in _QUEBRAS:
            self._fechar_linha()
        if tag in _TITULOS:
            self.titulo = int(tag[1])
        if tag in _NEGRITO:
            self.neg_atual = []

    def handle_endtag(self, tag):
        if tag == 'ac:parameter':
            self.ignorar = max(0, self.ignorar - 1)
            return
        if tag == 'ac:structured-macro':
            self._fechar_linha()
            if self.macros:
                self.macros.pop()
            return
        if tag in _NEGRITO and self.neg_atual is not None:
            self.neg_buf.append(''.join(self.neg_atual))
            self.neg_atual = None
            return
        if tag in ('td', 'th'):
            self._fechar_linha()
            self.celula = max(0, self.celula - 1)
            return
        if tag in _QUEBRAS:
            self._fechar_linha()
        if tag in _TITULOS:
            self.titulo = 0
        if tag in ('ul', 'ol'):
            self.pilha_lista = max(0, self.pilha_lista - 1)

    def handle_startendtag(self, tag, attrs):
        if tag == 'br':
            self._fechar_linha()
        else:
            self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.ignorar:
            return
        self.buf.append(data)
        if self.neg_atual is not None:
            self.neg_atual.append(data)


def converter(storage):
    """HTML storage -> lista de `Linha`."""
    c = _Conversor()
    # CDATA de macros de código (<![CDATA[...]]>) vira texto normal
    storage = re.sub(r'<!\[CDATA\[(.*?)\]\]>', lambda m: m.group(1).replace('<', '&lt;'), storage or '', flags=re.S)
    c.feed(storage)
    c._fechar_linha()
    return c.linhas


def texto_simples(storage):
    return unescape(re.sub(r'<[^>]+>', ' ', storage or ''))
