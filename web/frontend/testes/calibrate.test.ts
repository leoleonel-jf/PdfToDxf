import { describe, expect, it } from "vitest";
import { escalaPorDoisPontos, escalaPorEscalaDePlotagem } from "../src/calibrate.js";

describe("calibrate.ts espelha calibration.py", () => {
  it("dois pontos: fator é medida real dividida pela distância no papel", () => {
    // 300 pt no papel medindo 3,00 m na planta
    expect(escalaPorDoisPontos([0, 0], [300, 0], 3.0)).toBeCloseTo(0.01, 12);
    // distância na diagonal: 3-4-5
    expect(escalaPorDoisPontos([0, 0], [30, 40], 5.0)).toBeCloseTo(0.1, 12);
  });

  it("recusa dois pontos coincidentes", () => {
    expect(() => escalaPorDoisPontos([7, 7], [7, 7], 1.0))
      .toThrow(/coincidem/i);
  });

  it("recusa medida real não positiva", () => {
    expect(() => escalaPorDoisPontos([0, 0], [10, 0], 0)).toThrow(/positiva/i);
    expect(() => escalaPorDoisPontos([0, 0], [10, 0], -2)).toThrow(/positiva/i);
  });

  it("escala de plotagem 1:50 em metros", () => {
    // 1 pt = 25.4/72 mm de papel = 0.352777… mm; ×50 = 17.638… mm reais
    expect(escalaPorEscalaDePlotagem(50, "m")).toBeCloseTo(0.0176388888, 10);
    expect(escalaPorEscalaDePlotagem(50, "mm")).toBeCloseTo(17.6388888888, 8);
  });

  it("recusa razão não positiva", () => {
    expect(() => escalaPorEscalaDePlotagem(0, "m")).toThrow(/positiva/i);
  });
});
