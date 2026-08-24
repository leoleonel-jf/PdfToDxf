"""O banco de contas e consumo, e o segredo que torna suas linhas comparáveis.

SQLite num arquivo só, com WAL. As rotas do FastAPI deste projeto são
síncronas e rodam num pool de threads, então a conexão é **por thread**, criada
sob demanda — `check_same_thread=False` está fora de cogitação: ele silencia o
aviso sem resolver a corrida.

O segredo mora aqui porque ele é a chave dos `hmac` que formam duas **colunas
deste banco**: `consumo.balde` e `usuarios.criado_de`. Trocá-lo derruba as
sessões, zera as cotas de visitante em andamento e a contagem de contas por IP
do dia — nada se perde, as linhas antigas apenas deixam de casar e saem na
limpeza de 24 horas.
"""

from __future__ import annotations

import base64
import hmac
import os
import secrets
import sqlite3
import threading
import time
from hashlib import sha256
from pathlib import Path

PRAZO_DO_CONSUMO_S = 24 * 60 * 60

# Os domínios de `assinar`/`conferir`, **todos** listados aqui de propósito: é a
# lista que deixa ver de relance que dois usos diferentes não pegaram o mesmo
# nome. Nome novo, domínio novo — nunca reaproveitar um destes.
DOMINIO_SESSAO = "sessao"
DOMINIO_COOKIE_VISITANTE = "cookie-visitante"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    senha         TEXT NOT NULL,
    confirmado_em REAL,
    criado_em     REAL NOT NULL,
    criado_de     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    valor     TEXT PRIMARY KEY,
    tipo      TEXT NOT NULL,
    usuario   INTEGER NOT NULL,
    expira_em REAL NOT NULL,
    usado_em  REAL
);
CREATE TABLE IF NOT EXISTS consumo (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    balde      TEXT NOT NULL,
    tipo       TEXT NOT NULL,
    estado     TEXT NOT NULL,
    quando     REAL NOT NULL,
    referencia TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS i_consumo_janela
    ON consumo (balde, tipo, quando);
CREATE INDEX IF NOT EXISTS i_consumo_referencia
    ON consumo (referencia, estado);
CREATE INDEX IF NOT EXISTS i_usuarios_criado
    ON usuarios (criado_de, criado_em);
"""

_local = threading.local()
_segredo_gerado: bytes | None = None
_avisou = False


def caminho() -> Path:
    p = Path(os.environ.get("PDFTODXF_BANCO", "dados/contas.db"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def criar_tabelas(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)
    con.commit()


def conexao() -> sqlite3.Connection:
    """A conexão deste fio, criada na primeira vez que ele pede.

    O caminho é guardado junto: nos testes o `PDFTODXF_BANCO` muda entre
    arquivos, e uma conexão presa ao banco anterior daria falha muda.
    """
    atual = str(caminho())
    con = getattr(_local, "con", None)
    if con is not None and getattr(_local, "onde", None) == atual:
        return con
    if con is not None:
        con.close()

    con = sqlite3.connect(atual)
    con.row_factory = sqlite3.Row
    # O `busy_timeout` vem **antes** do `journal_mode`: trocar o journal pede o
    # lock de escrita, e sem o handler armado ele volta "database is locked" na
    # hora se outro fio estiver escrevendo — bem na conexão recém-criada, que é
    # justamente quando há concorrência.
    con.execute("PRAGMA busy_timeout=5000")
    # Escrita curta com WAL basta nesta escala; o `busy_timeout` é o que faz um
    # segundo escritor esperar em vez de voltar "database is locked" na cara do
    # usuário.
    con.execute("PRAGMA journal_mode=WAL")
    criar_tabelas(con)
    _local.con = con
    _local.onde = atual
    return con


def fechar() -> None:
    """Fecha a conexão deste fio. Existe para o teste, não para o serviço."""
    con = getattr(_local, "con", None)
    if con is not None:
        con.close()
        _local.con = None


def segredo() -> bytes:
    """A chave dos `hmac`, de `PDFTODXF_SEGREDO` ou aleatória por subida.

    Ausente, gera uma aleatória e avisa no log. Isso derruba as sessões a cada
    reinício — irrelevante em desenvolvimento, ruim em produção — mas nunca
    entrega um serviço com segredo fixo conhecido, que é o modo de falhar que
    importa.
    """
    global _segredo_gerado, _avisou
    do_ambiente = os.environ.get("PDFTODXF_SEGREDO")
    if do_ambiente:
        return do_ambiente.encode("utf-8")
    if _segredo_gerado is None:
        _segredo_gerado = secrets.token_bytes(32)
    if not _avisou:
        print("PDFTODXF_SEGREDO ausente: usando um segredo aleatorio desta "
              "subida. As sessoes caem a cada reinicio.")
        _avisou = True
    return _segredo_gerado


def marca(valor: str) -> str:
    """`hmac` hexadecimal do valor. É o que vai ao banco no lugar do dado cru."""
    return hmac.new(segredo(), (valor or "").encode("utf-8"), sha256).hexdigest()


def _mensagem(corpo: str, dominio: str) -> str:
    """O que de fato entra no `hmac`: o domínio **grudado** no corpo.

    O domínio não viaja no envelope — ele só existe do lado de quem assina e de
    quem confere. Não há campo para trocar, reordenar ou remover: um valor
    assinado num domínio simplesmente não fecha a conta em outro.
    """
    return f"{dominio}|{corpo}"


def assinar(dados: str, dominio: str) -> str:
    """`<corpo em base64url>.<assinatura>` — o formato dos cookies.

    **O `dominio` é obrigatório e não tem padrão**, de propósito: sem ele, todo
    valor assinado por este módulo sai do mesmo envelope, e o cookie do
    visitante e o cookie de sessão viram intercambiáveis. Hoje isso não é
    explorável — o corpo do visitante é um `token_urlsafe(24)`, e o `int()` de
    `auth.dono_da_sessao` o rejeita —, mas basta uma tarefa futura assinar algo
    que o usuário controle no formato `<inteiro>|<numero>` para o cookie do
    visitante virar sessão de qualquer conta. O domínio fecha isso na origem, e
    o parâmetro sem padrão obriga o próximo chamador a escolher um.
    """
    corpo = base64.urlsafe_b64encode(dados.encode("utf-8")).decode().rstrip("=")
    return f"{corpo}.{marca(_mensagem(corpo, dominio))}"


def conferir(assinado: str, dominio: str) -> str | None:
    """O conteúdo, se a assinatura casar **naquele domínio**. `None` se não."""
    corpo, ponto, assinatura = (assinado or "").partition(".")
    if not ponto or not assinatura:
        return None
    # `compare_digest` e não `==`: a comparação byte a byte que sai no primeiro
    # erro conta, pelo tempo, quantos caracteres já estavam certos.
    if not hmac.compare_digest(assinatura, marca(_mensagem(corpo, dominio))):
        return None
    try:
        recheio = "=" * (-len(corpo) % 4)
        return base64.urlsafe_b64decode(corpo + recheio).decode("utf-8")
    except Exception:
        return None


def limpar(agora: float | None = None) -> dict:
    """Apaga consumo de mais de 24 h e token vencido. Devolve quantos saíram."""
    agora = time.time() if agora is None else agora
    con = conexao()
    c1 = con.execute("DELETE FROM consumo WHERE quando < ?",
                     (agora - PRAZO_DO_CONSUMO_S,)).rowcount
    c2 = con.execute("DELETE FROM tokens WHERE expira_em < ?", (agora,)).rowcount
    con.commit()
    return {"consumo": c1, "tokens": c2}
