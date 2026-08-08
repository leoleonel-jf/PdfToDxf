"""A linha de comando: converter, inspecionar e a fronteira do núcleo."""

import dataclasses
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ezdxf

from pdftodxf import cli
from pdftodxf.optimize import ExportOptions
from tests.test_roundtrip import make_test_pdf


def pdf_de_teste() -> str:
    caminho = os.path.join(tempfile.mkdtemp(), "planta.pdf")
    make_test_pdf(caminho)
    return caminho


def test_flags_cobrem_todos_os_campos_de_exportoptions():
    """O conjunto de flags é exatamente o conjunto de campos do núcleo.

    É o teste que sustenta esta etapa. A CLI é o terceiro lugar que nomeia e
    defaulta as mesmas opções; sem esta amarra, acrescentar um campo ao
    ExportOptions deixaria a CLI para trás em silêncio, e a divergência só
    apareceria quando alguém reclamasse de um DXF diferente do esperado.
    """
    campos = {c.name for c in dataclasses.fields(ExportOptions)}
    expostos = set(cli.OPCOES_DE_COMPACTACAO.values())
    assert expostos == campos, (
        f"a CLI não expõe {campos - expostos} e inventa {expostos - campos}")
    print("OK: as flags cobrem exatamente os campos de ExportOptions")


def test_converte_e_gera_dxf_valido():
    entrada = pdf_de_teste()
    saida = os.path.join(tempfile.mkdtemp(), "saida.dxf")
    codigo = cli.main(["converter", entrada, "--escala", "0.01",
                       "--unidade", "m", "-o", saida])
    assert codigo == 0, codigo
    doc = ezdxf.readfile(saida)
    assert not doc.audit().has_errors
    assert doc.header["$INSUNITS"] == 6, "unidade metros"
    print("OK: converter gera um DXF válido")


def test_saida_padrao_fica_ao_lado_do_original():
    entrada = pdf_de_teste()
    codigo = cli.main(["converter", entrada, "--escala", "0.01"])
    assert codigo == 0, codigo
    esperado = entrada[:-4] + ".dxf"
    assert os.path.exists(esperado), esperado
    print("OK: sem -o, a saída fica ao lado do original")


def test_recusa_sobrescrever_sem_forcar():
    entrada = pdf_de_teste()
    saida = os.path.join(tempfile.mkdtemp(), "ja-existe.dxf")
    with open(saida, "w", encoding="utf-8") as f:
        f.write("nao me apague")

    codigo = cli.main(["converter", entrada, "--escala", "0.01", "-o", saida])
    assert codigo == 1, codigo
    with open(saida, encoding="utf-8") as f:
        assert f.read() == "nao me apague", "o arquivo foi sobrescrito mesmo assim"

    codigo = cli.main(["converter", entrada, "--escala", "0.01", "-o", saida,
                       "--forcar"])
    assert codigo == 0, codigo
    assert ezdxf.readfile(saida)
    print("OK: só sobrescreve com --forcar")


def test_escala_e_plotagem_equivalentes_dao_o_mesmo():
    """1:50 em metros equivale ao fator 0.0176388…

    Comparar os dois arquivos byte a byte **não** funciona: o ezdxf grava
    `$TDCREATE` e `$TDUPDATE` no cabeçalho, então dois DXF gerados em instantes
    diferentes divergem sem que nada de errado tenha acontecido. O que interessa
    é a geometria.
    """
    entrada = pdf_de_teste()
    pasta = tempfile.mkdtemp()
    por_plotagem = os.path.join(pasta, "a.dxf")
    por_fator = os.path.join(pasta, "b.dxf")

    assert cli.main(["converter", entrada, "--plotagem", "50", "-o",
                     por_plotagem]) == 0
    fator = cli.fator_de_escala(
        cli.montar_parser().parse_args(["converter", entrada, "--plotagem", "50"]))
    assert cli.main(["converter", entrada, "--escala", repr(fator), "-o",
                     por_fator]) == 0

    def geometria(caminho: str):
        doc = ezdxf.readfile(caminho)
        saida = []
        for e in doc.modelspace():
            if e.dxftype() == "LINE":
                saida.append(("LINE",
                              round(e.dxf.start.x, 6), round(e.dxf.start.y, 6),
                              round(e.dxf.end.x, 6), round(e.dxf.end.y, 6)))
            else:
                saida.append((e.dxftype(),))
        return sorted(saida)

    assert geometria(por_plotagem) == geometria(por_fator), \
        "os dois caminhos de escala divergiram"
    print("OK: --escala e --plotagem equivalentes dão a mesma geometria")


def test_escala_ausente_ou_duplicada_e_erro_de_uso():
    entrada = pdf_de_teste()
    assert cli.main(["converter", entrada]) == 1
    assert cli.main(["converter", entrada, "--escala", "0.01",
                     "--plotagem", "50"]) == 1
    print("OK: escala ausente ou duplicada devolve 1")


