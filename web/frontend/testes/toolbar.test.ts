import { describe, expect, it } from "vitest";
import {
  formatarBytes, opcoesEfetivas, textoDaComparacao,
} from "../src/toolbar.js";

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
  bytesBase: 0,
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

  it("a comparação mostra base, atual e a redução", () => {
    expect(textoDaComparacao(12_300_000, 4_100_000, false))
      .toBe("12,3 MB → 4,1 MB · −67%");
  });

  it("sem redução, mostra um número só", () => {
    expect(textoDaComparacao(4_100_000, 4_100_000, false)).toBe("4,1 MB");
  });

  it("redução abaixo de 1% não vira ruído na barra", () => {
    // Um número só, e é o atual: a barra tem de dizer o que o arquivo vai
    // pesar, não o que ele pesaria sem compactação nenhuma.
    expect(textoDaComparacao(1_000_000, 999_000, false)).toBe("999,0 kB");
  });

  it("a comparação parcial vem marcada", () => {
    expect(textoDaComparacao(12_300_000, 4_100_000, true))
      .toBe("12,3 MB → 4,1 MB · −67% (parcial)");
  });

  it("base zero não divide por zero", () => {
    expect(textoDaComparacao(0, 0, false)).toBe("0,0 kB");
  });

  it("formatarBytes vira kB abaixo de 1 MB", () => {
    expect(formatarBytes(2048)).toBe("2,0 kB");
    expect(formatarBytes(1_500_000)).toBe("1,5 MB");
  });
});
