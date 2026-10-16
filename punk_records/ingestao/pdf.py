"""
Conector genérico para documentação em ARQUIVO PDF local (sem rede).

Mesmo contrato do conector de wiki: recebe a configuração da fonte
(`fonte.json` do pacote) e devolve páginas BRUTAS + manifesto, que o
normalizador transforma em fichas. Não sabe nada de fornecedor nem de
fórmulas — tudo o que é específico do documento mora no `fonte.json`:

    "conector": "pdf",
    "arquivos": [{"id": "manual", "caminho": "origem/manual.pdf",
                  "contexto": "CTX", "paginas": [1, 73]}],
    "remover_linhas": ["^regex de cabeçalho/rodapé$", ...],
    "padrao_secao": "^\\d+(?:\\.\\d+)*\\.\\s+\\S",   # abre uma nova seção
    "normalizar_aspas_tipograficas": true

Segmentação: o texto do PDF (extraído com `pdftotext -layout`, do poppler)
é dividido em SEÇÕES pelo `padrao_secao` — uma seção vira uma "página"
bruta, com a página do PDF onde começa (`#page=N` na URL) e o intervalo de
páginas que cobre. Assim um bloco de função que atravessa a quebra de
página do PDF não é cortado ao meio.

Linhas de cabeçalho/rodapé repetidas (título do manual, número de página,
versão) são removidas pelas regex da fonte. Linhas de prosa quebradas pelo
layout (linha longa seguida de linha que começa em minúscula) são
reunidas. Aspas tipográficas (‘ ’ “ ”), que o editor de texto do manual
introduz e o dialeto não aceita, podem ser trocadas pelas retas — o texto
como saiu do PDF fica preservado em `texto_extraido` no bruto.

Incremental: se o SHA-256 do arquivo não mudou, o bruto existente é mantido.
"""

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

_ASPAS = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '´': "'"})


class _SemRede:
    requisicoes = 0


def _sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 16), b''):
            h.update(bloco)
    return h.hexdigest()


def _pdftotext(caminho, pagina):
    if not shutil.which('pdftotext'):
        raise SystemExit('pdftotext (poppler-utils) não encontrado — necessário para o conector pdf')
    r = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', '-f', str(pagina), '-l', str(pagina), caminho, '-'],
                       capture_output=True, text=True, check=True)
    return r.stdout


def _total_paginas(caminho):
    if shutil.which('pdfinfo'):
        r = subprocess.run(['pdfinfo', caminho], capture_output=True, text=True)
        m = re.search(r'^Pages:\s+(\d+)', r.stdout, re.M)
        if m:
            return int(m.group(1))
    return None


def _data_pdf(caminho):
    if shutil.which('pdfinfo'):
        r = subprocess.run(['pdfinfo', '-isodates', caminho], capture_output=True, text=True)
        m = re.search(r'^(?:ModDate|CreationDate):\s+(\S+)', r.stdout, re.M)
        if m:
            return m.group(1)
    return None


def linhas_limpas(texto_pagina, remover):
    """Texto de UMA página -> linhas (sem cabeçalho/rodapé, sem recuo)."""
    out = []
    for bruta in texto_pagina.replace('\f', '').split('\n'):
        t = re.sub(r'[ \t\xa0]+', ' ', bruta).strip()
        t = t.lstrip('\uf0b7\uf0a7\uf0d8•').strip()        # marcadores de lista do editor
        if not t or any(rx.search(t) for rx in remover):
            out.append('')                                   # preserva separação de parágrafo
            continue
        out.append(t)
    return out


def reunir_quebras(linhas, largura_min=95):
    """Junta prosa que o layout quebrou: linha longa + continuação em minúscula."""
    out = []
    for t in linhas:
        if out and t and out[-1] and len(out[-1]) >= largura_min and re.match(r'[a-zà-ú(]', t):
            out[-1] = out[-1] + ' ' + t
        else:
            out.append(t)
    return out


