"""Entrar, sair, e o que a sessão muda na cota."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
if "PDFTODXF_REGISTROS" not in os.environ:
    os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial
from web.api import auth, db
from web.api.main import app

# O `tests/test_api_extracao`, importado acima só pela fábrica de PDF, desliga a
# cota ao ser carregado (`PDFTODXF_COTA_ARQUIVOS=0`, que é "sem limite"). Aqui
# metade da bateria mede justamente a diferença entre a cota do visitante e a do
# logado: sem devolver as chaves ao estado ausente, os testes de 429 nunca
# barrariam nada e passariam por não fazer nada. Vem depois do import de
# propósito; antes, o import as apagaria de novo.
os.environ.pop("PDFTODXF_COTA_ARQUIVOS", None)
os.environ.pop("PDFTODXF_COTA_DOWNLOADS", None)


def cliente_novo() -> TestClient:
    return TestClient(app)


def limpar_consumo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def conta_pronta(email: str, senha: str = "abc12345") -> int:
    uid = auth.criar_conta(email, senha, "127.0.0.1")
    auth.confirmar_conta(uid)
    return uid


def test_entrar_e_sair():
    conta_pronta("gil@exemplo.com")
    cliente = cliente_novo()
    r = cliente.post("/api/auth/entrar",
                     json={"email": "GIL@exemplo.com", "senha": "abc12345"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "gil@exemplo.com"
    assert auth.COOKIE_SESSAO in cliente.cookies

    r = cliente.post("/api/auth/sair")
    assert r.status_code == 200
    assert not cliente.cookies.get(auth.COOKIE_SESSAO)
    print("OK: entrar grava a sessão e sair a apaga")


def test_email_inexistente_e_senha_errada_respondem_igual():
    conta_pronta("hel@exemplo.com")
    cliente = cliente_novo()
    a = cliente.post("/api/auth/entrar",
                     json={"email": "hel@exemplo.com", "senha": "errada!!"})
    b = cliente.post("/api/auth/entrar",
                     json={"email": "ninguem@exemplo.com", "senha": "errada!!"})
    assert a.status_code == b.status_code == 401, (a.status_code, b.status_code)
    assert a.json() == b.json(), (a.json(), b.json())
    print("OK: e-mail inexistente e senha errada devolvem a mesma coisa")


def test_o_cookie_de_sessao_e_httponly_e_samesite():
    conta_pronta("ines@exemplo.com")
    cliente = cliente_novo()
    r = cliente.post("/api/auth/entrar",
                     json={"email": "ines@exemplo.com", "senha": "abc12345"})
    bruto = r.headers.get("set-cookie", "")
    assert "httponly" in bruto.lower(), bruto
    assert "samesite=lax" in bruto.lower(), bruto
    print("OK: o cookie de sessão é HttpOnly e SameSite=Lax")


def test_sessao_forjada_e_vencida_nao_valem():
    class P:
        def __init__(self, valor):
            self.cookies = {auth.COOKIE_SESSAO: valor}
            self.headers = {}
            self.client = type("C", (), {"host": "127.0.0.1"})()

    uid = conta_pronta("joa@exemplo.com")
    assert auth.dono_da_sessao(P("inventado")) is None
    assert auth.dono_da_sessao(P("")) is None
    velha = auth.criar_sessao(uid, agora=time.time() - auth.PRAZO_SESSAO_S - 10)
    assert auth.dono_da_sessao(P(velha)) is None, "sessão vencida não vale"
    boa = auth.criar_sessao(uid)
    assert auth.dono_da_sessao(P(boa)) == (uid, True)
    print("OK: sessão forjada ou vencida não vale")


def test_trocar_o_segredo_invalida_as_sessoes():
    uid = conta_pronta("kai@exemplo.com")
    valor = auth.criar_sessao(uid)

    class P:
        cookies = {auth.COOKIE_SESSAO: valor}
        headers = {}
        client = type("C", (), {"host": "127.0.0.1"})()

    assert auth.dono_da_sessao(P()) is not None
    os.environ["PDFTODXF_SEGREDO"] = "outro-segredo"
    try:
        assert auth.dono_da_sessao(P()) is None
    finally:
        os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"
    print("OK: trocar o segredo invalida as sessões emitidas antes")


def test_logado_confirmado_envia_mais_que_visitante():
    limpar_consumo()
    conta_pronta("lia@exemplo.com")
    cliente = cliente_novo()
    cliente.post("/api/auth/entrar",
                 json={"email": "lia@exemplo.com", "senha": "abc12345"})
    for i in range(15):
        r = cliente.post("/api/jobs", files={
            "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
        assert r.status_code == 200, (i, r.status_code)
    r = cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    assert r.status_code == 429, r.status_code
    print("OK: logado confirmado envia 15 e é barrado no décimo sexto")


def test_conta_sem_confirmar_fica_com_cota_de_visitante():
    limpar_consumo()
    auth.criar_conta("mar@exemplo.com", "abc12345", "127.0.0.1")
    cliente = cliente_novo()
    cliente.post("/api/auth/entrar",
                 json={"email": "mar@exemplo.com", "senha": "abc12345"})
    for i in range(5):
        r = cliente.post("/api/jobs", files={
            "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
        assert r.status_code == 200, (i, r.status_code)
    r = cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    assert r.status_code == 429, r.status_code

    # E passa à cota cheia depois de confirmar.
    auth.confirmar_conta(auth.por_email("mar@exemplo.com")["id"])
    r = cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    assert r.status_code == 200, r.status_code
    print("OK: sem confirmar é cota de visitante; confirmar destrava a cheia")


def test_pdf_de_40_mb_e_recusado_ao_visitante_e_aceito_ao_logado():
    limpar_consumo()
    grande = b"%PDF-1.4\n" + b"0" * (40 * 1024 * 1024)

    visitante = cliente_novo()
    r = visitante.post("/api/jobs", files={
        "arquivo": ("g.pdf", grande, "application/pdf")})
    assert r.status_code == 413, r.status_code
    assert r.json()["teto_bytes"] == 10 * 1024 * 1024, r.json()

    conta_pronta("nel@exemplo.com")
    logado = cliente_novo()
    logado.post("/api/auth/entrar",
                json={"email": "nel@exemplo.com", "senha": "abc12345"})
    r = logado.post("/api/jobs", files={
        "arquivo": ("g.pdf", grande, "application/pdf")})
    # Passa do teto de tamanho e morre no `fitz` — que é 400, não 413.
    assert r.status_code == 400, r.status_code
    print("OK: 40 MB é recusado ao visitante por tamanho e aceito ao logado")


if __name__ == "__main__":
    test_entrar_e_sair()
    test_email_inexistente_e_senha_errada_respondem_igual()
    test_o_cookie_de_sessao_e_httponly_e_samesite()
    test_sessao_forjada_e_vencida_nao_valem()
    test_trocar_o_segredo_invalida_as_sessoes()
    test_logado_confirmado_envia_mais_que_visitante()
    test_conta_sem_confirmar_fica_com_cota_de_visitante()
    test_pdf_de_40_mb_e_recusado_ao_visitante_e_aceito_ao_logado()
    print("Todos os testes de sessão passaram.")
