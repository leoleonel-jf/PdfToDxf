"""Redução do DXF: filtros, deduplicação, junção em polilinhas e estimativa.

Todas as funções são puras (recebem/retornam listas de entidades de geometry.py,
coordenadas em pts de papel, Y para cima).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .calibration import PT_TO_MM
from .geometry import Arc, Bezier, Entity, Polyline, Segment, TextItem


@dataclass
class ExportOptions:
    """Opções de exportação/compactação escolhidas pelo usuário."""

    excluded_layers: set[str] = field(default_factory=set)
    drop_fills: bool = False           # remover preenchimentos (hachuras sólidas)
    min_len_mm: float = 0.0            # descartar segmentos menores que isso (mm de papel); 0 = off
    dedup: bool = False                # remover segmentos duplicados/sobrepostos
    join_polylines: bool = False       # unir segmentos encadeados em LWPOLYLINE
    round_coords: bool = False         # arredondar coordenadas na escrita


# bytes aproximados por entidade em DXF ASCII (medidos em arquivos reais)
_BYTES = {"Segment": 210, "Arc": 235, "Bezier": 620, "TextItem": 330}
_POLY_BASE = 180
_POLY_PER_PT = 42
_ROUND_FACTOR = 0.78  # arredondar coordenadas corta ~22% do tamanho


@dataclass
class EntityAttrs:
    """Etiquetas pré-calculadas, em arrays paralelos à lista de entidades.

    Produzidas uma única vez por `classify()` e consumidas por `select()` —
    tanto aqui quanto na versão TypeScript que roda no navegador. Guardar o
    julgamento caro como número é o que impede as duas implementações de
    divergirem.
    """

    kind: list[str] = field(default_factory=list)         # "Segment", "Arc", ...
    layer_id: list[int] = field(default_factory=list)     # índice em `layers`
    is_fill: list[bool] = field(default_factory=list)
    length_mm: list[float] = field(default_factory=list)  # 0.0 fora de Segment
    dup_group: list[int] = field(default_factory=list)    # -1 fora de Segment
    byte_cost: list[int] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    n_groups: int = 0

    def __len__(self) -> int:
        return len(self.kind)


def classify(entities: list[Entity]) -> EntityAttrs:
    """Fase cara: percorre as entidades uma vez e resume cada uma em números.

    O trabalho pesado é o `dup_group`: o conjunto de hash que descobre quais
    segmentos são o mesmo traço é montado aqui, uma única vez, e vira um
    inteiro por entidade.
    """
    attrs = EntityAttrs()
    layer_index: dict[str, int] = {}
    group_index: dict[tuple, int] = {}

    for e in entities:
        name = type(e).__name__

        lid = layer_index.get(e.layer)
        if lid is None:
            lid = len(attrs.layers)
            layer_index[e.layer] = lid
            attrs.layers.append(e.layer)

        if name == "Segment":
            length_mm = math.hypot(e.p2[0] - e.p1[0], e.p2[1] - e.p1[1]) * PT_TO_MM
            a = (round(e.p1[0], 3), round(e.p1[1], 3))
            b = (round(e.p2[0], 3), round(e.p2[1], 3))
            key = (e.layer, e.color, a, b) if a <= b else (e.layer, e.color, b, a)
            gid = group_index.get(key)
            if gid is None:
                gid = len(group_index)
                group_index[key] = gid
        else:
            length_mm = 0.0
            gid = -1

        if name == "Polyline":
            cost = _POLY_BASE + _POLY_PER_PT * len(e.points)
        else:
            cost = _BYTES.get(name, 300)

        attrs.kind.append(name)
        attrs.layer_id.append(lid)
        attrs.is_fill.append(e.is_fill)
        attrs.length_mm.append(length_mm)
        attrs.dup_group.append(gid)
        attrs.byte_cost.append(cost)

    attrs.n_groups = len(group_index)
    return attrs


def select(attrs: EntityAttrs, opts: ExportOptions) -> list[bool]:
    """Fase barata: decide quem entra, só comparando os números do classify().

    Sem hash e sem alocação por entidade — é esta função que é espelhada em
    TypeScript para a prévia do navegador. A ordem de varredura importa: dentro
    de um grupo de duplicatas, quem sobrevive é o primeiro que passa nos demais
    filtros.
    """
    excluded = {i for i, name in enumerate(attrs.layers)
                if name in opts.excluded_layers}
    emitted = bytearray(attrs.n_groups)
    mask = [False] * len(attrs)

    for i in range(len(attrs)):
        if attrs.layer_id[i] in excluded:
            continue
        if opts.drop_fills and attrs.is_fill[i]:
            continue
        if attrs.kind[i] == "Segment":
            if opts.min_len_mm > 0.0 and attrs.length_mm[i] < opts.min_len_mm:
                continue
            if opts.dedup:
                g = attrs.dup_group[i]
                if emitted[g]:
                    continue
                emitted[g] = 1
        mask[i] = True

    return mask


def apply_selection(entities: list[Entity], mask: list[bool]) -> list[Entity]:
    """Aplica a máscara do select() à lista original de entidades."""
    return [e for e, keep in zip(entities, mask) if keep]


def join_segments(entities: list[Entity]) -> list[Entity]:
    """Une segmentos encadeados (fim de um = início do outro) em Polylines.

    Agrupa por (layer, cor); segmentos isolados permanecem como Segment.
    A geometria não muda — só a representação (LWPOLYLINE é ~5x mais compacta).
    """
    others: list[Entity] = []
    groups: dict = {}
    for e in entities:
        if isinstance(e, Segment):
            groups.setdefault((e.layer, e.color), []).append(e)
        else:
            others.append(e)

    result: list[Entity] = others
    for (layer, color), segs in groups.items():
        n = len(segs)
        # endpoint -> lista de (índice do segmento, extremidade 0/1)
        point_map: dict = {}
        keys = []
        for i, s in enumerate(segs):
            ka = (round(s.p1[0], 3), round(s.p1[1], 3))
            kb = (round(s.p2[0], 3), round(s.p2[1], 3))
            keys.append((ka, kb))
            point_map.setdefault(ka, []).append((i, 0))
            point_map.setdefault(kb, []).append((i, 1))

        used = [False] * n

        def take_next(pt_key, exclude):
            """Próximo segmento não usado que toca pt_key."""
            for idx, end in point_map.get(pt_key, ()):
                if not used[idx] and idx != exclude:
                    return idx, end
            return None, None

        for i in range(n):
            if used[i]:
                continue
            used[i] = True
            chain = [segs[i].p1, segs[i].p2]
            chain_keys = [keys[i][0], keys[i][1]]
            # estende para frente
            while True:
                idx, end = take_next(chain_keys[-1], -1)
                if idx is None:
                    break
                used[idx] = True
                s = segs[idx]
                if end == 0:
                    chain.append(s.p2)
                    chain_keys.append(keys[idx][1])
                else:
                    chain.append(s.p1)
                    chain_keys.append(keys[idx][0])
            # estende para trás
            while True:
                idx, end = take_next(chain_keys[0], -1)
                if idx is None:
                    break
                used[idx] = True
                s = segs[idx]
                if end == 0:
                    chain.insert(0, s.p2)
                    chain_keys.insert(0, keys[idx][1])
                else:
                    chain.insert(0, s.p1)
                    chain_keys.insert(0, keys[idx][0])

            if len(chain) == 2:
                result.append(segs[i])
            else:
                closed = chain_keys[0] == chain_keys[-1]
                if closed:
                    chain = chain[:-1]
                result.append(Polyline(points=chain, closed=closed,
                                       layer=layer, color=color))
    return result


def estimate_bytes(attrs: EntityAttrs, mask: list[bool], opts: ExportOptions,
                   joined_stats: tuple[int, int, int] | None = None) -> int:
    """Estimativa do tamanho do DXF, em bytes, para a seleção dada.

    joined_stats: (n_polilinhas, total_de_vértices, n_segmentos_isolados) medidos
    de uma junção real, se disponível; senão usa a aproximação de 85% de
    encadeamento. É o único número aproximado da estimativa, e é o mesmo cálculo
    feito no navegador.
    """
    total = 0
    n_seg = 0
    for i, keep in enumerate(mask):
        if not keep:
            continue
        if attrs.kind[i] == "Segment":
            n_seg += 1
        else:
            total += attrs.byte_cost[i]

    if opts.join_polylines and n_seg:
        if joined_stats:
            n_poly, n_pts, n_alone = joined_stats
            total += n_poly * _POLY_BASE + n_pts * _POLY_PER_PT + n_alone * _BYTES["Segment"]
        else:
            # aproximação: ~85% dos segmentos se encadeiam em polilinhas
            chained = int(n_seg * 0.85)
            alone = n_seg - chained
            n_poly = max(1, chained // 12)  # cadeias médias de ~12 segmentos
            total += n_poly * _POLY_BASE + (chained + n_poly) * _POLY_PER_PT
            total += alone * _BYTES["Segment"]
    else:
        total += n_seg * _BYTES["Segment"]

    total += 60_000  # cabeçalho/tabelas
    if opts.round_coords:
        total = int(total * _ROUND_FACTOR)
    return total
