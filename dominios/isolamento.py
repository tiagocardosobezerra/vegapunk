"""
Verificação de isolamento CORE × PÚBLICO × PRIVADO.

Responde, de forma verificável (não por promessa em documentação):
  1. o core do motor de fórmulas não importa o motor de consultas nem é
     importado por ele (e não referencia a base Punk Records);
  2. o motor funciona SÓ com a camada pública (carga com somente_publico);
  3. nenhum pacote público se declara privado e vice-versa;
  4. a pasta privada está protegida por .gitignore;
  5. nenhum TERMO SENSÍVEL da camada privada aparece no core ou nos pacotes
     públicos. Termos sensíveis = nomes de funções que só existem na camada
     privada + a lista `termos_sensiveis.json` que cada pacote privado pode
     declarar (nomes internos, tabelas, campos, códigos da empresa);
  6. nenhuma MARCA de terceiro declarada por um pacote público (`"marcas"`
     no fonte.json/pacote.json) aparece fora do próprio pacote — core,
     SKILL.md, README.md, AVISO.md, COMO-INSTALAR.md, referencias/, testes/ e casos/. Mesma regra que o AVISO.md já
     impunha ao motor de consultas: nome de fornecedor não se repete na
     especificação da skill.
  7. nenhum TRECHO do texto da camada privada (sequência de
     `TAMANHO_TRECHO` palavras tirada dos JSON de cada pacote privado)
     aparece na superfície distribuível da skill. Trechos que também
     aparecem no texto da camada pública não contam: o fornecedor publica
     o mesmo texto nos dois lugares, e isso não é vazamento;
  8. falha fechada: todo pacote privado precisa contribuir com pelo menos
     um termo ou um trecho verificado. Uma camada privada que não verifica
     nada é tratada como falha, não como "nenhum vazamento".
  9. nenhum MAPA REAL na superfície distribuível: o mapa de um sistema real
     cita tabelas reais e é da instância (pacote privado). Todo mapa na
     superfície (arquivo `mapa*.json`, arquivo numa pasta `mapa/` ou JSON com
     as partes do contrato do mapa) precisa declarar `"ficticio": true` e só
     citar tabelas do schema fictício da fixture (`casos/tabelas_ficticias.json`).

Nenhuma checagem imprime termo ou trecho da camada privada: a saída diz
só onde está o vazamento (arquivo e linha) e quantos itens foram
verificados.
"""

import html
import json
import os
import re

from dominios.formulas import conhecimento as kb
from dominios.formulas.texto import normalizar

_EXT_TEXTO = ('.py', '.json', '.md', '.txt', '.jsonl')

# Impressão digital do texto privado: trechos de N palavras seguidas.
# 12 palavras é longo o bastante para não casar por coincidência e curto o
# bastante para pegar um parágrafo copiado.
TAMANHO_TRECHO = 12

# Superfície distribuível, por regra (ver `_superficie_distribuivel`).
_EXT_SUPERFICIE = ('.py', '.md', '.json', '.txt', '.sql', '.svg')
# Pastas de instância local: nada delas é distribuível.
_PASTAS_INSTANCIA = ('egghead',)
# Arquivos sem extensão de texto que também saem, pelo nome: a licença, os
# .gitignore (o da camada privada é a proteção que a checagem 4 exige) e o
# .gitattributes (fim de linha LF em todo checkout).
_NOMES_SUPERFICIE = ('LICENSE', '.gitignore', '.gitattributes')
# Pastas que nunca saem: camada privada, texto bruto do fornecedor, cópias de
# segurança e pastas técnicas.
_PASTAS_FORA = ('privado', 'bruto', 'backups', '__pycache__', '.git')
# Da camada privada só sai a proteção e a explicação, nunca um pacote.
_ARQUIVOS_DISTRIBUIVEIS_DO_PRIVADO = ('.gitignore', 'README.md')
# Fixtures fictícias (dados inventados, AVISO.md): saem inteiras, inclusive o
# pacote público com funções e a camada privada fictícia que os testes usam.
_PASTA_FIXTURES = os.path.join('casos', 'fixtures')
# Partes do contrato do mapa (fase 3): um JSON com alguma delas é um mapa.
_PARTES_DO_MAPA = ('cadastros', 'formulas', 'consultas', 'funcoes_de_consulta')
# Num pacote público só isto é distribuível (camada Linguagem fica local).
_ARQUIVOS_DISTRIBUIVEIS_DO_PACOTE = ('fonte.json', 'pacote.json', 'dialeto.json')
_SUBPASTAS_DISTRIBUIVEIS_DO_PACOTE = ('mapa', 'casos')


