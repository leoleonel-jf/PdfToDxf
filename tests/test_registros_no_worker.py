"""A extração de verdade grava o registro, e o serviço não o entrega pela web."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Como no test_api_extracao: no Windows o worker reimporta este arquivo, e
# reatribuir a variável faria o filho apontar para outra pasta.
if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
if "PDFTODXF_REGISTROS" not in os.environ:
    os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")

from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial, enviar, esperar
from web.api import registros
from web.api.main import app

cliente = TestClient(app)


def test_extracao_grava_o_registro():
    antes = {p.name for p in registros.pasta().iterdir()}
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "pronta"

    novos = [p for p in registros.pasta().iterdir() if p.name not in antes]
    assert len(novos) == 1, [p.name for p in novos]
    texto = novos[0].read_text(encoding="utf-8")
    assert texto.startswith("---\n")
    assert job in texto, "o job_id tem que estar no frontmatter"
    assert "## Textos da planta" in texto
    print("OK: a extração de verdade grava o registro")


def test_falha_ao_gravar_o_registro_nao_derruba_a_pagina():
    """Perder um registro não pode custar ao usuário a planta que ele veio converter."""
    from web.api import jobs

    original = os.environ["PDFTODXF_REGISTROS"]
    # Um arquivo no lugar da pasta: `mkdir` estoura e a gravação falha.
    impossivel = os.path.join(tempfile.mkdtemp(), "nao-e-pasta")
    with open(impossivel, "w") as f:
        f.write("x")
    os.environ["PDFTODXF_REGISTROS"] = impossivel
    try:
        job = enviar(bytes_do_pdf_vetorial())
        cliente.post(f"/api/jobs/{job}/pages/1")
        final = esperar(job, 1)
    finally:
        os.environ["PDFTODXF_REGISTROS"] = original

    assert final["situacao"] == "pronta", final
    print("OK: falha ao gravar o registro não impede a página de ficar pronta")


def test_nenhuma_rota_alcanca_a_pasta_de_registros():
    caminhos = [
        "/registros/",
        "/registros/qualquer.md",
        "/api/registros",
        "/../registros/qualquer.md",
        "/api/download/" + "a" * 32 + "/../../../registros/qualquer.md",
    ]
    for caminho in caminhos:
        r = cliente.get(caminho)
        assert r.status_code in (400, 404), (caminho, r.status_code)
    print("OK: nenhuma rota do serviço alcança a pasta de registros")


if __name__ == "__main__":
    test_extracao_grava_o_registro()
    test_falha_ao_gravar_o_registro_nao_derruba_a_pagina()
    test_nenhuma_rota_alcanca_a_pasta_de_registros()
    print("Todos os testes de registro no worker passaram.")
