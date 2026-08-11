/**
 * Espelho TypeScript de `optimize.select()`.
 *
 * Toda a paridade com o Python está presa por `tests/casos_select.json`. Se
 * mudar qualquer coisa aqui, os 1024 casos dizem se você quebrou o contrato.
 */

export const SEGMENTO = 0;

export type Opcoes = {
  excluded_layers: string[];
  drop_fills: boolean;
  min_len_mm: number;
  dedup: boolean;
  join_polylines: boolean;
  round_coords: boolean;
};

export type Atributos = {
  kind: Uint8Array;
  layer_id: Uint32Array;
  is_fill: Uint8Array;
  length_um: Uint32Array;
  dup_group: Int32Array;
  byte_cost: Uint32Array;
  layers: string[];
  n_groups: number;
};

export function selecionar(attrs: Atributos, opts: Opcoes): Uint8Array {
  const n = attrs.kind.length;

  // Conjunto de layers excluídos montado uma vez, antes do laço: dentro dele
  // seria uma busca por entidade, em até 3 milhões delas.
  const excluidos = new Set<number>();
  const nomesExcluidos = new Set(opts.excluded_layers);
  for (let i = 0; i < attrs.layers.length; i++) {
    if (nomesExcluidos.has(attrs.layers[i]!)) excluidos.add(i);
  }

  // `Math.round` e não `Math.trunc`: o Python escreve `int(x + 0.5)`
  // exatamente para casar com esta linha. Ver a docstring do select().
  const minLenUm = Math.round(opts.min_len_mm * 1000.0);

  const emitido = new Uint8Array(attrs.n_groups);
  const mascara = new Uint8Array(n);

  for (let i = 0; i < n; i++) {
    if (excluidos.has(attrs.layer_id[i]!)) continue;
    if (opts.drop_fills && attrs.is_fill[i]) continue;
    if (attrs.kind[i] === SEGMENTO) {
      // O filtro de comprimento vem antes de reservar o grupo: um segmento
      // curto demais não pode impedir o próximo do mesmo grupo de ser emitido.
      if (minLenUm > 0 && attrs.length_um[i]! < minLenUm) continue;
      if (opts.dedup) {
        const g = attrs.dup_group[i]!;
        if (emitido[g]) continue;
        emitido[g] = 1;
      }
    }
    mascara[i] = 1;
  }

  return mascara;
}
