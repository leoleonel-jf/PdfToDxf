"""O registro em Markdown de uma página extraída.

Este módulo monta um texto e grava um arquivo. Ele **não sabe** o que é conta
nem o que é cota: recebe tudo pronto em `dados`. É o que permite chamá-lo de
dentro do worker, que nunca abre o banco.

O IP aqui é o real, e não o `hmac` que a cota guarda. Não é contradição: a cota
só precisa saber "é o mesmo?"; o registro existe justamente para ser
rastreável. Os dois usos estão declarados na página de privacidade, com prazos
diferentes — 2 horas e 1 ano.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from pdftodxf.calibration import PT_TO_MM
from pdftodxf.geometry import limites

PRAZO_S = 365 * 24 * 60 * 60      # 1 ano
LIMITE_DO_NOME = 60
_PROIBIDO = re.compile(r"[^A-Za-z0-9_-]")


def pasta() -> Path:
    """Pasta dos registros, de `PDFTODXF_REGISTROS` ou `./registros`.

    Fora da pasta de trabalhos de propósito, e nunca servida pela web.
    """
    caminho = Path(os.environ.get("PDFTODXF_REGISTROS", "registros"))
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def _limpo(texto: str, limite: int) -> str:
    """Troca por `_` tudo que não for letra, número, hífen ou sublinhado.

    Aplicado à string **inteira**, e não só ao `basename`: um nome com `..\\`
    sobrevive ao `os.path.basename` em POSIX, e o barato aqui é não depender
    de qual separador a plataforma reconhece.
    """
    return _PROIBIDO.sub("_", texto or "")[:limite]


def nome_do_arquivo(ip: str, nome_pdf: str, pagina: int, quando: float) -> str:
    """`{ip}-{nome}-p{pagina}-{AAAAMMDD-HHMMSS}.md`, tudo higienizado."""
    sem_extensao = os.path.splitext(nome_pdf or "")[0]
    base = _limpo(sem_extensao, LIMITE_DO_NOME) or "planta"
    marca_tempo = time.strftime("%Y%m%d-%H%M%S", time.gmtime(quando))
    return f"{_limpo(ip, 45)}-{base}-p{int(pagina)}-{marca_tempo}.md"


def _yaml(valor) -> str:
    """Um escalar YAML seguro. JSON é YAML válido, e o `json` já escapa."""
    return json.dumps(valor, ensure_ascii=False)


def montar(dados: dict, resultado, attrs) -> str:
    por_layer: dict[str, int] = {}
    for i in range(len(attrs.layer_id)):
        nome = attrs.layers[attrs.layer_id[i]]
        por_layer[nome] = por_layer.get(nome, 0) + 1

    quando = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(dados["quando"]))
    linhas = [
        "---",
        f"ip: {_yaml(dados['ip'])}",
        f"conta: {_yaml(dados['conta'])}",
        f"nome: {_yaml(dados['nome'])}",
        f"pagina: {int(dados['pagina'])}",
        f"quando: {_yaml(quando + ' UTC')}",
        f"job_id: {_yaml(dados['job_id'])}",
        f"tamanho_pdf: {int(dados['tamanho_pdf'])}",
        f"segundos: {round(float(dados['segundos']), 2)}",
        "---",
        "",
        f"# {dados['nome']} — página {dados['pagina']}",
        "",
        "## Folha",
        "",
        f"- {resultado.page_width:.1f} x {resultado.page_height:.1f} pt",
        f"- {resultado.page_width * PT_TO_MM:.0f} x "
        f"{resultado.page_height * PT_TO_MM:.0f} mm",
    ]

    caixa = limites(resultado.entities)
    if caixa is None:
        linhas.append("- limites do desenho: nenhum (página sem geometria)")
    else:
        x0, y0, x1, y1 = caixa
        linhas.append(f"- limites do desenho: ({x0:.1f}, {y0:.1f}) a "
                      f"({x1:.1f}, {y1:.1f}) pt")

    linhas += ["", "## Entidades", "", "| tipo | quantidade |", "|---|---:|"]
    contagem = resultado.counts()
    for tipo in sorted(contagem):
        linhas.append(f"| {tipo} | {contagem[tipo]} |")

    linhas += ["", "## Layers", "", "| layer | entidades |", "|---|---:|"]
    for nome in sorted(por_layer, key=lambda n: (-por_layer[n], n)):
        linhas.append(f"| {nome} | {por_layer[nome]} |")

    linhas += ["", "## Textos da planta", "",
               "| texto | x | y | altura | rotação |", "|---|---:|---:|---:|---:|"]
    for e in resultado.entities:
        texto = getattr(e, "text", None)
        if texto is None:
            continue
        # `|` dentro do texto quebraria a tabela; a barra escapada é o que o
        # Markdown entende, e o texto vem do PDF do usuário.
        seguro = texto.replace("|", "\\|")
        linhas.append(f"| {seguro} | {e.position[0]:.1f} | {e.position[1]:.1f} "
                      f"| {e.height:.2f} | {e.rotation:.1f} |")

    return "\n".join(linhas) + "\n"


def gravar(dados: dict, resultado, attrs) -> Path:
    """Grava o registro e devolve o caminho. Nunca sobrescreve.

    O caminho final é conferido contra a pasta **depois** de resolvido, e não
    antes: a higienização do nome já deveria bastar, e esta é a rede de
    segurança de quem esqueceu um caso.
    """
    destino = pasta()
    nome = nome_do_arquivo(dados["ip"], dados["nome"], dados["pagina"],
                           dados["quando"])
    texto = montar(dados, resultado, attrs).encode("utf-8")

    raiz = destino.resolve()
    sufixo = 0
    while True:
        tentativa = nome if sufixo == 0 else f"{nome[:-3]}-{sufixo}.md"
        caminho = (destino / tentativa)
        if not caminho.resolve().is_relative_to(raiz):
            raise ValueError("o registro escaparia da pasta de registros")
        try:
            # `O_EXCL`: dois workers no mesmo segundo não podem se sobrescrever,
            # e conferir com `exists()` antes de abrir seria justamente a
            # corrida que se quer evitar.
            fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            sufixo += 1
            continue
        with os.fdopen(fd, "wb") as f:
            f.write(texto)
        return caminho


def expurgar(agora: float | None = None) -> list[str]:
    """Apaga o que passou de 1 ano. Devolve os nomes apagados."""
    agora = time.time() if agora is None else agora
    apagados = []
    for arquivo in pasta().iterdir():
        if not arquivo.is_file():
            continue
        try:
            if agora - arquivo.stat().st_mtime <= PRAZO_S:
                continue
            arquivo.unlink()
        except OSError:
            continue        # sumiu no meio da varredura, ou está preso: fica
        apagados.append(arquivo.name)
    return apagados
