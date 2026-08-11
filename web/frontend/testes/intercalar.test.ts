import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { intercalar, type Geometria } from "../src/formato.js";
import { selecionar } from "../src/select.js";
import { comoTexto } from "./ajuda/contrato.js";

const f = JSON.parse(readFileSync(
  fileURLToPath(new URL("../../../tests/fixtures/intercalacao.json", import.meta.url)),
  "utf-8"));

const CODIGO: Record<string, number> = {
  Segment: 0, Polyline: 1, Arc: 2, Bezier: 3, TextItem: 4,
};

/** Monta uma parte a partir dos índices que o dividir() escolheu. */
function parte(indices: number[]): Geometria {
  const n = indices.length;
  const g: Geometria = {
    n,
    layers: f.layers,
    n_groups: f.n_groups,
    idx: Uint32Array.from(indices),
    kind: Uint8Array.from(indices, (i) => CODIGO[f.kind[i]]!),
    layer_id: Uint32Array.from(indices, (i) => f.layer_id[i]),
    is_fill: Uint8Array.from(indices, (i) => (f.is_fill[i] ? 1 : 0)),
    length_um: Uint32Array.from(indices, (i) => f.length_um[i]),
    dup_group: Int32Array.from(indices, (i) => f.dup_group[i]),
    byte_cost: Uint32Array.from(indices, (i) => f.byte_cost[i]),
    cor: Uint32Array.from(indices, () => 0xffffffff),
    // Duas coordenadas por entidade, só para a intercalação ter o que mover.
    coord_off: Uint32Array.from({ length: n + 1 }, (_, k) => k * 2),
    coords: Float32Array.from(indices.flatMap((i) => [i, i + 0.5])),
    texto_off: new Uint32Array(n + 1),
    texto: new Uint8Array(0),
  };
  return g;
}

describe("intercalar devolve a ordem original", () => {
  const juntos = intercalar(parte(f.esqueleto), parte(f.detalhe));

  it("cobre tudo, uma vez só, em ordem crescente", () => {
    expect(juntos.n).toBe(f.esqueleto.length + f.detalhe.length);
    expect([...juntos.idx]).toEqual([...juntos.idx].sort((a, b) => a - b));
    expect(new Set(juntos.idx).size).toBe(juntos.n);
  });

  it("carrega as coordenadas junto com a entidade certa", () => {
    for (let k = 0; k < juntos.n; k++) {
      const original = juntos.idx[k]!;
      const c = juntos.coords.subarray(juntos.coord_off[k]!, juntos.coord_off[k + 1]!);
      expect([...c]).toEqual([original, original + 0.5]);
    }
  });

  it("com dedup ligado, bate com o select() do Python sobre a lista inteira", () => {
    expect(comoTexto(selecionar(juntos, f.opcoes))).toBe(f.mascara_esperada);
  });

  it("decidir por parte separada erra — é por isso que a intercalação existe", () => {
    const soEsqueleto = comoTexto(selecionar(parte(f.esqueleto), f.opcoes));
    const soDetalhe = comoTexto(selecionar(parte(f.detalhe), f.opcoes));
    const sobreviventesSeparados =
      [...soEsqueleto, ...soDetalhe].filter((c) => c === "1").length;
    const sobreviventesCertos = [...f.mascara_esperada].filter((c) => c === "1").length;
    expect(sobreviventesSeparados).toBeGreaterThan(sobreviventesCertos);
  });
});
