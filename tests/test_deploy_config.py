"""Os invariantes dos arquivos de execução.

Sem PyYAML de propósito: ele não está nos `requirements`, e um teste que o
importe passa nesta máquina e quebra na integração contínua. Os arquivos são
nossos e o formato é estável, então um extrator de bloco por indentação basta.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = Path(__file__).resolve().parents[1]
COMPOSE = (RAIZ / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
CADDY = (RAIZ / "deploy" / "Caddyfile").read_text(encoding="utf-8")
EXEMPLO = (RAIZ / "deploy" / ".env.exemplo").read_text(encoding="utf-8")


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


def test_o_caddy_limita_o_corpo():
    assert "max_size" in CADDY and "100MB" in CADDY, CADDY
    print("OK: o Caddy recusa corpo acima de 100 MB")


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


def test_o_deploy_nasce_desligado():
    """Sem a guarda, o primeiro merge tenta publicar numa VPS que não existe."""
    assert "DEPLOY_ATIVO" in WORKFLOW, WORKFLOW
    print("OK: o deploy só roda com DEPLOY_ATIVO ligado")


def test_o_deploy_so_roda_na_main():
    assert "branches: [main]" in WORKFLOW, WORKFLOW
    print("OK: o deploy só roda na main")


def test_publicar_volta_atras_e_falha():
    """Reverter em silêncio esconde a quebra: o job tem de ficar vermelho."""
    assert "ANTERIOR" in PUBLICAR, PUBLICAR
    assert "exit 1" in PUBLICAR, PUBLICAR
    assert "set -euo pipefail" in PUBLICAR, PUBLICAR
    print("OK: publicar.sh volta atrás e sai com erro")


if __name__ == "__main__":
    test_o_app_nao_publica_porta()
    test_os_tres_volumes_de_dados_existem()
    test_a_verificacao_de_saude_usa_a_rota_de_saude()
    test_o_proxies_esta_configurado()
    test_o_dominio_nao_esta_embutido_no_caddyfile()
    test_o_caddy_limita_o_corpo()
    test_o_exemplo_nao_tem_valor_nenhum()
    test_o_deploy_nasce_desligado()
    test_o_deploy_so_roda_na_main()
    test_publicar_volta_atras_e_falha()
    print("Todos os testes da configuração de deploy passaram.")
