"""Ponto de entrada do PdfToDxf.

Uso:
    python main.py              # abre a janela
    python main.py planta.pdf   # abre a janela já com o PDF carregado
"""

import sys

from pdftodxf.gui import run

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
