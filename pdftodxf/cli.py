"""Linha de comando do PdfToDxf.

Terceiro consumidor do núcleo, ao lado do desktop e da web. Ela **só** enxerga a
superfície pública — `extract_page`, `classify`, `select`, `ExportOptions`,
`estimate_bytes`, `export_dxf` e `calibration`. Essa restrição não é estilo: é o
que faz desta CLI um teste de que a fronteira existe. Se algum dia ela precisar
importar outra coisa, isso é um defeito do núcleo, não um detalhe daqui.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .calibration import INSUNITS, scale_from_plot_scale
from .dxf_writer import export_dxf
from .extractor import extract_page
from .numeros import ler_inteiro, ler_numero
from .optimize import ExportOptions, classify, estimate_bytes, select

SUCESSO = 0
ERRO_DE_USO = 1
PROBLEMA_NO_ARQUIVO = 2

# Flag longa → campo de ExportOptions. Um teste afirma que os valores deste
# dicionário são exatamente os campos do dataclass: é o que impede a CLI de
# ficar para trás quando o núcleo ganhar uma opção nova.
OPCOES_DE_COMPACTACAO = {
    "unir": "join_polylines",
    "arredondar": "round_coords",
    "dedup": "dedup",
    "sem_preenchimento": "drop_fills",
    "min_mm": "min_len_mm",
    "excluir_layer": "excluded_layers",
}


def _acrescentar_opcoes(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--unir", action="store_true",
                     help="unir segmentos encadeados em polilinhas")
    sub.add_argument("--arredondar", action="store_true",
                     help="arredondar as coordenadas na escrita")
    sub.add_argument("--dedup", action="store_true",
                     help="remover segmentos duplicados ou sobrepostos")
    sub.add_argument("--sem-preenchimento", action="store_true",
                     dest="sem_preenchimento",
                     help="descartar hachuras sólidas")
    # Os campos numéricos entram como texto e são lidos por `numeros.py`: o
    # `type=float` do argparse recusa a vírgula decimal e aborta o processo com
    # uma mensagem em inglês, fora do jogo de códigos de saída desta CLI.
    sub.add_argument("--min-mm", default="0", dest="min_mm",
                     metavar="N",
                     help="descartar segmentos menores que N mm de papel")
    sub.add_argument("--excluir-layer", action="append", default=[],
                     dest="excluir_layer", metavar="NOME",
                     help="não exportar este layer (pode repetir)")


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pdftodxf",
        description="Converte plantas em PDF vetorial para DXF em escala real.")
    comandos = parser.add_subparsers(dest="comando", required=True)

    conv = comandos.add_parser("converter", help="gravar o DXF")
    conv.add_argument("entrada", help="o PDF de entrada")
    conv.add_argument("--pagina", default="1", metavar="N",
                      help="página a converter, começando em 1 (padrão: 1)")
    conv.add_argument("--escala", metavar="F",
                      help="fator direto: 1 pt de papel vale F unidades")
    conv.add_argument("--plotagem", metavar="R",
                      help="escala de plotagem 1:R (ex.: 50 para 1:50)")
    conv.add_argument("--unidade", choices=sorted(INSUNITS), default="m",
                      help="unidade de saída (padrão: m)")
    conv.add_argument("-o", "--saida", metavar="CAMINHO",
                      help="onde gravar (padrão: ao lado do original, .dxf)")
    conv.add_argument("--forcar", action="store_true",
                      help="permitir sobrescrever um arquivo existente")
    _acrescentar_opcoes(conv)

    insp = comandos.add_parser(
        "inspecionar", help="descrever a planta sem gravar nada")
    insp.add_argument("entrada", help="o PDF de entrada")
    insp.add_argument("--pagina", metavar="N",
                      help="só esta página (padrão: todas)")

    return parser


def opcoes_de(args: argparse.Namespace) -> ExportOptions:
    minimo = ler_numero(args.min_mm, o_que="o valor de --min-mm")
    if minimo < 0:
        raise ValueError("O valor de --min-mm não pode ser negativo.")
    return ExportOptions(
        excluded_layers=set(args.excluir_layer),
        drop_fills=args.sem_preenchimento,
        min_len_mm=minimo,
        dedup=args.dedup,
        join_polylines=args.unir,
        round_coords=args.arredondar,
    )


def fator_de_escala(args: argparse.Namespace) -> float:
    """Devolve o fator, venha ele de `--escala` ou de `--plotagem`.

    Levanta `ValueError` se vierem os dois ou nenhum: são pedidos ambíguos, e
    escolher um por conta própria seria adivinhar a intenção de quem digitou.
    """
    tem_escala = args.escala is not None
    tem_plotagem = args.plotagem is not None
    if tem_escala and tem_plotagem:
        raise ValueError("Use --escala ou --plotagem, não os dois.")
    if not tem_escala and not tem_plotagem:
        raise ValueError("Falta a escala: use --escala ou --plotagem.")
    if tem_escala:
        escala = ler_numero(args.escala, o_que="a escala")
        if escala <= 0:
            raise ValueError("A escala deve ser positiva.")
        return escala
    return scale_from_plot_scale(
        ler_numero(args.plotagem, o_que="a escala de plotagem"), args.unidade)


def _extrair(entrada: str, pagina: int):
    """Extrai a página, traduzindo as falhas em mensagem e código de saída."""
    caminho = Path(entrada)
    if not caminho.is_file():
        raise FileNotFoundError(f"Não achei o arquivo: {entrada}")
    # A CLI conta páginas a partir de 1, como a API; o extractor conta de 0.
    resultado = extract_page(str(caminho), page_number=pagina - 1)
    if not resultado.entities:
        raise ValueError(
            "Esta página não tem desenho vetorial. Só funcionam PDFs gerados "
            "pelo CAD, não escaneados.")
    return resultado


def _converter(args: argparse.Namespace) -> int:
    try:
        escala = fator_de_escala(args)
        opts = opcoes_de(args)
        pagina = ler_inteiro(args.pagina, o_que="a página")
    except ValueError as e:
        print(f"erro: {e}", file=sys.stderr)
        return ERRO_DE_USO

    saida = Path(args.saida) if args.saida else Path(args.entrada).with_suffix(".dxf")
    if saida.exists() and not args.forcar:
        print(f"erro: {saida} já existe. Use --forcar para sobrescrever.",
              file=sys.stderr)
        return ERRO_DE_USO

    try:
        resultado = _extrair(args.entrada, pagina)
    except Exception as e:
        print(f"erro: {e}", file=sys.stderr)
        return PROBLEMA_NO_ARQUIVO

    attrs = classify(resultado.entities)
    saida.parent.mkdir(parents=True, exist_ok=True)
    contagem = export_dxf(resultado, str(saida), escala, args.unidade, opts,
                          attrs=attrs)

    total = sum(contagem.values())
    print(f"{saida}: {total} entidades "
          f"(de {len(resultado.entities)} extraídas), "
          f"1 pt = {escala:g} {args.unidade}")
    return SUCESSO


# As combinações que valem a pena mostrar: a de referência, cada uma das duas
# que mais mudam o tamanho, e as três juntas. Mais do que isso vira parede de
# números que ninguém lê.
COMBINACOES: list[tuple[str, ExportOptions]] = [
    ("sem opções", ExportOptions()),
    ("dedup", ExportOptions(dedup=True)),
    ("unir", ExportOptions(join_polylines=True)),
    ("dedup + unir + arredondar",
     ExportOptions(dedup=True, join_polylines=True, round_coords=True)),
]


def _mb(bytes_: int) -> str:
    return f"{bytes_ / 1_000_000:.1f} MB"


def _descrever_pagina(resultado, pagina: int) -> None:
    """Imprime o retrato de uma página já extraída.

    Recebe o resultado pronto, e não o caminho, de propósito: quem chama
    envolve só a extração num `except ValueError`, e assim uma falha daqui de
    dentro — de impressão, de cálculo, do que for — estoura de verdade em vez
    de ser exibida como "esta página não tem desenho vetorial". Foi o que
    aconteceu quando um `≈` não coube no console do Windows.
    """
    attrs = classify(resultado.entities)

    # Só ASCII no que o console engole: o cp1252 do Windows não tem "≈" nem
    # garante "×", e uma linha de retrato não vale um UnicodeEncodeError.
    print(f"\npágina {pagina}: {len(resultado.entities)} entidades, "
          f"folha de {resultado.page_width:.0f} x {resultado.page_height:.0f} pt")

    contagem = resultado.counts()
    for tipo in sorted(contagem):
        print(f"  {tipo:<10} {contagem[tipo]:>9}")

    por_layer: dict[str, int] = {}
    for i in range(len(attrs)):
        nome = attrs.layers[attrs.layer_id[i]]
        por_layer[nome] = por_layer.get(nome, 0) + 1
    print(f"  {len(por_layer)} layers:")
    for nome in sorted(por_layer, key=lambda n: -por_layer[n]):
        print(f"    {nome:<24} {por_layer[nome]:>9}")

    print("  estimativa do DXF:")
    for rotulo, opts in COMBINACOES:
        mascara = select(attrs, opts)
        sobrevivem = sum(1 for v in mascara if v)
        tamanho = estimate_bytes(attrs, mascara, opts)
        print(f"    {rotulo:<26} {sobrevivem:>9} entidades   ~ {_mb(tamanho)}")


def _inspecionar(args: argparse.Namespace) -> int:
    import fitz   # só aqui: inspecionar precisa contar as páginas do documento

    caminho = Path(args.entrada)
    if not caminho.is_file():
        print(f"erro: não achei o arquivo: {args.entrada}", file=sys.stderr)
        return PROBLEMA_NO_ARQUIVO

    try:
        with fitz.open(str(caminho)) as doc:
            n_paginas = doc.page_count
    except Exception as e:
        print(f"erro: não consegui abrir como PDF: {e}", file=sys.stderr)
        return PROBLEMA_NO_ARQUIVO

    print(f"{caminho.name}: {n_paginas} página(s)")
    if args.pagina is None:
        paginas = list(range(1, n_paginas + 1))
    else:
        try:
            paginas = [ler_inteiro(args.pagina, o_que="a página")]
        except ValueError as e:
            print(f"erro: {e}", file=sys.stderr)
            return ERRO_DE_USO

    for pagina in paginas:
        if pagina < 1 or pagina > n_paginas:
            print(f"erro: o documento tem {n_paginas} página(s)", file=sys.stderr)
            return PROBLEMA_NO_ARQUIVO
        try:
            resultado = _extrair(str(caminho), pagina)
        except ValueError as e:
            # Página sem vetores não interrompe o retrato das outras.
            print(f"\npágina {pagina}: {e}")
            continue
        _descrever_pagina(resultado, pagina)

    return SUCESSO


def main(argv: list[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    if args.comando == "converter":
        return _converter(args)
    return _inspecionar(args)
