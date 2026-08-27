import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { enviarPdf, exportar, ErroDaApi, esperarPagina, lerEstado,
        lerGeometriaBruta, type PedidoDeExportacao } from "../src/api.js";
import { coletar } from "../src/impressao.js";

/**
 * `coletar()` de verdade lê `screen`, que não existe no Node — o ambiente do
 * vitest (`vitest.config.ts` tem `environment: "node"`). Sem este mock,
 * `coletar()` sempre devolve `null` e os dois ramos que põem o cabeçalho
 * `X-Impressao` (aqui e em `exportar`) nunca executam em teste nenhum.
 */
vi.mock("../src/impressao.js", () => ({ coletar: vi.fn() }));
const coletarFalso = vi.mocked(coletar);

function respostaDe(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status, headers: { "content-type": "application/json" },
  });
}

const PEDIDO_MINIMO: PedidoDeExportacao = {
  escala: 1, unidade: "mm",
  opcoes: { excluded_layers: [], drop_fills: false, min_len_mm: 0,
           dedup: false, join_polylines: false, round_coords: false },
};

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
  cabecalhos: Record<string, string> = {};
  private ouvintes = new EventTarget();

  open(_metodo: string, _url: string): void {}
  setRequestHeader(nome: string, valor: string): void { this.cabecalhos[nome] = valor; }
  send(corpo: unknown): void { this.enviado = corpo; }
  // Um XHR de verdade só dispara o evento "abort" se `send()` já tiver
  // acontecido (estado UNSENT não dispara nada) — é exatamente a janela do
  // achado da revisão. Reproduzir isso aqui, em vez de sempre disparar, é o
  // que torna o teste da janela um teste de verdade, e não um que passaria
  // mesmo com o código antigo.
  abort(): void {
    this.abortado = true;
    if (this.enviado !== null) this.disparar("abort");
  }
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

// Padrão neutro: sem sinal coletado, os testes que não são sobre o cabeçalho
// `X-Impressao` continuam do jeito que estavam antes deste dublê existir.
beforeEach(() => {
  coletarFalso.mockReset();
  coletarFalso.mockResolvedValue(null);
});
afterEach(() => vi.unstubAllGlobals());

