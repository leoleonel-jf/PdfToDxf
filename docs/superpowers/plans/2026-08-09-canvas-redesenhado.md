# Etapa 3, parte 2 — o canvas redesenhado

> **Para quem executa com agentes:** SUB-SKILL OBRIGATÓRIA: use
> `superpowers:subagent-driven-development` (recomendado) ou
> `superpowers:executing-plans` para implementar tarefa a tarefa. Os passos usam
> caixas (`- [ ]`) para acompanhamento.

**Objetivo:** terminar a tela do conversor — desenhar a planta, girar opções
vendo a prévia mudar, calibrar por dois pontos e exportar o DXF — com o custo
por quadro dependendo do tamanho da janela, e não do tamanho da planta.

**Arquitetura:** uma thread. A lista do que desenhar é preparada uma vez, para
uma janela em volta do que está à vista, com teto por região escolhendo os
traços mais longos. Pan e zoom só re-traçam essa lista; preparar de novo só
acontece ao fim do gesto e só quando algo que a define mudou.

**Ferramental:** TypeScript, Vite, vitest, Playwright.

**Desenho que governa:**
`docs/superpowers/specs/2026-08-09-canvas-redesenho-design.md`.

## Como este plano se encaixa com o de 2026-08-04

O plano `docs/superpowers/plans/2026-08-04-frontend-canvas.md` **continua no
repositório e continua sendo a fonte do código** das tarefas que não mudaram.
Este documento não o repete: repetir 2 mil linhas criaria duas fontes de verdade
que divergiriam na primeira correção.

| Tarefa do plano de 2026-08-04 | Situação |
|---|---|
| 1 a 5 — andaime, `select.ts`, `estimativa.ts`, `formato.ts`, `intercalar` | **feitas**, commitadas, não mexer |
| 6 — `worker.ts` | **cancelada.** A medição mostrou que o worker protege a interface de uma pausa de 12 ms e deixa dentro a de 800 ms |
| 7 — `api.ts` | **executar como está** |
| 8 — `canvas.ts` | **substituída** pelas tarefas 1 a 4 deste plano |
| 9 — `calibrate.ts` (aritmética) | **executar como está** |
| 10 — `gestos.ts` | executar com a emenda da tarefa 5 deste plano |
| 11 — `estados.ts` e `estilo.css` | **executar como está** |
| 12 — `toolbar.ts` e `main.ts` | executar com as emendas da tarefa 6 deste plano |
| 13 — calibração na tela | **executar como está** |
| 14 — Playwright de ponta a ponta | **executar como está** |
| 15 — estáticos e Docker | **executar como está** |

**Ordem de execução:** tarefas 1 a 4 deste plano, depois a tarefa 7 do plano
antigo, depois a tarefa 5 deste, depois as tarefas 9 e 11 do antigo, depois a
tarefa 6 deste, e por fim as tarefas 13, 14 e 15 do antigo.

## Restrições globais

Valem para todas as tarefas; não repetidas em cada uma.

- **Idioma do código:** nomes de função, variável, arquivo e mensagem em
  português. Comentário explica *por quê*, não *o quê*.
- **Sem framework de interface e sem biblioteca de componentes.** CSS à mão com
  variáveis. Ícones em SVG embutido. Nada de gradiente, sombra ou animação
  decorativa.
- **Dependências de produção: zero.** Tudo no `package.json` é
  `devDependencies`. O que vai ao navegador é só código deste repositório.
- **Node 22, npm 10.**
- **Python:** sempre `./.venv/Scripts/python.exe`, nunca `python`.
- **Sem pytest.** Testes Python são funções com `assert` e um bloco
  `if __name__ == "__main__":`.
- **`tests/casos_select.json` não pode ser modificado.** Se o `git diff` dele
  sujar, o contrato quebrou.
- **Toda espera em teste é por condição, nunca por relógio.**
- **Diretório de trabalho do frontend:** `web/frontend/`. Todo `npm` roda de lá.
- **Nada proporcional ao número de entidades pode rodar a cada quadro.** É a
  regra que o desenho inteiro serve; qualquer laço novo sobre `n` dentro de um
  quadro é defeito.

## Constantes deste plano

```
LADO_REGIAO_PX = 4      lado da região do teto, em pixels
TETO_POR_REGIAO = 4     entidades por região
FOLGA_DA_JANELA = 0.5   meia tela para cada lado
FATOR_DE_ZOOM = 2       fora dessa faixa, prepara de novo
UM_POR_PONTO = 25.4 / 72 * 1000   = 352,7777… µm por ponto de papel
```

`UM_POR_PONTO` é onde se erra: `length_um` está em **micrômetros de papel** e as
coordenadas em **pontos**. Converter um pelo outro sem esse fator dá um limiar
352 vezes errado, e o sintoma é a tela em branco ou a tela cheia — nunca um erro.

---

### Tarefa 1: `ordem.ts`, o mais longo primeiro

**Arquivos:**
- Criar: `web/frontend/src/ordem.ts`
- Testar: `web/frontend/testes/ordem.test.ts`

**Interfaces:**
- Consome: nada
- Produz: `function ordenarPorComprimento(lengthUm: Uint32Array): Uint32Array`

- [ ] **Passo 1: escrever o teste que falha**

`web/frontend/testes/ordem.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { ordenarPorComprimento } from "../src/ordem.js";

describe("ordem.ts", () => {
  it("aceita array vazio", () => {
    expect([...ordenarPorComprimento(new Uint32Array(0))]).toEqual([]);
  });

  it("põe o mais longo primeiro", () => {
    const ordem = ordenarPorComprimento(Uint32Array.from([5, 100, 50, 1]));
    expect([...ordem]).toEqual([1, 2, 0, 3]);
  });

  it("empate mantém a ordem original — é estável", () => {
    // Sem estabilidade a lista de desenho mudaria de conteúdo entre execuções
    // com os mesmos dados, e nenhum teste de igualdade seria confiável.
    const ordem = ordenarPorComprimento(Uint32Array.from([7, 7, 9, 7]));
    expect([...ordem]).toEqual([2, 0, 1, 3]);
  });

  it("aguenta valores nos extremos do uint32", () => {
    const ordem = ordenarPorComprimento(
      Uint32Array.from([0, 0xffffffff, 0x10000, 0xffff]));
    expect([...ordem]).toEqual([1, 2, 3, 0]);
  });

  it("bate com uma ordenação de referência em dados variados", () => {
    const n = 5000;
    const comprimentos = new Uint32Array(n);
    let semente = 42;
    for (let i = 0; i < n; i++) {
      semente = (semente * 1664525 + 1013904223) >>> 0;
      comprimentos[i] = semente % 1000;      // empates de propósito
    }
    const obtido = [...ordenarPorComprimento(comprimentos)];
    const referencia = [...Array(n).keys()].sort((a, b) => {
      const d = comprimentos[b]! - comprimentos[a]!;
      return d !== 0 ? d : a - b;            // decrescente, estável
    });
    expect(obtido).toEqual(referencia);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/ordem.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/ordem.ts`**

