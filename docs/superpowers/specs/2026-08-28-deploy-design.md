# Etapa 5 — deploy: desenho

Escrito em 2026-08-28, depois de a etapa 4 inteira ser mesclada na `main`.
Governa a última etapa do projeto: levar a versão web ao ar, num domínio, para
o público.

A spec geral (`2026-08-01-pdftodxf-web-design.md`) já fixou a forma — Docker
Compose com app e Caddy, três volumes, segredos por variável de ambiente. Este
documento decide o que ela deixou em aberto e acrescenta o que as etapas 2 a 4
descobriram no caminho.

## A etapa são três blocos, nesta ordem

As dependências mandam a sequência, e não a preferência:

| Bloco | O que entrega | Por que nesta posição |
|---|---|---|
| **5a — No ar** | VPS, Compose, HTTPS, e-mail real, saúde, deploy contínuo, backup, sonda | O Brevo precisa de DNS no domínio; tudo o mais precisa do serviço existindo |
| **5b — Aguenta o público** | Exportação assíncrona e o teto de entidades medido | Medir o teto só vale no hardware de verdade, que o 5a cria |
| **5c — Entrada pelo Google** | OAuth, vinculação por e-mail | O Google exige domínio verificado e callback em HTTPS válido |

Cada bloco vira um plano próprio, executado em sessão de contexto limpo, como
as etapas anteriores. Este documento é o desenho dos três.

> **Ao fim do 5a o serviço está acessível, mas ainda não está pronto para ser
> anunciado:** a exportação continua capaz de derrubar o site, e é o 5b que
> conserta. **Não divulgue o endereço até o 5b entrar.** Decidido em
> 2026-08-28: o serviço fica público e anônimo, sem senha nem bloqueio por IP
> na frente — o risco é baixo enquanto ninguém souber o endereço, e uma senha
> temporária atrapalharia a conferência na tela.

## Decisões tomadas em 2026-08-28

Todas com o usuário, e é o que este desenho pressupõe:

| Assunto | Decisão |
|---|---|
| Hospedagem | VPS já contratada, Ubuntu LTS, **sem Docker instalado** |
| Domínio | Já registrado |
| E-mail | Provedor transacional, **Brevo** |
| Publicação | **Deploy contínuo**: mesclar na `main` sobe sozinho |
| Backup | Cópia diária **para fora da VPS** |
| Teto de entidades | **Subir antes de abrir**, com medição |
| Exportação no processo do site | **Corrigir nesta etapa** (bloco 5b) |
| Processos uvicorn | **Um só** |
| Monitoramento | Sonda externa gratuita na rota de saúde |
| Entrada pelo Google | **Dentro da etapa 5**, como bloco 5c |

## O que já existe, e não precisa ser construído

Levantado no código antes de desenhar, para o plano não gastar tarefa com o
que está pronto:

- **`deploy/Dockerfile`** — dois estágios, o node só no primeiro, imagem final
  sem `node_modules`, usuário sem privilégio, `PDFTODXF_DADOS=/dados`. **A
  imagem nunca foi construída**, porque não há `docker` nesta máquina: o
  primeiro `docker build` da vida do projeto acontece no 5a, e é razoável que
  ele falhe algumas vezes.
- **`web/api/enviador.py`** — **o caminho SMTP já está escrito**. Sem
  `PDFTODXF_SMTP_SERVIDOR` o e-mail vira arquivo em `dados/emails/`; com ele,
  vai por SMTP de verdade. O Brevo é **configuração, não código**.
- **`.github/workflows/ci.yml`** — três jobs verdes (Python, frontend, e2e). O
  deploy contínuo se apoia neles em vez de repetir testes.
- **`PDFTODXF_PROXIES`** — o serviço já sabe ler o IP real de trás de um proxy.
  Falta configurar.

E o que **não** existe, e é trabalho novo:

- **Rota de saúde.** Nenhuma. O deploy contínuo e a sonda dependem dela.
- **`docker-compose.yml` e `Caddyfile`.** A spec geral os nomeia; não existem.
- **Qualquer coisa de OAuth.** O 5c começa do zero.

