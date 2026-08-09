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
