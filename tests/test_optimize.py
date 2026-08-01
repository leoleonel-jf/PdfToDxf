"""Testes das otimizações de exportação (filtros, dedup, junção, estimativa)."""

import os
import sys
import tempfile

import ezdxf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.calibration import PT_TO_MM
from pdftodxf.dxf_writer import export_dxf
from pdftodxf.extractor import ExtractionResult
from pdftodxf.geometry import Polyline, Segment, TextItem
from pdftodxf.optimize import (EntityAttrs, ExportOptions, apply_selection,
                               classify, estimate_bytes, join_segments,
                               select)


def seg(x1, y1, x2, y2, layer="0", color=None, is_fill=False):
    return Segment(p1=(x1, y1), p2=(x2, y2), layer=layer, color=color,
                   is_fill=is_fill)


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


def estimar(ents, opts):
    a = classify(ents)
    return estimate_bytes(a, select(a, opts), opts)


def test_estimate_monotonic():
    ents = [seg(i, 0, i + 1, 0) for i in range(1000)]
    base = estimar(ents, ExportOptions())
    joined = estimar(ents, ExportOptions(join_polylines=True))
    rounded = estimar(ents, ExportOptions(round_coords=True))
    both = estimar(ents, ExportOptions(join_polylines=True, round_coords=True))
    assert joined < base and rounded < base and both < joined
    print("OK: estimativa monotônica")


def test_estimate_ignora_descartados():
    ents = [seg(0, 0, 1, 0, layer="A"), seg(0, 0, 1, 0, layer="B")]
    inteiro = estimar(ents, ExportOptions())
    metade = estimar(ents, ExportOptions(excluded_layers={"B"}))
    assert metade == inteiro - 210, (inteiro, metade)
    print("OK: estimativa ignora quem foi descartado")


def test_estimate_soma_custo_de_polilinha():
    ents = [Polyline(points=[(0, 0), (1, 0), (1, 1)])]
    a = classify(ents)
    vazio = estimate_bytes(a, [False], ExportOptions())
    cheio = estimate_bytes(a, [True], ExportOptions())
    assert cheio - vazio == 180 + 42 * 3, (vazio, cheio)
    print("OK: estimativa cobra polilinha por vértice")


def test_classify_layers():
    ents = [seg(0, 0, 1, 0, layer="A"), seg(0, 0, 1, 0, layer="B"),
            seg(0, 0, 1, 0, layer="A")]
    a = classify(ents)
    assert a.layers == ["A", "B"], a.layers
    assert a.layer_id == [0, 1, 0], a.layer_id
    print("OK: classify indexa layers")


def test_classify_length_mm():
    ents = [seg(0, 0, 1 / PT_TO_MM, 0), TextItem(text="x", position=(0, 0))]
    a = classify(ents)
    assert abs(a.length_mm[0] - 1.0) < 1e-9, a.length_mm
    assert a.length_mm[1] == 0.0
    print("OK: classify mede comprimento em mm")


def test_classify_dup_group():
    ents = [seg(0, 0, 1, 1),                    # 0
            seg(0, 0, 1, 1),                    # 1 duplicado exato
            seg(1, 1, 0, 0),                    # 2 duplicado invertido
            seg(0, 0, 2, 2),                    # 3 diferente
            seg(0, 0, 1, 1, layer="X"),         # 4 outro layer
            seg(0, 0, 1, 1, color=(1, 0, 0))]   # 5 outra cor
    a = classify(ents)
    assert a.dup_group[0] == a.dup_group[1] == a.dup_group[2]
    assert len({a.dup_group[0], a.dup_group[3], a.dup_group[4],
                a.dup_group[5]}) == 4
    assert a.n_groups == 4, a.n_groups
    print("OK: classify agrupa duplicatas")


def test_classify_nao_segmento_sem_grupo():
    ents = [TextItem(text="x", position=(0, 0)), seg(0, 0, 1, 0)]
    a = classify(ents)
    assert a.dup_group[0] == -1
    assert a.dup_group[1] >= 0
    print("OK: classify não agrupa quem não é segmento")


def test_classify_byte_cost():
    ents = [seg(0, 0, 1, 0),
            Polyline(points=[(0, 0), (1, 0), (1, 1)]),
            TextItem(text="x", position=(0, 0))]
    a = classify(ents)
    assert a.byte_cost[0] == 210, a.byte_cost
    assert a.byte_cost[1] == 180 + 42 * 3, a.byte_cost
    assert a.byte_cost[2] == 330, a.byte_cost
    print("OK: classify calcula custo em bytes")


def filtrar(ents, opts):
    """Atalho: classifica, seleciona e devolve as entidades que sobraram."""
    a = classify(ents)
    return apply_selection(ents, select(a, opts))


def test_select_layers():
    ents = [seg(0, 0, 1, 0, layer="A"), seg(0, 0, 1, 0, layer="B")]
    out = filtrar(ents, ExportOptions(excluded_layers={"B"}))
    assert len(out) == 1 and out[0].layer == "A"
    print("OK: select exclui layers")


def test_select_fills():
    ents = [seg(0, 0, 1, 0), seg(0, 0, 2, 0, is_fill=True)]
    out = filtrar(ents, ExportOptions(drop_fills=True))
    assert len(out) == 1 and not out[0].is_fill
    print("OK: select remove preenchimentos")


