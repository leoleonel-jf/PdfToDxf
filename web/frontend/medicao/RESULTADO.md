# Medição do custo — tarefa 1 da etapa 3

**Data:** 2026-08-08
**Navegador:** Chrome 151.0.0.0 (Windows NT 10.0; Win64; x64)
**Máquina:** 13th Gen Intel Core i7-13700H, 20 núcleos lógicos, Windows 11
**Como rodar:** `cd web/frontend && npm run dev`, depois
`http://localhost:5173/medicao/custo.html`

## A leitura que vale

**`select()` está muito abaixo de 50 ms e a construção dos `Path2D` no pior
caso está muito acima de 200 ms: o gargalo é o desenho, não a decisão — o Web
Worker resolve o problema errado, e a arquitetura precisa ser reaberta antes da
tarefa 5.**

## Os números

Três repetições dentro da mesma carga da página, em duas cargas independentes.
Os valores estão em milissegundos, na ordem em que saíram.

| Fase | Carga A | Carga B |
|---|---|---|
| gerar 3M entidades sintéticas | 83 / 87 / 56 | 153 / 136 / 56 |
| `select()` cru sobre 3 M | 12 / 9 / 10 | 11 / 18 / 14 |
| construir `Path2D` — 500 mil sobreviventes | 70 / 47 / 52 | 104 / 79 / 77 |
| construir `Path2D` — 3 milhões sobreviventes | 294 / 393 / 839 | 727 / 529 / 842 |

Sobreviventes com dedup: 500.000. Grupos de caminho: 8.

## Duas mudanças em relação ao que o plano mandava medir

Ambas registradas porque mudam a conclusão, não por gosto.

**1. Repetir três vezes dentro da mesma carga.** O plano mandava recarregar a
página e usar a segunda passagem, "para o JIT já estar aquecido". Recarregar
não aquece JIT nenhum: cada carga é um contexto de JavaScript novo. As duas
primeiras passagens feitas assim deram `select()` de 14 e depois 31 ms, e
`Path2D` de 146 e depois 84 ms — um fator de dois em ambos, em direções
opostas. Um número desses não sustenta uma decisão de arquitetura.

**2. Medir também o `Path2D` com as 3 milhões de entidades vivas.** O cenário do
plano roda `selecionar(dados, 500)`, que corta por comprimento **e** deduplica:
sobram 500 mil. Mas a tela precisa desenhar o que o usuário pedir, e o padrão é
**sem dedup** — a planta grande do acervo tem 2,33 milhões de entidades e 60%
delas são duplicatas, então é justamente ao desligar o dedup que as 3 milhões
aparecem no canvas. Medir só o caso já filtrado dava 47–104 ms, abaixo do limiar
de 200 ms do próprio plano, e levaria à conclusão oposta.

## O que isso quer dizer

- **Decidir é barato.** 3 milhões de entidades passam pelo `select()` em ~12 ms.
  Isso cabe folgado dentro de um quadro de 16 ms, na thread principal, a cada
  clique numa opção. Tirar essa conta do caminho principal não compra nada: o
  worker existia para proteger a interface de uma pausa que não acontece.
- **Desenhar é caro, e é caro no lugar errado.** Reconstruir os caminhos custa
  de 300 a 840 ms no pior caso. Como `Path2D` é API de DOM, ele **não existe
  dentro de um Web Worker** — essa fase teria de acontecer na thread principal
  de qualquer jeito. Ou seja: a arquitetura de duas threads move para fora os
  12 ms e deixa dentro os 800 ms.
- **O custo não é linear com o número de entidades e não é estável.** De 500 mil
  para 3 milhões (6×) o tempo vai de ~70 ms para ~500 ms (7×), com repetições
  chegando a 842 ms — sinal de pressão de memória e coleta de lixo, não de mais
  trabalho. Três `Path2D` de 3 milhões de segmentos cada é muita coisa viva ao
  mesmo tempo.

## Segunda medição: traçar custa mais que montar

Feita em 2026-08-09, durante o redesenho, por `medicao/desenho.html`. A primeira
mediu quanto custa **montar** os `Path2D`. Esta mede quanto custa **traçá-los**,
por quadro — a pergunta de que o pan e o zoom dependem, e que ninguém tinha
feito. Segmentos curtos espalhados pela folha inteira, que é como uma planta é.

O `getImageData` de um pixel ao fim de cada quadro é o que força a rasterização
a terminar antes de o cronômetro parar. Sem ele o Chrome volta de `stroke()`
antes de pintar, e a medida sairia otimista por uma ordem de grandeza.

| | quadro isolado | pan de 5 quadros | zoom 4× |
|---|---|---|---|
| 500 mil | 341 / 249 / 182 | 205 / 174 / 228 / 248 / 173 | 114 / 91 / 100 |
| 3 milhões | 1292 / 1091 / 815 | 768 / 964 / 749 / 297 / 558 | 784 / 668 / 714 |

Três conclusões, e elas mandam mais que as da primeira medição:

