"""Redefinição de senha e o teto de contas por IP por dia."""

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
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from web.api import auth, db, enviador, main
from web.api.main import app

cliente = TestClient(app)


def esperar_as_cartas() -> None:
    """Espera as threads de envio de `pedir_senha` terminarem.

    A carta sai fora do caminho do pedido — é isso que tira o transporte de
    e-mail do relógio da resposta —, então o `POST` volta antes de o arquivo
    existir. Esperar **pela thread**, e não dormir um valor arbitrário: dormir
    é teste intermitente disfarçado de teste.
    """
    for fio in threading.enumerate():
        if fio.name == main.NOME_DA_THREAD_DE_CARTA:
            fio.join(timeout=10)
            assert not fio.is_alive(), "a thread de envio não terminou"


def emails_novos(desde: float) -> list[str]:
    return [p.read_text(encoding="utf-8")
            for p in enviador.pasta_de_emails().iterdir()
            if p.is_file() and p.stat().st_mtime >= desde]


def emails_de(marcador: str) -> list[str]:
    """As cartas de um destinatário, pelo **nome do arquivo**.

    Sem depender de `st_mtime`: o nome do arquivo carrega o endereço, e um
    endereço por teste separa as cartas sem depender da resolução do carimbo
    de tempo do sistema de arquivos.
    """
    return [p.read_text(encoding="utf-8")
            for p in enviador.pasta_de_emails().iterdir()
            if p.is_file() and marcador in p.name]


def token_do_corpo(corpo: str) -> str:
    """O token do link `.../?senha=<token>` que a carta carrega."""
    return corpo.split("?senha=")[1].split()[0].strip()


class PedidoComCookie:
    """O mínimo de um `Request` que `auth` lê da sessão."""

    def __init__(self, valor):
        self.cookies = {auth.COOKIE_SESSAO: valor}
        self.headers = {}
        self.client = type("C", (), {"host": "127.0.0.1"})()


