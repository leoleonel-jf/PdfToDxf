"""A rota de saúde responde pelo que o serviço consegue fazer, não por estar viva."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ_DE_TESTE = tempfile.mkdtemp(prefix="pdftodxf-teste-")
os.environ.setdefault("PDFTODXF_DADOS", RAIZ_DE_TESTE)
os.environ.setdefault("PDFTODXF_BANCO", os.path.join(RAIZ_DE_TESTE, "contas.db"))

from fastapi.testclient import TestClient

from web.api import db
from web.api.main import app

cliente = TestClient(app)


def _com_ambiente(chave: str, valor: str):
    """Troca uma variável e devolve o que ela era, para restaurar depois."""
    antigo = os.environ.get(chave)
    os.environ[chave] = valor
    return antigo


def _restaurar(chave: str, antigo: str | None) -> None:
    if antigo is None:
        os.environ.pop(chave, None)
    else:
        os.environ[chave] = antigo


def test_servico_saudavel_responde_200():
    r = cliente.get("/api/saude")
    assert r.status_code == 200, r.status_code
    assert r.json() == {"ok": True}, r.json()
    print("OK: serviço saudável responde 200")


def test_pasta_de_dados_inutilizavel_responde_503():
    """Um caminho impossível é o disco cheio do teste: portátil, e sem root.

    `raiz()` faz `mkdir(parents=True)`; criar pasta **dentro de um arquivo**
    falha em qualquer sistema operacional, que é o que se quer provocar.
    """
    arquivo = Path(tempfile.mkdtemp(prefix="pdftodxf-teste-")) / "sou-um-arquivo"
    arquivo.write_text("x", encoding="utf-8")
    antigo = _com_ambiente("PDFTODXF_DADOS", str(arquivo / "dentro"))
    try:
        r = cliente.get("/api/saude")
        assert r.status_code == 503, r.status_code
        corpo = r.json()
        assert corpo["ok"] is False, corpo
        assert "dados" in corpo["falhas"], corpo
    finally:
        _restaurar("PDFTODXF_DADOS", antigo)
    print("OK: pasta de dados inutilizável responde 503")


def test_banco_inutilizavel_responde_503():
    arquivo = Path(tempfile.mkdtemp(prefix="pdftodxf-teste-")) / "sou-um-arquivo"
    arquivo.write_text("x", encoding="utf-8")
    antigo = _com_ambiente("PDFTODXF_BANCO", str(arquivo / "dentro" / "contas.db"))
    db.fechar()   # a conexão é por fio e guarda o caminho; sem isto ela reusa o antigo
    try:
        r = cliente.get("/api/saude")
        assert r.status_code == 503, r.status_code
        assert "banco" in r.json()["falhas"], r.json()
    finally:
        _restaurar("PDFTODXF_BANCO", antigo)
        db.fechar()
    print("OK: banco inutilizável responde 503")


def test_a_rota_nao_conta_mais_do_que_precisa():
    """É rota pública: o que ela conta, conta para qualquer um."""
    texto = cliente.get("/api/saude").text
    for proibido in ("/dados", "C:\\", "sqlite", "fastapi", "uvicorn"):
        assert proibido.lower() not in texto.lower(), texto
    print("OK: a resposta não expõe caminho nem versão")


def test_o_arquivo_de_prova_nao_fica_para_tras():
    """A limpeza periódica varre a raiz; lixo nosso não pode se acumular lá."""
    cliente.get("/api/saude")
    assert not (Path(os.environ["PDFTODXF_DADOS"]) / ".saude").exists()
    print("OK: a prova de escrita não deixa arquivo para trás")


if __name__ == "__main__":
    test_servico_saudavel_responde_200()
    test_pasta_de_dados_inutilizavel_responde_503()
    test_banco_inutilizavel_responde_503()
    test_a_rota_nao_conta_mais_do_que_precisa()
    test_o_arquivo_de_prova_nao_fica_para_tras()
    print("Todos os testes da rota de saúde passaram.")
