# Etapa 3.6 — indicadores de progresso: plano de implementação

> **Para quem executa com agentes:** SUB-SKILL OBRIGATÓRIA: use
> `superpowers:subagent-driven-development` ou `superpowers:executing-plans`.

**Objetivo:** contar ao usuário o que está acontecendo nos cinco momentos em que
a tela pode ficar parada — envio, extração, download do desenho, pintura e
exportação.

**Arquitetura:** o modelo e a formatação viram funções puras em `progresso.ts`,
testadas no vitest. `api.ts` ganha dois relatores de progresso: o envio troca
`fetch` por `XMLHttpRequest` (o único jeito de saber quantos bytes subiram) e o
download da geometria passa a ler o corpo em pedaços. A montagem do DOM fica em
`ui/controles.ts` e na ligação em `main.ts`, cobertas pelo Playwright.

**Documento que governa:** `docs/superpowers/specs/2026-08-09-progresso-design.md`

## Restrições globais

- **Nenhuma dependência nova**, nem de runtime nem de desenvolvimento.
- **O vitest roda com `environment: "node"`** — não existe `document`. Só código
  puro e `api.ts` (que se testa com `vi.stubGlobal`) entram em `testes/`.
- **Nada de Python muda.** Nenhuma rota muda de contrato.
- **Não toque no motor de desenho:** `canvas.ts`, `pintor.ts`, `lista.ts`,
  `ordem.ts`, `formato.ts`, `select.ts`, `estimativa.ts`, `camadas.ts`,
  `calibrate.ts`, `gestos.ts`. Importar deles é permitido; alterar, não.
- **Nunca inventar porcentagem.** Sem número real, o indicador é indeterminado.
- **Nunca `innerHTML`.**
- Comandos a partir de `web/frontend`: `npm test` · `npm run build` · `npm run e2e`.
- Há integração contínua a cada push e um pull request aberto: **todo commit tem
  de ficar verde**.

---

## Tarefa 1: o modelo puro e a formatação

**Arquivos:**
- Criar: `web/frontend/src/progresso.ts`
- Teste: `web/frontend/testes/progresso.test.ts`

**Interfaces:**
- Produz: o tipo `Progresso`, `fracao`, `porcentagem`, `tempoDecorrido`.
  As tarefas 2, 3 e 4 consomem.

- [ ] **Passo 1: escrever o teste que falha**

```ts
import { describe, expect, it } from "vitest";
import { fracao, porcentagem, tempoDecorrido } from "../src/progresso.js";

describe("progresso.ts", () => {
  it("a fração é o que foi feito sobre o total", () => {
    expect(fracao({ tipo: "determinado", feito: 5, total: 20 })).toBe(0.25);
  });

  it("indeterminado não tem fração nem porcentagem", () => {
    const p = { tipo: "indeterminado", desde: 0 } as const;
    expect(fracao(p)).toBe(null);
    expect(porcentagem(p)).toBe(null);
  });

  it("total zero não vira divisão por zero", () => {
    expect(fracao({ tipo: "determinado", feito: 3, total: 0 })).toBe(null);
  });

  it("a fração é presa entre 0 e 1", () => {
    expect(fracao({ tipo: "determinado", feito: 30, total: 20 })).toBe(1);
    expect(fracao({ tipo: "determinado", feito: -5, total: 20 })).toBe(0);
  });

  it("a porcentagem é inteira", () => {
    expect(porcentagem({ tipo: "determinado", feito: 1, total: 3 })).toBe(33);
  });

  it("abaixo de um segundo o tempo não aparece", () => {
    expect(tempoDecorrido(0, 0)).toBe("");
    expect(tempoDecorrido(0, 999)).toBe("");
  });

  it("os segundos aparecem inteiros até um minuto", () => {
    expect(tempoDecorrido(0, 1000)).toBe("1 s");
    expect(tempoDecorrido(0, 59_000)).toBe("59 s");
  });

  it("um minuto redondo não mostra os segundos", () => {
    expect(tempoDecorrido(0, 60_000)).toBe("1 min");
    expect(tempoDecorrido(0, 120_000)).toBe("2 min");
  });

  it("minuto quebrado mostra os segundos", () => {
    expect(tempoDecorrido(0, 61_000)).toBe("1 min 1 s");
    expect(tempoDecorrido(0, 95_000)).toBe("1 min 35 s");
  });

  it("de dez minutos em diante os segundos são ruído", () => {
    expect(tempoDecorrido(0, 635_000)).toBe("10 min");
    expect(tempoDecorrido(0, 3_600_000)).toBe("60 min");
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npx vitest run testes/progresso.test.ts
```