def test_pagina_inexistente_e_problema_de_arquivo():
    entrada = pdf_de_teste()
    assert cli.main(["converter", entrada, "--escala", "0.01",
                     "--pagina", "99"]) == 2
    print("OK: página inexistente devolve 2")


def test_excluir_layer_morde():
    entrada = pdf_de_teste()
    pasta = tempfile.mkdtemp()
    cheio = os.path.join(pasta, "cheio.dxf")
    sem_texto = os.path.join(pasta, "sem-texto.dxf")

    assert cli.main(["converter", entrada, "--escala", "0.01", "-o", cheio]) == 0
    assert cli.main(["converter", entrada, "--escala", "0.01", "-o", sem_texto,
                     "--excluir-layer", "TEXTO"]) == 0

    def textos(caminho: str) -> int:
        doc = ezdxf.readfile(caminho)
        return sum(1 for e in doc.modelspace() if e.dxftype() == "TEXT")

    assert textos(cheio) > 0, "o PDF de teste deveria ter texto"
    assert textos(sem_texto) == 0, "--excluir-layer não excluiu"
    print("OK: --excluir-layer some com o layer no arquivo gerado")


def test_inspecionar_descreve_a_planta_sem_gravar():
    """Imprime o retrato e não deixa arquivo para trás."""
    import io
    from contextlib import redirect_stdout

    entrada = pdf_de_teste()
    pasta = os.path.dirname(entrada)
    antes = set(os.listdir(pasta))

    saida = io.StringIO()
    with redirect_stdout(saida):
        codigo = cli.main(["inspecionar", entrada])
    assert codigo == 0, codigo

    texto = saida.getvalue()
    assert "TEXTO" in texto, texto           # um layer do PDF de teste
    assert "Segment" in texto, texto         # a contagem por tipo
    assert "dedup" in texto, texto           # uma das combinações
    assert set(os.listdir(pasta)) == antes, "inspecionar gravou alguma coisa"
    print("OK: inspecionar descreve a planta e não grava nada")


def test_inspecionar_pagina_inexistente():
    entrada = pdf_de_teste()
    assert cli.main(["inspecionar", entrada, "--pagina", "99"]) == 2
    print("OK: inspecionar em página inexistente devolve 2")


def test_cli_so_toca_a_superficie_publica_do_nucleo():
    """A CLI é o terceiro consumidor do núcleo e enxerga só o que é público.

    É esta amarra que faz dela um teste da fronteira, e não só uma
    conveniência: se alguém precisar puxar um detalhe interno para a CLI
    funcionar, isso é defeito do núcleo, e este teste força a conversa em vez
    de deixar o atalho passar.

    O `fitz` está na lista como exceção **conhecida e registrada**: contar as
    páginas de um documento não tem função pública no núcleo, e hoje tanto a
    CLI quanto `web/api/main.py` abrem o PyMuPDF na mão. Está na dívida do
    handoff. Se aparecer uma segunda exceção, é sinal de que a fronteira está
    vazando de verdade.
    """
    import ast
    import pathlib

    permitidos = {
        ".calibration", ".dxf_writer", ".extractor", ".optimize",
        "argparse", "sys", "pathlib", "__future__",
        "fitz",   # exceção registrada: contar páginas não é público no núcleo
    }

    fonte = pathlib.Path(cli.__file__).read_text(encoding="utf-8")
    usados = set()
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Import):
            usados.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            usados.add("." * no.level + (no.module or ""))

    intrusos = usados - permitidos
    assert not intrusos, (
        f"a CLI importa {intrusos}, fora da superfície pública do núcleo. "
        "Se ela precisa disso, o núcleo é que está incompleto.")
    print("OK: a CLI só toca a superfície pública do núcleo")


def test_nao_existe_caminho_que_pule_o_julgamento():
    """Nenhuma função pública grava DXF sem passar por classify/select.

    O `convert()` fazia isso: extraía e escrevia direto, ignorando as opções.
    Era a única porta dos fundos do projeto, e a CLI existe justamente para
    provar que só há um caminho.
    """
    from pdftodxf import dxf_writer
    assert not hasattr(dxf_writer, "convert"), (
        "convert() voltou: ela grava DXF sem passar pelo select()")
    print("OK: não há porta dos fundos para gravar DXF sem filtro")


if __name__ == "__main__":
    test_flags_cobrem_todos_os_campos_de_exportoptions()
    test_converte_e_gera_dxf_valido()
    test_saida_padrao_fica_ao_lado_do_original()
    test_recusa_sobrescrever_sem_forcar()
    test_escala_e_plotagem_equivalentes_dao_o_mesmo()
    test_escala_ausente_ou_duplicada_e_erro_de_uso()
    test_pagina_inexistente_e_problema_de_arquivo()
    test_excluir_layer_morde()
    test_inspecionar_descreve_a_planta_sem_gravar()
    test_inspecionar_pagina_inexistente()
    test_cli_so_toca_a_superficie_publica_do_nucleo()
    test_nao_existe_caminho_que_pule_o_julgamento()
    print("Todos os testes da linha de comando passaram.")
