import { describe, expect, it } from "vitest";
import {
  escalaPorDoisPontos, escalaPorEscalaDePlotagem, iniciarCalibragem,
  marcarPonto, posicaoDaLupa,
} from "../src/calibrate.js";
import { enquadrar } from "../src/canvas.js";

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
    // 1 pt = 25.4/72 mm de papel = 0.352777… mm; ×50 = 17.638… mm reais.
    // O esperado precisa de dígitos suficientes para a precisão pedida: com
    // `0.0176388888` e 10 casas o teste falha por 8,9e-11, e o culpado é o
    // literal truncado, não a conta.
    expect(escalaPorEscalaDePlotagem(50, "m")).toBeCloseTo(0.0176388888888889, 10);
    expect(escalaPorEscalaDePlotagem(50, "mm")).toBeCloseTo(17.6388888888889, 8);
  });

  it("recusa razão não positiva", () => {
    expect(() => escalaPorEscalaDePlotagem(0, "m")).toThrow(/positiva/i);
  });
});

describe("gesto da calibração", () => {
  const v = enquadrar(595, 842, 1000, 800);

  it("dois cliques fecham a calibragem, em coordenadas de papel", () => {
    let c = iniciarCalibragem();
    expect(c.ativa).toBe(true);
    c = marcarPonto(c, v, 100, 200);
    expect(c.pontos.length).toBe(1);
    expect(c.ativa).toBe(true);
    c = marcarPonto(c, v, 400, 200);
    expect(c.pontos.length).toBe(2);
    expect(c.ativa).toBe(false);
    // Mesmo Y de tela, então mesmo Y de papel: a distância é só horizontal.
    expect(c.pontos[0]![1]).toBeCloseTo(c.pontos[1]![1], 9);
  });

  it("um terceiro clique não entra", () => {
    let c = iniciarCalibragem();
    c = marcarPonto(c, v, 10, 10);
    c = marcarPonto(c, v, 20, 20);
    c = marcarPonto(c, v, 30, 30);
    expect(c.pontos.length).toBe(2);
  });

  it("a lupa foge do dedo e não sai da tela", () => {
    // Perto do canto superior esquerdo, a lupa vai para a direita e para baixo.
    const perto = posicaoDaLupa(10, 10, 1000, 800, 120);
    expect(perto.x).toBeGreaterThanOrEqual(0);
    expect(perto.y).toBeGreaterThanOrEqual(0);
    // Perto do canto oposto, ela cabe inteira dentro da tela.
    const longe = posicaoDaLupa(995, 795, 1000, 800, 120);
    expect(longe.x + 120).toBeLessThanOrEqual(1000);
    expect(longe.y + 120).toBeLessThanOrEqual(800);
  });
});
