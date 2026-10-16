"""
Importação do schema (CSV de introspecção -> punk_records.db): leitura e
validação dos CSVs, criação das 5 tabelas, métricas estruturais
(filhas/pais/conexões/score/ranking) e checagem de integridade das FKs.

Só estrutura entra: nomes de tabela e coluna, descrições e ligações. Movido
sem alteração do antigo `nomi_nomi_no_mi.py` (fase 1 da v3); exposto por
`york.py importar`.
"""

import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Set

from dominios.schema.config import COLUNAS_ESTRUTURA


# ==============================================================================
# ==============================================================================
# IMPORTAÇÃO (CSV -> punk_records.db)
# ==============================================================================

# Uma linha por par (tabela, coluna) obrigatória, coluna extra opcional.
COLUNAS_OBRIGATORIAS_CSV = {
    'tabelas.csv': {'tabela'},                                        # + descricao, tem_dados (opcionais)
    'colunas.csv': {'tabela', 'coluna'},                              # + descricao (opcional)
    'relacionamentos.csv': {'tabela_filha', 'campo_filho', 'tabela_mae', 'campo_mae'},
    'sistemas.csv': {'codigo_sistema', 'nome_sistema'},                # + descricao (opcional)
    'sinonimos.csv': {'termo', 'sinonimo'},
}

# Só estes dois são indispensáveis pro motor funcionar; os outros 3
# melhoram o resultado mas o motor degrada graciosamente sem eles (ver
# `carregar_dominio_do_db` e os guards de MODULOS_PRIORIZADOS acima).
CSV_OBRIGATORIOS = {'tabelas.csv', 'colunas.csv'}


# Linhas que o SSMS ("Results to File") e o sqlcmd acrescentam fora do
# resultado: não fazem parte do CSV.
_LINHAS_DE_RODAPE = re.compile(r'^(completion time:|\(\d+ (rows?|linhas?) (affected|afetadas?)\)$)', re.I)


class CsvVazioError(ValueError):
    """CSV de extração sem nenhuma linha de dados: nunca passa em silêncio."""


def ler_csv_extracao(caminho: str) -> 'tuple[List[str], List[Dict[str, str]]]':
    """Lê um CSV de extração: UTF-8 (com ou sem BOM) ou UTF-16 (o que o SSMS
    grava em "Results to File"), ignorando espaços no fim das linhas (o
    sqlcmd completa a coluna), linhas em branco e o rodapé do SSMS/sqlcmd.
    CSV vazio ou só com cabeçalho é RECUSADO com CsvVazioError."""
    import csv
    import io
    with open(caminho, 'rb') as f:
        bruto = f.read()
    if bruto.startswith((b'\xff\xfe', b'\xfe\xff')):
        texto = bruto.decode('utf-16')
    else:
        try:
            texto = bruto.decode('utf-8-sig')
        except UnicodeDecodeError as e:
            raise ValueError(f'{os.path.basename(caminho)}: codificação não reconhecida (esperado UTF-8 ou '
                             f'UTF-16): {e}') from None
    linhas = [l.rstrip() for l in texto.splitlines()]
    linhas = [l for l in linhas if l and not _LINHAS_DE_RODAPE.match(l)]
    linhas = _desembrulhar_grade_do_ssms(linhas)
    leitor = csv.DictReader(io.StringIO('\n'.join(linhas)))
    registros = list(leitor)
    if not registros:
        raise CsvVazioError(
            f'{os.path.basename(caminho)}: sem nenhuma linha de dados (arquivo vazio ou só com cabeçalho). '
            'A extração devolveu vazio: confira se o banco certo estava selecionado e o @esquema da consulta. '
            'Nada foi gravado.')
    return list(leitor.fieldnames or []), registros


def _desembrulhar_grade_do_ssms(linhas: List[str]) -> List[str]:
    """A consulta de extração devolve UMA coluna com a linha de CSV pronta.
    Salva pela grade do SSMS ("Save Results As"), cada linha de dados vira um
    campo só: entre aspas e com as aspas internas duplicadas. Se o cabeçalho
    tem várias colunas e TODA linha de dados é um campo só, desembrulha cada
    uma (sem perda). Em qualquer outro caso, não mexe."""
    import csv
    if len(linhas) < 2 or len(next(csv.reader([linhas[0]]))) < 2:
        return linhas
    campos = [next(csv.reader([l])) for l in linhas[1:]]
    if not all(len(c) == 1 and ',' in c[0] for c in campos):
        return linhas
    return [linhas[0]] + [c[0] for c in campos]


