"""
Conector genérico para wikis Confluence (REST API pública, sem login).

Não sabe nada de fornecedor nenhum nem de fórmulas: recebe uma configuração de fonte
(`fonte.json` do pacote de conhecimento) com páginas-semente, regras de
relevância e limites, e devolve páginas BRUTAS (formato storage do
Confluence + metadados de rastreabilidade) e um manifesto de descoberta.

Descoberta, por semente:
  1. a própria página;
  2. TODAS as descendentes na árvore (child/page, recursivo);
  3. links internos encontrados no corpo de cada página processada
     (<a href=...pageId=N>, /display/ESPACO/Titulo, <ac:link><ri:page>),
     seguidos enquanto forem RELEVANTES (regex da fonte) e dentro da
     profundidade máxima configurada — links de navegação, de outros
     produtos ou sem conteúdo técnico ficam registrados como
     `fora_de_escopo`, com o motivo, mas não são expandidos.

Incremental: se a página já existe em `bruto/` com a mesma versão, o
corpo não é baixado de novo (só os metadados).

Controle da árvore (F3-doc da v3), pelo `fonte.json`:
  - `excluir_page_ids`: páginas que nunca entram (nem as filhas delas);
    ficam no manifesto como `excluida`, com o motivo.
  - `paginas_aprovadas`: as páginas de árvore aceitas pelo usuário. Quando a
    lista existe, uma página NOVA na árvore de uma semente (que não está nela)
    não é baixada nem expandida: fica como `nova_na_arvore` no manifesto e no
    relatório, e só entra quando o usuário a acrescentar à lista. Assim
    ninguém precisa olhar a árvore de novo a cada ingestão.
  - pertencer à árvore de uma semente prevalece sobre ter sido achada por
    link: a página é reprocessada com o contexto da semente.
"""

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape

USER_AGENT = 'Mozilla/5.0 (compatible; Vegapunk-York/1.0; ingestao de documentacao tecnica publica)'


class ClienteConfluence:
    def __init__(self, base_url, pausa=0.25, tentativas=4, timeout=40):
        self.base = base_url.rstrip('/')
        self.pausa = pausa
        self.tentativas = tentativas
        self.timeout = timeout
        self.requisicoes = 0

    def _get(self, caminho, params=None):
        url = self.base + caminho
        if params:
            url += '?' + urllib.parse.urlencode(params)
        ultimo = None
        for i in range(self.tentativas):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT,
                                                           'Accept': 'application/json'})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    self.requisicoes += 1
                    dados = json.loads(r.read().decode('utf-8'))
                time.sleep(self.pausa)
                return dados
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    return {'_erro': e.code}
                ultimo = e
            except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
                ultimo = e   # ValueError: corpo não-JSON (ex.: desafio anti-bot)
            time.sleep(1.5 * (i + 1))
        return {'_erro': str(ultimo)}

    def pagina(self, page_id, com_corpo=True):
        expand = 'version,ancestors,space' + (',body.storage' if com_corpo else '')
        return self._get(f'/rest/api/content/{page_id}', {'expand': expand})

    def filhas(self, page_id):
        res, inicio = [], 0
        while True:
            d = self._get(f'/rest/api/content/{page_id}/child/page', {'limit': 100, 'start': inicio})
            if '_erro' in d:
                return res
            res.extend(d.get('results', []))
            if d.get('size', 0) < d.get('limit', 100):
                return res
            inicio += d.get('limit', 100)

    def por_titulo(self, espaco, titulo):
        d = self._get('/rest/api/content', {'spaceKey': espaco, 'title': titulo})
        r = d.get('results') or []
        return r[0]['id'] if r else None


def chave_titulo(espaco, titulo):
    """Chave tolerante para casar títulos citados em links com títulos
    reais (travessão × hífen, NBSP, caixa, espaços repetidos)."""
    t = unescape(titulo).replace('–', '-').replace('—', '-').replace(' ', ' ')
    return (espaco or '').upper(), re.sub(r'\s+', ' ', t).strip().casefold()


# ---------------------------------------------------------------- links

_RE_HREF = re.compile(r'href="([^"]+)"')
_RE_RI_PAGE = re.compile(r'<ri:page\s+([^>]*?)/?>')
_RE_ATTR = re.compile(r'([\w:-]+)="([^"]*)"')


