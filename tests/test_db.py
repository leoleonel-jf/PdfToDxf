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
    assinado = db.assinar("42|1700000000", db.DOMINIO_SESSAO)
    assert db.conferir(assinado, db.DOMINIO_SESSAO) == "42|1700000000"
    corpo, _, assinatura = assinado.partition(".")
    assert db.conferir(corpo + ".00" + assinatura[2:],
                       db.DOMINIO_SESSAO) is None, "assinatura mexida"
    assert db.conferir("", db.DOMINIO_SESSAO) is None
    assert db.conferir("sem-ponto", db.DOMINIO_SESSAO) is None
    os.environ["PDFTODXF_SEGREDO"] = "outro-segredo"
    try:
        assert db.conferir(assinado, db.DOMINIO_SESSAO) is None, \
            "trocar o segredo invalida"
    finally:
        os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"
    print("OK: assinar e conferir, e a troca do segredo invalida")


def test_um_dominio_nao_le_o_assinado_do_outro():
    """Separação de domínio: o envelope de um uso não abre no outro.

    Sem isto, o cookie do visitante e o cookie de sessão saem do mesmo envelope
    assinado, e qualquer valor que o serviço assine num deles é aceito no
    outro. Hoje não dá exploração — o corpo do visitante é um
    `token_urlsafe(24)`, que o `int()` de `auth.dono_da_sessao` recusa —, mas
    basta uma tarefa futura assinar algo controlável no formato
    `<inteiro>|<numero>` para virar forja de sessão.
    """
    de_sessao = db.assinar("42|1700000000", db.DOMINIO_SESSAO)
    de_cookie = db.assinar("42|1700000000", db.DOMINIO_COOKIE_VISITANTE)

    assert de_sessao != de_cookie, \
        "mesmo corpo em domínios diferentes tem de dar assinaturas diferentes"
    assert db.conferir(de_sessao, db.DOMINIO_COOKIE_VISITANTE) is None, \
        "o assinado da sessão não pode valer como cookie de visitante"
    assert db.conferir(de_cookie, db.DOMINIO_SESSAO) is None, \
        "o cookie de visitante não pode valer como sessão"
    # E cada um continua valendo no seu.
    assert db.conferir(de_sessao, db.DOMINIO_SESSAO) == "42|1700000000"
    assert db.conferir(de_cookie,
                       db.DOMINIO_COOKIE_VISITANTE) == "42|1700000000"
    # Trocar só o corpo de um envelope pelo do outro também não passa: o
    # domínio entra no `hmac`, e não num campo do envelope que dê para editar.
    corpo_de_cookie = de_cookie.partition(".")[0]
    _corpo, _, assinatura_de_sessao = de_sessao.partition(".")
    assert db.conferir(f"{corpo_de_cookie}.{assinatura_de_sessao}",
                       db.DOMINIO_COOKIE_VISITANTE) is None
    print("OK: um domínio não lê o assinado do outro")


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
    test_um_dominio_nao_le_o_assinado_do_outro()
    test_limpeza_apaga_consumo_velho_e_token_vencido()
    print("Todos os testes do banco passaram.")