def limpar_nulos(registros: List[Dict[str, str]]) -> int:
    """O texto literal NULL (o que o SSMS grava num campo nulo ao exportar)
    vira vazio, em qualquer campo. Devolve quantos campos foram convertidos,
    para o relatório de cada importação."""
    n = 0
    for r in registros:
        for k, v in r.items():
            if isinstance(v, str) and v.strip().upper() == 'NULL':
                r[k] = ''
                n += 1
    return n


def expandir_ligacoes(registros: List[Dict[str, str]]) -> 'tuple[List[Dict[str, str]], int]':
    """relacionamentos.csv no formato do dicionário do sistema: UMA linha por
    ligação, com os campos em lista ("CODEMP,CODPAI" -> "CODEMP,CODPAI"). Vira
    uma linha por campo, com o número da ligação em `ligacao` (1, 2, ... na
    ordem estável da ligação). Linha com um campo só também recebe número.
    Listas de tamanhos diferentes são recusadas. Devolve (linhas, ligações)."""
    if not any(',' in (r.get('campo_filho') or '') or ',' in (r.get('campo_mae') or '') for r in registros):
        return registros, 0
    ordenadas = sorted(registros, key=lambda r: tuple((r.get(k) or '').strip().upper() for k in
                                                     ('tabela_filha', 'tabela_mae', 'campo_filho', 'campo_mae')))
    out = []
    for n, r in enumerate(ordenadas, 1):
        filhos = [c.strip() for c in r['campo_filho'].split(',')]
        maes = [c.strip() for c in r['campo_mae'].split(',')]
        if len(filhos) != len(maes) or not all(filhos) or not all(maes):
            raise ValueError(f"relacionamentos.csv: ligação {r['tabela_filha']} -> {r['tabela_mae']} com listas de "
                             f"campos de tamanhos diferentes ou com campo vazio: {r['campo_filho']!r} -> "
                             f"{r['campo_mae']!r}. Nada foi gravado.")
        for cf, cm in zip(filhos, maes):
            out.append({**r, 'campo_filho': cf, 'campo_mae': cm, 'ligacao': str(n)})
    return out, len(ordenadas)


def _ler_csv(caminho: str, colunas_obrigatorias: Set[str]) -> List[Dict[str, str]]:
    cabecalho, registros = ler_csv_extracao(caminho)
    faltando = colunas_obrigatorias - set(cabecalho)
    if faltando:
        raise ValueError(
            f"{os.path.basename(caminho)}: faltam colunas obrigatórias no cabeçalho: "
            f"{', '.join(sorted(faltando))} (encontrado: {', '.join(sorted(cabecalho))})"
        )
    return registros


# Colunas de estrutura opcionais nos CSVs (fase 2 da v3, vindas do
# punk_records/extracao/tabelas.sql). CSV sem elas continua aceito: ficam
# nulas. Nenhuma delas entra no ranking da busca.
_COLUNAS_ESTRUTURA_INTEIRAS = ('tamanho', 'precisao', 'escala', 'ordem', 'pk_ordem')
RELACIONAMENTO_ESTRUTURA = (('constraint', 'constraint_nome'), ('ordem', 'ordem'))
_VERDADEIRO = {'1', 'true', 'sim', 's', 'yes', 'y'}


def _inteiro(valor):
    valor = (valor or '').strip()
    return int(valor) if valor.lstrip('-').isdigit() else None


def estrutura_da_coluna(row: Dict[str, str]) -> tuple:
    """(tipo, tamanho, precisao, escala, nulo, ordem, pk_ordem) de uma linha
    de colunas.csv; campo ausente ou vazio vira None."""
    out = []
    for campo in COLUNAS_ESTRUTURA:
        bruto = (row.get(campo) or '').strip()
        if campo == 'tipo':
            out.append(bruto.lower() or None)
        elif campo == 'nulo':
            out.append(None if not bruto else (1 if bruto.lower() in _VERDADEIRO else 0))
        else:
            out.append(_inteiro(bruto))
    return tuple(out)


