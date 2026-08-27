"""Extração de página: fila, estados e recusas."""

import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Só cria a pasta se a variável ainda não existe: no Windows o
# `ProcessPoolExecutor` usa spawn e reimporta este arquivo dentro de cada
# worker. Atribuir direto faria cada worker apontar para uma pasta temporária
# vazia sua em vez de herdar a do processo pai. O `if` em vez de `setdefault`
# porque o argumento do `setdefault` é avaliado sempre — cada worker deixaria
# uma pasta órfã atrás de si.
if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

# Aqui se testa a extração, não a cota: cada função envia o seu próprio PDF, e
# o padrão de 5 por janela barraria a bateria no meio. `0` é "sem limite" — o
# padrão continua o que é, e quem exercita a cota é o tests/test_api_cotas.py.
# Vale também para quem importa este arquivo (test_api_export,
# test_registros_no_worker), que envia pela mesma função `enviar`.
os.environ["PDFTODXF_COTA_ARQUIVOS"] = "0"
os.environ["PDFTODXF_COTA_DOWNLOADS"] = "0"
# Banco próprio e segredo fixo: sem isto a bateria escreveria consumo num
# `dados/contas.db` ao lado do repositório e avisaria do segredo aleatório. A
# guarda é a mesma do `PDFTODXF_DADOS`, pelo mesmo motivo do spawn.
if "PDFTODXF_BANCO" not in os.environ:
    os.environ["PDFTODXF_BANCO"] = os.path.join(
        tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

import fitz
from fastapi.testclient import TestClient

from tests.test_roundtrip import make_test_pdf
from web.api.main import app

cliente = TestClient(app)


def enviar(dados: bytes, nome: str = "planta.pdf") -> str:
    r = cliente.post("/api/jobs",
                     files={"arquivo": (nome, dados, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def bytes_do_pdf_vetorial() -> bytes:
    caminho = os.path.join(tempfile.mkdtemp(), "planta.pdf")
    make_test_pdf(caminho)
    with open(caminho, "rb") as f:
        return f.read()


def bytes_de_pdf_sem_vetores() -> bytes:
    """Uma página em branco: nenhum desenho, nenhum texto."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    caminho = os.path.join(tempfile.mkdtemp(), "branco.pdf")
    doc.save(caminho)
    doc.close()
    with open(caminho, "rb") as f:
        return f.read()


def bytes_de_pdf_de_duas_paginas() -> bytes:
    """Duas páginas iguais, cada uma com geometria vetorial de sobra."""
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page(width=595, height=842)
        shape = page.new_shape()
        shape.draw_line(fitz.Point(50, 50), fitz.Point(350, 50))
        shape.draw_rect(fitz.Rect(100, 100, 300, 300))
        shape.finish(color=(0, 0, 0), width=0.5)
        shape.commit()
    caminho = os.path.join(tempfile.mkdtemp(), "duas.pdf")
    doc.save(caminho)
    doc.close()
    with open(caminho, "rb") as f:
        return f.read()


def esperar(job_id: str, pagina: int, limite: float = 60.0) -> dict:
    """Aguarda a página sair da fila. Devolve o estado final."""
    fim = time.time() + limite
    while time.time() < fim:
        estado = cliente.get(f"/api/jobs/{job_id}/pages/{pagina}").json()
        if estado["situacao"] in ("pronta", "erro"):
            return estado
        time.sleep(0.2)
    raise AssertionError(f"a página {pagina} não terminou em {limite}s")


def esperar_sumir(caminho, porque: str, limite: float = 30.0) -> None:
    """Aguarda um arquivo sair do disco.

    `_apagar_origem_se_ocioso` roda **depois** de `_gravar_estado`, então a
    página fica "pronta" um instante antes de o original sumir. Conferir no
    mesmo passo em que `esperar` volta é uma corrida, e ela já custou falha
    intermitente aqui.

    A ordem lá está certa e não é o que se corrige: quem decide apagar lê a
    ficha, e a página que acabou de terminar só entra nela quando
    `_gravar_estado` grava — a mesma razão que faz a soltura da cota vir
    depois. Quem tem de ter paciência é este lado.
    """
    fim = time.time() + limite
    while time.time() < fim:
        if not caminho.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"{porque} (esperei {limite}s por {caminho})")


def test_extracao_completa():
    job = enviar(bytes_do_pdf_vetorial())
    r = cliente.post(f"/api/jobs/{job}/pages/1")
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] in ("na_fila", "extraindo", "pronta")
    estado = esperar(job, 1)
    assert estado["situacao"] == "pronta", estado
    assert estado["n_entidades"] > 0
    assert "TEXTO" in estado["layers"], estado["layers"]
    print("OK: extração de página conclui e informa contagens")


def test_pdf_original_e_apagado():
    from web.api import storage
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    esperar_sumir(storage.pasta(job) / "origem.pdf",
                  "o PDF original deveria sumir depois da extração")
    print("OK: PDF original é apagado após a extração")


def test_pagina_inexistente():
    job = enviar(bytes_do_pdf_vetorial())
    r = cliente.post(f"/api/jobs/{job}/pages/99")
    assert r.status_code == 404, r.status_code
    print("OK: página fora do documento é recusada")


def test_pdf_sem_vetores():
    job = enviar(bytes_de_pdf_sem_vetores(), nome="branco.pdf")
    cliente.post(f"/api/jobs/{job}/pages/1")
    estado = esperar(job, 1)
    assert estado["situacao"] == "erro", estado
    assert estado["codigo"] == "sem_vetores", estado
    assert "vetorial" in estado["mensagem"].lower(), estado["mensagem"]
    print("OK: PDF sem vetores dá erro identificável")


def test_teto_de_entidades():
    """Com o teto rebaixado, a mesma planta passa a ser recusada."""
    from web.api import limits
    original = limits.TETO_ENTIDADES
    limits.TETO_ENTIDADES = 3
    try:
        job = enviar(bytes_do_pdf_vetorial())
        cliente.post(f"/api/jobs/{job}/pages/1")
        estado = esperar(job, 1)
        assert estado["situacao"] == "erro", estado
        assert estado["codigo"] == "entidades_demais", estado
    finally:
        limits.TETO_ENTIDADES = original
    print("OK: teto de entidades recusa a página com mensagem clara")


def test_pedir_duas_vezes_nao_duplica():
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    cliente.post(f"/api/jobs/{job}/pages/1")
    estado = esperar(job, 1)
    assert estado["situacao"] == "pronta", estado
    print("OK: pedir a mesma página duas vezes não duplica trabalho")


def test_segunda_pagina_depois_da_primeira():
    """A página 2 pode ser pedida depois de a 1 ter terminado.

    O original só pode sumir quando não sobrar página para extrair. Apagá-lo
    assim que a fila esvazia deixava o documento de várias páginas pela metade:
    a segunda extração ia procurar um arquivo que não existia mais.
    """
    job = enviar(bytes_de_pdf_de_duas_paginas(), nome="duas.pdf")
    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "pronta"

    cliente.post(f"/api/jobs/{job}/pages/2")
    estado = esperar(job, 2)
    assert estado["situacao"] == "pronta", estado
    assert estado["n_entidades"] > 0, estado
    print("OK: página 2 é extraída depois de a página 1 ter terminado")


def test_original_some_quando_todas_as_paginas_terminam():
    from web.api import storage
    job = enviar(bytes_de_pdf_de_duas_paginas(), nome="duas.pdf")
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    assert (storage.pasta(job) / "origem.pdf").exists(), \
        "com a página 2 ainda por extrair, o original tem de ficar"

    cliente.post(f"/api/jobs/{job}/pages/2")
    esperar(job, 2)
    esperar_sumir(storage.pasta(job) / "origem.pdf",
                  "extraídas todas as páginas, o original deveria sumir")
    print("OK: original só some quando todas as páginas terminam")


def test_pedidos_simultaneos_submetem_uma_vez():
    """Vários POSTs concorrentes para a mesma página geram um worker só.

    As rotas são `def` síncrono, então o FastAPI as roda num pool de threads e
    dois pedidos chegam de fato ao mesmo tempo. Decidir e reservar têm de estar
    sob a mesma trava, ou os dois passam pela conferência antes de qualquer um
    gravar — e dois workers acabam gravando o mesmo cache.
    """
    from web.api import jobs

    job = enviar(bytes_do_pdf_vetorial())
    submissoes = []
    pool_real = jobs.pool()
    conta = threading.Lock()

    class PoolContado:
        def submit(self, *args, **kwargs):
            with conta:
                submissoes.append(args)
            return pool_real.submit(*args, **kwargs)

    original = jobs.pool
    jobs.pool = lambda: PoolContado()
    try:
        largada = threading.Barrier(6)

        def pedir():
            largada.wait()
            cliente.post(f"/api/jobs/{job}/pages/1")

        fios = [threading.Thread(target=pedir) for _ in range(6)]
        for f in fios:
            f.start()
        for f in fios:
            f.join()
    finally:
        jobs.pool = original

    assert esperar(job, 1)["situacao"] == "pronta"
    assert len(submissoes) == 1, f"{len(submissoes)} workers para a mesma página"
    print("OK: pedidos simultâneos da mesma página submetem um worker só")


def test_trabalho_apagado_nao_ressuscita_como_toco():
    """Trabalho apagado no meio da extração não pode voltar pela metade.

    A limpeza por cota pode levar um trabalho enquanto uma página dele ainda
    está em voo. O callback então gravava o estado, e o `ler_ficha(...) or {}`
    recriava a ficha sem `n_paginas` nem `nome` — um toco. As rotas seguintes
    estouravam `KeyError` e devolviam 500, quando a resposta honesta é 404: o
    trabalho não existe mais.
    """
    import shutil

    from web.api import jobs, storage

    job = enviar(bytes_do_pdf_vetorial())
    shutil.rmtree(storage.pasta(job), ignore_errors=True)
    jobs._gravar_estado(job, 1, {"situacao": "pronta"})

    assert storage.ler_ficha(job) is None, "a ficha do trabalho apagado voltou"
    assert cliente.get(f"/api/jobs/{job}").status_code == 404
    assert cliente.post(f"/api/jobs/{job}/pages/1").status_code == 404
    print("OK: trabalho apagado não ressuscita como ficha pela metade")


def test_falha_transitoria_ao_gravar_nao_prende_a_pagina():
    """Uma falha passageira ao gravar a ficha não pode prender a página.

    No Windows a troca atômica volta como `PermissionError` quando outro
    processo — antivírus, indexador, um `FileResponse` ainda aberto — segura o
    arquivo por um instante. Se isso acontece dentro do callback da extração, o
    `concurrent.futures` engole a exceção e a página fica em "na_fila" para
    sempre: o navegador pergunta e nunca recebe resposta.
    """
    from web.api import storage

    job = enviar(bytes_do_pdf_vetorial())

    real = os.replace
    POR_GRAVACAO = 3          # menos que storage.TENTATIVAS_DE_ACESSO
    restantes = [POR_GRAVACAO]
    total = [0]

    def replace_teimoso(origem, destino, *args, **kwargs):
        """Faz toda gravação da ficha falhar 3 vezes antes de deixar passar.

        Assim tanto a gravação do POST quanto a do callback da extração passam
        pelo caminho de repetição — é a do callback que importa, porque é a que
        ninguém está olhando.
        """
        if str(destino).endswith("ficha.json") and restantes[0] > 0:
            restantes[0] -= 1
            total[0] += 1
            raise PermissionError(5, "Acesso negado (simulado)")
        resposta = real(origem, destino, *args, **kwargs)
        if str(destino).endswith("ficha.json"):
            restantes[0] = POR_GRAVACAO
        return resposta

    storage.os.replace = replace_teimoso
    try:
        cliente.post(f"/api/jobs/{job}/pages/1")
        estado = esperar(job, 1, limite=30.0)
    finally:
        storage.os.replace = real

    assert total[0] >= 2 * POR_GRAVACAO, \
        f"só {total[0]} falhas: o callback não chegou a ser exercitado"
    assert estado["situacao"] == "pronta", estado
    print("OK: falha passageira ao gravar a ficha não prende a página")


def test_falha_transitoria_ao_ler_nao_derruba_a_consulta():
    """Uma falha passageira ao ler a ficha não pode virar 500 na consulta.

    É a mesma janela do teste acima, vista do outro lado. Enquanto
    `gravar_ficha` troca o destino, o arquivo fica um instante sem poder ser
    aberto por mais ninguém — e quem está do outro lado é justamente o
    navegador, perguntando o estado da página a cada 200 ms enquanto o worker
    termina. Sem paciência na leitura, o `PermissionError` sobe de `ler_ficha`
    por `jobs.estado` e a pergunta volta como 500 no meio da extração.
    """
    from web.api import storage

    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "pronta"

    real = open
    POR_LEITURA = 3           # menos que storage.TENTATIVAS_DE_ACESSO
    restantes = [POR_LEITURA]
    total = [0]

    def open_teimoso(arquivo, *args, **kwargs):
        """Faz toda abertura da ficha falhar 3 vezes antes de deixar passar.

        A rota lê a ficha duas vezes — uma em `_ficha_ou_404`, outra em
        `jobs.estado` —, e o contador volta ao cheio depois de cada abertura
        que passa, para que as duas leituras percorram o caminho de repetição.
        O temporário de `gravar_ficha` não entra aqui: o nome dele termina em
        `.tmp`, não em `ficha.json`.
        """
        if str(arquivo).endswith("ficha.json") and restantes[0] > 0:
            restantes[0] -= 1
            total[0] += 1
            raise PermissionError(13, "Permission denied (simulado)")
        resposta = real(arquivo, *args, **kwargs)
        if str(arquivo).endswith("ficha.json"):
            restantes[0] = POR_LEITURA
        return resposta

    # Nome no módulo, e não em `builtins`: `ler_ficha` procura `open` primeiro
    # nos globais de `storage`, então basta pôr um lá e tirá-lo depois — o
    # resto do processo continua com o `open` de verdade.
    storage.open = open_teimoso
    try:
        r = cliente.get(f"/api/jobs/{job}/pages/1")
    finally:
        del storage.open

    assert total[0] >= POR_LEITURA, \
        f"só {total[0]} falhas: a leitura não chegou a ser exercitada"
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] == "pronta", r.text
    print("OK: falha passageira ao ler a ficha não derruba a consulta")


def test_erro_inesperado_nao_se_disfarca_de_recurso():
    """Um defeito no servidor tem de chegar como `interno`, não como `recurso`.

    Apagar o original à mão simula uma falha que não é teto de memória nem de
    CPU. Enquanto tudo caía no mesmo `except`, um `FileNotFoundError` chegava ao
    usuário dizendo que a planta passou do limite de memória.
    """
    from web.api import storage

    job = enviar(bytes_do_pdf_vetorial())
    (storage.pasta(job) / "origem.pdf").unlink()
    cliente.post(f"/api/jobs/{job}/pages/1")
    estado = esperar(job, 1)
    assert estado["situacao"] == "erro", estado
    assert estado["codigo"] == "interno", estado
    print("OK: erro inesperado é classificado como interno")


if __name__ == "__main__":
    test_extracao_completa()
    test_pdf_original_e_apagado()
    test_pagina_inexistente()
    test_pdf_sem_vetores()
    test_teto_de_entidades()
    test_pedir_duas_vezes_nao_duplica()
    test_segunda_pagina_depois_da_primeira()
    test_original_some_quando_todas_as_paginas_terminam()
    test_pedidos_simultaneos_submetem_uma_vez()
    test_trabalho_apagado_nao_ressuscita_como_toco()
    test_falha_transitoria_ao_gravar_nao_prende_a_pagina()
    test_falha_transitoria_ao_ler_nao_derruba_a_consulta()
    test_erro_inesperado_nao_se_disfarca_de_recurso()
    print("Todos os testes de extração passaram.")
