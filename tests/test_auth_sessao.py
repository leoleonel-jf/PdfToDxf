"""Entrar, sair, e o que a sessão muda na cota."""

import hashlib
import os
import sys
import tempfile
import threading
import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
if "PDFTODXF_REGISTROS" not in os.environ:
    os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial
from web.api import auth, db, identidade
from web.api.main import app

# O `tests/test_api_extracao`, importado acima só pela fábrica de PDF, desliga a
# cota ao ser carregado (`PDFTODXF_COTA_ARQUIVOS=0`, que é "sem limite"). Aqui
# metade da bateria mede justamente a diferença entre a cota do visitante e a do
# logado: sem devolver as chaves ao estado ausente, os testes de 429 nunca
# barrariam nada e passariam por não fazer nada. Vem depois do import de
# propósito; antes, o import as apagaria de novo.
os.environ.pop("PDFTODXF_COTA_ARQUIVOS", None)
os.environ.pop("PDFTODXF_COTA_DOWNLOADS", None)


def cliente_novo() -> TestClient:
    return TestClient(app)


def limpar_consumo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def conta_pronta(email: str, senha: str = "abc12345") -> int:
    uid = auth.criar_conta(email, senha, "127.0.0.1")
    auth.confirmar_conta(uid)
    return uid


def um_pdf():
    return {"arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")}


class PedidoComCookie:
    """O mínimo de um `Request` que `auth` lê da sessão."""

    def __init__(self, valor):
        self.cookies = {auth.COOKIE_SESSAO: valor}
        self.headers = {}
        self.client = type("C", (), {"host": "127.0.0.1"})()


def contando_scrypt(fazer) -> int:
    """Roda `fazer` e devolve quantas vezes `hashlib.scrypt` foi chamado.

    Contador, e não cronômetro: um limiar de tempo daria teste intermitente, e
    o que se quer afirmar é exato — os dois caminhos pagam o mesmo número de
    hashes. A trava existe porque a rota roda no pool de threads do FastAPI.

    Mesmo desenho de `tests/test_auth_cadastro.py`, e duplicado de propósito:
    importar aquele módulo aqui reapontaria `PDFTODXF_BANCO` para o banco dele.
    """
    real = hashlib.scrypt
    trava = threading.Lock()
    quantas = [0]

    def contado(*args, **kwargs):
        with trava:
            quantas[0] += 1
        return real(*args, **kwargs)

    with mock.patch.object(hashlib, "scrypt", contado):
        fazer()
    return quantas[0]