```ts
/**
 * Ordem das entidades por comprimento decrescente.
 *
 * Existe por um motivo só: quando a lista de desenho preenche as vagas de cada
 * região, quem entra primeiro é o traço mais longo — o que mais se vê. Sem essa
 * ordem, o teto por região escolheria por acaso qual traço sobrevive.
 *
 * Radix de 16 bits em duas passadas, e não `sort` com comparador: o comparador
 * é uma chamada de função por comparação, e são dezenas de milhões delas em 3
 * milhões de entidades. Medido em ~250 ms.
 */

const BALDES = 65536;

export function ordenarPorComprimento(lengthUm: Uint32Array): Uint32Array {
  const n = lengthUm.length;
  let atual = new Uint32Array(n);
  for (let i = 0; i < n; i++) atual[i] = i;
  if (n === 0) return atual;

  // Ordenar pelo complemento e não inverter no fim: inverter destruiria a
  // estabilidade, e os empates sairiam em ordem inversa da original. Como a
  // lista de desenho é comparada em teste, isso viraria intermitência.
  const chave = new Uint32Array(n);
  for (let i = 0; i < n; i++) chave[i] = (0xffffffff - lengthUm[i]!) >>> 0;

  let outro = new Uint32Array(n);
  const contagem = new Uint32Array(BALDES);
  for (let passada = 0; passada < 2; passada++) {
    const deslocamento = passada * 16;
    contagem.fill(0);
    for (let i = 0; i < n; i++) {
      contagem[(chave[atual[i]!]! >>> deslocamento) & 0xffff]!++;
    }
    let soma = 0;
    for (let b = 0; b < BALDES; b++) {
      const c = contagem[b]!;
      contagem[b] = soma;
      soma += c;
    }
    for (let i = 0; i < n; i++) {
      const v = atual[i]!;
      outro[contagem[(chave[v]! >>> deslocamento) & 0xffff]!++] = v;
    }
    const troca = atual; atual = outro; outro = troca;
  }
  return atual;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os cinco testes novos verdes, e os 2058 anteriores intactos.

- [ ] **Passo 5: provar que o teste pega o defeito**

Troque, temporariamente, `chave[i] = (0xffffffff - lengthUm[i]!) >>> 0` por
`chave[i] = lengthUm[i]!` e inverta o resultado no fim com um laço. O teste do
empate tem de falhar — é ele que prende a estabilidade. Desfaça.

- [ ] **Passo 6: commit**

```bash
git add web/frontend/src/ordem.ts web/frontend/testes/ordem.test.ts
git commit -m "Ordem por comprimento decrescente, estavel, por radix de 16 bits"
```

---

### Tarefa 2: `canvas.ts`, a vista e o traçado de um lote

Vem antes do `lista.ts` porque é ele que define `Vista`, e a janela da lista é
descrita em coordenadas de papel derivadas da vista.

**Arquivos:**
- Criar: `web/frontend/src/canvas.ts`
- Criar: `web/frontend/testes/ajuda/canvas2d.ts`
- Testar: `web/frontend/testes/canvas.test.ts`

**Interfaces:**
- Consome: `Geometria`, `coordenadasDe`, `textoDe`, `SEM_COR` de
  `src/formato.ts`; `SEGMENTO` de `src/select.ts`
- Produz:
  - `type Vista = { escala: number; dx: number; dy: number }`
  - `type Retangulo = { x0: number; y0: number; x1: number; y1: number }`
  - `interface CaminhoDesenhavel { moveTo(x: number, y: number): void; lineTo(x: number, y: number): void; arc(cx: number, cy: number, r: number, a0: number, a1: number): void; bezierCurveTo(x1: number, y1: number, x2: number, y2: number, x3: number, y3: number): void; closePath(): void }`
  - `interface ContextoDesenhavel { save(): void; restore(): void; translate(x: number, y: number): void; rotate(a: number): void; clearRect(x: number, y: number, w: number, h: number): void; fillRect(x: number, y: number, w: number, h: number): void; fillText(t: string, x: number, y: number): void; stroke(c: CaminhoDesenhavel): void; lineWidth: number; strokeStyle: string; fillStyle: string; font: string }`
  - `function enquadrar(larguraPt: number, alturaPt: number, larguraTela: number, alturaTela: number): Vista`
  - `function pontoDaTela(v: Vista, x: number, y: number): { x: number; y: number }`
  - `function pontoDoPapel(v: Vista, x: number, y: number): { x: number; y: number }`
  - `function janelaVisivel(v: Vista, larguraTela: number, alturaTela: number, folga: number): Retangulo`
  - `function corDeInteiro(cor: number): string`
  - `function desenharLote(ctx: ContextoDesenhavel, g: Geometria, lote: Uint32Array, quantos: number, v: Vista, criarCaminho: () => CaminhoDesenhavel, limites: Retangulo): number`

`desenharLote` recebe a fábrica de caminhos em vez de chamar `new Path2D()`.
Não é abstração de enfeite: no vitest não existe `Path2D`, e injetar a fábrica é
o que permite gravar o que foi desenhado sem subir navegador. Ela devolve
**quantas entidades traçou**, que é o número que o teste compara com o lote.

- [ ] **Passo 1: o contexto de mentira, `web/frontend/testes/ajuda/canvas2d.ts`**

```ts
/** Caminho que grava o que mandaram desenhar, no lugar do Path2D do navegador. */
export class CaminhoGravado {
  readonly chamadas: Array<[string, ...number[]]> = [];
  moveTo(x: number, y: number) { this.chamadas.push(["moveTo", x, y]); }
  lineTo(x: number, y: number) { this.chamadas.push(["lineTo", x, y]); }
  arc(cx: number, cy: number, r: number, a0: number, a1: number) {
    this.chamadas.push(["arc", cx, cy, r, a0, a1]);
  }
  bezierCurveTo(x1: number, y1: number, x2: number, y2: number,
                x3: number, y3: number) {
    this.chamadas.push(["bezierCurveTo", x1, y1, x2, y2, x3, y3]);
  }
  closePath() { this.chamadas.push(["closePath"]); }

  /** Quantos traços começaram: um `moveTo` ou um `arc` por entidade. */
  get inicios(): number {
    return this.chamadas.filter((c) => c[0] === "moveTo" || c[0] === "arc").length;
  }
}

/** Contexto 2D de mentira, que guarda os caminhos traçados e os textos. */
export class ContextoGravado {
  lineWidth = 1;
  strokeStyle = "#000";
  fillStyle = "#000";
  font = "";
  readonly tracados: CaminhoGravado[] = [];
  readonly textos: Array<{ texto: string; x: number; y: number }> = [];
  readonly estilos: string[] = [];

  save() {}
  restore() {}
  translate(_x: number, _y: number) {}
  rotate(_a: number) {}
  clearRect(_x: number, _y: number, _w: number, _h: number) {}
  fillRect(_x: number, _y: number, _w: number, _h: number) {}
  fillText(t: string, x: number, y: number) { this.textos.push({ texto: t, x, y }); }
  stroke(c: CaminhoGravado) {
    this.tracados.push(c);
    this.estilos.push(this.strokeStyle);
  }

  /** Total de entidades traçadas, somando todos os caminhos. */
  get inicios(): number {
    return this.tracados.reduce((soma, c) => soma + c.inicios, 0);
  }
}
```

- [ ] **Passo 2: escrever o teste que falha**

`web/frontend/testes/canvas.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  desenharLote, enquadrar, janelaVisivel, pontoDaTela, pontoDoPapel,
} from "../src/canvas.js";
import { lerGeometria } from "../src/formato.js";
import { CaminhoGravado, ContextoGravado } from "./ajuda/canvas2d.js";

function fixture(nome: string): string {
  return fileURLToPath(new URL(`../../../tests/fixtures/${nome}`, import.meta.url));
}
const cru = readFileSync(fixture("geometria_exemplo.bin"));
const buffer = cru.buffer.slice(cru.byteOffset, cru.byteOffset + cru.byteLength);
const esperado = JSON.parse(readFileSync(fixture("geometria_exemplo.json"), "utf-8"));
const g = lerGeometria(buffer as ArrayBuffer, esperado.layers, esperado.n_groups);

const TODA_A_FOLHA = { x0: -1e9, y0: -1e9, x1: 1e9, y1: 1e9 };

describe("canvas.ts — a vista", () => {
  it("enquadra a folha inteira, centrada, sem distorcer", () => {
    const v = enquadrar(595, 842, 1000, 800);
    // Cabe pela altura: 800/842 é menor que 1000/595.
    expect(v.escala).toBeCloseTo(800 / 842, 10);
    const canto = pontoDaTela(v, 0, 0);
    const oposto = pontoDaTela(v, 595, 842);
    expect(canto.y).toBeCloseTo(0, 6);
    expect(oposto.y).toBeCloseTo(800, 6);
    // Sobra na horizontal, dividida igualmente.
    expect(canto.x).toBeCloseTo(1000 - oposto.x, 6);
  });

  it("ida e volta entre papel e tela devolve o mesmo ponto", () => {
    const v = enquadrar(595, 842, 1000, 800);
    const t = pontoDaTela(v, 123.5, 456.25);
    const p = pontoDoPapel(v, t.x, t.y);
    expect(p.x).toBeCloseTo(123.5, 6);
    expect(p.y).toBeCloseTo(456.25, 6);
  });

  it("a janela com folga é maior que a visível, na proporção pedida", () => {
    const v = enquadrar(595, 842, 1000, 800);
    const justa = janelaVisivel(v, 1000, 800, 0);
    const folgada = janelaVisivel(v, 1000, 800, 0.5);
    const larguraJusta = justa.x1 - justa.x0;
    expect(folgada.x1 - folgada.x0).toBeCloseTo(larguraJusta * 2, 6);
    // Cresce para os dois lados, mantendo o centro.
    expect((folgada.x0 + folgada.x1) / 2).toBeCloseTo((justa.x0 + justa.x1) / 2, 6);
  });
});

