/**
 * Quanto custa *traçar* — não montar — os caminhos, por quadro.
 *
 * A medição do `custo.ts` respondeu quanto custa montar os `Path2D`. Esta
 * responde a pergunta que o redesenho precisa e que ninguém mediu: se os
 * caminhos ficam montados e o pan/zoom só re-traça sob outra transformação,
 * quanto custa cada quadro? Se for caro, recortar por região visível deixa de
 * ser opcional e vira o eixo da arquitetura.
 */

// Ver a nota no `custo.ts`: sem isto os dois arquivos viram script global e as
// declarações de topo colidem.
export {};

const LARGURA_PAPEL = 595;   // A4 em pontos, como o extractor entrega
const ALTURA_PAPEL = 842;
const GRUPOS = 8;            // (layer, cor) distintos, como no custo.ts

const tela = document.querySelector<HTMLCanvasElement>("#tela")!;
const ctx = tela.getContext("2d")!;

function gerar(n: number) {
  const coords = new Float32Array(n * 4);
  const layerId = new Uint32Array(n);
  // Segmentos curtos espalhados pela folha inteira, que é como uma planta é:
  // muita linha pequena, não poucas linhas grandes.
  for (let i = 0; i < n; i++) {
    const x = (i * 7919) % LARGURA_PAPEL;
    const y = (i * 6271) % ALTURA_PAPEL;
    coords[i * 4] = x;
    coords[i * 4 + 1] = y;
    coords[i * 4 + 2] = x + 1.5;
    coords[i * 4 + 3] = y + 0.8;
    layerId[i] = i % GRUPOS;
  }
  return { coords, layerId, n };
}

function construir(d: ReturnType<typeof gerar>) {
  const porGrupo = new Map<number, Path2D>();
  for (let i = 0; i < d.n; i++) {
    const g = d.layerId[i]!;
    let caminho = porGrupo.get(g);
    if (!caminho) { caminho = new Path2D(); porGrupo.set(g, caminho); }
    caminho.moveTo(d.coords[i * 4]!, d.coords[i * 4 + 1]!);
    caminho.lineTo(d.coords[i * 4 + 2]!, d.coords[i * 4 + 3]!);
  }
  return porGrupo;
}

/**
 * Traça tudo uma vez e **força a rasterização a terminar** antes de parar o
 * cronômetro. Sem o `getImageData`, o Chrome devolve de `stroke()` antes de
 * pintar e a medição sairia otimista por uma ordem de grandeza.
 */
function tracar(caminhos: Map<number, Path2D>, escala: number, dx: number) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, tela.width, tela.height);
  ctx.setTransform(escala, 0, 0, escala, dx, 0);
  ctx.lineWidth = 1 / escala;
  ctx.strokeStyle = "#000";
  for (const caminho of caminhos.values()) ctx.stroke(caminho);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.getImageData(0, 0, 1, 1);
}

const linhas: string[] = [];
function mostrar() {
  document.querySelector("#saida")!.textContent = linhas.join("\n");
}

function cronometrar(nome: string, quantos: number, f: (k: number) => void) {
  const gastos: number[] = [];
  for (let k = 0; k < quantos; k++) {
    const inicio = performance.now();
    f(k);
    gastos.push(performance.now() - inicio);
  }
  linhas.push(`${nome}: ${gastos.map((g) => g.toFixed(0)).join(" / ")} ms`);
  mostrar();
}

for (const n of [500_000, 3_000_000]) {
  const rotulo = n >= 1_000_000 ? `${n / 1_000_000}M` : `${n / 1000} mil`;
  const dados = gerar(n);
  const caminhos = construir(dados);

  // Quadro isolado: o custo de mostrar a planta parada.
  cronometrar(`tracar ${rotulo}, quadro isolado`, 3,
              () => tracar(caminhos, 1.35, 0));

  // Cinco quadros seguidos com a transformação mudando: é o que um arrasto de
  // pan faz. Se cada quadro custar mais que 16 ms, o arrasto engasga.
  cronometrar(`tracar ${rotulo}, pan de 5 quadros`, 5,
              (k) => tracar(caminhos, 1.35, -k * 40));

  // Zoom de 4x: menos coisa cabe na tela, mas o traçado continua percorrendo
  // tudo. Mede quanto o recorte por regiao visivel teria a ganhar.
  cronometrar(`tracar ${rotulo}, zoom 4x`, 3,
              () => tracar(caminhos, 5.4, -600));
}

linhas.push(`navegador: ${navigator.userAgent}`);
mostrar();
