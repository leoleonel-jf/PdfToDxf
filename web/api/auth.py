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

  **`queimar_tempo` é só do login.** No pedido de redefinição de senha ele foi
  arrancado pela revisão da tarefa 9: lá os dois ramos são assimétricos de
  outro jeito (nenhum paga `scrypt`; o do e-mail existente paga um `INSERT` e
  uma carta), e somar um hash a um dos lados abria o oráculo em vez de
  fechá-lo — 10,0x com SMTP em 0 ms, faixas disjuntas. O que fecha lá é um
  **piso de resposta constante** nos dois ramos, com o envio fora do caminho
  do pedido: ver `main.PISO_DE_SENHA_S`.
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


def invalidar_tokens(usuario: int, tipo: str) -> int:
    """Queima os tokens daquele tipo que ainda estavam pendentes. Quantos foram.

    Pedir três links de redefinição e usar o terceiro deixava os dois primeiros
    válidos por até 1 h. Não é furo hoje — foram todos para a mesma caixa de
    entrada —, mas um link de senha que sobrevive à troca da senha é um segredo
    a mais no mundo sem motivo, e apagá-lo é um `UPDATE`.

    Marca `usado_em` em vez de apagar: é o mesmo estado que `usar_token` deixa,
    e a linha continua sendo o rastro daquele pedido até o `db.limpar` levar.
    """
    con = db.conexao()
    cursor = con.execute(
        "UPDATE tokens SET usado_em = ? "
        "WHERE usuario = ? AND tipo = ? AND usado_em IS NULL",
        (time.time(), usuario, tipo))
    con.commit()
    return int(cursor.rowcount)


def confirmar_conta(uid: int) -> None:
    con = db.conexao()
    con.execute("UPDATE usuarios SET confirmado_em = ? WHERE id = ?",
                (time.time(), uid))
    con.commit()


def url_base() -> str:
    return os.environ.get("PDFTODXF_URL_BASE", "http://localhost:8000").rstrip("/")


COOKIE_SESSAO = "pdftodxf_sessao"
PRAZO_SESSAO_S = 30 * 24 * 60 * 60
# Quanto a emissão pode estar à frente do relógio de agora e ainda valer. Existe
# só para tolerar relógio ligeiramente adiantado entre a emissão e a conferência
# (NTP corrigindo, máquina virtual retomando); não é folga de prazo.
FOLGA_DE_RELOGIO_S = 5 * 60


def _impressao(guardado: str) -> str:
    """Uma impressão curta do hash de senha guardado. **Nunca o hash em si.**

    `db.marca` é um `hmac` com o segredo do serviço: destes 16 dígitos
    hexadecimais não se reconstrói o hash, nem a senha, nem o sal. O que eles
    permitem é uma coisa só — perguntar "o hash de agora é o mesmo de quando
    esta sessão foi emitida?".
    """
    return db.marca(guardado)[:16]


def criar_sessao(uid: int, agora: float | None = None) -> str:
    """`<id>|<emitida em>|<impressão da senha>`, assinado.

    **Sem tabela de sessões.** Nesta escala o cookie assinado basta, e trocar o
    segredo derruba todas as sessões de uma vez — que é justamente o botão de
    emergência que se quer ter.

    A impressão é o que faz a **redefinição de senha** derrubar o que estava
    aberto, sem tabela de sessões e sem coluna nova: `hash_senha` sorteia um sal
    a cada chamada, então trocar a senha muda o hash guardado, muda a impressão,
    e toda sessão emitida antes deixa de casar — a de quem invadiu junto com a
    do dono, que entra de novo com a senha nova. Uma redefinição que não expulsa
    ninguém não protege de nada.

    Lê a linha do usuário de propósito, em vez de receber o hash pronto: quem
    chama não precisa lembrar de reler o banco depois de uma reescrita de hash,
    e é exatamente esse esquecimento que emitiria um cookie natimorto.
    """
    agora = time.time() if agora is None else agora
    linha = por_id(uid)
    impressao = _impressao(linha["senha"]) if linha is not None else ""
    return db.assinar(f"{int(uid)}|{agora:.0f}|{impressao}", db.DOMINIO_SESSAO)


