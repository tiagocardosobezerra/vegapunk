"""
Mapa (fase 3 da v3): onde as coisas moram no banco do sistema de origem.

O mapa é um arquivo de DECLARAÇÕES (`mapa.json`, contrato v2) que só cita
nomes de tabela, de coluna e de função. O York confere e compila o mapa na
Punk Records (tabelas `mapa_*`, migração 004), numa transação e com cópia de
segurança. O motor de fórmulas lê o mapa compilado; ninguém lê o arquivo.

O mapa de um sistema real cita tabelas reais: é da INSTÂNCIA (pacote
privado). Só um mapa fictício (`"ficticio": true`, tabelas da fixture) vai
para a superfície distribuível (`dominios/isolamento.py`, checagem 9).

Contrato v2 (todas as partes opcionais):
  versao: 2
  ficticio: true|false
  observacao: texto curto
  funcoes_de_consulta: {executar, ler_campo, avancar_registro: FUNÇÃO,
                        parametros_na_chamada: bool, evidencias: [texto curto]}
  formulas:  {tabela, chave: [COL], colunas: {papel: COL},
              tipo: {tabela, ligacao: [[COL da fórmula, COL do tipo]], descricao: COL}}
  consultas: {tabela, chave: [COL], colunas: {papel: COL},
              campos:     {tabela, chave: [COL], ligacao_com_consulta: [COL], campo, descricao, tipo: COL},
              parametros: {tabela, chave: [COL], ligacao_com_consulta: [COL], nome, descricao, tipo: COL}}
  cadastros: [{cadastro: id, tabela, chave: [COL], coluna_codigo: COL, coluna_descricao: COL,
               rotulos_parametro: [rótulo | {rotulo, prova: "documentacao", fonte: texto curto}],
               funcoes: [FUNÇÃO], nota: texto curto,
               ligacoes_formula: {tabela, chave_destino: [COL], colunas_origem_extra: [COL],
                                  colunas_por_papel: {papel: COL},
                                  papeis_confirmados: {papel: {prova: "usuario", fonte: texto curto,
                                                               data: AAAA-MM-DD,
                                                               descricao_da_origem_errada: bool}}}}]

O York RECUSA o arquivo inteiro (nada é gravado) se:
- aparecer qualquer campo fora do contrato, em qualquer nível;
- algum valor parecer conteúdo de registro: código junto de descrição,
  sequência de dígitos, texto de SQL ou de fórmula, texto longo, lista longa,
  número onde se espera nome;
- uma tabela ou coluna citada não existir no schema da Punk Records;
- uma `chave` declarada não contiver a PK inteira da tabela (ou a tabela não
  tiver PK conhecida); uma `chave_destino` idem; a ligação de origem não
  tiver o mesmo número de colunas que a chave de destino.

O PAPEL de cada coluna vem da DESCRIÇÃO da coluna no schema, nunca do nome:
a coluna declarada num papel cuja descrição não fala desse papel fica com
`papel_divergente` (a ligação continua, se provada; vira aviso). Toda coluna
de ligação com fórmula precisa de prova: FK no schema (`fk`) ou descrição
que cite fórmula (`descricao`); sem prova, o arquivo é recusado.
"""

import json
import os
import re
import unicodedata
from collections import defaultdict

VERSAO_CONTRATO = 2
VERSAO_MINIMA_DA_BASE = 6   # 004: tabelas mapa_*; 005: prova dos rótulos; 006: papel confirmado pelo usuário

