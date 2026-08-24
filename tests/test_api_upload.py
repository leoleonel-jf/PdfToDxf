"""Envio do PDF: teto de tamanho, arquivo inválido e ficha do trabalho."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# a raiz dos dados tem que ser definida antes de importar o serviço
os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

# Aqui se testa o envio, não a cota: várias destas funções enviam um arquivo
# cada, e o padrão de 5 por janela barraria a bateria no meio. `0` é
# "sem limite" — o padrão continua o que é, e quem exercita a cota é o
# tests/test_api_cotas.py.
os.environ["PDFTODXF_COTA_ARQUIVOS"] = "0"
os.environ["PDFTODXF_COTA_DOWNLOADS"] = "0"
# `0` aqui também é "sem limite", e "sem teto de plano" é o teto técnico do
# servidor — que é justamente o que `test_arquivo_grande_demais` confere.
os.environ["PDFTODXF_COTA_MB"] = "0"
# Banco próprio e segredo fixo: sem isto a bateria escreveria consumo num
# `dados/contas.db` ao lado do repositório e avisaria do segredo aleatório.
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

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


BORDA = "----pdftodxf-sem-content-length"


def multipart_em_pedacos(corpo: bytes, pedaco: int = 64 * 1024):
    """O `multipart` montado à mão, em pedaços.

    Corpo em gerador é o que faz o `httpx` sair *chunked*, **sem**
    `content-length` — e é assim que o envio escapa da primeira conferência e
    chega ao laço de leitura, que é o ramo que se quer exercitar.
    """
    yield (f"--{BORDA}\r\n"
           'Content-Disposition: form-data; name="arquivo"; '
           'filename="grande.pdf"\r\n'
           "Content-Type: application/pdf\r\n\r\n").encode()
    for i in range(0, len(corpo), pedaco):
        yield corpo[i:i + pedaco]
    yield f"\r\n--{BORDA}--\r\n".encode()


def test_arquivo_grande_nao_fica_em_disco():
    """O teto é conferido **durante** a gravação, e não só pelo `content-length`.

    Com `content-length` o envio morre antes de a pasta existir, e o
    `antes == depois` seria verdade por vacuidade — nada teria acontecido. Aqui
    o envio vai *chunked*: a pasta chega a ser criada, o `raise Recusa` de
    dentro do laço de `arquivo.read` é quem recusa (o 413 é o que prova qual
    ramo agiu — sem ele o entulho viraria um 400 de "não é PDF"), e o `rmtree`
    do caminho de falha é quem limpa.
    """
    from web.api import storage
    os.environ["PDFTODXF_COTA_MB"] = "1"   # teto pequeno: 2 MB de entulho bastam
    try:
        antes = set(p.name for p in storage.raiz().iterdir())
        entulho = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)
        pedido = cliente.build_request(
            "POST", "/api/jobs", content=multipart_em_pedacos(entulho),
            headers={"content-type": f"multipart/form-data; boundary={BORDA}"})
        assert "content-length" not in pedido.headers, dict(pedido.headers)
        r = cliente.send(pedido)
        assert r.status_code == 413, (r.status_code, r.text)
        assert r.json()["codigo"] == "tamanho", r.json()
        depois = set(p.name for p in storage.raiz().iterdir())
        assert antes == depois, f"sobrou lixo: {depois - antes}"
    finally:
        os.environ["PDFTODXF_COTA_MB"] = "0"
    print("OK: o teto barra durante a leitura, e o recusado não fica em disco")


if __name__ == "__main__":
    test_envio_aceito()
    test_consulta_do_trabalho()
    test_job_id_invalido_nao_toca_o_disco()
    test_arquivo_grande_demais()
    test_arquivo_que_nao_e_pdf()
    test_arquivo_grande_nao_fica_em_disco()
    print("Todos os testes de envio passaram.")
