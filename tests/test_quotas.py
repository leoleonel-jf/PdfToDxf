"""A cota: janela deslizante, reserva, confirmação e as chaves de configuração."""

import os
import sys
import tempfile

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

    # Página ruim antes de qualquer boa: solta.
    quotas.soltar("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 5

    # Boa e depois ruim: a ruim não desfaz.
    quotas.reservar(quem, "arquivo", "jobB", AGORA)
    quotas.confirmar("jobB")
    quotas.soltar("jobB")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4, "confirmado não solta"

    quotas.confirmar("jobB")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4, "confirmar não cobra"
    print("OK: confirmar e soltar são de mão única e idempotentes")


def test_a_mesma_referencia_nao_cobra_duas_vezes():
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "download", "jobA:chave1", AGORA)
    quotas.reservar(quem, "download", "jobA:chave1", AGORA)
    restam, _ = quotas.restante(quem, "download", AGORA)
    assert restam == 14, restam
    print("OK: a mesma referência não cobra duas vezes")


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
    test_a_mesma_referencia_nao_cobra_duas_vezes()
    test_downloads_do_visitante_param_no_decimo_sexto()
    test_logado_tem_o_triplo()
    test_chave_em_zero_nao_limita_e_ausente_cai_no_padrao()
    test_teto_de_mb_do_logado_e_truncado_no_teto_tecnico()
    test_conta_sem_confirmar_tem_cota_de_visitante()
    print("Todos os testes de cota passaram.")