# ------------------------------------------------------------------ contrato
_ID = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
_PAPEL = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
_SQL = re.compile(r'\b(select|insert|update|delete|from|where|join|union|exec|values|into)\b', re.I)
_FORMULA = re.compile(r'[A-Z]{2,}\s*\(.*\)|:=|\bSE\b.+\bENTAO\b', re.I)
_DIGITOS = re.compile(r'\d{3,}')
_CODIGO_E_DESCRICAO = re.compile(r'^\s*\w*\d\w*\s*[-–:=|]\s*\S')
LIMITE_ROTULO = 60
# Prova de um rótulo acrescentado ao cadastro: só a documentação do
# fornecedor (o dialeto e as regras do Shaka são nossos e não provam nada).
PROVAS_DE_ROTULO = {'documentacao'}
# Prova de um papel que a descrição da coluna NÃO confirma: só o usuário. O
# papel confirmado deixa de ser divergente; se a descrição da origem estiver
# errada, ela fica registrada como conhecida e o Edison não a usa como
# evidência em lugar nenhum.
PROVAS_DE_PAPEL = {'usuario'}
_DATA = re.compile(r'^\d{4}-\d{2}-\d{2}$')
LIMITE_TEXTO = 400
LIMITE_LISTA = 40


class MapaRecusado(ValueError):
    """O arquivo de mapa não segue o contrato ou não bate com o schema. Nada foi gravado."""

    def __init__(self, erros):
        self.erros = erros
        super().__init__(f'{len(erros)} problema(s) no mapa: ' + '; '.join(erros[:15]))


def _parece_conteudo(texto, rotulo=False):
    """Motivo pelo qual o texto parece conteúdo de registro, ou None."""
    if len(texto) > (LIMITE_ROTULO if rotulo else LIMITE_TEXTO):
        return 'texto longo demais para uma declaração'
    if _SQL.search(texto):
        return 'parece texto de SQL'
    if rotulo and _FORMULA.search(texto):
        return 'parece texto de fórmula'
    if _DIGITOS.search(texto):
        return 'tem sequência de dígitos (parece código ou valor de registro)'
    if _CODIGO_E_DESCRICAO.search(texto):
        return 'parece um código seguido de descrição (linha de cadastro)'
    return None


class _Conferente:
    def __init__(self):
        self.erros = []

    def erro(self, onde, msg):
        self.erros.append(f'{onde}: {msg}')

    def objeto(self, valor, onde, obrigatorios, opcionais=()):
        if not isinstance(valor, dict):
            self.erro(onde, 'esperado um objeto')
            return False
        extras = set(valor) - set(obrigatorios) - set(opcionais)
        for k in sorted(extras):
            self.erro(onde, f'campo fora do contrato: {k!r}')
        for k in obrigatorios:
            if k not in valor:
                self.erro(onde, f'falta o campo {k!r}')
        return not extras and all(k in valor for k in obrigatorios)

    def ident(self, valor, onde):
        if not isinstance(valor, str) or not _ID.match(valor):
            self.erro(onde, f'esperado um nome (letras, dígitos e _), veio {type(valor).__name__}'
                      + ('' if not isinstance(valor, str) else ' com caracteres fora do padrão'))
            return False
        return True

    def lista_ids(self, valor, onde, vazia=False):
        if not isinstance(valor, list) or (not valor and not vazia) or len(valor) > LIMITE_LISTA:
            self.erro(onde, 'esperada uma lista de nomes (não vazia, curta)')
            return False
        return all(self.ident(v, f'{onde}[{i}]') for i, v in enumerate(valor))

    def texto(self, valor, onde, rotulo=False):
        if not isinstance(valor, str) or not valor.strip():
            self.erro(onde, 'esperado um texto')
            return False
        motivo = _parece_conteudo(valor, rotulo)
        if motivo:
            self.erro(onde, f'recusado: {motivo}')
            return False
        return True

    def papeis(self, valor, onde):
        if not isinstance(valor, dict) or not valor or len(valor) > LIMITE_LISTA:
            self.erro(onde, 'esperado um objeto {papel: COLUNA}')
            return False
        ok = True
        for papel, col in valor.items():
            if not _PAPEL.match(papel):
                self.erro(onde, f'papel fora do padrão: {papel!r}')
                ok = False
            ok = self.ident(col, f'{onde}.{papel}') and ok
        return ok


