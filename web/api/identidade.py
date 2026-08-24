"""Quem está pedindo, e quais baldes de cota aquele pedido consome.

Logado é **um balde só** — a conta já é a identidade, e consultar IP e
impressão faria dois colegas do mesmo escritório dividirem a cota que cada um
pagou com um cadastro.

Visitante são **três**, com tetos diferentes: o cookie carrega a cota
anunciada, e IP e impressão são tetos folgados (`PDFTODXF_COTA_FOLGA`, padrão
4). O pedido passa se os três couberem, e o consumo é gravado nos três. O
cookie sozinho não tapa o furo de limpar o cookie e repetir; o IP sozinho faria
o escritório inteiro dividir cinco arquivos.

**A ordem de `baldes` é parte do contrato:** o primeiro é sempre o balde que
identifica quem pede — `cookie:` no visitante, `usuario:` no logado. `quotas`
usa esse primeiro balde como chave de idempotência do consumo, então trocar a
ordem faria a mesma identidade pagar duas vezes pelo mesmo trabalho.

**Este módulo não importa `auth`.** Ele precisa saber se há sessão, e `auth`
precisa do IP para o teto de contas por dia — seria um ciclo. Quem chama
resolve a sessão e passa o `dono`.
"""

from __future__ import annotations

import os
import re
import secrets
from typing import NamedTuple

from . import db

COOKIE = "pdftodxf_visitante"
PRAZO_DO_COOKIE_S = 365 * 24 * 60 * 60
FOLGA_PADRAO = 4
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Balde(NamedTuple):
    chave: str          # já com `db.marca` aplicada
    folga: int          # multiplicador do teto deste balde


class Dono(NamedTuple):
    id: int
    confirmado: bool


class Identidade(NamedTuple):
    tipo: str                       # "logado" | "visitante"
    usuario_id: int | None
    confirmado: bool
    baldes: tuple[Balde, ...]
    cookie_novo: str | None         # a gravar na resposta, se houver


def _folga() -> int:
    try:
        valor = int(os.environ.get("PDFTODXF_COTA_FOLGA", FOLGA_PADRAO))
    except ValueError:
        valor = FOLGA_PADRAO
    return max(1, valor)


def ip_do_pedido(request) -> str:
    """O endereço do cliente, contando `X-Forwarded-For` da direita para a esquerda.

    `PDFTODXF_PROXIES` diz quantos proxies confiáveis estão à frente. O padrão
    é `0`: **não confie no cabeçalho**, use o endereço da conexão. Sem esse
    contador qualquer um manda `X-Forwarded-For: 1.2.3.4` e a cota do IP vira
    decorativa — e o erro é silencioso, porque tudo continua funcionando.
    """
    cliente = getattr(request, "client", None)
    direto = cliente.host if cliente else ""
    try:
        proxies = int(os.environ.get("PDFTODXF_PROXIES", "0"))
    except ValueError:
        proxies = 0
    if proxies <= 0:
        return direto
    cru = request.headers.get("x-forwarded-for", "")
    lista = [p.strip() for p in cru.split(",") if p.strip()]
    if len(lista) >= proxies:
        return lista[-proxies]
    return direto


def impressao_do_pedido(request) -> str | None:
    """O hash que o navegador mandou em `X-Impressao`, se for o formato certo.

    Qualquer outro formato é ignorado **sem erro**: navegador com JS desligado,
    extensão de privacidade ou cliente que não manda o cabeçalho ficam com a
    cota do cookie e do IP, que é a cota anunciada. Quem escolhe se proteger
    não pode ser barrado por isso.
    """
    valor = (request.headers.get("x-impressao") or "").strip().lower()
    return valor if _HEX64.match(valor) else None


def _cookie_valido(request) -> str | None:
    guardado = request.cookies.get(COOKIE)
    return db.conferir(guardado) if guardado else None


def resolver(request, dono: Dono | None = None) -> Identidade:
    if dono is not None:
        return Identidade(tipo="logado", usuario_id=dono.id,
                          confirmado=dono.confirmado,
                          baldes=(Balde(db.marca(f"usuario:{dono.id}"), 1),),
                          cookie_novo=None)

    valor = _cookie_valido(request)
    cookie_novo = None
    if valor is None:
        valor = secrets.token_urlsafe(24)
        cookie_novo = db.assinar(valor)

    folga = _folga()
    # O balde do cookie **em primeiro**: `quotas._consumir` toma `baldes[0]`
    # como o balde que identifica o pedido e o usa como chave de idempotência.
    # IP e impressão são compartilhados — se um deles viesse primeiro, dois
    # visitantes do mesmo escritório dividiriam a idempotência um do outro.
    baldes = [Balde(db.marca(f"cookie:{valor}"), 1)]
    ip = ip_do_pedido(request)
    if ip:
        baldes.append(Balde(db.marca(f"ip:{ip}"), folga))
    impressao = impressao_do_pedido(request)
    if impressao:
        baldes.append(Balde(db.marca(f"impressao:{impressao}"), folga))

    return Identidade(tipo="visitante", usuario_id=None, confirmado=False,
                      baldes=tuple(baldes), cookie_novo=cookie_novo)


def gravar_cookie(resposta, ident: Identidade, seguro: bool = False) -> None:
    """Grava o cookie do visitante, se ele for novo. Idempotente."""
    if not ident.cookie_novo:
        return
    resposta.set_cookie(COOKIE, ident.cookie_novo, max_age=PRAZO_DO_COOKIE_S,
                        httponly=True, samesite="lax", secure=seguro, path="/")
