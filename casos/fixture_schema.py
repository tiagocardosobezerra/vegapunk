"""
Fixture fictícia do domínio schema ("Sistema Aurora").

Banco Punk Records de teste, 100% inventado, gerado sob demanda numa pasta
temporária. É o schema contra o qual rodam a avaliação do Pythagoras
(`pythagoras.py avaliar --dominio schema`) e o golden fictício do Atlas.
Movido sem alteração da antiga `scripts/stella.py` (fase 1 da v3).
"""

import random
import sqlite3

from punk_records.schema import criar_schema, calcular_metricas_e_scores


# ==============================================================================
# FIXTURE FICTÍCIA EMBUTIDA ("Sistema Aurora") — só para esta suite de testes
# ==============================================================================
# Módulos e tabelas 100% inventados; formato (prefixo de letra + nome +
# descrição de negócio em PT-BR) escolhido só para exercitar o motor em
# casos-limite conhecidos (tabela hub, tabela quase-órfã, termo genérico,
# ordinal por extenso, ambiguidade léxica). Nenhuma relação com nenhum
# ERP real.

_SISTEMAS = [
    ('N', 'Nucleo', 'Fundacao/geral'),
    ('T', 'Turno', 'Ponto/jornada'),
    ('F', 'Folha', 'Folha de pagamento'),
    ('S', 'Selecao', 'Recrutamento/carreira'),
    ('R', 'Reservado', ''),
]

_SINONIMOS = [
    ('colaborador', 'funcionario'), ('colaboradores', 'funcionario'),
    ('empregado', 'funcionario'), ('empregados', 'funcionario'),
    ('demissao', 'desligamento'), ('desligamento', 'deligamento'),
    ('salario', 'remuneracao'), ('salario', 'vencimento'),
    ('contratacao', 'admissao'), ('admitir', 'admissao'),
    ('ferias', 'gozo'), ('ponto', 'marcacao'), ('batida', 'marcacao'),
    ('empresa', 'unidade'), ('chefe', 'gestor'), ('chefe', 'superior'),
    ('supervisor', 'gestor'), ('supervisor', 'superior'),
    ('visita', 'visitante'), ('visitas', 'visitante'),
]

