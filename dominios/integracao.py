"""
Ponte entre os domínios (PLANO-V3.md, "Integração entre domínios: acrescenta,
não obriga"). Cada domínio funciona sozinho; quando os dois estão presentes,
esta ponte junta o que cada um sabe, sem que um importe o outro.

Hoje (fase 3): o `detalhar` de função ganha, por parâmetro de código, a
ligação com o cadastro do mapa e o SQL de apoio. A descoberta escreve o SQL
(`nomi_nomi_no_mi/apoio.py`); o Shaka valida os nomes de tabela e coluna
(`dominios/formulas/sql_apoio.py`). Sem a base de schema ou sem a camada
Mapa, `enriquecedor_de_detalhe` devolve None e o `detalhar` sai como antes.
"""


def enriquecedor_de_detalhe(db_path):
    """Função que acrescenta `ligacoes_parametros` às fichas do `detalhar`,
    ou None quando não há mapa compilado na base."""
    try:
        from nomi_nomi_no_mi.apoio import carregar_mapa, ligacoes
        from dominios.formulas.sql_apoio import validar_sql_de_apoio
    except ImportError:          # um dos domínios não está instalado: modo básico
        return None
    mapa = carregar_mapa(db_path)
    if not mapa:
        return None

    def enriquecer(fichas):
        for f in fichas:
            if f.get('encontrada') is False:
                continue
            itens = ligacoes(mapa, f)
            for it in itens:
                if it.get('sql_apoio'):
                    erros = validar_sql_de_apoio(it['sql_apoio'], mapa['nomes'])
                    it['sql_apoio_validado'] = not erros
                    if erros:                      # nunca entrega SQL com nome inventado
                        it['erros_sql_apoio'] = erros
                        it.pop('sql_apoio')
            if itens:
                f['ligacoes_parametros'] = itens
        return fichas
    return enriquecer
