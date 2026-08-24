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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import (auth, db, enviador, exportacao, identidade, jobs, quotas,
               registros, storage)

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
            # Os e-mails gravados em arquivo trazem o token **em claro**. Depois
            # de 48 h a linha do token já saiu do banco pelo `db.limpar` e o
            # arquivo é inerte, mas guardar segredo vencido para sempre é
            # sujeira. `storage.limpar` não pega esta pasta de propósito — ela
            # não passa por `validar_id` — então o expurgo é do próprio módulo.
            cartas = await asyncio.to_thread(enviador.expurgar)
            if cartas:
                print(f"limpeza: {len(cartas)} e-mails gravados em arquivo")
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
    # Pré-aquece o hash de mentira do `queimar_tempo`: sem isto, a primeira
    # chamada depois da subida paga `hash_senha` (~120 ms) *e* `conferir_senha`
    # (~110 ms) — 239 ms contra ~110 ms das chamadas seguintes e ~167 ms de um
    # `conferir_senha` real —, um oráculo de tiro único no primeiro login com
    # e-mail inexistente. Em thread pelo mesmo motivo das tabelas acima: um
    # `scrypt` de ~100 ms no laço de eventos atrasaria a subida.
    await asyncio.to_thread(auth.queimar_tempo)
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


def _gravar_sessao(resposta: Response, uid: int, seguro: bool) -> None:
    resposta.set_cookie(auth.COOKIE_SESSAO, auth.criar_sessao(uid),
                        max_age=auth.PRAZO_SESSAO_S, httponly=True,
                        samesite="lax", secure=seguro, path="/")


def quem_pede(request: Request, resposta: Response) -> identidade.Identidade:
    """A identidade do pedido, com a sessão já resolvida e o cookie renovado.

    Um lugar só. Cada rota resolvendo sessão por conta própria seria a receita
    para uma delas esquecer, e a cota do logado virar cota de visitante em
    silêncio — defeito que nenhum teste de unidade pega.

    **Toca o banco** (`auth.por_id`). Numa rota `async def` ela tem de ir para
    `asyncio.to_thread`, como `quotas.reservar` — ver o comentário em `enviar`.
    """
    seguro = request.url.scheme == "https"
    dono = auth.dono_da_sessao(request)
    if dono is not None and auth.precisa_renovar(request):
        _gravar_sessao(resposta, dono.id, seguro)
    ident = identidade.resolver(request, dono=dono)
    identidade.gravar_cookie(resposta, ident, seguro=seguro)
    return ident


