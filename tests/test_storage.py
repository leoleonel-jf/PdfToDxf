"""Expiração por prazo e cota de disco."""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

from web.api import limits, storage

AGORA = 1_800_000_000.0   # instante fixo, para o teste não depender do relógio


def trabalho(idade_segundos: float, bytes_de_lixo: int = 1024) -> str:
    job_id = storage.novo_id()
    storage.criar_trabalho(job_id, "planta.pdf", 1, bytes_de_lixo,
                           agora=AGORA - idade_segundos)
    with open(storage.pasta(job_id) / "lixo.bin", "wb") as f:
        f.write(b"0" * bytes_de_lixo)
    return job_id


def limpar_tudo():
    for p in storage.raiz().iterdir():
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


def test_expira_por_prazo():
    limpar_tudo()
    velho = trabalho(limits.PRAZO_SEGUNDOS + 60)
    novo = trabalho(60)
    relato = storage.limpar(agora=AGORA)
    assert velho in relato["expirados"], relato
    assert novo not in relato["expirados"], relato
    assert not storage.pasta(velho).exists()
    assert storage.pasta(novo).exists()
    print("OK: trabalho vencido é apagado, o recente fica")


def test_cota_apaga_o_mais_antigo_primeiro():
    limpar_tudo()
    original = limits.COTA_DISCO_BYTES
    limits.COTA_DISCO_BYTES = 5000
    try:
        antigo = trabalho(300, bytes_de_lixo=3000)
        recente = trabalho(60, bytes_de_lixo=3000)
        relato = storage.limpar(agora=AGORA)
        assert antigo in relato["por_cota"], relato
        assert recente not in relato["por_cota"], relato
        assert not storage.pasta(antigo).exists()
        assert storage.pasta(recente).exists()
    finally:
        limits.COTA_DISCO_BYTES = original
    print("OK: a cota apaga do mais antigo para o mais novo")


def test_limpeza_ignora_pasta_estranha():
    limpar_tudo()
    (storage.raiz() / "nao-e-um-trabalho").mkdir()
    relato = storage.limpar(agora=AGORA)
    assert relato["expirados"] == [] and relato["por_cota"] == []
    assert (storage.raiz() / "nao-e-um-trabalho").exists()
    print("OK: a limpeza não mexe em pasta que não é trabalho")


def test_limpeza_sobrevive_a_ficha_corrompida():
    limpar_tudo()
    job = trabalho(60)
    with open(storage.caminho_ficha(job), "w", encoding="utf-8") as f:
        f.write("{isto nao e json")
    relato = storage.limpar(agora=AGORA)
    assert job in relato["expirados"], "ficha ilegível deve ser tratada como lixo"
    print("OK: ficha corrompida não trava a limpeza")


def test_tamanho_total_soma_so_os_trabalhos():
    limpar_tudo()
    trabalho(60, bytes_de_lixo=2000)
    trabalho(60, bytes_de_lixo=3000)
    total = storage.tamanho_total()
    # 5000 de lixo mais as duas fichas, que são pequenas
    assert 5000 < total < 6000, total
    print("OK: tamanho_total soma o que está em disco")


def test_falha_ao_apagar_nao_conta_como_espaco_livre():
    """Pasta que não pôde ser apagada não pode ser dada como apagada.

    No Windows o `rmtree` falha enquanto alguém segura um arquivo — um download
    em andamento, por exemplo. Contando a pasta como liberada, a conta da cota
    subtrai um espaço que continua ocupado, a varredura para achando que já
    coube, e o disco segue enchendo. Melhor deixar para a próxima passagem.
    """
    limpar_tudo()
    original = limits.COTA_DISCO_BYTES
    limits.COTA_DISCO_BYTES = 5000
    rmtree_real = storage.shutil.rmtree

    def rmtree_que_falha(caminho, *args, **kwargs):
        return   # não apaga nada, e nem levanta: é o que ignore_errors faz

    storage.shutil.rmtree = rmtree_que_falha
    try:
        antigo = trabalho(300, bytes_de_lixo=3000)
        trabalho(60, bytes_de_lixo=3000)
        relato = storage.limpar(agora=AGORA)
        assert antigo not in relato["por_cota"], \
            "pasta que continua em disco não pode entrar no relato"
        assert storage.pasta(antigo).exists()
        assert relato["bytes_livres"] == 0, relato
    finally:
        storage.shutil.rmtree = rmtree_real
        limits.COTA_DISCO_BYTES = original
    print("OK: falha ao apagar não vira espaço livre no papel")


def test_limpeza_periodica_roda_no_ciclo_de_vida():
    """A tarefa de fundo do `lifespan` realmente apaga o que venceu.

    Nenhum outro teste entra no ciclo de vida: o `TestClient` só o executa
    quando usado como contexto. Sem este teste, um erro na fiação do `lifespan`
    — um nome trocado, uma tarefa que morre na primeira volta — só apareceria
    em produção, e em silêncio, porque o disco encheria devagar.
    """
    import time

    from fastapi.testclient import TestClient

    from web.api import main

    limpar_tudo()
    job_id = storage.novo_id()
    # Relógio real aqui, e não o AGORA fixo: quem decide é a tarefa de fundo.
    storage.criar_trabalho(job_id, "planta.pdf", 1, 10,
                           agora=time.time() - limits.PRAZO_SEGUNDOS - 60)

    intervalo = main.INTERVALO_LIMPEZA
    main.INTERVALO_LIMPEZA = 0.05
    try:
        with TestClient(main.app):
            fim = time.time() + 10
            while time.time() < fim and storage.pasta(job_id).exists():
                time.sleep(0.05)
    finally:
        main.INTERVALO_LIMPEZA = intervalo

    assert not storage.pasta(job_id).exists(), \
        "a tarefa periódica do ciclo de vida não limpou o trabalho vencido"
    print("OK: a limpeza periódica roda no ciclo de vida da app")


if __name__ == "__main__":
    test_expira_por_prazo()
    test_cota_apaga_o_mais_antigo_primeiro()
    test_limpeza_ignora_pasta_estranha()
    test_limpeza_sobrevive_a_ficha_corrompida()
    test_tamanho_total_soma_so_os_trabalhos()
    test_falha_ao_apagar_nao_conta_como_espaco_livre()
    test_limpeza_periodica_roda_no_ciclo_de_vida()
    print("Todos os testes de armazenamento passaram.")
