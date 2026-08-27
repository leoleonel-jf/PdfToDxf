"""GET /api/cota: o que a tela mostra no canto direito."""

import os
import sys
import tempfile

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

# O `tests/test_api_extracao`, importado acima só pela função auxiliar,
# desliga a cota ao ser carregado — lá se testa a extração, e a bateria não
# caberia em 5 envios. Aqui a cota **é** o assunto, então as chaves voltam ao
# estado ausente (mesmo ajuste de tests/test_api_cotas.py, e pelo mesmo
# motivo). Vem depois do import de propósito; antes, o import as apagaria de
# novo.
os.environ.pop("PDFTODXF_COTA_ARQUIVOS", None)
os.environ.pop("PDFTODXF_COTA_DOWNLOADS", None)


def cliente_novo() -> TestClient:
    return TestClient(app)


def limpar_consumo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def test_visitante_novo_ve_a_cota_cheia():
    limpar_consumo()
    r = cliente_novo().get("/api/cota")
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["tipo"] == "visitante" and c["email"] == ""
    assert c["arquivos"] == {"restam": 5, "de": 5, "libera_em": None}, c
    assert c["downloads"] == {"restam": 15, "de": 15, "libera_em": None}, c
    assert c["teto_bytes"] == 10 * 1024 * 1024
    print("OK: visitante novo vê a cota cheia")


def test_a_cota_cai_a_cada_envio():
    limpar_consumo()
    cliente = cliente_novo()
    cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    c = cliente.get("/api/cota").json()
    assert c["arquivos"]["restam"] == 4, c
    print("OK: a cota cai a cada envio")


def test_consultar_a_cota_nao_consome_cota():
    limpar_consumo()
    cliente = cliente_novo()
    for _ in range(10):
        cliente.get("/api/cota")
    assert cliente.get("/api/cota").json()["arquivos"]["restam"] == 5
    print("OK: consultar a cota não consome cota")


def test_esgotado_traz_o_libera_em():
    limpar_consumo()
    cliente = cliente_novo()
    for _ in range(5):
        cliente.post("/api/jobs", files={
            "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    c = cliente.get("/api/cota").json()
    assert c["arquivos"]["restam"] == 0
    assert c["arquivos"]["libera_em"], c
    print("OK: cota esgotada traz quando a próxima vaga abre")


def test_logado_ve_o_proprio_email_e_a_cota_maior():
    limpar_consumo()
    uid = auth.criar_conta("rui@exemplo.com", "abc12345", "127.0.0.1")
    auth.confirmar_conta(uid)
    cliente = cliente_novo()
    cliente.post("/api/auth/entrar",
                 json={"email": "rui@exemplo.com", "senha": "abc12345"})
    c = cliente.get("/api/cota").json()
    assert c["tipo"] == "logado" and c["email"] == "rui@exemplo.com"
    assert c["confirmado"] is True
    assert c["arquivos"]["de"] == 15 and c["downloads"]["de"] == 45
    assert c["teto_bytes"] == 100 * 1024 * 1024
    print("OK: logado vê o próprio e-mail e a cota maior")


def test_sem_limite_devolve_nulo_e_nao_um_numero_grande():
    limpar_consumo()
    os.environ["PDFTODXF_COTA_ARQUIVOS"] = "0"
    try:
        c = cliente_novo().get("/api/cota").json()
        assert c["arquivos"] == {"restam": None, "de": None, "libera_em": None}, c
    finally:
        del os.environ["PDFTODXF_COTA_ARQUIVOS"]
    print("OK: sem limite devolve nulo, e não um número grande")


if __name__ == "__main__":
    test_visitante_novo_ve_a_cota_cheia()
    test_a_cota_cai_a_cada_envio()
    test_consultar_a_cota_nao_consome_cota()
    test_esgotado_traz_o_libera_em()
    test_logado_ve_o_proprio_email_e_a_cota_maior()
    test_sem_limite_devolve_nulo_e_nao_um_numero_grande()
    print("Todos os testes da rota de cota passaram.")
