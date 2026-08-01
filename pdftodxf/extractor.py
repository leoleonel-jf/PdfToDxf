"""Extrai a geometria vetorial e o texto de uma página de PDF (PyMuPDF).

Saída: lista de entidades de `geometry.py` já em espaço Y-para-cima
(y' = altura_da_página - y), em pontos de papel (1/72").
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import fitz  # PyMuPDF

from .geometry import Arc, Bezier, Entity, Polyline, Segment, TextItem, bezier_to_arc


@dataclass
class ExtractionResult:
    entities: list[Entity] = field(default_factory=list)
    page_width: float = 0.0
    page_height: float = 0.0
    layers: set[str] = field(default_factory=set)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.entities:
            name = type(e).__name__
            out[name] = out.get(name, 0) + 1
        return out


def _color_name(rgb: tuple[float, float, float] | None) -> str:
    if rgb is None:
        return "COR_000000"
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb)
    return f"COR_{r:02X}{g:02X}{b:02X}"


def extract_page(pdf_path: str, page_number: int = 0, fit_arcs: bool = True,
                 arc_tol: float = 0.05) -> ExtractionResult:
    """Extrai desenhos vetoriais + texto da página (0-based) do PDF."""
    with fitz.open(pdf_path) as doc:
        page = doc[page_number]
        return _extract(page, fit_arcs=fit_arcs, arc_tol=arc_tol)


def _extract(page: fitz.Page, fit_arcs: bool, arc_tol: float) -> ExtractionResult:
    h = page.rect.height
    result = ExtractionResult(page_width=page.rect.width, page_height=h)

    def flip(p) -> tuple[float, float]:
        return (float(p.x), h - float(p.y))

    for path in page.get_drawings():
        color = path.get("color") or path.get("fill")
        layer = path.get("layer") or ""
        if not layer:
            layer = _color_name(color)
        result.layers.add(layer)
        # 'f'/'fs' = caminho com preenchimento (hachuras sólidas/triângulos)
        is_fill = path.get("type") in ("f", "fs")

        for item in path["items"]:
            kind = item[0]
            if kind == "l":  # linha
                result.entities.append(
                    Segment(p1=flip(item[1]), p2=flip(item[2]), layer=layer,
                            color=color, is_fill=is_fill))
            elif kind == "re":  # retângulo
                r = item[1]
                pts = [flip(fitz.Point(r.x0, r.y0)), flip(fitz.Point(r.x1, r.y0)),
                       flip(fitz.Point(r.x1, r.y1)), flip(fitz.Point(r.x0, r.y1))]
                result.entities.append(Polyline(points=pts, closed=True, layer=layer,
                                                color=color, is_fill=is_fill))
            elif kind == "qu":  # quadrilátero
                q = item[1]
                pts = [flip(q.ul), flip(q.ur), flip(q.lr), flip(q.ll)]
                result.entities.append(Polyline(points=pts, closed=True, layer=layer,
                                                color=color, is_fill=is_fill))
            elif kind == "c":  # Bézier cúbica
                bez = Bezier(p0=flip(item[1]), p1=flip(item[2]), p2=flip(item[3]),
                             p3=flip(item[4]), layer=layer, color=color, is_fill=is_fill)
                arc = bezier_to_arc(bez, tol=arc_tol) if fit_arcs else None
                result.entities.append(arc if arc is not None else bez)

    _extract_text(page, result)
    return result


def _extract_text(page: fitz.Page, result: ExtractionResult) -> None:
    h = page.rect.height
    text_layer = "TEXTO"
    data = page.get_text("dict")
    has_text = False
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            dx, dy = line.get("dir", (1.0, 0.0))
            # espaço Y-para-cima: inverte a componente Y da direção
            rotation = math.degrees(math.atan2(-dy, dx))
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                ox, oy = span.get("origin", (0.0, 0.0))
                # largura ocupada ao longo da linha de base (exata para
                # rotações de 0/90/180/270°, que cobrem plantas de CAD)
                bx0, by0, bx1, by1 = span.get("bbox", (0, 0, 0, 0))
                width = abs((bx1 - bx0) * dx) + abs((by1 - by0) * dy)
                result.entities.append(TextItem(
                    text=text,
                    position=(float(ox), h - float(oy)),
                    height=float(span.get("size", 1.0)) * 0.72,  # aprox. altura de caixa-alta
                    rotation=rotation,
                    width=width,
                    layer=text_layer,
                ))
                has_text = True
    if has_text:
        result.layers.add(text_layer)
