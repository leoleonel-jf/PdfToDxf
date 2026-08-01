"""Teste de ida-e-volta: gera um PDF vetorial sintético com medidas conhecidas,
converte para DXF e confere que a geometria bate (posição, escala, tipos)."""

import math
import os
import sys
import tempfile

import ezdxf
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.calibration import scale_from_plot_scale, scale_from_two_points
from pdftodxf.dxf_writer import write_dxf
from pdftodxf.extractor import extract_page

PAGE_W, PAGE_H = 595.0, 842.0  # A4 em pts

# Geometria de teste (coordenadas PDF, y para baixo)
LINE_P1, LINE_P2 = (100.0, 700.0), (400.0, 700.0)     # linha horizontal de 300 pt
RECT = fitz.Rect(100, 400, 250, 500)                  # 150 x 100 pt
CIRCLE_C, CIRCLE_R = fitz.Point(400, 300), 60.0


def make_test_pdf(path: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    shape = page.new_shape()
    shape.draw_line(fitz.Point(*LINE_P1), fitz.Point(*LINE_P2))
    shape.draw_rect(RECT)
    shape.draw_circle(CIRCLE_C, CIRCLE_R)
    shape.finish(color=(1, 0, 0), width=0.5)
    shape.commit()
    # curva Bézier que NÃO é arco de círculo -> deve virar SPLINE no DXF
    shape2 = page.new_shape()
    shape2.draw_bezier(fitz.Point(450, 600), fitz.Point(470, 520),
                       fitz.Point(530, 680), fitz.Point(550, 600))
    shape2.finish(color=(0, 0, 1), width=0.5, closePath=False)
    shape2.commit()
    page.insert_text(fitz.Point(120, 380), "350", fontsize=10)
    doc.save(path)
    doc.close()


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_roundtrip():
    tmp = tempfile.mkdtemp()
    pdf_path = os.path.join(tmp, "teste.pdf")
    dxf_path = os.path.join(tmp, "teste.dxf")
    make_test_pdf(pdf_path)

    result = extract_page(pdf_path)
    counts = result.counts()
    print("Extraido:", counts)
    assert counts.get("Segment", 0) >= 1, "linha nao extraida"
    assert counts.get("Polyline", 0) >= 1, "retangulo nao extraido"
    assert counts.get("Arc", 0) == 4, f"circulo deveria virar 4 arcos, veio {counts.get('Arc', 0)}"
    assert counts.get("TextItem", 0) == 1, "texto nao extraido"
    assert counts.get("Bezier", 0) == 1, "curva nao-circular deveria ficar como Bezier"

    # Calibração: a linha de 300 pt "mede" 3.00 m na planta
    seg = [e for e in result.entities if type(e).__name__ == "Segment"][0]
    scale = scale_from_two_points(seg.p1, seg.p2, 3.00)
    assert approx(scale, 0.01), f"fator esperado 0.01, veio {scale}"

    out_counts = write_dxf(result, dxf_path, scale=scale, unit="m")
    print("DXF:", out_counts)

    doc = ezdxf.readfile(dxf_path)
    auditor = doc.audit()
    assert not auditor.has_errors, f"DXF com erros: {auditor.errors}"
    msp = doc.modelspace()

    # Linha: y-flip -> y' = 842 - 700 = 142; escala 0.01
    lines = msp.query("LINE")
    assert len(lines) == 1
    ln = lines[0]
    got = sorted([(ln.dxf.start.x, ln.dxf.start.y), (ln.dxf.end.x, ln.dxf.end.y)])
    exp = sorted([(1.00, (PAGE_H - 700.0) * scale), (4.00, (PAGE_H - 700.0) * scale)])
    for (gx, gy), (ex, ey) in zip(got, exp):
        assert approx(gx, ex) and approx(gy, ey), f"linha: {got} != {exp}"
    # A medida calibrada confere: 3.00 m
    dist = math.hypot(ln.dxf.end.x - ln.dxf.start.x, ln.dxf.end.y - ln.dxf.start.y)
    assert approx(dist, 3.00), f"distancia calibrada {dist} != 3.00"

    # Retângulo: 150x100 pt -> 1.50 x 1.00 m
    polys = msp.query("LWPOLYLINE")
    assert len(polys) == 1
    pts = [(p[0], p[1]) for p in polys[0].get_points()]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert approx(max(xs) - min(xs), 1.50), f"largura ret {max(xs)-min(xs)}"
    assert approx(max(ys) - min(ys), 1.00), f"altura ret {max(ys)-min(ys)}"
    assert polys[0].closed

    # Círculo: 4 arcos com mesmo centro, raio 0.60 m e varredura de 90° cada
    arcs = msp.query("ARC")
    assert len(arcs) == 4
    exp_c = (CIRCLE_C.x * scale, (PAGE_H - CIRCLE_C.y) * scale)
    total_sweep = 0.0
    for a in arcs:
        assert approx(a.dxf.center.x, exp_c[0], 1e-3), f"centro x {a.dxf.center.x} != {exp_c[0]}"
        assert approx(a.dxf.center.y, exp_c[1], 1e-3), f"centro y {a.dxf.center.y} != {exp_c[1]}"
        assert approx(a.dxf.radius, 0.60, 1e-3), f"raio {a.dxf.radius} != 0.60"
        sweep = (a.dxf.end_angle - a.dxf.start_angle) % 360
        assert approx(sweep, 90.0, 1.0), f"varredura {sweep} != 90 (arco complementar!)"
        total_sweep += sweep
    assert approx(total_sweep, 360.0, 1.0), f"soma das varreduras {total_sweep} != 360"

    # Curva não-circular vira SPLINE com extremos corretos
    splines = msp.query("SPLINE")
    assert len(splines) == 1, f"esperava 1 SPLINE, veio {len(splines)}"
    cps = splines[0].control_points
    exp_start = (450 * scale, (PAGE_H - 600) * scale)
    exp_end = (550 * scale, (PAGE_H - 600) * scale)
    assert approx(cps[0][0], exp_start[0], 1e-6) and approx(cps[0][1], exp_start[1], 1e-6)
    assert approx(cps[-1][0], exp_end[0], 1e-6) and approx(cps[-1][1], exp_end[1], 1e-6)

    # Texto preservado, com alinhamento FIT ocupando a largura original do PDF
    texts = msp.query("TEXT")
    assert len(texts) == 1 and texts[0].dxf.text == "350"
    t = texts[0]
    ti = [e for e in result.entities if type(e).__name__ == "TextItem"][0]
    assert ti.width > 0, "largura do span nao extraida"
    assert t.dxf.halign == 5, f"esperava FIT (halign=5), veio {t.dxf.halign}"
    fit_w = math.hypot(t.dxf.align_point.x - t.dxf.insert.x,
                       t.dxf.align_point.y - t.dxf.insert.y)
    assert approx(fit_w, ti.width * scale, 1e-6), (
        f"largura FIT {fit_w} != {ti.width * scale}")

    # $INSUNITS = metros
    assert doc.header["$INSUNITS"] == 6

    print("OK: ida-e-volta com escala calibrada confere.")


def make_arc_bezier(cx, cy, r, a0_deg, sweep_deg):
    """Bézier padrão de arco circular (k = 4/3·tan(sweep/4))."""
    from pdftodxf.geometry import Bezier
    a0 = math.radians(a0_deg)
    a1 = math.radians(a0_deg + sweep_deg)
    k = 4 / 3 * math.tan((a1 - a0) / 4)
    p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
    p3 = (cx + r * math.cos(a1), cy + r * math.sin(a1))
    p1 = (p0[0] - k * r * math.sin(a0), p0[1] + k * r * math.cos(a0))
    p2 = (p3[0] + k * r * math.sin(a1), p3[1] - k * r * math.cos(a1))
    return Bezier(p0=p0, p1=p1, p2=p2, p3=p3)


def test_arc_sweep():
    """Todo arco reencaixado deve cobrir exatamente os pontos da Bézier
    (nunca o arco complementar), em qualquer quadrante e sentido."""
    from pdftodxf.geometry import bezier_to_arc, bezier_point

    for a0 in (0, 45, 90, 170, 260):
        for sweep in (30, 90, 120, -30, -90, -120):
            b = make_arc_bezier(10, 20, 5, a0, sweep)
            arc = bezier_to_arc(b, tol=0.05)
            assert arc is not None, f"a0={a0} sweep={sweep}: não reconhecido"
            asw = (arc.end_angle - arc.start_angle) % 360
            assert approx(asw, abs(sweep), 1.0), (
                f"a0={a0} sweep={sweep}: varredura DXF {asw:.1f} != {abs(sweep)}")
            for i in range(21):
                bx, by = bezier_point(b, i / 20)
                ang = math.degrees(math.atan2(by - arc.center[1],
                                              bx - arc.center[0])) % 360
                rel = (ang - arc.start_angle) % 360
                assert rel <= asw + 1e-6, (
                    f"a0={a0} sweep={sweep}: ponto t={i/20} fora do arco")
    print("OK: varredura dos arcos confere em todos os quadrantes/sentidos.")


def test_plot_scale():
    # 1:50 em metros: 1 pt = (25.4/72) mm papel * 50 = 17.6389 mm = 0.0176389 m
    s = scale_from_plot_scale(50, "m")
    assert approx(s, 25.4 / 72 * 50 / 1000, 1e-12)
    # 1:100 em cm
    s = scale_from_plot_scale(100, "cm")
    assert approx(s, 25.4 / 72 * 100 / 10, 1e-12)
    print("OK: escala de plotagem confere.")


if __name__ == "__main__":
    test_roundtrip()
    test_arc_sweep()
    test_plot_scale()
    print("Todos os testes passaram.")
