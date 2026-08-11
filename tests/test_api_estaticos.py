"""O serviço entrega o frontend compilado, sem atrapalhar as rotas da API."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

from fastapi.testclient import TestClient

from web.api.main import PASTA_ESTATICOS, app

cliente = TestClient(app)


def test_api_continua_respondendo():
    """A montagem dos estáticos não pode engolir /api."""
    r = cliente.get("/api/jobs/" + "z" * 32)
    assert r.status_code == 400, r.status_code
    print("OK: as rotas da API continuam antes dos estáticos")


def test_raiz_serve_o_index_quando_existe():
    if not (PASTA_ESTATICOS / "index.html").exists():
        print("OK: sem dist/ compilado, a raiz é opcional (pulado)")
        return
    r = cliente.get("/")
    assert r.status_code == 200, r.status_code
    assert "<html" in r.text.lower()
    print("OK: a raiz serve o index compilado")


def test_sem_dist_o_servico_ainda_sobe():
    """Sem o frontend compilado, a API tem de subir do mesmo jeito.

    É o caso de todo desenvolvedor que só mexe no Python, e do teste de API.
    """
    r = cliente.post("/api/jobs")
    assert r.status_code == 422, r.status_code
    print("OK: o serviço sobe mesmo sem o frontend compilado")


if __name__ == "__main__":
    test_api_continua_respondendo()
    test_raiz_serve_o_index_quando_existe()
    test_sem_dist_o_servico_ainda_sobe()
    print("Todos os testes de estáticos passaram.")
