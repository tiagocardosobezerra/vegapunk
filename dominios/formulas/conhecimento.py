"""
Knowledge providers do motor de fórmulas.

Um PACOTE de conhecimento é um diretório com (todos opcionais, exceto
o manifesto):

    fonte.json | pacote.json   manifesto (id, nome, visibilidade, dialeto, contextos, estende)
    dialeto.json               regras da linguagem (ver sintaxe.py) — só pacotes-base
    funcoes.json               fichas de função (schema em referencias/formulas.md)
    documentos.json            textos de referência (artigos, páginas inteiras)
    sinonimos.json             {"termo coloquial": ["termo do dicionário", ...]}
    receitas.json              padrões de fórmula nomeados (com origem)
    anotacoes.json             {"<id ou NOME>": [{"texto": ..., "tipo": ...}]}

Camadas (ordem de carga = ordem de precedência para ANOTAR, nunca para
apagar conhecimento documentado):

    publico/   pacotes distribuíveis (podem ser publicados com o core)
    privado/   pacotes locais da instalação (nunca exigidos pelo core)
    + caminhos extras em VEGAPUNK_FORMULAS_PRIVADO (separados por os.pathsep)

O core não lê nada de `privado/` quando `somente_publico=True` — é assim que
a versão distribuível roda e é testada.
"""

import difflib
import json
import math
import os
from collections import defaultdict, Counter

from .texto import normalizar, tokens, radical

# Constantes do ranking de `buscar`. Calibradas contra os grupos calibracao +
# heldout de testes/casos_busca_formulas.json; o grupo validacao_cega nunca é
# usado para escolhê-las (ver satelites/pythagoras.py). Qualquer
# mudança aqui: rode a suíte e o test_formulas_busca_qualidade.
PESOS_CAMPO = {'nome': 3.0, 'descricao': 2.0, 'descricao_alternativa': 1.5, 'parametro': 1.0,
               'rotulo_parametro': 0.5, 'observacao': 0.6, 'exemplo': 0.5, 'anotacao': 1.2}
BONUS_NOME_CITADO = 10.0       # pedido cita o nome da função (ex.: "usar ARREDONDA")
COBERTURA_BASE = 0.5           # score *= COBERTURA_BASE + cobertura
COBERTURA_POR_IDF = True       # cobertura ponderada pelo IDF dos termos (senão, contagem):
                               # faltar 'funcionário' pesa menos que faltar 'base'
BONUS_DESCRICAO = 6.0          # + BONUS_DESCRICAO * fração da descrição coberta pelo pedido
INFINITIVO = True              # 'arredondar' ~ 'arredonda', 'converter' ~ 'converte'

# Mesma filosofia (e mesmos valores iniciais) do motor de consultas — NÃO
# calibrados para fórmulas ainda; recalibrar com satelites/pythagoras.py quando
# houver confirmações reais suficientes (`shaka.py confirmar`):
FUZZY_CUTOFF = 0.82            # termo do pedido sem nenhum match tenta correção aproximada
FUZZY_TAMANHO_MIN = 5          # só termos de 5+ letras (evita "corrigir" palavras curtas)
LIMIAR_AMBIGUIDADE = 0.12      # 1º e 2º colocados (nomes distintos) a menos de 12% = ambíguo

# VEGAPUNK_PACOTES aponta para outra raiz de pacotes (ex.: o Atlas, para provar
# que o domínio schema roda sem o dicionário de fórmulas).
VAR_AMBIENTE_PACOTES = 'VEGAPUNK_PACOTES'
RAIZ_CONHECIMENTO = os.environ.get(VAR_AMBIENTE_PACOTES) or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'punk_records', 'pacotes')
VAR_AMBIENTE_PRIVADO = 'VEGAPUNK_FORMULAS_PRIVADO'


def _rad(termo):
    """Radical usado no índice e no pedido (mesma função dos dois lados)."""
    r = radical(termo)
    if INFINITIVO and r == termo and len(termo) >= 6 and termo[-2:] in ('ar', 'er', 'ir'):
        return termo[:-1]
    return r


def _ler(caminho, padrao=None):
    if not os.path.exists(caminho):
        return padrao
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


