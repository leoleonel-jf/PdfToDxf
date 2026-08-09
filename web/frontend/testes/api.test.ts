import { afterEach, describe, expect, it, vi } from "vitest";
import { enviarPdf, ErroDaApi, esperarPagina, lerEstado } from "../src/api.js";

function respostaDe(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status, headers: { "content-type": "application/json" },
  });
}

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

afterEach(() => vi.unstubAllGlobals());

describe("api.ts", () => {
  it("converte erro do servidor em ErroDaApi com o status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      respostaDe({ detail: "Trabalho não encontrado." }, 404)));
    await expect(lerEstado("a".repeat(32), 1)).rejects.toSatisfy(
      (e: unknown) => e instanceof ErroDaApi && e.status === 404);
  });

  it("espera a página sair da fila e avisa a cada mudança", async () => {
    const sequencia = [
      { situacao: "na_fila" },
      { situacao: "extraindo" },
      { situacao: "pronta", n_entidades: 8 },
    ];
    let chamada = 0;
    vi.stubGlobal("fetch", vi.fn(async () =>
      respostaDe(sequencia[Math.min(chamada++, sequencia.length - 1)])));

    const vistos: string[] = [];
    const controle = new AbortController();
    const final = await esperarPagina("a".repeat(32), 1, controle.signal,
                                      (e) => vistos.push(e.situacao));
    expect(final.situacao).toBe("pronta");
    expect(vistos).toEqual(["na_fila", "extraindo", "pronta"]);
  });

  it("para de esperar quando o sinal é abortado", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => respostaDe({ situacao: "na_fila" })));
    const controle = new AbortController();
    const promessa = esperarPagina("a".repeat(32), 1, controle.signal, () => {});
    controle.abort();
    await expect(promessa).rejects.toThrow(/abort/i);
  });

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
});
