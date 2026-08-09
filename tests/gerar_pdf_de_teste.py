"""Grava em disco o PDF sintético que a conferência da tela e o teste de ponta
a ponta enviam.

Sintético de propósito, e não uma planta do acervo: plantas de cliente não vão
para a árvore servida pelo dev server nem para o repositório. `*.pdf` está no
`.gitignore`, então o arquivo gerado não é versionado — ele é regerado a cada
execução, o que também evita que envelheça em silêncio.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_roundtrip import make_test_pdf

PADRAO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "web", "frontend", "public", "planta-de-teste.pdf")


def main() -> None:
    destino = sys.argv[1] if len(sys.argv) > 1 else PADRAO
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    make_test_pdf(destino)
    print(f"PDF de teste gravado: {destino} ({os.path.getsize(destino)} bytes)")


if __name__ == "__main__":
    main()
