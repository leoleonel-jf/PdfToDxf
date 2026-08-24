"""É mesmo quem diz ser: senha, cadastro, confirmação, sessão e redefinição.

Três decisões que parecem detalhe e não são:

- **A recusa nunca distingue "não existe" de "está errado".** Nem no cadastro,
  nem no login, nem na redefinição. Um formulário que responde diferente para
  e-mail cadastrado vira uma sonda para descobrir quem usa o serviço.
- **Todo caminho paga exatamente um `scrypt`**, porque a mensagem calada não
  adianta nada se o cronômetro contar a diferença. No cadastro isso já sai de
  graça: `criar_conta` avalia `hash_senha(senha)` como **argumento** do
  `INSERT`, então o hash é pago antes de o `IntegrityError` sequer disparar —
  e-mail novo e e-mail repetido gastam o mesmo. É acidente de escrita, não
  desenho: **não mexa nessa ordem sem medir de novo**, e não acrescente um
  segundo hash por cima (foi o que a revisão da tarefa 7 teve de arrancar da
  rota de registro, porque o repetido ficava 2x mais lento que o novo). Onde
  não há hash pago no caminho — o login com e-mail inexistente — é para isso
  que existe `queimar_tempo`.
- **Os parâmetros do `scrypt` vão gravados junto do hash.** Endurecer os custos
  depois não invalida senha nenhuma: quem entra com um hash antigo é reescrito
  com os novos naquele momento.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time

from . import db

N = 2 ** 15
R = 8
P = 1
TAMANHO = 32
PRAZO_CONFIRMACAO_S = 48 * 60 * 60
PRAZO_SENHA_S = 60 * 60
SENHA_MINIMA = 8

_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
# Hash descartável, com custo real, para o caminho do e-mail inexistente.
_DE_MENTIRA = None


def normalizar(email: str) -> str:
    return (email or "").strip().lower()


def email_valido(email: str) -> bool:
    # O comprimento é o do normalizado, e não o do valor cru: é o normalizado
    # que vai ao banco, e medir o cru recusaria um endereço de 250 caracteres
    # só por ter vindo com espaços em volta.
    limpo = normalizar(email)
    return bool(_EMAIL.match(limpo)) and len(limpo) <= 254


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode()


def hash_senha(senha: str, n: int = N, r: int = R, p: int = P) -> str:
    """`scrypt$n$r$p$sal$hash`, tudo em base64, com os parâmetros junto."""
    sal = secrets.token_bytes(16)
    bruto = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=n, r=r, p=p,
                           dklen=TAMANHO, maxmem=2 * n * r * 64 + 1024 * 1024)
    return f"scrypt${n}${r}${p}${_b64(sal)}${_b64(bruto)}"


def _partes(guardado: str):
    marca, n, r, p, sal, bruto = guardado.split("$")
    if marca != "scrypt":
        raise ValueError("formato desconhecido")
    return (int(n), int(r), int(p), base64.b64decode(sal),
            base64.b64decode(bruto))


def conferir_senha(senha: str, guardado: str) -> bool:
    try:
        n, r, p, sal, bruto = _partes(guardado)
    except Exception:
        return False
    try:
        calculado = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=n, r=r,
                                   p=p, dklen=len(bruto),
                                   maxmem=2 * n * r * 64 + 1024 * 1024)
    except Exception:
        # Parâmetros absurdos num hash corrompido não podem virar 500: isso é
        # senha que não confere, e o chamador já sabe o que fazer com `False`.
        return False
    # `compare_digest` e não `==`: a comparação que sai no primeiro byte errado
    # conta, pelo tempo, quanto do hash já estava certo.
    return hmac.compare_digest(calculado, bruto)


def precisa_reescrever(guardado: str) -> bool:
    """O hash foi feito com parâmetros mais fracos do que os de hoje?"""
    try:
        n, r, p, _sal, _bruto = _partes(guardado)
    except Exception:
        return True
    return (n, r, p) != (N, R, P)


def queimar_tempo() -> None:
    """Gasta o mesmo `scrypt` de um login de verdade, e joga fora.

    Sem isto, "e-mail não existe" responde em microssegundos e "senha errada"
    em dezenas de milissegundos — e o cronômetro conta o que a mensagem calou.

    É para o **login**, onde há de fato um caminho sem hash. No cadastro não
    serve: lá `criar_conta` já pagou o `scrypt` nos dois caminhos, e chamar
    isto por cima faz o e-mail repetido custar o dobro do novo — que é
    exatamente o oráculo que se queria fechar.
    """
    global _DE_MENTIRA
    if _DE_MENTIRA is None:
        _DE_MENTIRA = hash_senha("uma senha que ninguem usa")
    conferir_senha("tentativa", _DE_MENTIRA)


def por_email(email: str):
    return db.conexao().execute(
        "SELECT * FROM usuarios WHERE email = ?", (normalizar(email),)
    ).fetchone()


def por_id(uid: int):
    return db.conexao().execute(
        "SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone()


def criar_conta(email: str, senha: str, ip: str) -> int | None:
    """Cria a conta. Devolve `None` se o e-mail já existe.

    `hash_senha(senha)` é **argumento** do `INSERT`: o `scrypt` é avaliado antes
    de o banco ter chance de recusar por colisão. Custa um hash à toa quando o
    e-mail já existe, e é isso que iguala os dois tempos de resposta. Trocar por
    "consulta antes, hash depois" ficaria mais econômico e reabriria o oráculo
    de enumeração — se for mesmo trocar, o `queimar_tempo` tem de entrar junto,
    e a medição refeita.
    """
    con = db.conexao()
    try:
        cursor = con.execute(
            "INSERT INTO usuarios (email, senha, criado_em, criado_de) "
            "VALUES (?, ?, ?, ?)",
            (normalizar(email), hash_senha(senha), time.time(), db.marca(ip)))
        con.commit()
        return int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        con.rollback()
        return None


def reescrever_senha(uid: int, senha: str) -> None:
    con = db.conexao()
    con.execute("UPDATE usuarios SET senha = ? WHERE id = ?",
                (hash_senha(senha), uid))
    con.commit()


def novo_token(usuario: int, tipo: str, prazo_s: int) -> str:
    """Gera o token, guarda a **marca** dele e devolve o valor original.

    O valor só existe dentro do e-mail: vazamento do banco não entrega tokens
    utilizáveis.
    """
    valor = secrets.token_urlsafe(32)
    con = db.conexao()
    con.execute("INSERT INTO tokens (valor, tipo, usuario, expira_em) "
                "VALUES (?, ?, ?, ?)",
                (db.marca(valor), tipo, usuario, time.time() + prazo_s))
    con.commit()
    return valor


def usar_token(valor: str, tipo: str) -> int | None:
    """Consome o token e devolve o usuário. `None` se vencido, usado ou falso.

    O consumo é um `UPDATE` condicional, e não leitura-e-escrita: dois cliques
    no mesmo link chegam juntos, e só um pode valer.
    """
    con = db.conexao()
    agora = time.time()
    cursor = con.execute(
        "UPDATE tokens SET usado_em = ? "
        "WHERE valor = ? AND tipo = ? AND usado_em IS NULL AND expira_em > ?",
        (agora, db.marca(valor), tipo, agora))
    con.commit()
    if cursor.rowcount == 0:
        return None
    linha = con.execute("SELECT usuario FROM tokens WHERE valor = ?",
                        (db.marca(valor),)).fetchone()
    return int(linha["usuario"]) if linha else None


def confirmar_conta(uid: int) -> None:
    con = db.conexao()
    con.execute("UPDATE usuarios SET confirmado_em = ? WHERE id = ?",
                (time.time(), uid))
    con.commit()


def url_base() -> str:
    return os.environ.get("PDFTODXF_URL_BASE", "http://localhost:8000").rstrip("/")
