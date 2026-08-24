"""Cadastro, senha e confirmação de endereço."""

import ast
import hashlib
import inspect
import os
import secrets
import sys
import tempfile
import textwrap
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

from web.api import auth, db, enviador
from web.api.main import app

cliente = TestClient(app)


def emails_novos(desde: float) -> list[str]:
    saida = []
    for p in enviador.pasta_de_emails().iterdir():
        if p.is_file() and p.stat().st_mtime >= desde:
            saida.append(p.read_text(encoding="utf-8"))
    return saida


def emails_de(marcador: str) -> list[str]:
    """As cartas de um destinatário, pelo **nome do arquivo**.

    Sem depender de `st_mtime`: o nome do arquivo carrega o endereço, e um
    endereço sorteado por teste separa as cartas sem precisar da resolução do
    carimbo de tempo do sistema de arquivos.
    """
    return [p.read_text(encoding="utf-8")
            for p in enviador.pasta_de_emails().iterdir()
            if p.is_file() and marcador in p.name]


def contando_scrypt(fazer) -> int:
    """Roda `fazer` e devolve quantas vezes `hashlib.scrypt` foi chamado.

    Contador, e não cronômetro: um limiar de tempo daria teste intermitente, e
    o que se quer afirmar é exato — os dois caminhos pagam o mesmo número de
    hashes. A trava existe porque a rota roda no pool de threads do FastAPI.
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
    assert primeiro.content == segundo.content, \
        "e byte a byte: até o comprimento do corpo denunciaria a diferença"

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
    # 422 do Pydantic: corpo só com `detail`, e sem `codigo` nenhum.
    assert "codigo" not in r.json(), r.text

    r = cliente.post("/api/auth/registro",
                     json={"email": "nao-e-email", "senha": "abc12345"})
    assert r.status_code == 422, r.status_code
    # O nosso 422 vem com `codigo`, como toda recusa do app: é o que deixa a
    # tela distinguir "e-mail inválido" de uma queixa de validação do Pydantic
    # sem ler texto.
    assert r.json().get("codigo") == "email_invalido", r.text
    print("OK: senha curta e e-mail inválido são recusados, com código")


def test_cadastro_gasta_o_mesmo_scrypt_no_email_novo_e_no_repetido():
    """O oráculo de enumeração pelo relógio, medido por contagem.

    `criar_conta` avalia `hash_senha(senha)` como argumento do `INSERT`: o
    `scrypt` é pago **antes** de o `IntegrityError` disparar, nos dois caminhos.
    É o que iguala os tempos. Um `queimar_tempo()` na rota somaria um segundo
    hash só no caminho do e-mail repetido, e o cronômetro passaria a contar o
    que a resposta idêntica cala.
    """
    endereco = f"jonas-{secrets.token_hex(4)}@exemplo.com"

    def registrar(senha):
        def fazer():
            r = cliente.post("/api/auth/registro",
                             json={"email": endereco, "senha": senha})
            assert r.status_code == 200, r.text
        return contando_scrypt(fazer)

    novo = registrar("abc12345")
    repetido = registrar("outra999")

    assert novo >= 1, "o cadastro novo tem de pagar o hash da senha"
    assert novo == repetido, (
        f"e-mail novo gastou {novo} scrypt e e-mail repetido gastou "
        f"{repetido}: a diferença vira um oráculo de quem tem conta, mesmo "
        "com a resposta idêntica byte a byte")
    print("OK: e-mail novo e e-mail repetido pagam o mesmo número de scrypt")


def test_envios_simultaneos_ao_mesmo_endereco_nao_se_perdem():
    """Oito cartas ao mesmo destinatário no mesmo segundo, oito arquivos.

    O nome sai do segundo corrente mais o endereço, então todos disputam o
    mesmo nome. Conferir com `exists()` antes de gravar é a corrida em pessoa:
    os fios olham juntos, veem vazio juntos, e um apaga o outro — um link de
    confirmação perdido é uma conta que não ativa.
    """
    n = 8
    marcador = f"karina-{secrets.token_hex(4)}"
    endereco = f"{marcador}@exemplo.com"
    portao = threading.Barrier(n)

    def mandar(i):
        portao.wait()
        enviador.enviar(endereco, "Assunto", f"corpo numero {i}")

    fios = [threading.Thread(target=mandar, args=(i,)) for i in range(n)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()

    corpos = emails_de(marcador)
    assert len(corpos) == n, f"{n} envios viraram {len(corpos)} arquivos"
    # E não é o mesmo corpo repetido: cada envio sobreviveu inteiro.
    assert len({c for c in corpos}) == n, corpos
    print("OK: envios simultâneos ao mesmo endereço geram um arquivo cada")


def test_token_de_um_tipo_nao_serve_para_outro_nem_e_queimado():
    """O filtro por `tipo` no `usar_token`.

    Sem ele, o link de confirmação que chega por e-mail serviria de token de
    redefinição de senha — quem interceptasse um e-mail de cadastro trocaria a
    senha da conta. E a tentativa cruzada não pode consumir o token: senão dá
    para queimar o link de confirmação de qualquer um.
    """
    uid = auth.criar_conta("ivo@exemplo.com", "abc12345", "ip")
    token = auth.novo_token(uid, "confirmacao", prazo_s=3600)

    assert auth.usar_token(token, "senha") is None, \
        "token de confirmação não pode valer como token de redefinição"
    assert auth.usar_token(token, "confirmacao") == uid, \
        "a tentativa cruzada não pode ter queimado o token"
    print("OK: token de um tipo não serve para outro, e não é queimado")


def test_conferir_senha_compara_com_compare_digest():
    """O contrato, e não o cronômetro.

    `==` sai no primeiro byte diferente, e o tempo conta quantos bytes já
    estavam certos. Medir isso num teste seria intermitente; ler o fonte é
    determinístico — é o que `tests/test_cli.py` já faz para conferir imports.
    """
    fonte = textwrap.dedent(inspect.getsource(auth.conferir_senha))
    arvore = ast.parse(fonte)

    chamadas = {
        no.func.attr for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)}
    assert "compare_digest" in chamadas, \
        "conferir_senha tem de comparar com hmac.compare_digest"

    iguais = [no for no in ast.walk(arvore) if isinstance(no, ast.Compare)
              and any(isinstance(op, (ast.Eq, ast.NotEq)) for op in no.ops)]
    assert not iguais, (
        "conferir_senha compara com `==`/`!=`: a saída no primeiro byte errado "
        "conta pelo tempo quanto do hash já estava certo")
    print("OK: conferir_senha compara em tempo constante")


def test_email_longo_e_medido_depois_de_normalizado():
    """O comprimento é o do valor que vai ao banco, não o do cru."""
    local = "a" * 240
    limpo = f"{local}@exemplo.com"          # 252 caracteres
    assert len(limpo) == 252, len(limpo)
    assert auth.email_valido(f"  {limpo}  "), \
        "espaços em volta não podem estourar o teto de um endereço que cabe"
    assert not auth.email_valido("b" * 250 + "@exemplo.com")
    print("OK: o teto de comprimento vale sobre o e-mail normalizado")


def test_email_gravado_em_arquivo_e_expurgado_depois_do_prazo():
    """Higiene: o arquivo guarda o token em claro, e não fica para sempre."""
    marcador = f"lia-{secrets.token_hex(4)}"
    enviador.enviar(f"{marcador}@exemplo.com", "Assunto", "corpo")
    assert len(emails_de(marcador)) == 1

    enviador.expurgar()
    assert len(emails_de(marcador)) == 1, "carta nova não pode ser expurgada"

    apagados = enviador.expurgar(agora=time.time() + enviador.PRAZO_S + 1)
    assert any(marcador in nome for nome in apagados), apagados
    assert emails_de(marcador) == []
    print("OK: e-mail gravado em arquivo é expurgado depois do prazo")


if __name__ == "__main__":
    test_a_senha_nunca_aparece_em_texto()
    test_hash_de_parametros_antigos_e_reconhecido_e_marcado()
    test_cadastro_cria_a_conta_e_manda_o_link()
    test_cadastro_com_email_existente_responde_igual_e_avisa_o_dono()
    test_confirmar_liga_a_conta_e_o_token_so_serve_uma_vez()
    test_token_vencido_e_recusado()
    test_o_token_vai_ao_banco_como_marca()
    test_senha_curta_e_email_invalido_sao_recusados()
    test_cadastro_gasta_o_mesmo_scrypt_no_email_novo_e_no_repetido()
    test_envios_simultaneos_ao_mesmo_endereco_nao_se_perdem()
    test_token_de_um_tipo_nao_serve_para_outro_nem_e_queimado()
    test_conferir_senha_compara_com_compare_digest()
    test_email_longo_e_medido_depois_de_normalizado()
    # Por último de propósito: ele apaga a pasta de e-mails inteira ao forçar
    # o relógio para além do prazo.
    test_email_gravado_em_arquivo_e_expurgado_depois_do_prazo()
    print("Todos os testes de cadastro passaram.")
