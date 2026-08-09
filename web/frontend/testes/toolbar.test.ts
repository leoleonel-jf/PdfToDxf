import { describe, expect, it } from "vitest";
import { opcoesEfetivas, textoDaEstimativa } from "../src/toolbar.js";

const base = {
  opcoes: {
    excluded_layers: [], drop_fills: false, min_len_mm: 0,
    dedup: false, join_polylines: false, round_coords: false,
  },
  layersDesligados: new Set<string>(),
  escala: 0.01,
  unidade: "m" as const,
  parcial: false,
  bytes: 0,
  sobreviventes: 0,
};

describe("toolbar.ts", () => {
  it("layers desligados viram excluded_layers, em ordem estável", () => {
    const e = { ...base, layersDesligados: new Set(["TEXTO", "COTAS"]) };
    expect(opcoesEfetivas(e).excluded_layers).toEqual(["COTAS", "TEXTO"]);
  });

  it("a chave da exportação não muda por causa da ordem dos cliques", () => {
    const a = opcoesEfetivas({ ...base, layersDesligados: new Set(["A", "B"]) });
    const b = opcoesEfetivas({ ...base, layersDesligados: new Set(["B", "A"]) });
    expect(a.excluded_layers).toEqual(b.excluded_layers);
  });

  it("a estimativa parcial vem marcada", () => {
    expect(textoDaEstimativa(1_500_000, false)).toBe("≈ 1,5 MB");
    expect(textoDaEstimativa(1_500_000, true)).toBe("≈ 1,5 MB (parcial)");
    expect(textoDaEstimativa(2048, false)).toBe("≈ 2,0 kB");
  });
});