describe("canvas.ts — o traçado", () => {
  const v = enquadrar(595, 842, 1000, 800);

  it("traça exatamente as entidades do lote", () => {
    const lote = Uint32Array.from([0, 2, 5]);
    const ctx = new ContextoGravado();
    const quantos = desenharLote(ctx, g, lote, lote.length, v,
                                 () => new CaminhoGravado(), TODA_A_FOLHA);
    expect(quantos).toBe(3);
    expect(ctx.inicios).toBe(3);
  });

  it("respeita o `quantos`, para o pintor poder desenhar meio lote", () => {
    const lote = Uint32Array.from([0, 2, 5]);
    const ctx = new ContextoGravado();
    expect(desenharLote(ctx, g, lote, 1, v,
                        () => new CaminhoGravado(), TODA_A_FOLHA)).toBe(1);
    expect(ctx.inicios).toBe(1);
  });

  it("descarta o que está fora dos limites", () => {
    const lote = Uint32Array.from([0, 2, 5]);
    const ctx = new ContextoGravado();
    const longe = { x0: 10_000, y0: 10_000, x1: 20_000, y1: 20_000 };
    expect(desenharLote(ctx, g, lote, lote.length, v,
                        () => new CaminhoGravado(), longe)).toBe(0);
  });

  it("separa por cor: duas cores dão dois traçados", () => {
    // A entidade 0 é vermelha e a 5 não tem cor; ambas do layer PAREDES.
    const ctx = new ContextoGravado();
    desenharLote(ctx, g, Uint32Array.from([0, 5]), 2, v,
                 () => new CaminhoGravado(), TODA_A_FOLHA);
    expect(new Set(ctx.estilos).size).toBe(2);
  });

  it("o texto sai pelo fillText, com o conteúdo acentuado", () => {
    const ctx = new ContextoGravado();
    desenharLote(ctx, g, Uint32Array.from([4]), 1, v,
                 () => new CaminhoGravado(), TODA_A_FOLHA);
    expect(ctx.textos.map((t) => t.texto)).toEqual(["Sala de máquinas"]);
  });
});
```

- [ ] **Passo 3: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/canvas.ts`.

- [ ] **Passo 4: implementar `web/frontend/src/canvas.ts`**

```ts
/**
 * A vista — a conversão entre papel e tela — e o traçado de um lote pronto.
 *
 * Este arquivo não conhece lista, orçamento nem gesto. Ele recebe um lote de
 * índices e uma vista, e traça. É essa fronteira que permite provar, sem
 * navegador, que o desenhado corresponde ao escolhido.
 */
import { SEGMENTO } from "./select.js";
import { coordenadasDe, textoDe, SEM_COR, type Geometria } from "./formato.js";

const POLILINHA = 1, ARCO = 2, BEZIER = 3, TEXTO = 4;

export type Vista = { escala: number; dx: number; dy: number };
export type Retangulo = { x0: number; y0: number; x1: number; y1: number };

export interface CaminhoDesenhavel {
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  arc(cx: number, cy: number, r: number, a0: number, a1: number): void;
  bezierCurveTo(x1: number, y1: number, x2: number, y2: number,
                x3: number, y3: number): void;
  closePath(): void;
}

export interface ContextoDesenhavel {
  save(): void;
  restore(): void;
  translate(x: number, y: number): void;
  rotate(a: number): void;
  clearRect(x: number, y: number, w: number, h: number): void;
  fillRect(x: number, y: number, w: number, h: number): void;
  fillText(t: string, x: number, y: number): void;
  stroke(c: CaminhoDesenhavel): void;
  lineWidth: number;
  // A união vem do DOM: `CanvasRenderingContext2D.strokeStyle` aceita gradiente
  // e padrão além de texto. Declarar só `string` aqui faria o contexto de
  // verdade não caber nesta interface, e só o de mentira caberia — que é
  // exatamente o contrário do que ela serve para provar.
  strokeStyle: string | CanvasGradient | CanvasPattern;
  fillStyle: string | CanvasGradient | CanvasPattern;
  font: string;
}

export function enquadrar(larguraPt: number, alturaPt: number,
                          larguraTela: number, alturaTela: number): Vista {
  const escala = Math.min(larguraTela / larguraPt, alturaTela / alturaPt);
  return {
    escala,
    dx: (larguraTela - larguraPt * escala) / 2,
    dy: (alturaTela - alturaPt * escala) / 2,
  };
}

export function pontoDaTela(v: Vista, x: number, y: number) {
  return { x: x * v.escala + v.dx, y: y * v.escala + v.dy };
}

export function pontoDoPapel(v: Vista, x: number, y: number) {
  return { x: (x - v.dx) / v.escala, y: (y - v.dy) / v.escala };
}

/**
 * O retângulo de papel que a tela mostra, alargado por `folga` telas de cada
 * lado. `folga = 0.5` dá quatro vezes a área visível — é a janela da lista.
 */
export function janelaVisivel(v: Vista, larguraTela: number, alturaTela: number,
                              folga: number): Retangulo {
  const a = pontoDoPapel(v, 0, 0);
  const b = pontoDoPapel(v, larguraTela, alturaTela);
  const margemX = (b.x - a.x) * folga;
  const margemY = (b.y - a.y) * folga;
  return {
    x0: a.x - margemX, y0: a.y - margemY,
    x1: b.x + margemX, y1: b.y + margemY,
  };
}

export function corDeInteiro(cor: number): string {
  if (cor === SEM_COR) return "#111";
  return "#" + (cor & 0xffffff).toString(16).padStart(6, "0");
}

/** Chave de agrupamento: mesmo layer e mesma cor vão no mesmo caminho. */
function chaveDe(g: Geometria, i: number): number {
  // `cor` cabe em 24 bits úteis; o layer entra acima dela. Multiplicar em vez
  // de deslocar porque `<<` em JavaScript trabalha em 32 bits com sinal, e o
  // layer estouraria isso numa planta com muitos layers.
  return g.layer_id[i]! * 0x1000000 + (g.cor[i]! & 0xffffff);
}

/**
 * Traça as `quantos` primeiras entidades de `lote`, descartando o que cai fora
 * de `limites`. Devolve quantas traçou de fato.
 *
 * O `quantos` existe para o pintor poder desenhar meio lote num quadro e o
 * resto no seguinte, sem fatiar o array.
 */
export function desenharLote(ctx: ContextoDesenhavel, g: Geometria,
                             lote: Uint32Array, quantos: number, v: Vista,
                             criarCaminho: () => CaminhoDesenhavel,
                             limites: Retangulo): number {
  const porChave = new Map<number, { caminho: CaminhoDesenhavel; cor: number }>();
  const textos: Array<{ i: number; c: Float32Array }> = [];
  let tracadas = 0;

  for (let k = 0; k < quantos; k++) {
    const i = lote[k]!;
    const c = coordenadasDe(g, i);
    if (foraDos(limites, g, i, c)) continue;

    const tipo = g.kind[i]!;
    if (tipo === TEXTO) {
      textos.push({ i, c });
      tracadas++;
      continue;
    }

    const chave = chaveDe(g, i);
    let grupo = porChave.get(chave);
    if (!grupo) {
      grupo = { caminho: criarCaminho(), cor: g.cor[i]! };
      porChave.set(chave, grupo);
    }
    tracarNoCaminho(grupo.caminho, tipo, c, v);
    tracadas++;
  }

  ctx.lineWidth = 1;
  for (const grupo of porChave.values()) {
    ctx.strokeStyle = corDeInteiro(grupo.cor);
    ctx.stroke(grupo.caminho);
  }

  for (const { i, c } of textos) {
    const p = pontoDaTela(v, c[0]!, c[1]!);
    const altura = c[2]! * v.escala;
    ctx.save();
    ctx.translate(p.x, p.y);
    // O papel tem Y para cima e a tela para baixo, então o giro inverte.
    ctx.rotate((-c[3]! * Math.PI) / 180);
    ctx.fillStyle = corDeInteiro(g.cor[i]!);
    ctx.font = `${altura}px sans-serif`;
    ctx.fillText(textoDe(g, i), 0, 0);
    ctx.restore();
  }

  return tracadas;
}

/** Caixa da entidade contra os limites, em coordenadas de papel. */
function foraDos(limites: Retangulo, g: Geometria, i: number,
                 c: Float32Array): boolean {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  const tipo = g.kind[i]!;
  if (tipo === ARCO) {
    // Caixa do círculo inteiro: mais folgada que o arco real, e barata. Errar
    // para o lado de desenhar demais só custa tempo; para o outro, some traço.
    const r = c[2]!;
    minx = c[0]! - r; maxx = c[0]! + r;
    miny = c[1]! - r; maxy = c[1]! + r;
  } else if (tipo === TEXTO) {
    minx = c[0]!; maxx = c[0]! + c[4]!;
    miny = c[1]!; maxy = c[1]! + c[2]!;
  } else {
    const inicio = tipo === POLILINHA ? 1 : 0;
    for (let p = inicio; p + 1 < c.length; p += 2) {
      const x = c[p]!, y = c[p + 1]!;
      if (x < minx) minx = x;
      if (x > maxx) maxx = x;
      if (y < miny) miny = y;
      if (y > maxy) maxy = y;
    }
  }
  return maxx < limites.x0 || minx > limites.x1 ||
         maxy < limites.y0 || miny > limites.y1;
}

function tracarNoCaminho(caminho: CaminhoDesenhavel, tipo: number,
                         c: Float32Array, v: Vista): void {
  if (tipo === SEGMENTO) {
    const a = pontoDaTela(v, c[0]!, c[1]!);
    const b = pontoDaTela(v, c[2]!, c[3]!);
    caminho.moveTo(a.x, a.y);
    caminho.lineTo(b.x, b.y);
    return;
  }
  if (tipo === POLILINHA) {
    // c[0] é o "fechada"; os pontos começam em c[1].
    const primeiro = pontoDaTela(v, c[1]!, c[2]!);
    caminho.moveTo(primeiro.x, primeiro.y);
    for (let p = 3; p + 1 < c.length; p += 2) {
      const q = pontoDaTela(v, c[p]!, c[p + 1]!);
      caminho.lineTo(q.x, q.y);
    }
    if (c[0]! !== 0) caminho.closePath();
    return;
  }
  if (tipo === ARCO) {
    const centro = pontoDaTela(v, c[0]!, c[1]!);
    // Os ângulos do DXF são anti-horários com Y para cima; o canvas é horário
    // com Y para baixo. Trocar o sinal converte os dois de uma vez.
    caminho.arc(centro.x, centro.y, c[2]! * v.escala,
                (-c[3]! * Math.PI) / 180, (-c[4]! * Math.PI) / 180);
    return;
  }
  if (tipo === BEZIER) {
    const p0 = pontoDaTela(v, c[0]!, c[1]!);
    const p1 = pontoDaTela(v, c[2]!, c[3]!);
    const p2 = pontoDaTela(v, c[4]!, c[5]!);
    const p3 = pontoDaTela(v, c[6]!, c[7]!);
    caminho.moveTo(p0.x, p0.y);
    caminho.bezierCurveTo(p1.x, p1.y, p2.x, p2.y, p3.x, p3.y);
  }
}
```