def extrair_links(storage, base_hosts, espaco_padrao):
    """Devolve lista de referências {'tipo','valor','espaco'} encontradas no
    corpo (pageId explícito, /display/ESPACO/Titulo ou <ri:page>). Links
    para fora dos hosts da fonte viram tipo 'externo' (só registrados)."""
    refs = []
    for href in _RE_HREF.findall(storage or ''):
        href = unescape(href)
        p = urllib.parse.urlparse(href)
        host = (p.netloc or '').lower()
        if host and not any(host.endswith(h) for h in base_hosts):
            refs.append({'tipo': 'externo', 'valor': href})
            continue
        q = urllib.parse.parse_qs(p.query)
        if 'pageId' in q:
            refs.append({'tipo': 'id', 'valor': q['pageId'][0]})
        elif p.path.startswith('/display/'):
            partes = p.path.split('/')
            if len(partes) >= 4:
                refs.append({'tipo': 'titulo', 'espaco': partes[2],
                             'valor': urllib.parse.unquote_plus(partes[3])})
    for attrs in _RE_RI_PAGE.findall(storage or ''):
        a = dict(_RE_ATTR.findall(attrs))
        if 'ri:content-title' in a:
            refs.append({'tipo': 'titulo', 'espaco': a.get('ri:space-key', espaco_padrao),
                         'valor': unescape(a['ri:content-title'])})
    return refs


def _texto_simples(storage):
    return unescape(re.sub(r'<[^>]+>', ' ', storage or ''))


# ---------------------------------------------------------------- crawler