def _ler_texto(caminho):
    with open(caminho, encoding='utf-8') as f:
        return f.read()


def _arquivos(raiz, ignorar=()):
    for d, subdirs, arqs in os.walk(raiz):
        subdirs[:] = [s for s in subdirs if os.path.join(d, s) not in ignorar and s != '__pycache__']
        for a in arqs:
            if a.endswith(_EXT_TEXTO):
                yield os.path.join(d, a)


def _procurar(termos, alvos, raiz_rel, ignorar=(), mostrar_termo=True):
    """Primeira ocorrência (por arquivo) de qualquer termo, como palavra inteira.
    `mostrar_termo=False` para termos privados: o achado diz só arquivo e linha."""
    if not termos:
        return []
    rx = re.compile(r'(?<![\w])(' + '|'.join(re.escape(t) for t in sorted(termos, key=len, reverse=True)) +
                    r')(?![\w])', re.I)
    achados = []
    for alvo in alvos:
        for a in ([alvo] if os.path.isfile(alvo) else list(_arquivos(alvo, ignorar))):
            with open(a, encoding='utf-8', errors='ignore') as fh:
                for i, linha in enumerate(fh, 1):
                    m = rx.search(linha)
                    if m:
                        achados.append(f'{os.path.relpath(a, raiz_rel)}:{i}' +
                                       (f': "{m.group(1)}"' if mostrar_termo else ''))
                        break
    return achados


def _ler_texto_tolerante(caminho):
    with open(caminho, encoding='utf-8', errors='ignore') as f:
        return f.read()


def _palavras(texto):
    return re.findall(r'[a-z0-9]+', normalizar(texto))


def _trechos(palavras, n=TAMANHO_TRECHO):
    return {' '.join(palavras[i:i + n]) for i in range(len(palavras) - n + 1)}


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _trechos_de_json(diretorio):
    """Trechos de todas as strings (HTML decodificado) dos JSON de um diretório."""
    out = set()
    for a in _arquivos(diretorio):
        if not a.endswith('.json'):
            continue
        try:
            dados = json.loads(_ler_texto(a))
        except (ValueError, UnicodeDecodeError):
            continue
        for s in _strings(dados):
            out |= _trechos(_palavras(html.unescape(re.sub(r'<[^>]+>', ' ', s))))
    return out


def _pasta_do_pacote_publico(d, limite):
    """Pasta do pacote público que contém `d` (a filha de uma pasta
    `publico`), ou None. Não sobe acima de `limite`."""
    atual = os.path.abspath(d)
    limite = os.path.abspath(limite)
    while atual.startswith(limite + os.sep):
        pai = os.path.dirname(atual)
        if os.path.basename(pai) == 'publico':
            return atual
        atual = pai
    return None


def _distribuivel_no_pacote_publico(rel):
    """`rel`: caminho relativo à pasta de um pacote público. Regra do
    PLANO-V3.md: só `fonte.json`, `pacote.json`, `dialeto.json`, `*.md`,
    `mapa/` e `casos/` saem da instância; o resto é texto do fornecedor.
    Um `mapa/` aqui só passa pela checagem 9 se for fictício (o mapa de um
    sistema real é da instância, no pacote privado)."""
    partes = rel.split(os.sep)
    if len(partes) > 1:
        return partes[0] in _SUBPASTAS_DISTRIBUIVEIS_DO_PACOTE
    return partes[0] in _ARQUIVOS_DISTRIBUIVEIS_DO_PACOTE or partes[0].endswith('.md')


