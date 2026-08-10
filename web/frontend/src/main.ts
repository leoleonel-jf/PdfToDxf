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
  escalaPorDoisPontos, iniciarCalibragem, marcarPonto, posicaoDaLupa,
  type Calibragem,
} from "./calibrate.js";
import { ordenarPorComprimento } from "./ordem.js";
import { criarPintor, passo, type Cena } from "./pintor.js";
import { selecionar, type Opcoes } from "./select.js";
import { estimarBytes } from "./estimativa.js";
import { opcoesEfetivas, type EstadoDaTela } from "./toolbar.js";
import { montarBarra } from "./barra.js";
import {
  abrirEm, alternar, aoRedimensionar, estadoInicial, montarPainel,
  paraGuardar, type EstadoDoPainel, type Secao,
} from "./painel.js";
import { proporcaoRepetida, resumoDasCamadas, type ResumoDeCamada } from "./camadas.js";
import { secaoCamadas, secaoCompactacao, secaoEscala } from "./secoes.js";
import { criarBarraDeProgresso, criarBotao } from "./ui/controles.js";
import type { Progresso } from "./progresso.js";

const tela = document.querySelector<HTMLCanvasElement>("#desenho")!;
const ctx = tela.getContext("2d")!;
const barra = document.querySelector<HTMLElement>("#barra")!;
const painelRaiz = document.querySelector<HTMLElement>("#painel")!;
const painelAviso = document.querySelector<HTMLElement>("#aviso")!;
const faixaDetalhe = document.querySelector<HTMLElement>("#faixa-detalhe")!;

const estado: EstadoDaTela = {
  opcoes: {
    // Três ligadas de saída: as que só tiram redundância. `dedup` descarta
    // traços exatamente sobrepostos, `join_polylines` troca segmentos
    // encadeados por uma polilinha com os mesmos vértices, e `round_coords`
    // arredonda a 4 casas (dxf_writer.py:135) — com a unidade em metros, 0,1
    // mm de resolução, muito abaixo de qualquer tolerância de projeto.
    //
    // `drop_fills` fica desligada de propósito: ela apaga desenho de
    // verdade, hachura e área pintada somem da prancha. Ninguém deve
    // descobrir isso por acidente.
    excluded_layers: [], drop_fills: false, min_len_mm: 0,
    dedup: true, join_polylines: true, round_coords: true,
  },
  layersDesligados: new Set(),
  escala: 0.01,
  unidade: "m",
  parcial: false,
  bytes: 0,
  bytesBase: 0,
};

const CHAVE_DO_PAINEL = "pdftodxf.painel";

// O `try` não é zelo excessivo: em navegação privativa de alguns navegadores
// `localStorage` estoura ao ser lido, e a tela inteira morreria por causa de
// uma preferência de layout.
function guardado(): string | null {
  try { return localStorage.getItem(CHAVE_DO_PAINEL); } catch { return null; }
}

let painel: EstadoDoPainel = estadoInicial(window.innerWidth, guardado());

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
let camadas: ResumoDeCamada[] = [];

/** O que a tela está esperando agora, e nada se não estiver esperando nada. */
let emCurso: { onde: "aviso" | "faixa"; rotulo: string; p: Progresso } | null = null;
let cancelar: (() => void) | null = null;
let relogio = 0;

/** Início do preparo em curso, para a barra "Desenhando" — e não estado da tela. */
let inicioDoPreparo = 0;
/**
 * Quantas entidades a máscara atual mantém — o total da barra "Desenhando".
 *
 * Variável do laço de desenho, não de `EstadoDaTela`: a etapa 3.5 removeu o
 * campo `sobreviventes` de lá por ser código morto, e ele não volta.
 */
let sobreviventesDoPreparo = 0;

/**
 * A página inteira: todas as camadas, nenhuma compactação.
 *
 * É o "antes" que a barra mostra ao lado do "depois". Calculado só quando a
 * geometria troca — duas vezes por página, no esqueleto e no detalhe — e nunca
 * a cada clique: seriam ~12 ms jogados fora por opção marcada.
 */
const SEM_COMPACTACAO: Opcoes = {
  excluded_layers: [], drop_fills: false, min_len_mm: 0,
  dedup: false, join_polylines: false, round_coords: false,
};

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
    // Só aparece se demorar: numa planta leve o preparo termina em um quadro, e
    // piscar uma barra a cada clique numa opção seria pior do que não ter.
    if (!acabou && Date.now() - inicioDoPreparo > 300) {
      mostrarProgresso("faixa", "Desenhando",
                       { tipo: "determinado", feito: pintor.desenhadas,
                         total: sobreviventesDoPreparo });
    } else if (acabou && emCurso?.rotulo === "Desenhando") {
      esconderProgresso();
    }
    if (!acabou) agendar();
  });
}

