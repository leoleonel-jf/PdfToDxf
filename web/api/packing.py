"""Formato binário da geometria enviada ao navegador.

O arquivo se descreve sozinho: um cabeçalho com a tabela de seções e, em
seguida, os dados. O leitor TypeScript da etapa 3 monta as `TypedArray`
apontando direto para o buffer, sem copiar nada.

Tudo little-endian. Ver a tabela de seções no plano da etapa 2.
"""

from __future__ import annotations

import array
import struct
import sys

MAGICO = b"PDXF"
VERSAO = 1

IDX, KIND, LAYER_ID, IS_FILL, LENGTH_UM = 1, 2, 3, 4, 5
DUP_GROUP, BYTE_COST, COR, COORD_OFF, COORDS = 6, 7, 8, 9, 10
TEXTO_OFF, TEXTO = 11, 12

SEM_COR = 0xFFFFFFFF

ALINHAMENTO = 4
"""Toda seção começa em múltiplo de 4, com enchimento de zeros quando preciso.

`new Uint32Array(buffer, deslocamento, n)` levanta `RangeError` se o
deslocamento não for múltiplo de 4, e as seções de uint8 (`kind`, `is_fill`)
ocupam exatamente n bytes. Sem enchimento, qualquer página cuja contagem fuja
da tabuada do 4 desalinharia tudo o que vem depois — e do lado Python nada
denunciaria, porque `struct.unpack_from` lê de qualquer deslocamento.

O tamanho gravado na tabela é o real, sem o enchimento.
"""

_CODIGO_TIPO = {"Segment": 0, "Polyline": 1, "Arc": 2, "Bezier": 3,
                "TextItem": 4}

# Os códigos de `array` são do C, e o C não promete tamanho. Conferir aqui é
# barato e evita gerar um arquivo silenciosamente errado numa plataforma exótica.
for _codigo, _esperado in (("B", 1), ("I", 4), ("i", 4), ("f", 4)):
    if array.array(_codigo).itemsize != _esperado:
        raise RuntimeError(
            f"array('{_codigo}') mede {array.array(_codigo).itemsize} bytes, "
            f"e o formato precisa de {_esperado}")


def _cor_para_inteiro(rgb) -> int:
    if rgb is None:
        return SEM_COR
    # `round` e não `int(c * 255 + 0.5)` para casar com o `_color_name` do
    # extractor: a cor desenhada e o nome do layer `COR_RRGGBB` vêm do mesmo
    # RGB e não podem discordar.
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb)
    return (r << 16) | (g << 8) | b


def _bytes_de(codigo: str, valores) -> bytes:
    """Empacota uma sequência de números em little-endian.

    `array` em vez de `struct.pack(f"<{n}I", *valores)`: no teto de 3 milhões
    de entidades aquele desempacotamento montaria uma tupla de milhões de
    argumentos só para descartá-la em seguida.
    """
    dados = array.array(codigo, valores)
    if sys.byteorder != "little":
        dados.byteswap()
    return dados.tobytes()


def _coordenadas(e) -> list[float]:
    nome = type(e).__name__
    if nome == "Segment":
        return [e.p1[0], e.p1[1], e.p2[0], e.p2[1]]
    if nome == "Polyline":
        saida = [1.0 if e.closed else 0.0]
        for x, y in e.points:
            saida.append(x)
            saida.append(y)
        return saida
    if nome == "Arc":
        return [e.center[0], e.center[1], e.radius, e.start_angle, e.end_angle]
    if nome == "Bezier":
        return [e.p0[0], e.p0[1], e.p1[0], e.p1[1],
                e.p2[0], e.p2[1], e.p3[0], e.p3[1]]
    if nome == "TextItem":
        return [e.position[0], e.position[1], e.height, e.rotation, e.width]
    raise ValueError(f"tipo de entidade desconhecido: {nome}")