def estrutura_do_relacionamento(row: Dict[str, str]) -> tuple:
    """(constraint_nome, ordem) de uma linha de relacionamentos.csv."""
    return ((row.get('constraint') or '').strip() or None, _inteiro(row.get('ordem')))


def ligacao_do_relacionamento(row: Dict[str, str]):
    """Número da ligação do dicionário (formato em lista), ou None."""
    return _inteiro(row.get('ligacao'))


def criar_schema(conn: sqlite3.Connection):
    """Cria as 5 tabelas (schema vazio). Usado tanto para gerar o banco
    vazio publicado no repositório quanto como primeiro passo do
    `importar` (que recria do zero antes de popular)."""
    cur = conn.cursor()
    cur.executescript("""
        DROP TABLE IF EXISTS tabelas;
        DROP TABLE IF EXISTS colunas;
        DROP TABLE IF EXISTS relacionamentos;
        DROP TABLE IF EXISTS sistemas;
        DROP TABLE IF EXISTS sinonimos;

        CREATE TABLE tabelas (
            tabela TEXT PRIMARY KEY,
            descricao TEXT,
            score_relevancia REAL,
            ranking INTEGER,
            tabelas_filhas INTEGER,
            tabelas_pais INTEGER,
            conexoes_totais INTEGER,
            tem_dados INTEGER
        );
        CREATE TABLE colunas (
            tabela TEXT,
            coluna TEXT,
            descricao TEXT,
            tipo TEXT,
            tamanho INTEGER,
            precisao INTEGER,
            escala INTEGER,
            nulo INTEGER,
            ordem INTEGER,
            pk_ordem INTEGER
        );
        CREATE TABLE relacionamentos (
            tabela_filha TEXT,
            campo_filho TEXT,
            tabela_mae TEXT,
            campo_mae TEXT,
            constraint_nome TEXT,
            ordem INTEGER,
            ligacao INTEGER
        );
        CREATE TABLE sistemas (
            codigo_sistema TEXT PRIMARY KEY,
            nome_sistema TEXT,
            descricao TEXT
        );
        CREATE TABLE sinonimos (
            termo TEXT,
            sinonimo TEXT
        );
        CREATE INDEX idx_colunas_tabela ON colunas(tabela);
        CREATE INDEX idx_rel_filha ON relacionamentos(tabela_filha);
        CREATE INDEX idx_rel_mae ON relacionamentos(tabela_mae);
        CREATE INDEX idx_sinonimos_termo ON sinonimos(termo);
    """)
    conn.commit()


# Pesos estruturais do `score_relevancia` (filhas, conexões, pais). Só a
# proporção importa: o score passa por min-max em `_buscar_criticas`.
# Até a v3-fase4: 40/30/15 (v1, com a direção do dicionário trocada).
# Fase 5: recalibrados só no conjunto de calibração do schema real (grade
# de passo 0,05, direção das FKs corrigida, só ligação com as duas pontas
# na base) e conferidos uma vez no cego; a fixture segue 31/31.
PESO_FILHAS, PESO_CONEXOES, PESO_PAIS = 0.0, 0.15, 0.85


