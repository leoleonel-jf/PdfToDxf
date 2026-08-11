"""Gera a fixture que prova a intercalação do frontend.

A pergunta que ela responde: dividir em esqueleto e detalhe, intercalar de volta
e rodar o select() dá o mesmo que rodar o select() sobre a lista inteira? Com
dedup ligado, só dá se a intercalação restaurar a ordem original.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.geometry import Segment, TextItem
from pdftodxf.optimize import ExportOptions, classify, select
from web.api import packing

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def amostra():
    """Segmentos com comprimentos variados e duplicatas fartas.

    Os comprimentos alternam para que o `dividir()` espalhe membros do mesmo
    grupo de duplicatas entre as duas partes — que é o caso que interessa.
    """
    ents = []
    for i in range(400):
        comprido = (i % 3 == 0)
        alvo = 40.0 if comprido else 2.0
        # `i % 40` faz pares distantes na lista compartilharem coordenadas,
        # e portanto o grupo de duplicatas.
        x = float(i % 40)
        ents.append(Segment(p1=(x, 0.0), p2=(x, alvo), layer="PAREDES"))
    ents.append(TextItem(text="planta", position=(1.0, 1.0), layer="TEXTO"))
    return ents


def main() -> None:
    os.makedirs(PASTA, exist_ok=True)
    ents = amostra()
    a = classify(ents)
    esqueleto, detalhe, limiar = packing.dividir(a, alvo=60)
    assert esqueleto and detalhe, "a divisão precisa produzir as duas partes"

    opcoes = {"excluded_layers": [], "drop_fills": False, "min_len_mm": 0.0,
              "dedup": True, "join_polylines": False, "round_coords": False}
    opts = ExportOptions(excluded_layers=set(), drop_fills=False,
                         min_len_mm=0.0, dedup=True, join_polylines=False,
                         round_coords=False)
    mascara = select(a, opts)

    fixture = {
        "layers": a.layers,
        "n_groups": a.n_groups,
        "limiar_um": limiar,
        "esqueleto": esqueleto,
        "detalhe": detalhe,
        "opcoes": opcoes,
        "mascara_esperada": "".join("1" if v else "0" for v in mascara),
        "kind": a.kind,
        "layer_id": a.layer_id,
        "is_fill": [bool(v) for v in a.is_fill],
        "length_um": a.length_um,
        "dup_group": a.dup_group,
        "byte_cost": a.byte_cost,
    }
    with open(os.path.join(PASTA, "intercalacao.json"), "w",
              encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=1, sort_keys=True)

    cruzam = sum(1 for g in set(a.dup_group) if g >= 0
                 and any(a.dup_group[i] == g for i in esqueleto)
                 and any(a.dup_group[i] == g for i in detalhe))
    print(f"fixture gerada: {len(ents)} entidades, esqueleto {len(esqueleto)}, "
          f"detalhe {len(detalhe)}, {cruzam} grupos atravessando as duas partes")
    assert cruzam > 0, (
        "nenhum grupo de duplicatas ficou dividido entre as partes: a fixture "
        "não exercita o que se propõe a exercitar")


if __name__ == "__main__":
    main()