def conferir_contrato(m):
    """Lista de erros de contrato (sem olhar o schema)."""
    c = _Conferente()
    if not c.objeto(m, 'mapa', ['versao'], ['ficticio', 'observacao', 'funcoes_de_consulta', 'formulas',
                                            'consultas', 'cadastros']):
        if not isinstance(m, dict):
            return c.erros
    if m.get('versao') != VERSAO_CONTRATO:
        c.erro('mapa.versao', f'esperado {VERSAO_CONTRATO}')
    if 'ficticio' in m and not isinstance(m['ficticio'], bool):
        c.erro('mapa.ficticio', 'esperado true ou false')
    if 'observacao' in m:
        c.texto(m['observacao'], 'mapa.observacao')
    fc = m.get('funcoes_de_consulta')
    if fc is not None and c.objeto(fc, 'funcoes_de_consulta', [], ['executar', 'ler_campo', 'avancar_registro',
                                                                    'parametros_na_chamada', 'evidencias']):
        for k in ('executar', 'ler_campo', 'avancar_registro'):
            if k in fc:
                c.ident(fc[k], f'funcoes_de_consulta.{k}')
        if 'parametros_na_chamada' in fc and not isinstance(fc['parametros_na_chamada'], bool):
            c.erro('funcoes_de_consulta.parametros_na_chamada', 'esperado true ou false')
        ev = fc.get('evidencias', [])
        if not isinstance(ev, list) or len(ev) > 10:
            c.erro('funcoes_de_consulta.evidencias', 'esperada uma lista curta de textos')
        else:
            for i, t in enumerate(ev):
                c.texto(t, f'funcoes_de_consulta.evidencias[{i}]')
    f = m.get('formulas')
    if f is not None and c.objeto(f, 'formulas', ['tabela', 'chave'], ['colunas', 'tipo']):
        c.ident(f['tabela'], 'formulas.tabela')
        c.lista_ids(f['chave'], 'formulas.chave')
        if 'colunas' in f:
            c.papeis(f['colunas'], 'formulas.colunas')
        t = f.get('tipo')
        if t is not None and c.objeto(t, 'formulas.tipo', ['tabela', 'ligacao', 'descricao']):
            c.ident(t['tabela'], 'formulas.tipo.tabela')
            c.ident(t['descricao'], 'formulas.tipo.descricao')
            lig = t['ligacao']
            if not isinstance(lig, list) or not lig or not all(isinstance(p, list) and len(p) == 2 for p in lig):
                c.erro('formulas.tipo.ligacao', 'esperada uma lista de pares [COLUNA da fórmula, COLUNA do tipo]')
            else:
                for i, (a, b) in enumerate(lig):
                    c.ident(a, f'formulas.tipo.ligacao[{i}][0]')
                    c.ident(b, f'formulas.tipo.ligacao[{i}][1]')
    q = m.get('consultas')
    if q is not None and c.objeto(q, 'consultas', ['tabela', 'chave'], ['colunas', 'campos', 'parametros']):
        c.ident(q['tabela'], 'consultas.tabela')
        c.lista_ids(q['chave'], 'consultas.chave')
        if 'colunas' in q:
            c.papeis(q['colunas'], 'consultas.colunas')
        for parte, papeis in (('campos', ('campo', 'descricao', 'tipo')), ('parametros', ('nome', 'descricao', 'tipo'))):
            sub = q.get(parte)
            if sub is None:
                continue
            if c.objeto(sub, f'consultas.{parte}', ['tabela', 'chave', 'ligacao_com_consulta', papeis[0]], papeis[1:]):
                c.ident(sub['tabela'], f'consultas.{parte}.tabela')
                c.lista_ids(sub['chave'], f'consultas.{parte}.chave')
                c.lista_ids(sub['ligacao_com_consulta'], f'consultas.{parte}.ligacao_com_consulta')
                for p in papeis:
                    if p in sub:
                        c.ident(sub[p], f'consultas.{parte}.{p}')
    cads = m.get('cadastros')
    if cads is not None:
        if not isinstance(cads, list) or len(cads) > 200:
            c.erro('cadastros', 'esperada uma lista de cadastros')
        else:
            vistos = set()
            for i, cad in enumerate(cads):
                onde = f'cadastros[{i}]'
                if not c.objeto(cad, onde, ['cadastro', 'tabela', 'chave', 'coluna_codigo', 'rotulos_parametro'],
                                ['coluna_descricao', 'funcoes', 'nota', 'ligacoes_formula']):
                    continue
                if not isinstance(cad['cadastro'], str) or not _PAPEL.match(cad['cadastro']):
                    c.erro(f'{onde}.cadastro', 'esperado um identificador em minúsculas')
                elif cad['cadastro'] in vistos:
                    c.erro(f'{onde}.cadastro', f'repetido: {cad["cadastro"]!r}')
                vistos.add(cad.get('cadastro'))
                c.ident(cad['tabela'], f'{onde}.tabela')
                c.lista_ids(cad['chave'], f'{onde}.chave')
                c.ident(cad['coluna_codigo'], f'{onde}.coluna_codigo')
                if 'coluna_descricao' in cad:
                    c.ident(cad['coluna_descricao'], f'{onde}.coluna_descricao')
                rot = cad['rotulos_parametro']
                if not isinstance(rot, list) or not rot or len(rot) > LIMITE_LISTA:
                    c.erro(f'{onde}.rotulos_parametro', 'esperada uma lista curta de rótulos')
                else:
                    for j, r in enumerate(rot):
                        o = f'{onde}.rotulos_parametro[{j}]'
                        if isinstance(r, dict):
                            if c.objeto(r, o, ['rotulo', 'prova', 'fonte']):
                                c.texto(r['rotulo'], f'{o}.rotulo', rotulo=True)
                                if r['prova'] not in PROVAS_DE_ROTULO:
                                    c.erro(f'{o}.prova', f'esperado um de {sorted(PROVAS_DE_ROTULO)}')
                                c.texto(r['fonte'], f'{o}.fonte')
                        else:
                            c.texto(r, o, rotulo=True)
                if 'funcoes' in cad:
                    c.lista_ids(cad['funcoes'], f'{onde}.funcoes')
                if 'nota' in cad:
                    c.texto(cad['nota'], f'{onde}.nota')
                lf = cad.get('ligacoes_formula')
                if lf is not None and c.objeto(lf, f'{onde}.ligacoes_formula', ['tabela', 'chave_destino', 'colunas_por_papel'],
                                               ['colunas_origem_extra', 'papeis_confirmados']):
                    c.ident(lf['tabela'], f'{onde}.ligacoes_formula.tabela')
                    c.lista_ids(lf['chave_destino'], f'{onde}.ligacoes_formula.chave_destino')
                    c.lista_ids(lf.get('colunas_origem_extra', []), f'{onde}.ligacoes_formula.colunas_origem_extra', vazia=True)
                    c.papeis(lf['colunas_por_papel'], f'{onde}.ligacoes_formula.colunas_por_papel')
                    conf = lf.get('papeis_confirmados', {})
                    if not isinstance(conf, dict):
                        c.erro(f'{onde}.ligacoes_formula.papeis_confirmados', 'esperado um objeto {papel: confirmação}')
                        conf = {}
                    for papel_c, v in conf.items():
                        o = f'{onde}.ligacoes_formula.papeis_confirmados.{papel_c}'
                        if papel_c not in (lf.get('colunas_por_papel') or {}):
                            c.erro(o, 'papel confirmado que não está em colunas_por_papel')
                        if not c.objeto(v, o, ['prova', 'fonte', 'data'], ['descricao_da_origem_errada']):
                            continue
                        if v['prova'] not in PROVAS_DE_PAPEL:
                            c.erro(f'{o}.prova', f'esperado um de {sorted(PROVAS_DE_PAPEL)}')
                        c.texto(v['fonte'], f'{o}.fonte')
                        if not isinstance(v['data'], str) or not _DATA.match(v['data']):
                            c.erro(f'{o}.data', 'esperada uma data AAAA-MM-DD')
                        if not isinstance(v.get('descricao_da_origem_errada', False), bool):
                            c.erro(f'{o}.descricao_da_origem_errada', 'esperado true ou false')
    return c.erros