def calcular_metricas_e_scores(
    tabelas: 'Set[str] | List[str]', pares_filha_mae: List[tuple], pesos: 'tuple | None' = None
) -> Dict[str, Dict]:
    """Calcula, para cada tabela em `tabelas`, as métricas derivadas
    (tabelas_filhas, tabelas_pais, conexoes_totais) e o score_relevancia/
    ranking: filhas + conexões + pais, cada componente normalizado 0-100
    pelo máximo do conjunto (ver referencias/schema.md).

    Os pesos (PESO_FILHAS/PESO_CONEXOES/PESO_PAIS, no módulo) foram
    recalibrados na fase 5 da v3. Até a v3-fase4 eles preservavam a
    proporção relativa (40/30/15) que a fórmula original tinha antes de
    incluir um 4º componente — log do volume de registros (`total_registros`) por
    tabela. Esse componente foi removido do motor (auditoria de
    privacidade, setembro/2026): a contagem de linhas de uma tabela real
    é, ela própria, um dado sensível (revela volume de negócio da
    empresa) que não precisa ser lido/armazenado para o motor cumprir seu
    papel (achar a tabela certa por nome/coluna/FK, não por popularidade
    de dado). Renormalizar os 3 pesos restantes para somar 1.0 preserva a
    IMPORTÂNCIA RELATIVA entre eles (filhas > conexões > pais, na mesma
    proporção 40:30:15 de antes) — como o `score_relevancia` resultante só
    é usado depois de uma normalização min-max (ver `_buscar_criticas`),
    a ordenação final seria idêntica mesmo sem renormalizar; fazemos isso
    só para manter a escala 0-100 do docstring/comentários coerente.

    ÚNICA implementação desta fórmula no pacote — usada tanto por
    `importar_csvs` (schema real) quanto pela fixture fictícia de
    `casos/fixture_schema.py` (schema de teste), justamente para as duas nunca poderem
    dessincronizar: se a fórmula mudar aqui, a suíte de regressão passa a
    validar contra a fórmula nova automaticamente, sem precisar editar em
    dois lugares.

    `tabelas`: nomes de tabela (não precisa mais de contagem de registro
    nenhuma). `pares_filha_mae`: lista de (tabela_filha, tabela_mae) — só
    os dois campos usados para contar filhas/pais/conexões, não a linha
    de FK inteira.

    Só conta a ligação com as DUAS tabelas em `tabelas` (fase 5): ligação
    para tabela que não está na base não prova relevância. A linha da
    ligação continua na base; só deixa de contar aqui.

    `pesos`: (filhas, conexões, pais); omitido = os pesos do módulo.

    Retorna {tabela: {tabelas_filhas, tabelas_pais, conexoes_totais,
    score_relevancia, ranking}}.
    """
    existentes = set(tabelas)
    filhas_por_tabela = defaultdict(set)
    pais_por_tabela = defaultdict(set)
    for tabela_filha, tabela_mae in pares_filha_mae:
        if tabela_filha not in existentes or tabela_mae not in existentes:
            continue
        filhas_por_tabela[tabela_mae].add(tabela_filha)
        pais_por_tabela[tabela_filha].add(tabela_mae)

    metricas = {}
    for tabela in tabelas:
        n_filhas = len(filhas_por_tabela.get(tabela, ()))
        n_pais = len(pais_por_tabela.get(tabela, ()))
        metricas[tabela] = {
            'tabelas_filhas': n_filhas,
            'tabelas_pais': n_pais,
            'conexoes_totais': n_filhas + n_pais,
        }

    max_filhas = max((m['tabelas_filhas'] for m in metricas.values()), default=0) or 1
    max_conexoes = max((m['conexoes_totais'] for m in metricas.values()), default=0) or 1
    max_pais = max((m['tabelas_pais'] for m in metricas.values()), default=0) or 1

    # renormalizados para somar 1.0 (ver docstring acima)
    peso_filhas, peso_conexoes, peso_pais = pesos or (PESO_FILHAS, PESO_CONEXOES, PESO_PAIS)
    soma_pesos = peso_filhas + peso_conexoes + peso_pais

    scores = []
    for tabela, m in metricas.items():
        score = (
            100.0 * m['tabelas_filhas'] / max_filhas * peso_filhas
            + 100.0 * m['conexoes_totais'] / max_conexoes * peso_conexoes
            + 100.0 * m['tabelas_pais'] / max_pais * peso_pais
        ) / soma_pesos
        scores.append((tabela, round(score, 2)))
    # empate de score: desempata pelo nome da tabela (`tabelas` pode ser
    # um `set`, e a ordem dele depende de PYTHONHASHSEED)
    scores.sort(key=lambda par: (-par[1], par[0]))
    ranking_por_tabela = {tabela: i for i, (tabela, _) in enumerate(scores, start=1)}
    score_por_tabela = dict(scores)

    for tabela, m in metricas.items():
        m['score_relevancia'] = score_por_tabela[tabela]
        m['ranking'] = ranking_por_tabela[tabela]
    return metricas


