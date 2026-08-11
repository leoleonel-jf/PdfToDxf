"""A fixture do formato binário continua batendo com o packing.py."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.gerar_fixture_geometria import PASTA, amostra
from pdftodxf.optimize import classify
from web.api import packing


def test_fixture_esta_atualizada():
    r = amostra()
    a = classify(r.entities)
    agora = packing.empacotar(r, a, list(range(len(r.entities))))
    with open(os.path.join(PASTA, "geometria_exemplo.bin"), "rb") as f:
        gravado = f.read()
    assert agora == gravado, (
        "o packing.py mudou e a fixture ficou para trás. Rode "
        "tests/gerar_fixture_geometria.py e confira o git diff: se ele sujar, "
        "o formato mudou e o leitor TypeScript precisa acompanhar.")
    print("OK: a fixture do formato binário está atualizada")


def test_json_descreve_o_bin():
    with open(os.path.join(PASTA, "geometria_exemplo.json"), encoding="utf-8") as f:
        esperado = json.load(f)
    with open(os.path.join(PASTA, "geometria_exemplo.bin"), "rb") as f:
        lido = packing.desempacotar(f.read())
    assert lido["n"] == esperado["n"]
    assert lido["kind"] == esperado["kind"]
    assert lido["cor"] == esperado["cor"]
    print("OK: o JSON da fixture descreve o binário")


if __name__ == "__main__":
    test_fixture_esta_atualizada()
    test_json_descreve_o_bin()
    print("Todos os testes da fixture passaram.")
