"""A cota: janela deslizante, reserva, confirmação e as chaves de configuração."""

import contextlib
import io
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from web.api import db, identidade, limits, quotas

AGORA = 1_755_000_000.0


def visitante(cookie: str, ip: str = "198.51.100.1") -> identidade.Identidade:
    return identidade.Identidade(
        tipo="visitante", usuario_id=None, confirmado=False,
        baldes=(identidade.Balde(db.marca(f"cookie:{cookie}"), 1),
                identidade.Balde(db.marca(f"ip:{ip}"), 4)),
        cookie_novo=None)


def logado(uid: int, confirmado: bool = True) -> identidade.Identidade:
    return identidade.Identidade(
        tipo="logado", usuario_id=uid, confirmado=confirmado,
        baldes=(identidade.Balde(db.marca(f"usuario:{uid}"), 1),),
        cookie_novo=None)


def limpar_tudo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def estados(referencia: str | None = None) -> dict:
    """Quantas linhas há em cada estado — o que o banco de fato guardou."""
    con = db.conexao()
    if referencia is None:
        linhas = con.execute(
            "SELECT estado, count(*) AS n FROM consumo GROUP BY estado")
    else:
        linhas = con.execute(
            "SELECT estado, count(*) AS n FROM consumo "
            "WHERE referencia = ? GROUP BY estado", (referencia,))
    return {l["estado"]: int(l["n"]) for l in linhas}


def test_visitante_envia_cinco_e_para_no_sexto():
    limpar_tudo()
    quem = visitante("c1")
    for i in range(5):
        quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
    try:
        quotas.reservar(quem, "arquivo", "job5", AGORA)
        raise AssertionError("o sexto tinha que ser recusado")
    except quotas.SemVaga as e:
        assert e.tipo == "arquivo"
        assert e.libera_em and e.libera_em > AGORA
    print("OK: visitante envia 5 arquivos e é barrado no sexto")


def test_limpar_o_cookie_nao_devolve_cota():
    """O balde do IP continua contando, e é ele que tapa o furo do cookie."""
    limpar_tudo()
    for i in range(5):
        quotas.reservar(visitante("c1"), "arquivo", f"job{i}", AGORA)
    # Cookie novo, mesmo IP: cabe, porque o IP tem folga de 4x (teto 20).
    quotas.reservar(visitante("c2"), "arquivo", "job5", AGORA)

    for i in range(6, 20):
        quotas.reservar(visitante(f"c{i}"), "arquivo", f"job{i}", AGORA)
    try:
        quotas.reservar(visitante("c-final"), "arquivo", "job20", AGORA)
        raise AssertionError("o vigésimo primeiro tinha que ser recusado")
    except quotas.SemVaga:
        pass
    print("OK: limpar o cookie não devolve cota; o IP barra no 21º")


def test_a_janela_desliza():
    limpar_tudo()
    quem = visitante("c1")
    velho = AGORA - quotas.janela_s() - 1
    for i in range(5):
        quotas.reservar(quem, "arquivo", f"job{i}", velho)
    quotas.reservar(quem, "arquivo", "novo", AGORA)
    restam, _ = quotas.restante(quem, "arquivo", AGORA)
    assert restam == 4, restam
    print("OK: a janela desliza — consumo de 2 h e 1 s atrás não conta")