def validar_integridade_relacionamentos(
    tabelas_validas: Set[str], colunas_por_tabela: Dict[str, Set[str]], linhas_relacionamentos: List[Dict[str, str]]
) -> List[str]:
    """Confere se cada FK de `relacionamentos.csv` aponta pra uma tabela e
    coluna que realmente existem em `tabelas.csv`/`colunas.csv`. Não
    bloqueia o import (um typo não deve travar quem está importando) —
    só devolve avisos legíveis, um por problema encontrado, pra quem
    importou saber que aquela FK não vai virar um JOIN válido.
    """
    avisos = []
    for row in linhas_relacionamentos:
        tabela_filha = row['tabela_filha'].strip()
        campo_filho = row['campo_filho'].strip()
        tabela_mae = row['tabela_mae'].strip()
        campo_mae = row['campo_mae'].strip()

        if tabela_filha not in tabelas_validas:
            avisos.append(f"relacionamentos.csv: tabela_filha '{tabela_filha}' não está em tabelas.csv")
        elif campo_filho not in colunas_por_tabela.get(tabela_filha, set()):
            avisos.append(
                f"relacionamentos.csv: campo_filho '{campo_filho}' não está entre as colunas "
                f"de '{tabela_filha}' em colunas.csv — essa FK não vai gerar um JOIN válido"
            )

        if tabela_mae not in tabelas_validas:
            avisos.append(f"relacionamentos.csv: tabela_mae '{tabela_mae}' não está em tabelas.csv")
        elif campo_mae not in colunas_por_tabela.get(tabela_mae, set()):
            avisos.append(
                f"relacionamentos.csv: campo_mae '{campo_mae}' não está entre as colunas "
                f"de '{tabela_mae}' em colunas.csv — essa FK não vai gerar um JOIN válido"
            )
    return avisos