Esperado: FALHA, módulo não encontrado.

- [ ] **Passo 3: implementar**

```ts
/**
 * O modelo do indicador de progresso, e a formatação.
 *
 * Puro de propósito: é aqui que mora a única regra que importa — **nunca
 * inventar porcentagem**. Onde não há número real, o indicador é indeterminado,
 * e quem monta o DOM não tem como fingir o contrário.
 */

export type Progresso =
  | { tipo: "determinado"; feito: number; total: number }
  | { tipo: "indeterminado"; desde: number };

/** Fração de 0 a 1, presa nas pontas. `null` quando não há como saber. */
export function fracao(p: Progresso): number | null {
  if (p.tipo !== "determinado") return null;
  if (!(p.total > 0)) return null;
  return Math.min(1, Math.max(0, p.feito / p.total));
}

export function porcentagem(p: Progresso): number | null {
  const f = fracao(p);
  return f === null ? null : Math.round(f * 100);
}

/**
 * Tempo decorrido, curto e em português. Vazio abaixo de um segundo.
 *
 * Piscar "0 s" no instante em que a barra aparece é ruído — ninguém precisa
 * saber que se passaram trezentos milissegundos. E de dez minutos em diante os
 * segundos deixam de informar: quem espera dez minutos quer a ordem de
 * grandeza, não o relógio.
 */
export function tempoDecorrido(desde: number, agora: number): string {
  const s = Math.floor((agora - desde) / 1000);
  if (s < 1) return "";
  if (s < 60) return `${s} s`;
  const min = Math.floor(s / 60);
  const resto = s % 60;
  if (min >= 10 || resto === 0) return `${min} min`;
  return `${min} min ${resto} s`;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npx vitest run testes/progresso.test.ts && npm run build
```

Esperado: PASSA, 10 testes; build limpo.

- [ ] **Passo 5: commitar**

```bash
git add web/frontend/src/progresso.ts web/frontend/testes/progresso.test.ts
git commit -m "Modelo puro do indicador de progresso e a formatacao"
```

---

## Tarefa 2: o envio por `XMLHttpRequest`, com progresso e cancelamento

**Arquivos:**
- Modificar: `web/frontend/src/api.ts`
- Teste: `web/frontend/testes/api.test.ts`

**Interfaces:**
- `enviarPdf(arquivo, sinal?, aoProgredir?)` — `aoProgredir` recebe
  `(enviados: number, total: number)`. A tarefa 4 a usa.
- `ErroDaApi` e o comportamento de aborto **não mudam**.

> **Este é o passo perigoso da etapa.** `enviarPdf` é o único caminho por onde o
> PDF entra no serviço, e o tratamento de erro dele é o que a etapa 4 vai usar
> para a recusa por cota. Os testes abaixo existem para prender exatamente isso.

- [ ] **Passo 1: escrever os testes que falham**

Acrescente ao fim de `web/frontend/testes/api.test.ts`, dentro do `describe`:

