/**
 * Cálculo do fator de escala: pontos de papel (1/72") → unidade real.
 *
 * Espelho de `pdftodxf/calibration.py`. Aritmética simples, mas é ela que
 * decide se a planta sai com as medidas certas no CAD — por isso vive num
 * arquivo próprio, com teste próprio, em vez de espalhada pela interface.
 */

export const PT_PARA_MM = 25.4 / 72.0;

export type Unidade = "mm" | "cm" | "m";

export const MM_POR_UNIDADE: Record<Unidade, number> = {
  mm: 1.0, cm: 10.0, m: 1000.0,
};

/** Código $INSUNITS do DXF, para exibição; quem grava o DXF é o servidor. */
export const INSUNITS: Record<Unidade, number> = { mm: 4, cm: 5, m: 6 };

export function escalaPorDoisPontos(p1: [number, number], p2: [number, number],
                                    medidaReal: number): number {
  const papel = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
  if (papel < 1e-9) throw new Error("Os dois pontos de calibração coincidem.");
  if (medidaReal <= 0) throw new Error("A medida real deve ser positiva.");
  return medidaReal / papel;
}

export function escalaPorEscalaDePlotagem(razao: number,
                                          unidade: Unidade = "m"): number {
  if (razao <= 0) throw new Error("A escala deve ser positiva (ex.: 50 para 1:50).");
  return (PT_PARA_MM * razao) / MM_POR_UNIDADE[unidade];
}
