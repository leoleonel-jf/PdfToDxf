import { describe, expect, it } from "vitest";
import { janelaVisivel, enquadrar, type Retangulo } from "../src/canvas.js";
import { ordenarPorComprimento } from "../src/ordem.js";
import {
  avancarPreparo, iniciarPreparo, prepararTudo, precisaPreparar,
  TETO_POR_REGIAO, UM_POR_PONTO,
} from "../src/lista.js";
import type { Geometria } from "../src/formato.js";

/**
 * Segmentos sintéticos, todos no mesmo layer, com posição e comprimento dados.
 * Monta só o que a lista lê — é de propósito: se `lista.ts` passar a depender
 * de outro campo, este auxiliar deixa de compilar e o autor fica sabendo.
 */
function geometriaDe(segs: Array<[number, number, number, number]>): Geometria {
  const n = segs.length;
  const coords = new Float32Array(n * 4);
  const length_um = new Uint32Array(n);
  const coord_off = new Uint32Array(n + 1);
  for (let i = 0; i < n; i++) {
    const [x1, y1, x2, y2] = segs[i]!;
    coords.set([x1, y1, x2, y2], i * 4);
    coord_off[i + 1] = (i + 1) * 4;
    length_um[i] = Math.round(Math.hypot(x2 - x1, y2 - y1) * UM_POR_PONTO);
  }
  return {
    n, layers: ["0"], n_groups: n,
    idx: Uint32Array.from({ length: n }, (_, i) => i),
    kind: new Uint8Array(n),                 // tudo Segment
    layer_id: new Uint32Array(n),
    is_fill: new Uint8Array(n),
    length_um,
    dup_group: Int32Array.from({ length: n }, (_, i) => i),
    byte_cost: new Uint32Array(n),
    cor: new Uint32Array(n).fill(0xffffffff),
    coord_off, coords,
    texto_off: new Uint32Array(n + 1),
    texto: new Uint8Array(0),
  };
}

const FOLHA: Retangulo = { x0: 0, y0: 0, x1: 100, y1: 100 };

