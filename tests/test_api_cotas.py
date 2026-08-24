"""A cota vista pelas rotas: 429 no envio, 429 no download, 413 por tamanho."""

import os
import sys
import tempfile
import time as _time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
if "PDFTODXF_REGISTROS" not in os.environ:
    os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")
# O mesmo cuidado do `PDFTODXF_DADOS`: no Windows o `ProcessPoolExecutor` usa
# spawn e reimporta este arquivo dentro de cada worker. Sem a guarda, cada
# worker criaria uma pasta temporária sua e a deixaria órfã.
if "PDFTODXF_BANCO" not in os.environ:
    os.environ["PDFTODXF_BANCO"] = os.path.join(
        tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial, esperar
from web.api import db, quotas
from web.api.main import app

# O `tests/test_api_extracao`, importado acima só pelas duas funções auxiliares,
# desliga a cota ao ser carregado — lá se testa a extração, e a bateria inteira
# não caberia em 5 envios. Aqui a cota **é** o assunto, e o padrão da tabela é
# justamente o que se quer exercitar: devolve as chaves ao estado ausente. Vem
# depois do import de propósito; antes, o import as apagaria de novo.
os.environ.pop("PDFTODXF_COTA_ARQUIVOS", None)
os.environ.pop("PDFTODXF_COTA_DOWNLOADS", None)

PEDIDO = {"escala": 0.01, "unidade": "m", "opcoes": {}}


def cliente_novo() -> TestClient:
    """Cliente com pote de cookies próprio: é um visitante diferente."""
    return TestClient(app)


def limpar_consumo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def enviar_com(cliente, dados=None):
    return cliente.post("/api/jobs", files={
        "arquivo": ("planta.pdf", dados or bytes_do_pdf_vetorial(),
                    "application/pdf")})


def estados_de(job: str) -> set:
    con = db.conexao()
    return {l["estado"] for l in con.execute(
        "SELECT estado FROM consumo WHERE referencia = ?", (job,))}


def esperar_estados(job: str, esperado: set, limite: float = 10.0) -> set:
    """Aguarda o consumo daquele trabalho chegar ao estado esperado.

    A ficha da página é gravada **antes** de a cota ser confirmada ou solta —
    é essa a ordem que faz a última página a falhar aparecer na contagem. Logo,
    quando `esperar` devolve, a linha de consumo ainda pode estar um instante
    atrás. Esperar aqui é o que impede o teste de ler o meio do caminho.
    """
    fim = _time.time() + limite
    atual = estados_de(job)
    while _time.time() < fim:
        atual = estados_de(job)
        if atual == esperado:
            return atual
        _time.sleep(0.05)
    return atual


def pdf_de_duas_paginas(vetorial: tuple) -> bytes:
    """Duas páginas; `vetorial` diz quais delas levam desenho."""
    import fitz
    doc = fitz.open()
    for tem_vetor in vetorial:
        page = doc.new_page(width=595, height=842)
        if tem_vetor:
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


def test_visitante_e_barrado_no_sexto_envio():
    limpar_consumo()
    cliente = cliente_novo()
    for i in range(5):
        r = enviar_com(cliente)
        assert r.status_code == 200, (i, r.status_code, r.text)

    r = enviar_com(cliente)
    assert r.status_code == 429, r.status_code
    corpo = r.json()
    assert corpo["codigo"] == "cota_arquivos", corpo
    assert corpo["libera_em"], corpo
    # A mensagem não conta qual balde estourou.
    assert "cookie" not in r.text.lower() and "ip" not in corpo["detail"].lower()
    print("OK: o sexto envio do visitante responde 429 com codigo e libera_em")


def test_o_cookie_do_visitante_e_gravado_no_primeiro_envio():
    limpar_consumo()
    cliente = cliente_novo()
    r = enviar_com(cliente)
    assert r.status_code == 200
    from web.api.identidade import COOKIE
    assert COOKIE in cliente.cookies, dict(cliente.cookies)
    print("OK: o cookie do visitante é gravado no primeiro envio")


def test_visitante_recusado_tambem_recebe_o_cookie():
    """A recusa não pode engolir o `Set-Cookie`.

    O handler de `Recusa` monta um `JSONResponse` novo, e o `Response` que a
    rota recebeu por injeção não chega até ele. Sem levar o cookie pendente
    junto, o visitante recusado recomeça num balde de cookie novo a cada
    tentativa: só o balde do IP seguraria o furo, e o do cookie viraria
    descartável.
    """
    limpar_consumo()
    from web.api.identidade import COOKIE
    os.environ["PDFTODXF_COTA_ARQUIVOS"] = "1"
    os.environ["PDFTODXF_COTA_FOLGA"] = "1"   # o balde do IP enche com 1 também
    try:
        primeiro = cliente_novo()
        assert enviar_com(primeiro).status_code == 200

        # Visitante novo, sem cookie nenhum: o balde do IP já está cheio, então
        # ele leva 429 no **primeiro** pedido — nenhum 200 gravou cookie antes.
        recusado = cliente_novo()
        r = enviar_com(recusado)
        assert r.status_code == 429, (r.status_code, r.text)
        assert "set-cookie" in r.headers, dict(r.headers)
        valor = recusado.cookies.get(COOKIE)
        assert valor, dict(recusado.cookies)

        # A tentativa seguinte manda o cookie de volta e o servidor o
        # reconhece: não grava outro, porque não há outro a gravar. É o mesmo
        # balde, e não um balde por tentativa.
        de_novo = enviar_com(recusado)
        assert de_novo.status_code == 429, de_novo.status_code
        assert "set-cookie" not in de_novo.headers, \
            "cookie novo a cada recusa: o balde do cookie virou descartável"
        assert recusado.cookies.get(COOKIE) == valor
    finally:
        os.environ.pop("PDFTODXF_COTA_ARQUIVOS", None)
        os.environ.pop("PDFTODXF_COTA_FOLGA", None)
    print("OK: o visitante recusado recebe o cookie e cai no mesmo balde")


def test_pdf_sem_vetores_solta_a_reserva():
    limpar_consumo()
    cliente = cliente_novo()
    # Um PDF válido e sem desenho vetorial: a extração falha com sem_vetores.
    import fitz
    doc = fitz.open()
    doc.new_page()
    vazio = doc.tobytes()
    doc.close()

    r = enviar_com(cliente, vazio)
    assert r.status_code == 200, r.text
    job = r.json()["job_id"]
    cliente.post(f"/api/jobs/{job}/pages/1")
    final = esperar(job, 1)
    assert final["situacao"] == "erro" and final["codigo"] == "sem_vetores", final
    assert esperar_estados(job, {"solto"}) == {"solto"}

    # A vaga voltou: cinco envios bons ainda cabem.
    for i in range(5):
        assert enviar_com(cliente).status_code == 200, i
    print("OK: PDF sem vetores solta a reserva")


def test_pagina_boa_confirma_e_pagina_ruim_depois_nao_desfaz():
    limpar_consumo()
    cliente = cliente_novo()
    r = enviar_com(cliente)
    job = r.json()["job_id"]
    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "pronta"

    # Uma página inexistente não solta nada — e nem chega ao worker.
    cliente.post(f"/api/jobs/{job}/pages/99")

    estados = esperar_estados(job, {"confirmado"})
    assert estados == {"confirmado"}, estados
    print("OK: a página boa confirma, e o que vem depois não desfaz")


def test_pagina_ruim_antes_da_boa_nao_devolve_a_vaga():
    """Documento misto: a primeira página falhar não pode soltar a reserva.

    Soltar por página deixava furar o teto — converter primeiro a página
    escaneada devolvia a vaga, o upload seguinte entrava, e converter depois a
    página vetorial promovia uma reserva já solta.
    """
    limpar_consumo()
    cliente = cliente_novo()
    job = enviar_com(cliente, pdf_de_duas_paginas((False, True))).json()["job_id"]

    cliente.post(f"/api/jobs/{job}/pages/1")
    final = esperar(job, 1)
    assert final["situacao"] == "erro" and final["codigo"] == "sem_vetores", final
    # Meio segundo de folga: se a soltura fosse por página, ela já teria
    # acontecido; esperar só ajudaria a esconder o defeito.
    _time.sleep(0.5)
    estados = estados_de(job)
    assert estados == {"reservado"}, estados

    cliente.post(f"/api/jobs/{job}/pages/2")
    assert esperar(job, 2)["situacao"] == "pronta"
    estados = esperar_estados(job, {"confirmado"})
    assert estados == {"confirmado"}, estados
    print("OK: página ruim antes da boa não devolve a vaga, e a boa confirma")


def test_documento_todo_ruim_devolve_a_vaga_so_no_fim():
    """Duas páginas sem vetores: a vaga volta só depois de as duas terminarem."""
    limpar_consumo()
    cliente = cliente_novo()
    job = enviar_com(cliente, pdf_de_duas_paginas((False, False))).json()["job_id"]

    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "erro"
    _time.sleep(0.5)
    estados = estados_de(job)
    assert estados == {"reservado"}, estados

    cliente.post(f"/api/jobs/{job}/pages/2")
    assert esperar(job, 2)["situacao"] == "erro"
    estados = esperar_estados(job, {"solto"})
    assert estados == {"solto"}, estados
    print("OK: documento todo ruim devolve a vaga só depois da última página")


def test_combinacao_repetida_nao_consome_download():
    limpar_consumo()
    cliente = cliente_novo()
    job = enviar_com(cliente).json()["job_id"]
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)

    a = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
    assert a.status_code == 200 and a.json()["cache"] is False
    b = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
    assert b.status_code == 200 and b.json()["cache"] is True

    con = db.conexao()
    n = con.execute("SELECT count(*) AS n FROM consumo WHERE tipo = 'download'"
                    ).fetchone()["n"]
    # Dois baldes (cookie e IP), um consumo só: a segunda vez não cobrou.
    assert n == 2, n

    # Mudar qualquer campo cobra de novo.
    outro = {**PEDIDO, "unidade": "cm"}
    c = cliente.post(f"/api/jobs/{job}/pages/1/export", json=outro)
    assert c.status_code == 200 and c.json()["cache"] is False
    n2 = con.execute("SELECT count(*) AS n FROM consumo WHERE tipo = 'download'"
                     ).fetchone()["n"]
    assert n2 == 4, n2
    print("OK: repetir a combinação não consome; mudar um campo consome")


