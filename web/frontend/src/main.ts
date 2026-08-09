/**
 * Composição da tela.
 *
 * Aqui moram o estado e o laço de quadro. Todo o resto é módulo com uma
 * responsabilidade só; este arquivo é o único que os conhece todos.
 *
 * **Não há Web Worker.** Foi medido: o `select()` sobre 3 milhões de entidades
 * custa ~12 ms e cabe num quadro, enquanto o desenho custa centenas de
 * milissegundos e usa `Path2D`, que não existe dentro de um worker. Um worker
 * moveria para fora os 12 ms e deixaria dentro os 800. Ver
 * `web/frontend/medicao/RESULTADO.md`.
 */
import {
  enviarPdf, esperarPagina, exportar, lerGeometriaBruta, lerMeta,
  pedirExtracao, type Meta,
} from "./api.js";
import { enquadrar, type Vista } from "./canvas.js";
import { intercalar, lerGeometria, type Geometria } from "./formato.js";
import {
  aplicarArrasto, aplicarZoom, centro, distancia, fatorDaRoda,
  PAUSA_DO_GESTO_MS,
} from "./gestos.js";
import { avisoDaSituacao, avisoDoErro, type Aviso } from "./estados.js";
import {
  escalaPorDoisPontos, marcarPonto, posicaoDaLupa, type Calibragem,
} from "./calibrate.js";
import { ordenarPorComprimento } from "./ordem.js";
import { criarPintor, passo, type Cena } from "./pintor.js";
import { selecionar } from "./select.js";
import { estimarBytes } from "./estimativa.js";
import { opcoesEfetivas, type EstadoDaTela } from "./toolbar.js";
import { montarBarra } from "./barra.js";

const tela = document.querySelector<HTMLCanvasElement>("#desenho")!;
const ctx = tela.getContext("2d")!;
const barra = document.querySelector<HTMLElement>("#barra")!;
// A tarefa 6 lê `#painel` para montar o painel lateral; nesta tarefa o
// elemento já existe no HTML (passo 3), mas nada em JS o usa ainda — declarar
// a constante aqui e não usá-la falharia `noUnusedLocals`.
const painelAviso = document.querySelector<HTMLElement>("#aviso")!;
const faixaDetalhe = document.querySelector<HTMLElement>("#faixa-detalhe")!;

const estado: EstadoDaTela = {
  opcoes: {
    excluded_layers: [], drop_fills: false, min_len_mm: 0,
    dedup: false, join_polylines: false, round_coords: false,
  },
  layersDesligados: new Set(),
  escala: 0.01,
  unidade: "m",
  parcial: false,
  bytes: 0,
  bytesBase: 0,
  sobreviventes: 0,
};

let job = "";
let nomeDoArquivo = "";
let pagina = 1;
let nPaginas = 1;
let meta: Meta | null = null;
let geometria: Geometria | null = null;
// Anotados: sem a anotação o TypeScript infere `Uint8Array<ArrayBuffer>` do
// valor inicial, e isso é mais estreito que o `Uint8Array<ArrayBufferLike>` que
// vem do `select()` — cujas entradas são montadas sobre o buffer recebido do
// servidor, sem cópia.
let mascara: Uint8Array = new Uint8Array(0);
let ordem: Uint32Array = new Uint32Array(0);
let vista: Vista = { escala: 1, dx: 0, dy: 0 };
let geracao = 0;
let controle = new AbortController();
let calibragem: Calibragem | null = null;

const lupa = document.createElement("canvas");
lupa.className = "lupa";
lupa.width = 120;
lupa.height = 120;
lupa.hidden = true;
document.querySelector(".area-do-desenho")!.append(lupa);
const AUMENTO_DA_LUPA = 3;

const pintor = criarPintor();

/**
 * Quantas entidades o preparo consome por quadro.
 *
 * Preparar 3 milhões leva da ordem de meio segundo; esta fatia mantém o quadro
 * curto e a planta se completa à vista, em vez de a tela travar.
 */
const ORCAMENTO_POR_QUADRO = 20_000;

function ajustarTamanho(): void {
  const proporcao = window.devicePixelRatio || 1;
  tela.width = Math.round(tela.clientWidth * proporcao);
  tela.height = Math.round(tela.clientHeight * proporcao);
}

let pedido = 0;