```ts
  it("o envio relata progresso e resolve com a ficha", async () => {
    const x = new XhrFalso();
    vi.stubGlobal("XMLHttpRequest", function () { return x; });

    const vistos: Array<[number, number]> = [];
    const promessa = enviarPdf(new File(["abc"], "planta.pdf"), undefined,
                              (feito, total) => vistos.push([feito, total]));
    x.progresso(30, 100);
    x.progresso(100, 100);
    x.status = 200;
    x.responseText = JSON.stringify({ job_id: "a".repeat(32), nome: "planta.pdf",
                                      n_paginas: 1 });
    x.disparar("load");

    await expect(promessa).resolves.toMatchObject({ n_paginas: 1 });
    expect(vistos).toEqual([[30, 100], [100, 100]]);
  });

  it("o envio recusado vira ErroDaApi com o status e o detalhe", async () => {
    const x = new XhrFalso();
    vi.stubGlobal("XMLHttpRequest", function () { return x; });

    const promessa = enviarPdf(new File(["abc"], "planta.pdf"));
    x.status = 413;
    x.responseText = JSON.stringify({ detail: "O arquivo passa de 100 MB." });
    x.disparar("load");

    await expect(promessa).rejects.toSatisfy(
      (e: unknown) => e instanceof ErroDaApi && e.status === 413 &&
                      e.message === "O arquivo passa de 100 MB.");
  });

  it("abortar no meio do envio rejeita com AbortError e chama abort", async () => {
    const x = new XhrFalso();
    vi.stubGlobal("XMLHttpRequest", function () { return x; });

    const controle = new AbortController();
    const promessa = enviarPdf(new File(["abc"], "planta.pdf"), controle.signal);
    x.progresso(10, 100);
    controle.abort();

    await expect(promessa).rejects.toSatisfy(
      (e: unknown) => e instanceof DOMException && e.name === "AbortError");
    expect(x.abortado).toBe(true);
  });

  it("sinal já abortado nem chega a enviar", async () => {
    const x = new XhrFalso();
    vi.stubGlobal("XMLHttpRequest", function () { return x; });

    const controle = new AbortController();
    controle.abort();
    await expect(enviarPdf(new File(["abc"], "planta.pdf"), controle.signal))
      .rejects.toSatisfy((e: unknown) => e instanceof DOMException &&
                                         e.name === "AbortError");
    expect(x.enviado).toBe(null);
  });
```

E acrescente, no topo do arquivo, depois dos imports, o dublê:

```ts
/**
 * Um `XMLHttpRequest` de mentira, controlado pelo teste.
 *
 * Não há navegador aqui — o vitest roda em Node. O dublê expõe `progresso()` e
 * `disparar()` para o teste decidir a hora de cada evento, que é justamente o
 * que um envio de verdade não deixa controlar.
 */
class XhrFalso {
  upload = new EventTarget();
  status = 0;
  responseText = "";
  responseType = "";
  enviado: unknown = null;
  abortado = false;
  private ouvintes = new EventTarget();

  open(_metodo: string, _url: string): void {}
  send(corpo: unknown): void { this.enviado = corpo; }
  abort(): void { this.abortado = true; this.disparar("abort"); }
  addEventListener(t: string, f: EventListener): void {
    this.ouvintes.addEventListener(t, f);
  }
  removeEventListener(t: string, f: EventListener): void {
    this.ouvintes.removeEventListener(t, f);
  }
  disparar(t: string): void { this.ouvintes.dispatchEvent(new Event(t)); }
  progresso(loaded: number, total: number): void {
    const e = new Event("progress");
    Object.assign(e, { lengthComputable: true, loaded, total });
    this.upload.dispatchEvent(e);
  }
}
```

Ajuste a linha de importação para incluir `enviarPdf`.

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npx vitest run testes/api.test.ts
```

Esperado: FALHA — o `enviarPdf` atual usa `fetch` e ignora o dublê.

- [ ] **Passo 3: implementar**

Substitua `enviarPdf` em `web/frontend/src/api.ts` por:

```ts
/**
 * Envia o PDF, relatando quantos bytes já subiram.
 *
 * É o único pedido deste arquivo que não usa `fetch`, e a razão é única: o
 * `fetch` não expõe progresso de upload em navegador nenhum hoje. O corpo em
 * fluxo com `duplex: "half"` resolveria, e não tem suporte suficiente.
 *
 * Duas coisas não podem regredir aqui, porque já valiam antes: o `AbortSignal`
 * corta o envio em curso, e a recusa do servidor vira `ErroDaApi` com status e
 * detalhe — é por esse caminho que a mensagem de recusa chega à tela.
 */