# ------------------------------------------------------------------ schema
def _norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    return ''.join(ch if ch.isalnum() else ' ' for ch in s).split()


# Papéis genéricos: a descrição precisa ter uma destas palavras (prefixo de 5
# letras, sem acento). Papel que não está aqui usa as palavras do próprio nome
# do papel (`complemento_historico` -> "compl", "histo"): é o caso dos papéis
# que o pacote declara, como os das ligações com fórmula.
_TERMOS_DO_PAPEL = {
    'codigo': ['codig', 'cod', 'numer', 'ident', 'id'],
    'descricao': ['descr', 'nome', 'titul', 'razao'], 'titulo': ['titul', 'descr', 'nome'],
    'nome': ['nome', 'descr', 'razao'],
    'texto': ['texto', 'conte', 'formu'], 'sentenca': ['sente', 'sql'], 'tipo': ['tipo'],
    'campo': ['campo', 'colun'],
}


def _descricao_fala_do_papel(papel, descricao):
    palavras = _norm(descricao)
    termos = _TERMOS_DO_PAPEL.get(papel)
    if termos is None:
        partes = [p[:5] for p in papel.split('_') if p]
        return all(any(w.startswith(t) for w in palavras) for t in partes)
    return any(w.startswith(t) for t in termos for w in palavras)


