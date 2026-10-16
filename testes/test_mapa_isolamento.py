"""Fase 3a: o mapa de um sistema real é da instância. Na superfície
distribuível só entra mapa fictício (checagem 9 do isolamento), e a
distribuição sai numa pasta separada, sem .git e sem nada fora da allowlist.
Tudo com nomes fictícios; o "mapa real" plantado usa um nome inventado."""

import json
import os
import shutil
import sqlite3
import tempfile
import unittest

from _comum import _gravar_json, FIXTURE_FORMULAS, SKILL
from casos.fixture_schema import gerar_fixture_db
from dominios.distribuicao import DistribuicaoRecusada, conferir_distribuicao, distribuir, lista_distribuivel
from dominios.isolamento import verificar_isolamento, verificar_mapas

TABELA_INVENTADA = 'QZREALTABELAXPTO'


def _plantar(caminho, obj):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    _gravar_json(caminho, obj)


def _checagem_mapa(r):
    return [c for c in r['verificacoes'] if 'mapa real' in c['verificacao']][0]


class TestTabelasFicticias(unittest.TestCase):
    def test_lista_versionada_bate_com_a_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, 'f.db')
            gerar_fixture_db(db)
            c = sqlite3.connect(db)
            tabs = sorted(r[0] for r in c.execute('SELECT tabela FROM tabelas'))
            c.close()
        with open(os.path.join(SKILL, 'casos', 'tabelas_ficticias.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['tabelas'], tabs)


class TestMapaNaSuperficie(unittest.TestCase):
    def _copia(self, tmp):
        raiz = os.path.join(tmp, 'pacotes')
        shutil.copytree(FIXTURE_FORMULAS, raiz)
        return raiz

    def test_superficie_atual_nao_tem_mapa_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = verificar_isolamento(SKILL, self._copia(tmp))
            self.assertTrue(_checagem_mapa(r)['ok'], _checagem_mapa(r))

    def test_mapa_real_plantado_no_pacote_publico_e_recusado(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            _plantar(os.path.join(raiz, 'publico', 'ficticio', 'mapa', 'mapa.json'),
                         {'versao': 1, 'cadastros': [{'cadastro': 'x', 'tabela': TABELA_INVENTADA}]})
            r = verificar_isolamento(SKILL, raiz)
            self.assertFalse(r['ok'])
            ch = _checagem_mapa(r)
            self.assertFalse(ch['ok'])
            self.assertIn('ficticio', ch['detalhe'])
            self.assertNotIn(TABELA_INVENTADA, json.dumps(r, ensure_ascii=False))

    def test_mapa_que_se_diz_ficticio_mas_cita_tabela_real_e_recusado(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            _plantar(os.path.join(raiz, 'publico', 'ficticio', 'mapa', 'mapa.json'),
                         {'versao': 1, 'ficticio': True,
                          'cadastros': [{'tabela': 'F_CARGO'}, {'tabela': TABELA_INVENTADA}]})
            ch = _checagem_mapa(verificar_isolamento(SKILL, raiz))
            self.assertFalse(ch['ok'])
            self.assertIn('1 tabela(s) fora do schema fictício', ch['detalhe'])
            self.assertNotIn(TABELA_INVENTADA, ch['detalhe'])

    def test_mapa_ficticio_da_fixture_passa(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = self._copia(tmp)
            _plantar(os.path.join(raiz, 'publico', 'ficticio', 'mapa', 'mapa.json'),
                         {'versao': 1, 'ficticio': True, 'cadastros': [{'tabela': 'F_CARGO'}]})
            ch = _checagem_mapa(verificar_isolamento(SKILL, raiz))
            self.assertTrue(ch['ok'], ch)
            self.assertIn('mapa(s) na superfície', ch['detalhe'])

    def test_mapa_reconhecido_pelo_contrato_em_qualquer_nome(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = os.path.join(tmp, 'skill')
            os.makedirs(os.path.join(skill, 'casos'))
            shutil.copy2(os.path.join(SKILL, 'casos', 'tabelas_ficticias.json'), os.path.join(skill, 'casos'))
            outro = os.path.join(skill, 'casos', 'qualquer_nome.json')
            _plantar(outro, {'consultas': {'tabela': TABELA_INVENTADA}})
            problemas, n = verificar_mapas([outro], skill)
            self.assertEqual(n, 1)
            self.assertEqual(len(problemas), 1)


class TestDistribuicao(unittest.TestCase):
    def test_gera_so_a_allowlist_sem_git_nem_instancia(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = os.path.join(tmp, 'vegapunk')
            r = distribuir(SKILL, destino, verificar=False)
            permitidos = lista_distribuivel(SKILL)
            self.assertEqual(r['arquivos'], len(permitidos))
            self.assertEqual(conferir_distribuicao(destino, permitidos), [])
            self.assertTrue(os.path.exists(os.path.join(destino, 'SKILL.md')))
            fixtures = os.path.join('casos', 'fixtures') + os.sep
            for d, subdirs, arqs in os.walk(destino):
                self.assertNotIn('.git', subdirs + arqs)
                rel = os.path.relpath(d, destino)
                # de uma pasta privado só sai a proteção e a explicação (fora
                # as fixtures fictícias, que saem inteiras)
                if os.path.basename(rel) == 'privado' and not rel.startswith(fixtures):
                    self.assertEqual(subdirs, [])
                    self.assertLessEqual(set(arqs), {'.gitignore', 'README.md'})
                for a in arqs:
                    self.assertFalse(a.endswith(('.db', '.jsonl', '.csv')), a)
            self.assertTrue(os.path.exists(os.path.join(destino, 'casos', 'fixtures', 'formulas', 'publico',
                                                        'ficticio', 'funcoes.json')))
            self.assertTrue(os.path.exists(os.path.join(destino, 'punk_records', 'pacotes', 'privado', '.gitignore')))
            for nome in ('LICENSE', '.gitignore', '.gitattributes'):
                self.assertTrue(os.path.exists(os.path.join(destino, nome)), nome)
            publico = os.path.join(destino, 'punk_records', 'pacotes', 'publico')
            for p in (os.listdir(publico) if os.path.isdir(publico) else []):
                self.assertFalse(os.path.exists(os.path.join(publico, p, 'funcoes.json')), p)

    def test_nada_da_pasta_da_instancia_e_distribuivel(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = os.path.join(tmp, 'skill')
            os.makedirs(os.path.join(skill, 'egghead'))
            for nome in ('ESTADO.md', 'notas.md', 'linha.json'):
                with open(os.path.join(skill, 'egghead', nome), 'w', encoding='utf-8') as f:
                    f.write('memória da instância\n')
            with open(os.path.join(skill, 'SKILL.md'), 'w', encoding='utf-8') as f:
                f.write('Especificação.\n')
            self.assertEqual(lista_distribuivel(skill, os.path.join(tmp, 'pacotes')), ['SKILL.md'])

    def test_falha_e_apaga_a_pasta_se_aparecer_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = os.path.join(tmp, 'vegapunk')
            with self.assertRaises(DistribuicaoRecusada) as ctx:
                distribuir(SKILL, destino, verificar=False,
                           _antes_de_conferir=lambda d: os.makedirs(os.path.join(d, 'casos', '.git')))
            self.assertIn('.git', str(ctx.exception))
            self.assertFalse(os.path.exists(destino))

    def test_falha_se_aparecer_arquivo_fora_da_allowlist(self):
        def plantar(d):
            with open(os.path.join(d, 'extra.txt'), 'w', encoding='utf-8') as f:
                f.write('fora da allowlist\n')
        with tempfile.TemporaryDirectory() as tmp:
            destino = os.path.join(tmp, 'vegapunk')
            with self.assertRaises(DistribuicaoRecusada) as ctx:
                distribuir(SKILL, destino, verificar=False, _antes_de_conferir=plantar)
            self.assertIn('extra.txt: fora da allowlist', str(ctx.exception))
            self.assertFalse(os.path.exists(destino))

    def test_recusa_destino_dentro_do_repositorio_ou_nao_vazio(self):
        with self.assertRaises(DistribuicaoRecusada):
            distribuir(SKILL, os.path.join(SKILL, 'saida_proibida'), verificar=False)
        self.assertFalse(os.path.exists(os.path.join(SKILL, 'saida_proibida')))
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, 'ja_tem.txt'), 'w', encoding='utf-8') as f:
                f.write('x')
            with self.assertRaises(DistribuicaoRecusada):
                distribuir(SKILL, tmp, verificar=False)
            self.assertTrue(os.path.exists(os.path.join(tmp, 'ja_tem.txt')))


if __name__ == '__main__':
    unittest.main()