## Bloco 5a — No ar

### Os dois contêineres

`docker-compose.yml` com `app` e `caddy` numa rede interna. **Só o Caddy
publica portas** (80 e 443); o app não expõe nada ao host, o que o torna
inalcançável exceto pelo proxy. É o que garante que o `PDFTODXF_PROXIES` seja
suficiente: não há caminho que chegue ao app sem passar pelo Caddy.

Três volumes nomeados, um por prazo de vida:

| Volume | Conteúdo | Prazo | Servido pela web |
|---|---|---|---|
| `dados` | PDFs enviados, cache, DXF gerados, e-mails em arquivo | 4 horas | parcialmente, por rota autenticada |
| `registros` | os `.md` com os textos das plantas | 1 ano | **nunca** |
| `banco` | SQLite de contas e cotas | permanente | não |

A limpeza dos dois primeiros já roda como tarefa periódica dentro do app.

**Um processo uvicorn, e é decisão consciente.** As cotas e o freio de login
foram escritos supondo um processo; a atomicidade com vários nunca foi medida
e está declarada como pendência desde o PR #9. Um processo mantém a promessa
de cota exata. Se a vazão apertar, a correção é mover a contagem para o SQLite
com transação — e aí sim medir a corrida.

### O Caddy

Um `Caddyfile` curto: o domínio, e o Caddy resolve certificado e renovação
sozinho pelo Let's Encrypt. Além disso:

- **compressão** das respostas (a spec já contava com ela);
- **corpo limitado a 100 MB**, que é o teto de arquivo para conta confirmada —
  recusar no proxy poupa o app de receber o que ele vai rejeitar;
- **cabeçalhos de segurança** usuais, incluindo HSTS;
- **`X-Forwarded-For`** para o app, casado com `PDFTODXF_PROXIES`.

**Sem limite de taxa no Caddy.** O Caddy padrão não tem, e teria de ser
compilado com plugin. O app já tem freio por IP na entrada (`PDFTODXF_TENTATIVAS_POR_IP`,
padrão 30) e cota por IP em tudo o mais. Fica registrado como possível defesa
em profundidade futura, não como requisito desta etapa.

### O `PDFTODXF_PROXIES`, e por que ele é item de primeira classe

Sem ele configurado, o app vê o IP do contêiner do Caddy em toda requisição.
Consequência: **todos os visitantes do mundo dividem o mesmo balde de cota** —
o primeiro esgota, e ninguém mais consegue converter nada. O freio de login por
IP vira um freio global. É a configuração cuja ausência transforma o serviço
público num serviço quebrado, e por isso ganha teste próprio no plano: uma
requisição com `X-Forwarded-For` forjado tem de ser atribuída ao IP certo, e o
cabeçalho vindo de fora do proxy tem de ser ignorado.

### Segredos

Um `.env` na VPS, com permissão fechada, fora do git e fora da imagem. O que
mora nele: a chave de assinatura da sessão (`PDFTODXF_SEGREDO`), as credenciais
do Brevo, a `PDFTODXF_URL_BASE` (que os links dos e-mails usam), o
`PDFTODXF_PROXIES`, e no 5c o segredo do cliente Google.

`PDFTODXF_SEGREDO` ausente já avisa no log ao subir — isso é da etapa 4 e
continua valendo. Em produção, o plano acrescenta a conferência de que o aviso
**não** aparece.

### E-mail pelo Brevo

Preencher as cinco variáveis de SMTP e publicar SPF, DKIM e DMARC no DNS do
domínio. O critério de pronto não é "o código chama o SMTP" — é **um e-mail de
confirmação chegando numa caixa de verdade, e não no spam**.

Enquanto as variáveis não existirem, o serviço continua gravando os e-mails em
arquivo, que é o comportamento de desenvolvimento. Vale reparar que isso é uma
falha silenciosa em produção: o cadastro funciona, ninguém recebe nada, e nada
grita. O plano confere o envio de verdade antes de dar o bloco por pronto.

### A rota de saúde

