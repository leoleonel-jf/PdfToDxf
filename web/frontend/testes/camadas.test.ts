import { describe, expect, it } from "vitest";
import {
  precisaDeBusca, proporcaoRepetida, resumoDasCamadas,
} from "../src/camadas.js";
import type { Geometria } from "../src/formato.js";

/** Geometria mínima: só o que `resumoDasCamadas` lê é significativo. */
function geo(layers: string[], layerId: number[], cor: number[]): Geometria {
  const n = layerId.length;
  return {
    n,
    kind: new Uint8Array(n),
    layer_id: new Uint32Array(layerId),
    is_fill: new Uint8Array(n),
    length_um: new Uint32Array(n),
    dup_group: new Int32Array(n),
    byte_cost: new Uint32Array(n),
    layers,
    n_groups: 1,
    idx: new Uint32Array(n),
    cor: new Uint32Array(cor),
    coord_off: new Uint32Array(n + 1),
    coords: new Float32Array(0),
    texto_off: new Uint32Array(n + 1),
    texto: new Uint8Array(0),
  };
}

describe("camadas.ts", () => {
  it("conta as entidades de cada camada", () => {
    const r = resumoDasCamadas(geo(["A", "B"], [0, 0, 1], [1, 1, 2]));
    expect(r.map((c) => [c.nome, c.n])).toEqual([["A", 2], ["B", 1]]);
  });

  it("a soma das contagens é o total de entidades", () => {
    const r = resumoDasCamadas(geo(["A", "B", "C"], [2, 0, 2, 1, 2], [0, 0, 0, 0, 0]));
    expect(r.reduce((s, c) => s + c.n, 0)).toBe(5);
  });

  it("a cor é a mais frequente da camada, não a primeira", () => {
    const r = resumoDasCamadas(
      geo(["A"], [0, 0, 0], [0xff0000, 0x00ff00, 0x00ff00]));
    expect(r[0]!.cor).toBe(0x00ff00);
  });

  it("empate de frequência resolve pela menor cor, não pela ordem de chegada", () => {
    const a = resumoDasCamadas(geo(["A"], [0, 0], [0xff0000, 0x0000ff]));
    const b = resumoDasCamadas(geo(["A"], [0, 0], [0x0000ff, 0xff0000]));
    expect(a[0]!.cor).toBe(0x0000ff);
    expect(b[0]!.cor).toBe(a[0]!.cor);
  });

  it("camada sem nenhuma entidade não quebra e vem com contagem zero", () => {
    const r = resumoDasCamadas(geo(["A", "VAZIA"], [0], [0x123456]));
    expect(r[1]).toEqual({ indice: 1, nome: "VAZIA", n: 0, cor: 0 });
  });

  it("o índice devolvido é a posição em layers", () => {
    const r = resumoDasCamadas(geo(["A", "B", "C"], [1], [7]));
    expect(r.map((c) => c.indice)).toEqual([0, 1, 2]);
  });

  it("a proporção de repetidos vem dos grupos de duplicata", () => {
    // 5 entidades em 2 grupos: 3 são repetição de alguém.
    const g = geo(["A"], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]);
    g.n_groups = 2;
    expect(proporcaoRepetida(g)).toBe(60);
  });

  it("sem repetição nenhuma, a proporção é zero e não some", () => {
    const g = geo(["A"], [0, 0], [0, 0]);
    g.n_groups = 2;
    expect(proporcaoRepetida(g)).toBe(0);
  });

  it("página vazia não divide por zero", () => {
    const g = geo(["A"], [], []);
    g.n_groups = 0;
    expect(proporcaoRepetida(g)).toBe(null);
  });

  it("a busca de camadas aparece acima de quinze", () => {
    expect(precisaDeBusca(15)).toBe(false);
    expect(precisaDeBusca(16)).toBe(true);
  });
});
