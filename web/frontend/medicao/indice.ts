/**
 * O índice do redesenho, prototipado para medir antes de virar desenho.
 *
 * Três perguntas, nesta ordem:
 *  1. Quanto custa montar o índice sobre 3 milhões de entidades?
 *  2. Quanto custa um quadro recortando por região visível?
 *  3. O limiar de um pixel basta com a folha inteira à vista, ou é preciso um
 *     teto de traços por região de tela?
 *
 * A terceira é a que a análise põe em dúvida: se a maioria dos segmentos é
 * maior que um pixel, o limiar não corta nada e o que sobra é excesso de traço
 * por pixel.
 */
export {};

const N = 3_000_000;
const LARGURA_PAPEL = 595;      // A4 em pontos
const ALTURA_PAPEL = 842;
const UM_POR_PONTO = 25.4 / 72 * 1000;   // 1 pt = 352,78 µm
const GRUPOS = 8;

const tela = document.querySelector<HTMLCanvasElement>("#tela")!;
const ctx = tela.getContext("2d")!;

const linhas: string[] = [];
function mostrar() {
  document.querySelector("#saida")!.textContent = linhas.join("\n");
}
function cronometrar<T>(nome: string, quantos: number, f: () => T): T {
  const gastos: number[] = [];
  let r: T = undefined as T;
  for (let k = 0; k < quantos; k++) {
    const inicio = performance.now();
    r = f();
    gastos.push(performance.now() - inicio);
  }
  linhas.push(`${nome}: ${gastos.map((g) => g.toFixed(0)).join(" / ")} ms`);
  mostrar();
  return r;
}

/** Gerador determinístico: repetir a medição tem de dar o mesmo desenho. */
let semente = 123456789;
function aleatorio(): number {
  semente = (semente * 1664525 + 1013904223) >>> 0;
  return semente / 4294967296;
}

/**
 * Comprimentos log-uniformes de 0,05 a 100 pt.
 *
 * É a forma de uma planta de CAD: muita linha curta — hachura, tracinho de
 * cota — e poucas linhas longas. Uniforme daria uma planta que não existe e a
 * medição responderia à pergunta errada.
 */
function gerar() {
  const x1 = new Float32Array(N), y1 = new Float32Array(N);
  const x2 = new Float32Array(N), y2 = new Float32Array(N);
  const lengthUm = new Uint32Array(N);
  const layerId = new Uint8Array(N);
  const lnMin = Math.log(0.05), lnMax = Math.log(100);
  for (let i = 0; i < N; i++) {
    const comprimento = Math.exp(lnMin + aleatorio() * (lnMax - lnMin));
    const angulo = aleatorio() * Math.PI * 2;
    const x = aleatorio() * LARGURA_PAPEL;
    const y = aleatorio() * ALTURA_PAPEL;
    x1[i] = x; y1[i] = y;
    x2[i] = x + Math.cos(angulo) * comprimento;
    y2[i] = y + Math.sin(angulo) * comprimento;
    lengthUm[i] = Math.round(comprimento * UM_POR_PONTO);
    layerId[i] = i % GRUPOS;
  }
  return { x1, y1, x2, y2, lengthUm, layerId };
}

type Dados = ReturnType<typeof gerar>;

/**
 * Ordem global por comprimento decrescente, por radix de 16 bits em duas
 * passadas. `sort` com comparador chamaria uma função por comparação — dezenas
 * de milhões de chamadas em 3 milhões de itens.
 */
function ordenarPorComprimento(lengthUm: Uint32Array): Uint32Array {
  let atual = new Uint32Array(N);
  for (let i = 0; i < N; i++) atual[i] = i;
  let outro = new Uint32Array(N);
  const contagem = new Uint32Array(65536);
  for (let passada = 0; passada < 2; passada++) {
    const deslocamento = passada * 16;
    contagem.fill(0);
    for (let i = 0; i < N; i++) {
      contagem[(lengthUm[atual[i]!]! >>> deslocamento) & 0xffff]!++;
    }
    let soma = 0;
    for (let b = 0; b < 65536; b++) {
      const c = contagem[b]!;
      contagem[b] = soma;
      soma += c;
    }
    for (let i = 0; i < N; i++) {
      const v = atual[i]!;
      outro[contagem[(lengthUm[v]! >>> deslocamento) & 0xffff]!++] = v;
    }
    const troca = atual; atual = outro; outro = troca;
  }
  // O radix sobe; o índice quer descer — o mais longo primeiro é o que o teto
  // por região de tela precisa para manter o traço que importa.
  const descendente = new Uint32Array(N);
  for (let i = 0; i < N; i++) descendente[i] = atual[N - 1 - i]!;
  return descendente;
}

const COLUNAS = 64, LINHAS = 64;
const LARGURA_CELULA = LARGURA_PAPEL / COLUNAS;
const ALTURA_CELULA = ALTURA_PAPEL / LINHAS;
const EXTENSAO_CELULA = Math.min(LARGURA_CELULA, ALTURA_CELULA);

