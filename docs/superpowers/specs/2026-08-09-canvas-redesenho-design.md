# Etapa 3 — redesenho do canvas, depois da medição

Desenho validado em 2026-08-09. **Substitui a seção "A decisão que governa a
arquitetura" de `docs/superpowers/specs/2026-08-04-frontend-canvas-design.md`**,
e com ela o `worker.ts` e as tarefas 6 a 15 do plano
`docs/superpowers/plans/2026-08-04-frontend-canvas.md`. O resto daquele desenho
— fluxo de rede, estados, erros, calibração, ferramental — continua valendo, e
onde os dois discordarem vale este.

As tarefas 1 a 5 do plano antigo estão **feitas e não mudam**: `select.ts`,
`estimativa.ts`, `formato.ts` e a intercalação são espelhos do Python e valem em
qualquer arquitetura de desenho.

## Por que existe

O desenho de 2026-08-04 dizia, sobre a arquitetura de duas threads: "isto é uma
hipótese, não uma medida", e mandava medir antes de comprometer. A medição foi
feita e **derrubou a hipótese**. Depois derrubou também a primeira coisa que
entrou no lugar dela. Os números estão em `web/frontend/medicao/RESULTADO.md`;
o que importa aqui é o que cada um decidiu.

| Medida | Número | O que decidiu |
|---|---|---|
| `select()` sobre 3 milhões | ~12 ms | O Web Worker não se justifica: ele tiraria da thread principal 12 ms |
| Montar os `Path2D` de 3 milhões | 300–840 ms | O gargalo é o desenho, e `Path2D` é API de DOM — não existe em worker |
| **Traçar** 3 milhões, por quadro | 750–1290 ms | O custo dominante é por quadro, não por clique: pan e zoom não reconstroem nada e mesmo assim engasgam |
| Traçar 500 mil, por quadro | 173–341 ms | Não há teto seguro nem na planta média |
| Limiar de 1 pixel, folha inteira | sobram 1,8 M de 3 M | Descartar o que é menor que um pixel corta pouco: numa planta a maioria das linhas é maior que isso |
| Varrer 3 M por quadro para traçar 57 mil | 474–625 ms | — |
| Traçar os **mesmos** 57 mil de uma lista pronta | **15 ms** | Vinte vezes. A varredura é o custo; o traçado é de graça |

A última linha é a que governa este desenho. **Nada que dependa do número de
entidades pode acontecer a cada quadro.**

## A arquitetura

Uma thread. Sem Web Worker.

Na memória, depois que a página carrega:

- a `Geometria` já intercalada — `TypedArray` sobre o buffer recebido, sem cópia;
- a `mascara` do `select()`, refeita a cada mudança de opção (~12 ms);
- a **ordem por comprimento decrescente**, calculada uma vez;
- a **lista de desenho**, preparada para o zoom corrente.

### A lista de desenho

É o centro do desenho. Uma lista de índices de entidade, preparada uma vez, com
duas regras:

1. **Teto por região de papel.** A folha é dividida em regiões do tamanho de
   **4 × 4 pixels** no zoom para o qual a lista está sendo preparada, e cada
   região aceita no máximo **4 entidades**. Os dois valores vêm do protótipo:
   com teto de 4 a lista ficou em 113 mil e com teto de 2 em 57 mil, e as duas
   traçam dentro do quadro. Começar por 4 dá o desenho mais cheio das duas
   opções que cabem; a primeira tarefa do plano confirma ou ajusta o par,
   medindo, e o número escolhido fica registrado com o motivo.
2. **Os mais longos primeiro.** A preparação percorre as entidades na ordem de
   comprimento decrescente, então quem ocupa as vagas de cada região é o traço
   que mais se vê. É para isto, e só para isto, que a ordenação existe.

Entidades que não são segmento — texto, arco, polilinha, curva — entram sempre,
sem disputar vaga: são poucas e são a leitura do desenho.

O que a máscara zerou nunca entra. A simplificação não pode ressuscitar o que as
opções descartaram.

### O quadro

Com a lista pronta, um quadro é: aplicar a transformação, percorrer a lista,
descartar por caixa o que está fora da tela, traçar agrupando por (layer, cor).
Medido em **15 ms** com 57 mil entidades — quadro de 60 por segundo, inclusive
durante o arrasto.

