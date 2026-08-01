"""Testes das otimizações de exportação (filtros, dedup, junção, estimativa)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.calibration import PT_TO_MM
from pdftodxf.geometry import Polyline, Segment, TextItem
from pdftodxf.optimize import (ExportOptions, apply_filters, estimate_bytes,
                               join_segments)


def seg(x1, y1, x2, y2, layer="0", color=None, is_fill=False):
    return Segment(p1=(x1, y1), p2=(x2, y2), layer=layer, color=color,
                   is_fill=is_fill)


def test_filter_layers():
    ents = [seg(0, 0, 1, 0, layer="A"), seg(0, 0, 1, 0, layer="B")]
    out = apply_filters(ents, ExportOptions(excluded_layers={"B"}))
    assert len(out) == 1 and out[0].layer == "A"
    print("OK: filtro de layers")


def test_filter_fills():
    ents = [seg(0, 0, 1, 0), seg(0, 0, 1, 0, is_fill=True)]
    out = apply_filters(ents, ExportOptions(drop_fills=True))
    assert len(out) == 1 and not out[0].is_fill
    print("OK: filtro de preenchimentos")


def test_filter_micro():
    small = 0.05 / PT_TO_MM  # 0.05 mm em pts
    big = 5.0 / PT_TO_MM
    ents = [seg(0, 0, small, 0), seg(0, 0, big, 0)]
    out = apply_filters(ents, ExportOptions(min_len_mm=0.1))
    assert len(out) == 1 and out[0].p2[0] == big
    # limiar 0 desliga o filtro
    out = apply_filters(ents, ExportOptions(min_len_mm=0.0))
    assert len(out) == 2
    print("OK: filtro de micro-segmentos")


def test_dedup():
    ents = [seg(0, 0, 1, 1), seg(0, 0, 1, 1),      # duplicado exato
            seg(1, 1, 0, 0),                        # duplicado invertido
            seg(0, 0, 2, 2),                        # diferente
            seg(0, 0, 1, 1, layer="X")]             # mesmo traço, outro layer
    out = apply_filters(ents, ExportOptions(dedup=True))
    assert len(out) == 3, f"esperava 3, veio {len(out)}"
    print("OK: dedup de sobrepostos")


def test_join_chain():
    # 3 segmentos encadeados em L + 1 isolado
    ents = [seg(0, 0, 1, 0), seg(1, 0, 1, 1), seg(1, 1, 2, 1),
            seg(10, 10, 11, 10)]
    out = join_segments(ents)
    polys = [e for e in out if isinstance(e, Polyline)]
    segs = [e for e in out if isinstance(e, Segment)]
    assert len(polys) == 1 and len(segs) == 1
    assert len(polys[0].points) == 4
    assert polys[0].points[0] == (0, 0) and polys[0].points[-1] == (2, 1)
    assert not polys[0].closed
    print("OK: junção em cadeia aberta")


def test_join_closed():
    # quadrado fechado
    ents = [seg(0, 0, 1, 0), seg(1, 0, 1, 1), seg(1, 1, 0, 1), seg(0, 1, 0, 0)]
    out = join_segments(ents)
    assert len(out) == 1 and isinstance(out[0], Polyline)
    assert out[0].closed and len(out[0].points) == 4
    print("OK: junção em cadeia fechada")


def test_join_respects_layer_color():
    # mesmo ponto de emenda, layers diferentes: não pode unir
    ents = [seg(0, 0, 1, 0, layer="A"), seg(1, 0, 2, 0, layer="B")]
    out = join_segments(ents)
    assert all(isinstance(e, Segment) for e in out) and len(out) == 2
    print("OK: junção não mistura layers")


def test_join_preserves_non_segments():
    t = TextItem(text="oi", position=(0, 0))
    ents = [seg(0, 0, 1, 0), t]
    out = join_segments(ents)
    assert t in out
    print("OK: junção preserva outros tipos")


def test_estimate_monotonic():
    ents = [seg(i, 0, i + 1, 0) for i in range(1000)]
    base = estimate_bytes(ents, ExportOptions())
    joined = estimate_bytes(ents, ExportOptions(join_polylines=True))
    rounded = estimate_bytes(ents, ExportOptions(round_coords=True))
    both = estimate_bytes(ents, ExportOptions(join_polylines=True, round_coords=True))
    assert joined < base and rounded < base and both < joined
    print("OK: estimativa monotônica")


if __name__ == "__main__":
    test_filter_layers()
    test_filter_fills()
    test_filter_micro()
    test_dedup()
    test_join_chain()
    test_join_closed()
    test_join_respects_layer_color()
    test_join_preserves_non_segments()
    test_estimate_monotonic()
    print("Todos os testes de otimização passaram.")