/**
 * Um quadro por vez, e nunca dois pedidos em voo.
 *
 * Enquanto o preparo não termina, cada quadro agenda o seguinte: é assim que o
 * desenho se completa em fatias sem bloquear a interface.
 */
function agendar(): void {
  if (pedido || !geometria) return;
  pedido = requestAnimationFrame(() => {
    pedido = 0;
    if (!geometria) return;
    const cena: Cena = {
      g: geometria, mascara, ordem, v: vista,
      larguraTela: tela.width, alturaTela: tela.height, geracao,
    };
    const acabou = passo(pintor, cena, ctx, () => new Path2D(),
                         ORCAMENTO_POR_QUADRO);
    // O teste de ponta a ponta espera por esta contagem, e não por relógio: com
    // preparo fatiado, o número de quadros depende da máquina.
    tela.dataset["desenhadas"] = String(pintor.desenhadas);
    if (!acabou) agendar();
  });
}

/**
 * Refaz a máscara e a estimativa. ~12 ms em 3 milhões de entidades — cabe na
 * thread principal, e foi para provar isso que a tarefa 1 do plano existiu.
 */
function recalcular(): void {
  if (!geometria) return;
  const opts = opcoesEfetivas(estado);
  mascara = selecionar(geometria, opts);
  estado.bytes = estimarBytes(geometria, mascara, opts);
  let vivos = 0;
  for (const v of mascara) vivos += v;
  estado.sobreviventes = vivos;
  geracao++;                     // avisa o pintor que a lista precisa ser refeita
  montarTopo();
  agendar();
}

/**
 * Troca a geometria e recalcula tudo o que depende dela.
 *
 * A ordem por comprimento só depende dos comprimentos, e eles não mudam com as
 * opções: refazê-la a cada clique custaria ~250 ms à toa.
 */
function trocarGeometria(nova: Geometria): void {
  geometria = nova;
  ordem = ordenarPorComprimento(nova.length_um);
  recalcular();
}

function mostrarAviso(aviso: Aviso | null): void {
  if (!aviso) { painelAviso.hidden = true; return; }
  painelAviso.hidden = false;
  painelAviso.replaceChildren();
  const titulo = document.createElement("h2");
  titulo.textContent = aviso.titulo;
  const detalhe = document.createElement("p");
  detalhe.textContent = aviso.detalhe;
  painelAviso.append(titulo, detalhe);
}

async function abrir(arquivo: File): Promise<void> {
  // Trocar de planta ou de página aborta o que estiver em voo: sem isso, o
  // detalhe da página anterior chega depois e contamina o canvas.
  controle.abort();
  controle = new AbortController();
  const sinal = controle.signal;

  try {
    mostrarAviso({ titulo: "Enviando o PDF", detalhe: "Um instante.",
                   podeTentarDeNovo: false });
    const ficha = await enviarPdf(arquivo, sinal);
    nomeDoArquivo = arquivo.name;
    job = ficha.job_id;
    nPaginas = ficha.n_paginas;
    pagina = 1;
    await carregarPagina();
  } catch (erro) {
    if (sinal.aborted) return;
    mostrarAviso(avisoDoErro(erro));
  }
}

/** `n_groups` vem do maior grupo visto: o `meta.json` não o traz. */
function contarGrupos(g: Geometria): number {
  let n = 0;
  for (const v of g.dup_group) if (v + 1 > n) n = v + 1;
  return n;
}

