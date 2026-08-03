"""Layout em disco dos trabalhos e ciclo de vida dos arquivos.

    <raiz>/<job_id>/
        origem.pdf        apagado assim que a extração termina
        ficha.json        nome original, páginas, tamanho, hora de criação
        p<N>/             uma pasta por página extraída

`job_id` é hexadecimal de 32 caracteres. Nada que venha do cliente entra num
caminho sem passar por `validar_id`.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

_ID = re.compile(r"^[0-9a-f]{32}$")


def raiz() -> Path:
    """Pasta de dados, de `PDFTODXF_DADOS` ou `./dados`."""
    caminho = Path(os.environ.get("PDFTODXF_DADOS", "dados"))
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def validar_id(job_id: str) -> str:
    """Devolve o id se for válido; levanta ValueError se não for."""
    if not _ID.match(job_id or ""):
        raise ValueError("identificador de trabalho inválido")
    return job_id


def pasta(job_id: str) -> Path:
    return raiz() / validar_id(job_id)


def pasta_pagina(job_id: str, pagina: int) -> Path:
    if not isinstance(pagina, int) or pagina < 1 or pagina > 10_000:
        raise ValueError("número de página inválido")
    return pasta(job_id) / f"p{pagina}"


def novo_id() -> str:
    return uuid.uuid4().hex


def criar_trabalho(job_id: str, nome: str, n_paginas: int, tamanho: int,
                   agora: float | None = None) -> dict:
    """Grava a ficha do trabalho e devolve o que ela contém."""
    ficha = {
        "job_id": job_id,
        "nome": nome,
        "n_paginas": n_paginas,
        "tamanho": tamanho,
        "criado_em": time.time() if agora is None else agora,
        "paginas": {},
    }
    gravar_ficha(job_id, ficha)
    return ficha


def caminho_ficha(job_id: str) -> Path:
    return pasta(job_id) / "ficha.json"


def gravar_ficha(job_id: str, ficha: dict) -> None:
    p = caminho_ficha(job_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    temporario = p.with_suffix(".json.tmp")
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(ficha, f, ensure_ascii=False)
    os.replace(temporario, p)   # troca atômica: nunca deixa ficha pela metade


def ler_ficha(job_id: str) -> dict | None:
    p = caminho_ficha(job_id)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)
