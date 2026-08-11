import { describe, expect, it } from "vitest";
import {
  escalaPorDoisPontos, escalaPorEscalaDePlotagem, escalaValidaParaExportar,
  iniciarCalibragem, marcarPonto, medidaDigitada, posicaoDaLupa, razaoDeEscala,
  MM_POR_UNIDADE, type Unidade,
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

  /**
   * `NaN <= 0` é `false` em JavaScript — a guarda antiga (`medidaReal <= 0`)
   * deixava um `NaN` atravessar e devolver `NaN` como fator de escala. É o
   * caso de verdade: um usuário brasileiro digitando "0,50" com vírgula, que
   * `Number()` lê como `NaN`, sem nenhuma exceção para avisar.
   */
  it("recusa medida real NaN ou infinita, e não só zero ou negativa", () => {
    expect(() => escalaPorDoisPontos([0, 0], [10, 0], NaN)).toThrow(/positiva/i);
    expect(() => escalaPorDoisPontos([0, 0], [10, 0], Infinity))
      .toThrow(/positiva/i);
    expect(() => escalaPorDoisPontos([0, 0], [10, 0], -Infinity))
      .toThrow(/positiva/i);
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

/**
 * A ida e a volta da escala, que ninguém testava.
 *
 * Foi essa lacuna que deixou passar a tela calculando `1/escala` como se fosse
 * a razão de plotagem. É a conta que decide o tamanho da parede no CAD: se ela
 * erra, o DXF inteiro não serve.
 */
describe("razão de plotagem: ida e volta", () => {
  const UNIDADES: Unidade[] = ["mm", "cm", "m"];

  it("volta ao 1:50 de partida nas três unidades", () => {
    for (const u of UNIDADES) {
      expect(razaoDeEscala(escalaPorEscalaDePlotagem(50, u), u), u)
        .toBeCloseTo(50, 9);
    }
  });

  it("`escala = 0.01` em metros não é 1:100", () => {
    // O caso concreto que estava errado na tela: 1 pt de papel valendo 1 cm
    // real é 1:28,35, e não 1:100. Quem gravasse 1:50 acreditando em `1/escala`
    // punha 0,02 m/pt onde o certo é 0,0176 — 13% de erro em cada medida.
    expect(razaoDeEscala(0.01, "m")).not.toBeCloseTo(100, 0);
    expect(razaoDeEscala(0.01, "m")).toBeCloseTo(28.3464566929134, 9);
  });

  it("trocar a unidade preserva o tamanho físico", () => {
    // A fórmula do seletor de unidade em `secoes.ts`.
    const converter = (escala: number, de: Unidade, para: Unidade) =>
      (escala * MM_POR_UNIDADE[de]) / MM_POR_UNIDADE[para];

    const emMetros = escalaPorEscalaDePlotagem(50, "m");
    const emMilimetros = converter(emMetros, "m", "mm");
    // O mesmo comprimento, dito em outra unidade: a razão de plotagem não muda.
    expect(razaoDeEscala(emMilimetros, "mm")).toBeCloseTo(50, 9);
    expect(converter(emMilimetros, "mm", "m")).toBeCloseTo(emMetros, 12);
  });
});

/**
 * `Number("0,50")` é `NaN`: vírgula é como se escreve decimal em português, e
 * era exatamente o jeito natural de digitar que quebrava a calibração.
 */
describe("medidaDigitada aceita vírgula", () => {
  it("vírgula e ponto valem o mesmo", () => {
    expect(medidaDigitada("0,50")).toBeCloseTo(0.5, 12);
    expect(medidaDigitada("0.50")).toBeCloseTo(0.5, 12);
  });

  it("ignora espaço nas pontas", () => {
    expect(medidaDigitada(" 2 ")).toBe(2);
  });

  it("texto que não é número vira NaN", () => {
    expect(medidaDigitada("abc")).toBeNaN();
  });

  // `Number("")` é `0`, não `NaN` — comportamento do próprio `Number()`, não
  // desta função. É por isso que `escalaPorDoisPontos` guarda com `> 0`, e
  // não só com `Number.isFinite`: uma medida vazia também precisa ser
  // recusada, e `0` já cai fora da guarda sozinho.
  it("string vazia vira 0, e a guarda de escalaPorDoisPontos recusa 0 do mesmo jeito", () => {
    expect(medidaDigitada("")).toBe(0);
  });
});

describe("escalaValidaParaExportar: o cinto de segurança do botão Exportar", () => {
  it("aceita um número finito e positivo", () => {
    expect(escalaValidaParaExportar(0.01)).toBe(true);
  });

  it("recusa NaN, infinito, zero e negativo", () => {
    expect(escalaValidaParaExportar(NaN)).toBe(false);
    expect(escalaValidaParaExportar(Infinity)).toBe(false);
    expect(escalaValidaParaExportar(-Infinity)).toBe(false);
    expect(escalaValidaParaExportar(0)).toBe(false);
    expect(escalaValidaParaExportar(-1)).toBe(false);
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