- [ ] **Passo 5: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os oito testes novos verdes.

- [ ] **Passo 6: commit**

```bash
git add web/frontend/src/canvas.ts web/frontend/testes/canvas.test.ts \
        web/frontend/testes/ajuda/canvas2d.ts
git commit -m "Vista papel-tela e o tracado de um lote, contra contexto 2D falso"
```

---

### Tarefa 3: `lista.ts`, o coração do desenho

A tarefa mais importante deste plano. É ela que faz o custo depender da janela e
não da planta.

**Arquivos:**
- Criar: `web/frontend/src/lista.ts`
- Testar: `web/frontend/testes/lista.test.ts`

**Interfaces:**
- Consome: `Geometria`, `coordenadasDe` de `src/formato.ts`; `Vista`,
  `Retangulo` de `src/canvas.ts`
- Produz:
  - `const LADO_REGIAO_PX = 4`
  - `const TETO_POR_REGIAO = 4`
  - `const FOLGA_DA_JANELA = 0.5`
  - `const UM_POR_PONTO = (25.4 / 72) * 1000`
  - `const FATOR_DE_ZOOM = 2`
  - `type Preparo = { janela: Retangulo; escala: number; lista: Uint32Array; quantos: number; cursor: number; pronto: boolean; ocupacao: Uint8Array; colunas: number; linhas: number; ladoPt: number }`
  - `function iniciarPreparo(g: Geometria, janela: Retangulo, escala: number): Preparo`
  - `function avancarPreparo(p: Preparo, g: Geometria, mascara: Uint8Array, ordem: Uint32Array, orcamento: number): Preparo`
  - `function prepararTudo(g: Geometria, mascara: Uint8Array, ordem: Uint32Array, janela: Retangulo, escala: number): Preparo`
  - `function precisaPreparar(p: Preparo, v: Vista, larguraTela: number, alturaTela: number): boolean`

`avancarPreparo` consome no máximo `orcamento` entidades da ordem e devolve o
mesmo objeto com o cursor adiantado; `prepararTudo` é o laço até o fim, e existe
para o teste comparar o fatiado com o inteiro.

- [ ] **Passo 1: escrever o teste que falha**

