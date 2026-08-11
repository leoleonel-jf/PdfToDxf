/**
 * Espelho TypeScript de `optimize.estimate_bytes()`.
 *
 * O único número aproximado da tela. A aproximação está no ramo de "unir em
 * polilinhas": quanto os segmentos se encadeiam depende de quais sobreviveram
 * aos filtros, e medir isso de verdade exigiria fazer a junção. O Python aceita
 * estatísticas de uma junção real quando as tem; o navegador nunca tem, então
 * aqui existe só o ramo aproximado — e é esse que o contrato congela.
 */
import { SEGMENTO, type Atributos, type Opcoes } from "./select.js";

const BYTES_SEGMENTO = 210;
const POLI_BASE = 180;
const POLI_POR_PONTO = 42;
const FATOR_ARREDONDAR = 0.78;
const CABECALHO = 60_000;
const FRACAO_ENCADEADA = 0.85;
const SEGMENTOS_POR_CADEIA = 12;

export function estimarBytes(attrs: Atributos, mascara: Uint8Array,
                             opts: Opcoes): number {
  let total = 0;
  let nSeg = 0;
  for (let i = 0; i < mascara.length; i++) {
    if (!mascara[i]) continue;
    if (attrs.kind[i] === SEGMENTO) nSeg += 1;
    else total += attrs.byte_cost[i]!;
  }

  if (opts.join_polylines && nSeg) {
    // `Math.trunc`, não `Math.round`: o Python usa `int()`, que trunca.
    const encadeados = Math.trunc(nSeg * FRACAO_ENCADEADA);
    const sozinhos = nSeg - encadeados;
    const nPoli = Math.max(1, Math.floor(encadeados / SEGMENTOS_POR_CADEIA));
    total += nPoli * POLI_BASE + (encadeados + nPoli) * POLI_POR_PONTO;
    total += sozinhos * BYTES_SEGMENTO;
  } else {
    total += nSeg * BYTES_SEGMENTO;
  }

  total += CABECALHO;
  if (opts.round_coords) total = Math.trunc(total * FATOR_ARREDONDAR);
  return total;
}