`GET /api/saude`, sem autenticação, respondendo 200 com pouca coisa: que o
banco abre para leitura e que a pasta de dados aceita escrita. Não expõe
versão de dependência, caminho de disco, nem contagem de usuários — é rota
pública, e o que ela conta, conta para qualquer um.

Ela existe para dois consumidores: o deploy contínuo, que espera por ela antes
de considerar a subida boa, e a sonda externa. **Uma rota que só responde
"200 ok" sem tocar em banco nem em disco não serviria** — ela ficaria verde com
o volume desmontado, que é justamente a falha que se quer pegar.

### Deploy contínuo, e a rede de segurança que ele exige

Mesclar na `main` sobe sozinho. Sem passo humano entre mesclar e ir ao ar, a
segurança tem de estar no automatismo:

1. O workflow existente roda a suíte inteira. **Falhou, não constrói.**
2. Constrói a imagem e publica no registry, com a tag do commit — nunca só
   `latest`, porque voltar atrás precisa de um alvo nomeável.
3. Conecta na VPS por SSH, puxa a imagem e recria os contêineres.
4. **Espera a rota de saúde responder.** Se não responder no prazo, volta para
   a tag anterior, sobe de novo, e **falha o job** — falhar em silêncio depois
   de reverter esconderia a quebra.

A VPS não compila nada: a imagem chega pronta. O `npm ci` e o `pip install`
ficam no runner, e não concorrem com o serviço.

**O primeiro deploy é manual**, por natureza — não há como instalar Docker e
criar o `.env` por workflow. O automatismo entra depois de o serviço estar de
pé pela primeira vez.

### Backup

Cópia diária do SQLite **para fora da VPS**, com retenção. Duas exigências:

- **`.backup` do SQLite, nunca `cp`.** Copiar o arquivo com escrita em curso
  produz um banco corrompido — e o defeito só aparece no dia da restauração.
- **A restauração é testada dentro do plano**, uma vez, num banco vazio.
  Backup que nunca foi restaurado é esperança, não backup.

Os outros dois volumes ficam de fora: os temporários morrem em 4 horas por
desenho, e os registros são reconstituíveis a partir de nada — mas se perdem
de vez. Fica registrado como decisão consciente, não como esquecimento: quem
quiser guardá-los acrescenta um segundo destino ao mesmo mecanismo.

### Preparação da VPS

Ubuntu LTS sem Docker. O plano instala Docker e Compose, fecha o firewall
deixando 22, 80 e 443, e cria a chave de deploy que o workflow vai usar — uma
chave só para isso, não a chave pessoal do usuário.

### Sonda

Uma sonda externa gratuita batendo na rota de saúde a cada poucos minutos, com
aviso por e-mail. É o mínimo que resolve o caso que importa: o serviço fora do
ar sem ninguém saber.

### Pronto do 5a

- O domínio responde em HTTPS com certificado válido, sem aviso de navegador.
- Um PDF sobe, converte e baixa como DXF, pela internet.
- Um cadastro manda e-mail de verdade, que chega e **não** cai no spam; o link
  confirma a conta.
- **O IP que o app registra é o do visitante, não o do Caddy** — a prova de que
  o `PDFTODXF_PROXIES` está certo. Confere-se lendo o IP gravado no registro de
  uma conversão feita de fora da VPS (do celular na rede móvel, por exemplo) e
  comparando com o IP público de verdade daquele aparelho.
- `/api/saude` responde 200, e responde erro com o volume de dados desmontado.
- Mesclar na `main` publica sozinho; uma imagem que não sobe é revertida
  sozinha, e o job fica vermelho.
- O backup roda, e uma restauração foi feita e conferida.
- A sonda avisa quando o serviço cai (testado derrubando de propósito).

## Bloco 5b — Aguenta o público

### Exportação assíncrona

Hoje `POST /api/jobs/{job}/pages/{p}/export` faz o trabalho inteiro no processo
do site: carrega o `cache.pickle` (medido em ~230 MB no teto atual) e escreve o
DXF ali mesmo. A extração ganhou processo separado e tetos de memória e CPU na
etapa 2 exatamente para uma planta monstruosa morrer sozinha sem levar o site
junto; a exportação não tem nada disso.

