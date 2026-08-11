/**
 * Cálculo do fator de escala: pontos de papel (1/72") → unidade real.
 *
 * Espelho de `pdftodxf/calibration.py`. Aritmética simples, mas é ela que
 * decide se a planta sai com as medidas certas no CAD — por isso vive num
 * arquivo próprio, com teste próprio, em vez de espalhada pela interface.
 */
import { pontoDoPapel, type Vista } from "./canvas.js";

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
  // `medidaReal <= 0` deixaria passar `NaN`: em JavaScript `NaN <= 0` é
  // `false`. É o caso de verdade — um usuário brasileiro digitando "0,50" com
  // vírgula, que `Number()` lê como `NaN` — e sem a guarda certa ele atravessa
  // até o `JSON.stringify` da exportação, que o transforma em `null` e o
  // servidor recusa com um 422 que a tela não sabia explicar. `!(x > 0)`
  // sozinho ainda deixaria passar `Infinity` (`Infinity > 0` é `true`), então
  // o `Number.isFinite` entra para barrar esse caso também.
  if (!(Number.isFinite(medidaReal) && medidaReal > 0)) {
    throw new Error("A medida real deve ser positiva.");
  }
  return medidaReal / papel;
}

/**
 * Lê a medida que o usuário digitou, aceitando vírgula.
 *
 * `Number("0,50")` é `NaN`, e vírgula é como se escreve decimal em português —
 * ou seja, o jeito natural de digitar era exatamente o que quebrava a
 * calibração. Devolve `NaN` para entrada que não é número, e quem chama
 * decide o que fazer com isso.
 */
export function medidaDigitada(texto: string): number {
  return Number(texto.trim().replace(",", "."));
}

/**
 * Se `escala` pode ir para o servidor.
 *
 * O cinto de segurança do botão Exportar: a guarda de `escalaPorDoisPontos` e o
 * campo "Escala 1:" (com seu próprio `v > 0`) já não deveriam deixar `NaN` ou
 * infinito chegar aqui — mas "não deveriam" não é "não podem", e um
 * `JSON.stringify` de `NaN` vira `null` em silêncio. Melhor recusar na tela,
 * com uma mensagem que diz o que fazer, do que deixar o servidor recusar com
 * um 422 sem contexto nenhum.
 */
export function escalaValidaParaExportar(escala: number): boolean {
  return Number.isFinite(escala) && escala > 0;
}

export function escalaPorEscalaDePlotagem(razao: number,
                                          unidade: Unidade = "m"): number {
  if (razao <= 0) throw new Error("A escala deve ser positiva (ex.: 50 para 1:50).");
  return (PT_PARA_MM * razao) / MM_POR_UNIDADE[unidade];
}

/**
 * A inversa de `escalaPorEscalaDePlotagem`: o "N" de 1:N.
 *
 * A tela precisa mostrar a razão de plotagem, e calcular `1/escala` para isso
 * está errado — `escala` é unidade real por ponto de papel, não uma razão. Com
 * a unidade em metros, `escala = 0.01` é 1:28, não 1:100.
 */
export function razaoDeEscala(escala: number, unidade: Unidade = "m"): number {
  return (escala * MM_POR_UNIDADE[unidade]) / PT_PARA_MM;
}

// --- o gesto ----------------------------------------------------------------

export type Calibragem = {
  pontos: Array<[number, number]>;
  ativa: boolean;
};

export function iniciarCalibragem(): Calibragem {
  return { pontos: [], ativa: true };
}

/** Guarda o ponto em coordenadas de papel — nunca de tela, que muda com o zoom. */
export function marcarPonto(c: Calibragem, v: Vista,
                            telaX: number, telaY: number): Calibragem {
  if (!c.ativa || c.pontos.length >= 2) return c;
  const p = pontoDoPapel(v, telaX, telaY);
  const pontos: Array<[number, number]> = [...c.pontos, [p.x, p.y]];
  return { pontos, ativa: pontos.length < 2 };
}

const FOLGA_DA_LUPA = 24;

/**
 * Onde desenhar a lupa, dado onde está o dedo.
 *
 * No toque o dedo cobre exatamente o que precisa ser mirado — a extremidade de
 * uma cota — e sem a lupa ninguém acerta. Ela fica ao lado do dedo, e vira para
 * o outro lado quando esbarraria na borda.
 */
export function posicaoDaLupa(telaX: number, telaY: number,
                              larguraTela: number, alturaTela: number,
                              lado: number): { x: number; y: number } {
  let x = telaX + FOLGA_DA_LUPA;
  let y = telaY - lado - FOLGA_DA_LUPA;
  if (x + lado > larguraTela) x = telaX - lado - FOLGA_DA_LUPA;
  if (y < 0) y = telaY + FOLGA_DA_LUPA;
  x = Math.max(0, Math.min(x, larguraTela - lado));
  y = Math.max(0, Math.min(y, alturaTela - lado));
  return { x, y };
}
