"""Tipos geométricos intermediários e reencaixe de arcos a partir de Béziers.

Todas as coordenadas aqui já estão em espaço "Y para cima" (padrão CAD),
em pontos de papel (1 pt = 1/72"). A conversão de eixo é feita no extractor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

Point = tuple[float, float]


@dataclass
class Entity:
    layer: str = "0"
    color: tuple[float, float, float] | None = None  # RGB 0..1
    is_fill: bool = False  # veio de um caminho de preenchimento (hachura sólida)


@dataclass
class Segment(Entity):
    p1: Point = (0.0, 0.0)
    p2: Point = (0.0, 0.0)


@dataclass
class Polyline(Entity):
    points: list[Point] = field(default_factory=list)
    closed: bool = False


@dataclass
class Bezier(Entity):
    """Bézier cúbica: p0 (início), p1/p2 (controles), p3 (fim)."""

    p0: Point = (0.0, 0.0)
    p1: Point = (0.0, 0.0)
    p2: Point = (0.0, 0.0)
    p3: Point = (0.0, 0.0)


@dataclass
class Arc(Entity):
    center: Point = (0.0, 0.0)
    radius: float = 0.0
    start_angle: float = 0.0  # graus, CCW a partir do eixo X
    end_angle: float = 0.0


@dataclass
class TextItem(Entity):
    text: str = ""
    position: Point = (0.0, 0.0)  # início da linha de base
    height: float = 1.0
    rotation: float = 0.0  # graus
    width: float = 0.0  # largura ocupada no papel (pts), ao longo da linha de base


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bezier_point(b: Bezier, t: float) -> Point:
    """Avalia a Bézier cúbica no parâmetro t."""
    mt = 1.0 - t
    x = (
        mt * mt * mt * b.p0[0]
        + 3 * mt * mt * t * b.p1[0]
        + 3 * mt * t * t * b.p2[0]
        + t * t * t * b.p3[0]
    )
    y = (
        mt * mt * mt * b.p0[1]
        + 3 * mt * mt * t * b.p1[1]
        + 3 * mt * t * t * b.p2[1]
        + t * t * t * b.p3[1]
    )
    return (x, y)


def _circle_from_3_points(a: Point, b: Point, c: Point) -> tuple[Point, float] | None:
    """Círculo passando por 3 pontos. None se forem colineares."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    center = (ux, uy)
    return center, _dist(center, a)


def bezier_to_arc(b: Bezier, tol: float = 0.05, samples: int = 9) -> Arc | None:
    """Tenta reconhecer a Bézier como arco circular (caso comum em plots de CAD).

    Ajusta um círculo pelos extremos + ponto médio e verifica se todos os
    pontos amostrados ficam a menos de `tol` (em pts de papel) do raio.
    Retorna um Arc (ângulos CCW, convenção DXF) ou None.
    """
    chord = _dist(b.p0, b.p3)
    if chord < 1e-9:
        return None  # possivelmente círculo completo degenerado; manter como spline
    fit = _circle_from_3_points(b.p0, bezier_point(b, 0.5), b.p3)
    if fit is None:
        return None
    center, radius = fit
    if radius < 1e-9:
        return None
    for i in range(1, samples + 1):
        t = i / (samples + 1)
        if abs(_dist(center, bezier_point(b, t)) - radius) > tol:
            return None

    a0 = math.degrees(math.atan2(b.p0[1] - center[1], b.p0[0] - center[0]))
    a1 = math.degrees(math.atan2(b.p3[1] - center[1], b.p3[0] - center[0]))
    # Sentido da curva: o ponto médio do arco fica do lado oposto ao centro em
    # relação à corda p0->p3. Se cross(corda, mid-p0) < 0, o arco é CCW.
    mid = bezier_point(b, 0.5)
    cross = (b.p3[0] - b.p0[0]) * (mid[1] - b.p0[1]) - (b.p3[1] - b.p0[1]) * (mid[0] - b.p0[0])
    if cross < 0:  # CCW: start=a0, end=a1
        return Arc(center=center, radius=radius, start_angle=a0 % 360.0, end_angle=a1 % 360.0,
                   layer=b.layer, color=b.color)
    # CW: DXF exige CCW, então invertemos os ângulos
    return Arc(center=center, radius=radius, start_angle=a1 % 360.0, end_angle=a0 % 360.0,
               layer=b.layer, color=b.color)
