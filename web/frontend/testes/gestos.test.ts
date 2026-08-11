import { describe, expect, it } from "vitest";
import { enquadrar, pontoDoPapel } from "../src/canvas.js";
import {
  aplicarArrasto, aplicarZoom, fatorDaRoda, PAUSA_DO_GESTO_MS,
} from "../src/gestos.js";

const base = enquadrar(595, 842, 1000, 800);

describe("gestos.ts", () => {
  it("zoom mantém parado o ponto sob o cursor", () => {
    const antes = pontoDoPapel(base, 321, 456);
    const depois = pontoDoPapel(aplicarZoom(base, 1.25, 321, 456), 321, 456);
    expect(depois.x).toBeCloseTo(antes.x, 6);
    expect(depois.y).toBeCloseTo(antes.y, 6);
  });

  it("zoom para fora também mantém o ponto", () => {
    const antes = pontoDoPapel(base, 10, 790);
    const depois = pontoDoPapel(aplicarZoom(base, 0.5, 10, 790), 10, 790);
    expect(depois.x).toBeCloseTo(antes.x, 6);
    expect(depois.y).toBeCloseTo(antes.y, 6);
  });

  it("arrastar move o desenho exatamente o que o dedo andou", () => {
    const v = aplicarArrasto(base, 40, -25);
    expect(v.dx).toBeCloseTo(base.dx + 40, 9);
    expect(v.dy).toBeCloseTo(base.dy - 25, 9);
    expect(v.escala).toBe(base.escala);
  });

  it("roda para cima aproxima e para baixo afasta", () => {
    expect(fatorDaRoda(-100)).toBeGreaterThan(1);
    expect(fatorDaRoda(100)).toBeLessThan(1);
    // Um passo para cada lado devolve ao ponto de partida.
    expect(fatorDaRoda(-100) * fatorDaRoda(100)).toBeCloseTo(1, 9);
  });
});

describe("fim de gesto", () => {
  it("a pausa é curta o bastante para não parecer travada", () => {
    // Acima de ~200 ms a espera vira lentidão percebida; abaixo de ~80 ms um
    // arrasto normal dispara preparação no meio do caminho.
    expect(PAUSA_DO_GESTO_MS).toBeGreaterThanOrEqual(80);
    expect(PAUSA_DO_GESTO_MS).toBeLessThanOrEqual(200);
  });
});
