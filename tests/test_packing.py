"""Ida e volta do formato binário da geometria."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.extractor import ExtractionResult
from pdftodxf.geometry import Arc, Bezier, Polyline, Segment, TextItem
from pdftodxf.optimize import classify
from web.api import packing


def amostra() -> ExtractionResult:
    ents = [
        Segment(p1=(0.0, 0.0), p2=(30.0, 40.0), layer="PAREDES",
                color=(1.0, 0.0, 0.0)),
        Polyline(points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], closed=True,
                 layer="COTAS", is_fill=True),
        Arc(center=(5.0, 5.0), radius=2.0, start_angle=0.0, end_angle=90.0,
            layer="PAREDES"),
        Bezier(p0=(0.0, 0.0), p1=(1.0, 2.0), p2=(3.0, 4.0), p3=(5.0, 6.0),
               layer="COTAS"),
        TextItem(text="Sala de máquinas", position=(2.0, 3.0), height=4.0,
                 rotation=90.0, width=25.0, layer="TEXTO"),
    ]
    return ExtractionResult(entities=ents, page_width=595.0, page_height=842.0,
                            layers={"PAREDES", "COTAS", "TEXTO"})


def test_ida_e_volta_completa():
    r = amostra()
    a = classify(r.entities)
    dados = packing.empacotar(r, a, list(range(len(r.entities))))
    lido = packing.desempacotar(dados)

    assert lido["n"] == 5, lido["n"]
    assert lido["idx"] == [0, 1, 2, 3, 4]
    assert lido["kind"] == [0, 1, 2, 3, 4]
    assert lido["layer_id"] == a.layer_id
    assert lido["is_fill"] == [1 if v else 0 for v in a.is_fill]
    assert lido["length_um"] == a.length_um
    assert lido["dup_group"] == a.dup_group
    assert lido["byte_cost"] == a.byte_cost
    print("OK: atributos sobrevivem à ida e volta")


def test_coordenadas():
    r = amostra()
    a = classify(r.entities)
    lido = packing.desempacotar(packing.empacotar(r, a, list(range(5))))

    seg = lido["coords_de"](0)
    assert [round(v, 3) for v in seg] == [0.0, 0.0, 30.0, 40.0], seg
    poly = lido["coords_de"](1)
    assert poly[0] == 1.0, "primeiro float da polilinha é o 'fechada'"
    assert [round(v, 3) for v in poly[1:]] == [0.0, 0.0, 1.0, 0.0, 1.0, 1.0]
    arco = lido["coords_de"](2)
    assert [round(v, 3) for v in arco] == [5.0, 5.0, 2.0, 0.0, 90.0], arco
    texto = lido["coords_de"](4)
    assert [round(v, 3) for v in texto] == [2.0, 3.0, 4.0, 90.0, 25.0], texto
    print("OK: coordenadas de cada tipo saem na ordem certa")


def test_texto_e_cor():
    r = amostra()
    a = classify(r.entities)
    lido = packing.desempacotar(packing.empacotar(r, a, list(range(5))))

    assert lido["texto_de"](4) == "Sala de máquinas"
    assert lido["texto_de"](0) == ""
    assert lido["cor"][0] == 0xFF0000, hex(lido["cor"][0])
    assert lido["cor"][2] == 0xFFFFFFFF, hex(lido["cor"][2])
    print("OK: texto acentuado e cor sobrevivem")


def test_subconjunto_preserva_indice_global():
    r = amostra()
    a = classify(r.entities)
    lido = packing.desempacotar(packing.empacotar(r, a, [1, 3]))
    assert lido["n"] == 2
    assert lido["idx"] == [1, 3], lido["idx"]
    assert lido["kind"] == [1, 3]
    assert lido["texto_de"](0) == ""
    print("OK: parte com subconjunto guarda o índice global")


def test_cabecalho_rejeita_lixo():
    try:
        packing.desempacotar(b"NOPE" + b"\0" * 32)
    except ValueError:
        print("OK: cabeçalho inválido é recusado")
        return
    raise AssertionError("deveria ter recusado o cabeçalho")


def test_secoes_ficam_alinhadas():
    """Toda seção começa em múltiplo de 4, para qualquer contagem de entidades.

    O leitor da etapa 3 monta `new Uint32Array(buffer, deslocamento, n)` em
    cima do buffer, sem copiar, e o JavaScript levanta `RangeError` quando o
    deslocamento não é múltiplo do tamanho do elemento. As seções de uint8
    (`kind`, `is_fill`) ocupam exatamente n bytes, então sem enchimento
    qualquer página cuja contagem fuja da tabuada do 4 desalinharia tudo o que
    vem depois — e nenhum teste do lado Python perceberia, porque o
    `struct.unpack_from` lê de qualquer deslocamento.
    """
    r = amostra()
    a = classify(r.entities)
    for quantas in range(0, 6):
        dados = packing.empacotar(r, a, list(range(quantas)))
        lido = packing.desempacotar(dados)
        for tipo, (desloc, tamanho) in lido["secoes"].items():
            assert desloc % 4 == 0, f"n={quantas}, seção {tipo}, em {desloc}"
            assert desloc + tamanho <= len(dados), \
                f"n={quantas}, seção {tipo} passa do fim"
    print("OK: toda seção começa em múltiplo de 4")


def test_parte_vazia():
    """Zero entidades tem de gerar um arquivo válido, não uma exceção.

    A divisão esqueleto/detalhe da tarefa 5 produz parte vazia toda vez que uma
    das duas fatias não sobrar nada.
    """
    r = amostra()
    a = classify(r.entities)
    lido = packing.desempacotar(packing.empacotar(r, a, []))
    assert lido["n"] == 0
    assert lido["idx"] == []
    assert lido["kind"] == []
    assert lido["cor"] == []
    print("OK: parte vazia é um arquivo válido")


if __name__ == "__main__":
    test_ida_e_volta_completa()
    test_coordenadas()
    test_texto_e_cor()
    test_subconjunto_preserva_indice_global()
    test_cabecalho_rejeita_lixo()
    test_secoes_ficam_alinhadas()
    test_parte_vazia()
    print("Todos os testes de empacotamento passaram.")