export function enviarPdf(arquivo: File, sinal?: AbortSignal,
                          aoProgredir?: (enviados: number, total: number) => void):
                          Promise<Ficha> {
  return new Promise((resolve, reject) => {
    if (sinal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }

    const forma = new FormData();
    forma.append("arquivo", arquivo);

    const x = new XMLHttpRequest();
    x.open("POST", "/api/jobs");

    x.upload.addEventListener("progress", (e) => {
      const p = e as ProgressEvent;
      if (p.lengthComputable) aoProgredir?.(p.loaded, p.total);
    });

    const desistir = () => x.abort();
    sinal?.addEventListener("abort", desistir, { once: true });
    const limpar = () => sinal?.removeEventListener("abort", desistir);

    x.addEventListener("abort", () => {
      limpar();
      reject(new DOMException("Aborted", "AbortError"));
    });

    x.addEventListener("error", () => {
      limpar();
      reject(new TypeError("Não consegui falar com o servidor."));
    });

    x.addEventListener("load", () => {
      limpar();
      if (x.status >= 200 && x.status < 300) {
        try {
          resolve(JSON.parse(x.responseText) as Ficha);
        } catch {
          reject(new ErroDaApi(x.status, "O servidor respondeu algo que não entendi."));
        }
        return;
      }
      // Mesmo contrato do `pedir`: detalhe do corpo quando houver, status
      // quando não houver.
      let detalhe = `HTTP ${x.status}`;
      try {
        const corpo = JSON.parse(x.responseText);
        if (corpo?.detail) detalhe = String(corpo.detail);
      } catch {
        // Resposta sem JSON: fica o status, que já diz o suficiente.
      }
      reject(new ErroDaApi(x.status, detalhe));
    });

    x.send(forma);
  });
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npx vitest run testes/api.test.ts && npm run build && npm run e2e
```

Esperado: os três limpos. O ponta a ponta importa **muito** aqui: ele é a única
prova de que o envio de verdade, com um servidor de verdade, continua
funcionando depois da troca.

- [ ] **Passo 5: provar que o teste de aborto morde**

Comente a linha `sinal?.addEventListener("abort", desistir, { once: true });` e
rode `npx vitest run testes/api.test.ts`. O teste "abortar no meio do envio"
**tem de falhar**. Desfaça e confirme que volta a passar.

- [ ] **Passo 6: commitar**

```bash
git add web/frontend/src/api.ts web/frontend/testes/api.test.ts
git commit -m "Envio do PDF por XMLHttpRequest, com progresso e cancelamento"
```

---

## Tarefa 3: o download da geometria em pedaços

**Arquivos:**
- Modificar: `web/frontend/src/api.ts`
- Teste: `web/frontend/testes/api.test.ts`

**Interfaces:**
- `lerGeometriaBruta(job, pagina, parte, sinal?, aoProgredir?)` — `aoProgredir`
  recebe `(lidos: number, total: number | null)`. `total` é `null` quando o
  servidor não declara `Content-Length`.

- [ ] **Passo 1: escrever os testes que falham**

Acrescente ao `describe` de `web/frontend/testes/api.test.ts`:

```ts
  function respostaEmPedacos(pedacos: Uint8Array[], tamanho?: number): Response {
    const fluxo = new ReadableStream<Uint8Array>({
      start(controle) {
        for (const p of pedacos) controle.enqueue(p);
        controle.close();
      },
    });
    const cabecalhos: Record<string, string> = {};
    if (tamanho !== undefined) cabecalhos["content-length"] = String(tamanho);
    return new Response(fluxo, { status: 200, headers: cabecalhos });
  }

  it("a geometria chega inteira e o progresso acompanha", async () => {
    const a = new Uint8Array([1, 2, 3]);
    const b = new Uint8Array([4, 5]);
    vi.stubGlobal("fetch", vi.fn(async () => respostaEmPedacos([a, b], 5)));

    const vistos: Array<[number, number | null]> = [];
    const buffer = await lerGeometriaBruta("a".repeat(32), 1, "esqueleto",
                                           undefined,
                                           (lidos, total) => vistos.push([lidos, total]));

    expect(new Uint8Array(buffer)).toEqual(new Uint8Array([1, 2, 3, 4, 5]));
    expect(buffer.byteLength).toBe(5);
    expect(vistos).toEqual([[3, 5], [5, 5]]);
  });

  it("sem Content-Length o total é nulo, e não um palpite", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      respostaEmPedacos([new Uint8Array([7, 7])])));

    const vistos: Array<number | null> = [];
    await lerGeometriaBruta("a".repeat(32), 1, "detalhe", undefined,
                            (_lidos, total) => vistos.push(total));
    expect(vistos).toEqual([null]);
  });

  it("erro do servidor continua virando ErroDaApi antes de ler o corpo", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ detail: "A página ainda não está pronta." }),
                   { status: 409, headers: { "content-type": "application/json" } })));
    await expect(lerGeometriaBruta("a".repeat(32), 1, "esqueleto"))
      .rejects.toSatisfy((e: unknown) => e instanceof ErroDaApi && e.status === 409);
  });