`web/frontend/testes/lista.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { janelaVisivel, enquadrar, type Retangulo } from "../src/canvas.js";
import { ordenarPorComprimento } from "../src/ordem.js";
import {
  avancarPreparo, iniciarPreparo, prepararTudo, precisaPreparar,
  TETO_POR_REGIAO, UM_POR_PONTO,
} from "../src/lista.js";
import type { Geometria } from "../src/formato.js";

/**
 * Segmentos sintéticos, todos no mesmo layer, com posição e comprimento dados.
 * Monta só o que a lista lê — é de propósito: se `lista.ts` passar a depender
 * de outro campo, este auxiliar deixa de compilar e o autor fica sabendo.
 */
function geometriaDe(segs: Array<[number, number, number, number]>): Geometria {
  const n = segs.length;
  const coords = new Float32Array(n * 4);
  const length_um = new Uint32Array(n);
  const coord_off = new Uint32Array(n + 1);
  for (let i = 0; i < n; i++) {
    const [x1, y1, x2, y2] = segs[i]!;
    coords.set([x1, y1, x2, y2], i * 4);
    coord_off[i + 1] = (i + 1) * 4;
    length_um[i] = Math.round(Math.hypot(x2 - x1, y2 - y1) * UM_POR_PONTO);
  }
  return {
    n, layers: ["0"], n_groups: n,
    idx: Uint32Array.from({ length: n }, (_, i) => i),
    kind: new Uint8Array(n),                 // tudo Segment
    layer_id: new Uint32Array(n),
    is_fill: new Uint8Array(n),
    length_um,
    dup_group: Int32Array.from({ length: n }, (_, i) => i),
    byte_cost: new Uint32Array(n),
    cor: new Uint32Array(n).fill(0xffffffff),
    coord_off, coords,
    texto_off: new Uint32Array(n + 1),
    texto: new Uint8Array(0),
  };
}

const FOLHA: Retangulo = { x0: 0, y0: 0, x1: 100, y1: 100 };

describe("lista.ts", () => {
  it("nunca passa do teto por região", () => {
    // Dez segmentos empilhados no mesmo ponto: uma região só.
    const g = geometriaDe(Array.from({ length: 10 },
                                     (_, i) => [1, 1, 1 + i * 0.01, 1] as
                                       [number, number, number, number]));
    const ordem = ordenarPorComprimento(g.length_um);
    const p = prepararTudo(g, new Uint8Array(10).fill(1), ordem, FOLHA, 1);
    expect(p.quantos).toBe(TETO_POR_REGIAO);
  });

  it("entre candidatos da mesma região, fica o mais comprido", () => {
    const g = geometriaDe([[1, 1, 1.5, 1], [1, 1, 9, 1], [1, 1, 3, 1]]);
    const ordem = ordenarPorComprimento(g.length_um);
    // Teto de 4, mas só três candidatos: entram todos, na ordem do mais longo.
    const p = prepararTudo(g, new Uint8Array(3).fill(1), ordem, FOLHA, 1);
    expect([...p.lista.subarray(0, p.quantos)]).toEqual([1, 2, 0]);
  });

  it("nunca inclui o que a máscara zerou", () => {
    const g = geometriaDe([[1, 1, 9, 1], [50, 50, 58, 50]]);
    const ordem = ordenarPorComprimento(g.length_um);
    const mascara = Uint8Array.from([0, 1]);
    const p = prepararTudo(g, mascara, ordem, FOLHA, 1);
    expect([...p.lista.subarray(0, p.quantos)]).toEqual([1]);
  });

  it("quem não é segmento entra sempre, sem disputar vaga", () => {
    // Dez segmentos empilhados mais um texto no mesmo ponto: os segmentos são
    // cortados pelo teto, o texto não.
    const g = geometriaDe(Array.from({ length: 11 },
                                     (_, i) => [1, 1, 1 + i * 0.01, 1] as
                                       [number, number, number, number]));
    g.kind[10] = 4;                    // TextItem
    const ordem = ordenarPorComprimento(g.length_um);
    const p = prepararTudo(g, new Uint8Array(11).fill(1), ordem, FOLHA, 1);
    const escolhidos = [...p.lista.subarray(0, p.quantos)];
    expect(escolhidos).toContain(10);
    expect(escolhidos.filter((i) => i !== 10).length).toBe(TETO_POR_REGIAO);
  });

  it("não inclui o que está fora da janela", () => {
    const g = geometriaDe([[1, 1, 9, 1], [500, 500, 508, 500]]);
    const ordem = ordenarPorComprimento(g.length_um);
    const p = prepararTudo(g, new Uint8Array(2).fill(1), ordem, FOLHA, 1);
    expect([...p.lista.subarray(0, p.quantos)]).toEqual([0]);
  });

  it("fatiado dá exatamente a mesma lista que inteiro", () => {
    // O teste que impede o desenho de depender da velocidade da máquina.
    const segs: Array<[number, number, number, number]> = [];
    let semente = 7;
    const sorteio = () => {
      semente = (semente * 1664525 + 1013904223) >>> 0;
      return semente / 4294967296;
    };
    for (let i = 0; i < 4000; i++) {
      const x = sorteio() * 100, y = sorteio() * 100;
      const c = 0.05 + sorteio() * 5;
      segs.push([x, y, x + c, y + c / 2]);
    }
    const g = geometriaDe(segs);
    const mascara = Uint8Array.from({ length: segs.length },
                                    (_, i) => (i % 7 === 0 ? 0 : 1));
    const ordem = ordenarPorComprimento(g.length_um);

    const inteiro = prepararTudo(g, mascara, ordem, FOLHA, 1);

    let fatiado = iniciarPreparo(g, FOLHA, 1);
    let voltas = 0;
    while (!fatiado.pronto) {
      fatiado = avancarPreparo(fatiado, g, mascara, ordem, 37);
      voltas++;
    }
    expect(voltas).toBeGreaterThan(1);   // fatiou de verdade
    expect(fatiado.quantos).toBe(inteiro.quantos);
    expect([...fatiado.lista.subarray(0, fatiado.quantos)])
      .toEqual([...inteiro.lista.subarray(0, inteiro.quantos)]);
  });

  it("a lista não cresce quando o zoom fecha", () => {
    // É a razão de a janela existir. Com a folha inteira e com zoom de 20x, o
    // número de regiões é o mesmo, então a lista fica na mesma ordem.
    const segs: Array<[number, number, number, number]> = [];
    let semente = 99;
    const sorteio = () => {
      semente = (semente * 1664525 + 1013904223) >>> 0;
      return semente / 4294967296;
    };
    for (let i = 0; i < 20000; i++) {
      const x = sorteio() * 100, y = sorteio() * 100;
      segs.push([x, y, x + 0.3, y + 0.1]);
    }
    const g = geometriaDe(segs);
    const mascara = new Uint8Array(segs.length).fill(1);
    const ordem = ordenarPorComprimento(g.length_um);

    const larga = prepararTudo(g, mascara, ordem, FOLHA, 1);
    const perto = prepararTudo(g, mascara, ordem,
                               { x0: 40, y0: 40, x1: 45, y1: 45 }, 20);
    expect(perto.quantos).toBeLessThanOrEqual(larga.quantos * 2);
  });

  it("sabe dizer quando a vista saiu da janela", () => {
    const g = geometriaDe([[1, 1, 9, 1]]);
    const ordem = ordenarPorComprimento(g.length_um);
    const v = enquadrar(100, 100, 400, 400);
    const janela = janelaVisivel(v, 400, 400, 0.5);
    const p = prepararTudo(g, new Uint8Array(1).fill(1), ordem, janela, v.escala);

    expect(precisaPreparar(p, v, 400, 400)).toBe(false);
    // Zoom de 4x sai da faixa do fator 2.
    expect(precisaPreparar(p, { ...v, escala: v.escala * 4 }, 400, 400)).toBe(true);
    // Arrastar uma tela inteira sai da janela de meia tela de folga.
    expect(precisaPreparar(p, { ...v, dx: v.dx - 400 }, 400, 400)).toBe(true);
    // Arrastar um quarto de tela continua dentro.
    expect(precisaPreparar(p, { ...v, dx: v.dx - 100 }, 400, 400)).toBe(false);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/lista.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/lista.ts`**

```ts
/**
 * A lista do que desenhar, preparada uma vez.
 *
 * A regra que este arquivo serve: nada proporcional ao número de entidades pode
 * acontecer a cada quadro. Preparar a lista **é** proporcional, e é caro — por
 * isso acontece uma vez, fatiado entre quadros, e não a cada quadro.
 *
 * Duas escolhas que parecem detalhe e não são:
 *
 * - **A lista cobre uma janela, não a folha inteira.** Com regiões do tamanho
 *   de poucos pixels, a folha inteira no zoom fechado teria mais regiões do que
 *   entidades: o teto não cortaria nada e a lista voltaria ao tamanho da planta.
 * - **A ordem de percurso é a de comprimento decrescente.** É o que faz o traço
 *   que mais se vê ocupar a vaga da região, em vez de quem chegar primeiro.
 */
import { coordenadasDe, type Geometria } from "./formato.js";
import { SEGMENTO } from "./select.js";
import type { Retangulo, Vista } from "./canvas.js";

export const LADO_REGIAO_PX = 4;
export const TETO_POR_REGIAO = 4;
export const FOLGA_DA_JANELA = 0.5;
export const FATOR_DE_ZOOM = 2;

/** 1 pt = 1/72 pol = 25,4/72 mm. `length_um` está em micrômetros de papel. */
export const UM_POR_PONTO = (25.4 / 72) * 1000;

export type Preparo = {
  janela: Retangulo;
  escala: number;
  lista: Uint32Array;
  quantos: number;
  cursor: number;
  pronto: boolean;
  // Privados na prática; ficam no objeto para o preparo ser retomável sem que
  // `lista.ts` guarde estado próprio entre chamadas.
  ocupacao: Uint8Array;
  colunas: number;
  linhas: number;
  ladoPt: number;
};

export function iniciarPreparo(g: Geometria, janela: Retangulo,
                               escala: number): Preparo {
  const ladoPt = LADO_REGIAO_PX / escala;
  const colunas = Math.max(1, Math.ceil((janela.x1 - janela.x0) / ladoPt));
  const linhas = Math.max(1, Math.ceil((janela.y1 - janela.y0) / ladoPt));
  const teto = colunas * linhas * TETO_POR_REGIAO;
  return {
    janela, escala,
    // A lista nunca passa de `teto`, e nunca precisa de mais vagas que
    // entidades. `Math.min` evita reservar dezenas de megabytes numa página
    // pequena vista de muito perto.
    lista: new Uint32Array(Math.min(teto, g.n)),
    quantos: 0,
    cursor: 0,
    pronto: g.n === 0,
    ocupacao: new Uint8Array(colunas * linhas),
    colunas, linhas, ladoPt,
  };
}

/**
 * Consome no máximo `orcamento` entidades da ordem e devolve o preparo
 * adiantado. O resultado não depende de como o orçamento foi dividido: o
 * percurso é sempre o mesmo e o cursor só anda para a frente.
 */
export function avancarPreparo(p: Preparo, g: Geometria, mascara: Uint8Array,
                               ordem: Uint32Array, orcamento: number): Preparo {
  const fim = Math.min(ordem.length, p.cursor + orcamento);
  for (let k = p.cursor; k < fim; k++) {
    const i = ordem[k]!;
    if (!mascara[i]) continue;
    const c = coordenadasDe(g, i);
    if (c.length < 2) continue;

    // O ponto de referência é o primeiro da entidade. Basta: a região existe
    // para espalhar o traço pela folha, não para recortá-lo com precisão — quem
    // recorta é o `desenharLote`, pela caixa inteira.
    const x = c[0]!, y = c[1]!;
    if (x < p.janela.x0 || x > p.janela.x1 ||
        y < p.janela.y0 || y > p.janela.y1) continue;

    let coluna = Math.floor((x - p.janela.x0) / p.ladoPt);
    let linha = Math.floor((y - p.janela.y0) / p.ladoPt);
    if (coluna < 0) coluna = 0; else if (coluna >= p.colunas) coluna = p.colunas - 1;
    if (linha < 0) linha = 0; else if (linha >= p.linhas) linha = p.linhas - 1;

    if (p.quantos >= p.lista.length) continue;

    // Quem não é segmento entra sempre, sem disputar vaga: texto, arco,
    // polilinha e curva são poucos e são a leitura do desenho. Deixá-los
    // competir faria uma cota sumir junto de mil tracinhos de hachura.
    if (g.kind[i] !== SEGMENTO) {
      p.lista[p.quantos++] = i;
      continue;
    }

    const regiao = linha * p.colunas + coluna;
    if (p.ocupacao[regiao]! >= TETO_POR_REGIAO) continue;
    p.ocupacao[regiao]!++;
    p.lista[p.quantos++] = i;
  }
  p.cursor = fim;
  p.pronto = fim >= ordem.length;
  return p;
}

/** O preparo inteiro, de uma vez. O teste compara este com o fatiado. */
export function prepararTudo(g: Geometria, mascara: Uint8Array,
                             ordem: Uint32Array, janela: Retangulo,
                             escala: number): Preparo {
  const p = iniciarPreparo(g, janela, escala);
  return avancarPreparo(p, g, mascara, ordem, ordem.length);
}

/**
 * A vista saiu do que a lista cobre?
 *
 * Duas razões, e as duas importam: o zoom passou da faixa do fator 2, ou o
 * retângulo visível deixou de caber na janela preparada.
 */
export function precisaPreparar(p: Preparo, v: Vista, larguraTela: number,
                                alturaTela: number): boolean {
  const razao = v.escala / p.escala;
  if (razao >= FATOR_DE_ZOOM || razao <= 1 / FATOR_DE_ZOOM) return true;
  const x0 = (0 - v.dx) / v.escala;
  const y0 = (0 - v.dy) / v.escala;
  const x1 = (larguraTela - v.dx) / v.escala;
  const y1 = (alturaTela - v.dy) / v.escala;
  return x0 < p.janela.x0 || y0 < p.janela.y0 ||
         x1 > p.janela.x1 || y1 > p.janela.y1;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os sete testes novos verdes.

- [ ] **Passo 5: provar que o teste do fatiamento pega o defeito**

Troque, temporariamente, `p.cursor = fim` por `p.cursor = fim + 1`. O teste
"fatiado dá exatamente a mesma lista que inteiro" tem de falhar — ele existe
para pegar exatamente esse tipo de erro, que numa máquina rápida nunca
apareceria porque o orçamento cobriria tudo numa volta só. Desfaça.

- [ ] **Passo 6: confirmar os dois números na página de medição**

O spec fixa `LADO_REGIAO_PX = 4` e `TETO_POR_REGIAO = 4` a partir do protótipo,
e manda esta tarefa confirmar com a implementação de verdade.

Crie `web/frontend/medicao/preparo.html`, igual ao `indice.html` mas apontando
para `./preparo.ts`, e `web/frontend/medicao/preparo.ts`:

```ts
/**
 * O `lista.ts` de verdade, sobre 3 milhões de entidades.
 *
 * O protótipo do `indice.ts` mediu um esboço; este mede o que vai rodar. É o
 * passo que confirma ou derruba o par (lado da região, teto) que o spec fixou.
 */
