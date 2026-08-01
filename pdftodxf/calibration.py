"""Cálculo do fator de escala: pontos de papel (1/72") → unidade real."""

from __future__ import annotations

import math

PT_TO_MM = 25.4 / 72.0  # 1 pt em milímetros de papel

# Código $INSUNITS do DXF por unidade de saída
INSUNITS = {"mm": 4, "cm": 5, "m": 6}

# Quantos mm reais valem 1 unidade de saída
MM_PER_UNIT = {"mm": 1.0, "cm": 10.0, "m": 1000.0}


def scale_from_two_points(p1: tuple[float, float], p2: tuple[float, float],
                          real_dist: float) -> float:
    """Fator = distância real / distância no papel (em pts).

    `real_dist` já na unidade de saída desejada (ex.: 3.50 se for metros).
    """
    paper = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if paper < 1e-9:
        raise ValueError("Os dois pontos de calibração coincidem.")
    if real_dist <= 0:
        raise ValueError("A medida real deve ser positiva.")
    return real_dist / paper


def scale_from_plot_scale(ratio: float, unit: str = "m") -> float:
    """Fator para escala de plotagem 1:`ratio` com saída na `unit` dada.

    Ex.: 1:50 em metros → 1 pt = 0.3528 mm papel = 17.64 mm reais = 0.01764 m.
    """
    if ratio <= 0:
        raise ValueError("A escala deve ser positiva (ex.: 50 para 1:50).")
    if unit not in MM_PER_UNIT:
        raise ValueError(f"Unidade desconhecida: {unit!r} (use mm, cm ou m).")
    return PT_TO_MM * ratio / MM_PER_UNIT[unit]
