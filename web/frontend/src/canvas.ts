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

/**
 * A vista, e o eixo Y invertido embutido nela.
 *
 * O extractor entrega coordenadas em papel com **Y para cima**, que é o padrão
 * de CAD; o canvas tem Y para baixo. Por isso a conversão é
 * `telaY = dy - papelY * escala`, e não uma soma: sem a inversão a prévia sai
 * de cabeça para baixo. O `dy` já carrega a altura da folha, então a `Vista`
 * continua sendo três números e o `aplicarZoom` continua valendo sem mudança.
 *
 * É o mesmo que a prévia do app desktop faz com `(H - p[1])`.
 */
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
    // A borda de baixo do papel, em pixels de tela: metade da sobra mais a
    // folha inteira. Daí `telaY = dy - papelY * escala` põe o pé da folha
    // embaixo e o topo em cima.
    dy: (alturaTela + alturaPt * escala) / 2,
  };
}

export function pontoDaTela(v: Vista, x: number, y: number) {
  return { x: x * v.escala + v.dx, y: v.dy - y * v.escala };
}

export function pontoDoPapel(v: Vista, x: number, y: number) {
  return { x: (x - v.dx) / v.escala, y: (v.dy - y) / v.escala };
}

/**
 * O retângulo de papel que a tela mostra, alargado por `folga` telas de cada
 * lado. `folga = 0.25` dá duas vezes a largura visível — é a janela da lista.
 *
 * O `min`/`max` no eixo Y não é zelo: com o eixo invertido, o topo da tela
 * corresponde ao **maior** Y de papel, e um retângulo com `y0 > y1` não casaria
 * com nenhuma entidade.
 */
export function janelaVisivel(v: Vista, larguraTela: number, alturaTela: number,
                              folga: number): Retangulo {
  const a = pontoDoPapel(v, 0, 0);
  const b = pontoDoPapel(v, larguraTela, alturaTela);
  const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x);
  const y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
  const margemX = (x1 - x0) * folga;
  const margemY = (y1 - y0) * folga;
  return {
    x0: x0 - margemX, y0: y0 - margemY,
    x1: x1 + margemX, y1: y1 + margemY,
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
                     dy - coords[inicio + 1]! * escala);
      caminho.lineTo(coords[inicio + 2]! * escala + dx,
                     dy - coords[inicio + 3]! * escala);
    } else if (tipo === POLILINHA) {
      // coords[inicio] é o "fechada"; os pontos começam em inicio+1.
      caminho.moveTo(coords[inicio + 1]! * escala + dx,
                     dy - coords[inicio + 2]! * escala);
      for (let p = inicio + 3; p + 1 < fim; p += 2) {
        caminho.lineTo(coords[p]! * escala + dx, dy - coords[p + 1]! * escala);
      }
      if (coords[inicio]! !== 0) caminho.closePath();
    } else if (tipo === ARCO) {
      tracarArco(caminho, coords, inicio, escala, dx, dy);
    } else if (tipo === BEZIER) {
      caminho.moveTo(coords[inicio]! * escala + dx,
                     dy - coords[inicio + 1]! * escala);
      caminho.bezierCurveTo(
        coords[inicio + 2]! * escala + dx, dy - coords[inicio + 3]! * escala,
        coords[inicio + 4]! * escala + dx, dy - coords[inicio + 5]! * escala,
        coords[inicio + 6]! * escala + dx, dy - coords[inicio + 7]! * escala);
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
    // O papel gira anti-horário com Y para cima; a tela, horário com Y para
    // baixo. Trocar o sinal é o que mantém o texto na mesma inclinação.
    ctx.rotate((-c[3]! * Math.PI) / 180);
    ctx.fillStyle = corDeInteiro(g.cor[i]!);
    ctx.font = `${c[2]! * v.escala}px sans-serif`;
    ctx.fillText(textoDe(g, i), 0, 0);
    ctx.restore();
  }

  return tracadas;
}

/**
 * O arco, tesselado em segmentos de reta — como faz a prévia do app desktop.
 *
 * **Não** se usa `Path2D.arc()`, e a razão é concreta: `arc()` liga o ponto
 * atual ao início do arco com uma reta. Como os caminhos aqui são agrupados por
 * (layer, cor), cada arco ficava amarrado ao fim da entidade anterior, e a
 * planta aparecia coberta de linhas atravessando de um canto a outro — que
 * mudavam de lugar a cada zoom, porque a lista de desenho muda.
 *
 * O `% 360 || 360` vem do desktop e resolve dois casos de uma vez: o arco que
 * cruza o zero e o círculo completo, em que início e fim coincidem e a conta
 * ingênua daria varredura zero.
 */
function tracarArco(caminho: CaminhoDesenhavel, coords: Float32Array,
                    inicio: number, escala: number, dx: number,
                    dy: number): void {
  const cx = coords[inicio]!, cy = coords[inicio + 1]!, r = coords[inicio + 2]!;
  const a0 = coords[inicio + 3]!, a1 = coords[inicio + 4]!;
  const varredura = ((a1 - a0) % 360 + 360) % 360 || 360;
  const passos = Math.max(4, Math.min(64, Math.trunc(varredura / 6)));
  for (let i = 0; i <= passos; i++) {
    const a = ((a0 + (varredura * i) / passos) * Math.PI) / 180;
    const x = (cx + r * Math.cos(a)) * escala + dx;
    const y = dy - (cy + r * Math.sin(a)) * escala;
    if (i === 0) caminho.moveTo(x, y); else caminho.lineTo(x, y);
  }
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