def _superficie_distribuivel(raiz_skill, raiz_con):
    """Arquivos que podem sair da instância, definidos por regra (pastas e
    extensões), não por lista de caminhos:
    - extensões de texto (`_EXT_SUPERFICIE`) e os nomes de `_NOMES_SUPERFICIE`;
    - fora as pastas de instância (`_PASTAS_INSTANCIA`: nada delas sai, nem
      `*.md`, que lá é memória e relatório da instância) e as pastas técnicas
      e de texto do fornecedor (`_PASTAS_FORA`);
    - de uma pasta `privado`, só `_ARQUIVOS_DISTRIBUIVEIS_DO_PRIVADO` (a
      proteção e a explicação), nunca uma subpasta;
    - dentro de um pacote público (pasta filha de uma pasta `publico`), só
      o que `_distribuivel_no_pacote_publico` permite;
    - as fixtures fictícias (`_PASTA_FIXTURES`) saem inteiras: as duas regras
      acima não valem dentro delas."""
    raizes = [raiz_skill]
    if not raiz_con.startswith(raiz_skill + os.sep):
        raizes.append(os.path.join(raiz_con, 'publico'))
    fixtures = os.path.join(raiz_skill, _PASTA_FIXTURES)
    vistos = set()

    def entra(c):
        a = os.path.basename(c)
        return (a.endswith(_EXT_SUPERFICIE) or a in _NOMES_SUPERFICIE) and c not in vistos

    for raiz in raizes:
        for d, subdirs, arqs in os.walk(raiz):
            em_fixture = d == fixtures or d.startswith(fixtures + os.sep)
            em_instancia = any(p in _PASTAS_INSTANCIA for p in os.path.relpath(d, raiz).split(os.sep))
            if not em_fixture and not em_instancia:
                for s in subdirs:
                    if s == 'privado':
                        for a in _ARQUIVOS_DISTRIBUIVEIS_DO_PRIVADO:
                            c = os.path.join(d, s, a)
                            if os.path.isfile(c) and entra(c):
                                vistos.add(c)
                                yield c
            subdirs[:] = [x for x in subdirs if x not in _PASTAS_FORA or
                          (em_fixture and x == 'privado')]
            pacote = None if em_fixture else _pasta_do_pacote_publico(d, os.path.dirname(raiz))
            for a in arqs:
                c = os.path.join(d, a)
                if not entra(c) or em_instancia:
                    continue
                if pacote and not _distribuivel_no_pacote_publico(os.path.relpath(c, pacote)):
                    continue
                vistos.add(c)
                yield c


