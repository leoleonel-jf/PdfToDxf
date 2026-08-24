"""Rotas do serviço de conversão."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import time
import traceback
from pathlib import Path

import math

import fitz
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import (db, exportacao, identidade, jobs, limits, quotas, registros,
               storage)

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
async def enviar(request: Request, resposta: Response,
                 arquivo: UploadFile = File(...)) -> dict:
    """Recebe o PDF, confere o teto do plano, reserva a vaga e conta as páginas."""
    ident = identidade.resolver(request)
    identidade.gravar_cookie(resposta, ident,
                             seguro=request.url.scheme == "https")
    teto = quotas.limites(ident)["bytes"]

    # O `content-length` primeiro, e o teto de novo durante a leitura. O
    # primeiro recusa sem receber byte nenhum, que é o que a spec pede; o
    # segundo é a rede de segurança para quem mente no cabeçalho ou não o
    # manda.
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > teto:
        raise Recusa(413, f"O arquivo passa de {_mb(teto)} MB.", "tamanho",
                     teto_bytes=teto)

    job_id = storage.novo_id()
    try:
        quotas.reservar(ident, "arquivo", job_id)
    except quotas.SemVaga as e:
        raise _sem_vaga(e)

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
                if total > teto:
                    raise Recusa(413, f"O arquivo passa de {_mb(teto)} MB.",
                                 "tamanho", teto_bytes=teto)
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
        # O envio não virou trabalho nenhum: nada foi extraído, e a reserva não
        # tem mais o que confirmar. A vaga volta. Reserva que **fica** contando
        # é a de quem enviou um PDF bom e sumiu — essa consumiu disco e fila.
        quotas.soltar(job_id)
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
    ip = identidade.ip_do_pedido(request)
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


class Recusa(Exception):
    """Recusa com `codigo` no corpo, e não só `detail`.

    O `HTTPException` do FastAPI só sabe pôr `detail`, e a tela precisa
    distinguir "cota de arquivos" de "cota de downloads" sem ler texto — texto
    muda, código não. O `extra` é o que cada recusa acrescenta: `libera_em` na
    cota, `teto_bytes` no tamanho.
    """

    def __init__(self, status: int, detail: str, codigo: str, **extra):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.codigo = codigo
        self.extra = extra


@app.exception_handler(Recusa)
def _recusa(request: Request, exc: Recusa):
    return JSONResponse(status_code=exc.status,
                        content={"detail": exc.detail, "codigo": exc.codigo,
                                 **exc.extra})


def _sem_vaga(e: quotas.SemVaga) -> Recusa:
    quando = ""
    if e.libera_em:
        # Hora local do servidor, que é a do usuário nesta implantação. A tela
        # reformata a partir de `libera_em`; este texto é o que sobra para quem
        # lê a resposta crua.
        quando = time.strftime(" A próxima vaga abre às %H:%M.",
                               time.localtime(e.libera_em))
    if e.tipo == "arquivo":
        detalhe = ("Você já enviou o máximo de arquivos permitido nas últimas "
                   "horas." + quando)
        return Recusa(429, detalhe, "cota_arquivos", libera_em=e.libera_em)
    detalhe = ("Você já gerou o máximo de arquivos DXF permitido nas últimas "
               "horas. Baixar de novo um DXF que você já gerou continua "
               "liberado." + quando)
    return Recusa(429, detalhe, "cota_downloads", libera_em=e.libera_em)


class PedidoDeExportacao(BaseModel):
    # `allow_inf_nan=False` não é zelo: `gt=0.0` sozinho deixa passar Infinity,
    # que o JSON aceita, e o DXF sai com coordenadas infinitas. O nan já caía
    # aqui por acidente, porque `nan > 0` é falso.
    escala: float = Field(gt=0.0, allow_inf_nan=False)
    unidade: str = Field(pattern="^(mm|cm|m)$")
    opcoes: Opcoes = Field(default_factory=Opcoes)


@app.post("/api/jobs/{job_id}/pages/{pagina}/export")
def exportar(job_id: str, pagina: int, pedido: PedidoDeExportacao,
             request: Request, resposta: Response) -> dict:
    # Pelo cache.pickle e não pela pasta: é dele que a exportação vive, e sem a
    # conferência o `pickle.load` estouraria num 500 sem explicação.
    _arquivo_da_pagina(job_id, pagina, "cache.pickle")

    opcoes = pedido.opcoes.model_dump()
    ch = exportacao.chave(pagina, pedido.escala, pedido.unidade, opcoes)

    # A ordem é lei: chave, arquivo, e só então cota. Combinação já gerada nem
    # pergunta se há vaga — é o que faz repetir sair de graça. Consultar a cota
    # antes recusaria a reexportação de quem está sem vaga, contrariando a
    # promessa; gerar antes queimaria CPU para terminar em 429.
    ja_existe = exportacao.caminho_do_dxf(job_id, pagina, ch).exists()
    referencia = f"{job_id}:{ch}"

    if not ja_existe:
        ident = identidade.resolver(request)
        identidade.gravar_cookie(resposta, ident,
                                 seguro=request.url.scheme == "https")
        try:
            quotas.reservar(ident, "download", referencia)
        except quotas.SemVaga as e:
            raise _sem_vaga(e)

    try:
        ch, _caminho, do_cache, entidades = exportacao.gerar(
            job_id, pagina, pedido.escala, pedido.unidade, opcoes)
    except Exception:
        # Falhou ao gerar: o usuário não levou DXF nenhum, e não paga por isso.
        quotas.soltar(referencia)
        raise

    if not ja_existe:
        quotas.confirmar(referencia)
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