describe("api.ts", () => {
  it("converte erro do servidor em ErroDaApi com o status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      respostaDe({ detail: "Trabalho não encontrado." }, 404)));
    await expect(lerEstado("a".repeat(32), 1)).rejects.toSatisfy(
      (e: unknown) => e instanceof ErroDaApi && e.status === 404);
  });

  /**
   * O 422 de validação (FastAPI/Pydantic) devolve `detail` como **lista**, não
   * texto. `String(lista)` chama `toString()` de cada item, e um objeto sem
   * `toString()` próprio vira `"[object Object]"` — a mensagem que a tela
   * mostrava no lugar de dizer o que houve.
   */
  it("detail em lista de validação vira mensagem legível, não [object Object]", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => respostaDe({
      detail: [
        { loc: ["body", "escala"], msg: "value is not a valid float", type: "type_error" },
        { loc: ["body", "unidade"], msg: "field required", type: "value_error" },
      ],
    }, 422)));
    await expect(lerEstado("a".repeat(32), 1)).rejects.toSatisfy((e: unknown) =>
      e instanceof ErroDaApi && e.status === 422 &&
      !e.message.includes("[object Object]") &&
      e.message.includes("value is not a valid float") &&
      e.message.includes("field required"));
  });

  it("detail em lista sem msg legível cai no status, não em [object Object]", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      respostaDe({ detail: [{ loc: ["body"] }] }, 422)));
    await expect(lerEstado("a".repeat(32), 1)).rejects.toSatisfy((e: unknown) =>
      e instanceof ErroDaApi && !e.message.includes("[object Object]") &&
      e.message.includes("422"));
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

  /**
   * O achado da revisão: entre `x.open()` e `x.send()` existe uma janela em
   * que `send()` ainda não rodou — a tarefa 12 moveu `x.send()` para dentro
   * de `coletar().then(...)`, que é assíncrono. Um `x.abort()` nessa janela
   * não dispara evento nenhum (é o que o `XhrFalso.abort()` reproduz agora,
   * fiel ao XHR de verdade), então sem reconferir `sinal?.aborted` dentro do
   * `.then()` o PDF subiria mesmo cancelado — e sem isso, este teste trava
   * esperando uma promessa que nunca liquida.
   */
  it("abortar na janela entre open() e send() rejeita sem enviar", async () => {
    const x = new XhrFalso();
    vi.stubGlobal("XMLHttpRequest", function () { return x; });

    let resolverColeta!: (v: string | null) => void;
    coletarFalso.mockReset();
    coletarFalso.mockImplementationOnce(
      () => new Promise((r) => { resolverColeta = r; }));

    const controle = new AbortController();
    const promessa = enviarPdf(new File(["abc"], "planta.pdf"), controle.signal);

    // Ainda na janela: `coletar()` não resolveu, `send()` não rodou.
    controle.abort();
    expect(x.enviado).toBe(null);
    expect(x.abortado).toBe(true);

    // `coletar()` só resolve depois do abort — o cenário do achado.
    resolverColeta(null);

    await expect(promessa).rejects.toSatisfy(
      (e: unknown) => e instanceof DOMException && e.name === "AbortError");
    expect(x.enviado).toBe(null);
  });

  it("erro ao montar o cabeçalho não deixa a promessa presa", async () => {
    const x = new XhrFalso();
    vi.stubGlobal("XMLHttpRequest", function () { return x; });
    coletarFalso.mockResolvedValueOnce("hash-qualquer");
    x.setRequestHeader = () => { throw new Error("cabeçalho recusado"); };

    await expect(enviarPdf(new File(["abc"], "planta.pdf")))
      .rejects.toThrow("cabeçalho recusado");
  });

  it("o envio manda X-Impressao quando a coleta dá um hash", async () => {
    const x = new XhrFalso();
    vi.stubGlobal("XMLHttpRequest", function () { return x; });
    coletarFalso.mockResolvedValueOnce("hash-de-teste");

    const promessa = enviarPdf(new File(["abc"], "planta.pdf"));
    await vi.waitFor(() => { if (x.enviado === null) throw new Error("aguardando envio"); });

    expect(x.cabecalhos["X-Impressao"]).toBe("hash-de-teste");

    x.status = 200;
    x.responseText = JSON.stringify({ job_id: "a".repeat(32), nome: "planta.pdf",
                                      n_paginas: 1 });
    x.disparar("load");
    await expect(promessa).resolves.toMatchObject({ n_paginas: 1 });
  });

  it("o envio sem impressão coletada não manda o cabeçalho X-Impressao", async () => {
    const x = new XhrFalso();
    vi.stubGlobal("XMLHttpRequest", function () { return x; });
    coletarFalso.mockResolvedValueOnce(null);

    const promessa = enviarPdf(new File(["abc"], "planta.pdf"));
    await vi.waitFor(() => { if (x.enviado === null) throw new Error("aguardando envio"); });

    expect(x.cabecalhos["X-Impressao"]).toBeUndefined();

    x.status = 200;
    x.responseText = JSON.stringify({ job_id: "a".repeat(32), nome: "planta.pdf",
                                      n_paginas: 1 });
    x.disparar("load");
    await expect(promessa).resolves.toMatchObject({ n_paginas: 1 });
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

  /**
   * `ErroDaApi.codigo` chegou na tarefa 11 (`main.py:343` põe `codigo` ao
   * lado de `detail` na mesma `Recusa`), mas foi para produção sem teste — é
   * o item I1 da revisão. A tela inteira das cinco linhas de erro (tarefa 12)
   * distingue "sem vaga por cota" de "arquivo grande" por este campo, e não
   * por texto; um regressão aqui quebraria as cinco em silêncio.
   */
  it("preenche codigo a partir do corpo JSON de uma resposta de erro", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      respostaDe({ detail: "sem vaga", codigo: "cota_arquivos" }, 429)));
    await expect(lerEstado("a".repeat(32), 1)).rejects.toSatisfy(
      (e: unknown) => e instanceof ErroDaApi && e.codigo === "cota_arquivos");
  });

  it("resposta de erro sem codigo deixa o campo vazio", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      respostaDe({ detail: "não achei" }, 404)));
    await expect(lerEstado("a".repeat(32), 1)).rejects.toSatisfy(
      (e: unknown) => e instanceof ErroDaApi && e.codigo === "");
  });

  it("exportar manda X-Impressao quando a coleta dá um hash", async () => {
    coletarFalso.mockResolvedValueOnce("hash-exportar");
    let cabecalhosVistos: Record<string, string> | undefined;
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      cabecalhosVistos = init?.headers as Record<string, string>;
      return respostaDe({ chave: "k", url: "/u", cache: false, entidades: 1 });
    }));

    await exportar("a".repeat(32), 1, PEDIDO_MINIMO);

    expect(cabecalhosVistos?.["X-Impressao"]).toBe("hash-exportar");
  });

  it("exportar sem impressão coletada não manda o cabeçalho X-Impressao", async () => {
    coletarFalso.mockResolvedValueOnce(null);
    let cabecalhosVistos: Record<string, string> | undefined;
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      cabecalhosVistos = init?.headers as Record<string, string>;
      return respostaDe({ chave: "k", url: "/u", cache: false, entidades: 1 });
    }));

    await exportar("a".repeat(32), 1, PEDIDO_MINIMO);

    expect(cabecalhosVistos).not.toHaveProperty("X-Impressao");
  });
});