class _Schema:
    def __init__(self, conn):
        self.colunas = defaultdict(dict)        # TABELA -> {COLUNA: descricao}
        self.pk = defaultdict(set)
        cols = {r[1] for r in conn.execute('PRAGMA table_info(colunas)')}
        tem_pk = 'pk_ordem' in cols
        sql = 'SELECT tabela, coluna, descricao' + (', pk_ordem' if tem_pk else ', NULL') + ' FROM colunas'
        for t, col, d, pk in conn.execute(sql):
            if col == '#':
                continue
            self.colunas[t.upper()][col.upper()] = d or ''
            if pk is not None:
                self.pk[t.upper()].add(col.upper())
        self.tabelas = {t.upper() for (t,) in conn.execute('SELECT tabela FROM tabelas')}
        self.fks = set()
        for f, cf, m, cm in conn.execute('SELECT tabela_filha, campo_filho, tabela_mae, campo_mae FROM relacionamentos'):
            self.fks.add((f.upper(), cf.upper(), m.upper(), cm.upper()))

    def tabela(self, t, onde, erros):
        if t.upper() not in self.tabelas:
            erros.append(f'{onde}: tabela não existe no schema')
            return False
        return True

    def coluna(self, t, col, onde, erros):
        if col.upper() not in self.colunas.get(t.upper(), {}):
            erros.append(f'{onde}: coluna não existe na tabela do schema')
            return False
        return True

    def chave_completa(self, t, chave, onde, erros):
        pk = self.pk.get(t.upper())
        if not pk:
            erros.append(f'{onde}: a tabela não tem PK conhecida (rode `york.py enriquecer`); a chave não pode ser conferida')
            return False
        falta = pk - {c.upper() for c in chave}
        if falta:
            erros.append(f'{onde}: chave incompleta, falta(m) {len(falta)} coluna(s) da PK')
            return False
        return True

    def descricao(self, t, col):
        return self.colunas.get(t.upper(), {}).get(col.upper(), '')