def segmentar(paginas_linhas, padrao_secao, ignorar_secao=None):
    """[(nº página, [linhas])] -> seções [{titulo, pagina_inicial, pagina_final, linhas}]."""
    rx = re.compile(padrao_secao)
    rx_ign = re.compile(ignorar_secao) if ignorar_secao else None
    secoes, atual = [], None
    for n, linhas in paginas_linhas:
        for t in linhas:
            if t and rx.search(t) and not (rx_ign and rx_ign.search(t)):
                atual = {'titulo': t, 'pagina_inicial': n, 'pagina_final': n, 'linhas': []}
                secoes.append(atual)
                continue
            if atual is None:
                atual = {'titulo': '(preâmbulo)', 'pagina_inicial': n, 'pagina_final': n, 'linhas': []}
                secoes.append(atual)
            atual['linhas'].append(t)
            atual['pagina_final'] = n
    return secoes


def para_storage(titulo, linhas):
    """Seção -> HTML mínimo (um <p> por linha), no formato que `html_linhas` lê."""
    partes = [f'<h2>{html.escape(titulo)}</h2>']
    partes += [f'<p>{html.escape(t)}</p>' for t in linhas if t]
    return ''.join(partes)


class Rastreador:
    def __init__(self, fonte, dir_pacote, log=print):
        self.fonte = fonte
        self.dir = dir_pacote
        self.dir_bruto = os.path.join(dir_pacote, 'bruto')
        os.makedirs(self.dir_bruto, exist_ok=True)
        self.log = log
        self.cli = _SemRede()
        self.remover = [re.compile(p) for p in fonte.get('remover_linhas', [])]
        self.padrao_secao = fonte.get('padrao_secao', r'^\d+(?:\.\d+)*\.\s+\S')
        self.ignorar_secao = fonte.get('ignorar_secao')
        self.aspas = fonte.get('normalizar_aspas_tipograficas', False)

    def executar(self):
        manifesto = {}
        for arq in self.fonte.get('arquivos', []):
            caminho = os.path.join(self.dir, arq['caminho'])
            if not os.path.exists(caminho):
                raise SystemExit(f'{caminho} não existe (ver "arquivos" no fonte.json)')
            sha = _sha256_arquivo(caminho)
            total = _total_paginas(caminho)
            ini, fim = (arq.get('paginas') or [1, total])
            data = _data_pdf(caminho)
            nome = os.path.basename(caminho)
            pags = []
            for n in range(ini, (fim or ini) + 1):
                pags.append((n, reunir_quebras(linhas_limpas(_pdftotext(caminho, n), self.remover))))
            secoes = segmentar(pags, self.padrao_secao, self.ignorar_secao)
            for i, s in enumerate(secoes, 1):
                pid = f"{arq['id']}-s{i:03d}"
                extraido = '\n'.join(s['linhas'])
                linhas = [t.translate(_ASPAS) for t in s['linhas']] if self.aspas else s['linhas']
                titulo = s['titulo'].translate(_ASPAS) if self.aspas else s['titulo']
                storage = para_storage(titulo, linhas)
                bruto = {
                    'page_id': pid, 'titulo': titulo,
                    'url': f"arquivo://{nome}#page={s['pagina_inicial']}",
                    'espaco': arq['id'], 'versao': 1, 'atualizado_em': data,
                    'ancestrais': [], 'coletado_em': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'arquivo': nome, 'sha256_arquivo': sha,
                    'paginas_pdf': [s['pagina_inicial'], s['pagina_final']],
                    'sha256_storage': hashlib.sha256(storage.encode('utf-8')).hexdigest(),
                    'storage': storage, 'texto_extraido': extraido,
                }
                with open(os.path.join(self.dir_bruto, f'{pid}.json'), 'w', encoding='utf-8') as f:
                    json.dump(bruto, f, ensure_ascii=False, indent=1)
                manifesto[pid] = {
                    'page_id': pid, 'descoberta_via': [f"arquivo {nome}"], 'status': 'processada',
                    'motivo': 'seção do arquivo', 'titulo': titulo, 'url': bruto['url'], 'versao': 1,
                    'espaco': arq['id'], 'contexto': arq.get('contexto'), 'na_arvore': True,
                    'paginas_pdf': bruto['paginas_pdf'], 'sha256_arquivo': sha,
                }
                self.log(f"[{len(manifesto):4d}] processada  {pid} p.{s['pagina_inicial']}-{s['pagina_final']} "
                         f"{titulo[:60]}")
        return manifesto
