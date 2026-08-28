"""Os invariantes dos arquivos de execução.

Sem PyYAML de propósito: ele não está nos `requirements`, e um teste que o
importe passa nesta máquina e quebra na integração contínua. Os arquivos são
nossos e o formato é estável, então um extrator de bloco por indentação basta.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.api.limits import TETO_PDF_BYTES

RAIZ = Path(__file__).resolve().parents[1]
COMPOSE = (RAIZ / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
CADDY = (RAIZ / "deploy" / "Caddyfile").read_text(encoding="utf-8")
EXEMPLO = (RAIZ / "deploy" / ".env.exemplo").read_text(encoding="utf-8")
DOCKERFILE = (RAIZ / "deploy" / "Dockerfile").read_text(encoding="utf-8")


def bloco(texto: str, nome: str, recuo: int = 2) -> str:
    """O trecho de `nome:` até a próxima chave no mesmo recuo."""
    abertura = " " * recuo + nome + ":"
    linhas = texto.splitlines()
    for i, linha in enumerate(linhas):
        if linha.rstrip() == abertura:
            saida = []
            for seguinte in linhas[i + 1:]:
                if seguinte.strip() and not seguinte.startswith(" " * (recuo + 1)):
                    break
                saida.append(seguinte)
            return "\n".join(saida)
    raise AssertionError(f"bloco {nome!r} não encontrado")


def test_o_app_nao_publica_porta():
    """Se o app publicar porta, dá para chegar nele sem passar pelo Caddy — e
    aí o `X-Forwarded-For` vira palavra de qualquer um."""
    assert "ports:" not in bloco(COMPOSE, "app"), bloco(COMPOSE, "app")
    assert "ports:" in bloco(COMPOSE, "caddy")
    print("OK: só o Caddy publica porta")


def test_os_tres_volumes_de_dados_existem():
    corpo = bloco(COMPOSE, "app")
    for volume in ("dados:", "registros:", "banco:"):
        assert volume in corpo, corpo
    print("OK: os três volumes com prazos diferentes estão declarados")


def test_a_verificacao_de_saude_usa_a_rota_de_saude():
    corpo = bloco(COMPOSE, "app")
    assert "healthcheck:" in corpo, corpo
    assert "/api/saude" in corpo, corpo
    print("OK: o Compose confere a rota de saúde")


def test_o_proxies_esta_configurado():
    """Sem isto, o app vê o IP do Caddy e o mundo inteiro divide um balde de cota."""
    assert "PDFTODXF_PROXIES" in bloco(COMPOSE, "app")
    print("OK: PDFTODXF_PROXIES está configurado")


def test_o_dominio_nao_esta_embutido_no_caddyfile():
    assert "{$DOMINIO}" in CADDY, CADDY
    print("OK: o domínio vem do ambiente, não do arquivo")


def test_o_caddy_limita_o_corpo_no_valor_exato_em_bytes():
    """Em bytes, e igual ao teto do serviço.

    `100MB` no Caddy é 100.000.000 (SI), menor que os 104857600 de
    `limits.TETO_PDF_BYTES`: a diferença é uma faixa de ~4,8 MiB que o app
    aceitaria e o proxy recusa com um 413 cru, sem a mensagem que o projeto
    exige. Casar substring também deixava passar `100MB` escrito num
    comentário, então o que se lê aqui é a diretiva, sem comentário nenhum.
    """
    valores = [linha.split("#")[0].split()[1]
               for linha in CADDY.splitlines()
               if linha.split("#")[0].strip().startswith("max_size")]
    assert valores == [str(TETO_PDF_BYTES)], (valores, TETO_PDF_BYTES)
    print(f"OK: o Caddy recusa corpo acima de {TETO_PDF_BYTES} bytes exatos")


def test_o_caddy_nao_recebe_o_env_inteiro():
    """O Caddy precisa do DOMINIO e de nada mais. Dar-lhe o `.env` põe o
    segredo de sessão e a senha do SMTP no ambiente de um processo que não usa
    nem um nem outro — superfície de graça."""
    corpo = bloco(COMPOSE, "caddy")
    # Sem os comentários: o que vale é a diretiva, e o comentário aqui do lado
    # fala justamente de `env_file` para explicar por que ele não está.
    diretivas = "\n".join(l.split("#")[0] for l in corpo.splitlines())
    assert "env_file" not in diretivas, corpo
    assert "DOMINIO" in diretivas, corpo
    print("OK: o Caddy só recebe o DOMINIO")


def test_a_imagem_cria_e_da_dono_dos_tres_pontos_de_montagem():
    """Ponto de montagem que não existe na imagem o Docker cria como root, e o
    app roda como `servico`: faltando um, o serviço nunca fica saudável e o
    Caddy — que depende da saúde dele — nunca sobe."""
    plano = DOCKERFILE.replace("\\\n", " ")
    criacao = [l for l in plano.splitlines() if "mkdir" in l and "chown" in l]
    assert len(criacao) == 1, criacao
    for pasta in ("/dados", "/registros", "/banco"):
        assert criacao[0].count(pasta) == 2, (pasta, criacao[0])
    print("OK: os três pontos de montagem nascem com dono")


def test_o_exemplo_nao_tem_valor_nenhum():
    """`.env.exemplo` é modelo, não configuração: nenhuma linha com valor."""
    for linha in EXEMPLO.splitlines():
        limpa = linha.strip()
        if not limpa or limpa.startswith("#"):
            continue
        assert limpa.endswith("="), f"linha com valor no exemplo: {linha!r}"
    print("OK: o exemplo não carrega valor nenhum")


WORKFLOW = (RAIZ / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
PUBLICAR = (RAIZ / "deploy" / "publicar.sh").read_text(encoding="utf-8")


def gatilhos() -> str:
    """O bloco `on:` do workflow, **sem comentários**.

    Os comentários deste arquivo explicam justamente o gatilho que não está lá
    ("disparar no push deixava..."), e casar substring no texto cru daria
    verde para a configuração errada."""
    bruto = bloco(WORKFLOW, "on", recuo=0)
    return "\n".join(l.split("#")[0] for l in bruto.splitlines())


def test_o_deploy_nasce_desligado():
    """Sem a guarda, o primeiro merge tenta publicar numa VPS que não existe."""
    assert "DEPLOY_ATIVO" in WORKFLOW, WORKFLOW
    print("OK: o deploy só roda com DEPLOY_ATIVO ligado")


def test_o_deploy_so_roda_na_main():
    """Substring solta não prova nada — `branches: [main]` pode estar em
    qualquer lugar do arquivo. Quem decide é o bloco `on:`, e ele tem de
    filtrar a `main` uma vez só."""
    trechos = gatilhos()
    assert "branches: [main]" in trechos, trechos
    assert trechos.count("branches:") == 1, trechos
    print("OK: o deploy só roda na main")


def test_o_deploy_espera_a_integracao_continua():
    """O Dockerfile roda só `npm test`; a suíte Python mora no workflow `CI`.
    Disparando no push, um commit com teste Python quebrado construiria,
    publicaria e iria ao ar enquanto o CI ficava vermelho em paralelo."""
    trechos = gatilhos()
    assert "workflow_run:" in trechos, trechos
    assert "workflows: [CI]" in trechos, trechos
    assert "push:" not in trechos, trechos
    # Só o gatilho não basta: `workflow_run` dispara também quando o CI falha.
    assert "workflow_run.conclusion == 'success'" in WORKFLOW, WORKFLOW
    print("OK: o deploy só constrói depois de o CI passar")


def test_a_primeira_imagem_pode_ser_construida_a_mao():
    """A VPS não compila nada, e o `IMAGEM=` do primeiro `.env` precisa de uma
    etiqueta que já exista — antes de DEPLOY_ATIVO, que só se liga depois."""
    assert "workflow_dispatch:" in gatilhos(), gatilhos()
    assert "github.event_name == 'workflow_dispatch'" in WORKFLOW, WORKFLOW
    print("OK: dá para construir a primeira imagem à mão")


def test_publicar_volta_atras_e_falha():
    """Reverter em silêncio esconde a quebra: o job tem de ficar vermelho."""
    assert "ANTERIOR" in PUBLICAR, PUBLICAR
    assert "exit 1" in PUBLICAR, PUBLICAR
    assert "set -euo pipefail" in PUBLICAR, PUBLICAR
    # Sem `--no-deps` o `up` religa o caddy, que tem `depends_on:
    # service_healthy`; com a imagem nova doente o próprio comando sai com
    # erro e o `set -e` mata o script **dentro** de `trocar()`, antes de
    # qualquer volta atrás. O rollback fica inalcançável e o teste, verde.
    assert "--no-deps" in PUBLICAR, PUBLICAR
    print("OK: publicar.sh volta atrás, alcança a volta, e sai com erro")


def test_publicar_confere_pelo_dominio():
    """Saúde do contêiner é saúde por dentro. Com o Caddy morto o app segue
    saudável, o site está fora e o job ficaria verde."""
    assert "DOMINIO" in PUBLICAR, PUBLICAR
    assert "curl" in PUBLICAR, PUBLICAR
    assert "/api/saude" in PUBLICAR, PUBLICAR
    print("OK: publicar.sh confere o serviço pelo domínio")


def test_publicar_puxa_antes_de_reescrever_o_env():
    """Na ordem inversa, um registry fora do ar deixa o `.env` apontando para
    uma imagem que a VPS não tem."""
    puxada = PUBLICAR.index("docker compose pull app")
    escrita = PUBLICAR.index("anotar_imagem \"$imagem\"")
    assert puxada < escrita, (puxada, escrita)
    print("OK: publicar.sh puxa antes de reescrever o .env")


if __name__ == "__main__":
    test_o_app_nao_publica_porta()
    test_os_tres_volumes_de_dados_existem()
    test_a_verificacao_de_saude_usa_a_rota_de_saude()
    test_o_proxies_esta_configurado()
    test_o_dominio_nao_esta_embutido_no_caddyfile()
    test_o_caddy_limita_o_corpo_no_valor_exato_em_bytes()
    test_o_caddy_nao_recebe_o_env_inteiro()
    test_a_imagem_cria_e_da_dono_dos_tres_pontos_de_montagem()
    test_o_exemplo_nao_tem_valor_nenhum()
    test_o_deploy_nasce_desligado()
    test_o_deploy_so_roda_na_main()
    test_o_deploy_espera_a_integracao_continua()
    test_a_primeira_imagem_pode_ser_construida_a_mao()
    test_publicar_volta_atras_e_falha()
    test_publicar_confere_pelo_dominio()
    test_publicar_puxa_antes_de_reescrever_o_env()
    print("Todos os testes da configuração de deploy passaram.")
