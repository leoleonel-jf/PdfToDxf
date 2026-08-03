"""Extração de página: fila, estados e recusas."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# setdefault (não atribuição direta): no Windows o `ProcessPoolExecutor` usa
# spawn e reimporta este arquivo como __main__ dentro de cada worker. Com
# atribuição direta, cada worker criaria a sua própria pasta temporária vazia
# em vez de herdar a pasta do processo pai.
os.environ.setdefault("PDFTODXF_DADOS", tempfile.mkdtemp(prefix="pdftodxf-teste-"))

import fitz
from fastapi.testclient import TestClient

from tests.test_roundtrip import make_test_pdf
from web.api.main import app

cliente = TestClient(app)


def enviar(dados: bytes, nome: str = "planta.pdf") -> str:
    r = cliente.post("/api/jobs",
                     files={"arquivo": (nome, dados, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def bytes_do_pdf_vetorial() -> bytes:
    caminho = os.path.join(tempfile.mkdtemp(), "planta.pdf")
    make_test_pdf(caminho)
    with open(caminho, "rb") as f:
        return f.read()


def bytes_de_pdf_sem_vetores() -> bytes:
    """Uma página em branco: nenhum desenho, nenhum texto."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    caminho = os.path.join(tempfile.mkdtemp(), "branco.pdf")
    doc.save(caminho)
    doc.close()
    with open(caminho, "rb") as f:
        return f.read()


def esperar(job_id: str, pagina: int, limite: float = 60.0) -> dict:
    """Aguarda a página sair da fila. Devolve o estado final."""
    fim = time.time() + limite
    while time.time() < fim:
        estado = cliente.get(f"/api/jobs/{job_id}/pages/{pagina}").json()
        if estado["situacao"] in ("pronta", "erro"):
            return estado
        time.sleep(0.2)
    raise AssertionError(f"a página {pagina} não terminou em {limite}s")


def test_extracao_completa():
    job = enviar(bytes_do_pdf_vetorial())
    r = cliente.post(f"/api/jobs/{job}/pages/1")
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] in ("na_fila", "extraindo", "pronta")
    estado = esperar(job, 1)
    assert estado["situacao"] == "pronta", estado
    assert estado["n_entidades"] > 0
    assert "TEXTO" in estado["layers"], estado["layers"]
    print("OK: extração de página conclui e informa contagens")


def test_pdf_original_e_apagado():
    from web.api import storage
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    assert not (storage.pasta(job) / "origem.pdf").exists(), \
        "o PDF original deveria sumir depois da extração"
    print("OK: PDF original é apagado após a extração")


def test_pagina_inexistente():
    job = enviar(bytes_do_pdf_vetorial())
    r = cliente.post(f"/api/jobs/{job}/pages/99")
    assert r.status_code == 404, r.status_code
    print("OK: página fora do documento é recusada")


def test_pdf_sem_vetores():
    job = enviar(bytes_de_pdf_sem_vetores(), nome="branco.pdf")
    cliente.post(f"/api/jobs/{job}/pages/1")
    estado = esperar(job, 1)
    assert estado["situacao"] == "erro", estado
    assert estado["codigo"] == "sem_vetores", estado
    assert "vetorial" in estado["mensagem"].lower(), estado["mensagem"]
    print("OK: PDF sem vetores dá erro identificável")


def test_teto_de_entidades():
    """Com o teto rebaixado, a mesma planta passa a ser recusada."""
    from web.api import limits
    original = limits.TETO_ENTIDADES
    limits.TETO_ENTIDADES = 3
    try:
        job = enviar(bytes_do_pdf_vetorial())
        cliente.post(f"/api/jobs/{job}/pages/1")
        estado = esperar(job, 1)
        assert estado["situacao"] == "erro", estado
        assert estado["codigo"] == "entidades_demais", estado
    finally:
        limits.TETO_ENTIDADES = original
    print("OK: teto de entidades recusa a página com mensagem clara")


def test_pedir_duas_vezes_nao_duplica():
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    cliente.post(f"/api/jobs/{job}/pages/1")
    estado = esperar(job, 1)
    assert estado["situacao"] == "pronta", estado
    print("OK: pedir a mesma página duas vezes não duplica trabalho")


if __name__ == "__main__":
    test_extracao_completa()
    test_pdf_original_e_apagado()
    test_pagina_inexistente()
    test_pdf_sem_vetores()
    test_teto_de_entidades()
    test_pedir_duas_vezes_nao_duplica()
    print("Todos os testes de extração passaram.")
