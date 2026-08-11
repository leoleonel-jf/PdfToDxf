"""Gera a fixture que o leitor TypeScript do formato binário confere.

Determinística: regerar não pode sujar o `git diff`. Se sujar, o formato mudou.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.extractor import ExtractionResult
from pdftodxf.geometry import Arc, Bezier, Polyline, Segment, TextItem
from pdftodxf.optimize import classify
from web.api import packing

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def amostra() -> ExtractionResult:
    """Um exemplar de cada tipo, com cor, texto acentuado e preenchimento."""
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
        Segment(p1=(0.0, 0.0), p2=(30.0, 40.0), layer="PAREDES"),
    ]
    return ExtractionResult(entities=ents, page_width=595.0, page_height=842.0,
                            layers={"PAREDES", "COTAS", "TEXTO"})


def main() -> None:
    os.makedirs(PASTA, exist_ok=True)
    r = amostra()
    a = classify(r.entities)
    indices = list(range(len(r.entities)))
    dados = packing.empacotar(r, a, indices)

    with open(os.path.join(PASTA, "geometria_exemplo.bin"), "wb") as f:
        f.write(dados)

    lido = packing.desempacotar(dados)
    esperado = {
        "n": lido["n"],
        "layers": a.layers,
        "n_groups": a.n_groups,
        "idx": lido["idx"],
        "kind": lido["kind"],
        "layer_id": lido["layer_id"],
        "is_fill": lido["is_fill"],
        "length_um": lido["length_um"],
        "dup_group": lido["dup_group"],
        "byte_cost": lido["byte_cost"],
        "cor": lido["cor"],
        "coordenadas": [[round(v, 4) for v in lido["coords_de"](i)]
                        for i in range(lido["n"])],
        "textos": [lido["texto_de"](i) for i in range(lido["n"])],
    }
    caminho = os.path.join(PASTA, "geometria_exemplo.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(esperado, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"fixture gerada: {lido['n']} entidades, {len(dados)} bytes")


if __name__ == "__main__":
    main()