def _tabelas_citadas(obj):
    """Valores das chaves `tabela` em qualquer nível do mapa."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'tabela' and isinstance(v, str):
                yield v
            else:
                yield from _tabelas_citadas(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _tabelas_citadas(v)


def _e_mapa(caminho, obj):
    partes = caminho.split(os.sep)
    return (os.path.basename(caminho).startswith('mapa') or 'mapa' in partes[:-1]
            or (isinstance(obj, dict) and any(k in obj for k in _PARTES_DO_MAPA)))


def verificar_mapas(arquivos, raiz_skill):
    """Checagem 9: devolve ([problema], mapas encontrados). O problema diz só
    o caminho e a contagem, nunca o nome de tabela (num mapa real, informação
    da instância)."""
    lista = os.path.join(raiz_skill, 'casos', 'tabelas_ficticias.json')
    ficticias = set(json.loads(_ler_texto(lista))['tabelas']) if os.path.exists(lista) else set()
    problemas, n_mapas = [], 0
    for a in arquivos:
        if not a.endswith('.json'):
            continue
        try:
            obj = json.loads(_ler_texto(a))
        except (ValueError, UnicodeDecodeError):
            continue
        if not _e_mapa(os.path.relpath(a, raiz_skill), obj):
            continue
        rel = os.path.relpath(a, raiz_skill)
        n_mapas += 1
        if not (isinstance(obj, dict) and obj.get('ficticio') is True):
            problemas.append(f'{rel}: mapa sem "ficticio": true')
            continue
        fora = {t for t in _tabelas_citadas(obj) if t not in ficticias}
        if fora:
            problemas.append(f'{rel}: {len(fora)} tabela(s) fora do schema fictício')
    return problemas, n_mapas


def verificar_isolamento(raiz_skill, raiz_conhecimento=None):
    raiz_skill = os.path.abspath(raiz_skill)
    raiz_con = os.path.abspath(raiz_conhecimento or kb.RAIZ_CONHECIMENTO)
    dir_privado = os.path.join(raiz_con, 'privado')
    satelites = os.path.join(raiz_skill, 'satelites')
    # núcleo de fórmulas: o domínio, a ingestão da documentação, o próprio
    # verificador e o Shaka (antes, tudo isso ficava em scripts/formulas/ + shaka.py)
    core = [os.path.join(raiz_skill, 'dominios', 'formulas'), os.path.join(raiz_skill, 'dominios', 'isolamento.py'),
            os.path.join(raiz_skill, 'punk_records', 'ingestao'), os.path.join(satelites, 'shaka.py')]
    # atlas.py, pythagoras.py e york.py cobrem os DOIS domínios de propósito
    # (golden, avaliação e escrita de cada um, importando cada domínio só
    # quando usado): ficam fora da checagem de dependência, mas dentro das
    # checagens de termos e de marcas.
    cruzados = [os.path.join(satelites, f) for f in ('atlas.py', 'pythagoras.py', 'york.py')]
    checks = []

    def check(nome, ok, detalhe=''):
        checks.append({'verificacao': nome, 'ok': bool(ok), 'detalhe': detalhe})

    # 1. separação de motores
    viol = []
    for alvo in core:
        arqs = [alvo] if os.path.isfile(alvo) else list(_arquivos(alvo))
        for a in arqs:
            if not a.endswith('.py'):
                continue
            txt = _ler_texto(a)
            # importar o motor de consultas ou abrir SQLite (a base Punk Records) = acoplamento
            if re.search(r'^\s*(from|import)\s+(nomi_nomi_no_mi(?!\.texto_comum\b)|dominios\.schema|punk_records\.schema|sqlite3)\b', txt, re.M):
                viol.append(os.path.relpath(a, raiz_skill))
    check('core de fórmulas não depende do motor de consultas', not viol, ', '.join(viol))
    motor_schema = [p for p in (os.path.join(raiz_skill, 'nomi_nomi_no_mi'),
                                os.path.join(raiz_skill, 'dominios', 'schema')) if os.path.isdir(p)]
    if motor_schema:
        viol = [os.path.relpath(a, raiz_skill) for alvo in motor_schema for a in _arquivos(alvo)
                if a.endswith('.py') and re.search(r'^\s*(from|import)\s+(formulas|dominios\.formulas|shaka)\b',
                                                   _ler_texto(a), re.M)]
        check('motor de consultas não depende do motor de fórmulas', not viol, ', '.join(viol))

    # 2. funciona só com o público
    try:
        base_pub = kb.carregar(raiz_con, somente_publico=True)
        n = len(base_pub.funcoes)
        camadas = {f['camada'] for f in base_pub.funcoes.values()}
        detalhe = f'{n} funções públicas'
        fixture = os.path.join(raiz_skill, _PASTA_FIXTURES, 'formulas')
        if n == 0 and os.path.isdir(fixture):
            # versão distribuível: o texto do fornecedor não sai, os pacotes
            # públicos chegam sem funções até o `york.py ingerir`; o motor é
            # conferido com o pacote público fictício da fixture
            base_fic = kb.carregar(fixture, somente_publico=True)
            n = len(base_fic.funcoes)
            camadas = {f['camada'] for f in base_fic.funcoes.values()}
            detalhe = (f'0 funções públicas instaladas (documentação não ingerida); '
                       f'conferido com o pacote fictício: {n} funções públicas')
        check('motor carrega só com a camada pública', n > 0 and camadas <= {'publico'}, detalhe)
    except Exception as e:  # noqa: BLE001
        check('motor carrega só com a camada pública', False, repr(e))
        base_pub = None

    # 3. coerência de visibilidade
    pacotes = kb.descobrir_pacotes(raiz_con)
    errados = [p.id for p in pacotes if (p.camada == 'publico' and p.visibilidade != 'publico') or
               (p.camada == 'privado' and p.visibilidade == 'publico')]
    check('visibilidade declarada coerente com a camada', not errados, ', '.join(errados))

    # 4. .gitignore
    gi = os.path.join(dir_privado, '.gitignore')
    conteudo = _ler_texto(gi) if os.path.exists(gi) else ''
    check('camada privada protegida por .gitignore', re.search(r'^\*\s*$', conteudo, re.M) is not None, gi)

    # 5. vazamento de termos privados
    termos = set()
    nomes_pub = set(f['nome'] for f in base_pub.funcoes.values()) if base_pub else set()
    for p in pacotes:
        if p.camada != 'privado':
            continue
        # pacote privado pode declarar que os NOMES de função dele não são sigilosos
        # (ex.: complemento vindo de manual do próprio fornecedor); termos_sensiveis.json
        # continua valendo
        if p.manifesto.get('funcoes_sensiveis', True):
            termos |= {f['nome'].upper() for f in p.funcoes if f['nome'].upper() not in nomes_pub}
        ts = os.path.join(p.dir, 'termos_sensiveis.json')
        if os.path.exists(ts):
            termos |= {t for t in json.loads(_ler_texto(ts)) if len(t) >= 3}
    vaz = _procurar(termos, core + cruzados + [os.path.join(raiz_con, 'publico')], raiz_skill, mostrar_termo=False)
    check('nenhum termo da camada privada no core nem nos pacotes públicos', not vaz,
          f'{len(termos)} termos verificados' + ('; ' + '; '.join(vaz[:20]) if vaz else ''))

    # 6. marcas de terceiros só dentro do próprio pacote
    marcas = {m for p in pacotes if p.camada == 'publico' for m in p.manifesto.get('marcas', []) if len(m) >= 3}
    alvos = core + cruzados + [os.path.join(raiz_skill, x) for x in ('SKILL.md', 'README.md', 'AVISO.md', 'COMO-INSTALAR.md', 'referencias', 'testes', 'casos')]
    # fixtures de teste são dados fictícios por definição (AVISO.md) e os
    # próprios diretórios de pacote são o lugar CERTO da marca
    ignorar = {os.path.join(raiz_skill, 'casos', 'fixtures')} | {p.dir for p in pacotes}
    fora = _procurar(marcas, [a for a in alvos if os.path.exists(a)], raiz_skill, ignorar)
    check('marcas de terceiros só dentro do próprio pacote', not fora,
          f'{len(marcas)} marcas verificadas' + ('; ' + '; '.join(fora[:20]) if fora else ''))

    # 7. impressão digital do texto privado na superfície distribuível
    privados = [p for p in pacotes if p.camada == 'privado']
    texto_publico = set()
    for p in pacotes:
        if p.camada == 'publico':
            texto_publico |= _trechos_de_json(p.dir)
    trechos_por_pacote = {p.id: _trechos_de_json(p.dir) - texto_publico for p in privados}
    trechos = set().union(*trechos_por_pacote.values())
    arquivos = list(_superficie_distribuivel(raiz_skill, raiz_con))
    achados = []
    if trechos:
        for a in arquivos:
            n = len(_trechos(_palavras(_ler_texto_tolerante(a))) & trechos)
            if n:
                achados.append(f'{os.path.relpath(a, raiz_skill)} ({n} trechos)')
    check('nenhum trecho do texto privado na superfície distribuível', not achados,
          f'{len(trechos)} trechos verificados em {len(arquivos)} arquivos' +
          ('; ' + '; '.join(achados[:20]) if achados else ''))

    # 8. falha fechada: cada pacote privado precisa verificar alguma coisa
    vazios = []
    for p in privados:
        n = 0
        if p.manifesto.get('funcoes_sensiveis', True):
            n += len({f['nome'].upper() for f in p.funcoes if f['nome'].upper() not in nomes_pub})
        ts = os.path.join(p.dir, 'termos_sensiveis.json')
        if os.path.exists(ts):
            n += len([t for t in json.loads(_ler_texto(ts)) if len(t) >= 3])
        if not n and not trechos_por_pacote[p.id]:
            vazios.append(p.id)
    check('camada privada verificada de fato (falha fechada)', not vazios,
          f'{len(privados)} pacotes privados' +
          (f'; sem nenhum termo nem trecho verificável: {", ".join(vazios)}' if vazios else ''))

    # 9. nenhum mapa real na superfície distribuível
    problemas, n_mapas = verificar_mapas(arquivos, raiz_skill)
    check('nenhum mapa real na superfície distribuível (só mapa fictício)', not problemas,
          f'{n_mapas} mapa(s) na superfície' + ('; ' + '; '.join(problemas[:20]) if problemas else ''))
    return {'ok': all(c['ok'] for c in checks), 'verificacoes': checks}
