"""
Normalização de um pacote de conhecimento: `bruto/` + `paginas.json` ->
`funcoes.json`, `documentos.json` e `relatorio_ingestao.json`.

Regras:
  * nada é inventado — campo que a documentação não traz fica
    `null`/'nao_documentado' e entra em `nao_documentado`;
  * duplicidade = mesma função (NOME) no mesmo CONTEXTO vinda de mais de
    uma página/bloco: vira UM registro com várias `origens`; informação
    única de cada origem é preservada (sintaxes, descrições alternativas,
    exemplos e observações são unidos, não sobrescritos);
  * o mesmo NOME em contextos diferentes (ex.: GLOBAL × FOP) continua em
    registros separados, ligados por `mesmo_nome_em`;
  * toda ficha guarda a(s) origem(ns): page_id, URL, título, versão da
    página, data de atualização e hash do conteúdo bruto usado.
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

from dominios.formulas.texto import normalizar
from .extrator_funcoes import extrair_pagina, _extrair_chamadas, IDENT
from .html_linhas import converter
from dominios.formulas.sintaxe import analisar, percorrer


def _ler(caminho, padrao=None):
    if not os.path.exists(caminho):
        return padrao
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def _dialeto_da_fonte(dir_pacote, fonte):
    """Dialeto próprio do pacote; se não tiver e ESTENDER outro pacote, o
    dialeto do pacote-base (procurado na raiz de conhecimento) — sem copiar o
    arquivo, para o motor continuar com UM dialeto carregado."""
    proprio = os.path.join(dir_pacote, fonte.get('dialeto', 'dialeto.json'))
    if os.path.exists(proprio) or not fonte.get('estende'):
        return _ler(proprio, {})
    from dominios.formulas import conhecimento as kb
    # primeiro a raiz onde o próprio pacote está (<raiz>/<camada>/<id>), depois a padrão
    raiz_local = os.path.dirname(os.path.dirname(os.path.abspath(dir_pacote)))
    for raiz in (raiz_local, None):
        for p in kb.descobrir_pacotes(raiz):
            if p.id == fonte['estende'] and p.dialeto:
                return p.dialeto
    raise SystemExit(f"pacote-base '{fonte['estende']}' (com dialeto) não encontrado")


def _tipo_retorno_normalizado(txt, regras):
    if not txt:
        return 'nao_documentado'
    n = normalizar(txt).upper()
    for tipo, palavras in regras.items():
        for p in palavras:
            if normalizar(p).upper() in n:
                return tipo
    return 'desconhecido'


def _uniao(lista, chave):
    vistos, out = set(), []
    for x in lista:
        k = chave(x)
        if k not in vistos:
            vistos.add(k)
            out.append(x)
    return out


def normalizar_pacote(dir_pacote, log=print):
    fonte = _ler(os.path.join(dir_pacote, 'fonte.json'))
    dialeto = _dialeto_da_fonte(dir_pacote, fonte)
    manifesto = _ler(os.path.join(dir_pacote, 'paginas.json'), {})
    # Pacote que ESTENDE outro (ex.: complemento privado) gera fichas no
    # namespace do pacote-base, para o merge por id funcionar (mesma regra de
    # conhecimento.Pacote); documentos e receitas ficam com o id próprio.
    id_proprio = fonte['id']
    pacote = fonte.get('estende') or id_proprio

    fichas_por_chave = defaultdict(list)
    documentos = []
    paginas_sem_funcao = []
    funcoes_por_pagina = {}

    for pid, reg in sorted(manifesto.items()):
        if pid.startswith('_') or reg.get('status') != 'processada':
            continue
        bruto = _ler(os.path.join(dir_pacote, 'bruto', f'{pid}.json'))
        if not bruto:
            continue
        origem = {
            'pacote': id_proprio, 'page_id': bruto['page_id'], 'url': bruto['url'],
            'titulo_pagina': bruto['titulo'], 'versao_pagina': bruto['versao'],
            'atualizado_em': bruto.get('atualizado_em'), 'sha256_bruto': bruto['sha256_storage'],
            'relacao_com_semente': 'arvore' if reg.get('na_arvore') else 'link',
        }
        contexto = reg.get('contexto') or 'GLOBAL'
        linhas = converter(bruto['storage'])
        fichas = extrair_pagina(bruto, linhas, dialeto)
        funcoes_por_pagina[pid] = [f['nome'] for f in fichas]
        for f in fichas:
            f['origem'] = dict(origem)
            fichas_por_chave[(contexto, f['nome'])].append(f)
        # Toda página processada também vira DOCUMENTO de referência (texto
        # integral), para explicação e para conhecimento que não é ficha de
        # função (regras da linguagem, conceitos, notas de release...).
        texto = '\n'.join(l.texto for l in linhas)
        documentos.append({
            'id': f'{id_proprio}:doc:{pid}', 'contexto': contexto, 'titulo': bruto['titulo'],
            'tipo': 'pagina_de_funcoes' if fichas else 'artigo', 'texto': texto,
            'funcoes_extraidas': [f['nome'] for f in fichas], 'origem': origem,
        })
        if not fichas:
            paginas_sem_funcao.append({'page_id': pid, 'titulo': bruto['titulo'], 'contexto': contexto})

    regras_ret = dialeto.get('tipos_retorno', {})
    funcoes = []
    duplicidades = []
    conflitos = []
    exemplos_invalidos = []
    for (contexto, nome), fichas in sorted(fichas_por_chave.items()):
        ordem_conf = {'alta': 0, 'media': 1, 'baixa': 2}
        fichas.sort(key=lambda f: (ordem_conf[f['confianca_extracao']], -len(f['texto_original'])))
        base = fichas[0]
        if len(fichas) > 1:
            duplicidades.append({'contexto': contexto, 'nome': nome,
                                 'ocorrencias': [(f['origem']['page_id'], f['padrao_layout']) for f in fichas]})
        descricoes = _uniao([f['descricao'] for f in fichas if f['descricao']], lambda d: normalizar(d))
        assinaturas = _uniao([a for f in fichas for a in f['assinaturas']],
                             lambda a: re.sub(r'\s+', '', normalizar(a['texto'])))
        retornos = _uniao([f['tipo_retorno_documentado'] for f in fichas if f['tipo_retorno_documentado']],
                          lambda r: normalizar(r))
        if len({_tipo_retorno_normalizado(r, regras_ret) for r in retornos}) > 1:
            conflitos.append({'contexto': contexto, 'nome': nome, 'campo': 'tipo_retorno', 'valores': retornos})
        aridades = {len(a['argumentos']) for a in assinaturas if a['tem_parenteses']}
        # conflito = ORIGENS diferentes documentando aridades diferentes
        # (alternativas na mesma ficha, "F(A) ou F(A, B)", não são conflito)
        por_ficha = {frozenset(len(a['argumentos']) for a in f['assinaturas'] if a['tem_parenteses'])
                     for f in fichas if f['assinaturas']}
        if len(por_ficha) > 1:
            conflitos.append({'contexto': contexto, 'nome': nome, 'campo': 'aridade',
                              'valores': [a['texto'] for a in assinaturas]})
        exemplos = _uniao([e for f in fichas for e in f['exemplos']], lambda e: normalizar(e['codigo']))
        for e in exemplos:
            # O exemplo foi copiado da documentação. Se nem o parser do
            # dialeto aceita, fica marcado (não é "corrigido") — e não pode
            # ser usado como modelo de composição.
            _, erros, _ = analisar(e['codigo'], dialeto)
            e['valido_no_dialeto'] = not erros
            if erros:
                e['erro_parser'] = erros[0]['mensagem']
                exemplos_invalidos.append({'funcao': f'{pacote}:{contexto}:{nome}', 'codigo': e['codigo'],
                                           'erro': erros[0]['mensagem']})
        observacoes = _uniao([o for f in fichas for o in f['observacoes']], lambda o: normalizar(o['texto']))
        nao_doc = sorted(set.intersection(*[set(f['nao_documentado']) for f in fichas]))
        avisos = _uniao([a for f in fichas for a in f['avisos_extracao']], lambda a: a)
        conf = base['confianca_extracao']
        funcoes.append({
            'id': f'{pacote}:{contexto}:{nome}',
            'nome': nome,
            'contexto': contexto,
            'pacote': pacote,
            'categoria': 'nao_documentado',
            'grupo_documentacao': sorted({f['origem']['titulo_pagina'] for f in fichas}),
            'descricao': descricoes[0] if descricoes else None,
            'descricoes_alternativas': descricoes[1:],
            'assinaturas': assinaturas,
            'parametros': base['parametros'],
            'aridades_documentadas': sorted(aridades) if aridades else ([0] if assinaturas else []),
            'aceita_sem_parenteses': any(not a['tem_parenteses'] for a in assinaturas),
            'tipo_retorno_documentado': retornos[0] if retornos else None,
            'tipo_retorno_alternativo': retornos[1:],
            'tipo_retorno': _tipo_retorno_normalizado(retornos[0] if retornos else None, regras_ret),
            'exemplos': exemplos,
            'observacoes': observacoes,
            'restricoes': [o for o in observacoes if re.search(r'n[ãa]o\s+(dev|pode|poder)', normalizar(o['texto']))],
            'relacionadas': [],
            'mesmo_nome_em': [],
            'nao_documentado': nao_doc,
            'avisos_extracao': avisos,
            'confianca_extracao': conf,
            'origens': [f['origem'] for f in fichas],
            'texto_original': [f['texto_original'] for f in fichas],
        })

    # --- restrições de uso declaradas pela FONTE (regex em fonte.json) ------
    # Ex.: a documentação diz que certas variáveis "não devem ser utilizadas
    # para fórmula de seleção". O motor não conhece essa frase; a fonte
    # declara o padrão e o rótulo de uso, e o validador aplica.
    regras = [(re.compile(r['padrao'], re.I), r['uso_proibido']) for r in fonte.get('regras_restricao', [])]
    for f in funcoes:
        usos = {}
        for txt in f['texto_original']:
            for rx, uso in regras:
                m = rx.search(txt)
                if m and uso not in usos:
                    ini = max(0, m.start() - 80)
                    usos[uso] = txt[ini:m.end() + 40].replace('\n', ' ')
        f['usos_proibidos'] = [{'uso': u, 'evidencia': e} for u, e in sorted(usos.items())]

    # --- aridades observadas em exemplos documentados ----------------------
    # Se a documentação USA uma função com N argumentos num exemplo válido,
    # mas a sintaxe declarada diz outra coisa, isso é evidência (registrada
    # com a fonte) — o validador aceita com AVISO, não em silêncio.
    usos = defaultdict(list)
    for f in funcoes:
        for e in f['exemplos']:
            if not e.get('valido_no_dialeto'):
                continue
            ast, _, _ = analisar(e['codigo'], dialeto)
            for no in percorrer(ast):
                if no.get('tipo') == 'chamada':
                    usos[(f['contexto'], no['nome'])].append(
                        (len(no['args']), e['codigo'], f['origens'][0]['url']))
    # nomes usados em exemplos válidos da documentação que NÃO têm ficha em
    # nenhum contexto: lacuna da documentação (ou variável não declarada no
    # trecho). Ficam fora do dicionário — só listados para revisão humana.
    todos_nomes = {f['nome'] for f in funcoes}
    sem_ficha = defaultdict(set)
    for f in funcoes:
        for e in f['exemplos']:
            if not e.get('valido_no_dialeto'):
                continue
            ast, _, _ = analisar(e['codigo'], dialeto)
            decl = {n for no in percorrer(ast) if no.get('tipo') == 'declaracao' for n in no['nomes']}
            for no in percorrer(ast):
                if no.get('tipo') in ('chamada', 'identificador') and no['nome'] not in todos_nomes \
                        and no['nome'] not in decl:
                    sem_ficha[no['nome']].add(f['origens'][0]['page_id'])
    for f in funcoes:
        extra = {}
        for n, cod, url in usos.get((f['contexto'], f['nome']), []):
            if n not in f['aridades_documentadas'] and n not in extra:
                extra[n] = {'aridade': n, 'exemplo': cod, 'url': url}
        f['aridades_em_exemplos'] = [extra[k] for k in sorted(extra)]

    # --- relações (só entre funções que EXISTEM no dicionário) ------------
    contextos_cfg = fonte.get('contextos', {})
    por_nome = defaultdict(list)
    for f in funcoes:
        por_nome[f['nome']].append(f)
    for f in funcoes:
        visiveis = {f['contexto']} | set(contextos_cfg.get(f['contexto'], {}).get('herda', []))
        rel = {}
        for e in f['exemplos']:
            for n, _ in _extrair_chamadas(e['codigo']):
                n = n.upper()
                if n != f['nome'] and any(g['contexto'] in visiveis for g in por_nome.get(n, [])):
                    rel.setdefault(n, set()).add('usada_em_exemplo')
        for txt in f['texto_original'] + [o['texto'] for o in f['observacoes']]:
            for m in re.finditer(r'\b(' + IDENT + r')\b', txt):
                n = m.group(1)
                if len(n) < 3 or not n.isupper() or n == f['nome']:
                    continue
                if any(g['contexto'] in visiveis for g in por_nome.get(n, [])):
                    rel.setdefault(n, set()).add('citada_no_texto')
        f['relacionadas'] = [{'nome': n, 'evidencia': sorted(v)} for n, v in sorted(rel.items())]
        f['mesmo_nome_em'] = sorted(g['contexto'] for g in por_nome[f['nome']] if g is not f)

    # --- cobertura -----------------------------------------------------------
    nomes = {f['nome'] for f in funcoes}
    citadas_sem_ficha = defaultdict(set)
    for d in documentos:
        for m in re.finditer(r'(?:fun[çc][ãa]o|vari[áa]vel)(?:\s+de\s+f[óo]rmula)?\s+(' + IDENT + r')', d['texto'], re.I):
            n = m.group(1)
            if n.isupper() and len(n) >= 2 and n not in nomes:
                citadas_sem_ficha[n].add(d['origem']['page_id'])
    relatorio = {
        'pacote': id_proprio,
        'gerado_em': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'paginas_no_manifesto': len([k for k in manifesto if not k.startswith('_')]),
        'paginas_por_status': {s: len([1 for k, v in manifesto.items() if not k.startswith('_') and v.get('status') == s])
                               for s in ('processada', 'fora_de_escopo', 'erro', 'nao_processada', 'excluida',
                                         'nova_na_arvore')},
        'novas_na_arvore': [{'ref': k, **{c: v.get(c) for c in ('titulo', 'semente', 'contexto', 'descoberta_via')}}
                            for k, v in manifesto.items() if not k.startswith('_') and v.get('status') == 'nova_na_arvore'],
        'paginas_nao_processadas': [{'ref': k, **{c: v.get(c) for c in ('titulo', 'status', 'motivo', 'descoberta_via')}}
                                    for k, v in manifesto.items() if not k.startswith('_') and v.get('status') != 'processada'],
        'links_externos_registrados': manifesto.get('_externos', {}).get('links', []),
        'funcoes_total': len(funcoes),
        'funcoes_por_contexto': {c: len([f for f in funcoes if f['contexto'] == c]) for c in sorted({f['contexto'] for f in funcoes})},
        'funcoes_por_confianca': {c: len([f for f in funcoes if f['confianca_extracao'] == c]) for c in ('alta', 'media', 'baixa')},
        'funcoes_baixa_confianca': [f['id'] for f in funcoes if f['confianca_extracao'] == 'baixa'],
        'duplicidades_consolidadas': duplicidades,
        'conflitos_entre_origens': conflitos,
        'exemplos_documentados_que_nao_passam_no_parser': exemplos_invalidos,
        'paginas_sem_ficha_de_funcao': paginas_sem_funcao,
        'funcoes_por_pagina': funcoes_por_pagina,
        'citadas_no_texto_sem_ficha': {k: sorted(v) for k, v in sorted(citadas_sem_ficha.items())},
        'usados_em_exemplos_sem_ficha': {k: sorted(v) for k, v in sorted(sem_ficha.items())},
    }

    # --- receitas: programas de exemplo DOCUMENTADOS e válidos no dialeto ---
    # (padrões reais de composição — SE/REPITA/DECL — com origem rastreável)
    est = dialeto.get('estruturas', {})
    chaves = [v for v in (est.get('condicional', {}).get('inicio'), est.get('repeticao', {}).get('inicio'),
                          est.get('declaracao', {}).get('palavra')) if v]
    rx_prog = re.compile(r'\b(' + '|'.join(map(re.escape, chaves)) + r')\b', re.I) if chaves else None
    receitas, vistos = [], set()
    for f in funcoes:
        for e in f['exemplos']:
            if not (e.get('valido_no_dialeto') and rx_prog and rx_prog.search(e['codigo'])):
                continue
            chave = re.sub(r'\s+', '', normalizar(e['codigo']))
            if chave in vistos:
                continue
            vistos.add(chave)
            receitas.append({
                'id': f"{id_proprio}:receita:{len(receitas) + 1:03d}",
                'nome': f"Exemplo documentado de {f['nome']}",
                'contexto': f['contexto'],
                'descricao': ' '.join(e.get('explicacao', [])) or f.get('descricao') or '',
                'formula': e['codigo'],
                'funcoes': sorted({n.upper() for n, _ in _extrair_chamadas(e['codigo'])}),
                'palavras_chave': [f['nome']] + [r['nome'] for r in f['relacionadas']],
                'origem': f['origens'][0],
            })
    relatorio['receitas_documentadas'] = len(receitas)

    for nome_arq, dados in (('funcoes.json', funcoes), ('documentos.json', documentos),
                            ('receitas.json', receitas), ('relatorio_ingestao.json', relatorio)):
        with open(os.path.join(dir_pacote, nome_arq), 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
    log(f"{pacote}: {len(funcoes)} funções, {len(documentos)} documentos, "
        f"{len(duplicidades)} duplicidades consolidadas, {len(conflitos)} conflitos registrados")
    return relatorio
