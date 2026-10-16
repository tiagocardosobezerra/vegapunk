"""
Cada domínio roda sem o outro (PLANO-V3.md, "Integração entre domínios:
acrescenta, não obriga").

Verificação DINÂMICA: roda os testes e os comandos de um domínio num
processo em que os módulos do outro domínio estão bloqueados no import, e
em que os dados do outro domínio não existem:

- fórmulas sem schema: módulos do schema bloqueados e `VEGAPUNK_EGGHEAD`
  apontando para uma pasta vazia (sem base, sem log, sem golden real);
- schema sem fórmulas: módulos de fórmulas bloqueados e `VEGAPUNK_PACOTES`
  apontando para uma pasta vazia (nenhum pacote de conhecimento).

O bloqueio vale também para os subprocessos que os testes abrem (a Stella,
por exemplo): ele é instalado por um `sitecustomize.py` temporário no
PYTHONPATH, que todo processo Python novo carrega ao iniciar.

Só biblioteca padrão; não importa nenhum dos dois domínios.
"""

import os
import shutil
import subprocess
import sys
import tempfile

# O núcleo de texto comum (nomi_nomi_no_mi.texto_comum) não é do domínio schema: os
# dois domínios o usam. Todo o resto do pacote nomi_nomi_no_mi é schema.
MODULOS_SCHEMA = tuple(f'nomi_nomi_no_mi.{m}' for m in (
    'busca', 'indice', 'grafo', 'texto', 'saida', 'manutencao', 'historico', 'comandos')) + (
    'dominios.schema', 'punk_records.schema', 'punk_records.sinonimos', 'punk_records.migracoes',
    'casos.fixture_schema')
MODULOS_FORMULAS = ('dominios.formulas', 'dominios.isolamento', 'shaka', 'punk_records.ingestao')

_SITECUSTOMIZE = '''
import importlib.abc
import os
import sys

_BLOQUEADOS = tuple(m for m in os.environ.get('VEGAPUNK_SEM_MODULOS', '').split(',') if m)


class _DominioAusente(importlib.abc.MetaPathFinder):
    def find_spec(self, nome, caminho=None, alvo=None):
        if any(nome == b or nome.startswith(b + '.') for b in _BLOQUEADOS):
            raise ModuleNotFoundError(f'{nome}: domínio ausente (verificação de isolamento)', name=nome)
        return None


if _BLOQUEADOS:
    sys.meta_path.insert(0, _DominioAusente())
'''


def _rodar(raiz_skill, comando, env):
    r = subprocess.run([sys.executable] + comando, cwd=raiz_skill, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env)
    return r.returncode, r.stdout + r.stderr


def _cenario(raiz_skill, bloqueados, env_extra, comandos):
    """Roda `comandos` [(rótulo, argv, códigos aceitos)] com `bloqueados`."""
    tmp = tempfile.mkdtemp(prefix='vegapunk_separacao_')
    try:
        with open(os.path.join(tmp, 'sitecustomize.py'), 'w', encoding='utf-8') as f:
            f.write(_SITECUSTOMIZE)
        vazio = os.path.join(tmp, 'vazio')
        os.makedirs(vazio)
        env = dict(os.environ, PYTHONIOENCODING='utf-8', VEGAPUNK_SEM_MODULOS=','.join(bloqueados),
                   VEGAPUNK_SHAKA_LOG=os.path.join(tmp, 'shaka_log.jsonl'))
        env['PYTHONPATH'] = tmp + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        env.update({k: (vazio if v == '<vazio>' else v) for k, v in env_extra.items()})
        falhas, ok = [], []
        for rotulo, argv, aceitos in comandos:
            codigo, saida = _rodar(raiz_skill, argv, env)
            if codigo not in aceitos or 'domínio ausente (verificação de isolamento)' in saida:
                ultima = [l for l in saida.strip().splitlines() if l.strip()][-1:] or ['(sem saída)']
                falhas.append(f'{rotulo} (código {codigo}: {ultima[0][:160]})')
            else:
                ok.append(rotulo)
        return ok, falhas
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def verificar_dominios_separados(raiz_skill):
    """Devolve [{verificacao, ok, detalhe}], no formato do verificar-isolamento."""
    raiz_skill = os.path.abspath(raiz_skill)
    formulas = [
        ('testes de fórmulas', ['-m', 'unittest', 'discover', '-s', 'testes', '-p', 'test_formulas_*.py'], (0,)),
        ('testes dos pacotes públicos', ['-m', 'unittest', 'discover', '-s', 'testes', '-p', 'test_pacotes_publicos.py'], (0,)),
        ('avaliação de fórmulas', ['satelites/pythagoras.py', 'avaliar', '--dominio', 'formulas'], (0,)),
        ('Atlas de fórmulas', ['satelites/atlas.py', 'verificar', '--dominio', 'formulas'], (0,)),
        ('stella buscar', ['stella.py', 'buscar', '--dominio', 'formulas', 'arredondar valor'], (0, 1)),
        ('stella status', ['stella.py', 'status'], (0,)),
    ]
    schema = [
        ('testes de migração', ['-m', 'unittest', 'discover', '-s', 'testes', '-p', 'test_migracoes.py'], (0,)),
        ('avaliação do schema', ['satelites/pythagoras.py', 'avaliar', '--dominio', 'schema'], (0,)),
        ('Atlas do schema (inclui a Stella pela linha de comando)',
         ['satelites/atlas.py', 'verificar', '--dominio', 'schema'], (0,)),
        ('stella status', ['stella.py', 'status'], (0,)),
    ]
    resultado = []
    for nome, bloqueados, env_extra, comandos in (
            ('domínio de fórmulas roda sem o domínio schema', MODULOS_SCHEMA, {'VEGAPUNK_EGGHEAD': '<vazio>'}, formulas),
            ('domínio schema roda sem o domínio de fórmulas', MODULOS_FORMULAS, {'VEGAPUNK_PACOTES': '<vazio>'}, schema)):
        ok, falhas = _cenario(raiz_skill, bloqueados, env_extra, comandos)
        resultado.append({'verificacao': nome, 'ok': not falhas,
                          'detalhe': f'{len(ok)}/{len(comandos)} execuções OK'
                                     + ('; FALHARAM: ' + '; '.join(falhas) if falhas else '')})
    return resultado