def test_confirmar_e_soltar_sao_de_mao_unica():
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "arquivo", "jobA", AGORA)

    # Página ruim antes de qualquer boa: solta — e soltar de novo não muda nada.
    quotas.soltar("jobA")
    quotas.soltar("jobA")
    assert estados("jobA") == {"solto": 2}, estados("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 5

    # Boa e depois ruim: a ruim não desfaz.
    quotas.reservar(quem, "arquivo", "jobB", AGORA)
    quotas.confirmar("jobB")
    quotas.soltar("jobB")
    assert estados("jobB") == {"confirmado": 2}, "confirmado não solta"
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4

    # Confirmar de novo não duplica linha nem move o que já estava confirmado:
    # a contagem por estado é o que revela isso — o saldo sozinho não revelaria.
    quotas.confirmar("jobB")
    assert estados() == {"solto": 2, "confirmado": 2}, estados()
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4
    print("OK: confirmar e soltar são de mão única e idempotentes")


def test_ruim_antes_da_boa_a_boa_cobra():
    """Página 1 escaneada solta; página 2 com vetores cobra. O saldo cai."""
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "arquivo", "jobA", AGORA)
    quotas.soltar("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 5, "solto não ocupa vaga"
    quotas.confirmar("jobA")
    assert estados("jobA") == {"confirmado": 2}, estados("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4, "a página boa cobra"
    print("OK: ruim antes da boa — a boa cobra, o arquivo não sai de graça")


def test_boa_antes_da_ruim_a_ruim_nao_desfaz():
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "arquivo", "jobB", AGORA)
    quotas.confirmar("jobB")
    quotas.soltar("jobB")
    assert estados("jobB") == {"confirmado": 2}, estados("jobB")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4
    print("OK: boa antes da ruim — a ruim não desfaz o que foi confirmado")


def test_reserva_nunca_confirmada_continua_contando():
    limpar_tudo()
    quem = visitante("c1")
    for i in range(5):
        quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
    assert estados() == {"reservado": 10}, estados()
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 0
    try:
        quotas.reservar(quem, "arquivo", "job5", AGORA)
        raise AssertionError("reserva não confirmada tinha que continuar contando")
    except quotas.SemVaga:
        pass
    print("OK: reserva nunca confirmada continua ocupando a vaga")


def test_a_mesma_referencia_nao_cobra_duas_vezes():
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "download", "jobA:chave1", AGORA)
    quotas.reservar(quem, "download", "jobA:chave1", AGORA)
    restam, _ = quotas.restante(quem, "download", AGORA)
    assert restam == 14, restam

    # Outra identidade com a mesma referência **paga**: `job_id` é um uuid e a
    # rota não é presa à identidade, então quem recebe o link de um trabalho
    # alheio não herda a combinação que o dono pagou.
    outro = visitante("c2", ip="203.0.113.9")
    quotas.reservar(outro, "download", "jobA:chave1", AGORA)
    assert quotas.restante(outro, "download", AGORA)[0] == 14, "identidade nova paga"
    assert quotas.restante(quem, "download", AGORA)[0] == 14, "o dono não paga de novo"
    print("OK: a mesma referência não cobra duas vezes, mas outra identidade paga")


def test_libera_em_e_o_maior_entre_os_baldes_cheios():
    """Só há vaga quando todos os baldes tiverem vaga: manda o que libera por último."""
    limpar_tudo()
    quem = visitante("c1")
    cookie, ip = quem.baldes
    con = db.conexao()
    # Cookie cheio desde AGORA (teto 5), IP cheio desde AGORA+3600 (teto 20):
    # o cookie libera em AGORA+7200, o IP em AGORA+10800.
    con.executemany(
        "INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
        "VALUES (?, ?, ?, ?, ?)",
        [(cookie.chave, "arquivo", "confirmado", AGORA, f"c{i}")
         for i in range(5)]
        + [(ip.chave, "arquivo", "confirmado", AGORA + 3600, f"i{i}")
           for i in range(20)])
    con.commit()

    agora = AGORA + 3600
    esperado = AGORA + 3600 + quotas.janela_s()
    assert quotas.restante(quem, "arquivo", agora) == (0, esperado), \
        quotas.restante(quem, "arquivo", agora)
    try:
        quotas.reservar(quem, "arquivo", "novo", agora)
        raise AssertionError("com os dois baldes cheios tinha que recusar")
    except quotas.SemVaga as e:
        assert e.libera_em == esperado, (e.libera_em, esperado)

    # E no instante anunciado a vaga existe de verdade.
    quotas.reservar(quem, "arquivo", "novo", esperado)
    print("OK: libera_em é o maior entre os baldes cheios, e nele a vaga existe")


