"""A cópia do banco tem de sair válida mesmo com o serviço escrevendo."""

import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deploy.backup import apagar_antigos, copiar


def _banco_com_linhas(caminho: Path, quantas: int) -> None:
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE t (n INTEGER)")
    con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(quantas)])
    con.commit()
    con.close()


def test_a_copia_tem_todas_as_linhas():
    pasta = Path(tempfile.mkdtemp(prefix="pdftodxf-teste-"))
    origem = pasta / "contas.db"
    _banco_com_linhas(origem, 100)

    destino = copiar(origem, pasta / "copia.db")

    con = sqlite3.connect(destino)
    assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 100
    con.close()
    print("OK: a cópia tem todas as linhas")


def test_a_copia_sai_valida_com_escrita_em_curso():
    """É o caso que o `cp` erra, e o erro só aparece no dia da restauração."""
    pasta = Path(tempfile.mkdtemp(prefix="pdftodxf-teste-"))
    origem = pasta / "contas.db"
    _banco_com_linhas(origem, 10)

    escritor = sqlite3.connect(origem)
    escritor.execute("BEGIN")
    escritor.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(1000)])
    # Transação **aberta** de propósito: é o estado em que copiar o arquivo
    # com `cp` produziria um banco quebrado.
    try:
        destino = copiar(origem, pasta / "copia.db")
    finally:
        escritor.rollback()
        escritor.close()

    con = sqlite3.connect(destino)
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    # A cópia vê o banco confirmado, não o que a transação aberta ainda não
    # gravou: 10, e não 1010.
    assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 10
    con.close()
    print("OK: a cópia sai íntegra com escrita em curso")


def test_a_retencao_apaga_o_velho_e_mantem_o_novo():
    pasta = Path(tempfile.mkdtemp(prefix="pdftodxf-teste-"))
    agora = time.time()
    velho = pasta / "contas-2020-01-01.db"
    novo = pasta / "contas-2030-01-01.db"
    velho.write_bytes(b"x")
    novo.write_bytes(b"x")
    os.utime(velho, (agora - 40 * 86400, agora - 40 * 86400))
    os.utime(novo, (agora, agora))

    apagados = apagar_antigos(pasta, dias=30, agora=agora)

    assert velho in apagados and not velho.exists()
    assert novo.exists()
    print("OK: a retenção apaga o velho e mantém o novo")


if __name__ == "__main__":
    test_a_copia_tem_todas_as_linhas()
    test_a_copia_sai_valida_com_escrita_em_curso()
    test_a_retencao_apaga_o_velho_e_mantem_o_novo()
    print("Todos os testes do backup passaram.")
