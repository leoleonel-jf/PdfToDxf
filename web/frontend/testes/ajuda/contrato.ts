import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { Atributos, Opcoes } from "../../src/select.js";

/** Código numérico do `kind`, igual ao de web/api/packing.py. */
const CODIGO: Record<string, number> = {
  Segment: 0, Polyline: 1, Arc: 2, Bezier: 3, TextItem: 4,
};

export type Caso = {
  nome: string;
  tabela: number;
  opcoes: Opcoes;
  esperado: string;        // máscara como texto de 0 e 1
  bytes_esperado: number;
};

/**
 * Lê o contrato congelado e traduz o `kind` de string para código.
 *
 * A tradução mora aqui, e só aqui: o `select.ts` compara inteiros porque é isso
 * que chega do `geometry.bin`, e o `casos_select.json` guarda strings porque é
 * assim que o `classify()` do Python as produz. Nenhum dos dois muda por causa
 * do outro.
 */
export function carregarContrato(): { casos: Caso[]; tabelas: Atributos[] } {
  const caminho = fileURLToPath(
    new URL("../../../../tests/casos_select.json", import.meta.url));
  const cru = JSON.parse(readFileSync(caminho, "utf-8"));

  const tabelas: Atributos[] = cru.tabelas.map((t: any) => ({
    kind: Uint8Array.from(t.kind, (nome: string) => {
      const codigo = CODIGO[nome];
      if (codigo === undefined) throw new Error(`kind desconhecido: ${nome}`);
      return codigo;
    }),
    layer_id: Uint32Array.from(t.layer_id),
    is_fill: Uint8Array.from(t.is_fill, (v: boolean) => (v ? 1 : 0)),
    length_um: Uint32Array.from(t.length_um),
    dup_group: Int32Array.from(t.dup_group),
    byte_cost: Uint32Array.from(t.byte_cost),
    layers: t.layers,
    n_groups: t.n_groups,
  }));

  return { casos: cru.casos, tabelas };
}

/** Converte a máscara em texto de 0 e 1, como o contrato a guarda. */
export function comoTexto(mascara: Uint8Array): string {
  let saida = "";
  for (const v of mascara) saida += v ? "1" : "0";
  return saida;
}
