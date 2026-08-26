"""O registro .md de uma página: conteúdo, nome de arquivo e expurgo."""

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")

from pdftodxf.geometry import Segment, TextItem, limites
from pdftodxf.optimize import classify
from web.api import registros


class ResultadoFalso:
    """Um `ExtractionResult` de mentira, com o mínimo que `montar` lê."""

    def __init__(self, entidades, largura=841.89, altura=595.28):
        self.entities = entidades
        self.page_width = largura
        self.page_height = altura
        self.layers = {e.layer for e in entidades}

    def counts(self):
        saida = {}
        for e in self.entities:
            nome = type(e).__name__
            saida[nome] = saida.get(nome, 0) + 1
        return saida


def cenario():
    entidades = [
        Segment(p1=(10.0, 20.0), p2=(110.0, 20.0), layer="PAREDE"),
        Segment(p1=(110.0, 20.0), p2=(110.0, 220.0), layer="PAREDE"),
        TextItem(text="SALA 01", position=(50.0, 60.0), height=3.5,
                 rotation=0.0, layer="TEXTO"),
        TextItem(text="6,06", position=(70.0, 30.0), height=2.5,
                 rotation=90.0, layer="TEXTO"),
    ]
    resultado = ResultadoFalso(entidades)
    return resultado, classify(entidades)


DADOS = {
    "ip": "192.168.0.7",
    "conta": "",
    "nome": "LAY-1031.26.00_REV 00.pdf",
    "pagina": 1,
    "job_id": "a" * 32,
    "tamanho_pdf": 750_000,
    "segundos": 0.42,
    "quando": 1_755_000_000.0,
}


def test_limites_do_desenho():
    entidades = cenario()[0].entities
    assert limites([]) is None, "sem entidade não há limites"
    assert limites(entidades) == (10.0, 20.0, 110.0, 220.0)
    print("OK: os limites do desenho saem certos")


def test_o_md_traz_os_textos_e_os_numeros():
    resultado, attrs = cenario()
    texto = registros.montar(DADOS, resultado, attrs)

    assert texto.startswith("---\n"), "tem que abrir com frontmatter"
    assert 'ip: "192.168.0.7"' in texto
    assert 'nome: "LAY-1031.26.00_REV 00.pdf"' in texto
    assert "pagina: 1" in texto
    assert "tamanho_pdf: 750000" in texto
    assert "segundos: 0.42" in texto

    # Todo texto da planta tem que estar no registro: é para isso que ele existe.
    assert "SALA 01" in texto
    assert "6,06" in texto

    assert "PAREDE" in texto and "TEXTO" in texto
    assert "Segment" in texto and "TextItem" in texto
    # Folha em pt e em mm, e os limites do desenho.
    assert "841.9" in texto or "841,9" in texto
    assert "297" in texto, "595,28 pt = 210 mm e 841,89 pt = 297 mm"
    print("OK: o .md traz os textos, os layers e as dimensões")


def test_nome_com_travessia_e_higienizado():
    ruim = {**DADOS, "nome": "../../etc/passwd.pdf", "ip": "2001:db8::1"}
    nome = registros.nome_do_arquivo(ruim["ip"], ruim["nome"], 1, DADOS["quando"])
    assert "/" not in nome and "\\" not in nome, nome
    assert ".." not in nome.replace("_", ""), nome
    assert nome.endswith(".md")
    assert ":" not in nome, "dois-pontos não pode: o Windows recusa no nome"
    print("OK: nome com travessia é higienizado")


def test_gravar_nao_escapa_da_pasta():
    resultado, attrs = cenario()
    caminho = registros.gravar({**DADOS, "nome": "../../fora.pdf"},
                               resultado, attrs)
    assert caminho.resolve().is_relative_to(registros.pasta().resolve())
    assert caminho.exists()
    print("OK: o arquivo gravado não escapa da pasta de registros")


def test_dois_iguais_no_mesmo_segundo_nao_se_sobrescrevem():
    resultado, attrs = cenario()
    a = registros.gravar(DADOS, resultado, attrs)
    b = registros.gravar(DADOS, resultado, attrs)
    assert a != b, "o segundo tinha que ganhar sufixo"
    assert a.exists() and b.exists()
    print("OK: dois registros do mesmo segundo não se sobrescrevem")


def test_expurgo_de_um_ano():
    resultado, attrs = cenario()
    novo = registros.gravar(DADOS, resultado, attrs)
    velho = registros.pasta() / "velho.md"
    velho.write_text("registro antigo", encoding="utf-8")
    antigo = time.time() - registros.PRAZO_S - 60
    os.utime(velho, (antigo, antigo))

    apagados = registros.expurgar()
    assert "velho.md" in apagados, apagados
    assert not velho.exists()
    assert novo.exists(), "o registro novo tem que ficar"
    print("OK: o expurgo apaga o que passou de 1 ano e poupa o resto")


def test_expurgo_sobrevive_a_arquivo_trancado():
    """Um `PermissionError` no meio da varredura não pode abortar o expurgo
    dos demais: é o caso de um antivírus ou backup do Windows segurando um
    arquivo por um instante."""
    resultado, attrs = cenario()
    novo = registros.gravar(DADOS, resultado, attrs)

    antigo = time.time() - registros.PRAZO_S - 60

    velho = registros.pasta() / "velho.md"
    velho.write_text("registro antigo", encoding="utf-8")
    os.utime(velho, (antigo, antigo))

    trancado = registros.pasta() / "trancado.md"
    trancado.write_text("registro trancado", encoding="utf-8")
    os.utime(trancado, (antigo, antigo))

    stat_original = Path.stat

    def stat_as_vezes_falha(self, *args, **kwargs):
        if self.name == "trancado.md":
            raise PermissionError("arquivo em uso por outro processo")
        return stat_original(self, *args, **kwargs)

    with mock.patch.object(Path, "stat", stat_as_vezes_falha):
        apagados = registros.expurgar()

    assert "velho.md" in apagados, apagados
    assert "trancado.md" not in apagados, apagados
    assert not velho.exists(), "o velho, que não travou, tem que sumir"
    assert trancado.exists(), "o trancado sobrevive a esta passagem"
    assert novo.exists()
    print("OK: um arquivo trancado nao aborta o expurgo dos outros")


if __name__ == "__main__":
    test_limites_do_desenho()
    test_o_md_traz_os_textos_e_os_numeros()
    test_nome_com_travessia_e_higienizado()
    test_gravar_nao_escapa_da_pasta()
    test_dois_iguais_no_mesmo_segundo_nao_se_sobrescrevem()
    test_expurgo_de_um_ano()
    test_expurgo_sobrevive_a_arquivo_trancado()
    print("Todos os testes de registros passaram.")
