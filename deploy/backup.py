"""Cópia consistente do banco de contas, e o expurgo das cópias velhas.

**`cp` de um SQLite com escrita em curso produz um arquivo corrompido**, e o
defeito só aparece no dia da restauração — que é o pior dia possível para
descobrir. A API `backup()` do próprio SQLite copia página a página sob lock e
sai íntegra com o serviço rodando.

Programa independente de propósito: roda por `cron` na VPS sem subir o serviço
e sem importar nada de `web/`.

    python3 deploy/backup.py /banco/contas.db /var/backups/pdftodxf
"""

from __future__ import annotations

import os
import shlex
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def copiar(origem: Path, destino: Path) -> Path:
    """Cópia consistente de `origem` em `destino`. Devolve `destino`."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    fonte = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
    try:
        alvo = sqlite3.connect(destino)
        try:
            fonte.backup(alvo)
        finally:
            alvo.close()
    finally:
        fonte.close()
    return destino


def nome_do_dia(agora: float | None = None) -> str:
    quando = datetime.fromtimestamp(
        time.time() if agora is None else agora, tz=timezone.utc)
    return f"contas-{quando:%Y-%m-%d}.db"


def apagar_antigos(pasta: Path, dias: int,
                   agora: float | None = None) -> list[Path]:
    """Apaga as cópias com mais de `dias`. Devolve o que apagou."""
    agora = time.time() if agora is None else agora
    limite = agora - dias * 86400
    apagados = []
    for arquivo in sorted(pasta.glob("contas-*.db")):
        if arquivo.stat().st_mtime < limite:
            arquivo.unlink()
            apagados.append(arquivo)
    return apagados


def enviar_para_fora(arquivo: Path) -> None:
    """Roda o comando de `PDFTODXF_BACKUP_COMANDO`, se houver.

    O comando é configuração, não código: assim o projeto não escolhe entre
    rclone, aws-cli ou scp, e trocar de provedor não mexe em nada aqui.
    Sem ele, a cópia fica só local — e cópia local não sobrevive à VPS morrer.
    """
    comando = os.environ.get("PDFTODXF_BACKUP_COMANDO", "").strip()
    if not comando:
        print("AVISO: PDFTODXF_BACKUP_COMANDO vazio — a copia ficou so local, "
              "e copia local nao e backup.", file=sys.stderr)
        return
    subprocess.run(shlex.split(comando) + [str(arquivo)], check=True)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    origem, pasta = Path(argv[1]), Path(argv[2])
    if not origem.exists():
        print(f"Banco nao encontrado: {origem}. Confira o caminho no cron.",
              file=sys.stderr)
        return 1
    destino = copiar(origem, pasta / nome_do_dia())
    print(f"Copia feita: {destino} ({destino.stat().st_size} bytes)")
    enviar_para_fora(destino)
    dias = int(os.environ.get("PDFTODXF_BACKUP_DIAS", "30"))
    for velho in apagar_antigos(pasta, dias):
        print(f"Apagada por prazo: {velho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
