import { describe, expect, it } from "vitest";
import { enquadrar } from "../src/canvas.js";
import { criarPintor, passo, type Cena } from "../src/pintor.js";
import { ordenarPorComprimento } from "../src/ordem.js";
import { UM_POR_PONTO } from "../src/lista.js";
import type { Geometria } from "../src/formato.js";
import { CaminhoGravado, ContextoGravado } from "./ajuda/canvas2d.js";

function geometriaDe(quantos: number): Geometria {
  const coords = new Float32Array(quantos * 4);
  const length_um = new Uint32Array(quantos);
  const coord_off = new Uint32Array(quantos + 1);
  for (let i = 0; i < quantos; i++) {
    // Espalhados o bastante para não disputarem a mesma região.
    const x = (i % 50) * 2, y = Math.floor(i / 50) * 2;
    coords.set([x, y, x + 1, y + 1], i * 4);
    coord_off[i + 1] = (i + 1) * 4;
    length_um[i] = Math.round(Math.hypot(1, 1) * UM_POR_PONTO);
  }
  return {
    n: quantos, layers: ["0"], n_groups: quantos,
    idx: Uint32Array.from({ length: quantos }, (_, i) => i),
    kind: new Uint8Array(quantos),
    layer_id: new Uint32Array(quantos),
    is_fill: new Uint8Array(quantos),
    length_um,
    dup_group: Int32Array.from({ length: quantos }, (_, i) => i),
    byte_cost: new Uint32Array(quantos),
    cor: new Uint32Array(quantos).fill(0xffffffff),
    coord_off, coords,
    texto_off: new Uint32Array(quantos + 1),
    texto: new Uint8Array(0),
  };
}

function cenaDe(g: Geometria, geracao = 1): Cena {
  return {
    g,
    mascara: new Uint8Array(g.n).fill(1),
    ordem: ordenarPorComprimento(g.length_um),
    v: enquadrar(100, 100, 400, 400),
    larguraTela: 400, alturaTela: 400,
    geracao,
  };
}

describe("pintor.ts", () => {
  it("termina em vários quadros quando o orçamento é apertado", () => {
    const g = geometriaDe(500);
    const cena = cenaDe(g);
    const p = criarPintor();
    let quadros = 0;
    let acabou = false;
    while (!acabou && quadros < 100) {
      acabou = passo(p, cena, new ContextoGravado(),
                     () => new CaminhoGravado(), 40);
      quadros++;
    }
    expect(acabou).toBe(true);
    expect(quadros).toBeGreaterThan(1);
  });

  it("desenha, ao fim, tudo o que a lista escolheu", () => {
    const g = geometriaDe(300);
    const cena = cenaDe(g);
    const p = criarPintor();
    const ctx = new ContextoGravado();
    while (!passo(p, cena, ctx, () => new CaminhoGravado(), 1000));
    expect(p.preparo!.quantos).toBe(300);
    expect(p.desenhadas).toBe(300);
  });

  it("mudar a geração recomeça o preparo", () => {
    const g = geometriaDe(300);
    const p = criarPintor();
    while (!passo(p, cenaDe(g, 1), new ContextoGravado(),
                  () => new CaminhoGravado(), 1000));
    const primeira = p.preparo;

    const outra = cenaDe(g, 2);
    outra.mascara = new Uint8Array(g.n);          // nada sobrevive
    passo(p, outra, new ContextoGravado(), () => new CaminhoGravado(), 1000);
    expect(p.preparo).not.toBe(primeira);
    expect(p.preparo!.quantos).toBe(0);
  });

  it("pan pequeno não prepara de novo", () => {
    const g = geometriaDe(300);
    const cena = cenaDe(g);
    const p = criarPintor();
    while (!passo(p, cena, new ContextoGravado(),
                  () => new CaminhoGravado(), 1000));
    const antes = p.preparo;

    const movida: Cena = { ...cena, v: { ...cena.v, dx: cena.v.dx - 30 } };
    passo(p, movida, new ContextoGravado(), () => new CaminhoGravado(), 1000);
    expect(p.preparo).toBe(antes);
  });
});