/**
 * Grade com listas em ordem de comprimento decrescente.
 *
 * As pequenas entram pela célula do ponto médio, e a consulta alarga o
 * retângulo em uma célula para não perder quem cruza a borda — exato, e sem
 * duplicar entidade em várias células. As grandes ficam de fora, numa lista
 * percorrida sempre com teste de caixa: são poucas e são justamente as que se
 * quer ver com a folha inteira à vista.
 */
function construirIndice(d: Dados, ordem: Uint32Array) {
  const celulas = COLUNAS * LINHAS;
  const contagem = new Uint32Array(celulas + 1);
  const grandes: number[] = [];
  const celulaDe = new Int32Array(N);

  for (let k = 0; k < N; k++) {
    const i = ordem[k]!;
    const extensao = Math.max(Math.abs(d.x2[i]! - d.x1[i]!),
                              Math.abs(d.y2[i]! - d.y1[i]!));
    if (extensao > EXTENSAO_CELULA) { celulaDe[i] = -1; continue; }
    const mx = (d.x1[i]! + d.x2[i]!) * 0.5;
    const my = (d.y1[i]! + d.y2[i]!) * 0.5;
    let cx = (mx / LARGURA_CELULA) | 0, cy = (my / ALTURA_CELULA) | 0;
    if (cx < 0) cx = 0; else if (cx >= COLUNAS) cx = COLUNAS - 1;
    if (cy < 0) cy = 0; else if (cy >= LINHAS) cy = LINHAS - 1;
    const c = cy * COLUNAS + cx;
    celulaDe[i] = c;
    contagem[c + 1]!++;
  }
  for (let c = 0; c < celulas; c++) contagem[c + 1]! += contagem[c]!;
  const inicio = contagem;
  const cursor = Uint32Array.from(inicio);
  const itens = new Uint32Array(N - 0);
  let usados = 0;
  for (let k = 0; k < N; k++) {
    const i = ordem[k]!;
    const c = celulaDe[i]!;
    if (c < 0) { grandes.push(i); continue; }
    itens[cursor[c]!++] = i;
    usados++;
  }
  return { inicio, itens, usados, grandes: Uint32Array.from(grandes) };
}

type Indice = ReturnType<typeof construirIndice>;

const CAIXA = 4;   // lado, em pixels, da região de tela do teto de traços

/**
 * Um quadro. `tetoPorCaixa = 0` desliga o teto por região de tela.
 *
 * Devolve quantos segmentos foram efetivamente traçados: é o número que diz
 * qual mecanismo está segurando o custo.
 */
function quadro(d: Dados, idx: Indice, escala: number, panX: number,
                panY: number, limiarPx: number, tetoPorCaixa: number,
                ocupacao: Uint8Array): number {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, tela.width, tela.height);
  if (tetoPorCaixa) ocupacao.fill(0);
  const caixasPorLinha = Math.ceil(tela.width / CAIXA);

  // Retângulo visível em coordenadas de papel, alargado numa célula.
  const vx0 = -panX / escala - LARGURA_CELULA;
  const vy0 = -panY / escala - ALTURA_CELULA;
  const vx1 = (tela.width - panX) / escala + LARGURA_CELULA;
  const vy1 = (tela.height - panY) / escala + ALTURA_CELULA;
  const limiarUm = (limiarPx / escala) * UM_POR_PONTO;

  const caminhos: Path2D[] = [];
  for (let g = 0; g < GRUPOS; g++) caminhos.push(new Path2D());
  let tracados = 0;

  function talvezTracar(i: number): void {
    if (d.lengthUm[i]! < limiarUm) return;
    const ax = d.x1[i]! * escala + panX, ay = d.y1[i]! * escala + panY;
    if (tetoPorCaixa) {
      const bx = (ax / CAIXA) | 0, by = (ay / CAIXA) | 0;
      if (bx >= 0 && by >= 0 && ax < tela.width && ay < tela.height) {
        const b = by * caixasPorLinha + bx;
        if (ocupacao[b]! >= tetoPorCaixa) return;
        ocupacao[b]!++;
      }
    }
    const caminho = caminhos[d.layerId[i]!]!;
    caminho.moveTo(ax, ay);
    caminho.lineTo(d.x2[i]! * escala + panX, d.y2[i]! * escala + panY);
    tracados++;
  }

  // As grandes, com teste de caixa.
  for (let k = 0; k < idx.grandes.length; k++) {
    const i = idx.grandes[k]!;
    const minx = Math.min(d.x1[i]!, d.x2[i]!), maxx = Math.max(d.x1[i]!, d.x2[i]!);
    const miny = Math.min(d.y1[i]!, d.y2[i]!), maxy = Math.max(d.y1[i]!, d.y2[i]!);
    if (maxx < vx0 || minx > vx1 || maxy < vy0 || miny > vy1) continue;
    talvezTracar(i);
  }

  // As células que o retângulo toca. A lista de cada uma desce por comprimento,
  // então o primeiro item abaixo do limiar encerra a célula.
  let c0 = Math.max(0, (vx0 / LARGURA_CELULA) | 0);
  let c1 = Math.min(COLUNAS - 1, (vx1 / LARGURA_CELULA) | 0);
  let l0 = Math.max(0, (vy0 / ALTURA_CELULA) | 0);
  let l1 = Math.min(LINHAS - 1, (vy1 / ALTURA_CELULA) | 0);
  for (let cy = l0; cy <= l1; cy++) {
    for (let cx = c0; cx <= c1; cx++) {
      const c = cy * COLUNAS + cx;
      const fim = idx.inicio[c + 1]!;
      for (let p = idx.inicio[c]!; p < fim; p++) {
        const i = idx.itens[p]!;
        if (d.lengthUm[i]! < limiarUm) break;
        talvezTracar(i);
      }
    }
  }

  ctx.lineWidth = 1;
  ctx.strokeStyle = "#000";
  for (const caminho of caminhos) ctx.stroke(caminho);
  ctx.getImageData(0, 0, 1, 1);
  return tracados;
}