```

Inclua `lerGeometriaBruta` na linha de importação.

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npx vitest run testes/api.test.ts
```

Esperado: FALHA — a versão atual usa `arrayBuffer()` e não aceita
`aoProgredir`.

- [ ] **Passo 3: implementar**

Substitua `lerGeometriaBruta` por:

```ts
/**
 * Baixa a geometria lendo o corpo em pedaços, para poder relatar progresso.
 *
 * O buffer devolvido tem de ser byte a byte o mesmo que `arrayBuffer()`
 * devolvia: é sobre ele que o leitor do formato monta as `TypedArray` sem
 * copiar, e é por isso que as seções são enchidas até múltiplo de 4.
 */
export async function lerGeometriaBruta(job: string, pagina: number,
                                        parte: "esqueleto" | "detalhe",
                                        sinal?: AbortSignal,
                                        aoProgredir?: (lidos: number,
                                                       total: number | null) => void):
                                        Promise<ArrayBuffer> {
  const r = await pedir(
    `/api/jobs/${job}/pages/${pagina}/geometry.bin?parte=${parte}`,
    { signal: sinal });

  const declarado = Number(r.headers.get("content-length"));
  // Sem tamanho declarado — resposta comprimida, por exemplo — o progresso sai
  // indeterminado, e não com uma porcentagem inventada.
  const total = Number.isFinite(declarado) && declarado > 0 ? declarado : null;

  // Ambiente sem corpo em fluxo: cai no caminho antigo em vez de estourar.
  if (!r.body) return r.arrayBuffer();

  const leitor = r.body.getReader();
  const pedacos: Uint8Array[] = [];
  let lidos = 0;
  for (;;) {
    const { done, value } = await leitor.read();
    if (done) break;
    pedacos.push(value);
    lidos += value.byteLength;
    aoProgredir?.(lidos, total);
  }

  // Uma cópia só, no fim. Concatenar a cada pedaço seria quadrático, e numa
  // planta no teto são dezenas de megabytes.
  const inteiro = new Uint8Array(lidos);
  let onde = 0;
  for (const p of pedacos) {
    inteiro.set(p, onde);
    onde += p.byteLength;
  }
  return inteiro.buffer;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test && npm run build && npm run e2e
```

Esperado: os três limpos. O ponta a ponta prova que o desenho continua
aparecendo — se a concatenação estivesse errada, o leitor do formato estouraria
ou o canvas sairia vazio.