Não há grade espacial. Ela foi construída, medida e recusada: custava de 455 a
560 ms para montar e servia para evitar uma varredura que este desenho não faz.
Recortar por caixa dentro de uma lista de 57 mil custa menos de um milissegundo.

### Quando a lista é preparada de novo

Só em três situações, e nenhuma delas é pan:

| Evento | Por quê |
|---|---|
| A máscara mudou | clique em opção ou em layer: outras entidades disputam as vagas |
| O zoom dobrou ou caiu à metade | as regiões do teto valem para uma faixa de zoom, não para um valor. O fator **2** é o ponto de partida: dentro dele a lista fica no máximo duas vezes mais densa ou mais rala que o ideal, o que a rasterização absorve |
| O conjunto de entidades mudou | o esqueleto chegou; depois o detalhe chegou |

Preparar custa da ordem de 500 ms, e por isso é **fatiada entre quadros**: cada
quadro prepara um pedaço e desenha o que já tem. A planta se completa à vista,
a tela nunca trava e nenhum clique é ignorado. Zoom contínuo — pinça ou roda —
continua desenhando a lista antiga, a 15 ms, e só prepara quando o gesto para.

**A preparação fatiada tem de produzir exatamente a mesma lista que a preparação
inteira.** Se depender de quantos pedaços couberam em cada quadro, o desenho
passa a depender da velocidade da máquina, e o defeito só aparece na máquina
lenta de outra pessoa. Isso é teste, não intenção.

### O que se promete, e o que não

Contagem, estimativa e o DXF exportado são **exatos**, sempre: saem do
`select()`, que é o espelho preso por 1024 casos, e não do canvas.

O desenho é **aproximado com a folha inteira à vista** — o que não cabe no teto
por região não aparece — e vai ficando exato conforme se aproxima. Já era
inevitável: 3 milhões de entidades não cabem em 2 milhões de pixels, e a
rasterização apaga a diferença de qualquer jeito. O que este desenho faz é
escolher *quais* sobrevivem, em vez de deixar o acaso do traçado escolher.

Um indicador de "desenho simplificado" foi considerado e **não é exigido** —
decisão do usuário em 2026-08-09. Fica registrado para não voltar como novidade.

## Componentes

Em `web/frontend/src/`:

| Arquivo | Situação | Responsabilidade |
|---|---|---|
| `select.ts` | pronto | espelho de `optimize.select()` |
| `estimativa.ts` | pronto | espelho de `optimize.estimate_bytes()` |
| `formato.ts` | pronto | leitor do `geometry.bin` e a intercalação |
| `worker.ts` | **não existe** | — |
| `ordem.ts` | novo | ordem por comprimento decrescente, radix de 16 bits em duas passadas |
| `lista.ts` | novo | prepara a lista de desenho; retomável, para o pintor fatiar |
| `pintor.ts` | novo | o laço de quadro: orçamento, continuação, quando recomeçar |
| `canvas.ts` | novo | recebe um lote de índices e traça, agrupado por (layer, cor) |
| `gestos.ts` | novo | aritmética de pan e zoom, função pura |
| `api.ts`, `calibrate.ts`, `toolbar.ts`, `estados.ts`, `main.ts`, `estilo.css` | novos | como no desenho de 2026-08-04 |

As fronteiras, que é o que importa:

- **`ordem.ts` e `lista.ts` não conhecem canvas.** Entram arrays; saem arrays.
  `lista.ts` recebe um cursor e devolve onde parou, para o pintor continuar no
  quadro seguinte sem guardar estado dentro dela.
- **`canvas.ts` não conhece lista, orçamento nem gesto.** Recebe um lote pronto
  e uma transformação, e traça. É o que mantém de pé o teste do contexto 2D
  falso.
- **`pintor.ts` é o único com estado temporal.** Ele sabe se a transformação, a
  máscara ou a geometria mudaram, se recomeça ou continua, e quanto cabe num
  quadro. É pequeno de propósito: é o único lugar onde o tempo existe.

Quatro dos cinco novos — `ordem`, `lista`, `gestos` e `canvas` — são função pura
sobre arrays e se testam sem navegador, como o `select.ts`.

`conta.ts` não entra nesta etapa.

## Fluxo

