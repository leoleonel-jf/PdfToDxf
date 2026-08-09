/**
 * A vista — a conversão entre papel e tela — e o traçado de um lote pronto.
 *
 * Este arquivo não conhece lista, orçamento nem gesto. Ele recebe um lote de
 * índices e uma vista, e traça. É essa fronteira que permite provar, sem
 * navegador, que o desenhado corresponde ao escolhido.
 */
import { SEGMENTO } from "./select.js";
import { coordenadasDe, textoDe, SEM_COR, type Geometria } from "./formato.js";

const POLILINHA = 1, ARCO = 2, BEZIER = 3, TEXTO = 4;

export type Vista = { escala: number; dx: number; dy: number };
export type Retangulo = { x0: number; y0: number; x1: number; y1: number };

export interface CaminhoDesenhavel {
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  arc(cx: number, cy: number, r: number, a0: number, a1: number): void;
  bezierCurveTo(x1: number, y1: number, x2: number, y2: number,
                x3: number, y3: number): void;
  closePath(): void;
}

export interface ContextoDesenhavel {
  save(): void;
  restore(): void;
  translate(x: number, y: number): void;
  rotate(a: number): void;
  clearRect(x: number, y: number, w: number, h: number): void;
  fillRect(x: number, y: number, w: number, h: number): void;
  fillText(t: string, x: number, y: number): void;
  stroke(c: CaminhoDesenhavel): void;
  lineWidth: number;
  strokeStyle: string;
  fillStyle: string;
  font: string;
}

export function enquadrar(larguraPt: number, alturaPt: number,
                          larguraTela: number, alturaTela: number): Vista {
  const escala = Math.min(larguraTela / larguraPt, alturaTela / alturaPt);
  return {
    escala,
    dx: (larguraTela - larguraPt * escala) / 2,
    dy: (alturaTela - alturaPt * escala) / 2,
  };
}

export function pontoDaTela(v: Vista, x: number, y: number) {
  return { x: x * v.escala + v.dx, y: y * v.escala + v.dy };
}

export function pontoDoPapel(v: Vista, x: number, y: number) {
  return { x: (x - v.dx) / v.escala, y: (y - v.dy) / v.escala };
}

/**
 * O retângulo de papel que a tela mostra, alargado por `folga` telas de cada
 * lado. `folga = 0.5` dá quatro vezes a área visível — é a janela da lista.
 */
export function janelaVisivel(v: Vista, larguraTela: number, alturaTela: number,
                              folga: number): Retangulo {
  const a = pontoDoPapel(v, 0, 0);
  const b = pontoDoPapel(v, larguraTela, alturaTela);
  const margemX = (b.x - a.x) * folga;
  const margemY = (b.y - a.y) * folga;
  return {
    x0: a.x - margemX, y0: a.y - margemY,
    x1: b.x + margemX, y1: b.y + margemY,
  };
}

export function corDeInteiro(cor: number): string {
  if (cor === SEM_COR) return "#111";
  return "#" + (cor & 0xffffff).toString(16).padStart(6, "0");
}

/** Chave de agrupamento: mesmo layer e mesma cor vão no mesmo caminho. */
function chaveDe(g: Geometria, i: number): number {
  // `cor` cabe em 24 bits úteis; o layer entra acima dela. Multiplicar em vez
  // de deslocar porque `<<` em JavaScript trabalha em 32 bits com sinal, e o
  // layer estouraria isso numa planta com muitos layers.
  return g.layer_id[i]! * 0x1000000 + (g.cor[i]! & 0xffffff);
}

/**
 * Traça as `quantos` primeiras entidades de `lote`, descartando o que cai fora
 * de `limites`. Devolve quantas traçou de fato.
 *
 * O `quantos` existe para o pintor poder desenhar meio lote num quadro e o
 * resto no seguinte, sem fatiar o array.
 */
