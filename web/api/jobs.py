"""Fila de extração: cada página é extraída num processo separado.

Um `ProcessPoolExecutor` limita quantas extrações rodam ao mesmo tempo. Rodar
fora do processo do serviço é o que permite uma planta monstruosa morrer sozinha
sem levar o site junto: os limites de memória e de CPU são aplicados ao processo
filho.

O estado de uma página vale `"na_fila" | "extraindo" | "pronta" | "erro"`.
`"extraindo"` está no contrato mas nada o escreve hoje: quem manda no estado é o
processo pai, e ele não tem como saber a hora exata em que o worker pega o
trabalho. Quem lê deve tratá-lo como "ainda em andamento", igual a `"na_fila"`.
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import threading
import traceback
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from . import limits, packing, quotas, registros, storage


class SemVetores(Exception):
    """A página não tem geometria vetorial (PDF escaneado ou em branco)."""


class EntidadesDemais(Exception):
    """A página passa do teto de entidades.

    Os dois números vão em `args` porque esta exceção atravessa a fronteira de
    processo: o pickle padrão de exceção reconstrói o objeto chamando
    `cls(*args)`. Guardar só a mensagem formatada faria o `unpickle` estourar
    com "faltou argumento", e o erro real chegaria disfarçado de erro interno.
    """

    def __init__(self, quantas: int, teto: int):
        super().__init__(quantas, teto)
        self.quantas = quantas
        self.teto = teto

    def __str__(self) -> str:
        return f"{self.quantas} entidades, teto {self.teto}"


_pool: ProcessPoolExecutor | None = None


def pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=limits.EXTRACOES_SIMULTANEAS)
    return _pool


def _aplicar_limites(memoria: int, cpu: int) -> str:
    """Aplica limites de recurso ao processo atual. Devolve o que conseguiu.

    `resource` só existe em POSIX. Em Windows não há equivalente simples, e
    fingir que aplicou seria pior do que dizer que não aplicou: em produção o
    serviço roda em Linux dentro de contêiner, onde os limites valem.
    """
    try:
        import resource
    except ImportError:
        return "nenhum (plataforma sem resource)"
    resource.setrlimit(resource.RLIMIT_AS, (memoria, memoria))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    return f"memória {memoria} B, CPU {cpu} s"


def _gravar_atomico(caminho: Path, dados: bytes) -> None:
    """Grava por inteiro ou não grava: o worker pode morrer no meio.

    Quem lê estes arquivos são as rotas de geometria, e um `.bin` cortado pela
    metade viraria lixo na tela do usuário em vez de um erro honesto.
    """
    temporario = caminho.with_name(caminho.name + ".tmp")
    with open(temporario, "wb") as f:
        f.write(dados)
    os.replace(temporario, caminho)


def _extrair_no_worker(pdf: str, pagina: int, destino: str, teto_entidades: int,
                       teto_memoria: int, teto_cpu: int,
                       alvo_minimo_esqueleto: int,
                       pasta_registros: str, ip: str, conta: str,
                       nome_original: str, tamanho_pdf: int,
                       job_id: str) -> dict:
    """Roda no processo filho: extrai, classifica, divide e grava tudo.

    Recebe os tetos como argumento, e não os lê de `limits`, para que o processo
    pai continue sendo o único dono da política.
    """
    aplicados = _aplicar_limites(teto_memoria, teto_cpu)

    import time as _time
    comeco = _time.time()

    from pdftodxf.extractor import extract_page
    from pdftodxf.optimize import classify

    resultado = extract_page(pdf, page_number=pagina - 1)
    if not resultado.entities:
        raise SemVetores()
    if len(resultado.entities) > teto_entidades:
        raise EntidadesDemais(len(resultado.entities), teto_entidades)

    attrs = classify(resultado.entities)

    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    _gravar_atomico(pasta / "cache.pickle",
                    pickle.dumps({"resultado": resultado, "attrs": attrs},
                                 protocol=pickle.HIGHEST_PROTOCOL))

    alvo = packing.alvo_padrao(len(attrs), alvo_minimo_esqueleto)
    esqueleto, detalhe, limiar = packing.dividir(attrs, alvo)
    _gravar_atomico(pasta / "esqueleto.bin",
                    packing.empacotar(resultado, attrs, esqueleto))
    _gravar_atomico(pasta / "detalhe.bin",
                    packing.empacotar(resultado, attrs, detalhe))

    meta = {
        "pagina": pagina,
        "n_entidades": len(resultado.entities),
        "contagem": resultado.counts(),
        "layers": attrs.layers,
        "largura_pt": resultado.page_width,
        "altura_pt": resultado.page_height,
        "limiar_esqueleto_um": limiar,
        "partes": {"esqueleto": len(esqueleto), "detalhe": len(detalhe)},
    }
    _gravar_atomico(pasta / "meta.json",
                    json.dumps(meta, ensure_ascii=False).encode("utf-8"))

    # O registro é o último passo, e falhar aqui não pode custar a página. Ele
    # roda no worker, e não no processo pai, para não mandar todos os TextItem
    # de volta pela fronteira de processo só para escrevê-los num arquivo.
    try:
        os.environ["PDFTODXF_REGISTROS"] = pasta_registros
        from . import registros
        registros.gravar({
            "ip": ip, "conta": conta, "nome": nome_original,
            "pagina": pagina, "job_id": job_id,
            "tamanho_pdf": tamanho_pdf,
            "segundos": _time.time() - comeco,
            "quando": _time.time(),
        }, resultado, attrs)
    except Exception:
        traceback.print_exc()

    return {"situacao": "pronta", **meta, "limites_aplicados": aplicados}


_trava = threading.RLock()
"""Protege toda leitura-e-escrita da ficha.

