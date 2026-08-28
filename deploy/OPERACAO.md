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

## 3. A primeira imagem, construída à mão

**A VPS não compila nada** — por desenho, a imagem chega pronta. Então o
`IMAGEM=` do primeiro `.env` precisa de uma etiqueta que já exista no ghcr, e
ela tem de sair antes de `DEPLOY_ATIVO` (passo 6) existir. É para isso que o
workflow aceita disparo manual:

```bash
gh workflow run Deploy          # ou: Actions → Deploy → Run workflow
gh run watch                    # espere terminar
```

O job `Trocar a imagem na VPS` aparece **pulado**: sem `DEPLOY_ATIVO` ele não
roda, e é isso mesmo — aqui só se quer a imagem. A etiqueta sai no resumo do
run, pronta para copiar:

```bash
gh run view --log | grep 'IMAGEM='      # ou leia o resumo do run no navegador
```

### Torne o pacote público

**Pacote publicado com o `GITHUB_TOKEN` nasce privado, mesmo em repositório
público.** Sem este passo, o `docker compose pull` da VPS leva `denied` e o
passo 4 não sai do lugar.

No GitHub: perfil/organização → **Packages** → `pdftodxf` → *Package settings*
→ **Change visibility** → *Public*. Confira de fora, sem estar logado:

```bash
docker logout ghcr.io
docker pull <etiqueta>          # tem de baixar
```

> Escolhemos **pacote público** em vez de `docker login ghcr.io` na VPS: um
> token de leitura na VPS é mais um segredo para guardar, rodar e vazar, e a
> imagem não contém segredo nenhum (o `.env` vive só na VPS). Se um dia o
> conteúdo da imagem virar sensível, a troca é fazer login com um token de
> leitura só — e aí este parágrafo muda junto.

## 4. Primeiro deploy, manual

O automático só entra no passo 6.

```bash
cd /opt/pdftodxf
# copie do repositório: docker-compose.yml, Caddyfile, .env.exemplo,
# publicar.sh, backup.py
cp .env.exemplo .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # PDFTODXF_SEGREDO
# preencha .env: IMAGEM (a etiqueta do passo 3), DOMINIO, PDFTODXF_URL_BASE,
# PDFTODXF_SEGREDO
chmod +x publicar.sh
docker compose up -d
docker compose ps                      # app tem de aparecer "healthy"
curl -fsS https://<dominio>/api/saude   # {"ok":true}
```

**Confira que o aviso de segredo ausente não aparece** — ele existe desde a
etapa 4 justamente para denunciar um `.env` incompleto:

```bash
docker compose logs app | grep -i segredo    # não pode achar nada
```

## 5. Brevo

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

## 6. Ligar a publicação automática

Nesta ordem — a variável por último:

```bash
gh secret set VPS_HOST      --body "<ip-da-vps>"
gh secret set VPS_USUARIO   --body "$USUARIO"
gh secret set VPS_CHAVE     < ~/.ssh/pdftodxf_deploy
ssh-keyscan <ip-da-vps> 2>/dev/null | gh secret set VPS_HOSTKEY
gh variable set DEPLOY_ATIVO --body "1"
```

Depois disso, um commit inócuo na `main` tem de publicar sozinho — **depois de
o workflow `CI` ficar verde**, que é de quem o Deploy espera o sinal. CI
vermelho não constrói nem publica nada. Acompanhe em Actions e confirme que a
etiqueta nova está no ar:

```bash
grep '^IMAGEM=' /opt/pdftodxf/.env
```

## 7. Backup no cron

Diário, e a restauração testada uma vez.

**No crontab do `root`**, não no do usuário de deploy. São três motivos, e
qualquer um deles bastaria: `/var/lib/docker/volumes/` não é atravessável por
quem não é root, `/var/backups/pdftodxf` não é criável por ele, e
`/var/log/pdftodxf-backup.log` também não. No crontab do usuário, a tarefa
falharia toda noite — e falha silenciosa de backup é a pior espécie.

```bash
sudo mkdir -p /var/backups/pdftodxf
sudo touch /var/log/pdftodxf-backup.log
sudo crontab -e
```

Cole as três linhas abaixo. **A linha do comando é uma só** — o `cron` não
entende continuação com `\`, e quebrar a linha quebra a tarefa:

```cron
PDFTODXF_BACKUP_DIAS=30
PDFTODXF_BACKUP_COMANDO=rclone copyto --config /etc/rclone.conf {arquivo} remoto:pdftodxf/contas.db
15 3 * * * /usr/bin/python3 /opt/pdftodxf/backup.py /var/lib/docker/volumes/pdftodxf_banco/_data/contas.db /var/backups/pdftodxf >> /var/log/pdftodxf-backup.log 2>&1
```

> **Por que as variáveis vêm aqui, e não de `. ./.env`.** O `.env` é formato do
> Compose, não de shell: uma senha de SMTP com espaço, `$` ou aspas quebra o
> `source` — e quebraria o backup por causa de uma variável que ele nem usa. O
> `cron` lê `NOME=valor` literalmente, sem shell no meio, então o backup recebe
> só as duas variáveis que são dele. (No `cron`, `%` é especial: se o comando
> de envio tiver um, escape como `\%`.)

Confira na noite seguinte que rodou — e não confie no silêncio:

```bash
sudo tail -20 /var/log/pdftodxf-backup.log     # "Copia feita: ... bytes"
ls -l /var/backups/pdftodxf
```

A restauração, num banco de lado — **backup nunca restaurado é esperança**:

```bash
sudo cp /var/backups/pdftodxf/contas-$(date -u +%F).db /tmp/prova.db
sqlite3 /tmp/prova.db "PRAGMA integrity_check; SELECT count(*) FROM usuarios;"
# "ok" e a contagem batendo com a produção
```

## 8. Sonda

Cadastre `https://<dominio>/api/saude` no UptimeRobot (ou similar), com aviso
por e-mail, intervalo de 5 minutos. **Teste derrubando de propósito**, senão
você não sabe se ela avisa:

```bash
docker compose stop app     # espere o aviso chegar
docker compose start app    # e o de volta ao ar
```
