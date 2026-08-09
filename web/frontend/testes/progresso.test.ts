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
