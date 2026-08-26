"""Quem está pedindo: cookie anônimo, IP com proxies e impressão do navegador."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from web.api import db, identidade


class PedidoFalso:
    """O mínimo de um `Request` que `identidade` lê."""

    def __init__(self, cabecalhos=None, cookies=None, cliente="203.0.113.9"):
        self.headers = {k.lower(): v for k, v in (cabecalhos or {}).items()}
        self.cookies = cookies or {}
        self.client = type("C", (), {"host": cliente})()


def chaves(ident):
    return {b.chave for b in ident.baldes}


def test_visitante_novo_ganha_tres_baldes_e_um_cookie():
    p = PedidoFalso(cabecalhos={"X-Impressao": "b" * 64})
    ident = identidade.resolver(p)
    assert ident.tipo == "visitante"
    assert len(ident.baldes) == 3, ident.baldes
    assert ident.cookie_novo, "visitante sem cookie tem que ganhar um"
    folgas = sorted(b.folga for b in ident.baldes)
    assert folgas[0] == 1 and folgas[1] > 1 and folgas[2] > 1, folgas
    print("OK: visitante novo ganha três baldes e um cookie")


def test_o_mesmo_cookie_da_o_mesmo_balde():
    p = PedidoFalso()
    primeiro = identidade.resolver(p)
    devolta = PedidoFalso(cookies={identidade.COOKIE: primeiro.cookie_novo})
    segundo = identidade.resolver(devolta)
    assert segundo.cookie_novo is None, "cookie válido não é reemitido"
    assert chaves(primeiro) & chaves(segundo), "o balde do cookie tem que casar"
    print("OK: o mesmo cookie devolve o mesmo balde")


def test_cookie_forjado_e_descartado():
    p = PedidoFalso(cookies={identidade.COOKIE: "eu-inventei-isto"})
    ident = identidade.resolver(p)
    assert ident.cookie_novo, "cookie sem assinatura válida vira cookie novo"
    print("OK: cookie forjado é descartado e substituído")


def test_x_forwarded_for_e_ignorado_sem_proxies():
    os.environ["PDFTODXF_PROXIES"] = "0"
    p = PedidoFalso(cabecalhos={"X-Forwarded-For": "1.2.3.4"},
                    cliente="203.0.113.9")
    assert identidade.ip_do_pedido(p) == "203.0.113.9"
    print("OK: X-Forwarded-For forjado é ignorado com PDFTODXF_PROXIES=0")


def test_x_forwarded_for_com_um_proxy():
    os.environ["PDFTODXF_PROXIES"] = "1"
    try:
        p = PedidoFalso(cabecalhos={"X-Forwarded-For": "9.9.9.9, 198.51.100.4"},
                        cliente="127.0.0.1")
        # Com um proxy confiável à frente, o cliente é o último da lista — os
        # anteriores foram escritos por quem quis.
        assert identidade.ip_do_pedido(p) == "198.51.100.4"
        vazio = PedidoFalso(cliente="127.0.0.1")
        assert identidade.ip_do_pedido(vazio) == "127.0.0.1", \
            "sem cabeçalho, sobra o endereço da conexão"
    finally:
        os.environ["PDFTODXF_PROXIES"] = "0"
    print("OK: com um proxy, o IP sai da posição certa")


def test_impressao_malformada_e_ignorada_sem_erro():
    for ruim in ["", "curta", "z" * 64, "A" * 65, "../etc/passwd"]:
        p = PedidoFalso(cabecalhos={"X-Impressao": ruim})
        assert identidade.impressao_do_pedido(p) is None, ruim
        ident = identidade.resolver(p)
        assert len(ident.baldes) == 2, "sem impressão sobram cookie e IP"
    print("OK: impressão malformada é ignorada sem erro e sem bloquear")


def test_logado_tem_um_balde_so():
    p = PedidoFalso(cabecalhos={"X-Impressao": "c" * 64})
    ident = identidade.resolver(p, dono=identidade.Dono(id=7, confirmado=True))
    assert ident.tipo == "logado"
    assert ident.usuario_id == 7 and ident.confirmado is True
    assert len(ident.baldes) == 1 and ident.baldes[0].folga == 1
    assert ident.baldes[0].chave == db.marca("usuario:7")
    print("OK: logado consome um balde só; IP e impressão não entram")


def test_o_primeiro_balde_do_visitante_e_o_do_cookie():
    """A ordem é contrato: `quotas` usa `baldes[0]` como chave de idempotência.

    Se um balde compartilhado (IP ou impressão) viesse primeiro, dois
    visitantes do mesmo escritório dividiriam a idempotência um do outro.
    """
    p = PedidoFalso(cabecalhos={"X-Impressao": "d" * 64}, cliente="203.0.113.9")
    primeiro = identidade.resolver(p)
    outro_ip = PedidoFalso(cabecalhos={"X-Impressao": "d" * 64},
                           cookies={identidade.COOKIE: primeiro.cookie_novo},
                           cliente="198.51.100.7")
    segundo = identidade.resolver(outro_ip)
    assert primeiro.baldes[0].chave == segundo.baldes[0].chave, \
        "o primeiro balde é o do cookie, e ele não muda com o IP"
    assert primeiro.baldes[0].folga == 1, primeiro.baldes[0]
    assert primeiro.baldes[1].chave != segundo.baldes[1].chave, \
        "o segundo é o do IP, e ele muda com o IP"
    print("OK: o primeiro balde do visitante é o do cookie")


def test_conta_sem_confirmar_continua_identificada():
    p = PedidoFalso()
    ident = identidade.resolver(p, dono=identidade.Dono(id=7, confirmado=False))
    assert ident.tipo == "logado" and ident.confirmado is False
    print("OK: conta sem confirmar continua identificada, mas não confirmada")


if __name__ == "__main__":
    test_visitante_novo_ganha_tres_baldes_e_um_cookie()
    test_o_mesmo_cookie_da_o_mesmo_balde()
    test_cookie_forjado_e_descartado()
    test_x_forwarded_for_e_ignorado_sem_proxies()
    test_x_forwarded_for_com_um_proxy()
    test_impressao_malformada_e_ignorada_sem_erro()
    test_logado_tem_um_balde_so()
    test_o_primeiro_balde_do_visitante_e_o_do_cookie()
    test_conta_sem_confirmar_continua_identificada()
    print("Todos os testes de identidade passaram.")
