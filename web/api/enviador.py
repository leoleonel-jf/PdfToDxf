"""Manda e-mail: arquivo em desenvolvimento, SMTP em produção.

Sem `PDFTODXF_SMTP_SERVIDOR`, o e-mail vira um arquivo em `dados/emails/`. É o
que permite confirmar uma conta à mão e testar o fluxo inteiro **sem servidor
de e-mail nenhum** — inclusive no CI.
"""

from __future__ import annotations

import os
import smtplib
import stat
import time
import traceback
from email.message import EmailMessage
from pathlib import Path

from . import storage

# O arquivo carrega o token em claro; 48 h é o prazo do próprio token de
# confirmação, então depois disso ele não vale mais nada.
PRAZO_S = 48 * 60 * 60


def pasta_de_emails() -> Path:
    caminho = storage.raiz() / "emails"
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def remetente() -> str:
    return os.environ.get("PDFTODXF_SMTP_REMETENTE", "nao-responda@pdftodxf")


def _gravar_em_arquivo(para: str, assunto: str, corpo: str) -> None:
    """Grava a carta sem nunca sobrescrever outra.

    O nome sai do segundo corrente e do destinatário, então dois envios ao mesmo
    endereço no mesmo segundo disputam o mesmo nome. Conferir com `exists()`
    antes de abrir é justamente a corrida: os dois olham, os dois veem vazio, e
    o segundo apaga o primeiro — um link de confirmação sumindo aqui é uma conta
    que não ativa. `O_EXCL` num laço de tentativas resolve porque a criação e a
    reserva do nome viram uma coisa só, e é o mesmo caminho que
    `registros.gravar` já usa neste projeto.
    """
    destino = pasta_de_emails()
    seguro = "".join(c if c.isalnum() or c in "-_.@" else "_" for c in para)
    nome = f"{time.strftime('%Y%m%d-%H%M%S')}-{seguro[:60]}.txt"
    texto = f"Para: {para}\nAssunto: {assunto}\n\n{corpo}\n".encode("utf-8")

    raiz = destino.resolve()
    sufixo = 0
    while True:
        tentativa = nome if sufixo == 0 else f"{nome[:-4]}-{sufixo}.txt"
        caminho = destino / tentativa
        if not caminho.resolve().is_relative_to(raiz):
            raise ValueError("o e-mail escaparia da pasta de e-mails")
        try:
            fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            sufixo += 1
            continue
        with os.fdopen(fd, "wb") as f:
            f.write(texto)
        return


def enviar(para: str, assunto: str, corpo: str) -> None:
    """Manda, ou grava em arquivo. **Nunca levanta.**

    Uma falha de SMTP não pode derrubar o cadastro: a conta já existe, e o
    usuário pode pedir o link de novo. Estourar aqui devolveria 500 para quem
    acabou de se cadastrar com sucesso.
    """
    servidor = os.environ.get("PDFTODXF_SMTP_SERVIDOR")
    if not servidor:
        # O caminho de arquivo também não pode levantar: disco cheio ou pasta
        # sem permissão derrubaria o cadastro pelo mesmo motivo que o SMTP.
        try:
            _gravar_em_arquivo(para, assunto, corpo)
        except Exception:
            traceback.print_exc()
        return

    # Tudo dentro do `try`, e não só a conversa com o servidor: `int()` de uma
    # porta escrita errada e um cabeçalho com quebra de linha levantam antes de
    # abrir conexão nenhuma, e "nunca levanta" não pode ter exceção.
    try:
        msg = EmailMessage()
        msg["From"] = remetente()
        msg["To"] = para
        msg["Subject"] = assunto
        msg.set_content(corpo)
        porta = int(os.environ.get("PDFTODXF_SMTP_PORTA", "587"))
        usuario = os.environ.get("PDFTODXF_SMTP_USUARIO")
        senha = os.environ.get("PDFTODXF_SMTP_SENHA")
        with smtplib.SMTP(servidor, porta, timeout=20) as s:
            s.starttls()
            if usuario and senha:
                s.login(usuario, senha)
            s.send_message(msg)
    except Exception:
        traceback.print_exc()


def expurgar(agora: float | None = None) -> list[str]:
    """Apaga as cartas que passaram de 48 h. Devolve os nomes apagados.

    Higiene, não vazamento: `dados/` está no `.gitignore` e o token já saiu do
    banco pelo `db.limpar` quando o prazo vence. Mas o arquivo guarda o token em
    claro, e segredo vencido não tem por que ficar em disco para sempre.

    Nos moldes de `registros.expurgar`, inclusive no engolir de `OSError`: uma
    carta presa por outro processo fica para a passagem seguinte em vez de
    abortar a varredura inteira.
    """
    agora = time.time() if agora is None else agora
    apagados = []
    for arquivo in pasta_de_emails().iterdir():
        try:
            info = arquivo.stat()
            if not stat.S_ISREG(info.st_mode):
                continue
            if agora - info.st_mtime <= PRAZO_S:
                continue
            arquivo.unlink()
        except OSError:
            continue
        apagados.append(arquivo.name)
    return apagados
