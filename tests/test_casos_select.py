"""Roda os casos de tests/casos_select.json contra o select() do Python.

O mesmo arquivo é lido pelo vitest na etapa 3. Se as duas implementações
divergirem em qualquer caso, um dos dois lados quebra aqui.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.optimize import EntityAttrs, ExportOptions, select

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
                             dedup=o["dedup"])
        obtido = select(attrs, opts)
        assert obtido == caso["esperado"], f"divergência em {caso['nome']}"

    print(f"OK: {len(dados['casos'])} casos de paridade")


if __name__ == "__main__":
    test_casos()
    print("Todos os casos de paridade passaram.")
