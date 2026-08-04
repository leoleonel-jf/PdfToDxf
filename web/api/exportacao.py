"""Geração do DXF a partir do cache da extração, com reaproveitamento.

Cada combinação de página, escala, unidade e opções vira uma chave. O arquivo
gerado fica guardado sob essa chave, então pedir a mesma combinação de novo não
gera nada — só devolve o que já existe. Na etapa 4 é isso que vai permitir
repetir um download sem gastar cota.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import threading
from contextlib import contextmanager
from pathlib import Path

from pdftodxf.dxf_writer import export_dxf
from pdftodxf.optimize import ExportOptions

from . import storage

UNIDADES = ("mm", "cm", "m")

_HEX = frozenset("0123456789abcdef")


def chave(pagina: int, escala: float, unidade: str, opcoes: dict) -> str:
    """SHA-256 de um JSON canônico do pedido.

    Os layers excluídos são ordenados: quem exclui A e B tem que cair na mesma
    chave de quem exclui B e A.
    """
    canonico = {
        "pagina": pagina,
        "escala": repr(float(escala)),
        "unidade": unidade,
        "excluded_layers": sorted(opcoes.get("excluded_layers", [])),
        "drop_fills": bool(opcoes.get("drop_fills", False)),
        "min_len_mm": repr(float(opcoes.get("min_len_mm", 0.0))),
        "dedup": bool(opcoes.get("dedup", False)),
        "join_polylines": bool(opcoes.get("join_polylines", False)),
        "round_coords": bool(opcoes.get("round_coords", False)),
    }
    texto = json.dumps(canonico, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def pasta_export(job_id: str, pagina: int) -> Path:
    """Onde ficam os DXF de uma página. Não cria nada: quem grava é que cria."""
    return storage.pasta_pagina(job_id, pagina) / "export"


def caminho_do_dxf(job_id: str, pagina: int, ch: str) -> Path:
    if len(ch) != 64 or not _HEX.issuperset(ch):
        raise ValueError("chave inválida")
    return pasta_export(job_id, pagina) / f"{ch}.dxf"


def _arquivo_de_contagem(dxf: Path) -> Path:
    return dxf.with_suffix(".contagem.json")


def _contar(dxf: Path) -> int:
    arquivo = _arquivo_de_contagem(dxf)
    if not arquivo.exists():
        return 0
    with open(arquivo, encoding="utf-8") as f:
        return sum(json.load(f).values())


def _sufixo_unico() -> str:
    """Sufixo do arquivo temporário, único por processo e por fio."""
    return f".{os.getpid()}.{threading.get_ident()}.tmp"


_mapa_de_travas = threading.Lock()
_travas: dict[str, threading.Lock] = {}
_esperando: dict[str, int] = {}


@contextmanager
def _trava_da_chave(nome: str):
    """Uma trava por combinação, criada sob demanda e descartada no fim.

    Sem ela, quatro pedidos iguais chegando juntos geram o mesmo desenho quatro
    vezes — e numa planta no teto de 3 milhões de entidades isso é CPU jogada
    fora no processo que atende o site. Trancando por chave, o primeiro gera e
    os outros esperam e acham o arquivo pronto.

    A trava sai do mapa quando o último interessado vai embora, senão o mapa
    cresceria uma entrada por exportação até o processo morrer.
    """
    with _mapa_de_travas:
        trava = _travas.setdefault(nome, threading.Lock())
        _esperando[nome] = _esperando.get(nome, 0) + 1
    try:
        with trava:
            yield
    finally:
        with _mapa_de_travas:
            _esperando[nome] -= 1
            if _esperando[nome] == 0:
                del _esperando[nome]
                del _travas[nome]


def _trocar(temporario: Path, destino: Path) -> None:
    """`os.replace` tolerando quem chegou primeiro.

    A trava por chave só vale dentro de um processo; com mais de um worker de
    uvicorn, dois renomeios simultâneos para o mesmo destino ainda podem se
    cruzar, e no Windows isso volta como `ERROR_ACCESS_DENIED` em vez de
    simplesmente sobrescrever. Como a mesma chave significa o mesmo conteúdo,
    quem perde a corrida pode descartar o seu.
    """
    try:
        os.replace(temporario, destino)
    except OSError:
        if not destino.exists():
            raise


def gerar(job_id: str, pagina: int, escala: float, unidade: str,
          opcoes: dict) -> tuple[str, Path, bool, int]:
    """Devolve `(chave, caminho, veio_do_cache, entidades_escritas)`."""
    ch = chave(pagina, escala, unidade, opcoes)
    destino = caminho_do_dxf(job_id, pagina, ch)
    if destino.exists():
        return ch, destino, True, _contar(destino)

    with _trava_da_chave(f"{job_id}/{pagina}/{ch}"):
        # Quem esperou na trava pode ter ganhado o arquivo de presente.
        if destino.exists():
            return ch, destino, True, _contar(destino)
        return _gerar_de_fato(job_id, pagina, ch, destino, escala, unidade,
                              opcoes)


def _gerar_de_fato(job_id: str, pagina: int, ch: str, destino: Path,
                   escala: float, unidade: str,
                   opcoes: dict) -> tuple[str, Path, bool, int]:
    cache = storage.pasta_pagina(job_id, pagina) / "cache.pickle"
    with open(cache, "rb") as f:
        guardado = pickle.load(f)

    opts = ExportOptions(
        excluded_layers=set(opcoes.get("excluded_layers", [])),
        drop_fills=bool(opcoes.get("drop_fills", False)),
        min_len_mm=float(opcoes.get("min_len_mm", 0.0)),
        dedup=bool(opcoes.get("dedup", False)),
        join_polylines=bool(opcoes.get("join_polylines", False)),
        round_coords=bool(opcoes.get("round_coords", False)),
    )

    # Gerar num temporário e trocar no fim. Escrevendo direto no destino, um
    # worker morto no meio — ou outro processo gerando a mesma chave — deixaria
    # um DXF cortado, que o usuário baixaria com status 200 achando que é bom.
    destino.parent.mkdir(parents=True, exist_ok=True)
    sufixo = _sufixo_unico()
    dxf_temporario = destino.with_name(destino.name + sufixo)
    contagem_temporaria = _arquivo_de_contagem(destino).with_name(
        _arquivo_de_contagem(destino).name + sufixo)
    try:
        contagem = export_dxf(guardado["resultado"], str(dxf_temporario),
                              escala, unidade, opts, attrs=guardado["attrs"])
        with open(contagem_temporaria, "w", encoding="utf-8") as f:
            json.dump(contagem, f)
        # A contagem entra antes do DXF: quem enxergar o DXF pronto enxerga
        # também de quantas entidades ele é feito.
        _trocar(contagem_temporaria, _arquivo_de_contagem(destino))
        _trocar(dxf_temporario, destino)
    finally:
        for sobra in (dxf_temporario, contagem_temporaria):
            if sobra.exists():
                sobra.unlink()

    return ch, destino, False, sum(contagem.values())
