# Operação — roteiro da VPS

Passo a passo manual, para quem tem acesso ao servidor. Esta tarefa não tem
teste automatizado: o teste dela é o serviço no ar.

Onde aparecer `<dominio>`, `<ip-da-vps>` ou `<etiqueta>`, é substituição de
quem executa, não pendência.

> **Não divulgue o endereço até o bloco 5b entrar.** A exportação do DXF ainda
> roda no processo do site, e uma planta grande o bastante derruba tudo.

## 1. Preparar a VPS

Ubuntu LTS, como o usuário confirmou.

```bash
# Docker pelo repositório oficial — o `docker.io` do Ubuntu costuma vir velho
# e sem o plugin `compose`.
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"      # saia e entre de novo para valer
docker compose version               # tem de responder v2.x

sudo mkdir -p /opt/pdftodxf && sudo chown "$USER" /opt/pdftodxf

sudo ufw default deny incoming
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable && sudo ufw status
```

A chave de deploy é **só para isto**, não a chave pessoal. Gere-a na sua
máquina e instale só a pública:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pdftodxf_deploy -C "deploy pdftodxf"
ssh-copy-id -i ~/.ssh/pdftodxf_deploy.pub "$USUARIO@<ip-da-vps>"
```

## 2. Apontar o DNS

Registro A de `<dominio>` para `<ip-da-vps>`. Confira **antes** de subir o
Caddy — pedir certificado com DNS errado gasta tentativa no Let's Encrypt, e o
limite é por semana:

```bash
dig +short <dominio>     # tem de responder o IP da VPS
```

## 3. Primeiro deploy, manual

O automático só entra no passo 5.

```bash
cd /opt/pdftodxf
# copie do repositório: docker-compose.yml, Caddyfile, publicar.sh, backup.py
cp .env.exemplo .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # PDFTODXF_SEGREDO
# preencha .env: IMAGEM, DOMINIO, PDFTODXF_URL_BASE, PDFTODXF_SEGREDO
docker compose up -d
docker compose ps                      # app tem de aparecer "healthy"
curl -fsS https://<dominio>/api/saude   # {"ok":true}
```

**Confira que o aviso de segredo ausente não aparece** — ele existe desde a
etapa 4 justamente para denunciar um `.env` incompleto:

```bash
docker compose logs app | grep -i segredo    # não pode achar nada
```

## 4. Brevo

Crie a conta, verifique o domínio publicando SPF, DKIM e DMARC no DNS, e
preencha as cinco variáveis de SMTP no `.env`. Depois `docker compose up -d`
para o app relê-las. O critério não é o código chamar o SMTP — é o e-mail
**chegar**:

```bash
# cadastre-se no próprio serviço, com um endereço de verdade, e confira:
# (a) o e-mail chegou; (b) caiu na caixa de entrada, não no spam;
# (c) o link do e-mail confirma a conta e a cota sobe para 15.
docker compose exec app ls /dados/emails    # tem de estar VAZIO: se houver
                                            # arquivo aqui, o SMTP não pegou e
                                            # o serviço voltou ao modo arquivo
```

## 5. Ligar a publicação automática

Nesta ordem — a variável por último:

```bash
gh secret set VPS_HOST      --body "<ip-da-vps>"
gh secret set VPS_USUARIO   --body "$USUARIO"
gh secret set VPS_CHAVE     < ~/.ssh/pdftodxf_deploy
ssh-keyscan <ip-da-vps> 2>/dev/null | gh secret set VPS_HOSTKEY
gh variable set DEPLOY_ATIVO --body "1"
```

Depois disso, um commit inócuo na `main` tem de publicar sozinho. Acompanhe em
Actions e confirme que a etiqueta nova está no ar:

```bash
grep '^IMAGEM=' /opt/pdftodxf/.env
```

## 6. Backup no cron

Diário, e a restauração testada uma vez.

```bash
crontab -e
# 15 3 * * * cd /opt/pdftodxf && set -a && . ./.env && set +a && \
#   /usr/bin/python3 backup.py /var/lib/docker/volumes/pdftodxf_banco/_data/contas.db \
#   /var/backups/pdftodxf >> /var/log/pdftodxf-backup.log 2>&1
```

A restauração, num banco de lado — **backup nunca restaurado é esperança**:

```bash
cp /var/backups/pdftodxf/contas-$(date +%F).db /tmp/prova.db
sqlite3 /tmp/prova.db "PRAGMA integrity_check; SELECT count(*) FROM usuarios;"
# "ok" e a contagem batendo com a produção
```

## 7. Sonda

Cadastre `https://<dominio>/api/saude` no UptimeRobot (ou similar), com aviso
por e-mail, intervalo de 5 minutos. **Teste derrubando de propósito**, senão
você não sabe se ela avisa:

```bash
docker compose stop app     # espere o aviso chegar
docker compose start app    # e o de volta ao ar
```