class Pacote:
    def __init__(self, diretorio, camada):
        self.dir = os.path.abspath(diretorio)
        manifesto = _ler(os.path.join(self.dir, 'pacote.json')) or _ler(os.path.join(self.dir, 'fonte.json'))
        if not manifesto or 'id' not in manifesto:
            raise ValueError(f'{diretorio}: sem pacote.json/fonte.json com "id"')
        self.manifesto = manifesto
        self.id = manifesto['id']
        self.camada = camada                                  # 'publico' | 'privado'
        self.visibilidade = manifesto.get('visibilidade', camada)
        self.estende = manifesto.get('estende')               # id do pacote-base (privados)
        self.contextos = manifesto.get('contextos', {})
        ref_dialeto = manifesto.get('dialeto')
        self.dialeto = _ler(os.path.join(self.dir, ref_dialeto)) if ref_dialeto else None
        self.funcoes = _ler(os.path.join(self.dir, 'funcoes.json'), [])
        self.documentos = _ler(os.path.join(self.dir, 'documentos.json'), [])
        self.sinonimos = _ler(os.path.join(self.dir, 'sinonimos.json'), {})
        self.receitas = _ler(os.path.join(self.dir, 'receitas.json'), [])
        self.anotacoes = _ler(os.path.join(self.dir, 'anotacoes.json'), {})

    def resumo(self):
        return {'id': self.id, 'camada': self.camada, 'visibilidade': self.visibilidade,
                'estende': self.estende, 'funcoes': len(self.funcoes), 'documentos': len(self.documentos),
                'receitas': len(self.receitas), 'sinonimos': len(self.sinonimos), 'diretorio': self.dir}


def descobrir_pacotes(raiz=None, somente_publico=False, extras=None):
    raiz = os.path.abspath(raiz or RAIZ_CONHECIMENTO)
    achados = []
    camadas = [('publico', [os.path.join(raiz, 'publico')])]
    if not somente_publico:
        privados = [os.path.join(raiz, 'privado')]
        privados += [p for p in os.environ.get(VAR_AMBIENTE_PRIVADO, '').split(os.pathsep) if p]
        privados += list(extras or [])
        camadas.append(('privado', privados))
    for camada, bases in camadas:
        for base in bases:
            if not os.path.isdir(base):
                continue
            candidatos = [base] if any(os.path.exists(os.path.join(base, m)) for m in ('pacote.json', 'fonte.json')) \
                else [os.path.join(base, d) for d in sorted(os.listdir(base))]
            for d in candidatos:
                if os.path.isdir(d) and any(os.path.exists(os.path.join(d, m)) for m in ('pacote.json', 'fonte.json')):
                    achados.append(Pacote(d, camada))
    return achados


