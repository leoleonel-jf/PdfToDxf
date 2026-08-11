/**
 * O `lista.ts` de verdade, sobre 3 milhões de entidades.
 *
 * O protótipo do `indice.ts` mediu um esboço; este mede o que vai rodar. É o
 * passo que confirma ou derruba o par (lado da região, teto) que o spec fixou.
 */
export {};

import { enquadrar, janelaVisivel, desenharLote } from "../src/canvas.js";
import { ordenarPorComprimento } from "../src/ordem.js";
import { prepararTudo, FOLGA_DA_JANELA, UM_POR_PONTO } from "../src/lista.js";
import type { Geometria } from "../src/formato.js";

const N = 3_000_000;
const LARGURA_PAPEL = 595, ALTURA_PAPEL = 842;

const tela = document.querySelector<HTMLCanvasElement>("#tela")!;
const ctx = tela.getContext("2d")!;
const linhas: string[] = [];
const mostrar = () => {
  document.querySelector("#saida")!.textContent = linhas.join("\n");
};

let semente = 123456789;
const sorteio = () => {
  semente = (semente * 1664525 + 1013904223) >>> 0;
  return semente / 4294967296;
};

/** Mesma distribuição log-uniforme da terceira medição, para comparar. */
function gerar(): Geometria {
  const coords = new Float32Array(N * 4);
  const coord_off = new Uint32Array(N + 1);
  const length_um = new Uint32Array(N);
  const layer_id = new Uint32Array(N);
  const lnMin = Math.log(0.05), lnMax = Math.log(100);
  for (let i = 0; i < N; i++) {
    const comprimento = Math.exp(lnMin + sorteio() * (lnMax - lnMin));
    const angulo = sorteio() * Math.PI * 2;
    const x = sorteio() * LARGURA_PAPEL, y = sorteio() * ALTURA_PAPEL;
    coords.set([x, y, x + Math.cos(angulo) * comprimento,
                y + Math.sin(angulo) * comprimento], i * 4);
    coord_off[i + 1] = (i + 1) * 4;
    length_um[i] = Math.round(comprimento * UM_POR_PONTO);
    layer_id[i] = i % 8;
  }
  return {
    n: N, layers: ["0"], n_groups: N,
    idx: Uint32Array.from({ length: N }, (_, i) => i),
    kind: new Uint8Array(N), layer_id, is_fill: new Uint8Array(N),
    length_um,
    dup_group: Int32Array.from({ length: N }, (_, i) => i),
    byte_cost: new Uint32Array(N),
    cor: new Uint32Array(N).fill(0xffffffff),
    coord_off, coords,
    texto_off: new Uint32Array(N + 1), texto: new Uint8Array(0),
  };
}

/**
 * Reporta o **mínimo**, não a faixa.
 *
 * Sob carga o ruído só soma tempo: uma fatia roubada pelo escalonador, uma
 * coleta de lixo, outro processo no núcleo. Nada disso deixa o trabalho mais
 * rápido. Então o mínimo de muitas passagens é a estimativa honesta do custo
 * real, e é o único número que sobrevive a uma máquina ocupada. A mediana vai
 * junto para se ver o tamanho do ruído.
 */
function cronometrar<T>(nome: string, vezes: number, f: () => T): T {
  const gastos: number[] = [];
  let r: T = undefined as T;
  for (let k = 0; k < vezes; k++) {
    const inicio = performance.now();
    r = f();
    gastos.push(performance.now() - inicio);
  }
  const ordenados = [...gastos].sort((a, b) => a - b);
  const minimo = ordenados[0]!;
  const mediana = ordenados[Math.floor(ordenados.length / 2)]!;
  linhas.push(`${nome}: min ${minimo.toFixed(0)} ms, mediana ${mediana.toFixed(0)} ms`);
  mostrar();
  return r;
}

const g = cronometrar("gerar 3M", 1, gerar);
const mascara = new Uint8Array(N).fill(1);
const ordem = cronometrar("ordenarPorComprimento", 2,
                          () => ordenarPorComprimento(g.length_um));

const AJUSTE = Math.min(tela.width / LARGURA_PAPEL, tela.height / ALTURA_PAPEL);

/**
 * A varredura acontece toda numa carga só, de propósito.
 *
 * A primeira tentativa comparou execuções diferentes e não prestou: a máquina
 * estava carregada e o `gerar 3M`, que não mudou uma linha, foi de 976 para
 * 2000 ms entre uma e outra. Dentro da mesma carga, todas as combinações pegam
 * a mesma máquina no mesmo estado, e a comparação vale mesmo sob carga. O
 * `gerar 3M` acima fica como controle: se ele destoar do registrado no
 * RESULTADO.md, os números absolutos desta rodada não valem — só as razões.
 */
const ZOOMS: [string, number][] = [
  ["folha", AJUSTE], ["4x", AJUSTE * 4], ["16x", AJUSTE * 16],
];
const COMBINACOES: [number, number, number][] = [
  // lado em pixels, teto por região, folga da janela
  [4, 4, FOLGA_DA_JANELA],
  [4, 2, FOLGA_DA_JANELA],
  [8, 2, FOLGA_DA_JANELA],
  [8, 2, 0.25],
  [8, 1, 0.25],
];

for (const [lado, teto, folga] of COMBINACOES) {
  linhas.push(`--- regiao de ${lado} px, teto ${teto}, folga ${folga} ---`);
  for (const [nome, escala] of ZOOMS) {
    const v = enquadrar(LARGURA_PAPEL, ALTURA_PAPEL, tela.width, tela.height);
    v.escala = escala;
    const janela = janelaVisivel(v, tela.width, tela.height, folga);
    const visivel = janelaVisivel(v, tela.width, tela.height, 0);

    const p = prepararTudo(g, mascara, ordem, janela, escala, lado, teto);
    cronometrar(`  ${nome} | quadro`, 15, () => {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, tela.width, tela.height);
      desenharLote(ctx, g, p.lista, p.quantos, v, () => new Path2D(), visivel);
      ctx.getImageData(0, 0, 1, 1);   // força a rasterização a terminar
    });
    linhas[linhas.length - 1] +=
      `   (lista de ${p.quantos.toLocaleString("pt-BR")})`;
    mostrar();
  }
}

linhas.push(`navegador: ${navigator.userAgent}`);
mostrar();