def empacotar(resultado, attrs, indices: list[int]) -> bytes:
    """Monta o binário com as entidades de `indices`, nessa ordem.

    `indices` são posições na lista completa de entidades da extração. Elas vão
    gravadas na seção `idx` para que o navegador possa reunir esqueleto e
    detalhe sem ambiguidade.
    """
    n = len(indices)
    idx, kind, layer_id, is_fill = [], [], [], []
    length_um, dup_group, byte_cost, cor = [], [], [], []
    coords: list[float] = []
    coord_off = [0]
    texto = bytearray()
    texto_off = [0]

    for i in indices:
        e = resultado.entities[i]
        idx.append(i)
        kind.append(_CODIGO_TIPO[attrs.kind[i]])
        layer_id.append(attrs.layer_id[i])
        is_fill.append(1 if attrs.is_fill[i] else 0)
        length_um.append(attrs.length_um[i])
        dup_group.append(attrs.dup_group[i])
        byte_cost.append(attrs.byte_cost[i])
        cor.append(_cor_para_inteiro(e.color))

        coords.extend(_coordenadas(e))
        coord_off.append(len(coords))

        if attrs.kind[i] == "TextItem":
            texto.extend(e.text.encode("utf-8"))
        texto_off.append(len(texto))

    secoes = [
        (IDX, _bytes_de("I", idx)),
        (KIND, _bytes_de("B", kind)),
        (LAYER_ID, _bytes_de("I", layer_id)),
        (IS_FILL, _bytes_de("B", is_fill)),
        (LENGTH_UM, _bytes_de("I", length_um)),
        (DUP_GROUP, _bytes_de("i", dup_group)),
        (BYTE_COST, _bytes_de("I", byte_cost)),
        (COR, _bytes_de("I", cor)),
        (COORD_OFF, _bytes_de("I", coord_off)),
        (COORDS, _bytes_de("f", coords)),
        (TEXTO_OFF, _bytes_de("I", texto_off)),
        (TEXTO, bytes(texto)),
    ]

    cabecalho = bytearray()
    cabecalho += MAGICO
    cabecalho += struct.pack("<III", VERSAO, n, len(secoes))
    # 16 + 12 por seção: múltiplo de 4 para qualquer quantidade de seções, então
    # a primeira já começa alinhada.
    inicio_dados = len(cabecalho) + 12 * len(secoes)

    tabela = bytearray()
    corpo = bytearray()
    deslocamento = inicio_dados
    for tipo, dados in secoes:
        tabela += struct.pack("<III", tipo, deslocamento, len(dados))
        corpo += dados
        enchimento = -len(dados) % ALINHAMENTO
        corpo += b"\0" * enchimento
        deslocamento += len(dados) + enchimento

    return bytes(cabecalho + tabela + corpo)


def desempacotar(dados: bytes) -> dict:
    """Lê o binário de volta. Existe para os testes: em produção quem lê é o TS."""
    if len(dados) < 16 or dados[:4] != MAGICO:
        raise ValueError("não é um arquivo de geometria do PdfToDxf")
    versao, n, s = struct.unpack_from("<III", dados, 4)
    if versao != VERSAO:
        raise ValueError(f"versão {versao} desconhecida")
    if len(dados) < 16 + 12 * s:
        raise ValueError("tabela de seções cortada")

    tabela = {}
    for k in range(s):
        tipo, desloc, tamanho = struct.unpack_from("<III", dados, 16 + 12 * k)
        if desloc + tamanho > len(dados):
            raise ValueError(f"seção {tipo} passa do fim do arquivo")
        tabela[tipo] = (desloc, tamanho)

    def inteiros(tipo, formato, quantos):
        desloc, _ = tabela[tipo]
        return list(struct.unpack_from(f"<{quantos}{formato}", dados, desloc))

    coord_off = inteiros(COORD_OFF, "I", n + 1)
    texto_off = inteiros(TEXTO_OFF, "I", n + 1)
    desloc_coords, tam_coords = tabela[COORDS]
    coords = list(struct.unpack_from(f"<{tam_coords // 4}f", dados,
                                     desloc_coords))
    desloc_texto, tam_texto = tabela[TEXTO]
    blob = dados[desloc_texto:desloc_texto + tam_texto]

    return {
        "n": n,
        "secoes": tabela,
        "idx": inteiros(IDX, "I", n),
        "kind": inteiros(KIND, "B", n),
        "layer_id": inteiros(LAYER_ID, "I", n),
        "is_fill": inteiros(IS_FILL, "B", n),
        "length_um": inteiros(LENGTH_UM, "I", n),
        "dup_group": inteiros(DUP_GROUP, "i", n),
        "byte_cost": inteiros(BYTE_COST, "I", n),
        "cor": inteiros(COR, "I", n),
        "coords_de": lambda i: coords[coord_off[i]:coord_off[i + 1]],
        "texto_de": lambda i: blob[texto_off[i]:texto_off[i + 1]].decode("utf-8"),
    }