@app.post("/api/jobs")
async def enviar(request: Request, resposta: Response,
                 arquivo: UploadFile = File(...)) -> dict:
    """Recebe o PDF, confere o teto do plano, reserva a vaga e conta as páginas."""
    # Em thread pelo mesmo motivo do `reservar` lá embaixo: `quem_pede` lê o
    # banco (`auth.por_id`), e esta rota é `async def` — ela roda no fio do laço
    # de eventos. O `SELECT` em si é barato, mas quem paga caro é a **primeira**
    # chamada de cada fio: `db.conexao()` abre a conexão com
    # `PRAGMA journal_mode=WAL` e `criar_tabelas`, que pedem o lock de escrita
    # com `busy_timeout` de 5 s. Hoje nenhum fio de laço de eventos tem conexão
    # de SQLite (a subida e a limpeza já usam `to_thread`), e manter esse
    # invariante é mais simples de sustentar do que auditar consulta a consulta.
    ident = await asyncio.to_thread(quem_pede, request, resposta)
    teto = quotas.limites(ident)["bytes"]

    # O `content-length` primeiro, e o teto de novo durante a leitura. O
    # primeiro recusa sem receber byte nenhum, que é o que a spec pede; o
    # segundo é a rede de segurança para quem mente no cabeçalho ou não o
    # manda.
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > teto:
        raise Recusa(413, f"O arquivo passa de {_mb(teto)} MB.", "tamanho",
                     ident=ident, teto_bytes=teto)

    job_id = storage.novo_id()
    try:
        # Em thread: `reservar` abre `BEGIN IMMEDIATE` com `busy_timeout` de
        # 5 s, e esta rota é `async def` — ela roda **no fio do laço de
        # eventos**. Numa rajada de envios do mesmo IP os escritores se
        # serializam, e o bloqueio pararia o laço inteiro junto, inclusive os
        # `GET` de estado que a tela faz em polling. As rotas síncronas do
        # FastAPI já rodam num pool de threads e não têm o problema.
        #
        # `db.conexao()` é por fio, então a thread do pool usa a conexão dela e
        # não a do laço — é exatamente para isso que a conexão por fio existe.
        # A transação abre e fecha dentro da mesma chamada (`_consumir` sempre
        # sai por `COMMIT` ou `ROLLBACK`), então nada fica pendurado na thread.
        await asyncio.to_thread(quotas.reservar, ident, "arquivo", job_id)
    except quotas.SemVaga as e:
        raise _sem_vaga(e, ident)

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
                                 "tamanho", ident=ident, teto_bytes=teto)
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
        #
        # Em thread pelo mesmo motivo do `reservar` acima: é escrita no banco
        # numa rota `async def`.
        await asyncio.to_thread(quotas.soltar, job_id)
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

    A `ident` viaja junto porque o handler monta uma resposta nova e o
    `Response` que a rota recebeu por injeção não chega até lá: sem ela, o
    visitante recusado sairia sem cookie. Vem declarada, e não dentro de
    `**extra`, para não vazar para o corpo da resposta.
    """

    def __init__(self, status: int, detail: str, codigo: str,
                 ident=None, **extra):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.codigo = codigo
        self.ident = ident
        self.extra = extra


@app.exception_handler(Recusa)
def _recusa(request: Request, exc: Recusa):
    resposta = JSONResponse(status_code=exc.status,
                            content={"detail": exc.detail,
                                     "codigo": exc.codigo, **exc.extra})
    # O cookie pendente tem de sobreviver à recusa. Sem isto o visitante que
    # leva 413 ou 429 nunca recebe cookie nenhum e recomeça num balde novo a
    # cada tentativa: o balde do cookie viraria descartável, e só o do IP
    # seguraria o furo. Pela mesma `gravar_cookie` da rota, para não haver duas
    # versões da regra do cookie.
    if exc.ident is not None:
        identidade.gravar_cookie(resposta, exc.ident,
                                 seguro=request.url.scheme == "https")
    return resposta


def _sem_vaga(e: quotas.SemVaga, ident=None) -> Recusa:
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
        return Recusa(429, detalhe, "cota_arquivos", ident=ident,
                      libera_em=e.libera_em)
    detalhe = ("Você já gerou o máximo de arquivos DXF permitido nas últimas "
               "horas. Baixar de novo um DXF que você já gerou continua "
               "liberado." + quando)
    return Recusa(429, detalhe, "cota_downloads", ident=ident,
                  libera_em=e.libera_em)


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
        # Direto, sem `to_thread`: esta rota é síncrona, e o FastAPI já a roda
        # no pool de threads.
        ident = quem_pede(request, resposta)
        try:
            quotas.reservar(ident, "download", referencia)
        except quotas.SemVaga as e:
            raise _sem_vaga(e, ident)

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


class PedidoDeRegistro(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    senha: str = Field(min_length=8, max_length=200)


@app.post("/api/auth/registro")
def registrar(pedido: PedidoDeRegistro, request: Request) -> dict:
    """Cria a conta e dispara o link. **A resposta é a mesma nos dois casos.**

    E-mail já cadastrado recebe um aviso, e não o link — assim o dono do
    endereço fica sabendo, e quem sondou não descobre nada.
    """
    if not auth.email_valido(pedido.email):
        # `Recusa` e não `HTTPException`: com `codigo` a tela distingue isto de
        # um 422 do Pydantic, que tem outro formato de corpo.
        raise Recusa(422, "E-mail inválido.", "email_invalido")

    ip = identidade.ip_do_pedido(request)
    uid = auth.criar_conta(pedido.email, pedido.senha, ip)
    if uid is None:
        # **Nada de `queimar_tempo` aqui.** `criar_conta` avalia
        # `hash_senha(senha)` como argumento do `INSERT`, ou seja, paga o
        # `scrypt` antes de o `IntegrityError` disparar — nos dois caminhos. É
        # isso que iguala os tempos. Um hash a mais neste ramo faria o e-mail
        # repetido custar o dobro do novo e criaria o oráculo de enumeração que
        # a resposta idêntica existe para fechar (medido: 2.13x, faixas sem
        # sobreposição).
        enviador.enviar(
            auth.normalizar(pedido.email),
            "Tentativa de cadastro no PdfToDxf",
            "Alguém tentou criar uma conta no PdfToDxf com este endereço, que "
            "já tem cadastro.\n\nSe foi você, entre normalmente em "
            f"{auth.url_base()}/ — e use 'Esqueci a senha' se precisar.\n\n"
            "Se não foi você, pode ignorar esta mensagem: nada mudou na sua "
            "conta.")
    else:
        token = auth.novo_token(uid, "confirmacao", auth.PRAZO_CONFIRMACAO_S)
        enviador.enviar(
            auth.normalizar(pedido.email),
            "Confirme seu endereço no PdfToDxf",
            "Para ativar a cota maior da sua conta, confirme este endereço:\n\n"
            f"{auth.url_base()}/api/auth/confirmar/{token}\n\n"
            "O link vale por 48 horas. Se você não pediu isto, ignore.")

    return {"ok": True,
            "mensagem": "Se este endereço puder receber, o e-mail já saiu. "
                        "Confira a caixa de entrada."}


@app.get("/api/auth/confirmar/{token}")
def confirmar(token: str):
    uid = auth.usar_token(token, "confirmacao")
    if uid is None:
        raise Recusa(400, "Este link não vale mais. Peça outro entrando na sua "
                          "conta.", "token_invalido")
    auth.confirmar_conta(uid)
    return RedirectResponse(url="/?confirmado=1", status_code=303)


class PedidoDeEntrada(BaseModel):
    # O mínimo da senha é `1`, e não `auth.SENHA_MINIMA`: quem já tem uma senha
    # curta de antes precisa poder entrar para trocá-la, e recusar por
    # comprimento aqui contaria pela porta dos fundos que aquele endereço não
    # tem senha curta cadastrada.
    email: str = Field(min_length=3, max_length=254)
    senha: str = Field(min_length=1, max_length=200)


@app.post("/api/auth/entrar")
def entrar(pedido: PedidoDeEntrada, request: Request,
           resposta: Response) -> dict:
    """Confere as credenciais e grava a sessão.

    **A recusa é a mesma nos dois casos**, em texto e em tempo: e-mail que não
    existe e senha errada saem por aqui com o mesmo status e o mesmo corpo.
    """
    linha = auth.por_email(pedido.email)
    if linha is None:
        # `scrypt` de mentira: sem ele, "não existe" responde em microssegundos
        # e "senha errada" em dezenas de milissegundos, e o cronômetro conta o
        # que a mensagem calou. **Aqui ele serve de verdade**, ao contrário do
        # cadastro, onde `criar_conta` já paga o hash nos dois caminhos.
        auth.queimar_tempo()
        raise Recusa(401, "E-mail ou senha não conferem.", "credenciais")

    if not auth.conferir_senha(pedido.senha, linha["senha"]):
        raise Recusa(401, "E-mail ou senha não conferem.", "credenciais")

    if auth.precisa_reescrever(linha["senha"]):
        auth.reescrever_senha(linha["id"], pedido.senha)

    _gravar_sessao(resposta, int(linha["id"]), request.url.scheme == "https")
    return {"email": linha["email"],
            "confirmado": linha["confirmado_em"] is not None}


@app.post("/api/auth/sair")
def sair(resposta: Response) -> dict:
    resposta.delete_cookie(auth.COOKIE_SESSAO, path="/")
    return {"ok": True}


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
