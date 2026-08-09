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
