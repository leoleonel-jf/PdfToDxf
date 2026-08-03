"""Rotas do serviço de conversão."""

from __future__ import annotations

import os
import shutil

import fitz
from fastapi import FastAPI, File, HTTPException, UploadFile

from . import jobs, limits, storage

PEDACO = 1024 * 1024   # 1 MB por leitura do envio

app = FastAPI(title="PdfToDxf", docs_url=None, redoc_url=None)


def _mb(n: int) -> int:
    return n // (1024 * 1024)


@app.post("/api/jobs")
async def enviar(arquivo: UploadFile = File(...)) -> dict:
    """Recebe o PDF, confere o teto de tamanho e conta as páginas."""
    job_id = storage.novo_id()
    destino = storage.pasta(job_id)
    destino.mkdir(parents=True, exist_ok=True)
    origem = destino / "origem.pdf"

    total = 0
    try:
        with open(origem, "wb") as saida:
            while True:
                pedaco = await arquivo.read(PEDACO)
                if not pedaco:
                    break
                total += len(pedaco)
                if total > limits.TETO_PDF_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"O arquivo passa de {_mb(limits.TETO_PDF_BYTES)} MB.")
                saida.write(pedaco)

        if total == 0:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")

        try:
            with fitz.open(origem) as doc:
                n_paginas = doc.page_count
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Não consegui abrir o arquivo como PDF.")
    except Exception:
        shutil.rmtree(destino, ignore_errors=True)
        raise

    nome = os.path.basename(arquivo.filename or "planta.pdf")
    ficha = storage.criar_trabalho(job_id, nome, n_paginas, total)
    return {"job_id": job_id, "n_paginas": n_paginas, "nome": ficha["nome"]}


def _ficha_ou_404(job_id: str) -> dict:
    try:
        storage.validar_id(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identificador inválido.")
    ficha = storage.ler_ficha(job_id)
    if ficha is None:
        raise HTTPException(status_code=404, detail="Trabalho não encontrado.")
    return ficha


@app.get("/api/jobs/{job_id}")
def consultar(job_id: str) -> dict:
    return _ficha_ou_404(job_id)


@app.post("/api/jobs/{job_id}/pages/{pagina}")
def extrair_pagina(job_id: str, pagina: int) -> dict:
    ficha = _ficha_ou_404(job_id)
    if pagina < 1 or pagina > ficha["n_paginas"]:
        raise HTTPException(
            status_code=404,
            detail=f"O documento tem {ficha['n_paginas']} página(s).")
    return jobs.pedir_extracao(job_id, pagina)


@app.get("/api/jobs/{job_id}/pages/{pagina}")
def estado_da_pagina(job_id: str, pagina: int) -> dict:
    _ficha_ou_404(job_id)
    atual = jobs.estado(job_id, pagina)
    if atual is None:
        raise HTTPException(status_code=404, detail="Página não solicitada.")
    return atual
