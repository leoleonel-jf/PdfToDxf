"""Divisão em esqueleto e detalhe, e as rotas que servem as duas partes."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mesmo cuidado do test_api_extracao: no Windows o worker reimporta este
# arquivo, e reatribuir a variável faria o filho apontar para outra pasta.
if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

from fastapi.testclient import TestClient

from pdftodxf.geometry import Polyline, Segment, TextItem
from pdftodxf.optimize import classify
from tests.test_api_extracao import bytes_do_pdf_vetorial, enviar, esperar
from web.api import packing
from web.api.main import app

cliente = TestClient(app)


def test_divisao_cobre_tudo_sem_repetir():
    ents = [Segment(p1=(0.0, 0.0), p2=(float(i % 50 + 1), 0.0))
            for i in range(1000)]
    ents.append(TextItem(text="x", position=(0.0, 0.0)))
    a = classify(ents)
    esqueleto, detalhe, limiar = packing.dividir(a, alvo=100)

    assert set(esqueleto) & set(detalhe) == set(), "entidade em duas partes"
    assert sorted(esqueleto + detalhe) == list(range(len(ents))), \
        "juntas, as partes têm que dar a lista inteira"
    assert esqueleto == sorted(esqueleto), "o esqueleto perdeu a ordem original"
    assert detalhe == sorted(detalhe), "o detalhe perdeu a ordem original"
    assert len(ents) - 1 in esqueleto, "o texto tem que estar no esqueleto"
    assert limiar > 0
    print("OK: divisão cobre tudo, sem repetir e sem reordenar")


def test_pagina_pequena_nao_divide():
    ents = [Segment(p1=(0.0, 0.0), p2=(1.0, 0.0)) for _ in range(10)]
    a = classify(ents)
    esqueleto, detalhe, limiar = packing.dividir(a, alvo=100)
    assert len(esqueleto) == 10 and detalhe == []
    assert limiar == 0, "sem divisão, não há limiar"
    print("OK: página pequena vai inteira no esqueleto")


def test_esqueleto_fica_com_os_segmentos_mais_longos():
    ents = [Segment(p1=(0.0, 0.0), p2=(float(i + 1), 0.0)) for i in range(100)]
    a = classify(ents)
    esqueleto, detalhe, limiar = packing.dividir(a, alvo=10)
    assert all(a.length_um[i] >= limiar for i in esqueleto)
    assert all(a.length_um[i] < limiar for i in detalhe)
    print("OK: o esqueleto fica com os segmentos mais longos")


def test_pagina_sem_segmento_nenhum():
    """Página só de polilinhas, maior que o alvo: não há o que mandar ao detalhe.

    A regra só sabe cortar por comprimento de segmento. Sem segmento nenhum, a
    conta de vagas fica negativa e o caminho do `max()` recebe uma lista vazia.
    Uma planta em que todo traço virou polilinha — hachura pesada, por exemplo —
    chegaria ao usuário como erro interno.
    """
    ents = [Polyline(points=[(0.0, 0.0), (1.0, 1.0)]) for _ in range(30)]
    a = classify(ents)
    esqueleto, detalhe, limiar = packing.dividir(a, alvo=10)
    assert esqueleto == list(range(30)), esqueleto
    assert detalhe == []
    assert limiar == 0
    print("OK: página sem segmento nenhum não estoura")


def test_alvo_padrao_tem_piso_e_fracao():
    assert packing.alvo_padrao(100) == packing.ALVO_MINIMO
    assert packing.alvo_padrao(1_000_000) == 50_000
    print("OK: alvo padrão é 5% das entidades, com piso")


def test_rotas_servem_as_duas_partes():
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)

    meta = cliente.get(f"/api/jobs/{job}/pages/1/meta.json")
    assert meta.status_code == 200, meta.text
    m = meta.json()
    assert m["n_entidades"] > 0
    assert m["largura_pt"] > 0 and m["altura_pt"] > 0
    assert isinstance(m["layers"], list) and m["layers"]
    assert m["partes"]["esqueleto"] + m["partes"]["detalhe"] == m["n_entidades"]

    esq = cliente.get(f"/api/jobs/{job}/pages/1/geometry.bin?parte=esqueleto")
    assert esq.status_code == 200
    assert esq.headers["content-type"] == "application/octet-stream"
    lido = packing.desempacotar(esq.content)
    assert lido["n"] == m["partes"]["esqueleto"]

    det = cliente.get(f"/api/jobs/{job}/pages/1/geometry.bin?parte=detalhe")
    assert det.status_code == 200
    lido_det = packing.desempacotar(det.content)
    assert lido_det["n"] == m["partes"]["detalhe"]

    juntos = sorted(lido["idx"] + lido_det["idx"])
    assert juntos == list(range(m["n_entidades"])), \
        "esqueleto + detalhe não reproduzem a extração"
    print("OK: as rotas servem as duas partes e juntas reproduzem tudo")


def test_parte_invalida():
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    r = cliente.get(f"/api/jobs/{job}/pages/1/geometry.bin?parte=inventada")
    assert r.status_code == 400, r.status_code
    print("OK: parte desconhecida é recusada")


def test_pagina_nao_pronta_nao_serve_geometria():
    """Página que deu erro responde 409, não 500 nem arquivo pela metade."""
    from web.api import storage

    job = enviar(bytes_do_pdf_vetorial())
    (storage.pasta(job) / "origem.pdf").unlink()
    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "erro"

    r = cliente.get(f"/api/jobs/{job}/pages/1/geometry.bin?parte=esqueleto")
    assert r.status_code == 409, r.status_code
    m = cliente.get(f"/api/jobs/{job}/pages/1/meta.json")
    assert m.status_code == 409, m.status_code
    print("OK: página que não ficou pronta responde 409")


if __name__ == "__main__":
    test_divisao_cobre_tudo_sem_repetir()
    test_pagina_pequena_nao_divide()
    test_esqueleto_fica_com_os_segmentos_mais_longos()
    test_pagina_sem_segmento_nenhum()
    test_alvo_padrao_tem_piso_e_fracao()
    test_rotas_servem_as_duas_partes()
    test_parte_invalida()
    test_pagina_nao_pronta_nao_serve_geometria()
    print("Todos os testes de geometria passaram.")