_TABELAS_NOMEADAS = {
    'N_EMPRESA': [('#', 'Empresas cadastradas no grupo'), ('CODEMPRESA', 'Codigo da empresa'),
                 ('RAZAOSOCIAL', 'Razao social da empresa'), ('CNPJ', 'CNPJ da empresa')],
    'N_UNIDADE': [('#', 'Unidades da empresa'), ('CODUNIDADE', 'Codigo da unidade'),
                 ('CODEMPRESA', 'Codigo da empresa proprietaria da unidade'), ('NOMEUNIDADE', 'Nome da unidade')],
    'N_USUARIO': [('#', 'Usuarios com acesso ao sistema'), ('CODUSUARIO', 'Codigo do usuario'),
                 ('LOGIN', 'Login de acesso do usuario'), ('CODEMPRESA', 'Codigo da empresa do usuario')],
    'N_ENDERECO': [('#', 'Enderecos cadastrados no sistema'), ('CODENDERECO', 'Codigo do endereco'),
                  ('LOGRADOURO', 'Logradouro do endereco'), ('CODEMPRESA', 'Codigo da empresa dona do endereco')],
    'F_FUNCIONARIO': [('#', 'Colaboradores da empresa'), ('MATRICULA', 'Matricula do colaborador'),
                      ('CODEMPRESA', 'Codigo da empresa do colaborador'), ('NOME', 'Nome do colaborador'),
                      ('CPF', 'CPF do colaborador'), ('DATAADMISSAO', 'Data de admissao do colaborador'),
                      ('VALORREMUNERACAO', 'Valor da remuneracao mensal do colaborador'),
                      ('CODCARGO', 'Codigo do cargo do colaborador')],
    'F_CARGO': [('#', 'Cargos dos colaboradores'), ('CODCARGO', 'Codigo do cargo'),
               ('DESCRICAOCARGO', 'Descricao do cargo')],
    'F_SINDICATO': [('#', 'Sindicatos'), ('CODSINDICATO', 'Codigo do sindicato'),
                   ('NOMESINDICATO', 'Nome do sindicato')],
    'F_SINDICATO_OPCAO': [('#', 'Opcao de sindicato do colaborador'), ('MATRICULA', 'Matricula do colaborador'),
                         ('CODSINDICATO', 'Codigo do sindicato escolhido')],
    'F_CONVENIO': [('#', 'Convenios medicos da empresa'), ('CODCONVENIO', 'Codigo do convenio medico'),
                  ('NOMECONVENIO', 'Nome do convenio medico')],
    'F_MOTIVO_DESLIGAMENTO': [('#', 'Motivos de desligamento do colaborador'),
                             ('CODMOTIVO', 'Codigo do motivo de desligamento'),
                             ('DESCRICAOMOTIVO', 'Descricao do motivo de desligamento')],
    'F_TIPO_DESLIGAMENTO': [('#', 'Tipos de desligamento contratual'), ('CODTIPO', 'Codigo do tipo de desligamento'),
                           ('DESCRICAOTIPO', 'Descricao do tipo de desligamento contratual')],
    'F_DESLIGAMENTO': [('#', 'Dados de deligamento contratual do colaborador'),
                            ('MATRICULA', 'Matricula do colaborador'),
                            ('DATADESLIGAMENTO', 'Data de desligamento do colaborador'),
                            ('CODMOTIVO', 'Codigo do motivo de deligamento')],
    'F_PROVISAO_DECIMO_TERCEIRO': [('#', 'Provisao do 13 salario'), ('MATRICULA', 'Matricula do colaborador'),
                                 ('VALORPROVISAO', 'Valor provisionado do 13 salario')],
    'F_PROVISAO_FERIAS': [('#', 'Provisao de ferias do colaborador'), ('MATRICULA', 'Matricula do colaborador'),
                         ('VALORPROVISAO', 'Valor provisionado de ferias')],
    'F_BENEFICIO': [('#', 'Beneficios oferecidos ao colaborador'), ('MATRICULA', 'Matricula do colaborador'),
                   ('CODBENEFICIO', 'Codigo do beneficio')],
    'F_FERIAS': [('#', 'Ferias do colaborador'), ('MATRICULA', 'Matricula do colaborador'),
                ('DATAINICIOGOZO', 'Data de inicio do gozo de ferias')],
    'F_SALDO_FERIAS': [('#', 'Saldo de ferias do colaborador'), ('MATRICULA', 'Matricula do colaborador'),
                      ('DIASSALDO', 'Dias de saldo de ferias')],
    'F_SALDO_FERIAS_PERIODO': [('#', 'Saldo de ferias por periodo aquisitivo'), ('MATRICULA', 'Matricula do colaborador'),
                             ('PERIODOAQUISITIVO', 'Periodo aquisitivo de ferias')],
    'F_DADOS_PESSOAIS': [('#', 'Dados pessoais do colaborador'), ('MATRICULA', 'Matricula do colaborador'),
                ('DATANASCIMENTO', 'Data de nascimento do colaborador')],
    'T_HORARIO': [('#', 'Horarios de trabalho cadastrados'), ('CODHORARIO', 'Codigo do horario de trabalho'),
                 ('DESCRICAOHORARIO', 'Descricao do horario de trabalho')],
    'T_BANCO_HORAS': [('#', 'Banco de horas do colaborador'), ('MATRICULA', 'Matricula do colaborador'),
                       ('SALDOMINUTOS', 'Saldo em minutos do banco de horas')],
    'T_SALDO_BANCO_HORAS': [('#', 'Saldo consolidado do banco de horas do colaborador'),
                            ('MATRICULA', 'Matricula do colaborador'),
                            ('DATAAPURACAO', 'Data de apuracao do saldo do banco de horas')],
    'T_ABONO': [('#', 'Abonos lancados para os colaboradores'), ('MATRICULA', 'Matricula do colaborador'),
               ('CODABONO', 'Codigo do abono lancado')],
    'T_APROVACAO_EXPORTACAO': [('#', 'Aprovacao de exportacao do ponto eletronico'),
                              ('CODAPROVACAO', 'Codigo da aprovacao de exportacao'),
                              ('MATRICULA', 'Matricula do colaborador responsavel pela aprovacao')],
    'T_VISITANTE': [('#', 'Registro de visitantes recebidos na portaria'), ('CODVISITANTE', 'Codigo do visitante'),
                   ('NOMEVISITANTE', 'Nome do visitante'), ('DATAENTRADA', 'Data de entrada do visitante'),
                   ('CODEMPRESA_FK', 'Empresa/unidade onde o visitante foi recebido')],
    'S_CANDIDATO': [('#', 'Candidatos em processo seletivo'), ('CODCANDIDATO', 'Codigo do candidato'),
                   ('NOMECANDIDATO', 'Nome do candidato')],
    'S_HISTORICO_VAGA': [('#', 'Historico de vagas por funcao'), ('CODVAGA', 'Codigo da vaga'),
                        ('CODCARGO', 'Codigo do cargo relacionado a vaga')],
    'S_TREINAMENTO': [('#', 'Plano de treinamento do colaborador'), ('MATRICULA', 'Matricula do colaborador'),
                      ('CODTREINAMENTO', 'Codigo do treinamento')],
    'S_EXAME': [('#', 'Exames periodicos ocupacionais'), ('MATRICULA', 'Matricula do colaborador'),
               ('DATAEXAME', 'Data do exame periodico')],
    'S_ATESTADO': [('#', 'Atestados medicos do colaborador'), ('MATRICULA', 'Matricula do colaborador'),
                  ('DATAATESTADO', 'Data do atestado medico')],
    'S_BENEFICIO_VAGA': [('#', 'Beneficios do processo seletivo'), ('CODCANDIDATO', 'Codigo do candidato'),
                   ('CODBENEFICIO', 'Codigo do beneficio oferecido')],

    # Achado em auditoria (setembro/2026, caso real de um schema de
    # produção): uma tabela de STAGING sem NENHUM lastro estrutural
    # (deliberadamente SEM entrada em _RELACIONAMENTOS_NOMEADOS, então fica
    # com 0 conexões — único sinal estrutural que resta desde que
    # total_registros foi removido por privacidade), mas com colunas ricas
    # o bastante para bater TODOS os termos de um pedido — reproduzindo de
    # propósito o padrão observado no incidente real (nomes de tabela e de
    # fornecedor não repetidos aqui — ver AVISO.md).
    # Nenhum caso de CASOS_* anterior conseguia gerar esse cenário (ver
    # auditoria); esta tabela existe só para isso — ver o caso dedicado em
    # CASOS_CALIBRACAO que testa F_DESLIGAMENTO/F_MOTIVO_DESLIGAMENTO/
    # F_TIPO_DESLIGAMENTO vencendo ESTA tabela no top-1.
    'F_DESLIGAMENTO_STAGING_TEMP': [
        ('#', 'Staging temporario de desligamento antes de consolidar'),
        ('MATRICULA', 'Matricula do colaborador em processo de desligamento'),
        ('DATADESLIGAMENTO', 'Data prevista de desligamento do colaborador'),
        ('CODMOTIVO', 'Codigo do motivo de desligamento do colaborador'),
        ('DESCRICAOMOTIVO', 'Descricao do motivo de desligamento do colaborador'),
        ('CODTIPO', 'Codigo do tipo de desligamento contratual do colaborador'),
        ('DESCRICAOTIPO', 'Descricao do tipo de desligamento contratual'),
        ('OBSERVACAODESLIGAMENTO', 'Observacao sobre o desligamento do colaborador'),
        ('CODPENDENCIA', 'Pendencia de consolidacao do desligamento em staging'),
    ],
}