class BaseConhecimento:
    """Visão unificada (merge) dos pacotes carregados + índice de busca."""

    def __init__(self, pacotes):
        self.pacotes = pacotes
        self.avisos = []
        self.dialetos = {p.id: p.dialeto for p in pacotes if p.dialeto}
        self.contextos = {}
        self.funcoes = {}            # id -> ficha
        self.por_nome = defaultdict(list)
        self.documentos = []
        self.receitas = []
        self.sinonimos = defaultdict(set)
        for p in pacotes:
            base = p.estende or p.id
            for c, cfg in p.contextos.items():
                chave = (base, c)
                if chave in self.contextos and p.camada == 'privado':
                    # privado pode acrescentar herança, nunca remover
                    self.contextos[chave]['herda'] = sorted(set(self.contextos[chave]['herda']) |
                                                            set(cfg.get('herda', [])))
                else:
                    self.contextos[chave] = {'nome': cfg.get('nome', c), 'herda': list(cfg.get('herda', []))}
            for f in p.funcoes:
                self._incluir_funcao(dict(f), p)
            for d in p.documentos:
                self.documentos.append(dict(d, camada=p.camada))
            for r in p.receitas:
                self.receitas.append(dict(r, pacote=base, camada=p.camada))
            for termo, alvos in p.sinonimos.items():
                self.sinonimos[normalizar(termo)].update(normalizar(a) for a in alvos)
            for chave, notas in p.anotacoes.items():
                alvos = [self.funcoes[chave]] if chave in self.funcoes else \
                    [f for f in self.por_nome.get(chave.upper(), []) if f['pacote'] == base]
                if not alvos:
                    self.avisos.append(f'{p.id}: anotação para "{chave}", que não existe no dicionário — ignorada')
                for f in alvos:
                    f.setdefault('anotacoes', []).extend(dict(n, camada=p.camada, pacote_origem=p.id) for n in notas)
        self._indexar()
        self._tipos_inferidos()

    def _tipos_inferidos(self):
        """4d: `tipo_retorno_inferido` nas fichas sem tipo documentado cujo uso
        nas fontes limpas concorda (ver `tipos.py`). Com mais de um dialeto
        carregado, não infere (o exemplo não diz de qual dialeto é)."""
        self.sugestoes_de_tipo = {}
        if len(self.dialetos) != 1:
            return
        from .tipos import inferir
        r = inferir(self)
        for nome, inf in r['inferidos'].items():
            for f in self.por_nome.get(nome, []):
                if f.get('tipo_retorno') in ('nao_documentado', None, 'desconhecido', 'indefinido'):
                    f['tipo_retorno_inferido'] = {k: inf[k] for k in ('tipo', 'evidencia', 'ocorrencias')}
        self.sugestoes_de_tipo = r['sugestoes']

    # ------------------------------------------------------------- merge
    def _incluir_funcao(self, f, p):
        base = p.estende or p.id
        f.setdefault('pacote', base)
        f.setdefault('contexto', 'GLOBAL')
        f['id'] = f.get('id') or f"{base}:{f['contexto']}:{f['nome'].upper()}"
        f['nome'] = f['nome'].upper()
        f['camada'] = p.camada
        f.setdefault('origens', [{'pacote': p.id, 'camada': p.camada}])
        for o in f['origens']:
            o.setdefault('camada', p.camada)
        for campo, padrao in (('assinaturas', []), ('parametros', []), ('aridades_documentadas', []),
                              ('exemplos', []), ('observacoes', []), ('relacionadas', []),
                              ('usos_proibidos', []), ('descricoes_alternativas', []),
                              ('nao_documentado', []), ('avisos_extracao', []), ('texto_original', [])):
            f.setdefault(campo, padrao)
        f.setdefault('aceita_sem_parenteses', any(not a.get('tem_parenteses', True) for a in f['assinaturas']))
        f.setdefault('tipo_retorno', 'nao_documentado')
        f.setdefault('confianca_extracao', 'declarada' if p.camada == 'privado' else 'media')
        existente = self.funcoes.get(f['id'])
        if existente is None:
            self.funcoes[f['id']] = f
            self.por_nome[f['nome']].append(f)
            return
        if p.camada == 'privado' and existente['camada'] == 'publico':
            # Privado ENRIQUECE (exemplos, observações), nunca troca a assinatura documentada.
            # Exceção: se a documentação pública NÃO traz sintaxe nenhuma (aridade vazia),
            # a sintaxe privada preenche a lacuna — marcada em 'sintaxe_complementada_por'.
            if f.get('aridades_documentadas') and not existente.get('aridades_documentadas') \
                    and not existente.get('assinaturas'):
                for campo in ('assinaturas', 'parametros', 'aridades_documentadas'):
                    existente[campo] = f.get(campo, [])
                existente['aceita_sem_parenteses'] = any(not a.get('tem_parenteses', True)
                                                         for a in existente['assinaturas'])
                existente['sintaxe_complementada_por'] = p.id
            elif f.get('aridades_documentadas') and \
                    set(f['aridades_documentadas']) != set(existente.get('aridades_documentadas', [])):
                self.avisos.append(f"{p.id}: {f['id']} declara aridade {f['aridades_documentadas']} diferente da "
                                   f"documentação pública {existente.get('aridades_documentadas')} — mantida a pública; "
                                   f"variante privada registrada em 'variantes_privadas'")
                existente.setdefault('variantes_privadas', []).append(f)
            for campo in ('exemplos', 'observacoes'):
                existente[campo] = existente[campo] + [dict(x, camada='privado') for x in f.get(campo, [])]
            existente['origens'] = existente['origens'] + f['origens']
        else:
            self.avisos.append(f"{p.id}: {f['id']} duplicado — mantida a primeira ocorrência")

    # ------------------------------------------------------------- contexto
    def contextos_visiveis(self, contexto, pacote=None):
        """Contexto pedido + os que ele herda (transitivo). Sem contexto: todos."""
        if not contexto:
            return None
        contexto = contexto.upper()
        visiveis, fila = [], [contexto]
        while fila:
            c = fila.pop(0)
            if c in visiveis:
                continue
            visiveis.append(c)
            for (pac, nome), cfg in self.contextos.items():
                if nome == c and (pacote is None or pac == pacote):
                    fila.extend(cfg['herda'])
        return visiveis

    def resolver(self, nome, contexto=None, pacote=None):
        """Fichas visíveis para NOME no contexto (mais específico primeiro) e
        fichas existentes só em outros contextos."""
        todas = [f for f in self.por_nome.get(nome.upper(), []) if pacote is None or f['pacote'] == pacote]
        vis = self.contextos_visiveis(contexto, pacote)
        if vis is None:
            return todas, []
        ordem = {c: i for i, c in enumerate(vis)}
        dentro = sorted([f for f in todas if f['contexto'] in ordem], key=lambda f: ordem[f['contexto']])
        fora = [f for f in todas if f['contexto'] not in ordem]
        return dentro, fora

    def dialeto(self, pacote=None):
        if pacote and pacote in self.dialetos:
            return self.dialetos[pacote]
        if len(self.dialetos) == 1:
            return next(iter(self.dialetos.values()))
        if not self.dialetos:
            return {}
        raise ValueError('Mais de um dialeto carregado: informe --pacote (' + ', '.join(self.dialetos) + ')')

    # ------------------------------------------------------------- busca
    def _doc_tokens(self, f):
        w = PESOS_CAMPO
        partes = [(f['nome'], w['nome']), (f.get('descricao') or '', w['descricao'])]
        partes += [(d, w['descricao_alternativa']) for d in f.get('descricoes_alternativas', [])]
        partes += [(p.get('descricao') or '', w['parametro']) for p in f.get('parametros', [])]
        partes += [(p.get('rotulo_documentado') or '', w['rotulo_parametro']) for p in f.get('parametros', [])]
        partes += [(o.get('texto', ''), w['observacao']) for o in f.get('observacoes', [])]
        partes += [(e.get('texto', '') + ' ' + ' '.join(e.get('explicacao', [])), w['exemplo'])
                   for e in f.get('exemplos', [])]
        partes += [(n.get('texto', ''), w['anotacao']) for n in f.get('anotacoes', [])]
        pesos = Counter()
        for texto, peso in partes:
            for t in tokens(texto):
                r = _rad(t)
                pesos[r] = max(pesos[r], peso)
        r_nome = _rad(normalizar(f['nome']))
        pesos[r_nome] = max(pesos[r_nome], w['nome'])
        return pesos

    def _indexar(self):
        self._idx = {fid: self._doc_tokens(f) for fid, f in self.funcoes.items()}
        df = Counter()
        for pesos in self._idx.values():
            df.update(pesos.keys())
        n = max(1, len(self._idx))
        self._idf = {t: math.log(1 + n / (1 + c)) for t, c in df.items()}
        self._vocab = sorted(self._idf)   # vocabulário indexado (alvo da correção fuzzy)

    def expandir(self, termos, extra=None):
        """Termos + sinônimos do pacote (e `extra`: {termo: {sinônimos}}, ex.: os
        pares revisados da Punk Records), em cadeia, até 3 passadas."""
        out = list(termos)
        for _ in range(3):
            novos = [s for t in out for fonte in (self.sinonimos, extra or {}) for s in fonte.get(t, ())
                     if s not in out]
            if not novos:
                break
            out += novos
        return out

    def buscar(self, pedido, contexto=None, pacote=None, limite=10, sinonimos_extra=None):
        vis = self.contextos_visiveis(contexto, pacote)
        termos = self.expandir(tokens(pedido), sinonimos_extra)
        nomes_citados = {t.upper() for t in tokens(pedido, minimo=1)}
        rads = [_rad(t) for sub in termos for t in sub.split()]   # sinônimo pode ser expressão
        # Correção aproximada (fuzzy): só para termos que não batem em NADA do
        # vocabulário indexado — termo que já bate nunca é tocado (mesma regra
        # do motor de consultas). Sempre sinalizada em `fuzzy_aplicado`.
        correcoes = {}
        for r in dict.fromkeys(rads):
            if r not in self._idf and len(r) >= FUZZY_TAMANHO_MIN:
                c = difflib.get_close_matches(r, self._vocab, n=1, cutoff=FUZZY_CUTOFF)
                if c:
                    correcoes[r] = c[0]
        rads = [correcoes.get(r, r) for r in rads]
        unicos = set(rads)
        idf_max = math.log(1 + max(1, len(self._idx)))
        idf_total = sum(self._idf.get(r, idf_max) for r in unicos)
        res = []
        for fid, pesos in self._idx.items():
            f = self.funcoes[fid]
            if pacote and f['pacote'] != pacote:
                continue
            if vis is not None and f['contexto'] not in vis:
                continue
            score, batidos = 0.0, []
            for r in unicos:
                if r in pesos:
                    score += pesos[r] * self._idf.get(r, 0.0)
                    batidos.append(r)
            citado = f['nome'] in nomes_citados
            if citado:
                score += BONUS_NOME_CITADO
                batidos.append(f['nome'])
            if score > 0:
                if COBERTURA_POR_IDF:
                    cobertura = 1.0 if citado else \
                        sum(self._idf.get(r, 0.0) for r in batidos) / max(1e-9, idf_total)
                else:
                    cobertura = len(set(batidos)) / max(1, len(unicos))
                score *= (COBERTURA_BASE + cobertura)
                # desempate: quanto da DESCRIÇÃO o pedido cobre (descrição curta e
                # certeira > descrição longa que só menciona os termos de passagem)
                desc = {_rad(t) for t in tokens(f.get('descricao') or '')}
                if desc:
                    score += BONUS_DESCRICAO * len(desc & unicos) / len(desc)
                res.append((score, f, sorted(set(batidos))))
        res.sort(key=lambda x: (-x[0], x[1]['nome']))
        avisos = []
        if correcoes and res:
            avisos.append('Termo(s) sem correspondência no dicionário; aplicada correção aproximada (fuzzy): '
                          + ', '.join(f'"{o}" -> "{c}"' for o, c in correcoes.items())
                          + '. Confirme se a interpretação faz sentido.')
        # Ambiguidade: 1º colocado e o próximo de NOME diferente (a mesma função
        # em dois contextos não é ambiguidade) com scores próximos demais.
        margem, ambiguo = None, False
        if res and res[0][0] > 0:
            seg = next((x for x in res[1:] if x[1]['nome'] != res[0][1]['nome']), None)
            if seg:
                margem = round((res[0][0] - seg[0]) / res[0][0], 3)
                if margem < LIMIAR_AMBIGUIDADE:
                    ambiguo = True
                    avisos.append(f'Ambiguidade: "{res[0][1]["nome"]}" e "{seg[1]["nome"]}" ficaram com scores '
                                  f'próximos (diferença de {margem * 100:.0f}%). Confirme com o usuário qual é a '
                                  f'intenção antes de compor, em vez de assumir o 1º colocado.')
        if not res:
            avisos.append('Nenhuma função do dicionário corresponde ao pedido. Não invente: reformule com '
                          'outros termos ou informe que não há suporte documentado.')
        return {'pedido': pedido, 'contexto': contexto, 'termos': termos,
                'resultados': [{'score': round(s, 3), 'termos_batidos': b, **resumo_funcao(f)}
                               for s, f, b in res[:limite]],
                'receitas': self.buscar_receitas(pedido, contexto, limite=3),
                'fuzzy_aplicado': correcoes if (correcoes and res) else None,
                'ambiguidade': ambiguo, 'margem_top1_top2': margem,
                'avisos': avisos,
                # compatibilidade: primeiro aviso (ou None), como antes
                'aviso': avisos[0] if avisos else None}

    def buscar_receitas(self, pedido, contexto=None, limite=3):
        rads = set(_rad(t) for t in self.expandir(tokens(pedido)))
        vis = self.contextos_visiveis(contexto)
        out = []
        for r in self.receitas:
            if vis is not None and r.get('contexto') and r['contexto'] not in vis:
                continue
            alvo = set(_rad(t) for t in tokens(r.get('nome', '') + ' ' + r.get('descricao', '') + ' ' +
                                                  ' '.join(r.get('palavras_chave', []))))
            comum = rads & alvo
            if comum:
                out.append((len(comum) / max(1, len(rads)), r))
        out.sort(key=lambda x: -x[0])
        return [dict(r, score=round(s, 3)) for s, r in out[:limite]]


def resumo_funcao(f):
    return {
        'id': f['id'], 'nome': f['nome'], 'contexto': f['contexto'], 'camada': f.get('camada'),
        'descricao': f.get('descricao'),
        'assinaturas': [a['texto'] for a in f.get('assinaturas', [])],
        'aridades_documentadas': f.get('aridades_documentadas', []),
        'tipo_retorno': f.get('tipo_retorno'),
        'confianca_extracao': f.get('confianca_extracao'),
        'usos_proibidos': [u['uso'] for u in f.get('usos_proibidos', [])],
        'url': (f.get('origens') or [{}])[0].get('url'),
    }


def carregar(raiz=None, somente_publico=False, extras=None):
    return BaseConhecimento(descobrir_pacotes(raiz, somente_publico, extras))