export {};

import { enquadrar, janelaVisivel, desenharLote } from "../src/canvas.js";
import { ordenarPorComprimento } from "../src/ordem.js";
import { prepararTudo, FOLGA_DA_JANELA, UM_POR_PONTO } from "../src/lista.js";
import type { Geometria } from "../src/formato.js";

const N = 3_000_000;
const LARGURA_PAPEL = 595, ALTURA_PAPEL = 842;

const tela = document.querySelector<HTMLCanvasElement>("#tela")!;
const ctx = tela.getContext("2d")!;
const linhas: string[] = [];
const mostrar = () => {
  document.querySelector("#saida")!.textContent = linhas.join("\n");
};

let semente = 123456789;
const sorteio = () => {
  semente = (semente * 1664525 + 1013904223) >>> 0;
  return semente / 4294967296;
};

/** Mesma distribuição log-uniforme da terceira medição, para comparar. */
function gerar(): Geometria {
  const coords = new Float32Array(N * 4);
  const coord_off = new Uint32Array(N + 1);
  const length_um = new Uint32Array(N);
  const layer_id = new Uint32Array(N);
  const lnMin = Math.log(0.05), lnMax = Math.log(100);
  for (let i = 0; i < N; i++) {
    const comprimento = Math.exp(lnMin + sorteio() * (lnMax - lnMin));
    const angulo = sorteio() * Math.PI * 2;
    const x = sorteio() * LARGURA_PAPEL, y = sorteio() * ALTURA_PAPEL;
    coords.set([x, y, x + Math.cos(angulo) * comprimento,
                y + Math.sin(angulo) * comprimento], i * 4);
    coord_off[i + 1] = (i + 1) * 4;
    length_um[i] = Math.round(comprimento * UM_POR_PONTO);
    layer_id[i] = i % 8;
  }
  return {
    n: N, layers: ["0"], n_groups: N,
    idx: Uint32Array.from({ length: N }, (_, i) => i),
    kind: new Uint8Array(N), layer_id, is_fill: new Uint8Array(N),
    length_um,
    dup_group: Int32Array.from({ length: N }, (_, i) => i),
    byte_cost: new Uint32Array(N),
    cor: new Uint32Array(N).fill(0xffffffff),
    coord_off, coords,
    texto_off: new Uint32Array(N + 1), texto: new Uint8Array(0),
  };
}

function cronometrar<T>(nome: string, vezes: number, f: () => T): T {
  const gastos: number[] = [];
  let r: T = undefined as T;
  for (let k = 0; k < vezes; k++) {
    const inicio = performance.now();
    r = f();
    gastos.push(performance.now() - inicio);
  }
  linhas.push(`${nome}: ${gastos.map((g) => g.toFixed(0)).join(" / ")} ms`);
  mostrar();
  return r;
}

const g = cronometrar("gerar 3M", 1, gerar);
const mascara = new Uint8Array(N).fill(1);
const ordem = cronometrar("ordenarPorComprimento", 2,
                          () => ordenarPorComprimento(g.length_um));

for (const [nome, escala] of [
  ["folha inteira", Math.min(tela.width / LARGURA_PAPEL,
                             tela.height / ALTURA_PAPEL)],
  ["zoom 4x", 4 * Math.min(tela.width / LARGURA_PAPEL,
                           tela.height / ALTURA_PAPEL)],
  ["zoom 16x", 16 * Math.min(tela.width / LARGURA_PAPEL,
                             tela.height / ALTURA_PAPEL)],
] as [string, number][]) {
  const v = enquadrar(LARGURA_PAPEL, ALTURA_PAPEL, tela.width, tela.height);
  v.escala = escala;
  const janela = janelaVisivel(v, tela.width, tela.height, FOLGA_DA_JANELA);
  const visivel = janelaVisivel(v, tela.width, tela.height, 0);

  const p = cronometrar(`${nome} | prepararTudo`, 2,
                        () => prepararTudo(g, mascara, ordem, janela, escala));
  linhas[linhas.length - 1] += `   (lista de ${p.quantos.toLocaleString("pt-BR")})`;

  cronometrar(`${nome} | um quadro`, 5, () => {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, tela.width, tela.height);
    desenharLote(ctx, g, p.lista, p.quantos, v, () => new Path2D(), visivel);
    ctx.getImageData(0, 0, 1, 1);   // força a rasterização a terminar
  });
}

linhas.push(`navegador: ${navigator.userAgent}`);
mostrar();
```

Rode:

```bash
cd web/frontend && npm run dev
```

e abra `http://localhost:5173/medicao/preparo.html`.

**Critério, e ele decide:** o "um quadro" tem de ficar **abaixo de 33 ms** nos
três zooms. Se `TETO_POR_REGIAO = 4` passar disso, troque para `2` no
`lista.ts`, rode `npm test` de novo — o teste do teto usa a constante, então ele
acompanha — e meça outra vez. Registre em `RESULTADO.md` uma seção nova com a
tabela dos três zooms, o par adotado e a frase que diz por que ele foi adotado.

Se nem com teto 2 couber, **pare**: o desenho supõe que cabe, e não caber é
achado que muda o spec, não número para ajustar em silêncio.

