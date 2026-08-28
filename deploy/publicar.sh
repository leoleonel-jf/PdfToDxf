#!/usr/bin/env bash
# Troca a imagem em execução, espera ela ficar saudável, e volta atrás se não
# ficar. Roda **na VPS**, chamado por ssh pelo workflow de deploy.
#
#   uso: publicar.sh ghcr.io/dono/pdftodxf:<sha>
set -euo pipefail

NOVA="${1:?uso: publicar.sh <imagem>}"
RAIZ="${PDFTODXF_RAIZ:-/opt/pdftodxf}"
PRAZO="${PDFTODXF_PRAZO_SAUDE:-120}"

cd "$RAIZ"

# O que está rodando agora, para poder voltar. Vazio no primeiro deploy.
ANTERIOR="$(sed -n 's/^IMAGEM=//p' .env || true)"

trocar() {
  local imagem="$1"
  if grep -q '^IMAGEM=' .env; then
    # `|` como separador: o nome da imagem tem `/` e `:`.
    sed -i "s|^IMAGEM=.*|IMAGEM=${imagem}|" .env
  else
    echo "IMAGEM=${imagem}" >> .env
  fi
  docker compose pull app
  docker compose up -d
}

saudavel() {
  # Espera a **condição**, nunca um tempo de relógio fixo: numa VPS ocupada a
  # subida demora mais, e dormir um tanto arbitrário troca um falso vermelho
  # por outro.
  local fim=$((SECONDS + PRAZO))
  local id estado
  while (( SECONDS < fim )); do
    id="$(docker compose ps -q app || true)"
    if [ -n "$id" ]; then
      estado="$(docker inspect --format '{{.State.Health.Status}}' "$id" 2>/dev/null || echo desconhecido)"
      [ "$estado" = healthy ] && return 0
    fi
    sleep 3
  done
  return 1
}

echo "Subindo ${NOVA}"
trocar "$NOVA"

if saudavel; then
  echo "No ar: ${NOVA}"
  # Camadas velhas se acumulam e enchem o disco — e disco cheio derruba o
  # serviço pelo caminho mais bobo possível.
  docker image prune -f >/dev/null 2>&1 || true
  exit 0
fi

echo "A imagem nova nao ficou saudavel em ${PRAZO}s." >&2

if [ -z "$ANTERIOR" ]; then
  echo "Nao havia imagem anterior para voltar. O servico esta fora." >&2
  exit 1
fi

echo "Voltando para ${ANTERIOR}" >&2
trocar "$ANTERIOR"
if saudavel; then
  echo "Voltou para a anterior. A publicacao falhou, o servico esta no ar." >&2
else
  echo "A anterior tambem nao subiu. O servico esta fora, entre por ssh." >&2
fi
# Sempre vermelho: reverter em silencio esconde a quebra.
exit 1
