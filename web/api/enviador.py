"""Manda e-mail: arquivo em desenvolvimento, SMTP em produção.

Sem `PDFTODXF_SMTP_SERVIDOR`, o e-mail vira um arquivo em `dados/emails/`. É o
que permite confirmar uma conta à mão e testar o fluxo inteiro **sem servidor
de e-mail nenhum** — inclusive no CI.
"""

from __future__ import annotations

import os
import queue
import smtplib
import stat
import threading
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


# ---------------------------------------------------------------------------
# A fila de envio
#
# Existe para tirar o transporte de e-mail do caminho do pedido **sem** criar
# uma thread por pedido. `POST /api/auth/senha` responde igual para e-mail que
# existe e para e-mail que não existe, em texto e em tempo, e o transporte é de
# fora: dezenas a centenas de milissegundos que vazariam para o cronômetro de
# quem sonda a rota. A versão anterior disparava uma `threading.Thread` por
# carta dentro da própria rota — e o `.start()` roda **no caminho do pedido**,
# então um `RuntimeError: can't start new thread` saía como 500 só no ramo do
# e-mail que existe. Oráculo binário, barulhento, numa rota que qualquer um
# chama sem senha nenhuma e que criava threads sem teto.
#
# Com a fila, o caminho do pedido faz um `put_nowait` e volta. Ninguém cria
# thread ali, e o número de fios é fixo.
# ---------------------------------------------------------------------------

# Quantas cartas a fila segura. Passou disso, descarta — ver `enfileirar`.
TAMANHO_DA_FILA = 500
# Poucos fios de propósito: o gargalo é o servidor de e-mail, não nós, e o ponto
# de tudo isto é justamente **não** deixar a carga de envio crescer com a de
# pedidos.
FIOS_DE_ENVIO = 3
NOME_DO_FIO_DE_ENVIO = "enviador-de-carta"

_fila: queue.Queue = queue.Queue(maxsize=TAMANHO_DA_FILA)
_trava_dos_fios = threading.Lock()
_fios: list[threading.Thread] = []
_trava_do_contador = threading.Lock()
_enfileiradas = 0


def _trabalhar(fila: queue.Queue) -> None:
    """Serve a fila para sempre. **Uma carta ruim não mata o fio.**

    Se uma exceção derrubasse o trabalhador, a fila perderia um servidor a cada
    carta problemática até parar de escoar de vez, e aí ninguém receberia mais
    nada — falha silenciosa e permanente. `enviar` promete nunca levantar, mas
    a promessa é do contrato de hoje e garanti-la aqui custa três linhas.

    A fila vem por argumento, e não do global: assim o fio fica preso ao objeto
    com que nasceu. Um teste que troque `_fila` por outra fila mexe só em quem
    enfileira, e nunca acorda um trabalhador em cima da fila errada — que
    daria `task_done()` na contagem de outra.
    """
    while True:
        para, assunto, corpo = fila.get()
        try:
            enviar(para, assunto, corpo)
        except Exception:
            traceback.print_exc()
        finally:
            # Sempre, inclusive depois de erro: é o `task_done` que faz o
            # `join()` de `esperar_a_fila` voltar. Deixá-lo de fora do
            # `finally` penduraria o teste, não a produção.
            fila.task_done()


def _garantir_os_fios() -> None:
    """Cria os fios de envio **uma vez só**.

    Sob trava porque dois pedidos simultâneos que cheguem aqui juntos criariam
    dois conjuntos de fios, e o serviço acumularia trabalhadores a cada pico.

    `daemon=True` tem um preço, e ele fica registrado aqui: **no desligamento,
    as cartas ainda na fila ou em voo são descartadas sem aviso**. Quem pediu a
    redefinição de senha durante um deploy leu "o e-mail já saiu" e não vai
    receber nada — vai ter de pedir de novo. É preço aceito de propósito: o
    contrário seria prender o encerramento do serviço no tempo do transporte de
    e-mail, e esperar por carta em qualquer ponto do caminho do pedido é
    exatamente o que reabre a diferença de tempo entre os dois ramos que o piso
    de `main.pedir_senha` existe para fechar.
    """
    if _fios:
        return
    with _trava_dos_fios:
        if _fios:
            return
        novos = []
        try:
            for i in range(FIOS_DE_ENVIO):
                fio = threading.Thread(target=_trabalhar, args=(_fila,),
                                       name=f"{NOME_DO_FIO_DE_ENVIO}-{i}",
                                       daemon=True)
                fio.start()
                novos.append(fio)
        finally:
            # No `finally` de propósito: se um `start()` falhar no meio (o
            # `RuntimeError: can't start new thread` de novo), os que já
            # subiram continuam servindo a fila, e esquecê-los faria a chamada
            # seguinte criar um conjunto **por cima** deles — que é justamente
            # o crescimento sem teto de que esta fila veio nos livrar. Ficar
            # com um ou dois fios escoa mais devagar; ficar com dois conjuntos
            # é o defeito antigo de volta.
            _fios.extend(novos)


def enfileirar(para: str, assunto: str, corpo: str) -> None:
    """Põe a carta na fila e volta. **Nunca levanta e nunca bloqueia.**

    É a porta de entrada do caminho do pedido. Não levanta porque quem a chama
    é uma rota cuja resposta tem de ser idêntica nos dois ramos — uma exceção
    aqui viraria 500 num ramo e 200 no outro, que é o oráculo de enumeração de
    volta pela porta dos fundos. Não bloqueia pelo mesmo motivo: esperar por
    vaga poria o tempo do transporte de e-mail de volta no relógio da resposta.

    Fila cheia significa **descartar e registrar**, não esperar.
    """
    global _enfileiradas
    try:
        _fila.put_nowait((para, assunto, corpo))
    except queue.Full:
        print(f"enviador: fila de envio cheia ({_fila.maxsize}), carta "
              f"descartada para {para!r} — assunto {assunto!r}")
        return
    except Exception:
        traceback.print_exc()
        return

    with _trava_do_contador:
        _enfileiradas += 1

    # Depois do `put`, e não antes: se a criação dos fios falhar (o
    # `RuntimeError: can't start new thread` que motivou toda esta fila), a
    # carta já está guardada e sai quando o próximo pedido conseguir subir os
    # fios. E a falha não escapa: `enfileirar` não levanta.
    try:
        _garantir_os_fios()
    except Exception:
        traceback.print_exc()


def cartas_enfileiradas() -> int:
    """Quantas cartas entraram na fila desde que o processo subiu.

    É o que deixa o teste distinguir "a carta saiu pela fila" de "a carta saiu
    no fio do pedido": as duas gravam o mesmo arquivo no fim, então sem este
    contador o teste não notaria a volta do envio síncrono.
    """
    with _trava_do_contador:
        return _enfileiradas


def esperar_a_fila(limite_s: float = 10.0) -> bool:
    """Espera a fila escoar. Devolve `False` se estourou o prazo.

    Para o teste esperar o envio sem dormir um valor arbitrário — dormir é
    teste intermitente disfarçado de teste. `queue.Queue.join()` não aceita
    prazo, então ele roda num fio à parte e quem tem prazo é o `join` desse
    fio: assim um trabalhador travado vira falha de teste em vez de uma bateria
    pendurada para sempre.
    """
    fio = threading.Thread(target=_fila.join, daemon=True)
    fio.start()
    fio.join(limite_s)
    return not fio.is_alive()


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