- [ ] **Passo 7: commit**

```bash
git add web/frontend/src/lista.ts web/frontend/testes/lista.test.ts \
        web/frontend/medicao/preparo.html web/frontend/medicao/preparo.ts \
        web/frontend/medicao/RESULTADO.md
git commit -m "Lista de desenho preparada por janela, com teto por regiao"
```

---

### Tarefa 4: `pintor.ts`, o laço de quadro

O único arquivo com estado temporal. Pequeno de propósito.

**Arquivos:**
- Criar: `web/frontend/src/pintor.ts`
- Testar: `web/frontend/testes/pintor.test.ts`

**Interfaces:**
- Consome: `Preparo`, `iniciarPreparo`, `avancarPreparo`, `precisaPreparar` de
  `src/lista.ts`; `desenharLote`, `janelaVisivel`, `Vista` de `src/canvas.ts`
- Produz:
  - `type Cena = { g: Geometria; mascara: Uint8Array; ordem: Uint32Array; v: Vista; larguraTela: number; alturaTela: number; geracao: number }`
  - `type Pintor = { preparo: Preparo | null; desenhadas: number; geracao: number }`
  - `function criarPintor(): Pintor`
  - `function passo(p: Pintor, cena: Cena, ctx: ContextoDesenhavel, criarCaminho: () => CaminhoDesenhavel, orcamento: number): boolean`

`passo` faz um quadro e devolve `true` quando não há mais nada pendente. A
`geracao` da cena é o que diz ao pintor que a máscara ou a geometria mudaram:
quem muda incrementa, e o pintor compara.

- [ ] **Passo 1: escrever o teste que falha**

`web/frontend/testes/pintor.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { enquadrar } from "../src/canvas.js";
import { criarPintor, passo, type Cena } from "../src/pintor.js";
import { ordenarPorComprimento } from "../src/ordem.js";
import { UM_POR_PONTO } from "../src/lista.js";
import type { Geometria } from "../src/formato.js";
import { CaminhoGravado, ContextoGravado } from "./ajuda/canvas2d.js";

function geometriaDe(quantos: number): Geometria {
  const coords = new Float32Array(quantos * 4);
  const length_um = new Uint32Array(quantos);
  const coord_off = new Uint32Array(quantos + 1);
  for (let i = 0; i < quantos; i++) {
    // Espalhados o bastante para não disputarem a mesma região.
    const x = (i % 50) * 2, y = Math.floor(i / 50) * 2;
    coords.set([x, y, x + 1, y + 1], i * 4);
    coord_off[i + 1] = (i + 1) * 4;
    length_um[i] = Math.round(Math.hypot(1, 1) * UM_POR_PONTO);
  }
  return {
    n: quantos, layers: ["0"], n_groups: quantos,
    idx: Uint32Array.from({ length: quantos }, (_, i) => i),
    kind: new Uint8Array(quantos),
    layer_id: new Uint32Array(quantos),
    is_fill: new Uint8Array(quantos),
    length_um,
    dup_group: Int32Array.from({ length: quantos }, (_, i) => i),
    byte_cost: new Uint32Array(quantos),
    cor: new Uint32Array(quantos).fill(0xffffffff),
    coord_off, coords,
    texto_off: new Uint32Array(quantos + 1),
    texto: new Uint8Array(0),
  };
}

function cenaDe(g: Geometria, geracao = 1): Cena {
  return {
    g,
    mascara: new Uint8Array(g.n).fill(1),
    ordem: ordenarPorComprimento(g.length_um),
    v: enquadrar(100, 100, 400, 400),
    larguraTela: 400, alturaTela: 400,
    geracao,
  };
}

describe("pintor.ts", () => {
  it("termina em vários quadros quando o orçamento é apertado", () => {
    const g = geometriaDe(500);
    const cena = cenaDe(g);
    const p = criarPintor();
    let quadros = 0;
    let acabou = false;
    while (!acabou && quadros < 100) {
      acabou = passo(p, cena, new ContextoGravado(),
                     () => new CaminhoGravado(), 40);
      quadros++;
    }
    expect(acabou).toBe(true);
    expect(quadros).toBeGreaterThan(1);
  });

  it("desenha, ao fim, tudo o que a lista escolheu", () => {
    const g = geometriaDe(300);
    const cena = cenaDe(g);
    const p = criarPintor();
    const ctx = new ContextoGravado();
    while (!passo(p, cena, ctx, () => new CaminhoGravado(), 1000));
    expect(p.preparo!.quantos).toBe(300);
    expect(p.desenhadas).toBe(300);
  });

  it("mudar a geração recomeça o preparo", () => {
    const g = geometriaDe(300);
    const p = criarPintor();
    while (!passo(p, cenaDe(g, 1), new ContextoGravado(),
                  () => new CaminhoGravado(), 1000));
    const primeira = p.preparo;

    const outra = cenaDe(g, 2);
    outra.mascara = new Uint8Array(g.n);          // nada sobrevive
    passo(p, outra, new ContextoGravado(), () => new CaminhoGravado(), 1000);
    expect(p.preparo).not.toBe(primeira);
    expect(p.preparo!.quantos).toBe(0);
  });

  it("pan pequeno não prepara de novo", () => {
    const g = geometriaDe(300);
    const cena = cenaDe(g);
    const p = criarPintor();
    while (!passo(p, cena, new ContextoGravado(),
                  () => new CaminhoGravado(), 1000));
    const antes = p.preparo;

    const movida: Cena = { ...cena, v: { ...cena.v, dx: cena.v.dx - 30 } };
    passo(p, movida, new ContextoGravado(), () => new CaminhoGravado(), 1000);
    expect(p.preparo).toBe(antes);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/pintor.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/pintor.ts`**

```ts
/**
 * O laço de quadro: quem decide preparar, continuar ou só re-traçar.
 *
 * É o único arquivo desta parte com estado temporal, e é pequeno de propósito.
 * Tudo o que ele coordena — ordenar, preparar, traçar — é função pura em outro
 * lugar, testável sem relógio e sem navegador.
 */
import {
  desenharLote, janelaVisivel, type CaminhoDesenhavel,
  type ContextoDesenhavel, type Vista,
} from "./canvas.js";
import type { Geometria } from "./formato.js";
import {
  avancarPreparo, iniciarPreparo, precisaPreparar, FOLGA_DA_JANELA,
  type Preparo,
} from "./lista.js";

export type Cena = {
  g: Geometria;
  mascara: Uint8Array;
  ordem: Uint32Array;
  v: Vista;
  larguraTela: number;
  alturaTela: number;
  /** Sobe quando a máscara ou a geometria mudam. Quem muda incrementa. */
  geracao: number;
};

export type Pintor = {
  preparo: Preparo | null;
  desenhadas: number;
  geracao: number;
};

export function criarPintor(): Pintor {
  return { preparo: null, desenhadas: 0, geracao: -1 };
}

/**
 * Um quadro. Devolve `true` quando não há mais nada pendente — o preparo
 * terminou e tudo o que a lista escolheu já foi traçado ao menos uma vez.
 *
 * O `orcamento` limita as entidades processadas no preparo, não o traçado: o
 * traçado é barato justamente porque a lista já está pronta.
 */
export function passo(p: Pintor, cena: Cena, ctx: ContextoDesenhavel,
                      criarCaminho: () => CaminhoDesenhavel,
                      orcamento: number): boolean {
  const mudou = p.geracao !== cena.geracao;
  const saiu = p.preparo !== null &&
    precisaPreparar(p.preparo, cena.v, cena.larguraTela, cena.alturaTela);

  if (p.preparo === null || mudou || saiu) {
    const janela = janelaVisivel(cena.v, cena.larguraTela, cena.alturaTela,
                                 FOLGA_DA_JANELA);
    p.preparo = iniciarPreparo(cena.g, janela, cena.v.escala);
    p.geracao = cena.geracao;
    p.desenhadas = 0;
  }

  const preparo = p.preparo;
  if (!preparo.pronto) {
    avancarPreparo(preparo, cena.g, cena.mascara, cena.ordem, orcamento);
  }

  const limites = janelaVisivel(cena.v, cena.larguraTela, cena.alturaTela, 0);
  ctx.clearRect(0, 0, cena.larguraTela, cena.alturaTela);
  p.desenhadas = desenharLote(ctx, cena.g, preparo.lista, preparo.quantos,
                              cena.v, criarCaminho, limites);
  return preparo.pronto;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os quatro testes novos verdes.

- [ ] **Passo 5: commit**

```bash
git add web/frontend/src/pintor.ts web/frontend/testes/pintor.test.ts
git commit -m "Pintor: orcamento por quadro, continuacao e quando preparar de novo"
```

---

### Tarefa 5: `gestos.ts`, com a emenda do fim de gesto

Execute a **tarefa 10 do plano de 2026-08-04** — `web/frontend/src/gestos.ts`,
com `aplicarZoom`, `aplicarArrasto`, `fatorDaRoda`, `distancia` e `centro`, e o
teste que prova que o zoom mantém parado o ponto sob o dedo. O código está lá e
não muda.

**Duas emendas**, e só elas:

- [ ] **Emenda 1: importar `Vista` de `canvas.ts`, que agora é quem a define**

O plano antigo já importava de lá (`import { enquadrar, pontoDoPapel } from
"../src/canvas.js"` no teste). A tarefa 2 deste plano mantém `Vista`,
`enquadrar`, `pontoDaTela` e `pontoDoPapel` com as mesmas assinaturas, então
nada muda no código — confira só que o teste da tarefa 10 continua compilando.

- [ ] **Emenda 2: acrescentar o fim de gesto**

Ao fim de `web/frontend/src/gestos.ts`:

```ts
/**
 * Quanto tempo sem evento conta como "o gesto parou".
 *
 * Existe porque preparar a lista custa da ordem de meio segundo, e fazer isso
 * durante um arrasto ou uma pinça engasgaria o gesto. Enquanto o dedo se mexe a
 * tela desenha a lista que tem; a preparação espera a mão parar.
 */
