"""O banco: esquema, conexão por thread, segredo e limpeza."""

import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from web.api import db


def test_as_tabelas_nascem_na_primeira_conexao():
    con = db.conexao()
    nomes = {linha["name"] for linha in
             con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"usuarios", "tokens", "consumo"} <= nomes, nomes
    modo = con.execute("PRAGMA journal_mode").fetchone()[0]
    assert modo.lower() == "wal", modo
    print("OK: as três tabelas nascem na primeira conexão, com WAL")


def test_email_e_unico():
    import sqlite3
    con = db.conexao()
    con.execute("INSERT INTO usuarios (email, senha, criado_em, criado_de) "
                "VALUES (?, ?, ?, ?)", ("a@b.c", "x", time.time(), "ip"))
    con.commit()
    try:
        con.execute("INSERT INTO usuarios (email, senha, criado_em, criado_de) "
                    "VALUES (?, ?, ?, ?)", ("a@b.c", "y", time.time(), "ip"))
        con.commit()
        raise AssertionError("o e-mail repetido tinha que ser recusado")
    except sqlite3.IntegrityError:
        con.rollback()
    print("OK: o e-mail é único")


def test_uma_conexao_por_thread():
    """Sem `check_same_thread=False`: cada fio abre a sua."""
    daqui = db.conexao()
    de_la = []
    fio = threading.Thread(target=lambda: de_la.append(db.conexao()))
    fio.start()
    fio.join()
    assert de_la and de_la[0] is not daqui
    assert db.conexao() is daqui, "no mesmo fio, a conexão se repete"
    print("OK: uma conexão por thread, criada sob demanda")


def test_marca_e_estavel_e_depende_do_segredo():
    a = db.marca("192.168.0.1")
    assert a == db.marca("192.168.0.1")
    assert len(a) == 64 and a != "192.168.0.1"
    os.environ["PDFTODXF_SEGREDO"] = "outro-segredo"
    try:
        assert db.marca("192.168.0.1") != a, "trocar o segredo tem que mudar a marca"
    finally:
        os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"
    print("OK: a marca é estável e muda com o segredo")


def test_assinar_e_conferir():
    assinado = db.assinar("42|1700000000")
    assert db.conferir(assinado) == "42|1700000000"
    corpo, _, assinatura = assinado.partition(".")
    assert db.conferir(corpo + ".00" + assinatura[2:]) is None, "assinatura mexida"
    assert db.conferir("") is None
    assert db.conferir("sem-ponto") is None
    os.environ["PDFTODXF_SEGREDO"] = "outro-segredo"
    try:
        assert db.conferir(assinado) is None, "trocar o segredo invalida"
    finally:
        os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"
    print("OK: assinar e conferir, e a troca do segredo invalida")


def test_limpeza_apaga_consumo_velho_e_token_vencido():
    con = db.conexao()
    agora = time.time()
    con.execute("INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
                "VALUES (?,?,?,?,?)", ("b", "arquivo", "confirmado",
                                       agora - 25 * 3600, "velho"))
    con.execute("INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
                "VALUES (?,?,?,?,?)", ("b", "arquivo", "confirmado",
                                       agora - 60, "novo"))
    con.execute("INSERT INTO tokens (valor, tipo, usuario, expira_em) "
                "VALUES (?,?,?,?)", ("t-velho", "confirmacao", 1, agora - 10))
    con.execute("INSERT INTO tokens (valor, tipo, usuario, expira_em) "
                "VALUES (?,?,?,?)", ("t-novo", "confirmacao", 1, agora + 3600))
    con.commit()

    relato = db.limpar(agora)
    assert relato["consumo"] == 1 and relato["tokens"] == 1, relato
    restantes = {l["referencia"] for l in con.execute("SELECT referencia FROM consumo")}
    assert restantes == {"novo"}, restantes
    vivos = {l["valor"] for l in con.execute("SELECT valor FROM tokens")}
    assert vivos == {"t-novo"}, vivos
    print("OK: a limpeza apaga consumo de mais de 24 h e token vencido")


if __name__ == "__main__":
    test_as_tabelas_nascem_na_primeira_conexao()
    test_email_e_unico()
    test_uma_conexao_por_thread()
    test_marca_e_estavel_e_depende_do_segredo()
    test_assinar_e_conferir()
    test_limpeza_apaga_consumo_velho_e_token_vencido()
    print("Todos os testes do banco passaram.")
