"""Roda os casos de tests/casos_select.json contra o select() do Python.

O mesmo arquivo é lido pelo vitest na etapa 3. Se as duas implementações
divergirem em qualquer caso, um dos dois lados quebra aqui.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.optimize import (EntityAttrs, ExportOptions, estimate_bytes,
                               select)

CASOS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "casos_select.json")


def test_casos():
    with open(CASOS, encoding="utf-8") as f:
        dados = json.load(f)

    tabelas = []
    for a in dados["tabelas"]:
        tabelas.append(EntityAttrs(
            kind=a["kind"], layer_id=a["layer_id"], is_fill=a["is_fill"],
            length_mm=a["length_mm"], dup_group=a["dup_group"],
            byte_cost=a["byte_cost"], layers=a["layers"],
            n_groups=a["n_groups"]))

    for caso in dados["casos"]:
        attrs = tabelas[caso["tabela"]]
        o = caso["opcoes"]
        opts = ExportOptions(excluded_layers=set(o["excluded_layers"]),
                             drop_fills=o["drop_fills"],
                             min_len_mm=o["min_len_mm"],
                             dedup=o["dedup"],
                             join_polylines=o["join_polylines"],
                             round_coords=o["round_coords"])
        esperado = [c == "1" for c in caso["esperado"]]
        obtido = select(attrs, opts)
        divergentes = [i for i, (a, b) in enumerate(zip(obtido, esperado))
                       if a != b]
        assert not divergentes and len(obtido) == len(esperado), (
            f"divergência em {caso['nome']}: índices {divergentes[:5]}"
            f"{' e mais' if len(divergentes) > 5 else ''}")

        bytes_obtido = estimate_bytes(attrs, obtido, opts)
        assert bytes_obtido == caso["bytes_esperado"], (
            f"bytes divergentes em {caso['nome']}: "
            f"{bytes_obtido} != {caso['bytes_esperado']}")

    print(f"OK: {len(dados['casos'])} casos de paridade")


if __name__ == "__main__":
    test_casos()
    print("Todos os casos de paridade passaram.")