def test_select_micro():
    small = 0.05 / PT_TO_MM
    big = 5.0 / PT_TO_MM
    ents = [seg(0, 0, small, 0), seg(0, 0, big, 0)]
    out = filtrar(ents, ExportOptions(min_len_mm=0.1))
    assert len(out) == 1 and out[0].p2[0] == big
    out = filtrar(ents, ExportOptions(min_len_mm=0.0))
    assert len(out) == 2
    print("OK: select descarta micro-segmentos")


def test_select_dedup():
    ents = [seg(0, 0, 1, 1), seg(0, 0, 1, 1), seg(1, 1, 0, 0),
            seg(0, 0, 2, 2), seg(0, 0, 1, 1, layer="X")]
    out = filtrar(ents, ExportOptions(dedup=True))
    assert len(out) == 3, f"esperava 3, veio {len(out)}"
    print("OK: select deduplica sobrepostos")


def test_select_dedup_elege_o_primeiro_sobrevivente():
    # o primeiro do grupo é preenchimento; com drop_fills ligado quem deve
    # sobreviver é o segundo, e não os dois nem nenhum
    ents = [seg(0, 0, 1, 1, is_fill=True), seg(0, 0, 1, 1)]
    out = filtrar(ents, ExportOptions(dedup=True, drop_fills=True))
    assert len(out) == 1 and not out[0].is_fill
    # sem drop_fills, o primeiro do grupo é que fica
    out = filtrar(ents, ExportOptions(dedup=True))
    assert len(out) == 1 and out[0].is_fill
    print("OK: select elege o primeiro sobrevivente do grupo")


def test_select_dedup_nao_afeta_outros_tipos():
    t1 = TextItem(text="x", position=(0, 0))
    t2 = TextItem(text="x", position=(0, 0))
    out = filtrar([t1, t2], ExportOptions(dedup=True))
    assert len(out) == 2
    print("OK: dedup não mexe em quem não é segmento")


def test_select_preserva_ordem():
    ents = [seg(i, 0, i + 1, 0) for i in range(5)]
    out = filtrar(ents, ExportOptions())
    assert [e.p1[0] for e in out] == [0, 1, 2, 3, 4]
    print("OK: select preserva a ordem original")


def _resumo_dxf(path):
    """Resumo comparável do DXF: tipo, layer e geometria de cada entidade.

    Não compara os bytes do arquivo porque o cabeçalho traz carimbo de data e
    GUIDs, que mudam a cada gravação.
    """
    doc = ezdxf.readfile(path)
    resumo = []
    for e in doc.modelspace():
        t = e.dxftype()
        if t == "LINE":
            resumo.append((t, e.dxf.layer, tuple(e.dxf.start)[:2],
                           tuple(e.dxf.end)[:2]))
        elif t == "LWPOLYLINE":
            resumo.append((t, e.dxf.layer,
                           tuple((p[0], p[1]) for p in e.get_points())))
        elif t == "TEXT":
            resumo.append((t, e.dxf.layer, e.dxf.text,
                           tuple(e.dxf.insert)[:2]))
        else:
            resumo.append((t, e.dxf.layer))
    return resumo


def test_export_dxf_aceita_attrs_prontos():
    """Passar as etiquetas prontas dá exatamente o mesmo DXF que deixar
    o export_dxf() chamar classify() por conta própria."""
    ents = [seg(0, 0, 10, 0),                       # duplicata do próximo
            seg(0, 0, 10, 0),
            seg(0, 0, 0.05 / PT_TO_MM, 0),          # micro-segmento
            seg(0, 0, 5, 0, layer="B"),
            seg(0, 0, 5, 5, is_fill=True),
            Polyline(points=[(0, 0), (1, 0), (1, 1)]),
            TextItem(text="oi", position=(2, 2), height=2.0)]
    result = ExtractionResult(entities=ents, page_width=100.0,
                              page_height=100.0,
                              layers={e.layer for e in ents})
    opts = ExportOptions(excluded_layers={"B"}, drop_fills=True,
                         min_len_mm=0.1, dedup=True, join_polylines=True,
                         round_coords=True)
    tmp = tempfile.mkdtemp()
    sem_path = os.path.join(tmp, "sem_attrs.dxf")
    com_path = os.path.join(tmp, "com_attrs.dxf")

    sem = export_dxf(result, sem_path, scale=2.0, unit="mm", opts=opts)
    com = export_dxf(result, com_path, scale=2.0, unit="mm", opts=opts,
                     attrs=classify(ents))

    assert sem == com, (sem, com)
    assert _resumo_dxf(sem_path) == _resumo_dxf(com_path)
    assert sem, "o DXF de controle saiu vazio — o teste não provaria nada"
    print("OK: export_dxf reaproveita as etiquetas prontas")


if __name__ == "__main__":
    test_join_chain()
    test_join_closed()
    test_join_respects_layer_color()
    test_join_preserves_non_segments()
    test_estimate_monotonic()
    test_estimate_ignora_descartados()
    test_estimate_soma_custo_de_polilinha()
    test_classify_layers()
    test_classify_length_mm()
    test_classify_dup_group()
    test_classify_nao_segmento_sem_grupo()
    test_classify_byte_cost()
    test_select_layers()
    test_select_fills()
    test_select_micro()
    test_select_dedup()
    test_select_dedup_elege_o_primeiro_sobrevivente()
    test_select_dedup_nao_afeta_outros_tipos()
    test_select_preserva_ordem()
    test_export_dxf_aceita_attrs_prontos()
    print("Todos os testes de otimização passaram.")
