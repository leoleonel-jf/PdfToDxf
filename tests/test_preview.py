"""Testes da prévia: o canvas nunca pode ficar sem imagem durante o redesenho
(a "piscada branca") nem acumular imagens empilhadas."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_roundtrip import make_test_pdf

from pdftodxf.extractor import extract_page
from pdftodxf.gui import App


def _images(app):
    return [i for i in app.canvas.find_all() if app.canvas.type(i) == "image"]


def _pump(app, secs, watch=False):
    """Bombeia eventos da UI; com watch, retorna o menor nº de imagens visto."""
    lowest = 99
    end = time.time() + secs
    while time.time() < end:
        app.update()
        if watch:
            lowest = min(lowest, len(_images(app)))
        time.sleep(0.02)
    return lowest


def test_preview_never_blanks():
    tmp = tempfile.mkdtemp()
    pdf = os.path.join(tmp, "planta.pdf")
    make_test_pdf(pdf)

    app = App()
    app.update()
    app.open_pdf(pdf)
    app.update()
    app.extraction = extract_page(pdf)
    app._open_export_dialog()
    app.update()
    dlg = app.export_dialog

    _pump(app, 1.5)
    assert app._preview_entities is not None, "prévia deveria estar ativa"
    assert len(_images(app)) == 1, "deveria haver exatamente 1 imagem de fundo"

    # alternar opções não pode esvaziar o canvas em nenhum instante
    for nome, var in (("fills", dlg.var_fills), ("dedup", dlg.var_dedup),
                      ("join", dlg.var_join), ("fills", dlg.var_fills)):
        var.set(not var.get())
        dlg._on_change()
        lowest = _pump(app, 1.6, watch=True)
        assert lowest >= 1, f"canvas ficou vazio ao alternar {nome} (piscada branca)"
        assert len(_images(app)) == 1, f"imagens empilhadas após {nome}"

    # pan durante a prévia: reposiciona a imagem antiga, não apaga
    app.ox += 40
    app.oy += 25
    app._schedule_render()
    lowest = _pump(app, 1.6, watch=True)
    assert lowest >= 1, "canvas ficou vazio durante o pan"
    assert len(_images(app)) == 1

    # desligar a prévia volta ao PDF sem empilhar imagens
    dlg.var_preview.set(False)
    dlg._on_change()
    _pump(app, 1.5)
    assert app._preview_entities is None
    assert len(_images(app)) == 1

    app.destroy()
    print("OK: prévia sem piscada branca e sem imagens empilhadas.")


if __name__ == "__main__":
    test_preview_never_blanks()
    print("Todos os testes de prévia passaram.")
