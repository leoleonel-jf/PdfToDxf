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
    sub.add_argument("--min-mm", type=float, default=0.0, dest="min_mm",
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
    conv.add_argument("--pagina", type=int, default=1, metavar="N",
                      help="página a converter, começando em 1 (padrão: 1)")
    conv.add_argument("--escala", type=float, metavar="F",
                      help="fator direto: 1 pt de papel vale F unidades")
    conv.add_argument("--plotagem", type=float, metavar="R",
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
    insp.add_argument("--pagina", type=int, metavar="N",
                      help="só esta página (padrão: todas)")

    return parser


def opcoes_de(args: argparse.Namespace) -> ExportOptions:
    return ExportOptions(
        excluded_layers=set(args.excluir_layer),
        drop_fills=args.sem_preenchimento,
        min_len_mm=args.min_mm,
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
        if args.escala <= 0:
            raise ValueError("A escala deve ser positiva.")
        return args.escala
    return scale_from_plot_scale(args.plotagem, args.unidade)


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
    except ValueError as e:
        print(f"erro: {e}", file=sys.stderr)
        return ERRO_DE_USO

    saida = Path(args.saida) if args.saida else Path(args.entrada).with_suffix(".dxf")
    if saida.exists() and not args.forcar:
        print(f"erro: {saida} já existe. Use --forcar para sobrescrever.",
              file=sys.stderr)
        return ERRO_DE_USO

    try:
        resultado = _extrair(args.entrada, args.pagina)
    except Exception as e:
        print(f"erro: {e}", file=sys.stderr)
        return PROBLEMA_NO_ARQUIVO

    attrs = classify(resultado.entities)
    opts = opcoes_de(args)
    saida.parent.mkdir(parents=True, exist_ok=True)
    contagem = export_dxf(resultado, str(saida), escala, args.unidade, opts,
                          attrs=attrs)

    total = sum(contagem.values())
    print(f"{saida}: {total} entidades "
          f"(de {len(resultado.entities)} extraídas), "
          f"1 pt = {escala:g} {args.unidade}")
    return SUCESSO


def _inspecionar(args: argparse.Namespace) -> int:
    raise NotImplementedError("tarefa 2")


def main(argv: list[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    if args.comando == "converter":
        return _converter(args)
    return _inspecionar(args)