- [ ] **Passo 5: commitar**

```bash
git add web/frontend/src/api.ts web/frontend/testes/api.test.ts
git commit -m "Download da geometria em pedacos, relatando progresso"
```

---

## Tarefa 4: a barra na tela, nos cinco momentos

**Arquivos:**
- Modificar: `web/frontend/src/ui/controles.ts`
- Modificar: `web/frontend/src/estilo.css`
- Modificar: `web/frontend/src/main.ts`
- Teste: `web/frontend/e2e/conversao.spec.ts`

**Interfaces:**
- `criarBarraDeProgresso(p: Progresso, rotulo: string, agora: number): HTMLElement`

- [ ] **Passo 1: o componente**

Acrescente a `web/frontend/src/ui/controles.ts`:

```ts
import { porcentagem, tempoDecorrido, type Progresso } from "../progresso.js";

/**
 * A barra, determinada ou não.
 *
 * `<div role="progressbar">` e não `<progress>`: o elemento nativo não aceita o
 * tratamento visual do resto da tela sem gambiarra por navegador, e os
 * atributos `aria-value*` dão ao leitor de tela exatamente a mesma informação.
 *
 * Sem porcentagem, o rótulo mostra o tempo decorrido — que é verdade, ao
 * contrário de qualquer previsão que se pudesse inventar.
 */
export function criarBarraDeProgresso(p: Progresso, rotulo: string,
                                      agora: number): HTMLElement {
  const caixa = document.createElement("div");
  caixa.className = "progresso";
  caixa.dataset["teste"] = "progresso";

  const linha = document.createElement("div");
  linha.className = "apoio";
  const texto = document.createElement("span");
  texto.textContent = rotulo;
  const valor = document.createElement("span");
  valor.className = "secundario";
  const pct = porcentagem(p);
  valor.textContent = pct !== null
    ? `${pct}%`
    : tempoDecorrido((p as { desde: number }).desde, agora);
  linha.append(texto, valor);

  const trilho = document.createElement("div");
  trilho.className = "progresso-trilho";
  trilho.setAttribute("role", "progressbar");
  trilho.setAttribute("aria-label", rotulo);
  const trecho = document.createElement("div");
  if (pct !== null) {
    trilho.setAttribute("aria-valuemin", "0");
    trilho.setAttribute("aria-valuemax", "100");
    trilho.setAttribute("aria-valuenow", String(pct));
    trecho.className = "progresso-trecho";
    trecho.style.width = `${pct}%`;
  } else {
    trecho.className = "progresso-trecho indeterminado";
  }
  trilho.append(trecho);

  caixa.append(linha, trilho);
  return caixa;
}
```

- [ ] **Passo 2: o CSS**

Acrescente ao fim de `web/frontend/src/estilo.css`:

```css
/* --- progresso ----------------------------------------------------------- */

.progresso { display: flex; flex-direction: column; gap: var(--e1); width: 100%; max-width: 32rem; }
.progresso > .apoio { display: flex; justify-content: space-between; }

.progresso-trilho {
  height: 6px;
  border-radius: 3px;
  background: var(--c0);
  overflow: hidden;
}
.progresso-trecho { height: 100%; background: var(--destaque); transition: width 120ms linear; }

/* Indeterminado: um trecho que vai e volta. Não finge saber quanto falta —
   só diz que alguma coisa continua acontecendo. */
.progresso-trecho.indeterminado {
  width: 35%;
  animation: vaivem 1.4s ease-in-out infinite;
}
@keyframes vaivem {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(286%); }
}
@media (prefers-reduced-motion: reduce) {
  .progresso-trecho.indeterminado { animation: none; width: 100%; opacity: 0.4; }
}
```

- [ ] **Passo 3: ligar nos cinco momentos**

Em `web/frontend/src/main.ts`:

1. Importe:

