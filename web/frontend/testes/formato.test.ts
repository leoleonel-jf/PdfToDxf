import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { coordenadasDe, lerGeometria, textoDe } from "../src/formato.js";

function caminhoFixture(nome: string): string {
  return fileURLToPath(new URL(`../../../tests/fixtures/${nome}`, import.meta.url));
}

const cru = readFileSync(caminhoFixture("geometria_exemplo.bin"));
const buffer = cru.buffer.slice(cru.byteOffset, cru.byteOffset + cru.byteLength);
const esperado = JSON.parse(readFileSync(caminhoFixture("geometria_exemplo.json"), "utf-8"));

describe("formato.ts lê o que o packing.py escreveu", () => {
  const g = lerGeometria(buffer as ArrayBuffer, esperado.layers, esperado.n_groups);

  it("conta as entidades", () => {
    expect(g.n).toBe(esperado.n);
  });

  it("lê os atributos", () => {
    expect([...g.idx]).toEqual(esperado.idx);
    expect([...g.kind]).toEqual(esperado.kind);
    expect([...g.layer_id]).toEqual(esperado.layer_id);
    expect([...g.is_fill]).toEqual(esperado.is_fill);
    expect([...g.length_um]).toEqual(esperado.length_um);
    expect([...g.dup_group]).toEqual(esperado.dup_group);
    expect([...g.byte_cost]).toEqual(esperado.byte_cost);
    expect([...g.cor]).toEqual(esperado.cor);
  });

  it("lê as coordenadas de cada tipo", () => {
    for (let i = 0; i < g.n; i++) {
      const obtido = [...coordenadasDe(g, i)].map((v) => Number(v.toFixed(4)));
      expect(obtido).toEqual(esperado.coordenadas[i]);
    }
  });

  it("lê o texto acentuado", () => {
    for (let i = 0; i < g.n; i++) {
      expect(textoDe(g, i)).toBe(esperado.textos[i]);
    }
  });

  it("recusa um arquivo que não é do formato", () => {
    const lixo = new Uint8Array(64);
    lixo.set([78, 79, 80, 69]);   // "NOPE"
    expect(() => lerGeometria(lixo.buffer, [], 0)).toThrow(/formato/i);
  });
});
