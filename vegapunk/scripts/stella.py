#!/usr/bin/env python3
"""
================================================================================
 STELLA — suíte de regressão do Nomi Nomi no Mi (motor de descoberta de schema)
================================================================================
Nome de referência: Stella é a personalidade original do Vegapunk — a que dá
a palavra final sobre as demais. Aqui, é a suíte que confirma se o motor
ainda se comporta como o esperado depois de qualquer mudança (import de
dados novo ou alteração de estrutura/fórmula), antes de você aceitar essa
mudança.

Conjunto de pedidos em PT-BR, rotulados manualmente com a(s) tabela(s)
que DEVEM aparecer entre as top-N tabelas críticas retornadas por
`NomiNomiNoMi.buscar()`.

Por padrão, este arquivo GERA SOZINHO um banco de teste temporário e
100% FICTÍCIO ("Sistema Aurora") com as 5 tabelas (tabelas / colunas /
relacionamentos / sistemas / sinonimos) — o mesmo schema usado por
`importar` — e roda os casos contra ele. Assim a suite continua
autocontida mesmo com o `punk_records.db` publicado no repositório
vindo vazio (ver contextos/README.md). O banco temporário é apagado ao
final da execução; nada é escrito em `contextos/`.

Objetivo: qualquer mudança futura na fórmula de score, no matching de
termos ou nos sinônimos deve rodar este arquivo antes de ser aceita.
Se um caso que hoje passa passar a falhar, é sinal de regressão.

Uso:
    python3 stella.py                          # usa a fixture fictícia embutida
    python3 stella.py --db /caminho/schema.db   # usa um banco já importado (seu schema real)
    python3 stella.py -v                        # mostra o ranking completo de cada caso

Critério de sucesso por caso: a tabela esperada aparece entre as
top-N tabelas críticas (N = 'top', default 3). Usar top-N (não só
top-1) porque, para várias consultas, mais de uma tabela é uma
resposta legítima (ex.: "férias" pode retornar F_FERIAS ou
F_SALDO_FERIAS) — o que importa é que a tabela certa não fique enterrada
no meio de 30 resultados.

--------------------------------------------------------------------------------
QUATRO GRUPOS
--------------------------------------------------------------------------------
- INTEGRIDADE: não é sobre score/ranking — é um smoke test do caminho
  importar (CSV) -> detalhar/buscar -> JSON, que os três grupos abaixo
  NÃO cobrem (eles só chamam `engine.buscar()` em memória contra uma
  fixture que já nasce pronta). Roda um round-trip real e pequeno de CSV,
  com uma FK propositalmente errada, e confirma que a validação de
  integridade referencial do `importar` continua pegando o problema, que
  `detalhar()` devolve o que devia, e que tudo isso é serializável em
  JSON (o que a flag `--json` da CLI depende). Ver `_rodar_integridade`.

Os três grupos abaixo SÃO sobre score/ranking, por papel metodológico —
não misturar ao calibrar:
- CASOS_CALIBRACAO: usados para ajustar pesos/constantes da fórmula
  (PESOS_POR_MODULO, ESCALA_CONCEITOS, ALPHA_TERMOS_EXTRA). Passar aqui
  não é evidência forte de que o motor generaliza — é o mínimo esperado,
  já que a fórmula foi ajustada especificamente para acertá-los.
- CASOS_HELDOUT: tabelas nunca usadas na calibração original, mas
  cobrindo os mesmos tipos de caso-limite (tabela hub, tabela órfã,
  termo genérico, ordinal por extenso). Meça generalização com essa
  ressalva.
- CASOS_VALIDACAO_CEGA: criados por último, sem serem usados para
  ajustar peso nenhum. É o número mais confiável de "o motor
  generaliza ou só decorou os exemplos".

Se, no futuro, algum caso de HELDOUT ou VALIDACAO_CEGA for usado para
calibrar algo, ele perde a validade como medida de generalização — mova-o
para CASOS_CALIBRACAO e crie um lote novo.

Se você já importou seu próprio schema (ver contextos/README.md) e
quer um sinal de qualidade real (não fictício), escreva seus próprios
casos neste mesmo formato, com os nomes de tabela do SEU schema, e
rode com `--db` apontando para o seu banco importado.
================================================================================
"""