```ts
import { criarBarraDeProgresso } from "./ui/controles.js";
import type { Progresso } from "./progresso.js";
```

2. Declare, junto das variáveis de topo:

```ts
/** O que a tela está esperando agora, e nada se não estiver esperando nada. */
let emCurso: { onde: "aviso" | "faixa"; rotulo: string; p: Progresso } | null = null;
let cancelar: (() => void) | null = null;
let relogio = 0;

/**
 * O indeterminado precisa de um relógio; o determinado, não.
 *
 * Sem isto o tempo decorrido ficaria congelado no instante em que a barra
 * apareceu — que é justamente o pior momento, porque é quando ele vale zero.
 */
function ligarRelogio(): void {
  if (relogio) return;
  relogio = window.setInterval(() => {
    if (emCurso?.p.tipo === "indeterminado") desenharProgresso();
    else pararRelogio();
  }, 1000);
}

function pararRelogio(): void {
  if (relogio) { clearInterval(relogio); relogio = 0; }
}

function mostrarProgresso(onde: "aviso" | "faixa", rotulo: string,
                          p: Progresso, podeCancelar = false): void {
  emCurso = { onde, rotulo, p };
  if (!podeCancelar) cancelar = null;
  if (p.tipo === "indeterminado") ligarRelogio(); else pararRelogio();
  desenharProgresso();
}

function esconderProgresso(): void {
  emCurso = null;
  cancelar = null;
  pararRelogio();
  desenharProgresso();
}

function desenharProgresso(): void {
  if (!emCurso) {
    painelAviso.hidden = true;
    faixaDetalhe.hidden = true;
    return;
  }
  const barra = criarBarraDeProgresso(emCurso.p, emCurso.rotulo, Date.now());
  if (emCurso.onde === "faixa") {
    painelAviso.hidden = true;
    faixaDetalhe.hidden = false;
    faixaDetalhe.replaceChildren(barra);
    return;
  }
  faixaDetalhe.hidden = true;
  painelAviso.hidden = false;
  painelAviso.replaceChildren(barra);
  if (cancelar) {
    painelAviso.append(criarBotao({
      rotulo: "Cancelar", teste: "cancelar", aoClicar: () => cancelar?.(),
    }));
  }
}
```

Importe `criarBotao` junto de `criarBarraDeProgresso`.

3. **`mostrarAviso` limpa o progresso.** Acrescente `esconderProgresso();` como
   primeira linha do corpo de `mostrarAviso`, para que um erro nunca apareça por
   baixo de uma barra viva. Cuidado: `esconderProgresso` chama
   `desenharProgresso`, que esconde o painel — então `mostrarAviso` tem de
   continuar sendo quem decide a visibilidade depois disso.

4. **Envio.** Em `abrir()`, troque o `mostrarAviso({ titulo: "Enviando o PDF" …})`
   e a chamada de `enviarPdf` por:

```ts
    cancelar = () => controle.abort();
    mostrarProgresso("aviso", "Enviando o PDF", 
                     { tipo: "determinado", feito: 0, total: arquivo.size }, true);
    const ficha = await enviarPdf(arquivo, sinal, (feito, total) =>
      mostrarProgresso("aviso", "Enviando o PDF",
                       { tipo: "determinado", feito, total }, true));
    esconderProgresso();
```

5. **Extração.** Em `carregarPagina()`, no retorno de chamada de
   `esperarPagina`, troque a chamada de `mostrarAviso` por:

```ts
    const inicio = Date.now();
    const final = await esperarPagina(job, pagina, sinal, (e) => {
      if (e.situacao === "na_fila" || e.situacao === "extraindo") {
        mostrarProgresso("aviso", "Processando a planta",
                         { tipo: "indeterminado", desde: inicio });
      }
    });
```

6. **Download da geometria.** Nas duas chamadas de `lerGeometriaBruta`, passe o
   relator, e esconda ao terminar:

