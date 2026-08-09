import { afterEach, describe, expect, it, vi } from "vitest";
import { ErroDaApi, esperarPagina, lerEstado } from "../src/api.js";

function respostaDe(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status, headers: { "content-type": "application/json" },
  });
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
});
