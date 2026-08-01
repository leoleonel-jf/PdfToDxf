"""Gera o arquivo DXF (R2010) a partir das entidades extraídas."""

from __future__ import annotations

import re

import math

import ezdxf
from ezdxf import colors as ezcolors
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Bezier4P, Vec3, bezier_to_bspline

from .calibration import INSUNITS
from .extractor import ExtractionResult
from .geometry import Arc, Bezier, Polyline, Segment, TextItem

_INVALID_LAYER_CHARS = re.compile(r'[<>/\\":;?*|=`]')


def _sanitize_layer(name: str) -> str:
    name = _INVALID_LAYER_CHARS.sub("_", name).strip()
    return name or "0"


def _true_color(rgb: tuple[float, float, float] | None) -> int | None:
    if rgb is None:
        return None
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb)
    return ezcolors.rgb2int((r, g, b))


def write_dxf(result: ExtractionResult, output_path: str, scale: float = 1.0,
              unit: str = "m", entities=None,
              round_decimals: int | None = None) -> dict[str, int]:
    """Escreve o DXF aplicando o fator de escala. Retorna contagem por tipo.

    entities: lista alternativa (já filtrada/otimizada); default result.entities.
    round_decimals: arredonda coordenadas (casas decimais na unidade de saída).
    """
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = INSUNITS.get(unit, 6)
    msp = doc.modelspace()

    ent_list = result.entities if entities is None else entities
    used_layers = {e.layer for e in ent_list}
    layer_names: dict[str, str] = {}
    for layer in sorted(used_layers):
        safe = _sanitize_layer(layer)
        layer_names[layer] = safe
        if safe != "0" and safe not in doc.layers:
            doc.layers.add(safe)

    if round_decimals is None:
        def s(p: tuple[float, float]) -> tuple[float, float]:
            return (p[0] * scale, p[1] * scale)
    else:
        nd = round_decimals

        def s(p: tuple[float, float]) -> tuple[float, float]:
            return (round(p[0] * scale, nd), round(p[1] * scale, nd))

    counts: dict[str, int] = {}

    def attribs(e) -> dict:
        d = {"layer": layer_names.get(e.layer, "0")}
        tc = _true_color(e.color)
        if tc is not None:
            d["true_color"] = tc
        return d

    for e in ent_list:
        if isinstance(e, Segment):
            msp.add_line(s(e.p1), s(e.p2), dxfattribs=attribs(e))
            key = "LINE"
        elif isinstance(e, Polyline):
            msp.add_lwpolyline([s(p) for p in e.points], close=e.closed,
                               dxfattribs=attribs(e))
            key = "LWPOLYLINE"
        elif isinstance(e, Arc):
            if abs(((e.end_angle - e.start_angle) % 360.0)) < 1e-9:
                msp.add_circle(s(e.center), e.radius * scale, dxfattribs=attribs(e))
                key = "CIRCLE"
            else:
                msp.add_arc(s(e.center), e.radius * scale, e.start_angle,
                            e.end_angle, dxfattribs=attribs(e))
                key = "ARC"
        elif isinstance(e, Bezier):
            # Vec3 obrigatório: com tuplas, o Bezier4P acelerado (Cython) do
            # ezdxf 1.4.4 quebra ao emitir o aviso de deprecação
            bez = Bezier4P([Vec3(*s(e.p0)), Vec3(*s(e.p1)),
                            Vec3(*s(e.p2)), Vec3(*s(e.p3))])
            spline = msp.add_spline(dxfattribs=attribs(e))
            spline.apply_construction_tool(bezier_to_bspline([bez]))
            key = "SPLINE"
        elif isinstance(e, TextItem):
            txt = msp.add_text(e.text, dxfattribs={
                **attribs(e),
                "height": e.height * scale,
                "rotation": e.rotation,
            })
            if e.width > 1e-6:
                # FIT: estica/comprime o texto para ocupar exatamente a mesma
                # largura do PDF, independente da fonte usada pelo CAD
                rad = math.radians(e.rotation)
                p2 = (e.position[0] + e.width * math.cos(rad),
                      e.position[1] + e.width * math.sin(rad))
                txt.set_placement(s(e.position), s(p2),
                                  align=TextEntityAlignment.FIT)
            else:
                txt.set_placement(s(e.position))
            key = "TEXT"
        else:
            continue
        counts[key] = counts.get(key, 0) + 1

    doc.saveas(output_path)
    return counts


def export_dxf(result: ExtractionResult, output_path: str, scale: float,
               unit: str, opts) -> dict[str, int]:
    """Pipeline completo: filtros -> junção -> escrita, conforme ExportOptions."""
    from .optimize import apply_filters, join_segments

    entities = apply_filters(result.entities, opts)
    if opts.join_polylines:
        entities = join_segments(entities)
    decimals = 4 if opts.round_coords else None
    return write_dxf(result, output_path, scale=scale, unit=unit,
                     entities=entities, round_decimals=decimals)


def convert(pdf_path: str, output_path: str, scale: float, unit: str = "m",
            page_number: int = 0) -> dict[str, int]:
    """Conveniência: extrai a página e grava o DXF em um passo."""
    from .extractor import extract_page

    result = extract_page(pdf_path, page_number=page_number)
    return write_dxf(result, output_path, scale=scale, unit=unit)
