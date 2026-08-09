/**
 * O modelo do indicador de progresso, e a formatação.
 *
 * Puro de propósito: é aqui que mora a única regra que importa — **nunca
 * inventar porcentagem**. Onde não há número real, o indicador é indeterminado,
 * e quem monta o DOM não tem como fingir o contrário.
 */

export type Progresso =
  | { tipo: "determinado"; feito: number; total: number }
  | { tipo: "indeterminado"; desde: number };

/** Fração de 0 a 1, presa nas pontas. `null` quando não há como saber. */
export function fracao(p: Progresso): number | null {
  if (p.tipo !== "determinado") return null;
  if (!(p.total > 0)) return null;
  return Math.min(1, Math.max(0, p.feito / p.total));
}

export function porcentagem(p: Progresso): number | null {
  const f = fracao(p);
  return f === null ? null : Math.round(f * 100);
}

/**
 * Tempo decorrido, curto e em português. Vazio abaixo de um segundo.
 *
 * Piscar "0 s" no instante em que a barra aparece é ruído — ninguém precisa
 * saber que se passaram trezentos milissegundos. E de dez minutos em diante os
 * segundos deixam de informar: quem espera dez minutos quer a ordem de
 * grandeza, não o relógio.
 */
export function tempoDecorrido(desde: number, agora: number): string {
  const s = Math.floor((agora - desde) / 1000);
  if (s < 1) return "";
  if (s < 60) return `${s} s`;
  const min = Math.floor(s / 60);
  const resto = s % 60;
  if (min >= 10 || resto === 0) return `${min} min`;
  return `${min} min ${resto} s`;
}
