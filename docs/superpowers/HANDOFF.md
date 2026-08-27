# Handoff — versão web do PdfToDxf

Estado em 2026-08-27. Leia isto primeiro ao retomar em sessão nova.

> ## Se o pedido foi só "continuar", faça isto
>
> **A questão do ×100 está encerrada** (2026-08-21) e não é mais o primeiro
> passo — o usuário rodou o teste no AutoCAD e o `DIST` deu **6,06** na cota que
> mostra 606. Era o `DIMLFAC`. **O app está certo; não há nada a corrigir.**
> Detalhe logo abaixo, em "A questão do ×100, encerrada".
>
> **A etapa 4 está completa.** As tarefas 1 a 12 estão feitas: os seis PRs
> (#4 a #9) foram mesclados em 2026-08-26, e a tarefa 12 está no **PR #10**
> (branch `etapa4-erros-e-privacidade`), revisado, com bateria verde e
> aprovado para merge — falta só o usuário mesclar. **Leia "Onde a etapa 4
> parou" logo abaixo** para o estado, a lista ordenada e as dívidas; depois
> do PR #10, o próximo trabalho de sessão é planejar a etapa 5.
>
> **Para subir a tela**, quando ele pedir ou quando você precisar conferir algo:
> existe `.claude/launch.json` com dois alvos. Use a ferramenta de preview, não
> o Bash: `preview_start` com `pdftodxf-api` e depois com `pdftodxf-web`. A tela
> abre em `http://localhost:5173` — com `localhost`, **nunca** `127.0.0.1`, que
> o Vite recusa. Os servidores caem quando a sessão anterior encerra; se o
> usuário disser "deu erro" com `ERR_CONNECTION_REFUSED`, é isso, e a correção é
> subir os dois de novo.
>
> **Três coisas que não são para você fazer nem esperar:**
>
> - O **PR #3 já foi mesclado** em 2026-08-11, com commit de mescla (`0040dfc`),
>   levando as etapas 3, 3.5 e 3.6 para a `main`. Não há PR aberto. O branch
>   `frontend-canvas` foi preservado, como os outros branches de etapa.
> - A **imagem Docker** não foi construída porque o `docker` não existe nesta
>   máquina. Se o usuário instalar, é um comando; até lá, não tente.
> - Os itens que "dependem de você" em "O que falta" são do humano. Não os
>   execute por conta própria.
>
> As etapas 3, 3.5 e 3.6 estão prontas: **2174 testes de unidade, 21 de ponta a
> ponta**, 15 arquivos de teste Python, e **integração contínua verde no
> GitHub**. O desenho do canvas foi **refeito no meio da etapa 3**, depois de
> três medições derrubarem três arquiteturas — se for mexer no canvas, leia
> `web/frontend/medicao/RESULTADO.md` antes.
>
> **A conferência na tela já aconteceu, e valeu o que se esperava:** o usuário
> abriu com planta real em 2026-08-10 e achou três defeitos que teste nenhum
> pegava — as setinhas do campo de mm cobrindo o texto e sem casa decimal, a
> calibração virando `NaN` quando a medida era digitada com vírgula, e os
> pontos clicados não aparecendo na tela. **Os três estão corrigidos.**
>
> **A lição mais cara da etapa 3.5, para não se repetir:** o plano mandou
> reimplementar à mão duas conversões que o projeto já tinha prontas e testadas
> (`escalaPorEscalaDePlotagem` e `corDeInteiro`), e errou as duas — o DXF sairia
> com 11,34 m onde a parede tem 10,00 m. Sete revisões por tarefa não pegaram,
> porque cada uma só via o seu pedaço; a revisão final do branch pegou. **Antes
> de escrever qualquer conversão, procure se ela já existe no núcleo.**

## Onde a etapa 4 parou (2026-08-27)

O plano é `docs/superpowers/plans/2026-08-21-contas-cotas-registros.md`; o
ledger da execução é `.superpowers/sdd/progress-etapa4.md` (fora do git, só
nesta máquina, e é onde está o detalhe de cada tarefa). **As tarefas 1 a 12
estão completas.** Os seis PRs (#4 a #9) foram mesclados na `main` em
2026-08-26, as branches locais órfãs (`contas-cotas-registros` e as três
`claude/*`) foram apagadas e os worktrees removidos.

**A tarefa 12 foi executada em 2026-08-27**, no branch
`etapa4-erros-e-privacidade` ([PR #10](https://github.com/leoleonel-jf/PdfToDxf/pull/10)):
as cinco linhas de erro em `estados.ts`, `impressao.ts` (hash do navegador no
cabeçalho `X-Impressao`), `privacidade.html`, a recusa por tamanho antes do
envio, e o **passo 5c** — a caixa de nova senha para `/?senha=<token>`, o
aviso de `?confirmado=1`, e `acaoDaUrl` em `conta.ts` (`senha` ganha quando os
dois vêm juntos; a URL é limpa com `replaceState` preservando o resto da
query e o hash). O item **I1** (teste do `ErroDaApi.codigo`) foi coberto
antes de construir em cima, como pedido. Processo completo: implementador,
revisão por tarefa (2 Importantes achados e corrigidos — janela de abort no
`enviarPdf` e cobertura zero do `X-Impressao`), re-revisão, revisão final do
branch com triagem, rodada final de sete Menores, veredito **pronto para
merge**.

> **Bateria no topo do PR #10 (2026-08-27): 25/25 arquivos Python, 2199
> testes de frontend em 19 arquivos, build limpo, e2e 22/22 três vezes
> seguidas.** O worktree está limpo.

### O que fazer, nesta ordem

1. **Mesclar o [PR #10](https://github.com/leoleonel-jf/PdfToDxf/pull/10)** e
   conferir a bateria sobre a `main` mesclada.

2. **Decidir a dívida prioritária da revisão final:** as mensagens de
   `cota_arquivos` e `tamanho` dizem "com uma conta gratuita o limite sobe…"
   **também para quem já está logado** — conselho impossível de seguir. O
   texto veio verbatim do plano (passo 4 da tarefa 12) e o teste o exige, então
   mudar é decisão do usuário: exige passar o tipo da conta a `avisoDoErro` e
   ajustar o contrato do teste. Ver "Pendências abertas" abaixo.

3. **Planejar a etapa 5 — deploy.** A etapa 4 acabou; é o item 9 de "O que
   falta".

### As três sessões de fundo, encerradas e absorvidas

| Worktree | O que fez | Situação |
|---|---|---|
| `friendly-meninsky-f40d3f` | teste intermitente da limpeza periódica | **na `main`** (via PR #7) |
| `great-keller-c8dc41` | `PermissionError` na ficha sob carga | **na `main`** (rebaseado no PR #8) |
| `festive-wright-42fee4` | — | vazio, nada a trazer |

Branches e worktrees apagados em 2026-08-27.

O que a primeira corrigiu, porque o padrão se repete: o teste da limpeza
periódica dormia 0,3 s de relógio antes de cancelar a tarefa, e uma volta do
laço despacha quatro trabalhos em `asyncio.to_thread`. Numa máquina ocupada os
dois primeiros já estouravam o prazo. Sob carga de 40 processos, o A/B deu 5/10
antes e 10/10 depois. **Espere a condição, nunca um tempo de relógio.**

### Pendências abertas da etapa 4

Nenhuma bloqueia o merge do PR #10. Todas vêm do ledger, menos a última seção.

**Dívidas registradas na revisão final da tarefa 12 (2026-08-27):**

- **Prioritária, decisão do usuário:** mensagens de `cota_arquivos` e
  `tamanho` erradas para usuário logado (item 2 de "O que fazer" acima).
- `lerCota` não manda `X-Impressao`, então o saldo do canto ignora o balde da
  impressão: quando ele for o vinculante (cookie apagado, IP trocado), a tela
  mostra vaga e o envio leva 429.
- O token de redefinição fica irrecuperável se o usuário fechar a caixa
  `nova-senha` (a URL já foi limpa); o fallback "Esqueci a senha" existe e
  funciona.
- O token de senha viaja no path do `POST /api/auth/senha/{token}` e entra nos
  logs de acesso — desenho da rota (tarefa 9), não do frontend.
- A asserção negativa do teste do I1 passaria se `erroDaRecusa` nunca tocasse
  `codigo`; o teste positivo irmão cobre.

**Da tarefa 11 (tela)** — a revisão aprovou com ressalvas, tudo cobertura e UX:

- ~~**I1.** `ErroDaApi.codigo` sem teste.~~ **Fechado na tarefa 12**
  (`testes/api.test.ts`), antes de construir em cima, como pedido.
- **I2.** Erro no submit apaga os dois campos: senha errada faz o e-mail sumir
  junto.
- **I3.** `Escape` não fecha a caixa; sem `role="dialog"`; o foco não volta ao
  fechar.
- **I4.** `atualizarCota` sem guarda de "em voo": resposta velha pode
  sobrescrever a nova — o visitante aterrissando depois do login troca o e-mail
  de volta por "Entrar".
- **I5.** `horaDeLiberar` ignora `agora`: "libera às 14h20" continua na tela às
  15h.

**~~Para o usuário decidir~~ — decidido em 2026-08-26, e feito no PR #9:** não
havia freio de tentativas em `POST /api/auth/entrar`, e cada tentativa custava
um `scrypt` de ~110 ms e ~32 MB. O usuário escolheu **teto por IP no
aplicativo**, e não só na borda, para que a proteção não dependa de o serviço
estar inalcançável sem o Caddy. Implementado com a maquinaria de cota que já
existia, tipo `"tentativa"`, chave `PDFTODXF_TENTATIVAS_POR_IP` (padrão 30).

> **Se a etapa 5 acrescentar limite de taxa no Caddy, os dois convivem** — é
> defesa em profundidade, não duplicação. O que **não** foi medido é a
> atomicidade com mais de um processo `uvicorn`; está declarado no PR #9 e é
> item da etapa 5.

**Menores, detalhados no ledger:** o teste do `compare_digest` ainda passa se a
implementação chamar `compare_digest` e **descartar** o resultado, decidindo por
`==`; o comentário de `PISO_DE_SENHA_S` descreve uma thread por pedido que não
existe mais; trabalhador morto da fila de envio não é recriado; a guarda
`if linha else ""` de `GET /api/cota` não tem teste e a mutação sobrevive.

### Achado novo, não investigado: `test_api_cotas.py` sob carga

Apareceu por acidente em 2026-08-24, ao medir a bateria paralela. Isolado, o
arquivo dá 5/5; com 40 processos queimando CPU, falhou **1 de 6**:

```
PermissionError: [Errno 13] Permission denied:
  ...\pdftodxf-teste-<...>\<id>\ficha.json
```

É a mesma família que o `great-keller` atacou — a janela do `os.replace` na
troca atômica da ficha —, mas em **outro** arquivo de teste, e não sei se a
correção dele alcança este caminho. **Não peguei o traceback:** numa segunda
tentativa sob a mesma carga passou 8 de 8, e não insisti. Para reproduzir, suba
~40 processos de CPU e rode o arquivo em laço. **Confirme antes de corrigir**, e
comece conferindo se ele não sumiu sozinho depois de trazer o `great-keller`.

## Duas armadilhas de ambiente, para não perder tempo

**A porta 8000 pode estar ocupada por outro aplicativo do usuário.** Em
2026-08-11 havia um servidor `waitress` nela, redirecionando para `/login/` —
nada a ver com este projeto. O `playwright.config.ts` aponta para a 8000, então
`npm run e2e` fica esperando um servidor que nunca responde o que ele quer, e
morre com `Timed out waiting 60000ms from config.webServer`. **Não é defeito do
código.** Confira antes de investigar:

```
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/openapi.json
```

`200` é a nossa API; `404` ou um redirecionamento é outra coisa. Derrubar o
processo alheio **é decisão do usuário** — pergunte, não mate.

**O Vite precisa escutar nos dois endereços.** Por padrão ele sobe só em
`localhost` (IPv6) e recusa `127.0.0.1`, que é justamente onde o Playwright
procura. O `.claude/launch.json` já passa `--host` por causa disso, e com ele
tanto `http://localhost:5173` quanto `http://127.0.0.1:5173` funcionam.

## A questão do ×100, encerrada

> **Encerrada em 2026-08-21: era o `DIMLFAC`, e o app está certo.** O usuário
> rodou o teste da seção "A hipótese que falta testar" e o `DIST` mediu **6,06**
> entre as mesmas duas extremidades da cota que mostra 606. Como `DIST` não
> sofre `DIMLFAC` e a cota sofre, o fator 100 nasce no estilo de cota do desenho
> dele, não na nossa geometria. **Nenhuma correção de código.** O resto desta
> seção fica como registro do que foi medido, para não se remedir.

Não recomece a investigação — a cadeia inteira do app já foi medida, e está tudo
aqui.

### O sintoma

O usuário calibrou a planta real (`Input/LAY-1031.26.00_REV 00.pdf`) numa cota
de **6,06 m**, com a escala em **1:40** e a unidade em **m**, exportou, e o
AutoCAD mostrou **606,00** na mesma cota. Fator 100, que é metro→centímetro.
Ele confirmou que **não muda nada** escrever a medida com vírgula ou com ponto,
e que trocar m/cm/mm não altera o que ele vê.

### O que já foi medido, e fecha

| Trecho | Como foi medido | Resultado |
|---|---|---|
| Calibração por 2 cliques | Playwright na planta real, lendo a tela e o corpo do POST | mostra `1:23` e "8,13 mm reais", envia `escala 0,008128` + `"m"` — os três concordam |
| Campo "Escala 1:" | idem, com 1:50 | envia `0,017638` + `"m"` |
| Seletor de unidade | idem, as três | `0,0176` (m) · `1,7639` (cm) · `17,6389` (mm) — razão 1:100:1000, tamanho físico preservado |
| Cache da exportação | `web/api/exportacao.py::chave` | inclui escala **e** unidade; não há reentrega de arquivo errado |
| Escrita do DXF | `pdftodxf/dxf_writer.py::write_dxf` | coordenadas = `ponto × escala`; `$INSUNITS` = 6/5/4 conferido com o próprio ezdxf |
| A planta real, 1:40 em m | gerada pela API e medida com ezdxf | extensão **22,96 × 16,60 m** — ordem de grandeza certa para um prédio a 1:40 numa folha A2 (1684 × 1191 pt) |

Três arquivos de prova ficaram em `output/diag/`: `m.dxf`, `cm.dxf` e `mm.dxf`,
o mesmo desenho nas três unidades, mais `real-m.dxf`, a planta do usuário a 1:40
em metros. **São locais** — `output/` está no `.gitignore`, então não vieram do
repositório e podem não existir noutra máquina; regerá-los é um `curl` contra a
API, como descrito acima. Medidos com ezdxf, a mesma linha dá
`5,2917 m` · `529,1667 cm` · `5291,6667 mm`. O usuário mediu **outra** linha no
AutoCAD e obteve `529,17` · `52.916,67` · `529.166,67` — números diferentes dos
meus porque é outra linha, mas com **a mesma razão 1:100:1000**. Ou seja, a
conversão de unidade funciona, e o CAD dele não normaliza: mostra unidade crua.

### A hipótese que falta testar, e o teste

Se o arquivo tem 23 unidades de extensão e a cota mostra 606 sobre um vão de
6,06, quem multiplica por 100 é o AutoCAD. O suspeito nomeado é o **`DIMLFAC`**,
o fator de escala linear do estilo de cota — vale 100 em escritório que trabalha
em centímetro.

O teste separa os dois casos porque **`DIST` não sofre `DIMLFAC` e a cota
sofre**:

1. `DIMLFAC` na linha de comando → o valor.
2. `DIST` nas mesmas duas extremidades → o comprimento.

- `DIST` = **6,06** e cota = 606 → é o `DIMLFAC`. O app está certo, e não há
  nada a corrigir no código.
- `DIST` = **606** → a geometria está mesmo 100× e o defeito é nosso. Nesse
  caso **não procure nos trechos da tabela acima** — todos foram medidos e
  fecham. Comece pelo que não foi medido: o que o `extractor` devolve como
  coordenada (a suposição não verificada é que são pontos de PDF), e a
  `Vista`/`pontoDoPapel` do `canvas.ts` na conversão tela→papel.

## O projeto em uma frase

Transformar o PdfToDxf (app desktop Tkinter que converte plantas em PDF vetorial
para DXF em escala real) numa versão web pública, hospedada em VPS, com paridade
total de recursos. O app desktop continua existindo; as duas interfaces
compartilham o mesmo núcleo.

Documentos que governam o trabalho:

- **Especificação geral:** `docs/superpowers/specs/2026-08-01-pdftodxf-web-design.md`
- **Desenho da etapa 3:** `docs/superpowers/specs/2026-08-04-frontend-canvas-design.md`
- **Plano da etapa 1:** `docs/superpowers/plans/2026-08-01-nucleo-classify-select.md`
- **Plano da etapa 2:** `docs/superpowers/plans/2026-08-03-api-de-conversao.md`
- **Desenho da etapa 2.5:** `docs/superpowers/specs/2026-08-04-cli-design.md`
- **Plano da etapa 2.5:** `docs/superpowers/plans/2026-08-04-cli.md`
- **Plano da etapa 3:** `docs/superpowers/plans/2026-08-04-frontend-canvas.md`
- **Redesenho do canvas (2026-08-09), que substitui a arquitetura do desenho da
  etapa 3:** `docs/superpowers/specs/2026-08-09-canvas-redesenho-design.md`
- **Plano do redesenho:** `docs/superpowers/plans/2026-08-09-canvas-redesenhado.md`
  — é um *delta* sobre o plano de 2026-08-04, e a tabela no topo dele diz qual
  tarefa vem de qual documento
- **Medições que governam o canvas:** `web/frontend/medicao/RESULTADO.md`
- **Achados sobre auto-escala e medição:**
  `docs/superpowers/specs/2026-08-08-auto-escala-e-medicao-achados.md` — duas
  features futuras, decididas para **depois** da etapa 3. Não é spec; é o que se
  descobriu sondando uma planta real, e derruba premissas que parecem óbvias.

O projeto está dividido em 5 etapas: **1** núcleo, **2** API de conversão,
**3** frontend, **4** contas/cotas/registros, **5** deploy, mais uma **2.5**
curta que entrou depois: a linha de comando.

As etapas 1, 2, 2.5 e **3** estão planejadas e implementadas — a 3 com um passo
pendente, a imagem Docker. Todos os documentos foram escritos para bastar por
si: não é preciso resgatar a conversa que os originou.

> A etapa 3 é governada por **dois** documentos, e o segundo manda: o desenho de
> 2026-08-04 e o **redesenho de 2026-08-09**, que substituiu a arquitetura
> depois de a medição derrubá-la. O mesmo vale para os planos.

## Onde o código está

**Tudo está na `main` desde 2026-08-11**, quando o PR #3 foi mesclado com commit
de mescla (`0040dfc`), levando as etapas 3, 3.5 e 3.6. Antes dele, as etapas 1,
2 e 2.5 e a validação de entradas já tinham sido mescladas em cascata. A bateria
foi conferida **sobre o resultado da mescla**: 15 arquivos de teste Python,
2174 testes de frontend e build limpo. Os branches de etapa são **preservados**,
a pedido do usuário:

| Branch | Conteúdo | Situação |
|---|---|---|
| `main` | tudo, até a etapa 3.6 | **em dia** |
| `frontend-canvas` | etapas 3, 3.5 e 3.6 (PR #3) | mesclada, branch guardado |
| `nucleo-classify-select` | etapa 1 | mesclada, branch guardado |
| `api-de-conversao` | etapa 2 | mesclada, branch guardado |
| `linha-de-comando` | etapa 2.5 (PR #1) | mesclada, branch guardado |
| `entradas-tolerantes` | validação de entradas (PR #2) | mesclada, branch guardado |

> **Atenção, e foi decisão consciente:** a mesclagem aconteceu **sem** a revisão
> independente das tarefas 4 a 7 da etapa 2, que continua pendente (item 2 de "O
> que falta"). O código do formato binário está na `main` sem ter passado por um
> olhar de fora. Isso não some por estar mesclado — a etapa 3 vai escrever o
> leitor TypeScript em cima daquele formato, e é lá que um erro custa caro.

## O que está pronto

### Etapa 1 — núcleo `classify`/`select` (branch `nucleo-classify-select`)

Seis tarefas, todas implementadas e revisadas, mais uma revisão final do branch
cujos quatro achados importantes foram corrigidos.

`pdftodxf/optimize.py` foi dividido em duas fases:

- `classify(entities) -> EntityAttrs` — cara, roda uma vez no servidor. Resume
  cada entidade em números: `kind`, `layer_id`, `is_fill`, `length_um`
  (micrômetros de papel, inteiro), `dup_group`, `byte_cost`.
- `select(attrs, opts) -> list[bool]` — trivial, só comparações. **Será
  reescrita em TypeScript na etapa 3.**

A ideia central: o julgamento caro — quais segmentos são duplicatas entre si —
é feito uma vez, em Python, e vira um inteiro (`dup_group`). Assim o TypeScript
não precisa reimplementar algoritmo nenhum e não pode divergir.

`apply_filters()` foi removida. O app desktop usa o mesmo caminho.

**`tests/casos_select.json` é o contrato** que a implementação TypeScript terá
que obedecer: 1024 casos com tabelas de etiquetas, combinações de opções, a
máscara esperada e o `bytes_esperado`. Gerado por
`tests/gerar_casos_select.py`, verificado por `tests/test_casos_select.py`.
Regenerar é determinístico — se o `git diff` sujar, o comportamento mudou.

### Etapa 2 — API de conversão (branch `api-de-conversao`)

| Tarefa | O que faz | Situação |
|---|---|---|
| 1 | `length_um` inteiro no núcleo | pronta, revisada |
| 2 | serviço, envio do PDF, armazenamento | pronta, revisada |
| 3 | fila de extração em processo separado | pronta, revisada |
| 4 | empacotamento binário da geometria | pronta, sem revisão independente |
| 5 | divisão esqueleto/detalhe + rotas | pronta, sem revisão independente |
| 6 | exportação com cache por combinação | pronta, sem revisão independente |
| 7 | limpeza por prazo e cota de disco | pronta, sem revisão independente |

As sete tarefas estão feitas e a **definição de pronto da etapa 2 foi conferida
item a item**: os seis arquivos de teste novos passam junto dos quatro da etapa
1, o `requirements.txt` da raiz continua com três dependências, um PDF vetorial
sobe e volta como DXF válido inteiramente por HTTP, esqueleto e detalhe somados
reproduzem a extração, repetir uma exportação não gera arquivo novo, e os
trabalhos vencem em 4 horas com a cota apagando do mais antigo.

Arquivos existentes: `web/api/{__init__,limits,storage,jobs,packing,main}.py`,
`web/requirements.txt`, `tests/test_api_upload.py`, `tests/test_api_extracao.py`,
`tests/test_packing.py`, `tests/test_api_geometria.py`,
`tests/test_api_export.py`; e `web/api/exportacao.py`.

O formato binário da tarefa 4 enche cada seção até um múltiplo de 4. Isso não é
detalhe de gosto: `kind` e `is_fill` são uint8 e ocupam `n` bytes, então sem o
enchimento o `Uint32Array` da etapa 3 levantaria `RangeError` em qualquer página
cuja contagem fuja da tabuada do 4. A regra está no plano, junto da tabela.

### Etapa 2.5 — linha de comando (branch `linha-de-comando`)

Quatro tarefas, todas implementadas. `python -m pdftodxf` com dois comandos:
`converter` (grava o DXF) e `inspecionar` (descreve a planta sem gravar nada).
Arquivos novos: `pdftodxf/cli.py`, `pdftodxf/__main__.py`, `tests/test_cli.py`.

O que a etapa amarrou, além da conveniência:

- **As flags de compactação são exatamente os campos de `ExportOptions`**, e um
  teste falha se alguém acrescentar um campo sem a flag. A CLI é o terceiro
  lugar que nomeia as mesmas opções; sem essa amarra a divergência entraria em
  silêncio.
- **`dxf_writer.convert()` não existe mais.** Era a única função que gravava DXF
  sem passar por `classify`/`select`, ninguém a chamava, e um teste impede a
  volta dela.
- **A CLI só importa a superfície pública do núcleo**, verificado por um teste
  que lê o próprio `cli.py` com `ast`. A única exceção é o `fitz` para contar
  páginas — registrada na dívida abaixo, não escondida.

Dois defeitos apareceram ao rodar contra planta real, e foram corrigidos: o `≈`
da tabela de estimativa não cabe no cp1252 do console do Windows, e o
`except ValueError` que protegia páginas sem vetores engolia o
`UnicodeEncodeError` — que é subclasse de `ValueError` — e o exibia como "esta
página não tem desenho vetorial", com código de saída 0. Hoje só a extração fica
dentro do `try`, e o retrato roda fora dele.

### Etapa 3 — frontend (branch `frontend-canvas`, em andamento)

A medição derrubou a arquitetura do plano de 2026-08-04, o desenho foi refeito,
e a etapa passou a ser governada pelo plano de 2026-08-09 — **5 das 12 tarefas
dele estão prontas**, com 2086 testes verdes:

| Arquivo | O que faz |
|---|---|
| `select.ts`, `estimativa.ts`, `formato.ts` | espelhos do Python e o leitor do binário |
| `ordem.ts` | ordem por comprimento decrescente, radix estável |
| `canvas.ts` | vista papel↔tela e o traçado de um lote |
| `lista.ts` | a lista de desenho preparada por janela, retomável |
| `pintor.ts` | o laço de quadro: orçamento e quando preparar de novo |
| `api.ts` | cliente HTTP com recuo crescente e aborto por página |

A interface também está pronta: `gestos.ts`, `calibrate.ts`, `estados.ts`,
`estilo.css`, `toolbar.ts`, `main.ts`, a calibração com lupa, o Playwright de
ponta a ponta e os estáticos servidos pelo FastAPI. **Só a imagem Docker não foi
construída** — falta o `docker` na máquina.

**Três defeitos que só apareceram com planta real na tela**, e que nenhum teste
de unidade pegaria:

1. **O eixo Y estava sem inverter.** O extractor entrega Y para cima, padrão de
   CAD; o canvas tem Y para baixo. A prévia saía de cabeça para baixo, com todo
   texto invertido. A inversão entrou na `Vista` — é o mesmo que a prévia do
   desktop faz com `(H - p[1])`.
2. **`Path2D.arc()` liga o ponto atual ao início do arco com uma reta.** Como os
   caminhos são agrupados por (layer, cor), cada arco ficava amarrado ao fim da
   entidade anterior: a planta aparecia coberta de linhas atravessando, que
   mudavam a cada zoom. Hoje o arco é tesselado em segmentos, com o mesmo
   `sweep = (fim - início) % 360 or 360` do desktop.
3. **`display: grid` atropela o atributo `hidden`.** O painel de aviso ficava
   sempre visível e, tendo fundo escuro semitransparente, cobria a planta
   inteira. Consertado com `[hidden] { display: none !important; }`.

O terceiro foi pego pelo Playwright; os dois primeiros, pelo olho do usuário —
e é por isso que a conferência com planta real continua valendo mais do que
qualquer suíte.

**As constantes do desenho foram medidas e mudadas:** região de 8 px, teto 2,
folga 0,25 — o spec fixava 4 e 4 a partir de um protótipo, e medido com a
implementação de verdade aquele par dava 143 ms por quadro contra 31 ms deste.
**Nenhuma combinação fecha o alvo de 33 ms nos três zooms**, e o motivo está no
RESULTADO: o custo do quadro segue a **tinta rasterizada**, não a contagem de
entidades, e os três parâmetros só controlam contagem. O ajuste fino, e a
decisão sobre um cache de imagem para o pan, esperam **planta real na tela** —
é quando a qualidade do desenho pode ser vista em vez de suposta.

**Leia `docs/superpowers/specs/2026-08-09-canvas-redesenho-design.md`** — ele
substitui a seção de arquitetura do desenho de 2026-08-04 e é o que governa
daqui para a frente. Em uma frase: nada proporcional ao número de entidades
pode acontecer a cada quadro; a lista de desenho é preparada uma vez, com teto
por região de papel escolhendo os mais longos, e pan e zoom só re-traçam.

| Tarefa | O que faz | Situação |
|---|---|---|
| 1 | andaime do Vite e a medição do custo | pronta |
| 2 | `select.ts` contra os 1024 casos | pronta |
| 3 | `estimativa.ts`, mesmo contrato | pronta |
| 4 | `formato.ts`, leitor do binário | pronta |
| 5 | `intercalar()` e o achado do dedup | pronta |
| 6 a 15 | worker, canvas, calibração, tela | **paradas** |

**As três medições, e o que cada uma derrubou** — detalhe em
`web/frontend/medicao/RESULTADO.md`:

- O `select()` sobre 3 milhões de entidades custa **~12 ms**. Cabe folgado num
  quadro de 16 ms, na thread principal, a cada clique numa opção.
- Reconstruir os `Path2D` no pior caso custa **de 300 a 840 ms**.
- `Path2D` é API de DOM e **não existe dentro de um Web Worker**. Ou seja: a
  arquitetura de duas threads move para fora os 12 ms e deixa dentro os 800 ms.
  O worker das tarefas 5 e 6 do plano protege a interface de uma pausa que não
  acontece.
- **Traçar** 3 milhões custa de 750 a 1290 ms **por quadro**, e pan e zoom não
  reconstroem nada — o custo dominante é por quadro, não por clique. Nem 500
  mil dão folga: 173 a 341 ms.
- Traçar 57 mil de uma **lista pronta** custa **15 ms**; selecionar esses mesmos
  57 mil varrendo 3 milhões a cada quadro custa 500. Vinte vezes, com o mesmo
  desenho na tela. É esta medida que governa o desenho novo — e ela derrubou
  também a grade espacial, que chegou a ser construída e medida.

Duas correções na própria medição, ambas registradas no RESULTADO, porque sem
elas a conclusão sairia invertida: recarregar a página **não** aquece o JIT
(cada carga é um contexto novo, e a mesma fase variou por um fator de dois), e o
cenário do plano só media o caso **já deduplicado** — 500 mil sobreviventes,
47–104 ms, abaixo do limiar de 200 ms do próprio plano. O padrão da tela é *sem*
dedup, e é aí que as 3 milhões chegam ao canvas.

O que existe de código, tudo espelho do Python e válido em qualquer arquitetura:
`web/frontend/src/{select,estimativa,formato}.ts`, os testes em
`web/frontend/testes/`, e as duas fixtures novas geradas pelo Python
(`tests/gerar_fixture_geometria.py`, `tests/gerar_fixture_intercalacao.py`).

Duas coisas que os passos de mutação provaram, e não são teatro: trocar
`Math.round` por `Math.trunc` no `min_len_um` **quebra** casos do contrato, e
concatenar em vez de intercalar **quebra** o teste da ordem e o do dedup.

## O que está verificado

Rodados em 2026-08-08, todos passando com saída limpa:

```
./.venv/Scripts/python.exe tests/test_optimize.py
./.venv/Scripts/python.exe tests/test_roundtrip.py
./.venv/Scripts/python.exe tests/test_preview.py
./.venv/Scripts/python.exe tests/test_casos_select.py
./.venv/Scripts/python.exe tests/test_packing.py
./.venv/Scripts/python.exe tests/test_api_upload.py
./.venv/Scripts/python.exe tests/test_api_extracao.py
./.venv/Scripts/python.exe tests/test_api_geometria.py
./.venv/Scripts/python.exe tests/test_api_export.py
./.venv/Scripts/python.exe tests/test_storage.py
./.venv/Scripts/python.exe tests/test_cli.py
./.venv/Scripts/python.exe tests/test_numeros.py
./.venv/Scripts/python.exe tests/test_entradas_gui.py
./.venv/Scripts/python.exe tests/test_fixture_geometria.py
./.venv/Scripts/python.exe tests/test_api_estaticos.py
```

Os treze primeiros foram rodados de novo **sobre a `main` já mesclada**, e
passam. Mesclar sem conferir o resultado não prova nada: cada branch passava
sozinho. O décimo quarto é da etapa 3 e roda no branch `frontend-canvas`, onde
os quatorze passam juntos (2026-08-09).

Do lado TypeScript, no mesmo branch, **2110 testes de unidade e 2 de ponta a
ponta**, os últimos rodados três vezes seguidas sem falha:

```
cd web/frontend && npm test
cd web/frontend && npm run build
cd web/frontend && npm run e2e
```

**Para abrir a tela à mão, use `http://localhost:5173`, não `127.0.0.1`:** o
Vite escuta em `localhost` (IPv6) por padrão e recusa a conexão no IPv4. Foi o
que fez a tela "dar erro" numa conferência.

A bateria inteira foi rodada três vezes seguidas, sem falha nenhuma. Isso
importa: até a correção do commit `1687cef` ela era intermitente — uma página
ficava presa em `na_fila` e a espera estourava os 60 s. Se voltar a acontecer,
o suspeito é a troca atômica da ficha, não lentidão: a extração leva 0,5 s.

## Como rodar a bateria inteira

Medido em 2026-08-24 nesta máquina (20 núcleos), no branch
`contas-cotas-registros`. São **25 arquivos** em `tests/`, e cada um é um
programa independente — sem pytest, com `if __name__ == "__main__":`.

**Em paralelo, um processo por arquivo — 20 s:**

```bash
cd C:/Users/leole/Programas/PdfToDxf
for f in tests/test_*.py; do
  ( ./.venv/Scripts/python.exe "$f" >/tmp/log_$(basename "$f").txt 2>&1 \
      || echo "FALHA $f" ) &
done
wait
echo "fim"
```

Silêncio é sucesso: só as falhas se anunciam, e a saída de cada arquivo fica em
`/tmp/log_<arquivo>.txt` para ler depois. **Sequencial leva 131 s** — o paralelo
é ~7× mais rápido. Rodado três vezes seguidas, 25 de 25, sem falha.

**Por que dá para paralelizar:** cada arquivo monta as próprias pastas
temporárias e o próprio banco no topo do módulo (`PDFTODXF_DADOS`,
`PDFTODXF_BANCO` e companhia, por `tempfile.mkdtemp`). Não há estado
compartilhado entre eles. **Confira essa premissa ao acrescentar um arquivo de
teste** — um que grave no `dados/` do projeto quebraria os vizinhos, e a falha
apareceria no arquivo errado.

**Duas armadilhas do laço acima**, ambas custaram tempo em 2026-08-24:

- `wait` dentro de `$(...)` **não** espera os jobs do processo pai. A saída vaza
  para os comandos seguintes e você atribui a falha ao arquivo errado.
- Queimadores de CPU deixados vivos de uma medição anterior fazem a bateria
  falhar por contenção. Mate-os antes de concluir qualquer coisa.

O frontend continua separado, e é sequencial:

```bash
cd web/frontend && npm test && npm run build
```

O ponta a ponta (`npm run e2e`) tem armadilha própria — veja "Duas armadilhas de
ambiente" lá em cima, sobre a porta 8000.

## O que a planta real disse sobre os tetos

Medido em 2026-08-08 com `inspecionar`, que é para isso que ele existe.

A planta grande (`LAY-1028.26.00_REV 02`, 13,8 MB de PDF, A3) tem **2.332.566
entidades** numa página só — **78% do teto de 3 milhões da etapa 2**. Não é
folga: é uma planta comum do acervo, não um caso extremo inventado. Antes do
deploy, ou o teto sobe, ou a mensagem de recusa precisa ser honesta sobre o que
significa.

| Combinação | Entidades | DXF estimado |
|---|---|---|
| sem opções | 2.332.566 | ~496 MB |
| dedup | 933.715 | ~202 MB |
| unir | 2.332.566 | ~219 MB |
| dedup + unir + arredondar | 933.715 | ~80 MB |

Dois números que importam para a etapa 3: **60% das entidades são duplicatas**
(2,33 M caem para 934 mil com `dedup`), e a estimativa acertou o tamanho real
com 2% de erro — o DXF sem opções saiu com 508 MB contra os 496 MB previstos.

A planta pequena (`LAY-1031.26.00_REV 00`, 750 KB, a que está em `Input/` hoje)
tem 18.860 entidades e converte em segundos; é a que serve para as passagens
manuais. A grande foi apagada a pedido do usuário depois da medição — os números
acima são o que sobrou dela, e são o que interessa.

## O que falta

Os itens 1 a 7 **dependem do humano** — conferir na tela, decidir, trazer um
revisor de fora, ou instalar o que falta na máquina. Os itens 8 a 10 são
trabalho de sessão, e **não esperam pelos primeiros**.

### Depende de você

0. ~~Os dois números do AutoCAD que fecham a questão do ×100.~~ **Respondido em
   2026-08-21:** `DIST` = 6,06 na cota que mostra 606, ou seja, era o `DIMLFAC`
   e o app está certo. Ver "A questão do ×100, encerrada".

1. **Conferência manual do app desktop.** Só um humano pode fazer. A etapa 1
   mexeu em `pdftodxf/gui.py` e nenhum teste exercita a integração do painel de
   exportação com o canvas.

   ```
   ./.venv/Scripts/python.exe main.py "Input/LAY-1031.26.00_REV 00.pdf"
   ```

   Conferir: a planta aparece; **Calibrar (2 pontos)** mostra a escala na barra;
   **Exportar DXF…** abre o painel; marcar e desmarcar opções muda a contagem, a
   estimativa e a prévia; desligar um layer some com ele; salvar gera o arquivo;
   o DXF abre no CAD com as medidas certas.

2. **Revisão independente das tarefas 4 a 7.** Elas já passaram por uma
   revisão (commit `55f941b`), mas feita pelo mesmo modelo que as escreveu —
   aquele harness não permitia subagente. Ela achou e corrigiu três defeitos,
   dois graves, o que é sinal de que valeu; mas um autor revisando a si mesmo é
   cego onde o próprio modelo mental está errado. Vale um olhar de fora antes
   de a etapa 3 escrever o leitor TypeScript em cima do formato binário — esse
   é o ponto de não-retorno, porque depois dele um erro no formato custa duas
   implementações.

3. **Decidir sobre a exportação no processo do site** (ver dívida abaixo). É
   decisão de projeto, não conserto — muda o contrato da rota.

4. **Abrir no CAD um DXF gerado pela CLI** e conferir as medidas. É o único
   passo da etapa 2.5 que uma sessão não consegue fazer sozinha. O arquivo já
   está gerado, em `output/teste.dxf` — planta `LAY-1031.26.00_REV 00`,
   plotagem 1:50, unidade metro, 18.860 entidades.

5. **Decidir o que fazer com o teto de 3 milhões de entidades**, agora que se
   sabe que uma planta comum do acervo chega a 2,33 milhões (ver a seção acima).

6. ~~Revisar e mesclar o PR #3.~~ **Feito em 2026-08-11**, com commit de mescla
   e a bateria conferida sobre o resultado.

7. **Construir a imagem Docker**, quando houver `docker` na máquina. É o único
   item da etapa 3 que sobrou:

   ```
   docker build -f deploy/Dockerfile -t pdftodxf .
   docker run --rm -p 8000:8000 pdftodxf
   ```

### Etapa 3.5 — interface redesenhada (2026-08-09, pronta)

Não estava no plano de cinco etapas. Entrou depois de o usuário ver o cabeçalho
de duas faixas com planta real e dizer que não dava para entender nada e que
estava com "cara de sistema de prefeitura". Três direções foram desenhadas e
comparadas; ganhou o **painel lateral recolhível**.

- **Desenho:** `docs/superpowers/specs/2026-08-09-interface-redesenho-design.md`
- **Plano:** `docs/superpowers/plans/2026-08-09-interface-redesenhada.md`

O que mudou: barra superior fina (abrir, página, estimativa, exportar) e painel
de 260 px com Escala, Compactação e Camadas — recolhe para uma faixa de ícones
de 48 px, e vira gaveta abaixo de 900 px. Cada opção de compactação ganhou uma
linha explicando o efeito, e "remover duplicados" mostra a proporção real da
planta aberta. As camadas ganharam olho, bolinha de cor e contagem, tudo
calculado no navegador a partir do binário que já chega. A estimativa mostra
`12,3 MB → 4,1 MB · −67%` em vez de um número solto. Paleta e tipografia
refeitas, dez ícones Tabler colados inline, zero dependência nova.

**Três opções de compactação passaram a vir ligadas por padrão** — unir,
arredondar e remover duplicados, que só tiram redundância. "Remover
preenchimentos" fica desligada de propósito: ela apaga hachuras e áreas
pintadas do desenho.

Arquivos novos: `camadas.ts`, `painel.ts`, `secoes.ts`, `barra.ts`,
`ui/icones.ts`, `ui/controles.ts`. O motor de desenho não foi tocado.

**O que a revisão final pegou e as sete revisões por tarefa não:** a escala de
plotagem e a troca de unidade estavam sendo calculadas à mão, erradas, em vez de
usarem as funções já testadas do núcleo; a bolinha de cor não tratava a
sentinela `0xFFFFFFFF` e pintava branco onde o desenho é preto; e o painel de
aviso, sem `pointer-events: none`, engolia os cliques do canvas e impedia a
calibração por dois pontos de completar. Tudo corrigido, com teste de ida e
volta da escala que não existia.

### Defeito de ambiente que já passou (2026-08-09 → 2026-08-10)

> **Resolvido por um reinício da máquina.** Hoje a bateria dá **17 de 17** aqui,
> em 36 s. Fica registrado porque o diagnóstico é reaproveitável: se o mesmo
> sintoma voltar, comece pelo reinício em vez de caçar defeito no código.

Durante algumas horas, `npm run e2e` dava 9 de 10 nesta máquina e 10 de 10 no
CI. O que falhava era "converte uma planta de ponta a ponta", em
`download.path()`, com `canceled`. O navegador começava o download com o nome
certo e depois o cancelava.

**Não é do código**, e isto foi verificado, não suposto:

- o servidor está correto — exportação em 0,137 s e a rota de download devolve
  44.819 bytes de `application/dxf`, conferido com `curl` fora do navegador;
- voltar o `api.ts` à versão anterior à etapa 3.6 **não** muda nada;
- apagar as 111 pastas acumuladas em `dados/` **não** muda nada;
- tirar por completo o `link.remove()` depois do clique **não** muda nada;
- reinstalar o Chromium do Playwright **não** muda nada;
- o mesmo teste passava 10/10 nesta máquina duas horas antes;
- **o CI no Linux roda os dez e passa.**

Sintoma de apoio: a bateria caiu de 25 s para 2,7 min, e um `du` no `%TEMP%`
(2941 entradas) estourou dois minutos sem terminar. Reinstalar o Chromium do
Playwright não resolveu; **reiniciar o Windows resolveu.**

### Etapa 3.6 — indicadores de progresso (2026-08-10, pronta)

Entrou depois da 3.5, a pedido do usuário: a tela não contava o que estava
acontecendo nos momentos em que ficava parada.

- **Desenho:** `docs/superpowers/specs/2026-08-09-progresso-design.md`
- **Plano:** `docs/superpowers/plans/2026-08-09-progresso.md`

Cinco momentos ganharam indicador: envio do PDF (determinado, com botão de
cancelar), extração (indeterminado, com tempo decorrido), download da geometria
(determinado), pintura no canvas (indeterminado) e geração do DXF
(indeterminado). `enviarPdf` trocou `fetch` por `XMLHttpRequest`, que é o único
jeito de saber quantos bytes subiram; `lerGeometriaBruta` passou a ler o corpo
em pedaços. Nenhuma dependência nova.

**A regra que governa: nunca inventar porcentagem.** Sem número real, a barra é
indeterminada e mostra o tempo decorrido, que é verdade.

**O que a revisão final pegou, e as revisões por tarefa não:** o plano pôs
**cinco produtores disputando um slot só**, sem arbitragem. Disso saíam três
defeitos — a porcentagem de "Desenhando" era falsa (numerador contava a janela
visível, denominador contava a página inteira, então em qualquer zoom a barra
mentia); um tique da faixa apagava um aviso vivo na sobreposição, inclusive a
instrução da calibração e mensagens de erro; e o botão Cancelar era destruído e
recriado a cada ~50 ms, o que **engolia o clique** entre o apertar e o soltar.
Hoje são **dois indicadores independentes**, um por lugar, o aviso ganha do
progresso na sobreposição, e a barra é criada uma vez e só atualizada.

### Integração contínua (2026-08-09)

`.github/workflows/ci.yml`, três jobs em `push` e `pull_request`: testes Python
(um arquivo por vez, sob `xvfb`), frontend (`npm test` + `npm run build`) e
ponta a ponta (Playwright com Chromium). **Verde.**

Ao montá-la apareceu um defeito antigo: o `playwright.config.ts` subia o
servidor com `.venv/Scripts/python.exe`, e o `cmd.exe` corta no primeiro `/` —
as execuções verdes anteriores só passavam porque `reuseExistingServer` achava
um uvicorn já de pé. Hoje o caminho vem de `PDFTODXF_PYTHON`, com padrão certo
por plataforma.

### Trabalho de sessão

8. ~~**Terminar a etapa 4 — contas, cotas e registros.**~~ **Feita em
   2026-08-27**: as 12 tarefas completas, seis PRs mesclados e a tarefa 12 no
   PR #10, aprovado para merge. O que sobrou vive em "Pendências abertas da
   etapa 4", no topo.

   **Por que a etapa 4 antes da auto-escala**, decidido em 2026-08-09: as
   etapas 4 e 5 são o que leva o projeto ao objetivo declarado — versão web
   pública numa VPS. A auto-escala é melhoria de um conversor que já funciona,
   e os próprios achados de 2026-08-08 mostram que ela provavelmente precisa de
   OCR ou IA para ler o carimbo, o que é trabalho maior e mais incerto. Melhor
   depois de o produto estar no ar.

   O escopo da etapa 4 está na spec geral,
   `docs/superpowers/specs/2026-08-01-pdftodxf-web-design.md`. O desenho da
   etapa 3 deixou explicitamente de fora, para cá: o canto da conta na faixa 1,
   o indicador de cota restante, as cinco linhas de erro sobre cota esgotada, e
   a `privacidade.html` que o rodapé já referencia e que ainda não existe.

9. **Planejar a etapa 5 — deploy.** Depois da 4.


10. **Auto-escala e ferramentas de medição**, nessa ordem. A decisão de
    2026-08-08 dizia "depois da etapa 3"; em 2026-08-09 ficou **depois também
    das etapas 4 e 5**, pela razão do item 8. Os achados estão em
    `docs/superpowers/specs/2026-08-08-auto-escala-e-medicao-achados.md`.
    Comece por ele: a ideia original era deduzir a escala medindo uma cota, e a
    sondagem mostrou que nas plantas deste acervo a escala está escrita no
    carimbo e as cotas viraram desenho, sem texto para ler.

O que as revisões e a execução da etapa 2 pegaram, para não se perder: o PDF
original era apagado assim que a fila esvaziava, o que tornava impossível
extrair a página 2 de um documento de duas páginas; `pedir_extracao` conferia o
estado fora da trava, então dois POSTs simultâneos submetiam dois workers para a
mesma página; o formato binário não alinhava as seções, e o `Uint32Array` da
etapa 3 levantaria `RangeError`; uma página sem segmento nenhum estourava
`ValueError` na divisão; quatro exportações idênticas simultâneas disputavam o
mesmo destino e morriam em 500; e uma falha passageira na gravação da ficha
deixava a página presa em `na_fila` para sempre. A spec foi ajustada em dois
pontos, porque quem especificou errado foi o plano. Detalhe em
`.superpowers/sdd/progress-etapa2.md`.

## Ambiente

- **`.venv` no projeto.** Use sempre `./.venv/Scripts/python.exe`, nunca
  `python`. Está no `.gitignore`.
- Núcleo: PyMuPDF, ezdxf, Pillow (`requirements.txt`, não muda).
- Serviço: FastAPI, uvicorn, python-multipart, httpx2 (`web/requirements.txt`).
- Versões instaladas: FastAPI 0.141.1, Starlette 1.3.1, uvicorn 0.52.1,
  httpx2 2.9.1, Python 3.13.2.
- **`httpx2` é legítimo**, não é typosquat: o Starlette 1.3 o declara no extra
  `full` e `starlette/testclient.py` faz `import httpx2 as httpx`. Verificado.
- **Sem pytest.** Os testes deste projeto são funções com `assert` e um bloco
  `if __name__ == "__main__":`. Mantenha o padrão.
- **Integração contínua em `.github/workflows/ci.yml`**, três jobs em paralelo:
  os arquivos `tests/test_*.py` um a um (sob Xvfb, por causa das duas suítes de
  janela Tk), `npm test` + `npm run build`, e o Playwright. O runner não tem
  `.venv` — o `playwright.config.ts` e o `e2e/preparar.ts` aceitam
  **`PDFTODXF_PYTHON`** no lugar do `.venv/Scripts/python.exe`, e o padrão
  continua sendo o `.venv` local.

## Dívida conhecida

Nada disso bloqueia; está registrado para não se perder.

- **`ler_ficha` tem paciência no `open`, mas não no `exists()`.** Achado em
  2026-08-24, ao dar a `ler_ficha` a mesma repetição que `gravar_ficha` já
  tinha. A janela do `os.replace` que fazia a leitura estourar `PermissionError`
  alcança também o `Path.exists()` da linha de cima — só que ele engole o
  `OSError` e devolve `False`, e aí `ler_ficha` sai por `return None`. O
  navegador recebe um 404 "Trabalho não encontrado" no meio da extração, no
  lugar do 500 de antes: sintoma diferente, mesma janela. A correção é a mesma —
  passar a conferência de existência pelo `com_paciencia` de
  `web/api/storage.py`, com teste no molde do
  `test_falha_transitoria_ao_ler_nao_derruba_a_consulta`. **Diferença
  importante:** o defeito do `open` foi medido (2 de 6 execuções de
  `tests/test_api_extracao.py`); este é raciocínio sobre o código, ainda não
  visto acontecer. Confirme antes de corrigir.
- **`limpar()` não tolera `PermissionError` vindo de `ler_ficha`.** A leitura
  agora insiste cinco vezes, mas ainda pode desistir — e o
  `except (ValueError, KeyError, TypeError)` de `_trabalhos()` não pega
  `PermissionError`, que é `OSError`. Uma ficha ocupada na hora errada aborta a
  varredura inteira. O serviço não cai, porque o `except Exception` de
  `_limpeza_periodica` segura, mas a passagem toda se perde junto — o expurgo de
  registros, o de e-mails e o do banco vêm depois de `storage.limpar` no mesmo
  `try` — e só volta a rodar 10 minutos depois.
- **Contar páginas de um PDF não tem função pública no núcleo.** A CLI
  (`_inspecionar`) e `web/api/main.py` abrem o `fitz` na mão para isso, cada uma
  do seu jeito. Um `extractor.contar_paginas(caminho)` acabaria com a
  duplicação. Achado da etapa 2.5, quando a CLI virou o terceiro consumidor do
  núcleo e foi a única coisa que ela precisou de fora da superfície pública.
- **A saída da CLI supõe um console que aceita UTF-8, e o do Windows não
  aceita.** As linhas de retrato foram passadas para ASCII depois de o `≈`
  quebrar em cp1252, mas nada impede a próxima mensagem de reintroduzir o
  problema — não há teste que rode a CLI com um stdout de codificação estreita.
  Nomes de layer com acento vêm do PDF e continuam saindo por esse mesmo caminho.

- **O contrato congela o `select()`, não o `classify()`.** As tabelas do JSON são
  dado congelado, então mudar o `classify()` não quebra teste nenhum — muda
  silenciosamente o que o servidor manda, e prévia e DXF continuam concordando
  entre si, mas com o comportamento anterior. O controle hoje é de processo
  (regerar e conferir o diff), não de teste.
- **A caixa da calibração é um `window.prompt`.** Feio de propósito: trocá-lo
  por uma caixa própria é acabamento, e prendê-lo na tarefa teria deixado a
  revisão grande demais.
- **O plano de 2026-08-04 tinha quatro testes errados**, todos corrigidos nele e
  no código ao executar: o literal truncado da escala de plotagem, as asserções
  do `estados.ts` procurando palavras no campo errado, `1.500.000` bytes dando
  "1,4 MB" em vez de 1,5, e a configuração do Playwright esperando `/docs` numa
  API que sobe com `docs_url=None`. Nenhum era de implementação — todos de
  expectativa escrita à mão sem rodar.
- **O `npm audit` do frontend acusa 5 vulnerabilidades, todas a mesma raiz.** É
  o aviso do `esbuild` que permite a qualquer site fazer pedido ao servidor de
  desenvolvimento do Vite e ler a resposta. Só afeta `npm run dev`, que escuta
  em localhost, e nada disso vai ao navegador do usuário — o projeto não tem
  dependência de produção. Fechar exigiria Vite 8, que é mudança quebrando
  compatibilidade e diverge do plano; ficou registrado em vez de aplicado.
- **`EntityAttrs.kind` é lista de strings** e o laço quente do `select()` compara
  string por entidade. Em 3 milhões de entidades no navegador isso pesa. O
  formato binário da etapa 2 já grava código numérico; falta reconciliar.
- `"extraindo"` está no contrato de estado da página e nada o escreve: o
  processo pai é o dono do estado e não sabe a hora em que o worker pega o
  trabalho. Quem lê deve tratá-lo como "em andamento", igual a `"na_fila"`.
  Está documentado no topo de `web/api/jobs.py`.
- **A exportação roda no processo do site.** A extração ganhou processo
  separado e tetos de memória e CPU na tarefa 3 justamente para uma planta
  monstruosa morrer sozinha sem levar o site junto. A exportação da tarefa 6
  não tem nada disso: carrega o `cache.pickle` inteiro e escreve o DXF ali
  mesmo. Corrigir muda o contrato da rota — viraria assíncrona, com polling,
  como a extração — então é decisão de projeto, não conserto.
- `web/api/jobs.py`: o cache é gravado com `pickle.dumps`, que materializa o
  pickle inteiro na memória — medido em ~230 MB no teto de 3 milhões de
  entidades. O plano usava `pickle.dump` direto no arquivo; a regressão entrou
  quando o `_gravar_atomico` passou a receber bytes prontos. Basta ele aceitar
  uma função que escreve.
- `web/api/packing.py`: `desempacotar` levanta `KeyError`, e não `ValueError`,
  para um arquivo com a magia certa e a tabela de seções incompleta. Só afeta
  os testes — em produção quem lê o formato é o TypeScript.
- `web/api/main.py`: `criar_trabalho` fica fora do `try/except` que limpa o
  disco. Se a gravação da ficha falhar, a pasta do trabalho fica para trás.
- `tests/test_casos_select.py` já aponta os índices divergentes; a mensagem
  ficou boa, mas o `bytes_esperado` não aponta nada equivalente.

## Como o trabalho vem sendo feito

Processo que vale manter, porque pegou defeitos reais:

1. Um plano por etapa, escrito antes de qualquer código, com o código exato de
   cada passo e ciclo TDD explícito.
2. Execução tarefa a tarefa, cada uma num subagente com contexto limpo,
   recebendo só o seu brief.
3. Revisão por tarefa, num subagente separado, que recebe o brief, o relatório
   do implementador e o diff — e é instruído a **não confiar no relatório**.
4. Revisão final do branch inteiro num modelo mais capaz.
5. Achados menores vão para o ledger; importantes viram correção antes de seguir.

Os ledgers e briefs ficam em `.superpowers/sdd/` (ignorado pelo git, existe só
nesta máquina): `progress.md` para a etapa 1, `progress-etapa2.md` para a etapa 2,
e os briefs em `briefs/` e `briefs-etapa2/`.

**O que esse processo pegou** e um caminho direto não teria: geradores de teste
cuja grade de coordenadas era grande demais e quase não produzia duplicatas
(0 a 8 por amostra, uma amostra com nenhuma), deixando o algoritmo mais delicado
sem cobertura real; um par de coordenadas que não detectava a mudança do
arredondamento da chave; e três variantes erradas do `select()` que passavam no
contrato sem serem notadas.

## Regra do usuário

Perguntas sempre em múltipla escolha, com opções clicáveis, uma pergunta por
vez — inclusive para aprovar seções de plano ou esclarecer respostas genéricas.
