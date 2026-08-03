"""Envio do PDF: teto de tamanho, arquivo inválido e ficha do trabalho."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# a raiz dos dados tem que ser definida antes de importar o serviço
os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

from fastapi.testclient import TestClient

from tests.test_roundtrip import make_test_pdf
from web.api import limits
from web.api.main import app

cliente = TestClient(app)


def pdf_de_teste() -> bytes:
    caminho = os.path.join(tempfile.mkdtemp(), "planta.pdf")
    make_test_pdf(caminho)
    with open(caminho, "rb") as f:
        return f.read()


def test_envio_aceito():
    dados = pdf_de_teste()
    r = cliente.post("/api/jobs",
                     files={"arquivo": ("planta.pdf", dados, "application/pdf")})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert len(corpo["job_id"]) == 32
    assert corpo["n_paginas"] == 1, corpo
    assert corpo["nome"] == "planta.pdf"
    print("OK: envio aceito devolve ficha do trabalho")


def test_consulta_do_trabalho():
    dados = pdf_de_teste()
    job = cliente.post("/api/jobs",
                       files={"arquivo": ("planta.pdf", dados, "application/pdf")}).json()
    r = cliente.get(f"/api/jobs/{job['job_id']}")
    assert r.status_code == 200, r.text
    assert r.json()["n_paginas"] == 1
    print("OK: consulta devolve o trabalho")


def test_job_id_invalido_nao_toca_o_disco():
    for ruim in ("../etc", "..", "x" * 32, "a" * 31, "/absoluto"):
        r = cliente.get(f"/api/jobs/{ruim}")
        assert r.status_code in (400, 404), f"{ruim!r} devolveu {r.status_code}"
    print("OK: identificador inválido é recusado")


def test_arquivo_grande_demais():
    entulho = b"%PDF-1.4\n" + b"0" * (limits.TETO_PDF_BYTES + 1024)
    r = cliente.post("/api/jobs",
                     files={"arquivo": ("grande.pdf", entulho, "application/pdf")})
    assert r.status_code == 413, r.status_code
    assert "100" in r.json()["detail"], r.json()
    print("OK: arquivo acima do teto é recusado com 413")


def test_arquivo_que_nao_e_pdf():
    r = cliente.post("/api/jobs",
                     files={"arquivo": ("nao.pdf", b"isto nao e um pdf",
                                        "application/pdf")})
    assert r.status_code == 400, r.status_code
    print("OK: arquivo que não é PDF é recusado com 400")


def test_arquivo_grande_nao_fica_em_disco():
    """O teto é verificado durante a gravação, não depois: nenhum resto
    do envio recusado pode sobrar na pasta de dados."""
    from web.api import storage
    antes = set(p.name for p in storage.raiz().iterdir())
    entulho = b"%PDF-1.4\n" + b"0" * (limits.TETO_PDF_BYTES + 1024)
    cliente.post("/api/jobs",
                 files={"arquivo": ("grande.pdf", entulho, "application/pdf")})
    depois = set(p.name for p in storage.raiz().iterdir())
    assert antes == depois, f"sobrou lixo: {depois - antes}"
    print("OK: envio recusado não deixa resto em disco")


if __name__ == "__main__":
    test_envio_aceito()
    test_consulta_do_trabalho()
    test_job_id_invalido_nao_toca_o_disco()
    test_arquivo_grande_demais()
    test_arquivo_que_nao_e_pdf()
    test_arquivo_grande_nao_fica_em_disco()
    print("Todos os testes de envio passaram.")
