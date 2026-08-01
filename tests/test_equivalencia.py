"""Prova que classify()+select() reproduz apply_filters() em todos os casos.

Trava temporária: existe só para autorizar a remoção de apply_filters() na
tarefa 5 do plano do núcleo. Removida junto com ela.
"""

import itertools
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.geometry import Arc, Polyline, Segment, TextItem
from pdftodxf.optimize import (ExportOptions, apply_filters, apply_selection,
                               classify, select)

LAYERS = ["0", "PAREDES", "COTAS", "HACHURA"]
CORES = [None, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]


def gerar_entidades(n, semente):
    """Entidades aleatórias com muita repetição, para o dedup ter o que fazer."""
    rnd = random.Random(semente)
    ents = []
    for _ in range(n):
        layer = rnd.choice(LAYERS)
        cor = rnd.choice(CORES)
        fill = rnd.random() < 0.3
        tipo = rnd.random()
        if tipo < 0.75:
            # grade 3x3 (9 pontos, 36 pares) x 4 layers x 3 cores = 432 chaves
            # possiveis para ~225 segmentos: colisoes ficam comuns
            x1, y1, x2, y2 = (rnd.randrange(0, 3) for _ in range(4))
            if rnd.random() < 0.5:
                x1, y1, x2, y2 = x2, y2, x1, y1  # ponta invertida
            ents.append(Segment(p1=(float(x1), float(y1)), p2=(float(x2), float(y2)),
                                layer=layer, color=cor, is_fill=fill))
        elif tipo < 0.85:
            pts = [(float(rnd.randrange(0, 6)), float(rnd.randrange(0, 6)))
                   for _ in range(rnd.randrange(2, 6))]
            ents.append(Polyline(points=pts, layer=layer, color=cor, is_fill=fill))
        elif tipo < 0.95:
            ents.append(Arc(center=(0.0, 0.0), radius=float(rnd.randrange(1, 9)),
                            start_angle=0.0, end_angle=90.0,
                            layer=layer, color=cor, is_fill=fill))
        else:
            ents.append(TextItem(text="T", position=(0.0, 0.0), height=2.0,
                                 layer=layer, color=cor, is_fill=fill))
    return ents


def todas_as_opcoes():
    """Produto cartesiano dos filtros que select() e apply_filters() cobrem."""
    excluidos = [set(), {"HACHURA"}, {"COTAS", "HACHURA"}, set(LAYERS)]
    for exc, fills, micro, dedup in itertools.product(
            excluidos, [False, True], [0.0, 0.5, 2.0], [False, True]):
        yield ExportOptions(excluded_layers=exc, drop_fills=fills,
                            min_len_mm=micro, dedup=dedup)


def test_equivalencia():
    total = 0
    for semente in range(20):
        ents = gerar_entidades(300, semente)
        attrs = classify(ents)
        for opts in todas_as_opcoes():
            antigo = apply_filters(ents, opts)
            novo = apply_selection(ents, select(attrs, opts))
            assert len(antigo) == len(novo), (
                f"semente {semente} opts {opts}: "
                f"apply_filters deu {len(antigo)}, select deu {len(novo)}")
            for a, b in zip(antigo, novo):
                assert a is b, (
                    f"semente {semente} opts {opts}: entidades diferentes")
            total += 1
    print(f"OK: equivalência em {total} combinações")


if __name__ == "__main__":
    test_equivalencia()
    print("select() reproduz apply_filters() exatamente.")
