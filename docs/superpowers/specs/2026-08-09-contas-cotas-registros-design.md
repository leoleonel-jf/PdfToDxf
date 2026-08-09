# Etapa 4 — contas, cotas e registros

Data: 2026-08-09

Este documento governa a etapa 4. Ele **substitui**, nos pontos em que diverge,
as seções "Contas e cotas de uso" e "Registro de conversões" da especificação
geral (`2026-08-01-pdftodxf-web-design.md`). As divergências estão todas
nomeadas na seção "O que muda em relação à spec geral", e nenhuma é acidental.

Escrito para bastar por si: quem for implementar não precisa da conversa que o
originou.

## Objetivo

Fechar o que falta para o serviço poder ficar de pé em público:

1. **Registros** — um `.md` por página extraída, com os textos da planta e a
   identificação de quem pediu, guardado por 1 ano.
2. **Cotas** — quanto cada um pode enviar e baixar numa janela de 2 horas, e
   como o visitante sem conta é contado.
3. **Contas** — cadastro por e-mail com senha, confirmação do endereço, sessão,
   e a cota maior que a conta destrava.
4. **Tela** — o canto da conta, o indicador de cota, as caixas de entrar e
   cadastrar, as cinco linhas de erro que a etapa 3 deixou explicitamente para
   cá, e a `privacidade.html` que o rodapé já referencia e que não existe.

**Nenhuma dependência nova.** `sqlite3`, `hmac`, `hashlib.scrypt`, `smtplib`,
`secrets` e `email.message` são todos biblioteca padrão. O
`web/requirements.txt` termina a etapa com exatamente as linhas que já tem, e
isso é item da definição de pronto.

## O que muda em relação à spec geral

| Ponto | Spec geral (2026-08-01) | Aqui | Por quê |
|---|---|---|---|
| Cota do visitante | 1 arquivo, 3 downloads | **5 arquivos, 15 downloads** | Decisão do usuário em 2026-08-09: 1 arquivo por 2 h trava a própria conferência e não deixa margem para quem está só experimentando |
| Cota do logado | 3 arquivos, 3 downloads cada | **15 arquivos, 45 downloads** | Mantém a proporção de 3× que dá sentido ao cadastro |
| Teto de tamanho | 20 MB / 100 MB | **10 MB / 100 MB** | Decisão do usuário; aperta o visitante e mantém o teto técnico existente para quem tem conta |
| Hash de senha | Argon2 (`argon2-cffi`) | **`hashlib.scrypt`** | Mesma classe de defesa, zero dependência nova, e este projeto trata a lista de dependências como item de "pronto" |
| Entrada pelo Google | Nesta etapa | **Etapa 5** | Exige credenciais do Google Cloud e uma URL de retorno pública, que só existem com o domínio da etapa 5 |
| Identidade anônima | Cookie **e** IP, o mais restritivo | **Cookie com a cota cheia; IP e impressão do navegador com teto folgado** | O mais restritivo faz dois colegas do mesmo escritório dividirem 5 arquivos; o teto folgado ainda impede o laço de limpar-cookie-e-repetir |
| Impressão do navegador | Não prevista | **Terceiro balde, com teto folgado** | Aba anônima e cookie limpo não mudam a impressão digital — é o furo que o cookie sozinho não tapa |

Tudo o mais da spec geral continua valendo: janela deslizante, repetir download
de graça, falha de extração não consome cota, teto de contas por IP por dia,
registros em volume próprio com prazo de 1 ano.

## Onde isto encosta no que já existe

O código da etapa 2 não é reescrito. Os pontos de contato são cinco, e só:

| Arquivo existente | O que ganha |
|---|---|
| `web/api/main.py` | `POST /api/jobs` reserva a vaga e usa o teto de MB do plano; `POST .../export` cobra o download; rotas novas de conta e de cota |
| `web/api/jobs.py` | `pedir_extracao` passa IP e conta adiante; `_quando_terminar` confirma ou solta a reserva; `_extrair_no_worker` grava o registro |
| `web/api/storage.py` | intocado |
| `web/api/exportacao.py` | intocado — já devolve se a exportação veio do cache, que é exatamente o que decide se cobra |
| `web/frontend/src/toolbar.ts`, `estados.ts` | o canto da conta e as cinco linhas de erro |

