"""Cadastro, senha e confirmação de endereço."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from web.api import auth, db, enviador
from web.api.main import app

cliente = TestClient(app)


def emails_novos(desde: float) -> list[str]:
    saida = []
    for p in enviador.pasta_de_emails().iterdir():
        if p.is_file() and p.stat().st_mtime >= desde:
            saida.append(p.read_text(encoding="utf-8"))
    return saida


def test_a_senha_nunca_aparece_em_texto():
    guardado = auth.hash_senha("umaSenhaBoa123")
    assert "umaSenhaBoa123" not in guardado
    assert guardado.startswith("scrypt$"), guardado
    # Os parâmetros vão junto: endurecer os custos depois não invalida senha
    # nenhuma.
    assert len(guardado.split("$")) == 6, guardado
    assert auth.conferir_senha("umaSenhaBoa123", guardado)
    assert not auth.conferir_senha("outra", guardado)
    # Dois hashes da mesma senha diferem: o sal é por senha.
    assert auth.hash_senha("umaSenhaBoa123") != guardado
    print("OK: a senha vira scrypt com sal e parâmetros gravados")


def test_hash_de_parametros_antigos_e_reconhecido_e_marcado():
    fraco = auth.hash_senha("abc12345", n=2 ** 12)
    assert auth.conferir_senha("abc12345", fraco), "tem que continuar entrando"
    assert auth.precisa_reescrever(fraco), "e ser marcado para reescrita"
    assert not auth.precisa_reescrever(auth.hash_senha("abc12345"))
    print("OK: hash de parâmetros antigos entra e é marcado para reescrita")


def test_cadastro_cria_a_conta_e_manda_o_link():
    marco = time.time()
    r = cliente.post("/api/auth/registro",
                     json={"email": "Ana@Exemplo.COM", "senha": "abc12345"})
    assert r.status_code == 200, r.text

    linha = auth.por_email("ana@exemplo.com")
    assert linha is not None, "o e-mail é guardado em minúsculas"
    assert linha["confirmado_em"] is None
    assert "abc12345" not in linha["senha"]

    corpos = emails_novos(marco)
    assert len(corpos) == 1, corpos
    assert "/api/auth/confirmar/" in corpos[0], corpos[0]
    print("OK: o cadastro cria a conta e manda o link de confirmação")


def test_cadastro_com_email_existente_responde_igual_e_avisa_o_dono():
    primeiro = cliente.post("/api/auth/registro",
                            json={"email": "bia@exemplo.com", "senha": "abc12345"})
    marco = time.time()
    segundo = cliente.post("/api/auth/registro",
                           json={"email": "bia@exemplo.com", "senha": "outra999"})
    assert primeiro.status_code == segundo.status_code == 200
    assert primeiro.json() == segundo.json(), \
        "resposta diferente transformaria o cadastro numa sonda de quem tem conta"

    corpos = emails_novos(marco)
    assert len(corpos) == 1
    assert "/api/auth/confirmar/" not in corpos[0], \
        "quem já tem conta recebe aviso, não link de confirmação"
    assert "alguém" in corpos[0].lower() or "alguem" in corpos[0].lower()

    # E a senha da conta existente não pode ter sido trocada.
    linha = auth.por_email("bia@exemplo.com")
    assert auth.conferir_senha("abc12345", linha["senha"])
    print("OK: cadastro repetido responde igual e não conta quem tem conta")


def test_confirmar_liga_a_conta_e_o_token_so_serve_uma_vez():
    marco = time.time()
    cliente.post("/api/auth/registro",
                 json={"email": "caio@exemplo.com", "senha": "abc12345"})
    corpo = emails_novos(marco)[0]
    token = corpo.split("/api/auth/confirmar/")[1].split()[0].strip()

    r = cliente.get(f"/api/auth/confirmar/{token}", follow_redirects=False)
    assert r.status_code in (302, 303, 307), r.status_code
    assert auth.por_email("caio@exemplo.com")["confirmado_em"] is not None

    de_novo = cliente.get(f"/api/auth/confirmar/{token}", follow_redirects=False)
    assert de_novo.status_code == 400, de_novo.status_code
    print("OK: confirmar liga a conta, e o token não serve duas vezes")


def test_token_vencido_e_recusado():
    uid = auth.criar_conta("dan@exemplo.com", "abc12345", "ip")
    token = auth.novo_token(uid, "confirmacao", prazo_s=-1)
    r = cliente.get(f"/api/auth/confirmar/{token}", follow_redirects=False)
    assert r.status_code == 400, r.status_code
    assert auth.por_email("dan@exemplo.com")["confirmado_em"] is None
    print("OK: token vencido é recusado")


def test_o_token_vai_ao_banco_como_marca():
    uid = auth.criar_conta("eva@exemplo.com", "abc12345", "ip")
    token = auth.novo_token(uid, "confirmacao", prazo_s=3600)
    con = db.conexao()
    guardados = {l["valor"] for l in con.execute(
        "SELECT valor FROM tokens WHERE usuario = ?", (uid,))}
    assert token not in guardados, \
        "vazamento do banco não pode entregar tokens utilizáveis"
    assert db.marca(token) in guardados
    print("OK: o token vai ao banco como marca, não em claro")


def test_senha_curta_e_email_invalido_sao_recusados():
    r = cliente.post("/api/auth/registro",
                     json={"email": "fim@exemplo.com", "senha": "123"})
    assert r.status_code == 422, r.status_code
    r = cliente.post("/api/auth/registro",
                     json={"email": "nao-e-email", "senha": "abc12345"})
    assert r.status_code == 422, r.status_code
    print("OK: senha curta e e-mail inválido são recusados")


if __name__ == "__main__":
    test_a_senha_nunca_aparece_em_texto()
    test_hash_de_parametros_antigos_e_reconhecido_e_marcado()
    test_cadastro_cria_a_conta_e_manda_o_link()
    test_cadastro_com_email_existente_responde_igual_e_avisa_o_dono()
    test_confirmar_liga_a_conta_e_o_token_so_serve_uma_vez()
    test_token_vencido_e_recusado()
    test_o_token_vai_ao_banco_como_marca()
    test_senha_curta_e_email_invalido_sao_recusados()
    print("Todos os testes de cadastro passaram.")