def conferir_e_compilar(m, conn):
    """Confere o mapa contra o contrato e o schema. Devolve o mapa compilado
    (dict de linhas por tabela `mapa_*`) ou levanta MapaRecusado."""
    erros = conferir_contrato(m)
    if erros:
        raise MapaRecusado(erros)
    s = _Schema(conn)
    papeis, estruturas, cadastros, rotulos, funcoes, fconsulta = [], [], [], [], [], []

    def papel(parte, dono, nome, tabela, col, onde, prova='descricao'):
        if not (s.tabela(tabela, onde, erros) and s.coluna(tabela, col, onde, erros)):
            return
        d = s.descricao(tabela, col)
        papeis.append({'parte': parte, 'dono': dono, 'papel': nome, 'tabela': tabela.upper(), 'coluna': col.upper(),
                       'papel_divergente': 0 if _descricao_fala_do_papel(nome, d) else 1, 'prova': prova,
                       'prova_do_papel': 'descricao', 'fonte_do_papel': None, 'confirmado_em': None,
                       'descricao_errada': 0})

    def estrutura(parte, tabela, chave, onde, ligacao=None):
        if not s.tabela(tabela, onde, erros):
            return
        ok = all([s.coluna(tabela, c_, f'{onde}.chave', erros) for c_ in chave])
        if ok:
            s.chave_completa(tabela, chave, f'{onde}.chave', erros)
        estruturas.append({'parte': parte, 'tabela': tabela.upper(), 'chave': json.dumps([c_.upper() for c_ in chave]),
                           'ligacao': json.dumps(ligacao) if ligacao is not None else None})

    f = m.get('formulas')
    if f:
        estrutura('formulas', f['tabela'], f['chave'], 'formulas')
        for p, col in f.get('colunas', {}).items():
            papel('formulas', '', p, f['tabela'], col, f'formulas.colunas.{p}')
        t = f.get('tipo')
        if t:
            lig = [[a.upper(), b.upper()] for a, b in t['ligacao']]
            for i, (a, b) in enumerate(lig):
                s.coluna(f['tabela'], a, f'formulas.tipo.ligacao[{i}][0]', erros)
                s.coluna(t['tabela'], b, f'formulas.tipo.ligacao[{i}][1]', erros)
            estrutura('formulas.tipo', t['tabela'], [b for _, b in lig], 'formulas.tipo', ligacao=lig)
            papel('formulas.tipo', '', 'descricao', t['tabela'], t['descricao'], 'formulas.tipo.descricao')
    q = m.get('consultas')
    if q:
        estrutura('consultas', q['tabela'], q['chave'], 'consultas')
        for p, col in q.get('colunas', {}).items():
            papel('consultas', '', p, q['tabela'], col, f'consultas.colunas.{p}')
        for parte, ps in (('campos', ('campo', 'descricao', 'tipo')), ('parametros', ('nome', 'descricao', 'tipo'))):
            sub = q.get(parte)
            if not sub:
                continue
            lig = [c_.upper() for c_ in sub['ligacao_com_consulta']]
            for c_ in lig:
                s.coluna(sub['tabela'], c_, f'consultas.{parte}.ligacao_com_consulta', erros)
            if len(lig) != len(q['chave']):
                erros.append(f'consultas.{parte}.ligacao_com_consulta: precisa ter as {len(q["chave"])} colunas da '
                             'chave da consulta, na mesma ordem')
            estrutura(f'consultas.{parte}', sub['tabela'], sub['chave'], f'consultas.{parte}', ligacao=lig)
            for p in ps:
                if p in sub:
                    papel(f'consultas.{parte}', '', p, sub['tabela'], sub[p], f'consultas.{parte}.{p}')
    for i, cad in enumerate(m.get('cadastros', [])):
        onde = f'cadastros[{i}]'
        t = cad['tabela']
        if not s.tabela(t, onde, erros):
            continue
        estrutura(f'cadastro:{cad["cadastro"]}', t, cad['chave'], onde)
        if cad['coluna_codigo'].upper() not in {c_.upper() for c_ in cad['chave']}:
            erros.append(f'{onde}.coluna_codigo: precisa fazer parte da chave')
        papel('cadastro', cad['cadastro'], 'codigo', t, cad['coluna_codigo'], f'{onde}.coluna_codigo')
        if 'coluna_descricao' in cad:
            papel('cadastro', cad['cadastro'], 'descricao', t, cad['coluna_descricao'], f'{onde}.coluna_descricao')
        cadastros.append({'cadastro': cad['cadastro'], 'tabela': t.upper(), 'chave': json.dumps([c_.upper() for c_ in cad['chave']]),
                          'coluna_codigo': cad['coluna_codigo'].upper(),
                          'coluna_descricao': cad.get('coluna_descricao', '').upper() or None, 'nota': cad.get('nota')})
        for r in cad['rotulos_parametro']:
            texto, prova, fonte = (r['rotulo'], r['prova'], r['fonte']) if isinstance(r, dict) else (r, 'declarado', None)
            rotulos.append({'cadastro': cad['cadastro'], 'rotulo': texto, 'rotulo_normalizado': ' '.join(_norm(texto)),
                            'prova': prova, 'fonte': fonte})
        for fn in cad.get('funcoes', []):
            funcoes.append({'cadastro': cad['cadastro'], 'funcao': fn.upper()})
        lf = cad.get('ligacoes_formula')
        if lf:
            destino = lf['tabela']
            if s.tabela(destino, f'{onde}.ligacoes_formula', erros):
                ok = all([s.coluna(destino, c_, f'{onde}.ligacoes_formula.chave_destino', erros) for c_ in lf['chave_destino']])
                if ok:
                    s.chave_completa(destino, lf['chave_destino'], f'{onde}.ligacoes_formula.chave_destino', erros)
                extra = [c_.upper() for c_ in lf.get('colunas_origem_extra', [])]
                for c_ in extra:
                    s.coluna(t, c_, f'{onde}.ligacoes_formula.colunas_origem_extra', erros)
                if len(extra) + 1 != len(lf['chave_destino']):
                    erros.append(f'{onde}.ligacoes_formula: colunas_origem_extra + a coluna do papel precisam ter o '
                                 'mesmo número de colunas da chave_destino')
                alvo = lf['chave_destino'][-1].upper()
                for p, col in lf['colunas_por_papel'].items():
                    o = f'{onde}.ligacoes_formula.colunas_por_papel.{p}'
                    if not s.coluna(t, col, o, erros):
                        continue
                    if (t.upper(), col.upper(), destino.upper(), alvo) in s.fks:
                        prova = 'fk'
                    elif 'formu' in ' '.join(_norm(s.descricao(t, col))):
                        prova = 'descricao'
                    else:
                        erros.append(f'{o}: ligação com a fórmula sem prova (nem FK no schema, nem descrição que cite fórmula)')
                        continue
                    papel('ligacao_formula', cad['cadastro'], p, t, col, o, prova)
                    conf = lf.get('papeis_confirmados', {}).get(p)
                    if conf:                # o usuário resolveu a divergência: vale o papel declarado
                        papeis[-1].update({'papel_divergente': 0, 'prova_do_papel': conf['prova'],
                                           'fonte_do_papel': conf['fonte'], 'confirmado_em': conf['data'],
                                           'descricao_errada': 1 if conf.get('descricao_da_origem_errada') else 0})
                    papeis[-1]['destino'] = destino.upper()
                    papeis[-1]['colunas_origem'] = json.dumps(extra + [col.upper()])
                    papeis[-1]['chave_destino'] = json.dumps([c_.upper() for c_ in lf['chave_destino']])
    fc = m.get('funcoes_de_consulta')
    if fc:
        for k in ('executar', 'ler_campo', 'avancar_registro'):
            if k in fc:
                fconsulta.append({'papel': k, 'funcao': fc[k].upper()})
        fconsulta.append({'papel': 'parametros_na_chamada', 'funcao': '1' if fc.get('parametros_na_chamada') else '0'})
    if erros:
        raise MapaRecusado(erros)
    return {'mapa_estruturas': estruturas, 'mapa_cadastros': cadastros, 'mapa_rotulos': rotulos,
            'mapa_funcoes': funcoes, 'mapa_papeis': papeis, 'mapa_funcoes_consulta': fconsulta}


