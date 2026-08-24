"""Pode? — a cota por janela deslizante.

Um registro por consumo, com a hora. A cota disponível é o limite menos o que
foi consumido na janela: **não existe virada em horário fixo**, e por isso não
existe a meia-noite em que todo mundo volta a enviar de uma vez.

Reservar e confirmar são coisas separadas porque PDF sem vetores e worker morto
por recurso não podem consumir cota. A transição é de mão única e idempotente,
e é isso que faz o caso misto sair certo: num documento em que a página 1 é
escaneada e a página 2 tem vetores, a página 1 solta e a página 2 cobra; na
ordem inversa, a página 2 confirma e a página 1 não desfaz.

Reserva nunca confirmada **continua contando** até sair da janela. Quem envia e
fecha a aba consumiu banda e disco; não há varredura de reserva órfã, porque a
janela deslizante já é o prazo.
"""

from __future__ import annotations

import os
import time

from . import db, limits

PADROES = {
    "arquivos": 5,
    "downloads": 15,
    "mb": 10,
    "arquivos_logado": 15,
    "downloads_logado": 45,
    "mb_logado": 100,
    "janela_h": 2,
}


class SemVaga(Exception):
    """Não cabe nesta janela. `libera_em` é quando a próxima vaga abre."""

    def __init__(self, tipo: str, libera_em: float | None):
        super().__init__(tipo, libera_em)
        self.tipo = tipo
        self.libera_em = libera_em


def _chave(nome: str) -> int:
    """O valor de `PDFTODXF_COTA_<NOME>`, ou o padrão. `0` é sem limite."""
    cru = os.environ.get(f"PDFTODXF_COTA_{nome.upper()}")
    if cru is None or cru.strip() == "":
        return PADROES[nome]
    try:
        return max(0, int(cru))
    except ValueError:
        # Chave escrita errada cai no padrão, que é seguro — e não em
        # "sem limite", que seria o modo de falhar caro.
        return PADROES[nome]


def janela_s() -> int:
    horas = _chave("janela_h") or PADROES["janela_h"]
    return horas * 60 * 60


def limites(ident) -> dict:
    """Os tetos do plano de quem está pedindo.

    Conta sem o endereço confirmado tem cota de visitante — é o que faz a
    confirmação valer alguma coisa.
    """
    if ident.tipo == "logado" and ident.confirmado:
        mb = _chave("mb_logado")
        return {
            "arquivos": _chave("arquivos_logado"),
            "downloads": _chave("downloads_logado"),
            # Nunca acima do teto técnico: a chave é do plano, o teto é do
            # servidor. Deixar a chave passar por cima abriria um caminho de
            # derrubar o site por configuração.
            "bytes": min(mb * 1024 * 1024, limits.TETO_PDF_BYTES),
        }
    mb = _chave("mb")
    return {
        "arquivos": _chave("arquivos"),
        "downloads": _chave("downloads"),
        "bytes": min(mb * 1024 * 1024, limits.TETO_PDF_BYTES),
    }


def _teto(ident, tipo: str, balde) -> int:
    base = limites(ident)["arquivos" if tipo == "arquivo" else "downloads"]
    return 0 if base == 0 else base * balde.folga


def _contar(con, balde: str, tipo: str, desde: float) -> int:
    linha = con.execute(
        "SELECT count(*) AS n FROM consumo "
        "WHERE balde = ? AND tipo = ? AND quando > ?",
        (balde, tipo, desde)).fetchone()
    return int(linha["n"])


def _libera_em(con, balde: str, tipo: str, desde: float) -> float | None:
    """Quando abre a próxima vaga: a linha mais antiga da janela + a janela."""
    linha = con.execute(
        "SELECT min(quando) AS q FROM consumo "
        "WHERE balde = ? AND tipo = ? AND quando > ?",
        (balde, tipo, desde)).fetchone()
    return None if linha["q"] is None else float(linha["q"]) + janela_s()


def _consumir(ident, tipo: str, referencia: str, estado: str,
              agora: float | None) -> None:
    agora = time.time() if agora is None else agora
    desde = agora - janela_s()
    con = db.conexao()

    # `BEGIN IMMEDIATE`: contar e inserir têm de ser um passo só. Sem isso dois
    # envios simultâneos do mesmo visitante contam 4 cada um e gravam os dois,
    # e a sexta vaga aparece do nada.
    con.execute("BEGIN IMMEDIATE")
    try:
        ja = con.execute(
            "SELECT count(*) AS n FROM consumo WHERE referencia = ? AND tipo = ?",
            (referencia, tipo)).fetchone()
        if int(ja["n"]) > 0:
            # Referência já cobrada: repetir o pedido não custa de novo. É o
            # que faz clique duplicado e reenvio saírem de graça.
            con.execute("COMMIT")
            return

        for balde in ident.baldes:
            teto = _teto(ident, tipo, balde)
            if teto == 0:
                continue
            if _contar(con, balde.chave, tipo, desde) >= teto:
                libera = _libera_em(con, balde.chave, tipo, desde)
                con.execute("ROLLBACK")
                # Qual balde estourou não sai daqui: dizer isso conta a quem
                # tenta burlar exatamente o que ele precisa saber.
                raise SemVaga(tipo, libera)

        con.executemany(
            "INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
            "VALUES (?, ?, ?, ?, ?)",
            [(b.chave, tipo, estado, agora, referencia) for b in ident.baldes])
        con.execute("COMMIT")
    except SemVaga:
        raise
    except Exception:
        con.execute("ROLLBACK")
        raise


def reservar(ident, tipo: str, referencia: str, agora=None) -> None:
    """Guarda a vaga. Levanta `SemVaga` se não couber."""
    _consumir(ident, tipo, referencia, "reservado", agora)


def cobrar(ident, tipo: str, referencia: str, agora=None) -> None:
    """Consome de vez, sem passar por reserva. Levanta `SemVaga` se não couber."""
    _consumir(ident, tipo, referencia, "confirmado", agora)


def confirmar(referencia: str) -> None:
    """Promove as reservas daquela referência. Uma vez confirmado, nada solta."""
    con = db.conexao()
    con.execute("UPDATE consumo SET estado = 'confirmado' "
                "WHERE referencia = ? AND estado = 'reservado'", (referencia,))
    con.commit()


def soltar(referencia: str) -> None:
    """Devolve as vagas ainda reservadas. Não mexe no que já foi confirmado."""
    con = db.conexao()
    con.execute("DELETE FROM consumo "
                "WHERE referencia = ? AND estado = 'reservado'", (referencia,))
    con.commit()


def restante(ident, tipo: str, agora=None) -> tuple[int | None, float | None]:
    """`(quantas vagas restam, quando libera a próxima)`.

    `(None, None)` quando o tipo está sem limite — e não um número grande, que
    a tela mostraria como se fosse cota. O balde mais apertado é o que manda,
    porque é ele que vai recusar.
    """
    agora = time.time() if agora is None else agora
    desde = agora - janela_s()
    con = db.conexao()

    sobra: int | None = None
    libera: float | None = None
    for balde in ident.baldes:
        teto = _teto(ident, tipo, balde)
        if teto == 0:
            continue
        livre = max(0, teto - _contar(con, balde.chave, tipo, desde))
        if sobra is None or livre < sobra:
            sobra = livre
            libera = (_libera_em(con, balde.chave, tipo, desde)
                      if livre == 0 else None)
    return sobra, libera