def importar_csvs(dir_csvs: str, db_path: str, sobrescrever: bool = True) -> Dict[str, object]:
    """Lê tabelas.csv / colunas.csv / relacionamentos.csv / sistemas.csv
    / sinonimos.csv de `dir_csvs`, calcula os campos derivados
    (tabelas_filhas, tabelas_pais, conexoes_totais, score_relevancia,
    ranking — a pessoa não precisa calcular isso na mão) e grava tudo
    em `db_path`, recriando o schema do zero.

    `sistemas.csv` e `sinonimos.csv` são opcionais — se ausentes, o
    motor funciona sem inferência de módulo/expansão de sinônimo (ver
    guards de MODULOS_PRIORIZADOS/SINONIMOS no motor).

    Também valida (sem travar o import — ver `validar_integridade_
    relacionamentos`) se as FKs de `relacionamentos.csv` apontam pra
    tabelas/colunas que existem; os problemas encontrados voltam na
    chave 'avisos' do retorno.
    """
    if not os.path.isdir(dir_csvs):
        raise FileNotFoundError(f"Diretório não encontrado: {dir_csvs}")

    presentes = {f for f in COLUNAS_OBRIGATORIAS_CSV if os.path.exists(os.path.join(dir_csvs, f))}
    faltando_obrigatorios = CSV_OBRIGATORIOS - presentes
    if faltando_obrigatorios:
        raise FileNotFoundError(
            f"Arquivo(s) obrigatório(s) não encontrado(s) em {dir_csvs}: "
            f"{', '.join(sorted(faltando_obrigatorios))}"
        )

    dados = {}
    nulos = {}
    for nome_arquivo, colunas_obrig in COLUNAS_OBRIGATORIAS_CSV.items():
        caminho = os.path.join(dir_csvs, nome_arquivo)
        dados[nome_arquivo] = _ler_csv(caminho, colunas_obrig) if nome_arquivo in presentes else []
        nulos[nome_arquivo] = limpar_nulos(dados[nome_arquivo])
    dados['relacionamentos.csv'], ligacoes = expandir_ligacoes(dados['relacionamentos.csv'])

    if os.path.exists(db_path) and not sobrescrever:
        raise FileExistsError(f"{db_path} já existe (use sobrescrever=True/--forcar para substituir)")

    # --- integridade referencial: aviso, não trava (ver docstring da função) ---
    tabelas_validas = {row['tabela'].strip() for row in dados['tabelas.csv']}
    colunas_por_tabela = defaultdict(set)
    for row in dados['colunas.csv']:
        colunas_por_tabela[row['tabela'].strip()].add(row['coluna'].strip())
    avisos = validar_integridade_relacionamentos(
        tabelas_validas, colunas_por_tabela, dados['relacionamentos.csv']
    )

    conn = sqlite3.connect(db_path)
    criar_schema(conn)
    cur = conn.cursor()

    # --- colunas / relacionamentos / sistemas / sinonimos: import direto ---
    for row in dados['colunas.csv']:
        cur.execute(
            "INSERT INTO colunas (tabela, coluna, descricao, tipo, tamanho, precisao, escala, nulo, ordem, pk_ordem) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (row['tabela'].strip(), row['coluna'].strip(), (row.get('descricao') or '').strip())
            + estrutura_da_coluna(row)
        )
    for row in dados['relacionamentos.csv']:
        cur.execute(
            "INSERT INTO relacionamentos (tabela_filha, campo_filho, tabela_mae, campo_mae, constraint_nome, ordem, "
            "ligacao) VALUES (?,?,?,?,?,?,?)",
            (row['tabela_filha'].strip(), row['campo_filho'].strip(),
             row['tabela_mae'].strip(), row['campo_mae'].strip()) + estrutura_do_relacionamento(row)
            + (ligacao_do_relacionamento(row),)
        )
    for row in dados['sistemas.csv']:
        cur.execute(
            "INSERT INTO sistemas (codigo_sistema, nome_sistema, descricao) VALUES (?,?,?)",
            (row['codigo_sistema'].strip(), row['nome_sistema'].strip(), (row.get('descricao') or '').strip())
        )
    for row in dados['sinonimos.csv']:
        cur.execute(
            "INSERT INTO sinonimos (termo, sinonimo) VALUES (?,?)",
            (row['termo'].strip().lower(), row['sinonimo'].strip().lower())
        )

    # --- tabelas: descrição e métricas derivadas (tabelas_filhas/pais/
    # conexoes, score_relevancia, ranking) são CALCULADAS, não digitadas —
    # ver `calcular_metricas_e_scores` (mesma função usada pela fixture
    # fictícia (casos/fixture_schema.py), para as duas nunca dessincronizarem). O motor
    # não lê nem grava contagem de linha (total_registros) — só metadados
    # estruturais (nome/coluna/FK), nunca volume de dado real (auditoria
    # de privacidade, setembro/2026 — ver `calcular_metricas_e_scores`).
    #
    # `tem_dados` (v1.5) é a exceção deliberada: um sinal BINÁRIO
    # (populada ou vazia), não uma contagem — o suficiente para
    # `PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL` distinguir uma tabela de
    # staging vazia (0 conexões, sem dado nenhum) de uma tabela real mas
    # só sem FK modelada (0 conexões, mas com dado) sem expor volume de
    # negócio nenhum. Opcional no CSV — ausente/vazio/não reconhecido
    # vira 0 (mesmo comportamento conservador de antes desta coluna
    # existir: sem evidência de dado, o motor não assume que há dado).
    descricao_por_tabela = {
        row['tabela'].strip(): (row.get('descricao') or '').strip() for row in dados['tabelas.csv']
    }
    VALORES_VERDADEIROS = {'1', 'true', 'sim', 's', 'yes', 'y'}
    tem_dados_por_tabela = {
        row['tabela'].strip(): (
            1 if (row.get('tem_dados') or '').strip().lower() in VALORES_VERDADEIROS else 0
        )
        for row in dados['tabelas.csv']
    }
    pares_filha_mae = [
        (row['tabela_filha'].strip(), row['tabela_mae'].strip()) for row in dados['relacionamentos.csv']
    ]
    metricas = calcular_metricas_e_scores(tabelas_validas, pares_filha_mae)

    for tabela, m in metricas.items():
        cur.execute(
            """INSERT INTO tabelas
               (tabela, descricao, score_relevancia, ranking,
                tabelas_filhas, tabelas_pais, conexoes_totais, tem_dados)
               VALUES (?,?,?,?,?,?,?,?)""",
            (tabela, descricao_por_tabela.get(tabela) or None, m['score_relevancia'], m['ranking'],
             m['tabelas_filhas'], m['tabelas_pais'], m['conexoes_totais'],
             tem_dados_por_tabela.get(tabela, 0))
        )

    conn.commit()
    contagens = {
        'tabelas': len(metricas),
        'colunas': len(dados['colunas.csv']),
        'relacionamentos': len(dados['relacionamentos.csv']),
        'sistemas': len(dados['sistemas.csv']),
        'sinonimos': len(dados['sinonimos.csv']),
        'ligacoes_do_dicionario': ligacoes,
        'nulos_convertidos': sum(nulos.values()),
        'avisos': avisos,
    }
    conn.close()
    return contagens