COLUNAS_MAPA = {
    'mapa_estruturas': ('parte', 'tabela', 'chave', 'ligacao'),
    'mapa_cadastros': ('cadastro', 'tabela', 'chave', 'coluna_codigo', 'coluna_descricao', 'nota'),
    'mapa_rotulos': ('cadastro', 'rotulo', 'rotulo_normalizado', 'prova', 'fonte'),
    'mapa_funcoes': ('cadastro', 'funcao'),
    'mapa_papeis': ('parte', 'dono', 'papel', 'tabela', 'coluna', 'papel_divergente', 'prova', 'destino',
                    'colunas_origem', 'chave_destino', 'prova_do_papel', 'fonte_do_papel', 'confirmado_em',
                    'descricao_errada'),
    'mapa_funcoes_consulta': ('papel', 'funcao'),
}


def compilar(caminho_mapa, db_path, destino_backup=None):
    """York: confere e grava o mapa na Punk Records (versão >= 4), com cópia
    de segurança e numa transação. Substitui o mapa compilado anterior
    inteiro. Devolve o relatório (contagens e divergências)."""
    import hashlib
    import shutil
    import sqlite3

    from punk_records import migracoes

    with open(caminho_mapa, 'rb') as fh:
        bruto = fh.read()
    try:
        m = json.loads(bruto.decode('utf-8-sig'))
    except (UnicodeDecodeError, ValueError) as e:
        raise MapaRecusado([f'arquivo não é JSON válido em UTF-8: {e}']) from None
    conn = sqlite3.connect(f'file:{os.path.abspath(db_path)}?mode=ro', uri=True)
    try:
        versao = migracoes.versao_atual(conn)
        if versao < VERSAO_MINIMA_DA_BASE:
            raise RuntimeError(f'base na versão {versao}; rode `york.py migrar aplicar` antes '
                               f'(o mapa precisa da versão {VERSAO_MINIMA_DA_BASE})')
        compilado = conferir_e_compilar(m, conn)
    finally:
        conn.close()
    if migracoes._sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite presentes: {migracoes._sobras(db_path)}')
    copia = migracoes.copiar_seguranca(db_path, destino_backup)
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute('BEGIN IMMEDIATE')
        for tabela, cols in COLUNAS_MAPA.items():
            conn.execute(f'DELETE FROM {tabela}')
            for linha in compilado[tabela]:
                conn.execute(f'INSERT INTO {tabela} ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})',
                             tuple(linha.get(c_) for c_ in cols))
        conn.execute("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('mapa:sha256', ?)",
                     (hashlib.sha256(bruto).hexdigest(),))
        conn.execute("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('mapa:ficticio', ?)",
                     ('1' if m.get('ficticio') else '0',))
        conn.execute('COMMIT')
        ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if ok != 'ok':
            raise RuntimeError(f'integrity_check depois da compilação do mapa: {ok}')
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except sqlite3.OperationalError:
            pass
        conn.close()
        shutil.copy2(copia, db_path)
        raise
    conn.close()
    if migracoes._sobras(db_path):
        raise RuntimeError(f'arquivos temporários do SQLite ficaram para trás: {migracoes._sobras(db_path)}')
    divergentes = [p for p in compilado['mapa_papeis'] if p['papel_divergente']]
    resolvidos = [p for p in compilado['mapa_papeis'] if p['prova_do_papel'] == 'usuario']
    return {'copia': copia, **{t: len(v) for t, v in compilado.items()},
            'divergencias': [{k: p[k] for k in ('parte', 'dono', 'papel', 'tabela', 'coluna', 'prova')} for p in divergentes],
            'resolvidos_pelo_usuario': [{k: p[k] for k in ('parte', 'dono', 'papel', 'tabela', 'coluna', 'fonte_do_papel',
                                                           'confirmado_em', 'descricao_errada')} for p in resolvidos]}
