"""Exportação do DXF e o cache por combinação de opções."""

import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mesmo cuidado do test_api_extracao: no Windows o worker reimporta este
# arquivo, e reatribuir a variável faria o filho apontar para outra pasta.
if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

# Aqui se testa a exportação e o cache por chave, não a cota: a bateria envia
# um arquivo por função e gera uma dezena de combinações inéditas, e os padrões
# de 5 e 15 por janela a barrariam no meio. `0` é "sem limite" — o padrão
# continua o que é, e quem exercita a cota é o tests/test_api_cotas.py.
os.environ["PDFTODXF_COTA_ARQUIVOS"] = "0"
os.environ["PDFTODXF_COTA_DOWNLOADS"] = "0"
if "PDFTODXF_BANCO" not in os.environ:
    os.environ["PDFTODXF_BANCO"] = os.path.join(
        tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

import ezdxf
from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial, enviar, esperar
from web.api.main import app

cliente = TestClient(app)

PEDIDO = {
    "escala": 0.01,
    "unidade": "m",
    "opcoes": {
        "excluded_layers": [],
        "drop_fills": False,
        "min_len_mm": 0.0,
        "dedup": False,
        "join_polylines": False,
        "round_coords": False,
    },
}


def preparar() -> str:
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    return job


def test_exportacao_gera_dxf_valido():
    job = preparar()
    r = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["cache"] is False
    assert corpo["entidades"] > 0

    baixado = cliente.get(corpo["url"])
    assert baixado.status_code == 200, baixado.text
    assert baixado.headers["content-type"] == "application/dxf"

    caminho = os.path.join(tempfile.mkdtemp(), "saida.dxf")
    with open(caminho, "wb") as f:
        f.write(baixado.content)
    doc = ezdxf.readfile(caminho)
    assert not doc.audit().has_errors
    assert doc.header["$INSUNITS"] == 6, "unidade metros"
    print("OK: exportação gera um DXF válido em metros")


def test_mesma_combinacao_reaproveita():
    job = preparar()
    primeiro = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO).json()
    segundo = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO).json()
    assert primeiro["url"] == segundo["url"]
    assert segundo["cache"] is True, "a segunda vez tinha que vir do cache"
    assert segundo["entidades"] == primeiro["entidades"], \
        "a contagem do cache tem que bater com a da geração"
    print("OK: repetir a mesma combinação reaproveita o arquivo")


def test_combinacao_diferente_gera_outro():
    job = preparar()
    a = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO).json()
    outro = {**PEDIDO, "opcoes": {**PEDIDO["opcoes"], "dedup": True}}
    b = cliente.post(f"/api/jobs/{job}/pages/1/export", json=outro).json()
    assert a["url"] != b["url"], "opções diferentes têm que dar chaves diferentes"
    assert b["cache"] is False
    print("OK: combinação diferente gera arquivo novo")


def test_ordem_dos_layers_nao_muda_a_chave():
    job = preparar()
    um = {**PEDIDO, "opcoes": {**PEDIDO["opcoes"],
                               "excluded_layers": ["TEXTO", "COR_FF0000"]}}
    dois = {**PEDIDO, "opcoes": {**PEDIDO["opcoes"],
                                 "excluded_layers": ["COR_FF0000", "TEXTO"]}}
    a = cliente.post(f"/api/jobs/{job}/pages/1/export", json=um).json()
    b = cliente.post(f"/api/jobs/{job}/pages/1/export", json=dois).json()
    assert a["url"] == b["url"], "a chave não pode depender da ordem da lista"
    assert b["cache"] is True
    print("OK: a chave não depende da ordem dos layers excluídos")


def test_pedido_invalido():
    job = preparar()
    ruim = {**PEDIDO, "unidade": "polegadas"}
    r = cliente.post(f"/api/jobs/{job}/pages/1/export", json=ruim)
    assert r.status_code == 422, r.status_code
    ruim = {**PEDIDO, "escala": 0.0}
    r = cliente.post(f"/api/jobs/{job}/pages/1/export", json=ruim)
    assert r.status_code == 422, r.status_code
    print("OK: pedido inválido é recusado antes de gerar")


def test_escala_infinita_e_recusada():
    """`gt=0.0` não basta: `inf > 0` é verdadeiro, e o JSON permite Infinity.

    O nan já caía sozinho — `nan > 0` é falso —, mas o infinito atravessava a
    conferência e virava um DXF de coordenadas infinitas, que nenhum CAD abre.
    """
    job = preparar()
    for ruim in ("Infinity", "-Infinity", "NaN"):
        corpo = ('{"escala": %s, "unidade": "m", "opcoes": {}}' % ruim)
        r = cliente.post(f"/api/jobs/{job}/pages/1/export", content=corpo,
                         headers={"content-type": "application/json"})
        assert r.status_code == 422, (ruim, r.status_code)
    print("OK: escala infinita ou nan é recusada")


def test_download_com_chave_inventada():
    job = preparar()
    r = cliente.get(f"/api/download/{job}/{'a' * 64}")
    assert r.status_code == 404, r.status_code
    r = cliente.get(f"/api/download/{job}/../../etc/passwd")
    assert r.status_code in (400, 404), r.status_code
    print("OK: chave inventada ou maliciosa não entrega arquivo")


def test_export_em_pagina_que_nao_ficou_pronta():
    from web.api import storage

    job = enviar(bytes_do_pdf_vetorial())
    (storage.pasta(job) / "origem.pdf").unlink()
    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "erro"

    r = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
    assert r.status_code == 409, r.status_code
    print("OK: exportar página que não ficou pronta responde 409")


def test_geracoes_simultaneas_da_mesma_chave():
    """Quatro pedidos idênticos ao mesmo tempo: um gera, três aproveitam.

    Todos chegam vendo o arquivo faltando. Sem trava por chave os quatro geram
    o mesmo desenho — CPU jogada fora no processo que atende o site — e as
    quatro gravações disputam o mesmo destino; no Windows a troca volta como
    `ERROR_ACCESS_DENIED` e o pedido morre em 500.
    """
    job = preparar()
    largada = threading.Barrier(4)
    respostas = []
    trava = threading.Lock()

    def exportar():
        largada.wait()
        r = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
        with trava:
            respostas.append(r)

    fios = [threading.Thread(target=exportar) for _ in range(4)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()

    assert len(respostas) == 4
    assert all(r.status_code == 200 for r in respostas), \
        [r.status_code for r in respostas]
    urls = {r.json()["url"] for r in respostas}
    assert len(urls) == 1, urls
    geraram = [r for r in respostas if r.json()["cache"] is False]
    assert len(geraram) == 1, f"{len(geraram)} geraram o mesmo arquivo"

    baixado = cliente.get(urls.pop())
    assert baixado.status_code == 200
    caminho = os.path.join(tempfile.mkdtemp(), "simultaneo.dxf")
    with open(caminho, "wb") as f:
        f.write(baixado.content)
    doc = ezdxf.readfile(caminho)
    assert not doc.audit().has_errors
    print("OK: gerações simultâneas da mesma chave não corrompem o arquivo")


if __name__ == "__main__":
    test_exportacao_gera_dxf_valido()
    test_mesma_combinacao_reaproveita()
    test_combinacao_diferente_gera_outro()
    test_ordem_dos_layers_nao_muda_a_chave()
    test_pedido_invalido()
    test_escala_infinita_e_recusada()
    test_download_com_chave_inventada()
    test_export_em_pagina_que_nao_ficou_pronta()
    test_geracoes_simultaneas_da_mesma_chave()
    print("Todos os testes de exportação passaram.")