async function carregarPagina(): Promise<void> {
  controle.abort();
  controle = new AbortController();
  const sinal = controle.signal;

  geometria = null;
  faixaDetalhe.hidden = true;

  try {
    await pedirExtracao(job, pagina, sinal);
    const final = await esperarPagina(job, pagina, sinal, (e) =>
      mostrarAviso(avisoDaSituacao(e.situacao, e.codigo, e.mensagem)));
    if (final.situacao === "erro") {
      mostrarAviso(avisoDaSituacao("erro", final.codigo, final.mensagem));
      return;
    }

    meta = await lerMeta(job, pagina, sinal);
    mostrarAviso(null);
    estado.layersDesligados.clear();

    const cruEsqueleto = await lerGeometriaBruta(job, pagina, "esqueleto", sinal);
    if (sinal.aborted) return;
    const esqueleto = lerGeometria(cruEsqueleto, meta.layers, 0);
    esqueleto.n_groups = contarGrupos(esqueleto);
    estado.parcial = meta.partes.detalhe > 0;
    faixaDetalhe.hidden = !estado.parcial;
    faixaDetalhe.textContent = "Carregando o detalhe do desenho…";

    ajustarTamanho();
    vista = enquadrar(meta.largura_pt, meta.altura_pt, tela.width, tela.height);
    trocarGeometria(esqueleto);

    if (estado.parcial) {
      const cruDetalhe = await lerGeometriaBruta(job, pagina, "detalhe", sinal);
      if (sinal.aborted) return;
      const parteDetalhe = lerGeometria(cruDetalhe, meta.layers, 0);
      // A intercalação restaura a ordem original. Sem ela, o dedup elegeria um
      // sobrevivente por parte e a tela mostraria duplicata que o DXF não tem.
      const inteira = intercalar(esqueleto, parteDetalhe);
      inteira.n_groups = contarGrupos(inteira);
      estado.parcial = false;
      faixaDetalhe.hidden = true;
      trocarGeometria(inteira);
    }
  } catch (erro) {
    if (sinal.aborted) return;
    mostrarAviso(avisoDoErro(erro));
  }
}

function montarTopo(): void {
  montarBarra(barra, {
    estado,
    nomeDoArquivo,
    pagina,
    nPaginas,
    temGeometria: Boolean(geometria),
    mostrarMenu: false,          // a tarefa 6 liga isto ao modo do painel
    aoAbrirArquivo: (arquivo) => void abrir(arquivo),
    aoTrocarPagina: (p) => { pagina = p; void carregarPagina(); },
    aoAlternarPainel: () => {},  // a tarefa 6 liga isto
    aoExportar: () => void baixar(),
  });
}

async function baixar(): Promise<void> {
  try {
    const r = await exportar(job, pagina, {
      escala: estado.escala, unidade: estado.unidade,
      opcoes: opcoesEfetivas(estado),
    });
    const link = document.createElement("a");
    link.href = r.url;
    link.download = "";
    link.id = "link-do-dxf";
    document.body.append(link);
    link.click();
    link.remove();
  } catch (erro) {
    mostrarAviso(avisoDoErro(erro));
  }
}

// --- gestos -----------------------------------------------------------------

let arrastando = false;
let ultimoX = 0, ultimoY = 0;
let pinca: { distancia: number } | null = null;
let paradaDoGesto = 0;

/**
 * Move a vista, redesenha já com a lista que existe, e só depois de a mão parar
 * dá ao pintor a chance de preparar de novo.
 *
 * Preparar durante o gesto engasgaria o arrasto: são centenas de milissegundos.
 * Quem decide se vale refazer é o `precisaPreparar` dentro do pintor; aqui só
 * se oferece o momento.
 */
function aoMexer(nova: Vista): void {
  vista = nova;
  agendar();
  clearTimeout(paradaDoGesto);
  paradaDoGesto = window.setTimeout(agendar, PAUSA_DO_GESTO_MS);
}

/**
 * A lupa do toque.
 *
 * Recorta um pedaço do próprio canvas e o amplia: não redesenha nada, então
 * custa o mesmo em qualquer planta. No celular o dedo cobre exatamente a
 * extremidade que precisa ser mirada, e sem ela ninguém acerta a cota.
 */
function moverLupa(clienteX: number, clienteY: number): void {
  if (!calibragem?.ativa) { lupa.hidden = true; return; }
  const caixa = tela.getBoundingClientRect();
  const proporcao = window.devicePixelRatio || 1;
  const x = (clienteX - caixa.left) * proporcao;
  const y = (clienteY - caixa.top) * proporcao;

  const ctxLupa = lupa.getContext("2d")!;
  const lado = lupa.width / AUMENTO_DA_LUPA;
  ctxLupa.clearRect(0, 0, lupa.width, lupa.height);
  ctxLupa.drawImage(tela, x - lado / 2, y - lado / 2, lado, lado,
                    0, 0, lupa.width, lupa.height);
  // Cruz no centro, para mirar o que o dedo esconde.
  ctxLupa.strokeStyle = "#3d7eff";
  ctxLupa.beginPath();
  ctxLupa.moveTo(lupa.width / 2, 0);
  ctxLupa.lineTo(lupa.width / 2, lupa.height);
  ctxLupa.moveTo(0, lupa.height / 2);
  ctxLupa.lineTo(lupa.width, lupa.height / 2);
  ctxLupa.stroke();

  const onde = posicaoDaLupa(clienteX - caixa.left, clienteY - caixa.top,
                             caixa.width, caixa.height, lupa.width);
  lupa.style.left = `${onde.x}px`;
  lupa.style.top = `${onde.y}px`;
  lupa.hidden = false;
}

