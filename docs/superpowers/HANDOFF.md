# Handoff — versão web do PdfToDxf

Estado em 2026-08-08. Leia isto primeiro ao retomar em sessão nova.

> **Se o pedido foi só "continuar":** execute o plano da etapa 3,
> `docs/superpowers/plans/2026-08-04-frontend-canvas.md` — 15 tarefas, e a
> primeira **não é código**: é a medição no navegador que decide a arquitetura.
> Ele é o próximo trabalho que uma sessão consegue fazer sozinha. Os itens 1 a 4
> da lista "O que falta" **dependem de você, humano**, e não são pré-requisito
> para a etapa 3: não fique bloqueado neles nem os execute por conta própria.

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
- **Achados sobre auto-escala e medição:**
  `docs/superpowers/specs/2026-08-08-auto-escala-e-medicao-achados.md` — duas
  features futuras, decididas para **depois** da etapa 3. Não é spec; é o que se
  descobriu sondando uma planta real, e derruba premissas que parecem óbvias.

O projeto está dividido em 5 etapas: **1** núcleo, **2** API de conversão,
**3** frontend, **4** contas/cotas/registros, **5** deploy, mais uma **2.5**
curta que entrou depois: a linha de comando.

As etapas 1, 2 e 2.5 estão planejadas e implementadas. A **3** tem desenho e
plano prontos e nenhuma linha de código escrita. Todos os documentos foram
escritos para bastar por si: não é preciso resgatar a conversa que os originou.

## Onde o código está

| Branch | Conteúdo | Situação |
|---|---|---|
| `main` | até o plano da etapa 1 | base |
| `nucleo-classify-select` | etapa 1 inteira + plano da etapa 2 | **pronta, não mesclada** |
| `api-de-conversao` | etapa 2 inteira | **pronta, não mesclada** |
| `linha-de-comando` | etapa 2.5 inteira | **pronta, não mesclada** |

`linha-de-comando` sai de `api-de-conversao`, que sai de `nucleo-classify-select`,
que sai de `main`. Nada foi mesclado ainda. A 2.5 saiu da 2, e não do núcleo,
porque a definição de pronto dela exige a bateria inteira passando — e os testes
da API só existem no branch da etapa 2.

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
```

A bateria inteira foi rodada três vezes seguidas, sem falha nenhuma. Isso
importa: até a correção do commit `1687cef` ela era intermitente — uma página
ficava presa em `na_fila` e a espera estourava os 60 s. Se voltar a acontecer,
o suspeito é a troca atômica da ficha, não lentidão: a extração leva 0,5 s.

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

Os seis primeiros itens **dependem do humano** — conferir na tela, decidir,
mesclar, ou trazer um revisor de fora. Os dois últimos são trabalho de sessão, e
não esperam pelos primeiros.

### Depende de você

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

5. **Mesclar as etapas 1, 2 e 2.5** quando a conferência manual passar.
   `main` → `nucleo-classify-select` → `api-de-conversao` →
   `linha-de-comando`, nessa ordem.

6. **Decidir o que fazer com o teto de 3 milhões de entidades**, agora que se
   sabe que uma planta comum do acervo chega a 2,33 milhões (ver a seção acima).

### Trabalho de sessão

7. **Executar o plano da etapa 3**, `docs/superpowers/plans/2026-08-04-frontend-canvas.md`
   — 15 tarefas. Comece pela tarefa 1, que **não é código**: é uma medição no
   navegador do custo do `select()` e da reconstrução dos `Path2D` em 3 milhões
   de entidades. A escolha pelo Web Worker é hipótese fundamentada, não número
   medido, e o plano diz em que resultado parar e reabrir a arquitetura antes de
   seguir. Não pule essa tarefa: as tarefas 5 e 6 dependem do que ela decidir.

8. **Planejar as etapas 4 e 5.**

9. **Auto-escala e ferramentas de medição**, nessa ordem, **depois da etapa 3** —
   decisão de 2026-08-08. Os achados e as decisões já tomadas estão em
   `docs/superpowers/specs/2026-08-08-auto-escala-e-medicao-achados.md`. Comece
   por ele: a ideia original era deduzir a escala medindo uma cota, e a sondagem
   mostrou que nas plantas deste acervo a escala está escrita no carimbo e as
   cotas viraram desenho, sem texto para ler.

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

## Dívida conhecida

Nada disso bloqueia; está registrado para não se perder.

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