- **O custo dominante é por quadro, não por clique.** Traçar 3 milhões custa de
  750 a 1290 ms; montar custava de 300 a 840 ms. Um arrasto de pan roda a ~1
  quadro por segundo, e nada é reconstruído nesse caminho.
- **Não há teto seguro nem na planta pequena.** 500 mil segmentos já dão 173 a
  341 ms por quadro, ou seja ~4 quadros por segundo. Não é um problema só do
  pior caso.
- **O `stroke()` não recorta sozinho.** Com zoom de 4×, 15/16 da folha estão
  fora da tela e o custo cai de ~900 para ~720 ms. O tempo é gasto percorrendo
  segmentos que não aparecem — que é exatamente o que um recorte por região
  visível elimina.

## Terceira medição: a varredura é o custo, não o traçado

Feita em 2026-08-09 por `medicao/indice.html`, durante o redesenho, para
responder antes de escrever o spec — e não depois — quanto custa o índice que o
desenho novo pretendia usar. **Navegador diferente das duas primeiras:** o
embutido do app (Chromium 148 sobre Electron), porque a extensão do Chrome não
voltou depois de a máquina reiniciar. Mesmo motor, versão um pouco atrás.

3 milhões de segmentos com comprimentos log-uniformes de 0,05 a 100 pt — a forma
de uma planta de CAD, muita linha curta e poucas longas. Uniforme daria uma
planta que não existe e responderia à pergunta errada.

### Montar o índice

| Fase | ms |
|---|---|
| ordenar por comprimento (radix de 16 bits, 2 passadas) | 270 / 233 |
| montar a grade | 560 / 455 |

Das 3 milhões, 893 mil ficaram **fora** da grade, na lista de "grandes": são as
que não cabem numa célula. Com esta distribuição, quase um terço.

### O quadro, com grade e com os filtros

| Zoom | Filtro | Traçados | ms |
|---|---|---|---|
| folha inteira | nenhum | 3.000.000 | 1701 / 1743 / 1546 |
| folha inteira | limiar de 1 px | 1.797.261 | 941 / 950 / 1118 |
| folha inteira | limiar + teto de 4 por caixa | 113.600 | 423 / 529 / 563 |
| folha inteira | limiar + teto de 2 por caixa | 56.800 | 474 / 517 / 625 |
| zoom 4× | limiar + teto de 2 por caixa | 220.857 | 505 / 374 / 426 |
| zoom 16× | limiar + teto de 2 por caixa | 59.480 | 167 / 169 / 169 |

Duas coisas já aparecem aqui. **O limiar de um pixel corta pouco**: 1,8 milhão
de segmentos sobrevive a ele com a folha inteira à vista, porque numa planta a
maioria das linhas é maior que um pixel. E **reduzir o traçado de 3 milhões para
57 mil não fez o quadro cair na mesma proporção** — de ~1600 ms para ~500 ms, e
não para ~20 ms. Algo além do traçado estava dominando.

### O experimento de controle, que é o que decidiu

A mesma lista de 56.800, já pronta, sem varrer as 3 milhões:

| | ms |
|---|---|
| desenhar a lista pronta | 22 / 17 / 27 / 17 / 15 |
| desenhar a lista pronta, pan de 5 quadros | 15 / 16 / 16 / 15 / 14 |

**Vinte vezes mais rápido, desenhando exatamente as mesmas entidades.** O meio
segundo era inteiramente a varredura das 3 milhões, refeita a cada quadro. O
traçado de 57 mil segmentos custa 15 ms, que é quadro de 60 por segundo.

### O que isso decidiu

- **A grade foi descartada.** Ela custava de 455 a 560 ms para montar e existia
  para evitar uma varredura que o desenho novo não faz mais. Recortar por região
  dentro de uma lista de 57 mil é um teste de caixa sobre 57 mil itens, abaixo
  de um milissegundo.
- **A lista de desenho é preparada uma vez, não por quadro.** O teto por região
  escolhe os mais longos primeiro, e por isso a ordenação por comprimento é o
  único pré-cálculo que sobra.
- **Pan e zoom não preparam nada**: re-traçam a lista sob outra transformação,
  a 15 ms. Preparar de novo só quando o zoom muda muito ou quando a máscara
  muda — e essa preparação, de ~500 ms, é fatiada entre quadros.

O código da grade continua em `medicao/indice.ts` de propósito: é o registro do
que foi medido e recusado, e sem ele a linha "a grade foi descartada" seria
afirmação sem prova.

## O que reabrir antes da tarefa 5

Isto é o achado, não a solução — a solução é decisão de projeto:

- O worker do plano (tarefas 5 e 6) deixa de se justificar como está descrito.
- O problema real é **não reconstruir todos os caminhos a cada mudança de
  opção**. As direções que a medição sugere, sem escolher entre elas: manter os
  `Path2D` montados uma vez e variar só o que é desenhado; recortar por região
  visível; desenhar em fatias ao longo de vários quadros; ou desistir do
  `Path2D` agrupado e traçar direto no contexto 2D.
- Se ainda assim houver worker, o que ele deve carregar é outra coisa que não o
  `select()`.
