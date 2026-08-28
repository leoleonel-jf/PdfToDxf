# Briefing — etapa 5a do PdfToDxf (deploy: pôr no ar)

Documento auto-contido, escrito para quem chega sem nenhum histórico da
conversa que o originou. Se você é a assistente que vai executar este trabalho,
leia isto inteiro antes de tocar em qualquer coisa.

## O projeto, em um parágrafo

O PdfToDxf converte plantas em PDF vetorial para DXF em escala real. Existia
como app desktop em Tkinter; foi transformado numa versão web que compartilha o
mesmo núcleo Python. O trabalho está dividido em cinco etapas: núcleo, API de
conversão, linha de comando, frontend, contas/cotas/registros, e deploy. **As
etapas 1 a 4 estão prontas e mescladas na `main`.** Falta a etapa 5 — pôr no
ar — e é o que você vai fazer.

Repositório: `github.com/leoleonel-jf/PdfToDxf`. O dono é brasileiro e trabalha
em português; responda em português.

## Leia estes dois arquivos, nesta ordem

1. **`docs/superpowers/specs/2026-08-28-deploy-design.md`** — o desenho da
   etapa 5, com as decisões já tomadas. **É o seu contrato.** Não redecida o
   que ele decide.
2. **`docs/superpowers/HANDOFF.md`** — o estado do projeto inteiro, escrito
   para quem chega frio: o que está pronto, o que foi medido, quais armadilhas
   já custaram tempo, e as dívidas conhecidas.

O resto do `docs/superpowers/` são as specs e os planos das etapas anteriores.
Consulte se precisar, mas não é obrigatório.

> **O que você **não** vai receber:** a pasta `.superpowers/sdd/` do autor
> original (ledger de execução, briefs e relatórios de revisão) é ignorada pelo
> git e só existe na máquina dele. Os dois arquivos acima foram escritos
> justamente para bastar sem ela.

## O seu escopo: só o bloco 5a

A etapa 5 são três blocos sequenciais. **Você faz o 5a.** Não comece o 5b nem o
5c — o desenho explica por que a ordem importa.

**5a entrega:** VPS preparada, Docker Compose com app e Caddy, HTTPS no
domínio, e-mail real pelo Brevo, rota de saúde, deploy contínuo com volta
automática, backup diário para fora da VPS, e sonda externa.

**5b (depois):** exportação assíncrona e o teto de entidades medido.
**5c (depois):** entrada pelo Google.

## Decisões já tomadas — não as reabra

| Assunto | Decisão |
|---|---|
| Hospedagem | VPS já contratada, Ubuntu LTS, **sem Docker instalado** |
| Domínio | Já registrado (o dono informa qual) |
| E-mail | **Brevo**, SMTP transacional |
| Publicação | **Deploy contínuo**: mesclar na `main` sobe sozinho |
| Backup | Cópia diária **para fora da VPS**, com restauração testada |
| Processos uvicorn | **Um só** — a atomicidade da cota supõe isso |
| Limite de taxa no Caddy | **Não** — exigiria plugin, e o app já freia por IP |
| Monitoramento | Sonda externa gratuita na rota de saúde |

## O que já existe, e não precisa ser construído

Conferido no código. Não gaste tarefa com isto:

- **`deploy/Dockerfile`** — dois estágios, node só no primeiro, imagem final
  sem `node_modules`, usuário sem privilégio. **Nunca foi construído**, porque
  não há `docker` na máquina do autor. O primeiro `docker build` da vida do
  projeto é seu, e é razoável que falhe algumas vezes.
- **`web/api/enviador.py`** — **o caminho SMTP já está escrito.** Sem
  `PDFTODXF_SMTP_SERVIDOR` o e-mail vira arquivo em `dados/emails/`; com ele,
  vai por SMTP. **O Brevo é configuração, não código.**
- **`.github/workflows/ci.yml`** — três jobs verdes (Python, frontend, e2e). O
  deploy contínuo se apoia neles em vez de repetir testes.
- **`PDFTODXF_PROXIES`** — o app já sabe ler o IP real de trás de um proxy.
  Falta configurar.

## O que é trabalho novo

- **`GET /api/saude`** — não existe nenhuma rota de saúde. Ela tem de conferir
  que o banco abre e que a pasta de dados aceita escrita. Uma rota que só
  responde `200 ok` sem tocar em nada ficaria verde com o volume desmontado,
  que é justamente a falha a pegar. Sem autenticação, e sem contar nada que não
  se conte a um estranho.
- **`deploy/docker-compose.yml` e `deploy/Caddyfile`** — a spec geral os
  nomeia; não existem.
- **Workflow de deploy contínuo** — com verificação de saúde e volta automática
  para a imagem anterior se ela não responder. Sem passo humano entre mesclar e
  ir ao ar, a rede de segurança tem de estar no automatismo, e um job que
  reverte em silêncio esconde a quebra: ele tem de **falhar**.
- **Backup** — `.backup` do SQLite, **nunca `cp`** (copiar com escrita em curso
  produz banco corrompido, e o defeito só aparece no dia da restauração).

## A armadilha que estraga tudo se passar batido