_RELACIONAMENTOS_NOMEADOS = [
    ('N_UNIDADE', 'CODEMPRESA', 'N_EMPRESA', 'CODEMPRESA'),
    ('N_USUARIO', 'CODEMPRESA', 'N_EMPRESA', 'CODEMPRESA'),
    ('N_ENDERECO', 'CODEMPRESA', 'N_EMPRESA', 'CODEMPRESA'),
    ('F_FUNCIONARIO', 'CODEMPRESA', 'N_EMPRESA', 'CODEMPRESA'),
    ('F_FUNCIONARIO', 'CODCARGO', 'F_CARGO', 'CODCARGO'),
    ('F_SINDICATO_OPCAO', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('F_SINDICATO_OPCAO', 'CODSINDICATO', 'F_SINDICATO', 'CODSINDICATO'),
    ('F_MOTIVO_DESLIGAMENTO', 'CODTIPO', 'F_TIPO_DESLIGAMENTO', 'CODTIPO'),
    ('F_DESLIGAMENTO', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('F_DESLIGAMENTO', 'CODMOTIVO', 'F_MOTIVO_DESLIGAMENTO', 'CODMOTIVO'),
    ('F_PROVISAO_DECIMO_TERCEIRO', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('F_PROVISAO_FERIAS', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('F_BENEFICIO', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('F_FERIAS', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('F_SALDO_FERIAS', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('F_SALDO_FERIAS_PERIODO', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('F_DADOS_PESSOAIS', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('T_BANCO_HORAS', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('T_SALDO_BANCO_HORAS', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('T_ABONO', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('T_APROVACAO_EXPORTACAO', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('S_HISTORICO_VAGA', 'CODCARGO', 'F_CARGO', 'CODCARGO'),
    ('S_TREINAMENTO', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('S_EXAME', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('S_ATESTADO', 'MATRICULA', 'F_FUNCIONARIO', 'MATRICULA'),
    ('S_BENEFICIO_VAGA', 'CODCANDIDATO', 'S_CANDIDATO', 'CODCANDIDATO'),
    # Adicionada junto com a remoção de total_registros (auditoria de
    # privacidade, setembro/2026): sem o componente de volume de dados, uma
    # tabela sem NENHUMA FK modelada passa a ser tratada como "sem lastro
    # estrutural" (ver PENALIDADE_TABELA_SEM_LASTRO_ESTRUTURAL) mesmo
    # quando é uma tabela real e pequena, não staging vazio — T_VISITANTE
    # ficava sem nenhuma FK na fixture só por omissão, não porque um
    # sistema real modelaria um registro de portaria sem vínculo a
    # empresa/unidade. Corrigido aqui para refletir um schema real.
    ('T_VISITANTE', 'CODEMPRESA_FK', 'N_EMPRESA', 'CODEMPRESA'),
]

_FILLER_TERMOS = [
    'codigo', 'data', 'registro', 'responsavel', 'situacao', 'status',
    'motivo', 'tipo', 'numero', 'valor', 'observacao', 'usuario',
    'ativo', 'historico', 'origem', 'destino', 'referencia', 'sequencia',
    'processo', 'evento', 'periodo', 'quantidade', 'percentual',
]

def _gerar_tabela_filler(seed, nome: str):
    """Gera as colunas (e as FKs correspondentes) de UMA tabela de ruído,
    determinístico por (seed, nome) — usa um `random.Random` PRÓPRIO em vez
    de mexer no estado global do módulo `random`. Isso garante duas coisas:

    1. Adicionar/remover outras tabelas de ruído (mudar `n_por_modulo`, ou
       qualquer outra coisa gerada antes/depois) nunca muda os dados desta
       tabela — cada tabela só depende do próprio nome, não da ordem/
       quantidade de chamadas de `random` que aconteceram antes dela num
       stream compartilhado.
    2. As colunas e as FKs são decididas UMA vez, na mesma chamada — a FK
       opcional pra F_FUNCIONARIO (MATRICULA_FK) só é gerada se a coluna
       MATRICULA_FK também for adicionada às colunas da tabela, então as
       duas nunca ficam dessincronizadas (FK apontando pra coluna que essa
       mesma tabela não tem).
    """
    rng = random.Random(f"{seed}:{nome}")
    pool = list(_FILLER_TERMOS)
    rng.shuffle(pool)
    n_cols = rng.randint(3, 9)
    termos = rng.sample(pool, k=min(n_cols, len(pool)))
    cols = [('#', '')] + [(f"COD{t.upper()}", f"{t.capitalize()} de controle interno") for t in termos]
    cols.append(('CODEMPRESA_FK', 'Empresa proprietaria do registro'))
    rels = [(nome, 'CODEMPRESA_FK', 'N_EMPRESA', 'CODEMPRESA')]

    if rng.random() < 0.35:
        cols.append(('MATRICULA_FK', 'Colaborador responsavel pelo registro'))
        rels.append((nome, 'MATRICULA_FK', 'F_FUNCIONARIO', 'MATRICULA'))

    return cols, rels


def _gerar_filler(seed, n_por_modulo=40):
    """Gera as `n_por_modulo` tabelas de ruído de cada um dos 4 módulos
    (N/T/F/S) — usadas só pra exercitar o motor discriminando a tabela
    certa em meio a muitas parecidas; nenhum caso de teste as tem como
    resposta esperada."""
    tabelas = []
    for letra in ('N', 'T', 'F', 'S'):
        for i in range(n_por_modulo):
            nome = f"{letra}_AUX{i:03d}"
            cols, rels = _gerar_tabela_filler(seed, nome)
            tabelas.append((nome, cols, rels))
    return tabelas


def gerar_fixture_db(caminho: str, n_filler_por_modulo=40, seed=42):
    """Gera o banco de teste fictício ('Sistema Aurora') em `caminho`,
    usando o MESMO schema de 5 tabelas que `importar` produz (via
    `criar_schema`) — a fixture não é um formato especial, é só um
    banco Punk Records populado com dados inventados."""
    conn = sqlite3.connect(caminho)
    criar_schema(conn)
    cur = conn.cursor()

    todas_tabelas = dict(_TABELAS_NOMEADAS)
    rels = list(_RELACIONAMENTOS_NOMEADOS)
    for nome, cols, rels_tabela in _gerar_filler(seed, n_filler_por_modulo):
        todas_tabelas[nome] = cols
        rels.extend(rels_tabela)

    for tabela, cols in todas_tabelas.items():
        for coluna, desc in cols:
            cur.execute("INSERT INTO colunas (tabela, coluna, descricao) VALUES (?,?,?)", (tabela, coluna, desc))
    for r in rels:
        cur.execute(
            "INSERT INTO relacionamentos (tabela_filha, campo_filho, tabela_mae, campo_mae) VALUES (?,?,?,?)", r
        )
    for codigo_sistema, nome_sistema, descricao in _SISTEMAS:
        cur.execute(
            "INSERT INTO sistemas (codigo_sistema, nome_sistema, descricao) VALUES (?,?,?)",
            (codigo_sistema, nome_sistema, descricao)
        )
    for termo, sinonimo in _SINONIMOS:
        cur.execute("INSERT INTO sinonimos (termo, sinonimo) VALUES (?,?)", (termo, sinonimo))

    # métricas/score derivados — `calcular_metricas_e_scores` é a MESMA
    # função usada por `importar_csvs` (não uma cópia), então a fixture
    # nunca pode dessincronizar da fórmula real.
    pares_filha_mae = [(tabela_filha, tabela_mae) for tabela_filha, _cf, tabela_mae, _cm in rels]
    metricas = calcular_metricas_e_scores(set(todas_tabelas.keys()), pares_filha_mae)

    # tem_dados (v1.5): todas as tabelas da fixture são "populadas" por
    # padrão, EXCETO F_DESLIGAMENTO_STAGING_TEMP — que existe
    # especificamente para simular uma tabela de staging vazia (ver
    # comentário em _TABELAS_NOMEADAS). É o único jeito de reproduzir o
    # incidente real (staging vazia vencendo tabela real) na fixture sem
    # reintroduzir contagem de registro nenhuma.
    for tabela, m in metricas.items():
        tem_dados = 0 if tabela == 'F_DESLIGAMENTO_STAGING_TEMP' else 1
        cur.execute(
            """INSERT INTO tabelas
               (tabela, descricao, score_relevancia, ranking,
                tabelas_filhas, tabelas_pais, conexoes_totais, tem_dados)
               VALUES (?,NULL,?,?,?,?,?,?)""",
            (tabela, m['score_relevancia'], m['ranking'],
             m['tabelas_filhas'], m['tabelas_pais'], m['conexoes_totais'], tem_dados)
        )

    _estrutura_ficticia(cur)
    conn.commit()
    conn.close()


def _tipo_ficticio(coluna):
    """Tipo inventado, por regra fixa sobre o nome (fase 2 da v3)."""
    if coluna.startswith(('COD', 'MATRICULA')) or coluna.endswith('_FK'):
        return ('int', 4, 10, 0)
    if coluna.startswith(('DATA', 'DT')):
        return ('datetime', 8, 23, 3)
    if coluna.startswith(('VALOR', 'VLR', 'SALARIO')):
        return ('decimal', 9, 15, 2)
    if coluna in ('CPF', 'CNPJ'):
        return ('char', 14, 0, 0)
    return ('varchar', 100, 0, 0)


def _estrutura_ficticia(cur):
    """Fase 2 da v3: tipo, nulo, ordem e PK de cada coluna e nome de
    constraint de cada FK, inventados por regra fixa (sem sorteio) sobre as
    linhas que já existem. Nenhuma linha nova: as métricas e o ranking da
    fixture não mudam. A coluna '#' é a descrição da tabela e fica sem
    estrutura; a primeira coluna real é a PK."""
    por_tabela = {}
    for rowid, tabela, coluna in cur.execute('SELECT rowid, tabela, coluna FROM colunas ORDER BY rowid').fetchall():
        if coluna == '#':
            continue
        ordem = len(por_tabela.setdefault(tabela, [])) + 1
        por_tabela[tabela].append(coluna)
        pk = 1 if ordem == 1 else None
        tipo, tamanho, precisao, escala = _tipo_ficticio(coluna)
        cur.execute('UPDATE colunas SET tipo = ?, tamanho = ?, precisao = ?, escala = ?, nulo = ?, ordem = ?, '
                    'pk_ordem = ? WHERE rowid = ?',
                    (tipo, tamanho, precisao, escala, 0 if pk else 1, ordem, pk, rowid))
    for rowid, filha, campo, mae in cur.execute(
            'SELECT rowid, tabela_filha, campo_filho, tabela_mae FROM relacionamentos ORDER BY rowid').fetchall():
        cur.execute('UPDATE relacionamentos SET constraint_nome = ?, ordem = 1 WHERE rowid = ?',
                    (f'FK_{filha}_{mae}_{campo}', rowid))