def entrar(email: str, senha: str) -> str:
    """Entra num cliente novo e devolve o cookie de sessão emitido."""
    c = TestClient(app)
    r = c.post("/api/auth/entrar", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    valor = c.cookies.get(auth.COOKIE_SESSAO)
    assert valor, "entrar tinha de ter gravado o cookie de sessão"
    return valor


def test_pedir_redefinicao_manda_o_link():
    auth.criar_conta("ola@exemplo.com", "senhaVelha1", "127.0.0.1")
    marco = time.time()
    r = cliente.post("/api/auth/senha", json={"email": "ola@exemplo.com"})
    assert r.status_code == 200, r.text
    esperar_as_cartas()
    corpos = emails_novos(marco)
    # O link é o da **tela** (`/?senha=<token>`), e não o da API: a rota que
    # troca a senha é um POST, e um GET que já trocasse seria disparado por
    # qualquer pré-carregador de link do cliente de e-mail.
    assert len(corpos) == 1 and "?senha=" in corpos[0], corpos
    assert "/api/auth/senha/" not in corpos[0], corpos[0]
    print("OK: pedir redefinição manda o link")


def test_email_inexistente_responde_igual_e_nao_manda_nada():
    marco = time.time()
    a = cliente.post("/api/auth/senha", json={"email": "ola@exemplo.com"})
    b = cliente.post("/api/auth/senha", json={"email": "ninguem@exemplo.com"})
    esperar_as_cartas()
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert a.content == b.content, \
        "e byte a byte: até o comprimento do corpo denunciaria a diferença"
    # E os cabeçalhos junto: um `content-length` diferente contaria o mesmo que
    # o corpo, e um `set-cookie` só num dos ramos contaria tudo.
    assert dict(a.headers) == dict(b.headers), (dict(a.headers), dict(b.headers))
    assert "set-cookie" not in a.headers and "set-cookie" not in b.headers, \
        "pedir redefinição não emite sessão nenhuma, nem no ramo que existe"
    # O inexistente não gera e-mail nenhum, mas responde igual.
    assert len(emails_novos(marco)) == 1
    print("OK: e-mail inexistente responde igual e não manda nada")


def contando_scrypt(fazer) -> int:
    """Roda `fazer` e devolve quantas vezes `hashlib.scrypt` foi chamado.

    Contador, e não cronômetro: um limiar de tempo daria teste intermitente. A
    trava existe porque a rota roda no pool de threads do FastAPI. Mesmo desenho
    de `test_auth_cadastro` e `test_auth_sessao`, duplicado de propósito —
    importar aqueles módulos reapontaria `PDFTODXF_BANCO` para o banco deles.
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


def test_pedir_senha_gasta_o_mesmo_scrypt_nos_dois_ramos():
    """Os dois ramos gastam o **mesmo** número de `scrypt` — que é zero.

    A versão anterior deste teste exigia `>= 1` no ramo do inexistente, para
    prender um `queimar_tempo` que a revisão da tarefa 9 mediu e arrancou: ele
    não igualava os ramos, deslocava (10,0x com SMTP em 0 ms, faixas disjuntas,
    100% de acurácia de limiar). O que iguala é o piso de resposta constante de
    `main.PISO_DE_SENHA_S`, e com ele nenhum dos dois ramos hasheia coisa
    nenhuma. **Se alguém voltar a somar um hash a um dos lados, este teste cai.**

    Contador, e não cronômetro: um limiar de tempo daria teste intermitente.
    """
    auth.criar_conta("par@exemplo.com", "senhaVelha1", "127.0.0.1")

    def pedindo(email):
        def fazer():
            r = cliente.post("/api/auth/senha", json={"email": email})
            assert r.status_code == 200, r.text
            esperar_as_cartas()
        return fazer

    existe = contando_scrypt(pedindo("par@exemplo.com"))
    nao_existe = contando_scrypt(pedindo("ninguem-mesmo@exemplo.com"))
    assert existe == nao_existe == 0, (
        f"os ramos de pedir redefinição gastaram {existe} e {nao_existe} "
        "scrypt: assimetria de hash é oráculo de enumeração pelo relógio")
    print("OK: pedir senha gasta o mesmo scrypt nos dois ramos (zero)")


def test_a_carta_sai_mesmo_com_o_envio_em_thread():
    """Tirar o envio do caminho do pedido não pode tirá-lo do mundo."""
    auth.criar_conta("thr@exemplo.com", "senhaVelha1", "127.0.0.1")
    r = cliente.post("/api/auth/senha", json={"email": "thr@exemplo.com"})
    assert r.status_code == 200, r.text
    esperar_as_cartas()
    corpos = emails_de("thr@exemplo.com")
    assert len(corpos) == 1 and "?senha=" in corpos[0], corpos
    print("OK: a carta sai mesmo com o envio em thread")


def test_concluir_a_redefinicao_troca_a_senha():
    auth.criar_conta("pat@exemplo.com", "senhaVelha1", "127.0.0.1")
    cliente.post("/api/auth/senha", json={"email": "pat@exemplo.com"})
    esperar_as_cartas()
    corpo = emails_de("pat@exemplo.com")[0]
    token = token_do_corpo(corpo)

    r = cliente.post(f"/api/auth/senha/{token}", json={"senha": "senhaNova99"})
    assert r.status_code == 200, r.text

    linha = auth.por_email("pat@exemplo.com")
    assert auth.conferir_senha("senhaNova99", linha["senha"])
    assert not auth.conferir_senha("senhaVelha1", linha["senha"])

    de_novo = cliente.post(f"/api/auth/senha/{token}",
                           json={"senha": "outraAinda1"})
    assert de_novo.status_code == 400, "o token não serve duas vezes"
    print("OK: concluir a redefinição troca a senha, e o token só vale uma vez")


def test_token_de_confirmacao_nao_serve_para_redefinir_senha():
    uid = auth.criar_conta("qua@exemplo.com", "senhaVelha1", "127.0.0.1")
    token = auth.novo_token(uid, "confirmacao", auth.PRAZO_CONFIRMACAO_S)
    r = cliente.post(f"/api/auth/senha/{token}", json={"senha": "senhaNova99"})
    assert r.status_code == 400, r.status_code
    assert auth.conferir_senha("senhaVelha1", auth.por_email("qua@exemplo.com")["senha"])
    print("OK: token de um tipo não serve para o outro")


def test_token_de_senha_vencido_e_recusado():
    """O filtro de `expira_em` em `usar_token`, preso por este caminho.

    A bateria de senha inteira sobrevivia à mutação "`usar_token` sem o filtro
    de `expira_em`" — quem a matava era `test_auth_cadastro`, por um token de
    outro tipo. Um prazo de redefinição que não vence é um link de troca de
    senha vivo para sempre na caixa de entrada.
    """
    uid = auth.criar_conta("ven@exemplo.com", "senhaVelha1", "127.0.0.1")
    antes = auth.por_email("ven@exemplo.com")["senha"]
    token = auth.novo_token(uid, "senha", -10)   # já nasceu vencido

    r = cliente.post(f"/api/auth/senha/{token}", json={"senha": "senhaNova99"})
    assert r.status_code == 400, r.status_code
    assert r.json()["codigo"] == "token_invalido", r.json()
    assert auth.por_email("ven@exemplo.com")["senha"] == antes, \
        "o hash no banco mudou com um token vencido"
    print("OK: token de redefinição vencido é recusado e a senha não muda")


def test_concluir_invalida_os_outros_links_pendentes():
    """Usar um link queima os outros do mesmo usuário.

    Os tokens saem de `novo_token` direto, e não das cartas: a rota só faz isso
    mesmo, e ler três arquivos do mesmo destinatário dependeria da ordem em que
    o sistema de arquivos os lista.
    """
    uid = auth.criar_conta("tres@exemplo.com", "senhaVelha1", "127.0.0.1")
    primeiro = auth.novo_token(uid, "senha", auth.PRAZO_SENHA_S)
    segundo = auth.novo_token(uid, "senha", auth.PRAZO_SENHA_S)
    terceiro = auth.novo_token(uid, "senha", auth.PRAZO_SENHA_S)

    r = cliente.post(f"/api/auth/senha/{terceiro}", json={"senha": "senhaNova99"})
    assert r.status_code == 200, r.text

    for velho in (primeiro, segundo):
        r = cliente.post(f"/api/auth/senha/{velho}",
                         json={"senha": "invadida123"})
        assert r.status_code == 400, (velho, r.status_code)
    assert auth.conferir_senha("senhaNova99",
                               auth.por_email("tres@exemplo.com")["senha"]), \
        "um link pendente de antes ainda trocou a senha"

    # E não queima os de outro usuário.
    outro = auth.criar_conta("solo@exemplo.com", "senhaVelha1", "127.0.0.1")
    dele = auth.novo_token(outro, "senha", auth.PRAZO_SENHA_S)
    meu = auth.novo_token(uid, "senha", auth.PRAZO_SENHA_S)
    r = cliente.post(f"/api/auth/senha/{meu}", json={"senha": "maisUma123"})
    assert r.status_code == 200, r.text
    r = cliente.post(f"/api/auth/senha/{dele}", json={"senha": "aDeleAgora1"})
    assert r.status_code == 200, "o link do outro usuário foi queimado junto"
    print("OK: concluir invalida os outros links pendentes, só os do dono")


def test_redefinir_derruba_as_sessoes_abertas():
    """A redefinição serve para expulsar quem entrou — senão não serve a nada.

    A sessão é um cookie assinado de 30 dias, sem tabela nenhuma. Sem a
    impressão da senha dentro dela, quem redefine a senha porque desconfia que
    alguém entrou na conta **deixa esse alguém logado por até 30 dias**.
    """
    uid = auth.criar_conta("sam@exemplo.com", "senhaVelha1", "127.0.0.1")
    auth.confirmar_conta(uid)

    invasor = entrar("sam@exemplo.com", "senhaVelha1")
    assert auth.dono_da_sessao(PedidoComCookie(invasor)) == (uid, True)

    r = cliente.post("/api/auth/senha", json={"email": "sam@exemplo.com"})
    assert r.status_code == 200, r.text
    esperar_as_cartas()
    token = token_do_corpo(emails_de("sam@exemplo.com")[0])
    r = cliente.post(f"/api/auth/senha/{token}", json={"senha": "senhaNova99"})
    assert r.status_code == 200, r.text

    assert auth.dono_da_sessao(PedidoComCookie(invasor)) is None, \
        ("a sessão aberta antes da redefinição continuou valendo: quem invadiu "
         "fica dentro da conta por até 30 dias")

    # E a sessão emitida **depois** vale: o dono entra de novo com a senha nova.
    do_dono = entrar("sam@exemplo.com", "senhaNova99")
    assert auth.dono_da_sessao(PedidoComCookie(do_dono)) == (uid, True)
    print("OK: redefinir a senha derruba as sessões abertas, e a nova vale")


def test_login_que_reescreve_o_hash_devolve_sessao_que_funciona():
    """A ordem em `entrar`: reescrever o hash **antes** de emitir a sessão.

    A reescrita de hash de parâmetros antigos (`precisa_reescrever` →
    `reescrever_senha`) também muda o hash guardado, e portanto a impressão.
    Como ela acontece antes da emissão, no mesmo pedido, a sessão nova sai com
    a impressão certa. Inverter as duas linhas devolveria ao usuário um cookie
    natimorto — ele entraria com sucesso e o pedido seguinte já sairia como
    visitante.
    """
    uid = auth.criar_conta("tom@exemplo.com", "senhaVelha1", "127.0.0.1")
    auth.confirmar_conta(uid)

    fraco = auth.hash_senha("senhaVelha1", n=4096)
    con = db.conexao()
    con.execute("UPDATE usuarios SET senha = ? WHERE id = ?", (fraco, uid))
    con.commit()
    assert auth.precisa_reescrever(auth.por_email("tom@exemplo.com")["senha"])

    valor = entrar("tom@exemplo.com", "senhaVelha1")
    assert not auth.precisa_reescrever(auth.por_email("tom@exemplo.com")["senha"]), \
        "o hash fraco tinha de ter sido reescrito"
    assert auth.dono_da_sessao(PedidoComCookie(valor)) == (uid, True), \
        ("a sessão saiu com a impressão do hash antigo: a reescrita tem de "
         "acontecer antes de `_gravar_sessao` em `entrar`")
    print("OK: o login que reescreve o hash devolve uma sessão que funciona")


def test_trocar_a_senha_de_um_nao_derruba_a_sessao_de_outro():
    """A impressão é da senha **daquele** usuário, e não de um estado global."""
    a = auth.criar_conta("ana@exemplo.com", "senhaVelha1", "127.0.0.1")
    b = auth.criar_conta("bob@exemplo.com", "senhaVelha1", "127.0.0.1")
    auth.confirmar_conta(a)
    auth.confirmar_conta(b)

    de_a = entrar("ana@exemplo.com", "senhaVelha1")
    de_b = entrar("bob@exemplo.com", "senhaVelha1")

    auth.reescrever_senha(b, "senhaNova99")

    assert auth.dono_da_sessao(PedidoComCookie(de_b)) is None
    assert auth.dono_da_sessao(PedidoComCookie(de_a)) == (a, True), \
        "trocar a senha de um usuário não pode derrubar a sessão de outro"
    print("OK: trocar a senha de um não derruba a sessão de outro")


def test_teto_de_contas_por_ip_por_dia():
    con = db.conexao()
    con.execute("DELETE FROM usuarios")
    con.commit()
    for i in range(5):
        r = cliente.post("/api/auth/registro",
                         json={"email": f"serie{i}@exemplo.com",
                               "senha": "abc12345"})
        assert r.status_code == 200, (i, r.text)
    r = cliente.post("/api/auth/registro",
                     json={"email": "serie5@exemplo.com", "senha": "abc12345"})
    assert r.status_code == 429, r.status_code
    assert r.json()["codigo"] == "contas_demais", r.json()
    assert auth.por_email("serie5@exemplo.com") is None, "não pode ter criado"
    print("OK: o teto de contas por IP barra a sexta do dia")


def test_teto_de_contas_por_ip_com_lixo_cai_no_padrao():
    """Negativo é lixo, e lixo cai no padrão — nunca em "sem limite".

    `max(0, int(...))` grampeava `-1` em `0`, e `0` aqui significa sem limite:
    a convenção de "sem limite" de outros sistemas — o lixo mais provável de
    aparecer nesta chave — desligava o teto do cadastro inteiro em silêncio.
    Mesmo tratamento de `quotas._chave`.
    """
    antes = os.environ.get("PDFTODXF_CONTAS_POR_IP_DIA")
    try:
        for lixo in ("-1", "-3", "abc", "", "  "):
            os.environ["PDFTODXF_CONTAS_POR_IP_DIA"] = lixo
            assert auth.teto_de_contas_por_ip() == auth.CONTAS_POR_IP_DIA, lixo
        # E o que não é lixo continua valendo, `0` inclusive: aqui ele é a
        # forma **deliberada** de dizer "sem limite".
        os.environ["PDFTODXF_CONTAS_POR_IP_DIA"] = "0"
        assert auth.teto_de_contas_por_ip() == 0
        os.environ["PDFTODXF_CONTAS_POR_IP_DIA"] = "9"
        assert auth.teto_de_contas_por_ip() == 9
        os.environ.pop("PDFTODXF_CONTAS_POR_IP_DIA")
        assert auth.teto_de_contas_por_ip() == auth.CONTAS_POR_IP_DIA
    finally:
        os.environ.pop("PDFTODXF_CONTAS_POR_IP_DIA", None)
        if antes is not None:
            os.environ["PDFTODXF_CONTAS_POR_IP_DIA"] = antes
    print("OK: teto de contas por IP com valor negativo cai no padrão")


def test_conta_de_ontem_nao_conta_para_hoje():
    con = db.conexao()
    con.execute("DELETE FROM usuarios")
    con.commit()
    ontem = time.time() - 25 * 60 * 60
    for i in range(5):
        con.execute("INSERT INTO usuarios (email, senha, criado_em, criado_de) "
                    "VALUES (?, ?, ?, ?)",
                    (f"velho{i}@exemplo.com", "x", ontem, db.marca("testclient")))
    con.commit()
    assert auth.contas_do_ip_hoje("testclient") == 0
    print("OK: conta de mais de 24 h não conta para o teto de hoje")


if __name__ == "__main__":
    test_pedir_redefinicao_manda_o_link()
    test_email_inexistente_responde_igual_e_nao_manda_nada()
    test_pedir_senha_gasta_o_mesmo_scrypt_nos_dois_ramos()
    test_a_carta_sai_mesmo_com_o_envio_em_thread()
    test_concluir_a_redefinicao_troca_a_senha()
    test_token_de_confirmacao_nao_serve_para_redefinir_senha()
    test_token_de_senha_vencido_e_recusado()
    test_concluir_invalida_os_outros_links_pendentes()
    test_redefinir_derruba_as_sessoes_abertas()
    test_login_que_reescreve_o_hash_devolve_sessao_que_funciona()
    test_trocar_a_senha_de_um_nao_derruba_a_sessao_de_outro()
    # Os do teto por último: eles esvaziam a tabela `usuarios`.
    test_teto_de_contas_por_ip_por_dia()
    test_teto_de_contas_por_ip_com_lixo_cai_no_padrao()
    test_conta_de_ontem_nao_conta_para_hoje()
    print("Todos os testes de redefinição de senha passaram.")
