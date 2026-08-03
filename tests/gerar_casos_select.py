"""Gera tests/casos_select.json, o contrato entre o select() do Python e o do
navegador.

Cada caso congela duas coisas: a máscara devolvida pelo `select()` e o número
devolvido pelo `estimate_bytes()`. O segundo importa porque a estimativa usa
divisão inteira e truncamento (`chained // 12`, `int(...)`), que não existem em
JavaScript — sem um número congelado, a versão TypeScript escreveria no escuro.

Rode depois de qualquer mudança em select() ou classify():

    python tests/gerar_casos_select.py

O arquivo gerado é versionado. Se ele mudar num commit que não pretendia mudar
comportamento, isso é um alerta, não um detalhe.

O campo "esperado" de cada caso é a máscara booleana do select(), mas gravada
como uma string de '0'/'1' (um caractere por entidade) em vez de uma lista de
booleanos — com 1024 casos e ~230 entidades por tabela, uma lista de booleanos
com indent=1 gastava ~2,8 MB só em vírgulas e quebras de linha. Para decodificar
em Python: `[c == "1" for c in caso["esperado"]]`. Em TypeScript, a mesma ideia:
`[...s].map(c => c === "1")`.

`length_um` (nas tabelas) é o comprimento de cada segmento em inteiro de
micrômetros de papel — 0 fora de Segment. É o `EntityAttrs.length_um` de
`classify()`, gravado sem arredondamento porque já é inteiro. O limiar
`min_len_mm` de cada caso se converte para a mesma unidade com
`Math.round(min_len_mm * 1000)` (ou `int(min_len_mm * 1000 + 0.5)` em Python —
mesma regra de arredondamento para cima no meio, para as duas linguagens nunca
discordarem sobre um comprimento bem em cima do limiar).
"""

import itertools
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.calibration import PT_TO_MM
from pdftodxf.geometry import Arc, Polyline, Segment, TextItem
from pdftodxf.optimize import ExportOptions, classify, estimate_bytes, select

SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "casos_select.json")

LAYERS = ["0", "PAREDES", "COTAS", "HACHURA"]
CORES = [None, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]

# Comprimento exato de um segmento de 1 pt, com as mesmas 9 casas com que os
# comprimentos eram gravados no contrato antes de virar inteiro. Usado como
# limiar de min_len_mm para que a comparação `length_um < min_len_um` seja
# exercitada na igualdade: com `<` o segmento de 1 pt sobrevive, com `<=` ele
# some.
LIMIAR_1PT = round(PT_TO_MM, 9)

# Com length_um inteiro, o limiar de 0.5 mm vira 500 µm exatos
# (int(0.5 * 1000 + 0.5) == 500). A chave de duplicata arredonda em 3 casas de
# pt (~0,353 µm de resolução) — mais fina que 1 µm —, então dentro de um mesmo
# grupo de duplicata cabem comprimentos que arredondam para µm inteiros
# diferentes, um de cada lado do limiar. 1.417 pt (o valor que servia antes de
# length_um virar inteiro) não serve mais: os dois lados do grupo caem no
# mesmo bucket de 3 casas (1.417) e ambos arredondam para 500 µm — o limiar
# deixa de ser exercitado. 1.41551 e 1.41591 pt arredondam para o mesmo bucket
# de 3 casas (1.416) mas para µm diferentes (499 e 500).
CURTO_PT = 1.41551   # 499 µm — abaixo do limiar de 500 µm (0.5 mm)
LONGO_PT = 1.41591   # 500 µm — no limiar de 500 µm (0.5 mm)
# Mesma ideia em torno do limiar de 1 pt (LIMIAR_1PT, que vira 353 µm): 0.9999
# e 1.0001 pt (o par de antes) arredondam os dois para 353 µm com length_um
# inteiro. 0.99851 e 0.99922 pt compartilham o bucket de 3 casas (0.999) e
# arredondam para 352 e 353 µm.
CURTO_1PT = 0.99851  # 352 µm — abaixo do limiar de 353 µm
LONGO_1PT = 0.99922  # 353 µm — no limiar de 353 µm


def gerar_entidades(n, semente):
    """Entidades numa grade de 3x3, para produzir duplicatas em quantidade.

    A grade precisa ser pequena de propósito: 9 pontos dão 36 pares não
    ordenados que, multiplicados pelos 4 layers e 3 cores, somam 432 chaves
    possíveis para ~225 segmentos. Numa grade de 6x6 as colisões ficam raras e
    o caminho do dedup mal é exercitado.
    """
    rnd = random.Random(semente)
    ents = []
    for _ in range(n):
        layer = rnd.choice(LAYERS)
        cor = rnd.choice(CORES)
        fill = rnd.random() < 0.3
        tipo = rnd.random()
        if tipo < 0.75:
            x1, y1, x2, y2 = (float(rnd.randrange(0, 3)) for _ in range(4))
            if rnd.random() < 0.5:
                x1, y1, x2, y2 = x2, y2, x1, y1
            ents.append(Segment(p1=(x1, y1), p2=(x2, y2), layer=layer,
                                color=cor, is_fill=fill))
        elif tipo < 0.85:
            pts = [(float(rnd.randrange(0, 6)), float(rnd.randrange(0, 6)))
                   for _ in range(rnd.randrange(2, 6))]
            ents.append(Polyline(points=pts, layer=layer, color=cor, is_fill=fill))
        elif tipo < 0.95:
            ents.append(Arc(center=(0.0, 0.0), radius=3.0, start_angle=0.0,
                            end_angle=90.0, layer=layer, color=cor, is_fill=fill))
        else:
            ents.append(TextItem(text="T", position=(0.0, 0.0), height=2.0,
                                 layer=layer, color=cor, is_fill=fill))
    return ents