def test_baixar_o_arquivo_nunca_cobra():
    limpar_consumo()
    cliente = cliente_novo()
    job = enviar_com(cliente).json()["job_id"]
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    url = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO).json()["url"]

    con = db.conexao()
    antes = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]
    for _ in range(3):
        assert cliente.get(url).status_code == 200
    depois = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]
    assert antes == depois, (antes, depois)
    print("OK: GET /api/download nunca cobra")


def test_navegar_e_extrair_nao_consomem():
    limpar_consumo()
    cliente = cliente_novo()
    job = enviar_com(cliente).json()["job_id"]
    con = db.conexao()
    antes = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]

    cliente.get(f"/api/jobs/{job}")
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    cliente.get(f"/api/jobs/{job}/pages/1")
    cliente.get(f"/api/jobs/{job}/pages/1/meta.json")
    cliente.get(f"/api/jobs/{job}/pages/1/geometry.bin?parte=esqueleto")

    depois = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]
    assert antes == depois, (antes, depois)
    print("OK: navegar, extrair e baixar geometria não consomem cota")


def test_pdf_acima_do_teto_do_plano_e_recusado_com_o_numero():
    limpar_consumo()
    cliente = cliente_novo()
    os.environ["PDFTODXF_COTA_MB"] = "1"
    try:
        grande = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)
        r = cliente.post("/api/jobs", files={
            "arquivo": ("grande.pdf", grande, "application/pdf")})
        assert r.status_code == 413, r.status_code
        corpo = r.json()
        assert corpo["codigo"] == "tamanho", corpo
        assert corpo["teto_bytes"] == 1024 * 1024, corpo
    finally:
        del os.environ["PDFTODXF_COTA_MB"]
    # Recusado antes de reservar: nenhuma linha de consumo foi gravada.
    con = db.conexao()
    n = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]
    assert n == 0, n
    print("OK: PDF acima do teto do plano é 413 com o teto em bytes, sem cobrar")