**`PDFTODXF_PROXIES`.** Sem ele configurado, o app enxerga o IP do contêiner do
Caddy em toda requisição. Consequência: **todos os visitantes do mundo dividem
o mesmo balde de cota** — o primeiro esgota e ninguém mais converte nada, e o
freio de login por IP vira um freio global.

Trate como item de primeira classe, com teste: uma requisição com
`X-Forwarded-For` tem de ser atribuída ao IP certo, e o cabeçalho vindo de fora
do proxy tem de ser ignorado.

## Ambiente e convenções do projeto

- **Windows 11, PowerShell 7+** na máquina do autor. Há Bash disponível.
- **Use sempre `./.venv/Scripts/python.exe`**, nunca `python` puro.
- **Sem pytest.** Os testes são funções com `assert` e um bloco
  `if __name__ == "__main__":`. São 25 arquivos em `tests/`, cada um um
  programa independente. Mantenha o padrão.
- **Frontend:** `cd web/frontend && npm test && npm run build`. São 2222 testes
  de unidade. O ponta a ponta é `npm run e2e` (Playwright, 22 testes).
- **Nenhuma dependência nova** sem motivo forte: `requirements.txt`,
  `web/requirements.txt` e `web/frontend/package.json` são estáveis de
  propósito.
- **Commits em português, sem acentos no assunto** (o console do Windows é
  cp1252).
- **Toda mensagem de erro diz o que houve e o que fazer.** "Erro ao processar"
  não é mensagem.
- **Texto de tela vai por `textContent`**, nunca `innerHTML`.

### Armadilhas de ambiente que já custaram tempo

- **A porta 8000 pode estar ocupada por outro aplicativo do dono.** O
  `playwright.config.ts` aponta para ela, e o e2e trava esperando um servidor
  que nunca responde o que ele quer. Confira antes de investigar:
  `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/openapi.json`
  — `200` é a API do projeto; um redirecionamento é processo alheio. **Derrubar
  processo do usuário é decisão dele: pergunte, não mate.**
- **Para abrir a tela à mão use `http://localhost:5173`, nunca `127.0.0.1`** —
  o Vite escuta em `localhost` (IPv6) por padrão.
- **A bateria Python roda em paralelo, um processo por arquivo** (20 s contra
  131 s sequencial), porque cada arquivo monta as próprias pastas temporárias.
  Confira essa premissa se acrescentar um arquivo de teste.

## O que só o dono pode providenciar

Peça, não tente adivinhar:

- O **domínio** e acesso ao painel de DNS (o Caddy precisa do nome; o Brevo
  precisa publicar SPF, DKIM e DMARC lá).
- **Acesso à VPS.** A chave privada **nunca** se cola numa conversa — o que se
  compartilha é a chave pública. Peça que ele instale a chave pública de deploy
  no servidor.
- **Conta no Brevo**, criada, para tirar as credenciais SMTP.
- **Destino do backup** — conta e credenciais do armazenamento de objetos.
- **Conta na sonda** (UptimeRobot ou similar).

Segredos moram num `.env` na VPS, com permissão fechada. **Nunca no
repositório, nunca dentro da imagem.**

## Como o trabalho vem sendo feito neste projeto

O processo pegou defeitos reais e vale manter:

1. Plano escrito antes do código, com ciclo de teste explícito por tarefa.
2. Execução tarefa a tarefa, com contexto limpo.
3. Revisão de cada tarefa por um olhar separado, instruído a **não confiar** no
   relatório de quem implementou.
4. Revisão do branch inteiro no fim.
5. **PRs pequenos** — é regra de ouro do dono.

Duas lições caras, para não se repetirem:

- **Antes de escrever qualquer conversão, procure se ela já existe no núcleo.**
  Numa etapa anterior o plano mandou reimplementar duas conversões que já
  existiam testadas, errou as duas, e o DXF sairia com 11,34 m onde a parede
  tem 10,00 m. Sete revisões por tarefa não pegaram.
- **Espere a condição, nunca um tempo de relógio.** Testes que dormem antes de
  conferir falham sob carga, e o diagnóstico vai parar no arquivo errado.

## Critérios de pronto do 5a

Confira item a item. Marcar sem rodar não prova nada.

- O domínio responde em HTTPS com certificado válido, sem aviso de navegador.
- Um PDF sobe, converte e baixa como DXF, pela internet.
- Um cadastro manda e-mail de verdade, que **chega e não cai no spam**; o link
  confirma a conta.
- **O IP que o app registra é o do visitante, não o do Caddy** — confere-se
  lendo o IP gravado no registro de uma conversão feita de fora da VPS (do
  celular na rede móvel, por exemplo).
- `/api/saude` responde 200, e responde **erro** com o volume de dados
  desmontado.
- Mesclar na `main` publica sozinho; uma imagem que não sobe é revertida
  sozinha, e o job fica **vermelho**.
- O backup roda, e **uma restauração foi feita e conferida**.
- A sonda avisa quando o serviço cai — testado derrubando de propósito.

## Uma ressalva que não pode se perder

Ao fim do 5a o serviço está acessível, **mas a exportação do DXF ainda roda no
processo do site** e uma planta grande o bastante derruba tudo. É o bloco 5b
que conserta. **Diga ao dono para não divulgar o endereço até o 5b entrar.**