export const PAUSA_DO_GESTO_MS = 120;
```

E ao fim de `web/frontend/testes/gestos.test.ts`:

```ts
import { PAUSA_DO_GESTO_MS } from "../src/gestos.js";

describe("fim de gesto", () => {
  it("a pausa é curta o bastante para não parecer travada", () => {
    // Acima de ~200 ms a espera vira lentidão percebida; abaixo de ~80 ms um
    // arrasto normal dispara preparação no meio do caminho.
    expect(PAUSA_DO_GESTO_MS).toBeGreaterThanOrEqual(80);
    expect(PAUSA_DO_GESTO_MS).toBeLessThanOrEqual(200);
  });
});
```

- [ ] **Commit**

```bash
git add web/frontend/src/gestos.ts web/frontend/testes/gestos.test.ts
git commit -m "Gestos de pan e zoom, com a pausa que decide o fim do gesto"
```

---

### Tarefa 6: `toolbar.ts` e `main.ts`, com as emendas do redesenho

Execute a **tarefa 12 do plano de 2026-08-04** — `opcoesEfetivas`,
`textoDaEstimativa`, `montarFaixaDeOpcoes` e a composição da tela. O código de
`toolbar.ts` e os testes dele não mudam: não tocam em worker nem em desenho.

O que muda é o `main.ts`, e são quatro pontos. Onde o plano antigo mandar falar
com o worker, faça assim:

- [ ] **Emenda 1: sem worker, e a máscara na thread principal**

```ts
// O `select()` sobre 3 milhões de entidades custa ~12 ms — cabe num quadro.
// Foi medido; ver web/frontend/medicao/RESULTADO.md. Não há worker.
function recalcular(): void {
  const opts = opcoesEfetivas(estado);
  mascara = selecionar(geometria, opts);
  estado.bytes = estimarBytes(geometria, mascara, opts);
  estado.sobreviventes = mascara.reduce((a: number, b: number) => a + b, 0);
  geracao++;                 // avisa o pintor que a lista precisa ser refeita
  atualizarFaixa();
}
```

- [ ] **Emenda 2: a ordem é calculada quando a geometria muda, não a cada clique**

```ts
// Só depende dos comprimentos, e eles não mudam com as opções. Refazer a cada
// clique custaria ~250 ms à toa.
function trocarGeometria(nova: Geometria): void {
  geometria = nova;
  ordem = ordenarPorComprimento(geometria.length_um);
  recalcular();
}
```

- [ ] **Emenda 3: o laço de quadro**

```ts
const pintor = criarPintor();
let pedido = 0;

/**
 * Um quadro por vez, e nunca dois pedidos em voo. O orçamento de 20 mil
 * entidades por quadro vem da medição: preparar 3 milhões leva ~500 ms, e essa
 * fatia mantém o quadro abaixo de 16 ms na máquina de referência.
 */
function agendar(): void {
  if (pedido) return;
  pedido = requestAnimationFrame(() => {
    pedido = 0;
    const cena: Cena = {
      g: geometria, mascara, ordem, v: vista,
      larguraTela: tela.width, alturaTela: tela.height, geracao,
    };
    const acabou = passo(pintor, cena, ctx, () => new Path2D(), 20_000);
    faixaDeCarregamento.hidden = acabou && !faltaDetalhe;
    if (!acabou) agendar();
  });
}
```

- [ ] **Emenda 4: o gesto agenda, e o fim do gesto também**

```ts
let paradaDoGesto = 0;

function aoMexer(nova: Vista): void {
  vista = nova;
  agendar();                        // re-traça já, com a lista que existe
  clearTimeout(paradaDoGesto);
  // O `precisaPreparar` de dentro do pintor decide se vale refazer; aqui só se
  // dá a ele a chance, depois que a mão parou.
  paradaDoGesto = setTimeout(agendar, PAUSA_DO_GESTO_MS);
}
```

- [ ] **Passo final: rodar tudo e commitar**

```bash
cd web/frontend && npm test && npm run build
```

```bash
git add web/frontend/src/toolbar.ts web/frontend/src/main.ts \
        web/frontend/testes/toolbar.test.ts
git commit -m "Tela montada: mascara na thread principal e o pintor no laco de quadro"
```

---

### Tarefas 7 a 10: as que vêm inteiras do plano de 2026-08-04

Execute, nesta ordem, sem emenda nenhuma. O código está no plano antigo.

- [ ] **Tarefa 7 = tarefa 7 do plano antigo:** `api.ts`, o cliente HTTP com
  recuo crescente e `AbortController` por página. Faça-a **antes** da tarefa 6
  deste plano: o `main.ts` a consome.
- [ ] **Tarefa 8 = tarefa 9 do plano antigo:** `calibrate.ts`, a aritmética da
  escala por dois pontos e por escala de plotagem.
- [ ] **Tarefa 9 = tarefa 11 do plano antigo:** `estados.ts` e `estilo.css`.
- [ ] **Tarefa 10 = tarefa 13 do plano antigo:** a calibração na tela, com lupa
  no toque.

---

### Tarefa 11: Playwright de ponta a ponta

Execute a **tarefa 14 do plano de 2026-08-04**, inclusive o `globalSetup` que
gera o PDF sintético a cada execução em vez de versioná-lo — `*.pdf` está no
`.gitignore` e abrir exceção ali enfraqueceria a regra que protege as plantas
dos clientes.

**Uma emenda**, porque o desenho mudou:

- [ ] **Emenda: esperar o desenho por condição, não por relógio**

O teste não pode esperar "meio segundo até a planta aparecer": com preparação
fatiada, o número de quadros depende da máquina. Exponha a contagem no DOM e
espere por ela:

```ts
// Em main.ts, ao fim de cada quadro:
tela.dataset["desenhadas"] = String(pintor.desenhadas);
```

```ts
// No teste:
await expect
  .poll(async () => Number(await tela.getAttribute("data-desenhadas")))
  .toBeGreaterThan(0);
```

---

### Tarefa 12: servir os estáticos e compilar no Docker

Execute a **tarefa 15 do plano de 2026-08-04**, sem emenda. O estágio de build
do frontend e o `StaticFiles` do FastAPI não foram tocados pelo redesenho.

---

## Definição de pronto da etapa 3

- [ ] `cd web/frontend && npm test` verde, incluindo os 2058 que já existiam
- [ ] `cd web/frontend && npm run build` sem erro de tipo
- [ ] `npm run e2e` verde
- [ ] Os quatorze arquivos de teste Python passando, mais o
      `tests/test_api_estaticos.py` da tarefa 12
- [ ] `git diff tests/casos_select.json` vazio
- [ ] `web/frontend/medicao/RESULTADO.md` registra os números do teto e do lado
      da região efetivamente adotados, com o motivo
- [ ] Um PDF vetorial sobe, aparece no canvas, gira opções com a prévia
      mudando, calibra por dois pontos e exporta um DXF que abre no CAD com as
      medidas certas — conferência manual, a única que fecha a etapa