describe("lista.ts", () => {
  it("nunca passa do teto por região", () => {
    // Dez segmentos empilhados no mesmo ponto: uma região só.
    const g = geometriaDe(Array.from({ length: 10 },
                                     (_, i) => [1, 1, 1 + i * 0.01, 1] as
                                       [number, number, number, number]));
    const ordem = ordenarPorComprimento(g.length_um);
    const p = prepararTudo(g, new Uint8Array(10).fill(1), ordem, FOLHA, 1);
    expect(p.quantos).toBe(TETO_POR_REGIAO);
  });

  it("entre candidatos da mesma região, fica o mais comprido", () => {
    const g = geometriaDe([[1, 1, 1.5, 1], [1, 1, 9, 1], [1, 1, 3, 1]]);
    const ordem = ordenarPorComprimento(g.length_um);
    // Teto de 4, mas só três candidatos: entram todos, na ordem do mais longo.
    const p = prepararTudo(g, new Uint8Array(3).fill(1), ordem, FOLHA, 1);
    expect([...p.lista.subarray(0, p.quantos)]).toEqual([1, 2, 0]);
  });

  it("nunca inclui o que a máscara zerou", () => {
    const g = geometriaDe([[1, 1, 9, 1], [50, 50, 58, 50]]);
    const ordem = ordenarPorComprimento(g.length_um);
    const mascara = Uint8Array.from([0, 1]);
    const p = prepararTudo(g, mascara, ordem, FOLHA, 1);
    expect([...p.lista.subarray(0, p.quantos)]).toEqual([1]);
  });

  it("quem não é segmento entra sempre, sem disputar vaga", () => {
    // Dez segmentos empilhados mais um texto no mesmo ponto: os segmentos são
    // cortados pelo teto, o texto não.
    const g = geometriaDe(Array.from({ length: 11 },
                                     (_, i) => [1, 1, 1 + i * 0.01, 1] as
                                       [number, number, number, number]));
    g.kind[10] = 4;                    // TextItem
    const ordem = ordenarPorComprimento(g.length_um);
    const p = prepararTudo(g, new Uint8Array(11).fill(1), ordem, FOLHA, 1);
    const escolhidos = [...p.lista.subarray(0, p.quantos)];
    expect(escolhidos).toContain(10);
    expect(escolhidos.filter((i) => i !== 10).length).toBe(TETO_POR_REGIAO);
  });

  it("não inclui o que está fora da janela", () => {
    const g = geometriaDe([[1, 1, 9, 1], [500, 500, 508, 500]]);
    const ordem = ordenarPorComprimento(g.length_um);
    const p = prepararTudo(g, new Uint8Array(2).fill(1), ordem, FOLHA, 1);
    expect([...p.lista.subarray(0, p.quantos)]).toEqual([0]);
  });

  it("fatiado dá exatamente a mesma lista que inteiro", () => {
    // O teste que impede o desenho de depender da velocidade da máquina.
    const segs: Array<[number, number, number, number]> = [];
    let semente = 7;
    const sorteio = () => {
      semente = (semente * 1664525 + 1013904223) >>> 0;
      return semente / 4294967296;
    };
    for (let i = 0; i < 4000; i++) {
      const x = sorteio() * 100, y = sorteio() * 100;
      const c = 0.05 + sorteio() * 5;
      segs.push([x, y, x + c, y + c / 2]);
    }
    const g = geometriaDe(segs);
    const mascara = Uint8Array.from({ length: segs.length },
                                    (_, i) => (i % 7 === 0 ? 0 : 1));
    const ordem = ordenarPorComprimento(g.length_um);

    const inteiro = prepararTudo(g, mascara, ordem, FOLHA, 1);

    let fatiado = iniciarPreparo(g, FOLHA, 1);
    let voltas = 0;
    while (!fatiado.pronto) {
      fatiado = avancarPreparo(fatiado, g, mascara, ordem, 37);
      voltas++;
    }
    expect(voltas).toBeGreaterThan(1);   // fatiou de verdade
    expect(fatiado.quantos).toBe(inteiro.quantos);
    expect([...fatiado.lista.subarray(0, fatiado.quantos)])
      .toEqual([...inteiro.lista.subarray(0, inteiro.quantos)]);
  });

  it("a lista não cresce quando o zoom fecha", () => {
    // É a razão de a janela existir. Com a folha inteira e com zoom de 20x, o
    // número de regiões é o mesmo, então a lista fica na mesma ordem.
    const segs: Array<[number, number, number, number]> = [];
    let semente = 99;
    const sorteio = () => {
      semente = (semente * 1664525 + 1013904223) >>> 0;
      return semente / 4294967296;
    };
    for (let i = 0; i < 20000; i++) {
      const x = sorteio() * 100, y = sorteio() * 100;
      segs.push([x, y, x + 0.3, y + 0.1]);
    }
    const g = geometriaDe(segs);
    const mascara = new Uint8Array(segs.length).fill(1);
    const ordem = ordenarPorComprimento(g.length_um);

    const larga = prepararTudo(g, mascara, ordem, FOLHA, 1);
    const perto = prepararTudo(g, mascara, ordem,
                               { x0: 40, y0: 40, x1: 45, y1: 45 }, 20);
    expect(perto.quantos).toBeLessThanOrEqual(larga.quantos * 2);
  });

  it("sabe dizer quando a vista saiu da janela", () => {
    const g = geometriaDe([[1, 1, 9, 1]]);
    const ordem = ordenarPorComprimento(g.length_um);
    const v = enquadrar(100, 100, 400, 400);
    const janela = janelaVisivel(v, 400, 400, 0.5);
    const p = prepararTudo(g, new Uint8Array(1).fill(1), ordem, janela, v.escala);

    expect(precisaPreparar(p, v, 400, 400)).toBe(false);
    // Zoom de 4x sai da faixa do fator 2.
    expect(precisaPreparar(p, { ...v, escala: v.escala * 4 }, 400, 400)).toBe(true);
    // Arrastar uma tela inteira sai da janela de meia tela de folga.
    expect(precisaPreparar(p, { ...v, dx: v.dx - 400 }, 400, 400)).toBe(true);
    // Arrastar um quarto de tela continua dentro.
    expect(precisaPreparar(p, { ...v, dx: v.dx - 100 }, 400, 400)).toBe(false);
  });
});
