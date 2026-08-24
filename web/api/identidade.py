"""Quem está pedindo, e quais baldes de cota aquele pedido consome.

Logado **e confirmado** é **um balde só** — a conta já é a identidade, e
consultar IP e impressão faria dois colegas do mesmo escritório dividirem a cota
que cada um pagou com um cadastro.

**Conta sem o endereço confirmado fica nos baldes de visitante**, os mesmos
três, com as mesmas folgas. É o que a confirmação compra: trocar três baldes
compartilhados por um balde próprio. Sem isso, cadastrar-se com um endereço
descartável devolveria um balde novo e privado ao visitante que acabou de
esgotar a cota — cinco arquivos a mais por cadastro, num laço de custo zero e
sem passar por caixa de entrada nenhuma. Os *números* já eram os de visitante
(`quotas.limites`); o furo era o balde.

Visitante são **três**, com tetos diferentes: o cookie carrega a cota
anunciada, e IP e impressão são tetos folgados (`PDFTODXF_COTA_FOLGA`, padrão
4). O pedido passa se os três couberem, e o consumo é gravado nos três. O
cookie sozinho não tapa o furo de limpar o cookie e repetir; o IP sozinho faria
o escritório inteiro dividir cinco arquivos.

**A ordem de `baldes` é parte do contrato:** o primeiro é sempre o balde que
identifica quem pede — `cookie:` no visitante **e no logado sem confirmar**,
`usuario:` só no logado **confirmado**. `quotas` usa esse primeiro balde como
chave de idempotência do consumo, então trocar a ordem faria a mesma
identidade pagar duas vezes pelo mesmo trabalho.

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
    return db.conferir(guardado, db.DOMINIO_COOKIE_VISITANTE) if guardado else None


def _baldes_de_visitante(request) -> tuple[tuple[Balde, ...], str | None]:
    """Os três baldes compartilhados, e o cookie a emitir se ainda não houver."""
    valor = _cookie_valido(request)
    cookie_novo = None
    if valor is None:
        valor = secrets.token_urlsafe(24)
        cookie_novo = db.assinar(valor, db.DOMINIO_COOKIE_VISITANTE)

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
    return tuple(baldes), cookie_novo


def resolver(request, dono: Dono | None = None) -> Identidade:
    if dono is not None and dono.confirmado:
        # **Só o confirmado** ganha balde próprio. É exatamente isso que a
        # confirmação do endereço compra: sair dos três baldes compartilhados
        # com o resto do escritório e passar a ter um balde só seu.
        return Identidade(tipo="logado", usuario_id=dono.id, confirmado=True,
                          baldes=(Balde(db.marca(f"usuario:{dono.id}"), 1),),
                          cookie_novo=None)

    baldes, cookie_novo = _baldes_de_visitante(request)

    if dono is not None:
        # Conta sem confirmar: **os mesmos baldes de um visitante**, com as
        # mesmas folgas. Um balde `usuario:<id>` aqui seria um balde novo e
        # vazio a cada cadastro — quem esgotou a cota criaria uma conta com um
        # endereço descartável, não abriria e-mail nenhum, e voltaria com cinco
        # arquivos. É o reinício barato que os três baldes existem para impedir.
        #
        # O `tipo`, o `usuario_id` e o `confirmado` continuam os de um logado:
        # a tela precisa mostrar o e-mail e a linha "falta confirmar seu
        # e-mail". **Só a lista de baldes muda** — e o `cookie_novo` sai para
        # ele como para qualquer visitante, porque agora ele depende do balde
        # do cookie para ser contado.
        return Identidade(tipo="logado", usuario_id=dono.id, confirmado=False,
                          baldes=baldes, cookie_novo=cookie_novo)

    return Identidade(tipo="visitante", usuario_id=None, confirmado=False,
                      baldes=baldes, cookie_novo=cookie_novo)


def gravar_cookie(resposta, ident: Identidade, seguro: bool = False) -> None:
    """Grava o cookie do visitante, se ele for novo. Idempotente."""
    if not ident.cookie_novo:
        return
    resposta.set_cookie(COOKIE, ident.cookie_novo, max_age=PRAZO_DO_COOKIE_S,
                        httponly=True, samesite="lax", secure=seguro, path="/")
