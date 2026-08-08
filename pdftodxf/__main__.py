"""Torna o pacote executável: `python -m pdftodxf`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