O worker **nunca** toca no banco. Ele recebe o que precisa por argumento e
grava um arquivo; toda escrita em SQLite acontece no processo do serviço. É a
mesma regra que a etapa 2 já usa para os tetos ("o processo pai continua sendo
o único dono da política") e evita a pergunta de o que fazer quando quatro
workers escrevem no mesmo banco ao mesmo tempo.

## Peças novas

```
web/api/
  db.py           SQLite: esquema, conexão, criação das tabelas
  identidade.py   resolve quem está pedindo — sessão, cookie anônimo, IP, impressão
  quotas.py       janela deslizante, reserva e confirmação, leitura das chaves
  auth.py         cadastro, confirmação, entrar, sair, redefinir senha
  enviador.py     manda e-mail: grava em arquivo no dev, SMTP em produção
  registros.py    monta o .md de uma página e expurga o que passou de 1 ano
web/frontend/src/
  conta.ts        caixas de entrar e cadastrar, canto da conta, cota restante
  impressao.ts    coleta os sinais do navegador e manda só o hash
  privacidade.html
```

Cada uma tem um trabalho só e uma fronteira que dá para descrever numa frase:
`identidade.py` responde "quem é"; `quotas.py` responde "pode?"; `auth.py`
responde "é mesmo quem diz ser"; `registros.py` escreve um arquivo e não sabe
nada de conta nem de cota.

## Identidade

`identidade.py` resolve uma vez por requisição e devolve um objeto com o tipo e
os baldes que aquela requisição consome.

### Logado

Sessão assinada válida → **um balde só**, `usuario:<id>`, com a cota de logado.
IP e impressão não são consultados: a conta já é a identidade.

### Visitante

Três baldes, com tetos diferentes:

| Balde | Chave | Cota de arquivos | Cota de downloads |
|---|---|---|---|
| `cookie` | valor aleatório assinado, 1 ano | 5 | 15 |
| `ip` | `hmac(segredo, ip)` | 20 (5 × folga 4) | 60 |
| `impressao` | `hmac(segredo, hash do navegador)` | 20 | 60 |

O pedido passa **se os três couberem**, e o consumo é gravado **nos três**. A
mensagem de recusa é a mesma nos três casos — dizer qual balde estourou seria
contar a quem tenta burlar exatamente o que ele precisa saber.

**Impressão ausente não bloqueia.** Navegador com JS desligado, extensão de
privacidade, cliente que não manda o cabeçalho: aquele balde simplesmente não
entra na conta. Quem escolhe se proteger fica com a cota do cookie e do IP, que
é a cota anunciada.

### O IP

Vem do `X-Forwarded-For`, contado **da direita para a esquerda**, pulando tantos
endereços quantos `PDFTODXF_PROXIES` disser. O padrão é `0`, que significa "não
confie no cabeçalho, use o endereço da conexão" — o certo em desenvolvimento.
Na VPS, com o Caddy na frente, o valor é `1`.

Sem esse contador, qualquer um manda `X-Forwarded-For: 1.2.3.4` e a cota do IP
vira decorativa. Confiar no cabeçalho inteiro é o erro clássico aqui, e ele é
silencioso: tudo funciona, só não protege.

### A impressão do navegador

`impressao.ts` monta uma string com sinais estáveis dentro de uma janela de duas
horas — `User-Agent`, idioma, resolução e profundidade de cor da tela, fuso
horário, número de núcleos, e um hash do desenho de um canvas 2D — calcula o
SHA-256 dela e manda **só o hash**, em `X-Impressao`, como 64 caracteres
hexadecimais. Qualquer outro formato é ignorado sem erro.

Os sinais crus **nunca saem do navegador**. O servidor aplica `hmac` com o
segredo antes de guardar, então nem o hash do cliente aparece no banco.

Duas coisas que isto compra, e vale escrever para ninguém esperar mais: aba
anônima e cookie apagado **mantêm** a mesma impressão, que é o caso comum de
quem quer mais cota; e trocar de navegador, de máquina ou usar um bloqueador
muda tudo, o que este desenho aceita — por isso a impressão é um teto folgado, e
não a identidade principal.

## Cotas

### A tabela

Um registro por consumo, com a hora. A cota disponível é o limite menos o que
foi consumido na janela — não existe virada em horário fixo.

```
consumo(id, balde, tipo, estado, quando, referencia)
  tipo       'arquivo' | 'download'
  estado     'reservado' | 'confirmado'
  referencia job_id, ou "job_id:chave" da exportação
```

Contar é `SELECT count(*) WHERE balde=? AND tipo=? AND quando > agora - janela`,
com índice em `(balde, tipo, quando)`. "Quando libera" é a linha mais antiga
dentro da janela, mais a janela.

### Reserva e confirmação

A spec geral manda que PDF sem vetores e worker morto por recurso **não**
consumam cota. Isso obriga a separar reservar de confirmar:

1. **`POST /api/jobs`** reserva uma vaga de `arquivo` em cada balde, com
   `referencia = job_id`, **antes** de começar a gravar o PDF. Se não couber, a
   resposta é 429 e nenhum byte é recebido.
2. **A primeira página que termina bem** promove as reservas daquele `job_id` a
   `confirmado`.
3. **A primeira página que termina em erro** apaga as reservas daquele `job_id`
   — mas só se ainda estiverem em `reservado`. Uma vez confirmado, nada mais
   solta.

A transição é de mão única e idempotente, e é isso que faz o caso misto sair
certo: num documento em que a página 1 é escaneada e a página 2 tem vetores, a
página 1 solta e a página 2 cobra; na ordem inversa, a página 2 confirma e a
página 1 não desfaz.

**Reserva nunca confirmada continua contando** até sair da janela. Quem envia e
fecha a aba consumiu banda e disco do servidor, e não há por que devolver a
vaga. Não existe varredura de reserva órfã: a janela deslizante já é o prazo.

### Downloads

Cobrados no `POST .../export`, e **só quando a combinação é inédita**.
Consequência desejada: repetir a mesma página, escala, unidade e opções sai de
graça, então conexão que cai, clique duplicado e download perdido não custam
nada.

A ordem importa e é esta: **calcula a chave da combinação, olha se o arquivo já
existe, e só então consulta a cota.** Combinação já gerada nem chega a perguntar
se há vaga. Gerar primeiro e cobrar depois faria uma planta grande queimar CPU
para terminar em 429; consultar a cota primeiro faria uma reexportação ser
recusada de quem está sem vaga, contrariando a promessa de que repetir é livre.

O `GET /api/download/...` nunca cobra. Ele só entrega um arquivo que já foi pago
no export — e é ele que o navegador repete quando a transferência falha.

### O que não consome nada

Escolher página, extrair, baixar geometria, calibrar, ligar e desligar layers,
mexer nas opções, ver a estimativa. Só enviar e gerar uma exportação inédita
contam.

## Contas

Só e-mail com senha nesta etapa. A entrada pelo Google fica para a etapa 5,
quando houver domínio e credenciais.

### Cadastro e confirmação

- A senha vira `scrypt$n$r$p$sal$hash`, tudo em base64, com **os parâmetros
  gravados junto**. Endurecer os custos depois não invalida as senhas
  existentes: quem entra com um hash de parâmetros antigos é reescrito com os
  novos naquele momento.
- O e-mail é guardado em minúsculas e é único.
- Um token de confirmação é gerado com `secrets.token_urlsafe`, guardado como
  `hmac`, com prazo. O valor original só existe dentro do e-mail. Vazamento do
  banco não entrega tokens utilizáveis.
- **Conta sem o endereço confirmado tem cota de visitante.** É o que faz a
  confirmação valer alguma coisa, e é o que a spec geral já dizia.

**Cadastro com e-mail já existente responde exatamente como o cadastro novo**, e
manda ao dono do endereço um aviso ("alguém tentou criar conta com este e-mail;
se foi você, entre por aqui") em vez do link. Sem isso, o formulário de cadastro
vira uma sonda para descobrir quem tem conta no serviço.

Pela mesma razão, a recusa de login não distingue "e-mail não existe" de "senha
errada", e o caminho do e-mail inexistente executa um `scrypt` de mentira, para
que o tempo de resposta não conte a diferença.

### Sessão

Cookie assinado com `hmac`, carregando `usuario_id`, hora de emissão e prazo.
`HttpOnly`, `SameSite=Lax`, `Secure` quando a origem é HTTPS. Renovado quando
passa da metade do prazo. **Sem tabela de sessões** — para um serviço com esta
escala, o cookie assinado basta, e trocar o segredo derruba todas as sessões,
que é o botão de emergência que se quer ter.

### Redefinição de senha

Mesmo mecanismo de token do cadastro, com prazo curto. Pedir redefinição para um
e-mail inexistente responde igual a pedir para um existente.

### Teto de contas por IP

`PDFTODXF_CONTAS_POR_IP_DIA`, padrão 5. O IP é guardado como `hmac` na linha do
usuário, e a conta do dia é feita sobre essa coluna. Sem isso, fabricar contas
em série multiplica a cota sem esforço.

## Registros

`registros.py` monta o texto e grava; ele não sabe o que é conta nem cota.

### Onde roda

Dentro do worker, no fim de `_extrair_no_worker`, junto com o `classify()`. Não
depende de o usuário chegar a exportar. O worker recebe por argumento o que
precisa e que ele não tem como saber: pasta dos registros, IP, identificador da
conta (vazio para visitante), nome original do PDF, tamanho em bytes e `job_id`.
O tempo de extração é medido ali dentro.

Gravar no worker, e não no processo pai, evita mandar todos os `TextItem` de
volta pela fronteira de processo só para escrevê-los num arquivo.

**Falha ao gravar o registro não derruba a extração.** Ela é registrada no log e
a página continua ficando pronta. O registro serve à transparência; perder um
não pode custar ao usuário a planta que ele veio converter.

### Nome do arquivo

`{ip}-{nome-do-pdf}-p{pagina}-{timestamp}.md`

- `ip` com `.` e `:` trocados por `_`
- `nome-do-pdf` sem extensão, só letras, números, hífen e sublinhado, truncado
  em 60 caracteres
- `pagina` começando em 1
- `timestamp` `YYYYMMDD-HHMMSS` em UTC

Colisão ganha sufixo numérico. O caminho final é **sempre** conferido contra a
pasta de registros depois de resolvido, e não antes: um nome com `../` ou com
barras é higienizado, e a conferência final é a rede de segurança de quem
esqueceu um caso.

### Conteúdo

Frontmatter YAML com IP, conta, nome original, página, data e hora, `job_id`,
tamanho do PDF em bytes e tempo de extração em segundos. Corpo com os textos da
planta em tabela (texto, posição, altura, rotação, na ordem em que o extrator os
encontrou), os layers com a contagem de cada um, a contagem por tipo de
entidade, e as dimensões da folha em pontos e em mm com os limites do desenho.

Geometria não entra — só texto e números agregados.

### Prazo e isolamento

Pasta própria, vinda de `PDFTODXF_REGISTROS`, **fora** da pasta dos arquivos
temporários e nunca servida pela web. Expurgo de 1 ano na mesma limpeza
periódica que já roda de 10 em 10 minutos.

> **O IP aqui é o real, não o hash.** Parece contradizer a tabela de cotas, que
> guarda `hmac`, e não contradiz: a cota só precisa saber "é o mesmo?", e o
> registro existe justamente para ser rastreável. Os dois usos são declarados na
> página de privacidade, com prazos diferentes — 2 horas e 1 ano.

## Rotas

Novas:

| Rota | Efeito |
|---|---|
| `POST /api/auth/registro` | Cria a conta e dispara o link de confirmação |
| `GET /api/auth/confirmar/{token}` | Confirma o endereço e redireciona para a tela |
| `POST /api/auth/entrar` | Entra por e-mail e senha |
| `POST /api/auth/sair` | Encerra a sessão |
| `POST /api/auth/senha` | Pede a redefinição |
| `POST /api/auth/senha/{token}` | Conclui a redefinição |
| `GET /api/cota` | Arquivos e downloads restantes, e quando a próxima vaga libera |

Alteradas:

| Rota | O que muda |
|---|---|
| `POST /api/jobs` | Resolve identidade, reserva a vaga (429 se não couber), aplica o teto de MB do plano |
| `POST /api/jobs/{id}/pages/{n}` | Passa IP e conta para o worker, para o registro |
| `POST /api/jobs/{id}/pages/{n}/export` | Cobra o download quando a combinação é inédita (429 se não couber) |

### Corpo das recusas

Recusa de cota é **429** com `{"detail": ..., "codigo": ..., "libera_em": ...}`,
onde `codigo` é `cota_arquivos` ou `cota_downloads` e `libera_em` é o instante
em que a próxima vaga abre. Arquivo acima do teto do plano é **413** com
`codigo: "tamanho"` e o teto em bytes, para a tela poder dizer o número certo
sem tê-lo escrito em dois lugares.

## Banco

SQLite num arquivo só, em `PDFTODXF_BANCO` (padrão `dados/contas.db`), com WAL
ligado. As tabelas são criadas na subida se não existirem.

```sql
usuarios(id, email, senha, confirmado_em, criado_em, criado_de)
tokens(valor, tipo, usuario, expira_em, usado_em)
consumo(id, balde, tipo, estado, quando, referencia)
```

`usuarios.email` é único; `usuarios.senha` guarda o hash com os parâmetros;
`usuarios.criado_de` é o `hmac` do IP de criação; `tokens.valor` é o `hmac` do
token. Índices em `consumo(balde, tipo, quando)` e `consumo(referencia, estado)`.

As rotas do FastAPI deste projeto são síncronas e rodam num pool de threads,
então a conexão é por thread, com `check_same_thread=False` fora de cogitação —
uma conexão por thread, criada sob demanda. Escritas curtas e WAL bastam para
esta escala; se um dia não bastarem, o problema aparece como `database is
locked` e não como corrupção.

A limpeza periódica também apaga do banco: `consumo` com mais de 24 horas e
`tokens` vencidos.

## Configuração

`0` significa **sem limite** nas chaves de cota. Chave ausente cai no padrão da
tabela — e o padrão é seguro, não é ilimitado.

| Chave | Padrão | O que é |
|---|---|---|
| `PDFTODXF_COTA_ARQUIVOS` | 5 | arquivos por janela, visitante |
| `PDFTODXF_COTA_DOWNLOADS` | 15 | exportações inéditas por janela, visitante |
| `PDFTODXF_COTA_MB` | 10 | teto de tamanho do PDF, visitante |
| `PDFTODXF_COTA_ARQUIVOS_LOGADO` | 15 | |
| `PDFTODXF_COTA_DOWNLOADS_LOGADO` | 45 | |
| `PDFTODXF_COTA_MB_LOGADO` | 100 | nunca acima de `limits.TETO_PDF_BYTES` |
| `PDFTODXF_COTA_JANELA_H` | 2 | tamanho da janela, em horas — **uma só, vale para visitante e logado** |
| `PDFTODXF_COTA_FOLGA` | 4 | multiplicador dos baldes de IP e de impressão |
| `PDFTODXF_CONTAS_POR_IP_DIA` | 5 | |
| `PDFTODXF_PROXIES` | 0 | proxies confiáveis à frente; 1 na VPS |
| `PDFTODXF_SEGREDO` | aleatório por subida | chave dos `hmac` e das sessões |
| `PDFTODXF_BANCO` | `dados/contas.db` | |
| `PDFTODXF_REGISTROS` | `registros` | |
| `PDFTODXF_URL_BASE` | `http://localhost:8000` | base dos links de e-mail |
| `PDFTODXF_SMTP_*` | ausente | servidor, porta, usuário, senha, remetente |

**`PDFTODXF_SEGREDO` ausente gera um segredo aleatório na subida e avisa no
log.** Isso derruba as sessões a cada reinício, o que atrapalha em produção e é
irrelevante em desenvolvimento — mas nunca gera um serviço com segredo fixo
conhecido, que é o modo de falhar que importa.

> **Trocar o segredo faz mais do que derrubar as sessões.** Ele é a chave dos
> `hmac` que formam `consumo.balde` e `usuarios.criado_de`, então a troca também
> zera todas as cotas de visitante em andamento e a contagem de contas por IP do
> dia. Nenhum dado se perde e nada quebra — as linhas antigas simplesmente
> deixam de casar e saem na limpeza de 24 horas. Vale saber antes de girar a
> chave num pico de uso.

Sem `PDFTODXF_SMTP_*`, o enviador grava o e-mail num arquivo em
`dados/emails/`. É o que permite confirmar uma conta à mão em desenvolvimento e
testar o fluxo inteiro sem servidor de e-mail nenhum.

## Tela

- **Canto direito da faixa 1:** a cota restante ("3 de 5 arquivos · libera às
  14h20") e o botão **Entrar**, ou o e-mail da conta com a opção de sair.
- **Caixas de entrar e cadastrar**, no CSS próprio que já existe. Sem
  biblioteca.
- **As cinco linhas de erro** que o desenho da etapa 3 listou e deixou para cá:
  cota de arquivos esgotada (oferecendo o cadastro ao visitante), cota de
  downloads esgotada (lembrando que repetir uma exportação já feita é livre),
  arquivo acima do teto do plano — mostrado **antes** de o envio começar, pelo
  tamanho que o navegador informa —, trabalho expirado, e conta ainda não
  confirmada.
- **`privacidade.html`**, que o rodapé já referencia: o que é guardado (textos
  das plantas e IP por 1 ano; hash do cookie, do IP e da impressão do navegador
  por 2 horas), por quê, por quanto tempo, e como pedir a remoção.
- **`impressao.ts`**, que coleta os sinais e manda o hash no cabeçalho.

## Testes

No padrão do projeto: funções com `assert` e bloco `if __name__ == "__main__"`,
sem pytest.

**Cotas.** Visitante envia 5 arquivos e é barrado no sexto; baixa 15 combinações
inéditas e é barrado na décima sexta. Limpar o cookie não devolve cota, porque
os baldes de IP e de impressão continuam contando. Um sexto envio de um IP com
cinco cookies diferentes passa (folga de 4×) e o vigésimo primeiro não. Repetir
a mesma combinação de página, escala, unidade e opções não consome; mudar
qualquer campo consome. PDF sem vetores, planta acima do teto de entidades e
worker morto por recurso soltam a reserva. Uma página boa depois de uma página
ruim confirma mesmo assim, e uma página ruim depois de uma boa não desfaz.
Navegar, calibrar e alternar opções não consomem nada. A janela desliza: um
consumo de 2 h e 1 s atrás não conta mais. Chave em `0` não limita; chave
ausente cai no padrão; `PDFTODXF_COTA_MB_LOGADO` acima do teto técnico é
truncado.

**Contas.** PDF de 40 MB é recusado ao visitante e aceito ao logado, e a recusa
carrega o teto em bytes. Acima de 100 MB é recusado para todos. Conta sem
confirmar fica com cota de visitante e passa à cota cheia depois de confirmar. A
senha nunca aparece em texto no banco. Cadastro com e-mail já existente responde
igual ao cadastro novo. Login com e-mail inexistente e login com senha errada
devolvem a mesma coisa. Token de confirmação vencido é recusado, e token usado
não serve duas vezes. O teto de contas por IP por dia barra a sexta. Trocar o
segredo invalida as sessões emitidas antes.

**Identidade.** `X-Forwarded-For` forjado é ignorado com `PDFTODXF_PROXIES=0`, e
respeitado na posição certa com `1`. `X-Impressao` malformado é ignorado sem
erro e sem bloquear. Ausência de impressão não impede o envio.

**Registros.** A extração de um PDF sintético gera o `.md` esperado, com todos os
textos da planta presentes. Um nome com `../` e barras é higienizado e o arquivo
não escapa da pasta. Dois envios do mesmo arquivo pelo mesmo IP no mesmo segundo
não se sobrescrevem. Registro com mais de 1 ano é apagado pelo expurgo e o mais
novo permanece. **Nenhuma rota do serviço alcança a pasta de registros** — o
teste tenta pelos caminhos óbvios e espera 404. Falha ao gravar o registro não
impede a página de ficar pronta.

## Ordem de implementação

Registros primeiro, porque não dependem de conta nem de cota e fecham sozinhos:

| # | Tarefa |
|---|---|
| 1 | `registros.py`: monta o `.md`, higieniza o nome, resolve colisão |
| 2 | Liga o registro ao worker e o expurgo de 1 ano à limpeza periódica |
| 3 | `db.py`: esquema, conexão por thread, criação na subida |
| 4 | `identidade.py`: cookie anônimo, IP com proxies, impressão |
| 5 | `quotas.py`: janela deslizante, reserva, confirmação, chaves |
| 6 | Liga a cota ao envio e à exportação, com as recusas 429 e 413 |
| 7 | `enviador.py` e o cadastro com confirmação |
| 8 | Entrar, sair e a sessão em cookie assinado |
| 9 | Redefinição de senha e o teto de contas por IP |
| 10 | `GET /api/cota` |
| 11 | Tela: canto da conta, caixas de entrar e cadastrar, cota restante |
| 12 | Tela: as cinco linhas de erro, `privacidade.html`, `impressao.ts` |

## Fora de escopo

- Entrada pelo Google (etapa 5, com o domínio)
- Planos pagos, cobrança e cotas compradas
- Painel administrativo de usuários
- Verificação anti-robô
- Alterar e-mail de uma conta existente, e apagar a própria conta pela tela — a
  remoção é por pedido, como a página de privacidade explica

## Riscos e limites aceitos

- **A impressão do navegador colide.** Vinte notebooks de imagem corporativa
  idêntica geram a mesma. Por isso ela é teto folgado, e não identidade — a
  colisão custa cota a quem compartilha máquina e IP, e o teto de 4× é o que dá
  a folga para isso não doer.
- **Quem quiser burlar, burla.** Trocar de navegador, de máquina ou de rede
  zera os três baldes. O desenho protege contra o esforço casual, que é o que
  existe em volume; contra esforço deliberado, só uma conta obrigatória
  protegeria, e isso contraria o objetivo de o serviço ser aberto.
- **Reserva não confirmada custa uma vaga.** Enviar e fechar a aba consome, e
  não devolve até a janela deslizar. É escolha, não descuido: o servidor gastou
  banda e disco de qualquer jeito.
- **Coletar impressão do navegador é dado pessoal sob a LGPD.** Fica declarado
  na `privacidade.html`, guardado só como `hmac` e por 2 horas. Se o custo
  jurídico pesar mais que o benefício, apagar o balde `impressao` é remover uma
  chamada — a cota continua funcionando com cookie e IP.
- **A exportação continua rodando no processo do site**, dívida herdada da etapa
  2 e não resolvida aqui. A cota limita quantas exportações acontecem, o que
  reduz a exposição, mas não a elimina.