Os passos de rede não mudam em relação ao desenho de 2026-08-04: envio do PDF,
escolha da página, consulta de estado com recuo de 300 ms a 2 s, `meta.json`,
calibração por dois pontos, exportação. Toda busca sob um `AbortController`
amarrado à página corrente — o detalhe da página anterior chegando depois da
troca continua sendo um defeito silencioso, e continua sendo evitado assim.

O miolo:

| Evento | O que acontece |
|---|---|
| Esqueleto chega | `lerGeometria` → `ordem` → `select` → prepara a lista → desenha e enquadra a folha |
| Detalhe chega | `intercalar` → `ordem` → `select` → prepara de novo → desenha |
| Clique em opção ou layer | `select` + `estimarBytes` (~12 ms, thread principal) → prepara de novo, fatiado |
| Pan | só a transformação muda → traça a mesma lista, 15 ms |
| Zoom | traça a mesma lista durante o gesto; prepara de novo quando o gesto para, e só se o zoom saiu da faixa do fator 2 |
| Janela redimensionada | como o zoom |

Uma regra em vez de seis casos: **o pintor recomeça quando muda a transformação,
a máscara ou o conjunto de entidades; e só prepara a lista de novo quando muda a
máscara, o conjunto, ou o zoom além de um fator.**

## Estados e erros

Inalterados em relação ao desenho de 2026-08-04. A tabela que mapeia `na_fila` e
`extraindo`, `sem_vetores`, `entidades_demais`, `recurso`, `interno`, o 404 do
trabalho expirado e o 413 do envio grande demais continua valendo. `"extraindo"`
segue tratado como sinônimo de `"na_fila"`, porque está no contrato da API e
nada o escreve.

A preparação da lista não ganha indicador próprio: cai na faixa de "carregando
detalhe" que aquele desenho já previa. Para quem olha é o mesmo fato — o desenho
ainda vai mudar.

## Testes

Os três primeiros existem e passam; os dois últimos vêm do desenho de
2026-08-04; os quatro do meio são novos.

| Teste | O que prende |
|---|---|
| Paridade, 1024 casos | a prévia é o DXF |
| Leitor do formato, contra fixture do Python | a ponte entre as duas implementações do formato |
| Intercalação | o achado do dedup: decidir por parte separada elege dois sobreviventes |
| `lista` respeita o teto e prefere os longos | nenhuma região passa do teto; entre dois candidatos fica o mais comprido |
| **`lista` fatiada é igual a `lista` inteira** | o desenho não pode depender de quantos pedaços couberam em cada quadro |
| `lista` nunca inclui o que a máscara zerou | a simplificação não ressuscita o que as opções descartaram |
| Zoom mantém parado o ponto sob o dedo | função pura em `gestos.ts`, provada sem navegador |
| Canvas contra contexto 2D falso | o traçado corresponde ao lote, agrupado por (layer, cor) |
| Ponta a ponta no Playwright | envia, desenha, clica, calibra, exporta — espera por condição, nunca por relógio |

As páginas de `web/frontend/medicao/` ficam no repositório e **não viram teste**.
Um limite de tempo em teste automático seria intermitente na primeira máquina
ocupada. Elas são instrumento de decisão; o `RESULTADO.md` é o registro.

## O que este desenho corrige no de 2026-08-04

1. **A arquitetura de duas threads sai.** O `select()` custa ~12 ms sobre 3
   milhões de entidades, e `Path2D` não existe dentro de um Web Worker. O worker
   moveria para fora os 12 ms e deixaria dentro os 800.
2. **"Reconstruir os `Path2D`" deixa de ser o evento caro.** O evento caro é
   qualquer coisa proporcional ao número de entidades acontecendo por quadro.
3. **A prévia passa a ser declaradamente aproximada no desenho** com a folha
   inteira à vista — não só provisória enquanto o detalhe não chegou. A
   exatidão continua inteira na contagem, na estimativa e no DXF.
4. **`gestos.ts` ganha importância.** Ele já estava previsto; agora é ele que
   decide quando a lista precisa ser preparada de novo.

## Fora de escopo

- Conta, cota e registro — etapa 4.
- Docker, Caddy e o deploy — etapa 5.
- Auto-escala e ferramentas de medição — decididas para depois da etapa 3, em
  `docs/superpowers/specs/2026-08-08-auto-escala-e-medicao-achados.md`.
- Vetorização de PDF escaneado, saída em DWG — fora do projeto.