/**
 * Refaz a máscara e a estimativa. ~12 ms em 3 milhões de entidades — cabe na
 * thread principal, e foi para provar isso que a tarefa 1 do plano existiu.
 */
function recalcular(): void {
  // Sem geometria não há o que recalcular, mas há o que redesenhar: é este o
  // caminho de todo clique no painel, e sair sem remontar deixaria o
  // interruptor mostrando o estado anterior ao próprio clique.
  if (!geometria) { montarTudo(); return; }
  const opts = opcoesEfetivas(estado);
  mascara = selecionar(geometria, opts);
  estado.bytes = estimarBytes(geometria, mascara, opts);
  geracao++;                     // avisa o pintor que a lista precisa ser refeita
  // Total da barra "Desenhando": conta os sobreviventes desta máscara. Variável
  // do laço de desenho — não de `EstadoDaTela` — porque só o preparo usa.
  sobreviventesDoPreparo = 0;
  for (const v of mascara) if (v) sobreviventesDoPreparo++;
  montarTudo();
  inicioDoPreparo = Date.now();
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
  camadas = resumoDasCamadas(nova);
  estado.bytesBase = estimarBytes(nova, selecionar(nova, SEM_COMPACTACAO),
                                  SEM_COMPACTACAO);
  recalcular();
}

/**
 * O indeterminado precisa de um relógio; o determinado, não.
 *
 * Sem isto o tempo decorrido ficaria congelado no instante em que a barra
 * apareceu — que é justamente o pior momento, porque é quando ele vale zero.
 */
function ligarRelogio(): void {
  if (relogio) return;
  relogio = window.setInterval(() => {
    if (emCurso?.p.tipo === "indeterminado") desenharProgresso();
    else pararRelogio();
  }, 1000);
}

function pararRelogio(): void {
  if (relogio) { clearInterval(relogio); relogio = 0; }
}

function mostrarProgresso(onde: "aviso" | "faixa", rotulo: string,
                          p: Progresso, podeCancelar = false): void {
  emCurso = { onde, rotulo, p };
  if (!podeCancelar) cancelar = null;
  if (p.tipo === "indeterminado") ligarRelogio(); else pararRelogio();
  desenharProgresso();
}

function esconderProgresso(): void {
  emCurso = null;
  cancelar = null;
  pararRelogio();
  desenharProgresso();
}

function desenharProgresso(): void {
  // Limpa sempre os dois locais, não só o que perde a vez: sem isto, uma barra
  // que nasceu no `painelAviso` (o envio) e a próxima que nasce na `faixaDetalhe`
  // (o download) deixam dois `[data-teste="progresso"]` na página ao mesmo
  // tempo — um escondido, mas ainda achável — e qualquer asserção de ponta a
  // ponta sobre "a barra" quebra por ambiguidade.
  if (!emCurso) {
    painelAviso.hidden = true;
    painelAviso.replaceChildren();
    faixaDetalhe.hidden = true;
    faixaDetalhe.replaceChildren();
    return;
  }
  const barra = criarBarraDeProgresso(emCurso.p, emCurso.rotulo, Date.now());
  if (emCurso.onde === "faixa") {
    painelAviso.hidden = true;
    painelAviso.replaceChildren();
    faixaDetalhe.hidden = false;
    faixaDetalhe.replaceChildren(barra);
    return;
  }
  faixaDetalhe.hidden = true;
  faixaDetalhe.replaceChildren();
  painelAviso.hidden = false;
  painelAviso.replaceChildren(barra);
  if (cancelar) {
    painelAviso.append(criarBotao({
      rotulo: "Cancelar", teste: "cancelar", aoClicar: () => cancelar?.(),
    }));
  }
}

/**
 * `esconderProgresso()` primeiro: um erro nunca pode aparecer por baixo de
 * uma barra viva. Ela chama `desenharProgresso`, que esconde `painelAviso` —
 * por isso é `mostrarAviso`, e não ela, quem decide a visibilidade depois.
 */