```ts
    const cruEsqueleto = await lerGeometriaBruta(
      job, pagina, "esqueleto", sinal, (lidos, total) =>
        mostrarProgresso("faixa", "Carregando o desenho", total
          ? { tipo: "determinado", feito: lidos, total }
          : { tipo: "indeterminado", desde: inicio }));
    esconderProgresso();
```

E o mesmo para o `detalhe`, com o rótulo `"Carregando o detalhe do desenho"`.
A linha que hoje escreve `faixaDetalhe.textContent = "Carregando o detalhe…"`
sai — quem escreve na faixa agora é `desenharProgresso`.

7. **Pintura.** Em `agendar()`, depois de `tela.dataset["desenhadas"] = …`:

```ts
    // Só aparece se demorar: numa planta leve o preparo termina em um quadro, e
    // piscar uma barra a cada clique numa opção seria pior do que não ter.
    if (!acabou && Date.now() - inicioDoPreparo > 300) {
      mostrarProgresso("faixa", "Desenhando",
                       { tipo: "determinado", feito: pintor.desenhadas,
                         total: estado.sobreviventesDoPreparo });
    } else if (acabou && emCurso?.rotulo === "Desenhando") {
      esconderProgresso();
    }
```

Declare `let inicioDoPreparo = 0;` no topo e grave `inicioDoPreparo = Date.now();`
em `recalcular()`, logo antes de `agendar()`. Para o total, use a contagem de
sobreviventes: some a máscara em `recalcular()` e guarde numa variável de topo
`let sobreviventesDoPreparo = 0;` — a etapa 3.5 removeu o campo `sobreviventes`
de `EstadoDaTela` por ser código morto, e ele **não deve voltar para lá**; esta
é uma variável local do laço de desenho, não estado da tela.

8. **Exportação.** Em `baixar()`:

```ts
async function baixar(): Promise<void> {
  const inicio = Date.now();
  try {
    mostrarProgresso("aviso", "Gerando o DXF", { tipo: "indeterminado", desde: inicio });
    const r = await exportar(job, pagina, { … });
    esconderProgresso();
    …
  } catch (erro) {
    mostrarAviso(avisoDoErro(erro));
  }
}
```

- [ ] **Passo 4: os casos de ponta a ponta**

Acrescente a `web/frontend/e2e/conversao.spec.ts`:

```ts
test("o envio mostra barra de progresso e ela some ao terminar", async ({ page }) => {
  await page.goto("/");
  const progresso = t(page, "progresso");
  await page.setInputFiles("#escolher-pdf", PLANTA);
  // A barra pode passar rápido; o que importa é que ela some no fim.
  await expect(t(page, "exportar")).toBeEnabled({ timeout: 60_000 });
  await expect(progresso).toBeHidden();
});

test("exportar mostra o indicador enquanto o servidor gera o DXF", async ({ page }) => {
  await abrirPlanta(page);
  const download = page.waitForEvent("download");
  await t(page, "exportar").click();
  await download;
  await expect(t(page, "progresso")).toBeHidden();
});
```

- [ ] **Passo 5: rodar**

```bash
cd web/frontend && npm test && npm run build && npm run e2e && npm run e2e
```

Esperado: tudo verde, duas vezes seguidas.

- [ ] **Passo 6: commitar**

```bash
git add web/frontend/src/ui/controles.ts web/frontend/src/estilo.css web/frontend/src/main.ts web/frontend/e2e/conversao.spec.ts
git commit -m "Barra de progresso nos cinco momentos de espera"
```

---

## Definição de pronto

- [ ] `npm test` verde, com `progresso.test.ts` novo e `api.test.ts` ampliado
- [ ] `npm run build` limpo
- [ ] `npm run e2e` verde duas vezes seguidas
- [ ] `package.json` sem dependência nova
- [ ] Nenhum arquivo do motor de desenho nem de Python no `git diff` da etapa
- [ ] Nenhuma porcentagem aparece onde o número não é real
- [ ] Conferência à mão, na tela, com planta real — do usuário
