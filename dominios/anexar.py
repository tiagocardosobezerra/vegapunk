"""
Acrescentar uma linha a um arquivo de log (JSONL) com trava entre processos.

Abrir em modo de acréscimo não basta: no Windows, dois processos que gravam
ao mesmo tempo podem escrever no mesmo ponto do arquivo, e uma linha some.
Medido: 6 confirmações em paralelo, 5 linhas no log. A trava é um byte no
início do próprio arquivo (sem arquivo auxiliar); quem chega depois espera.
Só biblioteca padrão; serve aos dois domínios.
"""

import os

try:                                    # Windows
    import msvcrt

    def _travar(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)       # tenta por até ~10 s

    def _destravar(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
except ImportError:                     # POSIX
    import fcntl

    def _travar(fd):
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _destravar(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)


def anexar_linha(caminho, linha):
    """Grava `linha` (com o fim de linha) no fim de `caminho`, sob trava.
    OSError sobe para quem chamou decidir (o log de uso é best-effort)."""
    dados = (linha if linha.endswith('\n') else linha + '\n').encode('utf-8')
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_BINARY', 0), 0o644)
    try:
        _travar(fd)
        try:
            os.lseek(fd, 0, os.SEEK_END)
            os.write(fd, dados)
        finally:
            _destravar(fd)
    finally:
        os.close(fd)