function mostrarAviso(aviso: Aviso | null): void {
  esconderProgresso();
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
  // Identidade e não rótulo: outra chamada a `abrir()` mais nova usa o mesmo
  // texto "Enviando o PDF", e comparar por rótulo esconderia a barra dela.
  let meuProgresso: typeof emCurso = null;

  try {
    cancelar = () => controle.abort();
    mostrarProgresso("aviso", "Enviando o PDF",
                     { tipo: "determinado", feito: 0, total: arquivo.size }, true);
    meuProgresso = emCurso;
    const ficha = await enviarPdf(arquivo, sinal, (feito, total) =>
      mostrarProgresso("aviso", "Enviando o PDF",
                       { tipo: "determinado", feito, total }, true));
    esconderProgresso();
    nomeDoArquivo = arquivo.name;
    job = ficha.job_id;
    nPaginas = ficha.n_paginas;
    pagina = 1;
    await carregarPagina();
  } catch (erro) {
    if (sinal.aborted) {
      // O clique em "Cancelar" aborta de verdade — sem isto, a barra ficava
      // presa na tela para sempre, com um botão que já não fazia nada.
      if (emCurso === meuProgresso) esconderProgresso();
      return;
    }
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
  estado.bytes = 0;
  estado.bytesBase = 0;
  // `esconderProgresso()` e não só `faixaDetalhe.hidden = true`: sem isto, uma
  // barra indeterminada da página anterior (relógio ligado) sobreviveria à
  // troca de página e reapareceria sozinha no próximo tique.
  esconderProgresso();
  // Sem remontar aqui, numa planta de várias páginas o "Exportar DXF" continua
  // habilitado com a estimativa da página anterior — e o clique exportaria uma
  // página que ainda não foi extraída.
  montarTudo();

  try {
    await pedirExtracao(job, pagina, sinal);
    const inicio = Date.now();
    const final = await esperarPagina(job, pagina, sinal, (e) => {
      if (e.situacao === "na_fila" || e.situacao === "extraindo") {
        mostrarProgresso("aviso", "Processando a planta",
                         { tipo: "indeterminado", desde: inicio });
      }
    });
    if (final.situacao === "erro") {
      mostrarAviso(avisoDaSituacao("erro", final.codigo, final.mensagem));
      return;
    }

    meta = await lerMeta(job, pagina, sinal);
    mostrarAviso(null);
    estado.layersDesligados.clear();
    camadas = [];

    const cruEsqueleto = await lerGeometriaBruta(
      job, pagina, "esqueleto", sinal, (lidos, total) =>
        mostrarProgresso("faixa", "Carregando o desenho", total
          ? { tipo: "determinado", feito: lidos, total }
          : { tipo: "indeterminado", desde: inicio }));
    esconderProgresso();
    if (sinal.aborted) return;
    const esqueleto = lerGeometria(cruEsqueleto, meta.layers, 0);
    esqueleto.n_groups = contarGrupos(esqueleto);
    estado.parcial = meta.partes.detalhe > 0;

    ajustarTamanho();
    vista = enquadrar(meta.largura_pt, meta.altura_pt, tela.width, tela.height);
    trocarGeometria(esqueleto);

    if (estado.parcial) {
      const cruDetalhe = await lerGeometriaBruta(
        job, pagina, "detalhe", sinal, (lidos, total) =>
          mostrarProgresso("faixa", "Carregando o detalhe do desenho", total
            ? { tipo: "determinado", feito: lidos, total }
            : { tipo: "indeterminado", desde: inicio }));
      esconderProgresso();
      if (sinal.aborted) return;
      const parteDetalhe = lerGeometria(cruDetalhe, meta.layers, 0);
      // A intercalação restaura a ordem original. Sem ela, o dedup elegeria um
      // sobrevivente por parte e a tela mostraria duplicata que o DXF não tem.
      const inteira = intercalar(esqueleto, parteDetalhe);
      inteira.n_groups = contarGrupos(inteira);
      estado.parcial = false;
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
    mostrarMenu: painel.modo === "gaveta",
    aoAbrirArquivo: (arquivo) => void abrir(arquivo),
    aoTrocarPagina: (p) => { pagina = p; void carregarPagina(); },
    aoAlternarPainel: alternarPainel,
    aoExportar: () => void baixar(),
  });
}

function montarPainelLateral(): void {
  montarPainel(painelRaiz, painel, {
    escala: () => secaoEscala(estado, Boolean(geometria), iniciarCalibracao,
                              aoMudarOpcoes),
    compactacao: () => secaoCompactacao(
      estado, geometria ? proporcaoRepetida(geometria) : null, aoMudarOpcoes),
    camadas: () => secaoCamadas(estado, camadas, estado.parcial, aoMudarOpcoes),
  }, alternarPainel, (s: Secao) => {
    painel = abrirEm(painel, s);
    montarTudo();
    // Abrir o painel na seção certa é metade do trabalho: com 260 px de
    // largura, Camadas fica abaixo da dobra e o usuário teria de procurar o
    // que acabou de pedir.
    document.querySelector(`[data-teste="secao-${s}"]`)
      ?.scrollIntoView({ block: "start" });
  });
}

/** Alterna o painel e grava a preferência. Os dois botões passam por aqui. */
function alternarPainel(): void {
  painel = alternar(painel);
  const g = paraGuardar(painel);
  try {
    if (g) localStorage.setItem(CHAVE_DO_PAINEL, g);
  } catch { /* navegação privativa recusa gravar; a tela não pode morrer por isso */ }
  montarTudo();
}

const BUSCA = '[data-teste="busca-camadas"]';

/**
 * Remonta a tela preservando foco, cursor, rolagem e o filtro de camadas.
 *
 * O painel é reconstruído do zero a cada mudança, e as setas de um campo
 * numérico disparam `change` a cada passo: sem isto, apertar ↑ duas vezes no
 * campo de mm tira o foco do campo já na primeira. Reencontrar o elemento pelo
 * `data-teste` é mais barato do que remontar por partes, e resolve todos os
 * campos de uma vez — inclusive a busca de camadas.
 *
 * Rolagem e filtro andam junto com o foco pelo mesmo motivo: filtrar por
 * "parede" e clicar no olho de uma camada não pode devolver a lista inteira,
 * com o campo vazio e o painel no topo.
 */
function montarTudo(): void {
  const ativo = document.activeElement;
  const foco = ativo instanceof HTMLElement ? ativo.dataset["teste"] : undefined;
  // `selectionStart` estoura em `input type=number` em alguns navegadores.
  const cursor = ativo instanceof HTMLInputElement && ativo.type !== "number"
    ? [ativo.selectionStart, ativo.selectionEnd] as const
    : null;
  const rolagem = painelRaiz.scrollTop;
  const rolagemDaLista =
    painelRaiz.querySelector<HTMLElement>(".lista-de-camadas")?.scrollTop ?? 0;
  const filtro = painelRaiz.querySelector<HTMLInputElement>(BUSCA)?.value ?? "";

  montarTopo();
  montarPainelLateral();

  // O filtro volta antes da rolagem: é ele que decide a altura da lista.
  const busca = painelRaiz.querySelector<HTMLInputElement>(BUSCA);
  if (busca && filtro) {
    busca.value = filtro;
    busca.dispatchEvent(new Event("input"));
  }
  painelRaiz.scrollTop = rolagem;
  const lista = painelRaiz.querySelector<HTMLElement>(".lista-de-camadas");
  if (lista) lista.scrollTop = rolagemDaLista;

  if (!foco) return;
  // `CSS.escape` porque o `data-teste` de uma camada carrega o nome que veio do
  // PDF: uma camada chamada `EIXO"A` faria o seletor estourar aqui, depois de
  // remontar e antes de repintar, deixando a tela congelada.
  const novo = document.querySelector<HTMLElement>(
    `[data-teste="${CSS.escape(foco)}"]`);
  if (!novo) return;
  novo.focus();
  if (novo instanceof HTMLInputElement && cursor && cursor[0] !== null) {
    novo.setSelectionRange(cursor[0], cursor[1]);
  }
}

function aoMudarOpcoes(): void {
  recalcular();          // recalcular já chama montarTudo pelo caminho abaixo
}

function iniciarCalibracao(): void {
  calibragem = iniciarCalibragem();
  mostrarAviso({ titulo: "Calibração", podeTentarDeNovo: false,
                 detalhe: "Toque nas duas extremidades de uma medida " +
                          "conhecida da planta." });
  montarTudo();
}

async function baixar(): Promise<void> {
  const inicio = Date.now();
  try {
    mostrarProgresso("aviso", "Gerando o DXF", { tipo: "indeterminado", desde: inicio });
    const r = await exportar(job, pagina, {
      escala: estado.escala, unidade: estado.unidade,
      opcoes: opcoesEfetivas(estado),
    });
    esconderProgresso();
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
  montarTudo();
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
  const novo = aoRedimensionar(painel, window.innerWidth, guardado());
  if (novo !== painel) { painel = novo; montarTudo(); }
  ajustarTamanho();
  aoMexer(vista);
});

ajustarTamanho();
montarTudo();