class Rastreador:
    """Executa a descoberta descrita no topo do módulo e grava `bruto/`."""

    def __init__(self, fonte, dir_pacote, log=print):
        self.fonte = fonte
        self.dir_bruto = os.path.join(dir_pacote, 'bruto')
        os.makedirs(self.dir_bruto, exist_ok=True)
        self.cli = ClienteConfluence(fonte['base_url'], pausa=fonte.get('pausa_segundos', 0.25))
        regras = fonte.get('relevancia', {})
        self.padroes = [re.compile(p, re.I) for p in regras.get('padroes_conteudo', [])]
        self.padroes_titulo = [re.compile(p, re.I) for p in regras.get('padroes_titulo', [])]
        self.min_padroes = regras.get('minimo_padroes', len(self.padroes))
        self.espacos = set(regras.get('espacos_permitidos', []))
        self.prof_max = regras.get('profundidade_links', 2)
        self.limite = fonte.get('limite_paginas', 3000)
        self.hosts = [urllib.parse.urlparse(fonte['base_url']).netloc.lower()] + \
            [h.lower() for h in fonte.get('hosts_equivalentes', [])]
        self.log = log
        self.manifesto = {}   # page_id -> registro
        self.titulos = {}     # chave_titulo -> page_id (páginas já vistas)
        self.excluidas = {str(x) for x in fonte.get('excluir_page_ids', [])}
        aprovadas = fonte.get('paginas_aprovadas')
        self.aprovadas = None if aprovadas is None else (
            {str(x) for x in aprovadas} | {str(sm['page_id']) for sm in fonte['sementes']})

    # -- util
    def _url(self, pid):
        return f"{self.fonte['base_url'].rstrip('/')}/pages/releaseview.action?pageId={pid}"

    def _caminho(self, pid):
        return os.path.join(self.dir_bruto, f'{pid}.json')

    def _relevante(self, titulo, storage):
        """Relevante se o TÍTULO casa algum `padroes_titulo` ou se o
        conteúdo casa pelo menos `minimo_padroes` de `padroes_conteudo`."""
        hits_t = [p.pattern for p in self.padroes_titulo if p.search(titulo or '')]
        txt = _texto_simples(storage)
        hits = [p.pattern for p in self.padroes if p.search(txt)]
        if hits_t:
            return True, ['título: ' + h for h in hits_t] + hits
        return len(hits) >= self.min_padroes, hits

    def _obter(self, pid):
        """Baixa (ou reaproveita, se a versão não mudou) a página bruta."""
        meta = self.cli.pagina(pid, com_corpo=False)
        if '_erro' in meta:
            return None, f"erro HTTP/rede: {meta['_erro']}"
        caminho = self._caminho(pid)
        if os.path.exists(caminho):
            with open(caminho, encoding='utf-8') as f:
                antigo = json.load(f)
            if antigo.get('versao') == meta['version']['number']:
                return antigo, None
        d = self.cli.pagina(pid, com_corpo=True)
        if '_erro' in d:
            return None, f"erro HTTP/rede: {d['_erro']}"
        storage = d['body']['storage']['value']
        bruto = {
            'page_id': d['id'],
            'titulo': d['title'],
            'url': self._url(d['id']),
            'espaco': d['space']['key'],
            'versao': d['version']['number'],
            'atualizado_em': d['version'].get('when'),
            'ancestrais': [{'page_id': a['id'], 'titulo': a['title']} for a in d.get('ancestors', [])],
            'coletado_em': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'sha256_storage': hashlib.sha256(storage.encode('utf-8')).hexdigest(),
            'storage': storage,
        }
        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump(bruto, f, ensure_ascii=False, indent=1)
        return bruto, None

    def _registrar(self, pid, **kw):
        reg = self.manifesto.setdefault(pid, {'page_id': pid, 'descoberta_via': []})
        via = kw.pop('via', None)
        if via and via not in reg['descoberta_via']:
            reg['descoberta_via'].append(via)
        reg.update({k: v for k, v in kw.items() if v is not None})
        return reg

    # -- descoberta
    def executar(self):
        fila = []  # (pid, semente, contexto, profundidade_link, na_arvore, via)
        for s in self.fonte['sementes']:
            fila.append((str(s['page_id']), s['page_id'], s.get('contexto'), 0, True, 'semente'))
        titulos_resolvidos = {}

        while fila:
            pid, semente, contexto, prof, na_arvore, via = fila.pop(0)
            reg = self.manifesto.get(pid)
            if reg and reg.get('status'):
                # Uma página vista primeiro por link (descartada por relevância
                # ou processada com o contexto de quem a citou) e depois achada
                # como descendente de semente é reprocessada: pertencer à árvore
                # prevalece, inclusive no contexto.
                vista_por_link = reg['status'] == 'fora_de_escopo' or (
                    reg['status'] == 'processada' and not reg.get('na_arvore'))
                if not (na_arvore and vista_por_link):
                    self._registrar(pid, via=via)
                    continue
            if pid in self.excluidas:
                self._registrar(pid, via=via, status='excluida', motivo='excluída por id no fonte.json',
                                url=self._url(pid))
                continue
            if na_arvore and self.aprovadas is not None and pid not in self.aprovadas:
                meta = self.cli.pagina(pid, com_corpo=False)
                self._registrar(pid, via=via, status='nova_na_arvore', url=self._url(pid),
                                titulo=meta.get('title') if '_erro' not in meta else None,
                                semente=str(semente), contexto=contexto,
                                motivo='página nova na árvore da semente: só entra com o aceite do usuário '
                                       '(acrescente o id em paginas_aprovadas, ou em excluir_page_ids)')
                continue
            if len(self.manifesto) >= self.limite:
                self._registrar(pid, via=via, status='nao_processada',
                                motivo=f'limite de {self.limite} páginas atingido')
                continue
            bruto, erro = self._obter(pid)
            if erro:
                self._registrar(pid, via=via, status='erro', motivo=erro, url=self._url(pid))
                continue
            relevante, hits = self._relevante(bruto['titulo'], bruto['storage'])
            if not na_arvore and bruto['espaco'] not in self.espacos:
                status, motivo = 'fora_de_escopo', f"espaço {bruto['espaco']} fora da lista permitida"
            elif not na_arvore and not relevante:
                status, motivo = 'fora_de_escopo', 'título/conteúdo sem os padrões de relevância da fonte'
            else:
                status, motivo = 'processada', ('árvore da semente' if na_arvore else
                                                f'link relevante (padrões: {", ".join(hits)})')
            self.titulos[chave_titulo(bruto['espaco'], bruto['titulo'])] = pid
            self._registrar(pid, via=via, status=status, motivo=motivo, titulo=bruto['titulo'],
                            url=bruto['url'], versao=bruto['versao'], espaco=bruto['espaco'],
                            semente=str(semente), contexto=contexto, na_arvore=na_arvore,
                            relevante_por_conteudo=relevante,
                            caminho=' > '.join(a['titulo'] for a in bruto['ancestrais'][-3:]))
            self.log(f"[{len(self.manifesto):4d}] {status:15s} {pid} {bruto['titulo'][:70]}")
            if status != 'processada':
                continue

            # 1) descendentes — herdam `na_arvore` da mãe: filhas de uma
            #    página externa relevante continuam sujeitas ao filtro de
            #    relevância (evita absorver uma árvore inteira de outro produto)
            for filha in self.cli.filhas(pid):
                self.titulos[chave_titulo(bruto['espaco'], filha['title'])] = filha['id']
                fila.append((filha['id'], semente, contexto, prof, na_arvore, f'filha de {pid}'))

            # 2) links do corpo
            if prof >= self.prof_max:
                continue
            for ref in extrair_links(bruto['storage'], self.hosts, bruto['espaco']):
                if ref['tipo'] == 'externo':
                    self.manifesto.setdefault('_externos', {'links': []})
                    lst = self.manifesto['_externos']['links']
                    item = {'de': pid, 'url': ref['valor']}
                    if item not in lst:
                        lst.append(item)
                    continue
                if ref['tipo'] == 'titulo':
                    chave = (ref['espaco'], ref['valor'])
                    alvo = self.titulos.get(chave_titulo(*chave))
                    if not alvo:
                        if chave not in titulos_resolvidos:
                            titulos_resolvidos[chave] = self.cli.por_titulo(*chave)
                        alvo = titulos_resolvidos[chave]
                    if not alvo:
                        self._registrar(f"titulo:{ref['espaco']}:{ref['valor']}", via=f'link em {pid}',
                                        status='erro', motivo='título não resolvido')
                        continue
                else:
                    alvo = ref['valor']
                if alvo == pid:
                    continue
                fila.append((alvo, semente, contexto, prof + 1, False, f'link em {pid}'))
        return self.manifesto