def _seg(x1, y1, x2, y2, layer, fill=False):
    return Segment(p1=(x1, y1), p2=(x2, y2), layer=layer, color=None,
                   is_fill=fill)


def gerar_entidades_limiar():
    """Tabela escrita à mão: duplicatas com comprimentos ao redor do limiar.

    Nas tabelas sorteadas todos os membros de um `dup_group` têm coordenadas
    idênticas e portanto o mesmo comprimento — trocar a ordem entre o filtro de
    comprimento e a reserva do grupo no `select()` não muda nenhuma máscara. Em
    PDF real as duplicatas nascem de aritmética de ponto flutuante: colidem no
    `round(..., 3)` da chave, mas seus comprimentos diferem um pouco.

    Cada par abaixo mora no mesmo grupo e cerca um limiar de `min_len_mm`. Com
    o curto vindo primeiro, a implementação correta descarta o curto **sem**
    reservar o grupo e emite o longo; a implementação que reserva o grupo antes
    de olhar o comprimento perde os dois.
    """
    return [
        # 1-2: curto primeiro, longo depois (limiar de 0.5 mm)
        _seg(0.0, 0.0, CURTO_PT, 0.0, "PAREDES"),
        _seg(0.0, 0.0, LONGO_PT, 0.0, "PAREDES"),
        # 3-4: a ordem inversa, que sobrevive nas duas implementações
        _seg(0.0, 1.0, LONGO_PT, 1.0, "PAREDES"),
        _seg(0.0, 1.0, CURTO_PT, 1.0, "PAREDES"),
        # 5-6: mesmo arranjo em torno do limiar de 1 pt
        _seg(0.0, 2.0, CURTO_1PT, 2.0, "COTAS"),
        _seg(0.0, 2.0, LONGO_1PT, 2.0, "COTAS"),
        # 7-9: dois curtos antes do longo, o primeiro deles preenchimento
        _seg(0.0, 3.0, CURTO_PT, 3.0, "COTAS", fill=True),
        _seg(0.0, 3.0, CURTO_PT, 3.0, "COTAS"),
        _seg(0.0, 3.0, LONGO_PT, 3.0, "COTAS"),
        # 10-12: o mesmo num layer que algumas opções excluem
        _seg(0.0, 4.0, CURTO_PT, 4.0, "HACHURA"),
        _seg(0.0, 4.0, CURTO_1PT, 4.0, "HACHURA", fill=True),
        _seg(0.0, 4.0, LONGO_PT, 4.0, "HACHURA"),
        # não-segmentos, para o custo em bytes não ficar só de LINE
        Polyline(points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], layer="0"),
        Arc(center=(0.0, 0.0), radius=3.0, start_angle=0.0, end_angle=90.0,
            layer="0"),
        TextItem(text="T", position=(0.0, 0.0), height=2.0, layer="0"),
    ]


def opcoes_variadas():
    """Produto cartesiano das opções.

    `join_polylines` e `round_coords` não mudam a máscara do `select()`, mas
    mudam o `estimate_bytes` — entram aqui porque o contrato também congela o
    número de bytes.
    """
    excluidos = [[], ["HACHURA"], ["COTAS", "HACHURA"], list(LAYERS)]
    for exc, fills, micro, dedup, juntar, arredondar in itertools.product(
            excluidos, [False, True], [0.0, LIMIAR_1PT, 0.5, 2.0],
            [False, True], [False, True], [False, True]):
        yield exc, fills, micro, dedup, juntar, arredondar


def main():
    tabelas = []
    casos = []
    fontes = [(f"semente{s}", gerar_entidades(300, s)) for s in range(3)]
    fontes.append(("limiar", gerar_entidades_limiar()))

    for indice, (nome_tabela, ents) in enumerate(fontes):
        attrs = classify(ents)
        tabelas.append({
            "kind": attrs.kind,
            "layer_id": attrs.layer_id,
            "is_fill": attrs.is_fill,
            "length_um": attrs.length_um,
            "dup_group": attrs.dup_group,
            "byte_cost": attrs.byte_cost,
            "layers": attrs.layers,
            "n_groups": attrs.n_groups,
        })
        for i, (exc, fills, micro, dedup, juntar,
                arredondar) in enumerate(opcoes_variadas()):
            opts = ExportOptions(excluded_layers=set(exc), drop_fills=fills,
                                 min_len_mm=micro, dedup=dedup,
                                 join_polylines=juntar,
                                 round_coords=arredondar)
            mask = select(attrs, opts)
            casos.append({
                "nome": f"{nome_tabela}-opcao{i}",
                "tabela": indice,
                "opcoes": {
                    "excluded_layers": exc,
                    "drop_fills": fills,
                    "min_len_mm": micro,
                    "dedup": dedup,
                    "join_polylines": juntar,
                    "round_coords": arredondar,
                },
                "esperado": "".join("1" if k else "0" for k in mask),
                "bytes_esperado": estimate_bytes(attrs, mask, opts),
            })

    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump({"tabelas": tabelas, "casos": casos}, f, ensure_ascii=False,
                  indent=1, sort_keys=True)
        f.write("\n")
    print(f"{len(casos)} casos gravados em {SAIDA}")


if __name__ == "__main__":
    main()