def test_entrar_e_sair():
    conta_pronta("gil@exemplo.com")
    cliente = cliente_novo()
    r = cliente.post("/api/auth/entrar",
                     json={"email": "GIL@exemplo.com", "senha": "abc12345"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "gil@exemplo.com"
    assert auth.COOKIE_SESSAO in cliente.cookies

    r = cliente.post("/api/auth/sair")
    assert r.status_code == 200
    assert not cliente.cookies.get(auth.COOKIE_SESSAO)
    print("OK: entrar grava a sessão e sair a apaga")


def test_email_inexistente_e_senha_errada_respondem_igual():
    conta_pronta("hel@exemplo.com")
    cliente = cliente_novo()
    a = cliente.post("/api/auth/entrar",
                     json={"email": "hel@exemplo.com", "senha": "errada!!"})
    b = cliente.post("/api/auth/entrar",
                     json={"email": "ninguem@exemplo.com", "senha": "errada!!"})
    assert a.status_code == b.status_code == 401, (a.status_code, b.status_code)
    assert a.json() == b.json(), (a.json(), b.json())
    print("OK: e-mail inexistente e senha errada devolvem a mesma coisa")


def test_o_cookie_de_sessao_e_httponly_e_samesite():
    conta_pronta("ines@exemplo.com")
    cliente = cliente_novo()
    r = cliente.post("/api/auth/entrar",
                     json={"email": "ines@exemplo.com", "senha": "abc12345"})
    bruto = r.headers.get("set-cookie", "")
    assert "httponly" in bruto.lower(), bruto
    assert "samesite=lax" in bruto.lower(), bruto
    print("OK: o cookie de sessão é HttpOnly e SameSite=Lax")


def _cookie_de(bruto_lista, nome: str) -> str:
    """O `Set-Cookie` cru daquele nome, dentre os que a resposta trouxe."""
    for bruto in bruto_lista:
        if bruto.startswith(f"{nome}="):
            return bruto
    raise AssertionError(f"nenhum Set-Cookie de {nome!r} em {bruto_lista}")


def test_cookie_de_sessao_leva_secure_so_em_https():
    """`Secure` depende do esquema do pedido, não de uma constante.

    `request.url.scheme == "https"` é o que decide `seguro` em `_gravar_sessao`.
    Sem este teste, `seguro = False` sempre passava as seis baterias — o cookie
    de sessão sairia sem `Secure` mesmo atrás de HTTPS em produção, viajando em
    claro num downgrade — porque nenhum teste lia o `Set-Cookie` cru. O
    `TestClient` aceita `base_url` com esquema; aqui os dois é que importam.
    """
    conta_pronta("bia@exemplo.com")

    def entrar(base_url: str) -> str:
        cliente = TestClient(app, base_url=base_url)
        r = cliente.post("/api/auth/entrar",
                         json={"email": "bia@exemplo.com", "senha": "abc12345"})
        assert r.status_code == 200, r.text
        return _cookie_de(r.headers.get_list("set-cookie"), auth.COOKIE_SESSAO)

    via_https = entrar("https://testserver")
    via_http = entrar("http://testserver")

    assert "secure" in via_https.lower(), via_https
    assert "secure" not in via_http.lower(), via_http
    for bruto in (via_https, via_http):
        assert "httponly" in bruto.lower(), bruto
        assert "samesite=lax" in bruto.lower(), bruto
    print("OK: cookie de sessão leva Secure em https e não em http")


def test_cookie_de_visitante_leva_secure_so_em_https():
    """O mesmo defeito de `Secure`, agora para `identidade.gravar_cookie`.

    `quem_pede` calcula `seguro` do mesmo jeito para os dois cookies; o furo
    de `_gravar_sessao` podia muito bem existir aqui também, sem teste nenhum
    que falasse nisso.
    """
    limpar_consumo()

    def enviar(base_url: str) -> str:
        cliente = TestClient(app, base_url=base_url)
        r = cliente.post("/api/jobs", files=um_pdf())
        assert r.status_code == 200, r.text
        return _cookie_de(r.headers.get_list("set-cookie"), identidade.COOKIE)

    via_https = enviar("https://testserver")
    via_http = enviar("http://testserver")

    assert "secure" in via_https.lower(), via_https
    assert "secure" not in via_http.lower(), via_http
    for bruto in (via_https, via_http):
        assert "httponly" in bruto.lower(), bruto
        assert "samesite=lax" in bruto.lower(), bruto
    print("OK: cookie de visitante leva Secure em https e não em http")


def test_sessao_forjada_e_vencida_nao_valem():
    P = PedidoComCookie
    uid = conta_pronta("joa@exemplo.com")
    assert auth.dono_da_sessao(P("inventado")) is None
    assert auth.dono_da_sessao(P("")) is None
    velha = auth.criar_sessao(uid, agora=time.time() - auth.PRAZO_SESSAO_S - 10)
    assert auth.dono_da_sessao(P(velha)) is None, "sessão vencida não vale"
    boa = auth.criar_sessao(uid)
    assert auth.dono_da_sessao(P(boa)) == (uid, True)
    print("OK: sessão forjada ou vencida não vale")


def test_sessao_emitida_no_futuro_nao_vale():
    """O prazo tem piso, e não só teto.

    `time.time() - emitida` fica negativo para uma emissão à frente do agora, e
    o teto de prazo nunca dispara: o cookie valeria para sempre. Não é forjável
    sem o segredo e `criar_sessao` não produz isso sozinha — o caso real é o
    relógio do servidor andar para trás depois de emitir.
    """
    uid = conta_pronta("qua@exemplo.com")

    do_futuro = auth.criar_sessao(uid, agora=time.time() + 24 * 60 * 60)
    assert auth.dono_da_sessao(PedidoComCookie(do_futuro)) is None, \
        "emissão no futuro não pode valer — e valeria para sempre"
    assert auth.precisa_renovar(PedidoComCookie(do_futuro)) is False

    # Bem no limite: a folga existe para tolerar relógio ligeiramente
    # adiantado, e não pode derrubar sessão legítima.
    quase = auth.criar_sessao(
        uid, agora=time.time() + auth.FOLGA_DE_RELOGIO_S / 2)
    assert auth.dono_da_sessao(PedidoComCookie(quase)) == (uid, True), \
        "a folga de relógio tem de continuar aceitando"
    print("OK: sessão emitida no futuro não vale, mas a folga de relógio sim")


def test_sessao_de_conta_apagada_nao_vale():
    """Cookie válido, assinatura boa, prazo em dia — e a conta não existe mais.

    Sem a consulta a `por_id`, `dono_da_sessao` devolveria um `Dono` inventado
    a partir do que está escrito no cookie, e o cookie ressuscitaria a conta
    apagada.
    """
    uid = conta_pronta("rui@exemplo.com")
    valor = auth.criar_sessao(uid)
    assert auth.dono_da_sessao(PedidoComCookie(valor)) == (uid, True)

    con = db.conexao()
    con.execute("DELETE FROM usuarios WHERE id = ?", (uid,))
    con.commit()

    assert auth.dono_da_sessao(PedidoComCookie(valor)) is None, \
        "a conta sumiu; o cookie não pode ressuscitá-la"
    print("OK: sessão de conta apagada não vale")


def test_entrar_gasta_o_mesmo_scrypt_nos_dois_jeitos_de_recusar():
    """O oráculo de enumeração pelo relógio, medido por contagem.

    A resposta é idêntica byte a byte nos dois casos, mas sem `queimar_tempo`
    o e-mail inexistente sai sem pagar `scrypt` nenhum e a senha errada paga
    um — e o cronômetro conta o que a mensagem calou. Contador, e não
    cronômetro: o que se afirma é exato.
    """
    conta_pronta("olga@exemplo.com")
    cliente = cliente_novo()
    # Pré-aquece o hash de mentira: a **primeira** chamada de `queimar_tempo`
    # paga `hash_senha` *e* `conferir_senha`, e a contagem sairia 2 contra 1
    # por um motivo que não é o que este teste mede. Em produção quem pré-
    # aquece é o `ciclo_de_vida`.
    auth.queimar_tempo()

    def recusar(email):
        def fazer():
            r = cliente.post("/api/auth/entrar",
                             json={"email": email, "senha": "nao-e-a-senha"})
            assert r.status_code == 401, r.text
        return contando_scrypt(fazer)

    inexistente = recusar("ninguem-mesmo@exemplo.com")
    senha_errada = recusar("olga@exemplo.com")

    assert senha_errada >= 1, "a senha errada tem de pagar um scrypt de verdade"
    assert inexistente == senha_errada, (
        f"e-mail inexistente gastou {inexistente} scrypt e senha errada gastou "
        f"{senha_errada}: a diferença vira um oráculo de quem tem conta, mesmo "
        "com a resposta idêntica byte a byte")
    print("OK: e-mail inexistente e senha errada pagam o mesmo número de scrypt")


def test_entrar_reescreve_hash_de_parametros_fracos():
    """Entrar com um hash antigo tem de deixá-lo com os parâmetros de hoje.

    `precisa_reescrever` sozinho já é testado em `test_auth_cadastro`; o que se
    afirma aqui é a **fiação** — que a rota de entrada de fato chama, grava, e
    que a senha continua entrando depois.
    """
    uid = conta_pronta("pia@exemplo.com")
    fraco = auth.hash_senha("abc12345", n=4096)
    con = db.conexao()
    con.execute("UPDATE usuarios SET senha = ? WHERE id = ?", (fraco, uid))
    con.commit()
    assert auth.precisa_reescrever(auth.por_email("pia@exemplo.com")["senha"])

    r = cliente_novo().post("/api/auth/entrar",
                            json={"email": "pia@exemplo.com",
                                  "senha": "abc12345"})
    assert r.status_code == 200, r.text

    guardado = auth.por_email("pia@exemplo.com")["senha"]
    assert guardado != fraco, "o hash fraco tinha de ter sido reescrito"
    assert not auth.precisa_reescrever(guardado), guardado
    assert guardado.split("$")[1:4] == [str(auth.N), str(auth.R), str(auth.P)], \
        guardado
    assert auth.conferir_senha("abc12345", guardado), \
        "a senha tem de continuar valendo depois da reescrita"
    r = cliente_novo().post("/api/auth/entrar",
                            json={"email": "pia@exemplo.com",
                                  "senha": "abc12345"})
    assert r.status_code == 200, r.text
    print("OK: entrar reescreve o hash fraco com os parâmetros de hoje")


def test_trocar_o_segredo_invalida_as_sessoes():
    uid = conta_pronta("kai@exemplo.com")
    valor = auth.criar_sessao(uid)

    class P:
        cookies = {auth.COOKIE_SESSAO: valor}
        headers = {}
        client = type("C", (), {"host": "127.0.0.1"})()

    assert auth.dono_da_sessao(P()) is not None
    os.environ["PDFTODXF_SEGREDO"] = "outro-segredo"
    try:
        assert auth.dono_da_sessao(P()) is None
    finally:
        os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"
    print("OK: trocar o segredo invalida as sessões emitidas antes")


def test_logado_confirmado_envia_mais_que_visitante():
    limpar_consumo()
    conta_pronta("lia@exemplo.com")
    cliente = cliente_novo()
    cliente.post("/api/auth/entrar",
                 json={"email": "lia@exemplo.com", "senha": "abc12345"})
    for i in range(15):
        r = cliente.post("/api/jobs", files={
            "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
        assert r.status_code == 200, (i, r.status_code)
    r = cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    assert r.status_code == 429, r.status_code
    print("OK: logado confirmado envia 15 e é barrado no décimo sexto")


def test_conta_sem_confirmar_fica_com_cota_de_visitante():
    limpar_consumo()
    auth.criar_conta("mar@exemplo.com", "abc12345", "127.0.0.1")
    cliente = cliente_novo()
    cliente.post("/api/auth/entrar",
                 json={"email": "mar@exemplo.com", "senha": "abc12345"})
    for i in range(5):
        r = cliente.post("/api/jobs", files={
            "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
        assert r.status_code == 200, (i, r.status_code)
    r = cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    assert r.status_code == 429, r.status_code

    # E passa à cota cheia depois de confirmar.
    auth.confirmar_conta(auth.por_email("mar@exemplo.com")["id"])
    r = cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    assert r.status_code == 200, r.status_code
    print("OK: sem confirmar é cota de visitante; confirmar destrava a cheia")


def test_conta_sem_confirmar_nao_devolve_vagas_ao_visitante_esgotado():
    """Cadastrar-se sem confirmar não pode zerar o balde do visitante.

    O furo: `resolver` devolvia um balde `usuario:<id>` novo e privado a quem
    ainda não confirmou o endereço. Quem esgotasse a cota de visitante criava
    uma conta com um endereço descartável, entrava, e voltava com cinco
    arquivos — sem abrir caixa de entrada nenhuma. Laço de custo zero, e o
    reinício barato que os três baldes existem para impedir. Os *números* já
    estavam certos (`quotas.limites` já dá cota de visitante a quem não
    confirmou); o que estava errado era o **balde**.
    """
    limpar_consumo()
    cliente = cliente_novo()
    for i in range(5):
        r = cliente.post("/api/jobs", files=um_pdf())
        assert r.status_code == 200, (i, r.status_code)
    r = cliente.post("/api/jobs", files=um_pdf())
    assert r.status_code == 429, r.status_code

    # Mesmo navegador, mesmo IP: cadastra e entra, sem confirmar nada.
    auth.criar_conta("ola@exemplo.com", "abc12345", "127.0.0.1")
    r = cliente.post("/api/auth/entrar",
                     json={"email": "ola@exemplo.com", "senha": "abc12345"})
    assert r.status_code == 200, r.text

    r = cliente.post("/api/jobs", files=um_pdf())
    assert r.status_code == 429, (
        f"conta sem confirmar devolveu vaga ao visitante esgotado ({r.status_code})"
        ": endereço descartável viraria cota nova de graça")

    # É a confirmação do endereço que compra o balde próprio.
    auth.confirmar_conta(auth.por_email("ola@exemplo.com")["id"])
    r = cliente.post("/api/jobs", files=um_pdf())
    assert r.status_code == 200, r.status_code
    print("OK: sem confirmar não devolve vagas; confirmar é o que compra o balde")


def test_pdf_de_40_mb_e_recusado_ao_visitante_e_aceito_ao_logado():
    limpar_consumo()
    grande = b"%PDF-1.4\n" + b"0" * (40 * 1024 * 1024)

    visitante = cliente_novo()
    r = visitante.post("/api/jobs", files={
        "arquivo": ("g.pdf", grande, "application/pdf")})
    assert r.status_code == 413, r.status_code
    assert r.json()["teto_bytes"] == 10 * 1024 * 1024, r.json()

    conta_pronta("nel@exemplo.com")
    logado = cliente_novo()
    logado.post("/api/auth/entrar",
                json={"email": "nel@exemplo.com", "senha": "abc12345"})
    r = logado.post("/api/jobs", files={
        "arquivo": ("g.pdf", grande, "application/pdf")})
    # Passa do teto de tamanho e morre no `fitz` — que é 400, não 413.
    assert r.status_code == 400, r.status_code
    print("OK: 40 MB é recusado ao visitante por tamanho e aceito ao logado")


if __name__ == "__main__":
    test_entrar_e_sair()
    test_email_inexistente_e_senha_errada_respondem_igual()
    test_o_cookie_de_sessao_e_httponly_e_samesite()
    test_cookie_de_sessao_leva_secure_so_em_https()
    test_cookie_de_visitante_leva_secure_so_em_https()
    test_sessao_forjada_e_vencida_nao_valem()
    test_sessao_emitida_no_futuro_nao_vale()
    test_sessao_de_conta_apagada_nao_vale()
    test_entrar_gasta_o_mesmo_scrypt_nos_dois_jeitos_de_recusar()
    test_entrar_reescreve_hash_de_parametros_fracos()
    test_trocar_o_segredo_invalida_as_sessoes()
    test_logado_confirmado_envia_mais_que_visitante()
    test_conta_sem_confirmar_fica_com_cota_de_visitante()
    test_conta_sem_confirmar_nao_devolve_vagas_ao_visitante_esgotado()
    test_pdf_de_40_mb_e_recusado_ao_visitante_e_aceito_ao_logado()
    print("Todos os testes de sessão passaram.")