def _sessao(request):
    valor = request.cookies.get(COOKIE_SESSAO)
    conteudo = db.conferir(valor, db.DOMINIO_SESSAO) if valor else None
    if not conteudo:
        return None
    partes = conteudo.split("|")
    if len(partes) != 3:
        # Cookie do formato antigo, de duas partes, ou lixo com `|` sobrando.
        # Recusa: sem a impressão não há como saber se a senha mudou desde a
        # emissão, e aceitá-lo "por compatibilidade" deixaria de pé justamente
        # as sessões que a redefinição existe para derrubar. O custo é os
        # logados de antes desta versão entrarem de novo, uma vez.
        return None
    uid, emitida, impressao = partes
    try:
        uid, emitida = int(uid), float(emitida)
    except ValueError:
        return None
    # **Piso, e não só teto.** O prazo é medido por `agora - emitida`: com uma
    # emissão no futuro essa conta fica negativa e nunca passa do prazo, ou
    # seja, o cookie valeria para sempre. Não é forjável sem o segredo e
    # `criar_sessao` não produz isso sozinha — o caso real é o relógio do
    # servidor andar para trás depois de emitir. Uma emissão à frente do agora
    # além da folga de relógio é lixo: recusa.
    if emitida > time.time() + FOLGA_DE_RELOGIO_S:
        return None
    return uid, emitida, impressao


def dono_da_sessao(request):
    """Quem é o dono desta sessão, se ela existe e vale. `None` se não."""
    from . import identidade
    lido = _sessao(request)
    if lido is None:
        return None
    uid, emitida, impressao = lido
    if time.time() - emitida > PRAZO_SESSAO_S:
        return None
    linha = por_id(uid)
    if linha is None:
        return None      # a conta sumiu; o cookie não pode ressuscitá-la
    # A impressão é **recalculada** do hash de agora, e não lida de lugar
    # nenhum: é isso que faz a troca de senha expulsar quem estava dentro.
    if not hmac.compare_digest(impressao, _impressao(linha["senha"])):
        return None
    return identidade.Dono(id=uid, confirmado=linha["confirmado_em"] is not None)


def precisa_renovar(request) -> bool:
    """Passou da metade do prazo? Então vale reemitir o cookie."""
    lido = _sessao(request)
    if lido is None:
        return False
    return time.time() - lido[1] > PRAZO_SESSAO_S / 2


UM_DIA_S = 24 * 60 * 60


CONTAS_POR_IP_DIA = 5


def teto_de_contas_por_ip() -> int:
    """Quantas contas um endereço pode criar por dia. `0` é sem limite.

    Mesmo tratamento de lixo de `quotas._chave`, e pelo mesmo motivo: chave
    vazia, escrita errada ou **negativa** cai no padrão. `max(0, ...)` grampeava
    o negativo em `0`, que aqui significa "sem limite" — e `-1` é justamente a
    convenção de "sem limite" de outros sistemas, ou seja, o lixo mais provável
    de aparecer. O teto do cadastro inteiro sumia em silêncio.
    """
    cru = os.environ.get("PDFTODXF_CONTAS_POR_IP_DIA")
    if cru is None or cru.strip() == "":
        return CONTAS_POR_IP_DIA
    try:
        valor = int(cru)
    except ValueError:
        return CONTAS_POR_IP_DIA
    return CONTAS_POR_IP_DIA if valor < 0 else valor


def contas_do_ip_hoje(ip: str, agora: float | None = None) -> int:
    """Quantas contas saíram deste IP nas últimas 24 h.

    Sem isto, fabricar contas em série multiplica a cota sem esforço nenhum. O
    ganho por conta é limitado — desde a tarefa 8 uma conta sem confirmar fica
    nos baldes de visitante —, mas não é zero, e a série é de custo zero.

    O IP vai na coluna como `marca`, e a conta é feita sobre ela.
    """
    agora = time.time() if agora is None else agora
    linha = db.conexao().execute(
        "SELECT count(*) AS n FROM usuarios "
        "WHERE criado_de = ? AND criado_em > ?",
        (db.marca(ip), agora - UM_DIA_S)).fetchone()
    return int(linha["n"])