import argparse
import json
import os
import random
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nomi_nomi_no_mi import (  # noqa: E402
    NomiNomiNoMi, DEFAULT_DB_PATH, criar_schema,
    calcular_metricas_e_scores, importar_csvs,
)


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
                   ('NOMEVISITANTE', 'Nome do visitante'), ('DATAENTRADA', 'Data de entrada do visitante')],
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
]

_FILLER_TERMOS = [
    'codigo', 'data', 'registro', 'responsavel', 'situacao', 'status',
    'motivo', 'tipo', 'numero', 'valor', 'observacao', 'usuario',
    'ativo', 'historico', 'origem', 'destino', 'referencia', 'sequencia',
    'processo', 'evento', 'periodo', 'quantidade', 'percentual',
]

_REGISTROS_ESPECIAIS = {
    'N_EMPRESA': 40, 'F_FUNCIONARIO': 18500, 'T_HORARIO': 12,
    'N_ENDERECO': 900, 'F_PROVISAO_DECIMO_TERCEIRO': 1500,
}


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
    banco Punk Records populado com dados inventados.

    `total_registros` de cada tabela também é derivado de um
    `random.Random` próprio por tabela (seed + nome), pelo mesmo motivo
    do `_gerar_tabela_filler`: nenhuma tabela deve mudar de valor por
    causa de uma mudança em outra."""
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

    # total_registros plausível por tabela + métricas/score derivados —
    # `calcular_metricas_e_scores` é a MESMA função usada por `importar_csvs`
    # (não uma cópia), então a fixture nunca pode dessincronizar da fórmula real.
    tabelas_registros = {}
    for tabela in todas_tabelas:
        if tabela in _REGISTROS_ESPECIAIS:
            tabelas_registros[tabela] = _REGISTROS_ESPECIAIS[tabela]
        else:
            rng_registros = random.Random(f"{seed}:{tabela}:registros")
            if tabela in _TABELAS_NOMEADAS:
                tabelas_registros[tabela] = rng_registros.randint(50, 5000)
            else:
                tabelas_registros[tabela] = rng_registros.randint(0, 2000)

    pares_filha_mae = [(tabela_filha, tabela_mae) for tabela_filha, _cf, tabela_mae, _cm in rels]
    metricas = calcular_metricas_e_scores(tabelas_registros, pares_filha_mae)

    for tabela, m in metricas.items():
        cur.execute(
            """INSERT INTO tabelas
               (tabela, descricao, score_relevancia, ranking, total_registros,
                tabelas_filhas, tabelas_pais, conexoes_totais)
               VALUES (?,NULL,?,?,?,?,?,?)""",
            (tabela, m['score_relevancia'], m['ranking'], m['total_registros'],
             m['tabelas_filhas'], m['tabelas_pais'], m['conexoes_totais'])
        )

    conn.commit()
    conn.close()


# ==============================================================================
# CASOS DE TESTE
# ==============================================================================
# Cada caso: (pedido em PT-BR, {tabelas aceitas como resposta correta}, top-N, comentário)
CASOS_CALIBRACAO = [
    ("preciso da data de admissao dos colaboradores", {"F_FUNCIONARIO"}, 3,
     "Testa que uma tabela hub muito conectada (N_EMPRESA) não vence por conexões sozinha."),
    ("quero saber o salario dos colaboradores", {"F_FUNCIONARIO"}, 3,
     "Testa sinônimo 'salario'->'remuneracao'."),
    ("matricula do colaborador", {"F_FUNCIONARIO"}, 3,
     "Termo 'matricula' aparece em várias tabelas (FK comum); teste de discriminação."),
    ("ferias dos colaboradores", {"F_FERIAS", "F_SALDO_FERIAS", "F_SALDO_FERIAS_PERIODO", "F_PROVISAO_FERIAS"}, 5,
     "Múltiplas tabelas legítimas de férias no dataset de exemplo."),
    ("dados do desligamento de contrato", {"F_DESLIGAMENTO"}, 3,
     "Testa o termo 'desligamento' direto (sem precisar de sinônimo aqui)."),
    ("quero ver a demissao do colaborador", {"F_DESLIGAMENTO", "F_MOTIVO_DESLIGAMENTO", "F_TIPO_DESLIGAMENTO"}, 5,
     "Testa sinônimo 'demissao'->'desligamento'."),
    ("cargo do colaborador", {"F_CARGO"}, 3, "Termo curto e comum ('cargo'); teste de precisão."),
    ("empresas cadastradas no sistema", {"N_EMPRESA"}, 3,
     "N_EMPRESA é a tabela hub mais conectada do dataset — aqui ELA é a resposta certa, então o "
     "teste confirma que o fix do log() não 'proibiu' hubs de vencer, só parou de deixá-los "
     "vencer por padrão."),
    ("unidades da empresa", {"N_UNIDADE"}, 3, "Testa termo 'unidade' não sendo ofuscado por N_EMPRESA (o hub)."),
    ("usuarios com acesso ao sistema", {"N_USUARIO"}, 3, "Módulo N (Núcleo), tabela de usuários."),
    ("abono lancado para o colaborador", {"T_ABONO"}, 5, "Módulo T (Turno), termo composto."),
    ("visitante registrado na portaria", {"T_VISITANTE"}, 5,
     "'portaria' é ambíguo em PT-BR (recepção vs. decreto administrativo) — caso-limite de "
     "ambiguidade léxica, não sempre no top."),
]

CASOS_HELDOUT = [
    ("beneficios do colaborador", {"F_BENEFICIO", "S_BENEFICIO_VAGA"}, 3, "Módulo F/S — mais de uma tabela legítima."),
    ("horario de trabalho cadastrado", {"T_HORARIO"}, 5, "Tabela pequena/quase órfã do módulo T."),
    ("banco de horas do colaborador", {"T_BANCO_HORAS", "T_SALDO_BANCO_HORAS"}, 5, "Módulo T, tabela nova."),
    ("endereco cadastrado no sistema", {"N_ENDERECO"}, 3,
     "Caso-limite: 'sistema'/'cadastrado' são termos genéricos que tendem a puxar tabelas maiores."),
    ("plano de treinamento do colaborador", {"S_TREINAMENTO"}, 5, "Módulo S, tabela nova."),
    ("atestado medico do colaborador", {"S_ATESTADO"}, 5, "Módulo S, tabela nova."),
    ("decimo terceiro salario", {"F_PROVISAO_DECIMO_TERCEIRO"}, 5,
     "Testa normalização de ordinal por extenso ('décimo terceiro' -> '13'); tabela quase órfã."),
    ("atraso do colaborador no banco de horas", {"T_BANCO_HORAS", "T_SALDO_BANCO_HORAS"}, 5,
     "Multi-conceito: 'atraso' + 'banco de horas' + 'colaborador'."),
    ("matricula e cpf do colaborador", {"F_FUNCIONARIO"}, 3, "Caso fácil de controle."),
    ("xpto123 inexistente blablabla", set(), 0, "Pedido sem sentido — deve devolver vazio, não lixo forçado."),
]

CASOS_VALIDACAO_CEGA = [
    ("motivo do desligamento do colaborador", {"F_MOTIVO_DESLIGAMENTO"}, 5, "Tabela nunca usada antes."),
    ("convenio medico da empresa", {"F_CONVENIO"}, 5, "Módulo F, tabela nova."),
    ("exames periodicos do colaborador", {"S_EXAME"}, 5, "Módulo S, tabela nova."),
    ("sindicato do colaborador", {"F_SINDICATO_OPCAO", "F_SINDICATO"}, 5, "Módulo F."),
    ("candidatos a vaga de emprego", {"S_CANDIDATO"}, 5, "Módulo S, processo seletivo."),
    ("historico de vagas por funcao", {"S_HISTORICO_VAGA"}, 5, "Módulo S, tabela nova."),
    ("data de nascimento do colaborador", {"F_FUNCIONARIO", "F_DADOS_PESSOAIS"}, 3, "Caso fácil de controle."),
    ("motivo de afastamento medico", {"F_DESLIGAMENTO", "S_ATESTADO", "F_MOTIVO_DESLIGAMENTO"}, 5,
     "Query genuinamente ambígua — qualquer uma das três seria defensável."),
]


def _rodar_integridade(verbose: bool) -> bool:
    """Smoke test do caminho importar -> detalhar/buscar -> JSON — os
    grupos de CALIBRAÇÃO/HELD-OUT/VALIDAÇÃO CEGA não cobrem isso, porque
    chamam `engine.buscar()` direto em memória contra uma fixture que já
    nasce pronta, nunca passando pelo parsing de CSV nem pelo `detalhar`.

    Faz um round-trip real e pequeno: escreve 3 CSVs num diretório
    temporário — com uma FK válida e uma FK com um campo_filho digitado
    errado de propósito — roda `importar_csvs` de verdade e confirma que:
    1) a validação de integridade referencial (ver
       `validar_integridade_relacionamentos` em nomi_nomi_no_mi.py) pega
       exatamente a FK com o typo, sem travar o import;
    2) `detalhar()` devolve as colunas e as FKs esperadas;
    3) tanto `detalhar()` quanto `buscar()` são serializáveis em JSON
       (o que a flag `--json` da CLI depende)."""
    print("--- INTEGRIDADE (importar / detalhar / --json) ---\n")
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        csv_dir = os.path.join(tmp, 'csvs')
        os.makedirs(csv_dir)
        with open(os.path.join(csv_dir, 'tabelas.csv'), 'w', encoding='utf-8', newline='') as f:
            f.write(
                "tabela,total_registros,descricao\n"
                "X_PAI,10,Tabela pai de teste\n"
                "X_FILHA,20,Tabela filha de teste\n"
            )
        with open(os.path.join(csv_dir, 'colunas.csv'), 'w', encoding='utf-8', newline='') as f:
            f.write(
                "tabela,coluna,descricao\n"
                "X_PAI,CODPAI,Codigo do pai\n"
                "X_FILHA,CODPAI_FK,FK para o pai\n"
                "X_FILHA,CODFILHA,Codigo da filha\n"
            )
        with open(os.path.join(csv_dir, 'relacionamentos.csv'), 'w', encoding='utf-8', newline='') as f:
            f.write(
                "tabela_filha,campo_filho,tabela_mae,campo_mae\n"
                "X_FILHA,CODPAI_FK,X_PAI,CODPAI\n"       # FK válida
                "X_FILHA,CODINEXISTENTE,X_PAI,CODPAI\n"  # FK com typo proposital
            )
        db_path = os.path.join(tmp, 'integridade.db')

        contagens = importar_csvs(csv_dir, db_path, sobrescrever=True)
        avisos = contagens.get('avisos', [])
        if len(avisos) == 1 and 'CODINEXISTENTE' in avisos[0]:
            print("[PASSOU] importar detecta a FK com campo_filho inexistente e avisa (sem travar o import)")
        else:
            ok = False
            print(f"[FALHOU] esperava 1 aviso citando CODINEXISTENTE, obteve: {avisos}")

        engine = NomiNomiNoMi(db_path)
        try:
            det = engine.detalhar(['X_FILHA'])
            colunas_filha = {c['coluna'] for c in det['tabelas']['X_FILHA']['colunas']}
            fks = det['tabelas']['X_FILHA']['relacionamentos']
            if {'CODPAI_FK', 'CODFILHA'} <= colunas_filha and len(fks) == 2:
                print("[PASSOU] detalhar retorna as colunas e as 2 FKs de X_FILHA (inclusive a inválida — "
                      "detalhar não filtra, só expõe; quem decide o que fazer com o aviso é quem chama)")
            else:
                ok = False
                print(f"[FALHOU] detalhar inesperado: colunas={colunas_filha} fks={fks}")

            json.dumps(det, ensure_ascii=False)
            resultado_busca = engine.buscar("codigo da filha", limite_criticas=5)
            json.dumps(resultado_busca, ensure_ascii=False)
            print("[PASSOU] detalhar() e buscar() são serializáveis em JSON (--json não quebra)")
            if verbose:
                print(f"         avisos do import: {avisos}")
        except Exception as e:
            ok = False
            print(f"[FALHOU] erro rodando detalhar/buscar/json: {e!r}")
        finally:
            engine.fechar()

    print(f"\nINTEGRIDADE: {'PASSOU' if ok else 'FALHOU'}\n")
    return ok


def _rodar_grupo(engine, nome_grupo, casos, top_n_override, verbose):
    total = len(casos)
    if total == 0:
        print(f"--- {nome_grupo} (0 casos, grupo vazio — pulando) ---\n")
        return 0, 0, []
    passou = 0
    falhas = []
    print(f"--- {nome_grupo} ({total} casos) ---\n")
    for pedido, esperadas, top_n, comentario in casos:
        n = top_n_override or top_n
        resultado = engine.buscar(pedido, limite_criticas=30)
        tabelas_no_topo = [t['tabela'] for t in resultado['criticas'][:n]] if n else \
            [t['tabela'] for t in resultado['criticas']]

        acertou = (len(resultado['criticas']) == 0) if not esperadas else bool(esperadas & set(tabelas_no_topo))
        status = "PASSOU" if acertou else "FALHOU"
        if acertou:
            passou += 1
        else:
            falhas.append((pedido, esperadas, tabelas_no_topo))

        print(f"[{status}] \"{pedido}\"")
        print(f"         esperado (top-{n}): {sorted(esperadas) or '(vazio)'}")
        print(f"         obtido   (top-{n}): {tabelas_no_topo}")
        if verbose:
            print(f"         módulo inferido: {resultado['modulo']}")
            for t in resultado['criticas'][:n or 5]:
                print(f"           - {t['tabela']:<20} score={t['score_dinamico']}")
        print(f"         nota: {comentario}\n")

    print(f"{nome_grupo}: {passou}/{total} ({passou/total*100:.0f}%)\n")
    return passou, total, falhas


def rodar(db_path: str, top_n_override: int = None, verbose: bool = False) -> bool:
    print(f"Rodando suite de testes contra: {db_path}\n")
    print("=" * 70)
    ok_integridade = _rodar_integridade(verbose)
    print("=" * 70)

    engine = NomiNomiNoMi(db_path)
    p1, t1, f1 = _rodar_grupo(engine, "CALIBRAÇÃO", CASOS_CALIBRACAO, top_n_override, verbose)
    print("=" * 70)
    p2, t2, f2 = _rodar_grupo(engine, "HELD-OUT", CASOS_HELDOUT, top_n_override, verbose)
    print("=" * 70)
    p3, t3, f3 = _rodar_grupo(engine, "VALIDAÇÃO CEGA", CASOS_VALIDACAO_CEGA, top_n_override, verbose)
    print("=" * 70)
    engine.fechar()

    passou_total, total = p1 + p2 + p3, t1 + t2 + t3
    todas_falhas = f1 + f2 + f3

    def _linha(nome, p, t):
        return f"  {nome}: (grupo vazio)" if t == 0 else f"  {nome}: {p}/{t} ({p/t*100:.0f}%)"

    print(f"INTEGRIDADE: {'PASSOU' if ok_integridade else 'FALHOU'}")
    if total:
        print(f"RESULTADO FINAL (grupos de calibração): {passou_total}/{total} ({passou_total/total*100:.0f}%)")
    else:
        print("RESULTADO FINAL (grupos de calibração): nenhum caso definido")
    print(_linha("Calibração", p1, t1))
    print(_linha("Held-out", p2, t2))
    print(_linha("Validação cega", p3, t3) + ("  <- número mais confiável de generalização" if t3 else ""))
    if todas_falhas:
        print("\nCasos que falharam:")
        for pedido, esperadas, obtido in todas_falhas:
            print(f"  - \"{pedido}\" | esperava {sorted(esperadas) or '(vazio)'} | obteve {obtido}")
    print("=" * 70)
    return ok_integridade and passou_total == total


def main():
    parser = argparse.ArgumentParser(description="Stella — suíte de regressão do Nomi Nomi no Mi")
    parser.add_argument(
        '--db', default=None,
        help='Banco já importado a testar (ex: contextos/punk_records.db real). '
             'Se omitido, gera e usa uma fixture fictícia temporária.'
    )
    parser.add_argument('--top', type=int, default=None, help='Sobrescreve o top-N de todos os casos')
    parser.add_argument('-v', '--verbose', action='store_true', help='Mostra ranking completo por caso')
    args = parser.parse_args()

    if args.db:
        if not os.path.exists(args.db):
            print(f"ERRO: banco não encontrado em {args.db}", file=sys.stderr)
            sys.exit(1)
        ok = rodar(args.db, top_n_override=args.top, verbose=args.verbose)
        sys.exit(0 if ok else 1)

    with tempfile.TemporaryDirectory() as tmp:
        db_fixture = os.path.join(tmp, 'fixture_aurora.db')
        gerar_fixture_db(db_fixture)
        ok = rodar(db_fixture, top_n_override=args.top, verbose=args.verbose)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
