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
  // A união vem do DOM: `CanvasRenderingContext2D.strokeStyle` aceita gradiente
  // e padrão além de texto. Declarar só `string` aqui faria o contexto de
  // verdade não caber nesta interface, e só o de mentira caberia — que é
  // exatamente o contrário do que ela serve para provar.
  strokeStyle: string | CanvasGradient | CanvasPattern;
  fillStyle: string | CanvasGradient | CanvasPattern;
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
  const textos: number[] = [];
  let tracadas = 0;

  // O laço quente não aloca nada: nem `subarray` para as coordenadas, nem
  // objeto `{x, y}` por ponto. Alocar três vezes por entidade custou 4x o
  // tempo do quadro quando foi medido — ver medicao/RESULTADO.md. Por isso ele
  // trabalha com deslocamentos crus dentro de `g.coords`.
  const coords = g.coords;
  const escala = v.escala, dx = v.dx, dy = v.dy;

  for (let k = 0; k < quantos; k++) {
    const i = lote[k]!;
    const inicio = g.coord_off[i]!;
    const fim = g.coord_off[i + 1]!;
    const tipo = g.kind[i]!;
    if (foraDos(limites, tipo, coords, inicio, fim)) continue;

    if (tipo === TEXTO) {
      textos.push(i);
      tracadas++;
      continue;
    }

    const chave = chaveDe(g, i);
    let grupo = porChave.get(chave);
    if (!grupo) {
      grupo = { caminho: criarCaminho(), cor: g.cor[i]! };
      porChave.set(chave, grupo);
    }
    const caminho = grupo.caminho;

    if (tipo === SEGMENTO) {
      caminho.moveTo(coords[inicio]! * escala + dx,
                     coords[inicio + 1]! * escala + dy);
      caminho.lineTo(coords[inicio + 2]! * escala + dx,
                     coords[inicio + 3]! * escala + dy);
    } else if (tipo === POLILINHA) {
      // coords[inicio] é o "fechada"; os pontos começam em inicio+1.
      caminho.moveTo(coords[inicio + 1]! * escala + dx,
                     coords[inicio + 2]! * escala + dy);
      for (let p = inicio + 3; p + 1 < fim; p += 2) {
        caminho.lineTo(coords[p]! * escala + dx, coords[p + 1]! * escala + dy);
      }
      if (coords[inicio]! !== 0) caminho.closePath();
    } else if (tipo === ARCO) {
      // Os ângulos do DXF são anti-horários com Y para cima; o canvas é horário
      // com Y para baixo. Trocar o sinal converte os dois de uma vez.
      caminho.arc(coords[inicio]! * escala + dx, coords[inicio + 1]! * escala + dy,
                  coords[inicio + 2]! * escala,
                  (-coords[inicio + 3]! * Math.PI) / 180,
                  (-coords[inicio + 4]! * Math.PI) / 180);
    } else if (tipo === BEZIER) {
      caminho.moveTo(coords[inicio]! * escala + dx,
                     coords[inicio + 1]! * escala + dy);
      caminho.bezierCurveTo(
        coords[inicio + 2]! * escala + dx, coords[inicio + 3]! * escala + dy,
        coords[inicio + 4]! * escala + dx, coords[inicio + 5]! * escala + dy,
        coords[inicio + 6]! * escala + dx, coords[inicio + 7]! * escala + dy);
    }
    tracadas++;
  }

  ctx.lineWidth = 1;
  for (const grupo of porChave.values()) {
    ctx.strokeStyle = corDeInteiro(grupo.cor);
    ctx.stroke(grupo.caminho);
  }

  // Fora do laço quente: textos são poucos, e aqui a clareza vale mais.
  for (const i of textos) {
    const c = coordenadasDe(g, i);
    const p = pontoDaTela(v, c[0]!, c[1]!);
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate((-c[3]! * Math.PI) / 180);
    ctx.fillStyle = corDeInteiro(g.cor[i]!);
    ctx.font = `${c[2]! * v.escala}px sans-serif`;
    ctx.fillText(textoDe(g, i), 0, 0);
    ctx.restore();
  }

  return tracadas;
}

/**
 * Caixa da entidade contra os limites, em coordenadas de papel.
 *
 * Recebe deslocamentos em vez de um `Float32Array` fatiado: é chamada uma vez
 * por entidade do lote, e um `subarray` por chamada é lixo que o coletor paga
 * no meio do quadro.
 */
function foraDos(limites: Retangulo, tipo: number, coords: Float32Array,
                 inicio: number, fim: number): boolean {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  if (tipo === ARCO) {
    // Caixa do círculo inteiro: mais folgada que o arco real, e barata. Errar
    // para o lado de desenhar demais só custa tempo; para o outro, some traço.
    const r = coords[inicio + 2]!;
    minx = coords[inicio]! - r; maxx = coords[inicio]! + r;
    miny = coords[inicio + 1]! - r; maxy = coords[inicio + 1]! + r;
  } else if (tipo === TEXTO) {
    minx = coords[inicio]!; maxx = minx + coords[inicio + 4]!;
    miny = coords[inicio + 1]!; maxy = miny + coords[inicio + 2]!;
  } else {
    const primeiro = tipo === POLILINHA ? inicio + 1 : inicio;
    for (let p = primeiro; p + 1 < fim; p += 2) {
      const x = coords[p]!, y = coords[p + 1]!;
      if (x < minx) minx = x;
      if (x > maxx) maxx = x;
      if (y < miny) miny = y;
      if (y > maxy) maxy = y;
    }
  }
  return maxx < limites.x0 || minx > limites.x1 ||
         maxy < limites.y0 || miny > limites.y1;
}