export function desenharLote(ctx: ContextoDesenhavel, g: Geometria,
                             lote: Uint32Array, quantos: number, v: Vista,
                             criarCaminho: () => CaminhoDesenhavel,
                             limites: Retangulo): number {
  const porChave = new Map<number, { caminho: CaminhoDesenhavel; cor: number }>();
  const textos: Array<{ i: number; c: Float32Array }> = [];
  let tracadas = 0;

  for (let k = 0; k < quantos; k++) {
    const i = lote[k]!;
    const c = coordenadasDe(g, i);
    if (foraDos(limites, g, i, c)) continue;

    const tipo = g.kind[i]!;
    if (tipo === TEXTO) {
      textos.push({ i, c });
      tracadas++;
      continue;
    }

    const chave = chaveDe(g, i);
    let grupo = porChave.get(chave);
    if (!grupo) {
      grupo = { caminho: criarCaminho(), cor: g.cor[i]! };
      porChave.set(chave, grupo);
    }
    tracarNoCaminho(grupo.caminho, tipo, c, v);
    tracadas++;
  }

  ctx.lineWidth = 1;
  for (const grupo of porChave.values()) {
    ctx.strokeStyle = corDeInteiro(grupo.cor);
    ctx.stroke(grupo.caminho);
  }

  for (const { i, c } of textos) {
    const p = pontoDaTela(v, c[0]!, c[1]!);
    const altura = c[2]! * v.escala;
    ctx.save();
    ctx.translate(p.x, p.y);
    // O papel tem Y para cima e a tela para baixo, então o giro inverte.
    ctx.rotate((-c[3]! * Math.PI) / 180);
    ctx.fillStyle = corDeInteiro(g.cor[i]!);
    ctx.font = `${altura}px sans-serif`;
    ctx.fillText(textoDe(g, i), 0, 0);
    ctx.restore();
  }

  return tracadas;
}

/** Caixa da entidade contra os limites, em coordenadas de papel. */
function foraDos(limites: Retangulo, g: Geometria, i: number,
                 c: Float32Array): boolean {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  const tipo = g.kind[i]!;
  if (tipo === ARCO) {
    // Caixa do círculo inteiro: mais folgada que o arco real, e barata. Errar
    // para o lado de desenhar demais só custa tempo; para o outro, some traço.
    const r = c[2]!;
    minx = c[0]! - r; maxx = c[0]! + r;
    miny = c[1]! - r; maxy = c[1]! + r;
  } else if (tipo === TEXTO) {
    minx = c[0]!; maxx = c[0]! + c[4]!;
    miny = c[1]!; maxy = c[1]! + c[2]!;
  } else {
    const inicio = tipo === POLILINHA ? 1 : 0;
    for (let p = inicio; p + 1 < c.length; p += 2) {
      const x = c[p]!, y = c[p + 1]!;
      if (x < minx) minx = x;
      if (x > maxx) maxx = x;
      if (y < miny) miny = y;
      if (y > maxy) maxy = y;
    }
  }
  return maxx < limites.x0 || minx > limites.x1 ||
         maxy < limites.y0 || miny > limites.y1;
}

function tracarNoCaminho(caminho: CaminhoDesenhavel, tipo: number,
                         c: Float32Array, v: Vista): void {
  if (tipo === SEGMENTO) {
    const a = pontoDaTela(v, c[0]!, c[1]!);
    const b = pontoDaTela(v, c[2]!, c[3]!);
    caminho.moveTo(a.x, a.y);
    caminho.lineTo(b.x, b.y);
    return;
  }
  if (tipo === POLILINHA) {
    // c[0] é o "fechada"; os pontos começam em c[1].
    const primeiro = pontoDaTela(v, c[1]!, c[2]!);
    caminho.moveTo(primeiro.x, primeiro.y);
    for (let p = 3; p + 1 < c.length; p += 2) {
      const q = pontoDaTela(v, c[p]!, c[p + 1]!);
      caminho.lineTo(q.x, q.y);
    }
    if (c[0]! !== 0) caminho.closePath();
    return;
  }
  if (tipo === ARCO) {
    const centro = pontoDaTela(v, c[0]!, c[1]!);
    // Os ângulos do DXF são anti-horários com Y para cima; o canvas é horário
    // com Y para baixo. Trocar o sinal converte os dois de uma vez.
    caminho.arc(centro.x, centro.y, c[2]! * v.escala,
                (-c[3]! * Math.PI) / 180, (-c[4]! * Math.PI) / 180);
    return;
  }
  if (tipo === BEZIER) {
    const p0 = pontoDaTela(v, c[0]!, c[1]!);
    const p1 = pontoDaTela(v, c[2]!, c[3]!);
    const p2 = pontoDaTela(v, c[4]!, c[5]!);
    const p3 = pontoDaTela(v, c[6]!, c[7]!);
    caminho.moveTo(p0.x, p0.y);
    caminho.bezierCurveTo(p1.x, p1.y, p2.x, p2.y, p3.x, p3.y);
  }
}