Reentrante porque `pedir_extracao` decide sob a trava e chama `_gravar_estado`
por baixo, e porque um futuro que já terminou faz o `add_done_callback` rodar
no mesmo fio que submeteu.
"""


def _gravar_estado(job_id: str, pagina: int, estado: dict) -> None:
    """Atualiza o estado de uma página dentro da ficha do trabalho.

    A trava é obrigatória: com 4 workers, dois callbacks podem entrar aqui ao
    mesmo tempo, e sem ela o segundo leria a ficha antes de o primeiro gravar —
    o estado de uma das páginas sumiria.
    """
    with _trava:
        ficha = storage.ler_ficha(job_id)
        if ficha is None:
            # O trabalho sumiu enquanto a página era extraída — expirou, caiu
            # pela cota, ou o envio foi desfeito. Recriar a ficha aqui deixava
            # um toco sem `n_paginas` nem `nome`, e as rotas seguintes
            # estouravam KeyError em 500 no lugar do 404 honesto.
            return
        ficha.setdefault("paginas", {})[str(pagina)] = estado
        storage.gravar_ficha(job_id, ficha)


def _quando_terminar(job_id: str, pagina: int, futuro) -> None:
    try:
        estado = futuro.result()
    except SemVetores:
        estado = {"situacao": "erro", "codigo": "sem_vetores",
                  "mensagem": "Esta página não tem desenho vetorial. "
                              "Só funcionam PDFs gerados pelo CAD, não escaneados."}
    except EntidadesDemais as e:
        quantas = f"{e.quantas:,}".replace(",", ".")
        teto = f"{e.teto:,}".replace(",", ".")
        estado = {"situacao": "erro", "codigo": "entidades_demais",
                  "mensagem": f"A planta tem {quantas} elementos e o limite "
                              f"é {teto}."}
    except (BrokenProcessPool, MemoryError) as e:
        estado = {"situacao": "erro", "codigo": "recurso",
                  "mensagem": "Não consegui processar esta planta: ela passou do "
                              "limite de memória ou de tempo do servidor."}
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
    except Exception as e:
        estado = {"situacao": "erro", "codigo": "interno",
                  "mensagem": "Não consegui processar esta planta. "
                              "A falha foi registrada no servidor."}
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)

    try:
        _gravar_estado(job_id, pagina, estado)
        _apagar_origem_se_ocioso(job_id)
    except Exception as e:
        # Aqui é o fim da linha: o `concurrent.futures` engole o que escapar de
        # um callback e só o registra no log. Sem esta tentativa final, uma
        # falha ao gravar deixaria a página em "na_fila" para sempre — o
        # navegador perguntaria sem nunca receber resposta.
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
        try:
            _gravar_estado(job_id, pagina, {
                "situacao": "erro", "codigo": "interno",
                "mensagem": "Não consegui registrar o resultado desta página. "
                            "A falha foi registrada no servidor."})
        except Exception as outra:
            traceback.print_exception(type(outra), outra,
                                      outra.__traceback__, file=sys.stderr)

    # A primeira página boa promove a reserva. A soltura, porém, só acontece
    # quando **todas** as páginas do documento terminaram e **nenhuma** deu
    # certo.
    #
    # Soltar por página, como a primeira versão desta etapa fazia, deixava
    # furar o teto: converter primeiro a página escaneada devolvia a vaga, o
    # upload seguinte entrava, e converter depois a página vetorial promovia
    # uma reserva já solta. Medido, com o teto em 5: 40 conversões numa janela
    # feita para 5. Prender a vaga enquanto houver página por extrair é a mesma
    # regra que a spec já aplica a quem envia e fecha a aba — "reserva nunca
    # confirmada continua contando".
    #
    # Vem **depois** de gravar o estado, e não antes: `_documento_todo_falhou`
    # lê a ficha, e a página que acabou de terminar só entra nela quando
    # `_gravar_estado` grava. Antes, a última página a falhar não se veria na
    # contagem, e a vaga nunca seria solta.
    try:
        if estado.get("situacao") == "pronta":
            quotas.confirmar(job_id)
        elif _documento_todo_falhou(job_id):
            quotas.soltar(job_id)
    except Exception as e:
        # A cota não pode derrubar a entrega da página. Uma reserva que ficou
        # em pé custa uma vaga por 2 horas; uma página perdida custa a planta.
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)


def _documento_todo_falhou(job_id: str) -> bool:
    """Todas as páginas terminaram, e nenhuma delas ficou pronta?

    A condição é sobre o documento inteiro, não sobre a página que acabou de
    terminar. Enquanto faltar página, o usuário ainda pode pedi-la, e ela pode
    ser a boa: devolver a vaga antes disso é o que permitia converter de graça
    alternando a ordem das páginas.
    """
    with _trava:
        ficha = storage.ler_ficha(job_id)
        if not ficha:
            return False        # sem ficha não há o que decidir; a vaga fica
        n_paginas = ficha.get("n_paginas") or 0
        if n_paginas <= 0:
            return False
        paginas = list(ficha.get("paginas", {}).values())
        terminadas = [p for p in paginas
                      if p.get("situacao") in ("pronta", "erro")]
        if len(terminadas) < n_paginas:
            return False
        return not any(p.get("situacao") == "pronta" for p in terminadas)


def _apagar_origem_se_ocioso(job_id: str) -> None:
    """Apaga o PDF original quando não sobra página nenhuma para extrair.

    A condição é *todas* as páginas do documento terem terminado, não só as
    pedidas até agora. Enquanto faltar página, o usuário ainda pode pedi-la, e
    sem o original não há de onde extrair: apagar cedo demais deixava a planta
    de várias páginas pela metade, com a segunda extração falhando por arquivo
    inexistente. O que sobra sai na expiração de 4 horas, da tarefa 7.
    """
    with _trava:
        ficha = storage.ler_ficha(job_id)
        if not ficha:
            return
        n_paginas = ficha.get("n_paginas") or 0
        if n_paginas <= 0:
            return
        terminadas = [p for p in ficha.get("paginas", {}).values()
                      if p.get("situacao") in ("pronta", "erro")]
        if len(terminadas) < n_paginas:
            return
        origem = storage.pasta(job_id) / "origem.pdf"
        if origem.exists():
            origem.unlink()


def estado(job_id: str, pagina: int) -> dict | None:
    ficha = storage.ler_ficha(job_id)
    if ficha is None:
        return None
    return ficha.get("paginas", {}).get(str(pagina))


def pedir_extracao(job_id: str, pagina: int, ip: str = "",
                   conta: str = "") -> dict:
    """Enfileira a extração da página, se ela já não estiver em andamento.

    Conferir e reservar acontecem sob a mesma trava. As rotas do FastAPI são
    síncronas, então rodam num pool de threads e dois POSTs para a mesma página
    chegam de fato ao mesmo tempo: separar as duas coisas deixaria os dois
    passarem pela conferência antes de qualquer um gravar, e dois workers
    disputariam o mesmo `cache.pickle`.
    """
    with _trava:
        atual = estado(job_id, pagina)
        if atual and atual.get("situacao") in ("na_fila", "extraindo", "pronta"):
            return atual

        inicial = {"situacao": "na_fila"}
        _gravar_estado(job_id, pagina, inicial)

        origem = storage.pasta(job_id) / "origem.pdf"
        destino = storage.pasta_pagina(job_id, pagina)
        ficha = storage.ler_ficha(job_id) or {}
        try:
            pasta_registros = str(registros.pasta())
        except OSError:
            # `registros.pasta()` cria a pasta na hora (mkdir); se isso
            # falhar aqui, no processo pai, a falha não pode custar a
            # página — o registro é só transparência. Passa o caminho cru
            # adiante: o worker tenta de novo dentro do próprio try que já
            # engole erro de gravação de registro.
            pasta_registros = os.environ.get("PDFTODXF_REGISTROS", "registros")
        try:
            futuro = pool().submit(
                _extrair_no_worker, str(origem), pagina, str(destino),
                limits.TETO_ENTIDADES, limits.TETO_MEMORIA_WORKER_BYTES,
                limits.TETO_CPU_WORKER_SEGUNDOS, packing.ALVO_MINIMO,
                pasta_registros, ip, conta,
                ficha.get("nome", "planta.pdf"), int(ficha.get("tamanho", 0)),
                job_id)
        except Exception as e:
            # Sem isto a página ficaria em "na_fila" para sempre, esperando um
            # worker que nunca foi submetido.
            traceback.print_exception(type(e), e, e.__traceback__,
                                      file=sys.stderr)
            falha = {"situacao": "erro", "codigo": "interno",
                     "mensagem": "Não consegui enfileirar esta página. "
                                 "A falha foi registrada no servidor."}
            _gravar_estado(job_id, pagina, falha)
            return falha
        futuro.add_done_callback(
            lambda f: _quando_terminar(job_id, pagina, f))
        return inicial