def test_download_esgotado_responde_429():
    limpar_consumo()
    cliente = cliente_novo()
    os.environ["PDFTODXF_COTA_DOWNLOADS"] = "1"
    try:
        job = enviar_com(cliente).json()["job_id"]
        cliente.post(f"/api/jobs/{job}/pages/1")
        esperar(job, 1)
        assert cliente.post(f"/api/jobs/{job}/pages/1/export",
                            json=PEDIDO).status_code == 200
        r = cliente.post(f"/api/jobs/{job}/pages/1/export",
                         json={**PEDIDO, "unidade": "cm"})
        assert r.status_code == 429, r.status_code
        assert r.json()["codigo"] == "cota_downloads", r.json()

        # Repetir a combinação já gerada continua livre, mesmo sem vaga.
        de_novo = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
        assert de_novo.status_code == 200 and de_novo.json()["cache"] is True
    finally:
        del os.environ["PDFTODXF_COTA_DOWNLOADS"]
    print("OK: download esgotado é 429, e repetir o que já existe continua livre")


if __name__ == "__main__":
    test_visitante_e_barrado_no_sexto_envio()
    test_o_cookie_do_visitante_e_gravado_no_primeiro_envio()
    test_visitante_recusado_tambem_recebe_o_cookie()
    test_pdf_sem_vetores_solta_a_reserva()
    test_pagina_boa_confirma_e_pagina_ruim_depois_nao_desfaz()
    test_pagina_ruim_antes_da_boa_nao_devolve_a_vaga()
    test_documento_todo_ruim_devolve_a_vaga_so_no_fim()
    test_combinacao_repetida_nao_consome_download()
    test_baixar_o_arquivo_nunca_cobra()
    test_navegar_e_extrair_nao_consomem()
    test_pdf_acima_do_teto_do_plano_e_recusado_com_o_numero()
    test_download_esgotado_responde_429()
    print("Todos os testes de cota nas rotas passaram.")
