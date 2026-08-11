/**
 * A matemática dos gestos, separada de quem escuta os eventos.
 *
 * Tudo aqui é função pura sobre a `Vista`: dá para provar que o zoom mantém o
 * ponto sob o dedo parado sem abrir navegador. O que fica para a conferência
 * manual é o tato — se o gesto *parece* certo —, não a aritmética.
 */
import type { Vista } from "./canvas.js";

const PASSO_DA_RODA = 1.0015;

/**
 * Quanto tempo sem evento conta como "o gesto parou".
 *
 * Existe porque preparar a lista custa da ordem de meio segundo, e fazer isso
 * durante um arrasto ou uma pinça engasgaria o gesto. Enquanto o dedo se mexe a
 * tela desenha a lista que tem; a preparação espera a mão parar.
 */
export const PAUSA_DO_GESTO_MS = 120;

export function fatorDaRoda(deltaY: number): number {
  // Exponencial, não linear: assim dois passos seguidos multiplicam o zoom, e
  // um passo para cada lado volta exatamente ao ponto de partida.
  return Math.pow(PASSO_DA_RODA, -deltaY);
}

/**
 * Aplica zoom mantendo fixo o ponto de papel que está sob (telaX, telaY).
 *
 * Sem isso o desenho foge do cursor e a navegação vira perseguição.
 */
export function aplicarZoom(v: Vista, fator: number,
                            telaX: number, telaY: number): Vista {
  const escala = v.escala * fator;
  return {
    escala,
    dx: telaX - (telaX - v.dx) * fator,
    dy: telaY + (v.dy - telaY) * fator,
  };
}

export function aplicarArrasto(v: Vista, dx: number, dy: number): Vista {
  return { escala: v.escala, dx: v.dx + dx, dy: v.dy + dy };
}

export function distancia(a: { x: number; y: number },
                          b: { x: number; y: number }): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

export function centro(a: { x: number; y: number }, b: { x: number; y: number }) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}