tela.addEventListener("click", (e) => {
  if (!calibragem?.ativa) return;
  const proporcao = window.devicePixelRatio || 1;
  const caixa = tela.getBoundingClientRect();
  calibragem = marcarPonto(calibragem, vista,
                           (e.clientX - caixa.left) * proporcao,
                           (e.clientY - caixa.top) * proporcao);
  if (calibragem.ativa) return;

  // Provisório e feio de propósito: uma caixa própria é trabalho de acabamento,
  // e está registrado como dívida no fim da etapa.
  const medida = window.prompt(
    `Quanto mede essa distância na planta, em ${estado.unidade}?`, "1");
  if (medida === null) { calibragem = null; mostrarAviso(null); return; }
  try {
    estado.escala = escalaPorDoisPontos(calibragem.pontos[0]!,
                                        calibragem.pontos[1]!, Number(medida));
    mostrarAviso(null);
  } catch (erro) {
    mostrarAviso({ titulo: "Não deu para calibrar", podeTentarDeNovo: true,
                   detalhe: erro instanceof Error ? erro.message : "" });
  }
  calibragem = null;
  montarTopo();
});

tela.addEventListener("pointerdown", (e) => {
  arrastando = true;
  ultimoX = e.clientX;
  ultimoY = e.clientY;
  tela.setPointerCapture(e.pointerId);
});
tela.addEventListener("pointermove", (e) => {
  if (e.pointerType === "touch") moverLupa(e.clientX, e.clientY);
  // Durante a calibração o arrasto não move a planta: o dedo está mirando um
  // ponto, e mover o desenho embaixo dele erraria a medida.
  if (!arrastando || calibragem?.ativa) return;
  const proporcao = window.devicePixelRatio || 1;
  aoMexer(aplicarArrasto(vista, (e.clientX - ultimoX) * proporcao,
                         (e.clientY - ultimoY) * proporcao));
  ultimoX = e.clientX;
  ultimoY = e.clientY;
});
tela.addEventListener("pointerup", () => {
  arrastando = false;
  lupa.hidden = true;
});
tela.addEventListener("pointercancel", () => { arrastando = false; });

tela.addEventListener("wheel", (e) => {
  e.preventDefault();
  const proporcao = window.devicePixelRatio || 1;
  const caixa = tela.getBoundingClientRect();
  aoMexer(aplicarZoom(vista, fatorDaRoda(e.deltaY),
                      (e.clientX - caixa.left) * proporcao,
                      (e.clientY - caixa.top) * proporcao));
}, { passive: false });

tela.addEventListener("touchmove", (e) => {
  if (e.touches.length !== 2) return;
  e.preventDefault();
  const proporcao = window.devicePixelRatio || 1;
  const caixa = tela.getBoundingClientRect();
  const a = { x: (e.touches[0]!.clientX - caixa.left) * proporcao,
              y: (e.touches[0]!.clientY - caixa.top) * proporcao };
  const b = { x: (e.touches[1]!.clientX - caixa.left) * proporcao,
              y: (e.touches[1]!.clientY - caixa.top) * proporcao };
  const agora = distancia(a, b);
  if (pinca) {
    const meio = centro(a, b);
    aoMexer(aplicarZoom(vista, agora / pinca.distancia, meio.x, meio.y));
  }
  pinca = { distancia: agora };
}, { passive: false });
tela.addEventListener("touchend", () => { pinca = null; });

tela.addEventListener("dblclick", () => {
  if (!meta) return;
  ajustarTamanho();
  aoMexer(enquadrar(meta.largura_pt, meta.altura_pt, tela.width, tela.height));
});

window.addEventListener("resize", () => {
  ajustarTamanho();
  aoMexer(vista);
});

ajustarTamanho();
montarTopo();
