"""Extração de página: fila, estados e recusas."""

import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Só cria a pasta se a variável ainda não existe: no Windows o
# `ProcessPoolExecutor` usa spawn e reimporta este arquivo dentro de cada
# worker. Atribuir direto faria cada worker apontar para uma pasta temporária
# vazia sua em vez de herdar a do processo pai. O `if` em vez de `setdefault`
# porque o argumento do `setdefault` é avaliado sempre — cada worker deixaria
# uma pasta órfã atrás de si.
if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

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


def bytes_de_pdf_de_duas_paginas() -> bytes:
    """Duas páginas iguais, cada uma com geometria vetorial de sobra."""
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page(width=595, height=842)
        shape = page.new_shape()
        shape.draw_line(fitz.Point(50, 50), fitz.Point(350, 50))
        shape.draw_rect(fitz.Rect(100, 100, 300, 300))
        shape.finish(color=(0, 0, 0), width=0.5)
        shape.commit()
    caminho = os.path.join(tempfile.mkdtemp(), "duas.pdf")
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


def test_segunda_pagina_depois_da_primeira():
    """A página 2 pode ser pedida depois de a 1 ter terminado.

    O original só pode sumir quando não sobrar página para extrair. Apagá-lo
    assim que a fila esvazia deixava o documento de várias páginas pela metade:
    a segunda extração ia procurar um arquivo que não existia mais.
    """
    job = enviar(bytes_de_pdf_de_duas_paginas(), nome="duas.pdf")
    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "pronta"

    cliente.post(f"/api/jobs/{job}/pages/2")
    estado = esperar(job, 2)
    assert estado["situacao"] == "pronta", estado
    assert estado["n_entidades"] > 0, estado
    print("OK: página 2 é extraída depois de a página 1 ter terminado")


def test_original_some_quando_todas_as_paginas_terminam():
    from web.api import storage
    job = enviar(bytes_de_pdf_de_duas_paginas(), nome="duas.pdf")
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    assert (storage.pasta(job) / "origem.pdf").exists(), \
        "com a página 2 ainda por extrair, o original tem de ficar"

    cliente.post(f"/api/jobs/{job}/pages/2")
    esperar(job, 2)
    assert not (storage.pasta(job) / "origem.pdf").exists(), \
        "extraídas todas as páginas, o original deveria sumir"
    print("OK: original só some quando todas as páginas terminam")


def test_pedidos_simultaneos_submetem_uma_vez():
    """Vários POSTs concorrentes para a mesma página geram um worker só.

    As rotas são `def` síncrono, então o FastAPI as roda num pool de threads e
    dois pedidos chegam de fato ao mesmo tempo. Decidir e reservar têm de estar
    sob a mesma trava, ou os dois passam pela conferência antes de qualquer um
    gravar — e dois workers acabam gravando o mesmo cache.
    """
    from web.api import jobs

    job = enviar(bytes_do_pdf_vetorial())
    submissoes = []
    pool_real = jobs.pool()
    conta = threading.Lock()

    class PoolContado:
        def submit(self, *args, **kwargs):
            with conta:
                submissoes.append(args)
            return pool_real.submit(*args, **kwargs)

    original = jobs.pool
    jobs.pool = lambda: PoolContado()
    try:
        largada = threading.Barrier(6)

        def pedir():
            largada.wait()
            cliente.post(f"/api/jobs/{job}/pages/1")

        fios = [threading.Thread(target=pedir) for _ in range(6)]
        for f in fios:
            f.start()
        for f in fios:
            f.join()
    finally:
        jobs.pool = original

    assert esperar(job, 1)["situacao"] == "pronta"
    assert len(submissoes) == 1, f"{len(submissoes)} workers para a mesma página"
    print("OK: pedidos simultâneos da mesma página submetem um worker só")


def test_erro_inesperado_nao_se_disfarca_de_recurso():
    """Um defeito no servidor tem de chegar como `interno`, não como `recurso`.

    Apagar o original à mão simula uma falha que não é teto de memória nem de
    CPU. Enquanto tudo caía no mesmo `except`, um `FileNotFoundError` chegava ao
    usuário dizendo que a planta passou do limite de memória.
    """
    from web.api import storage

    job = enviar(bytes_do_pdf_vetorial())
    (storage.pasta(job) / "origem.pdf").unlink()
    cliente.post(f"/api/jobs/{job}/pages/1")
    estado = esperar(job, 1)
    assert estado["situacao"] == "erro", estado
    assert estado["codigo"] == "interno", estado
    print("OK: erro inesperado é classificado como interno")


if __name__ == "__main__":
    test_extracao_completa()
    test_pdf_original_e_apagado()
    test_pagina_inexistente()
    test_pdf_sem_vetores()
    test_teto_de_entidades()
    test_pedir_duas_vezes_nao_duplica()
    test_segunda_pagina_depois_da_primeira()
    test_original_some_quando_todas_as_paginas_terminam()
    test_pedidos_simultaneos_submetem_uma_vez()
    test_erro_inesperado_nao_se_disfarca_de_recurso()
    print("Todos os testes de extração passaram.")
