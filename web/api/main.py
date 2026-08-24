"""Rotas do serviço de conversão."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import traceback
from pathlib import Path

import math

import fitz
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import db, exportacao, jobs, limits, registros, storage

PEDACO = 1024 * 1024   # 1 MB por leitura do envio
INTERVALO_LIMPEZA = 10 * 60   # 10 minutos


async def _limpeza_periodica() -> None:
    while True:
        await asyncio.sleep(INTERVALO_LIMPEZA)
        try:
            # Em thread: a limpeza percorre o disco e travaria o laço de eventos.
            relato = await asyncio.to_thread(storage.limpar)
            if relato["expirados"] or relato["por_cota"]:
                print(f"limpeza: {len(relato['expirados'])} vencidos, "
                      f"{len(relato['por_cota'])} por cota")
            apagados = await asyncio.to_thread(registros.expurgar)
            if apagados:
                print(f"limpeza: {len(apagados)} registros com mais de 1 ano")
            do_banco = await asyncio.to_thread(db.limpar)
            if do_banco["consumo"] or do_banco["tokens"]:
                print(f"limpeza: {do_banco['consumo']} consumos e "
                      f"{do_banco['tokens']} tokens vencidos")
        except Exception:
            traceback.print_exc()   # a limpeza nunca pode derrubar o serviço


@contextlib.asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    # As tabelas nascem na subida, e não no primeiro pedido: assim um erro de
    # permissão no arquivo do banco aparece ao subir, e não na cara do primeiro
    # usuário.
    await asyncio.to_thread(lambda: db.criar_tabelas(db.conexao()))
    tarefa = asyncio.create_task(_limpeza_periodica())
    try:
        yield
    finally:
        tarefa.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarefa


# `lifespan=` e não `@app.on_event`: os decoradores de evento estão obsoletos
# desde o FastAPI 0.109 e sujariam a saída dos testes com DeprecationWarning.
app = FastAPI(title="PdfToDxf", docs_url=None, redoc_url=None,
              lifespan=ciclo_de_vida)


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
def extrair_pagina(job_id: str, pagina: int, request: Request) -> dict:
    ficha = _ficha_ou_404(job_id)
    if pagina < 1 or pagina > ficha["n_paginas"]:
        raise HTTPException(
            status_code=404,
            detail=f"O documento tem {ficha['n_paginas']} página(s).")
    ip = request.client.host if request.client else ""
    return jobs.pedir_extracao(job_id, pagina, ip=ip, conta="")


@app.get("/api/jobs/{job_id}/pages/{pagina}")
def estado_da_pagina(job_id: str, pagina: int) -> dict:
    _ficha_ou_404(job_id)
    atual = jobs.estado(job_id, pagina)
    if atual is None:
        raise HTTPException(status_code=404, detail="Página não solicitada.")
    return atual


def _pagina_pronta(job_id: str, pagina: int) -> Path:
    """Pasta de uma página que já terminou a extração."""
    _ficha_ou_404(job_id)
    atual = jobs.estado(job_id, pagina)
    if atual is None:
        raise HTTPException(status_code=404, detail="Página não solicitada.")
    if atual.get("situacao") != "pronta":
        raise HTTPException(status_code=409,
                            detail="A página ainda não está pronta.")
    return storage.pasta_pagina(job_id, pagina)


def _arquivo_da_pagina(job_id: str, pagina: int, nome: str) -> Path:
    """Caminho de um arquivo de uma página que já ficou pronta."""
    caminho = _pagina_pronta(job_id, pagina) / nome
    if not caminho.exists():
        # Página marcada como pronta sem o arquivo é defeito nosso; sem esta
        # conferência o `FileResponse` estouraria no meio do envio, e o cliente
        # veria a conexão cair em vez de um erro.
        raise HTTPException(status_code=500,
                            detail="Arquivo da página não encontrado.")
    return caminho


@app.get("/api/jobs/{job_id}/pages/{pagina}/meta.json")
def meta_da_pagina(job_id: str, pagina: int) -> FileResponse:
    return FileResponse(_arquivo_da_pagina(job_id, pagina, "meta.json"),
                        media_type="application/json")


@app.get("/api/jobs/{job_id}/pages/{pagina}/geometry.bin")
def geometria(job_id: str, pagina: int, parte: str = "esqueleto") -> FileResponse:
    if parte not in ("esqueleto", "detalhe"):
        raise HTTPException(status_code=400,
                            detail="A parte tem que ser 'esqueleto' ou 'detalhe'.")
    return FileResponse(_arquivo_da_pagina(job_id, pagina, f"{parte}.bin"),
                        media_type="application/octet-stream")


class Opcoes(BaseModel):
    excluded_layers: list[str] = Field(default_factory=list)
    drop_fills: bool = False
    min_len_mm: float = Field(default=0.0, ge=0.0, le=1000.0)
    dedup: bool = False
    join_polylines: bool = False
    round_coords: bool = False


def _serializavel(valor):
    """Troca por texto o que não cabe em JSON, mantendo o resto intacto."""
    if isinstance(valor, float) and not math.isfinite(valor):
        return repr(valor)
    if isinstance(valor, dict):
        return {k: _serializavel(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_serializavel(v) for v in valor]
    if isinstance(valor, (str, int, bool, type(None))):
        return valor
    return repr(valor)


@app.exception_handler(RequestValidationError)
def _erro_de_validacao(request: Request, exc: RequestValidationError):
    """422 com o detalhe saneado.

    O relato padrão devolve o valor recebido junto da queixa. Quando esse valor
    é `inf` ou `nan` — exatamente o caso que se quer recusar — o codificador de
    JSON estoura ao montar a resposta, e a recusa vira um 500 sem explicação.
    """
    return JSONResponse(status_code=422,
                        content={"detail": _serializavel(exc.errors())})


class PedidoDeExportacao(BaseModel):
    # `allow_inf_nan=False` não é zelo: `gt=0.0` sozinho deixa passar Infinity,
    # que o JSON aceita, e o DXF sai com coordenadas infinitas. O nan já caía
    # aqui por acidente, porque `nan > 0` é falso.
    escala: float = Field(gt=0.0, allow_inf_nan=False)
    unidade: str = Field(pattern="^(mm|cm|m)$")
    opcoes: Opcoes = Field(default_factory=Opcoes)


@app.post("/api/jobs/{job_id}/pages/{pagina}/export")
def exportar(job_id: str, pagina: int, pedido: PedidoDeExportacao) -> dict:
    # Pelo cache.pickle e não pela pasta: é dele que a exportação vive, e sem a
    # conferência o `pickle.load` estouraria num 500 sem explicação.
    _arquivo_da_pagina(job_id, pagina, "cache.pickle")
    ch, _caminho, do_cache, entidades = exportacao.gerar(
        job_id, pagina, pedido.escala, pedido.unidade, pedido.opcoes.model_dump())
    return {
        "chave": ch,
        "url": f"/api/download/{job_id}/{ch}",
        "cache": do_cache,
        "entidades": entidades,
    }


@app.get("/api/download/{job_id}/{ch}")
def baixar(job_id: str, ch: str) -> FileResponse:
    ficha = _ficha_ou_404(job_id)
    for pagina in ficha.get("paginas", {}):
        try:
            caminho = exportacao.caminho_do_dxf(job_id, int(pagina), ch)
        except ValueError:
            raise HTTPException(status_code=400, detail="Chave inválida.")
        if caminho.exists():
            nome = os.path.splitext(ficha["nome"])[0] + ".dxf"
            return FileResponse(caminho, media_type="application/dxf",
                                filename=nome)
    raise HTTPException(status_code=404, detail="Arquivo não encontrado.")


from fastapi.staticfiles import StaticFiles

PASTA_ESTATICOS = Path(__file__).resolve().parents[1] / "frontend" / "dist"

# A montagem vem por último de propósito: o FastAPI resolve as rotas na ordem
# em que foram declaradas, e um `/` montado antes engoliria `/api/...`.
#
# O `if` existe porque quem mexe só no Python não compila o frontend, e o
# serviço tem de subir do mesmo jeito — inclusive nos testes de API.
if PASTA_ESTATICOS.is_dir():
    app.mount("/", StaticFiles(directory=PASTA_ESTATICOS, html=True),
              name="frontend")
