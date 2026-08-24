"""Manda e-mail: arquivo em desenvolvimento, SMTP em produção.

Sem `PDFTODXF_SMTP_SERVIDOR`, o e-mail vira um arquivo em `dados/emails/`. É o
que permite confirmar uma conta à mão e testar o fluxo inteiro **sem servidor
de e-mail nenhum** — inclusive no CI.
"""

from __future__ import annotations

import os
import smtplib
import time
import traceback
from email.message import EmailMessage
from pathlib import Path

from . import storage


def pasta_de_emails() -> Path:
    caminho = storage.raiz() / "emails"
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def remetente() -> str:
    return os.environ.get("PDFTODXF_SMTP_REMETENTE", "nao-responda@pdftodxf")


def _gravar_em_arquivo(para: str, assunto: str, corpo: str) -> None:
    seguro = "".join(c if c.isalnum() or c in "-_.@" else "_" for c in para)
    nome = f"{time.strftime('%Y%m%d-%H%M%S')}-{seguro[:60]}.txt"
    caminho = pasta_de_emails() / nome
    sufixo = 0
    while caminho.exists():
        sufixo += 1
        caminho = pasta_de_emails() / f"{nome[:-4]}-{sufixo}.txt"
    caminho.write_text(f"Para: {para}\nAssunto: {assunto}\n\n{corpo}\n",
                       encoding="utf-8")


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