O desenho é **o mesmo da extração, reaproveitado**, não um mecanismo novo: o
POST enfileira e devolve na hora, o trabalho roda em processo separado com
tetos, a tela consulta o estado, e o download vem quando ficar pronto.

Duas coisas precisam sobreviver à mudança, e são o risco da tarefa:

- **O cache continua respondendo na hora.** Repetir uma combinação já gerada
  não enfileira e não consome cota. Isso é contrato da etapa 2 e da etapa 4, e
  é o que impede que baixar de novo o mesmo arquivo custe uma vaga.
- **A cota é reservada no pedido, não na entrega.** Senão dez pedidos
  enfileirados passam todos pela conferência antes de qualquer um consumir.

A tela já tem a barra indeterminada de "gerando DXF" e já sabe consultar o
estado da extração — a mudança reaproveita as duas coisas.

### O teto de entidades

Pendência desde 2026-08-08. Uma planta comum do acervo (`LAY-1028.26.00_REV 02`)
tem 2.332.566 entidades, **78% do teto de 3 milhões**. Não é caso extremo
inventado: é o que o usuário converte.

A medição roda **na VPS**, com plantas de tamanho crescente, achando onde a
memória e o tempo do worker estouram de verdade. O teto novo fica com margem
abaixo disso, e a mensagem de recusa passa a dizer o que significa e o que
fazer. Número escolhido por medição, não por chute — e por isso este bloco
espera o 5a.

### Pronto do 5b

- Uma exportação grande não derruba o site: ela morre sozinha e a tela recebe
  um erro que explica o que houve.
- Repetir uma combinação já gerada responde na hora e não consome cota.
- O teto novo tem um número medido por trás, e uma planta acima dele é recusada
  com mensagem honesta.

## Bloco 5c — Entrada pelo Google

Credenciais no Google Cloud, callback no domínio já com HTTPS, botão na caixa
de conta que a etapa 4 construiu.

**Conta criada pelo Google nasce confirmada**, porque o Google atesta o
endereço — é o que destrava a cota maior sem e-mail de confirmação.

**A vinculação é o ponto delicado.** A spec geral manda ligar à conta de mesmo
e-mail em vez de criar outra, e isso é o vetor clássico de sequestro: quem
consegue um `id_token` com o e-mail de outra pessoa, sem verificação, entra na
conta dela. O desenho **recusa a vinculação quando `email_verified` não vier
verdadeiro** — quem chegar assim segue pelo cadastro normal, com confirmação
por e-mail.

O segredo do cliente mora no `.env`, como os outros.

### Pronto do 5c

- Entrar pelo Google com e-mail novo cria conta já confirmada.
- Entrar pelo Google com o e-mail de uma conta que já existe **vincula**, não
  duplica.
- Um `id_token` sem `email_verified` não vincula a conta nenhuma.

## Fora de escopo, e por quê

- **Vários processos uvicorn.** Decidido: um só. Mexer nisso exige acertar a
  atomicidade da cota, que é tarefa própria.
- **Limite de taxa no Caddy.** Exigiria compilar com plugin; o app já freia por
  IP.
- **Backup dos registros e dos temporários.** Decisão consciente, explicada
  acima.
- **Planos pagos, painel administrativo, captcha, DWG, PDF escaneado,
  auto-escala.** Continuam fora, como na spec geral. A auto-escala é o próximo
  trabalho depois desta etapa, e tem achados próprios em
  `2026-08-08-auto-escala-e-medicao-achados.md`.

## Dívidas conhecidas que este desenho não fecha

Ficam registradas para não se perderem, e nenhuma bloqueia:

- Reabrir a caixa de nova senha depois de fechada exige uma affordance nova.
- O token de redefinição viaja no path do POST e entra nos logs de acesso.
- `ler_ficha` tem paciência no `open` mas não no `exists()`; `limpar()` não
  tolera `PermissionError` vindo dela.
- Contar páginas de um PDF não tem função pública no núcleo.
- A revisão independente das tarefas 4 a 7 da etapa 2 nunca aconteceu.