def test_dezesseis_ao_mesmo_tempo_passam_exatamente_cinco():
    """Contar e inserir são um passo só — sem `BEGIN IMMEDIATE` isso quebra."""
    limpar_tudo()
    quem = visitante("c-corrida")
    n = 16
    portao = threading.Barrier(n)
    passou, recusado, erros = [], [], []

    def tentar(i):
        portao.wait()
        try:
            quotas.reservar(quem, "arquivo", f"corrida{i}", AGORA)
            passou.append(i)
        except quotas.SemVaga:
            recusado.append(i)
        except Exception as e:  # noqa: BLE001 — qualquer erro é falha do teste
            erros.append(repr(e))
        finally:
            db.fechar()

    fios = [threading.Thread(target=tentar, args=(i,)) for i in range(n)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()

    assert not erros, erros
    assert len(passou) == 5, (len(passou), len(recusado))
    assert len(recusado) == n - 5, len(recusado)
    linhas = db.conexao().execute("SELECT count(*) AS n FROM consumo").fetchone()
    assert int(linhas["n"]) == 5 * len(quem.baldes), int(linhas["n"])
    print(f"OK: {n} pedidos ao mesmo tempo e exatamente 5 passam")


def test_downloads_do_visitante_param_no_decimo_sexto():
    limpar_tudo()
    quem = visitante("c1")
    for i in range(15):
        quotas.cobrar(quem, "download", f"jobA:{i}", AGORA)
    try:
        quotas.cobrar(quem, "download", "jobA:16", AGORA)
        raise AssertionError("o décimo sexto tinha que ser recusado")
    except quotas.SemVaga as e:
        assert e.tipo == "download"
    print("OK: visitante baixa 15 combinações inéditas e para na décima sexta")


def test_logado_tem_o_triplo():
    limpar_tudo()
    quem = logado(1)
    assert quotas.limites(quem)["arquivos"] == 15
    assert quotas.limites(quem)["downloads"] == 45
    for i in range(15):
        quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
    try:
        quotas.reservar(quem, "arquivo", "job15", AGORA)
        raise AssertionError("o décimo sexto tinha que ser recusado")
    except quotas.SemVaga:
        pass
    print("OK: logado tem o triplo da cota do visitante")


def test_chave_em_zero_nao_limita_e_ausente_cai_no_padrao():
    limpar_tudo()
    quem = visitante("c1")
    os.environ["PDFTODXF_COTA_ARQUIVOS"] = "0"
    try:
        for i in range(30):
            quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
        restam, libera = quotas.restante(quem, "arquivo", AGORA)
        assert restam is None and libera is None, (restam, libera)
    finally:
        del os.environ["PDFTODXF_COTA_ARQUIVOS"]
    assert quotas.limites(visitante("c9"))["arquivos"] == 5, "ausente cai no padrão"
    print("OK: chave em 0 não limita; chave ausente cai no padrão")


def test_chave_negativa_cai_no_padrao():
    """`-1` é "sem limite" em outros sistemas; aqui é lixo, e lixo vira padrão."""
    limpar_tudo()
    for cru in ("-1", "-999"):
        os.environ["PDFTODXF_COTA_ARQUIVOS"] = cru
        try:
            assert quotas.limites(visitante("c1"))["arquivos"] == 5, cru
            quem = visitante(f"neg{cru}")
            for i in range(5):
                quotas.reservar(quem, "arquivo", f"neg{cru}-{i}", AGORA)
            try:
                quotas.reservar(quem, "arquivo", f"neg{cru}-5", AGORA)
                raise AssertionError(f"{cru} não podia abrir a cota inteira")
            except quotas.SemVaga:
                pass
        finally:
            del os.environ["PDFTODXF_COTA_ARQUIVOS"]
    print("OK: chave negativa cai no padrão, não em sem-limite")


def test_janela_em_zero_cai_no_padrao():
    os.environ["PDFTODXF_COTA_JANELA_H"] = "0"
    try:
        assert quotas.janela_s() == 2 * 60 * 60, quotas.janela_s()
    finally:
        del os.environ["PDFTODXF_COTA_JANELA_H"]
    print("OK: janela em 0 cai no padrão de 2 h, não vira janela infinita")


def test_janela_maior_que_a_limpeza_avisa_uma_vez():
    os.environ["PDFTODXF_COTA_JANELA_H"] = "48"
    quotas._avisou_janela = False
    saida = io.StringIO()
    try:
        with contextlib.redirect_stdout(saida):
            assert quotas.janela_s() == 48 * 60 * 60
            quotas.janela_s()
            quotas.janela_s()
    finally:
        del os.environ["PDFTODXF_COTA_JANELA_H"]
        quotas._avisou_janela = False
    texto = saida.getvalue()
    assert texto.count("PDFTODXF_COTA_JANELA_H") == 1, texto

    calada = io.StringIO()
    with contextlib.redirect_stdout(calada):
        quotas.janela_s()
    assert calada.getvalue() == "", calada.getvalue()
    print("OK: janela acima do prazo da limpeza avisa, e avisa uma vez só")


def test_tipo_desconhecido_e_erro():
    """Um `"arquivos"` no plural pegaria o teto errado e abriria um balde vazio."""
    quem = visitante("c1")
    tentativas = (
        lambda: quotas.reservar(quem, "arquivos", "jobX", AGORA),
        lambda: quotas.cobrar(quem, "downloads", "jobX", AGORA),
        lambda: quotas.restante(quem, "arquivos", AGORA),
    )
    for tentar in tentativas:
        try:
            tentar()
            raise AssertionError("tipo fora da lista tinha que levantar ValueError")
        except ValueError:
            pass
    print("OK: tipo fora de (arquivo, download) levanta ValueError")


def test_teto_de_mb_do_logado_e_truncado_no_teto_tecnico():
    os.environ["PDFTODXF_COTA_MB_LOGADO"] = "500"
    try:
        assert quotas.limites(logado(1))["bytes"] == limits.TETO_PDF_BYTES
    finally:
        del os.environ["PDFTODXF_COTA_MB_LOGADO"]
    assert quotas.limites(visitante("c1"))["bytes"] == 10 * 1024 * 1024
    print("OK: o teto de MB do logado nunca passa do teto técnico")


def test_conta_sem_confirmar_tem_cota_de_visitante():
    quem = logado(3, confirmado=False)
    assert quotas.limites(quem)["arquivos"] == 5
    assert quotas.limites(quem)["bytes"] == 10 * 1024 * 1024
    print("OK: conta sem confirmar fica com a cota de visitante")


if __name__ == "__main__":
    test_visitante_envia_cinco_e_para_no_sexto()
    test_limpar_o_cookie_nao_devolve_cota()
    test_a_janela_desliza()
    test_confirmar_e_soltar_sao_de_mao_unica()
    test_ruim_antes_da_boa_a_boa_cobra()
    test_boa_antes_da_ruim_a_ruim_nao_desfaz()
    test_reserva_nunca_confirmada_continua_contando()
    test_a_mesma_referencia_nao_cobra_duas_vezes()
    test_libera_em_e_o_maior_entre_os_baldes_cheios()
    test_dezesseis_ao_mesmo_tempo_passam_exatamente_cinco()
    test_downloads_do_visitante_param_no_decimo_sexto()
    test_logado_tem_o_triplo()
    test_chave_em_zero_nao_limita_e_ausente_cai_no_padrao()
    test_chave_negativa_cai_no_padrao()
    test_janela_em_zero_cai_no_padrao()
    test_janela_maior_que_a_limpeza_avisa_uma_vez()
    test_tipo_desconhecido_e_erro()
    test_teto_de_mb_do_logado_e_truncado_no_teto_tecnico()
    test_conta_sem_confirmar_tem_cota_de_visitante()
    print("Todos os testes de cota passaram.")