const dados = cronometrar("gerar 3M", 1, gerar);
const ordem = cronometrar("ordenar por comprimento (radix)", 2,
                          () => ordenarPorComprimento(dados.lengthUm));
const indice = cronometrar("montar a grade", 2,
                           () => construirIndice(dados, ordem));
linhas.push(`   nas celulas: ${indice.usados}, grandes: ${indice.grandes.length}`);
mostrar();

const ocupacao = new Uint8Array(Math.ceil(tela.width / CAIXA) *
                                Math.ceil(tela.height / CAIXA));

const ESCALA_FOLHA = Math.min(tela.width / LARGURA_PAPEL,
                              tela.height / ALTURA_PAPEL);

for (const [nome, escala, panX, panY] of [
  ["folha inteira", ESCALA_FOLHA, 0, 0],
  ["zoom 4x", ESCALA_FOLHA * 4, -600, -800],
  ["zoom 16x", ESCALA_FOLHA * 16, -3000, -4000],
] as [string, number, number, number][]) {
  for (const [rotulo, limiarPx, teto] of [
    ["sem limiar nem teto", 0, 0],
    ["limiar de 1 px", 1, 0],
    ["limiar + teto de 4 por caixa", 1, 4],
    ["limiar + teto de 2 por caixa", 1, 2],
  ] as [string, number, number][]) {
    let tracados = 0;
    cronometrar(`${nome} | ${rotulo}`, 3, () => {
      tracados = quadro(dados, indice, escala, panX, panY, limiarPx, teto,
                        ocupacao);
    });
    linhas[linhas.length - 1] += `   (${tracados.toLocaleString("pt-BR")} tracados)`;
    mostrar();
  }
}

/**
 * Experimento de controle: desenhar a MESMA lista, já pronta.
 *
 * Sem ele não dá para saber se o meio segundo por quadro é o traçado ou a
 * varredura das 3 milhões. Se esta medida for barata, a conclusão é que a
 * lista precisa ser preparada uma vez em vez de reconstruída por quadro.
 */
function coletar(escala: number, panX: number, panY: number,
                 limiarPx: number, teto: number): Uint32Array {
  const coletados: number[] = [];
  const ocup = new Uint8Array(ocupacao.length);
  const caixasPorLinha = Math.ceil(tela.width / CAIXA);
  const limiarUm = (limiarPx / escala) * UM_POR_PONTO;
  for (let i = 0; i < N; i++) {
    if (dados.lengthUm[i]! < limiarUm) continue;
    const ax = dados.x1[i]! * escala + panX, ay = dados.y1[i]! * escala + panY;
    if (ax < 0 || ay < 0 || ax >= tela.width || ay >= tela.height) continue;
    const b = ((ay / CAIXA) | 0) * caixasPorLinha + ((ax / CAIXA) | 0);
    if (ocup[b]! >= teto) continue;
    ocup[b]!++;
    coletados.push(i);
  }
  return Uint32Array.from(coletados);
}

function quadroDeLista(lista: Uint32Array, escala: number, panX: number,
                       panY: number): void {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, tela.width, tela.height);
  const caminhos: Path2D[] = [];
  for (let g = 0; g < GRUPOS; g++) caminhos.push(new Path2D());
  for (let k = 0; k < lista.length; k++) {
    const i = lista[k]!;
    const caminho = caminhos[dados.layerId[i]!]!;
    caminho.moveTo(dados.x1[i]! * escala + panX, dados.y1[i]! * escala + panY);
    caminho.lineTo(dados.x2[i]! * escala + panX, dados.y2[i]! * escala + panY);
  }
  ctx.lineWidth = 1;
  ctx.strokeStyle = "#000";
  for (const caminho of caminhos) ctx.stroke(caminho);
  ctx.getImageData(0, 0, 1, 1);
}

const lista = coletar(ESCALA_FOLHA, 0, 0, 1, 2);
linhas.push(`--- controle: a mesma lista, ja pronta (${lista.length} itens) ---`);
cronometrar("desenhar a lista pronta", 5,
            () => quadroDeLista(lista, ESCALA_FOLHA, 0, 0));
cronometrar("desenhar a lista pronta, pan de 5 quadros", 5,
            () => quadroDeLista(lista, ESCALA_FOLHA, -20, -20));

linhas.push(`navegador: ${navigator.userAgent}`);
mostrar();
