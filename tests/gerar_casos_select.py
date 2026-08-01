"""Gera tests/casos_select.json, o contrato entre o select() do Python e o do
navegador.

Rode depois de qualquer mudança em select() ou classify():

    python tests/gerar_casos_select.py

O arquivo gerado é versionado. Se ele mudar num commit que não pretendia mudar
comportamento, isso é um alerta, não um detalhe.
"""

import itertools
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.geometry import Arc, Polyline, Segment, TextItem
from pdftodxf.optimize import ExportOptions, classify, select

SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "casos_select.json")

LAYERS = ["0", "PAREDES", "COTAS", "HACHURA"]
CORES = [None, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]


def gerar_entidades(n, semente):
    """Entidades numa grade de 3x3, para produzir duplicatas em quantidade.

    A grade precisa ser pequena de propósito: 9 pontos dão 36 pares não
    ordenados que, multiplicados pelos 4 layers e 3 cores, somam 432 chaves
    possíveis para ~225 segmentos. Numa grade de 6x6 as colisões ficam raras e
    o caminho do dedup mal é exercitado.
    """
    rnd = random.Random(semente)
    ents = []
    for _ in range(n):
        layer = rnd.choice(LAYERS)
        cor = rnd.choice(CORES)
        fill = rnd.random() < 0.3
        tipo = rnd.random()
        if tipo < 0.75:
            x1, y1, x2, y2 = (float(rnd.randrange(0, 3)) for _ in range(4))
            if rnd.random() < 0.5:
                x1, y1, x2, y2 = x2, y2, x1, y1
            ents.append(Segment(p1=(x1, y1), p2=(x2, y2), layer=layer,
                                color=cor, is_fill=fill))
        elif tipo < 0.85:
            pts = [(float(rnd.randrange(0, 6)), float(rnd.randrange(0, 6)))
                   for _ in range(rnd.randrange(2, 6))]
            ents.append(Polyline(points=pts, layer=layer, color=cor, is_fill=fill))
        elif tipo < 0.95:
            ents.append(Arc(center=(0.0, 0.0), radius=3.0, start_angle=0.0,
                            end_angle=90.0, layer=layer, color=cor, is_fill=fill))
        else:
            ents.append(TextItem(text="T", position=(0.0, 0.0), height=2.0,
                                 layer=layer, color=cor, is_fill=fill))
    return ents


def opcoes_variadas():
    excluidos = [[], ["HACHURA"], ["COTAS", "HACHURA"], list(LAYERS)]
    for exc, fills, micro, dedup in itertools.product(
            excluidos, [False, True], [0.0, 0.5, 2.0], [False, True]):
        yield exc, fills, micro, dedup


def main():
    tabelas = []
    casos = []
    for semente in range(3):
        ents = gerar_entidades(300, semente)
        attrs = classify(ents)
        tabelas.append({
            "kind": attrs.kind,
            "layer_id": attrs.layer_id,
            "is_fill": attrs.is_fill,
            "length_mm": [round(v, 9) for v in attrs.length_mm],
            "dup_group": attrs.dup_group,
            "byte_cost": attrs.byte_cost,
            "layers": attrs.layers,
            "n_groups": attrs.n_groups,
        })
        for i, (exc, fills, micro, dedup) in enumerate(opcoes_variadas()):
            opts = ExportOptions(excluded_layers=set(exc), drop_fills=fills,
                                 min_len_mm=micro, dedup=dedup)
            casos.append({
                "nome": f"semente{semente}-opcao{i}",
                "tabela": semente,
                "opcoes": {
                    "excluded_layers": exc,
                    "drop_fills": fills,
                    "min_len_mm": micro,
                    "dedup": dedup,
                },
                "esperado": select(attrs, opts),
            })

    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump({"tabelas": tabelas, "casos": casos}, f, ensure_ascii=False,
                  indent=1, sort_keys=True)
        f.write("\n")
    print(f"{len(casos)} casos gravados em {SAIDA}")


if __name__ == "__main__":
    main()
