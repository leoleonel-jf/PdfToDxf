#!/usr/bin/env bash
# Troca a imagem em execução, espera ela ficar saudável, confere o site pelo
# domínio, e volta atrás se qualquer uma dessas etapas não fechar. Roda **na
# VPS**, chamado por ssh pelo workflow de deploy.
#
#   uso: publicar.sh ghcr.io/dono/pdftodxf:<sha>
set -euo pipefail

NOVA="${1:?uso: publicar.sh <imagem>}"
RAIZ="${PDFTODXF_RAIZ:-/opt/pdftodxf}"
PRAZO="${PDFTODXF_PRAZO_SAUDE:-120}"

cd "$RAIZ"

# O que está rodando agora, para poder voltar. Vazio no primeiro deploy.
ANTERIOR="$(sed -n 's/^IMAGEM=//p' .env | head -n1 || true)"

anotar_imagem() {
  local imagem="$1"
  if grep -q '^IMAGEM=' .env; then
    # `|` como separador: o nome da imagem tem `/` e `:`.
    sed -i "s|^IMAGEM=.*|IMAGEM=${imagem}|" .env
  else
    echo "IMAGEM=${imagem}" >> .env
  fi
}

trocar() {
  # `puxar=nao` na volta atrás: a imagem anterior já está no disco, e depender
  # do registry justamente na hora de consertar é depender dele no pior
  # momento possível.
  local imagem="$1" puxar="${2:-sim}"
  if [ "$puxar" = sim ]; then
    # Puxa **antes** de reescrever o `.env`. Na ordem inversa, um registry
    # fora do ar deixaria o arquivo apontando para uma imagem que a VPS não
    # tem. A variável no ambiente vence a do `.env` na interpolação do
    # Compose, então dá para puxar sem ter escrito nada ainda.
    IMAGEM="$imagem" docker compose pull app
  fi
  anotar_imagem "$imagem"
  # `--no-deps`, e só o `app`: o `caddy` tem `depends_on: service_healthy`, e
  # um `up` que o inclua sai com erro ("dependency failed to start") quando a
  # imagem nova não fica saudável. Sob `set -e` isso mataria o script aqui
  # dentro, antes de qualquer volta atrás. Quem decide a saúde é `saudavel()`.
  docker compose up -d --no-deps app
}

subir_o_resto() {
  # Só depois de o app estar saudável — que é exatamente a condição que o
  # `depends_on` do caddy espera.
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

no_ar_pelo_dominio() {
  # Saúde do contêiner é saúde **por dentro**. Se o Caddy morrer — Caddyfile
  # ruim, certificado não emitido — o app continua saudável e o site está
  # fora, e o job ficaria verde com o serviço inacessível. Esta é a única
  # conferência que fala do que o visitante vê.
  local dominio
  dominio="$(sed -n 's/^DOMINIO=//p' .env | head -n1 || true)"
  if [ -z "$dominio" ]; then
    echo "AVISO: DOMINIO vazio no .env — sem conferencia pelo dominio." >&2
    return 0
  fi
  local fim=$((SECONDS + PRAZO))
  while (( SECONDS < fim )); do
    if curl -fsS --max-time 10 "https://${dominio}/api/saude" >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
  done
  echo "O app esta saudavel por dentro, mas https://${dominio}/api/saude nao" \
       "responde. Olhe o caddy: docker compose logs caddy" >&2
  return 1
}

echo "Subindo ${NOVA}"
trocar "$NOVA"

if saudavel && subir_o_resto && no_ar_pelo_dominio; then
  echo "No ar: ${NOVA}"
  # Camadas velhas se acumulam e enchem o disco — e disco cheio derruba o
  # serviço pelo caminho mais bobo possível.
  docker image prune -f >/dev/null 2>&1 || true
  exit 0
fi

echo "A imagem nova nao entrou no ar dentro do prazo (${PRAZO}s por etapa)." >&2

if [ -z "$ANTERIOR" ]; then
  echo "Nao havia imagem anterior para voltar. O servico esta fora." >&2
  exit 1
fi

echo "Voltando para ${ANTERIOR}" >&2
trocar "$ANTERIOR" nao
if saudavel && subir_o_resto && no_ar_pelo_dominio; then
  echo "Voltou para a anterior. A publicacao falhou, o servico esta no ar." >&2
else
  echo "A anterior tambem nao subiu. O servico esta fora, entre por ssh." >&2
fi
# Sempre vermelho: reverter em silencio esconde a quebra.
exit 1
