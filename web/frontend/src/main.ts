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
  concluirSenha, entrar, enviarPdf, ErroDaApi, esperarPagina, exportar,
  lerCota, lerGeometriaBruta, lerMeta, pedirExtracao, pedirSenha, registrar,
  sair, type Cota, type Meta,
} from "./api.js";
import { acaoDaUrl, montarCaixaDeConta, type ModoDaCaixa } from "./conta.js";
import { enquadrar, pontoDaTela, type Vista } from "./canvas.js";
import { intercalar, lerGeometria, type Geometria } from "./formato.js";
import {
  aplicarArrasto, aplicarZoom, centro, distancia, fatorDaRoda,
  PAUSA_DO_GESTO_MS,
} from "./gestos.js";
import { avisoDaSituacao, avisoDoErro, type Aviso } from "./estados.js";
import {
  escalaPorDoisPontos, escalaValidaParaExportar, iniciarCalibragem,
  marcarPonto, medidaDigitada, posicaoDaLupa, type Calibragem,
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
import {
  atualizarBarraDeProgresso, criarBarraDeProgresso, criarBotao,
} from "./ui/controles.js";
import { porcentagem, type Progresso } from "./progresso.js";

const tela = document.querySelector<HTMLCanvasElement>("#desenho")!;
const ctx = tela.getContext("2d")!;
const barra = document.querySelector<HTMLElement>("#barra")!;
const painelRaiz = document.querySelector<HTMLElement>("#painel")!;
const painelAviso = document.querySelector<HTMLElement>("#aviso")!;
const faixaDetalhe = document.querySelector<HTMLElement>("#faixa-detalhe")!;
const caixaDaConta = document.querySelector<HTMLElement>("#conta")!;

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

/**
 * Dois lugares de espera, dois donos — e nunca um só disputado por cinco.
 *
 * Havia um slot único para os cinco momentos, sem arbitragem: um tique do
 * download escrevia nele e, de quebra, apagava o aviso que a calibração tinha
 * acabado de pôr na sobreposição, porque os dois moram no mesmo elemento.
 * Agora cada momento escreve **no seu**: envio, extração e exportação na
 * sobreposição; download e desenho na faixa de baixo. Quem pinta um lugar
 * nunca toca no outro.
 */
type Momento = { rotulo: string; p: Progresso; detalhe?: string };
let progressoAviso: Momento | null = null;
let progressoFaixa: Momento | null = null;

/**
 * O aviso vivo, e ele ganha do progresso na sobreposição.
 *
 * Instrução de calibração e mensagem de erro vêm antes de qualquer barra: a
 * barra volta sozinha quando o aviso sair.
 */
let avisoCorrente: Aviso | null = null;
let cancelar: (() => void) | null = null;
let relogio = 0;

/**
 * Qual envio está valendo agora.
 *
 * A guarda não pode ser a identidade do objeto de progresso: ele é recriado a
 * cada tique, e a comparação viraria falsa exatamente quando o usuário mais
 * precisa cancelar — num arquivo grande, depois de o envio já ter andado.
 */
let envioEmCurso = 0;

/** Início do preparo em curso, para a barra "Desenhando" — e não estado da tela. */
let inicioDoPreparo = 0;

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

const areaDoDesenho = document.querySelector<HTMLElement>(".area-do-desenho")!;

const lupa = document.createElement("canvas");
lupa.className = "lupa";
lupa.width = 120;
lupa.height = 120;
lupa.hidden = true;
areaDoDesenho.append(lupa);
const AUMENTO_DA_LUPA = 3;

/**
 * As marcas dos pontos já clicados na calibração.
 *
 * Sem elas o primeiro clique não deixa rastro nenhum na tela, e o usuário não
 * sabe se pegou. Vivem fora do motor de desenho — elementos absolutos dentro
 * de `.area-do-desenho`, como a lupa — porque `calibragem.pontos` guarda
 * coordenadas de **papel**, e recolocá-las a cada `aoMexer` é mais simples do
 * que fazer o `pintor.ts` conhecer um estado que não é dele.
 */
const marcasDeCalibracao: HTMLElement[] = [];

function redesenharMarcasDeCalibracao(): void {
  const pontos = calibragem?.pontos ?? [];
  while (marcasDeCalibracao.length < pontos.length) {
    const marca = document.createElement("div");
    marca.className = "marca-calibracao";
    areaDoDesenho.append(marca);
    marcasDeCalibracao.push(marca);
  }
  while (marcasDeCalibracao.length > pontos.length) {
    marcasDeCalibracao.pop()!.remove();
  }
  const proporcao = window.devicePixelRatio || 1;
  pontos.forEach((p, i) => {
    const naTela = pontoDaTela(vista, p[0]!, p[1]!);
    const marca = marcasDeCalibracao[i]!;
    marca.style.left = `${naTela.x / proporcao}px`;
    marca.style.top = `${naTela.y / proporcao}px`;
  });
}

/** Limpa as marcas quando a calibração termina ou é cancelada. */
function limparMarcasDeCalibracao(): void {
  for (const m of marcasDeCalibracao) m.remove();
  marcasDeCalibracao.length = 0;
}

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
    //
    // **Indeterminada, e não uma porcentagem.** O par óbvio seria
    // `pintor.desenhadas` sobre os sobreviventes da máscara, e ele mente: o
    // numerador conta o que foi traçado dentro da janela visível e o
    // denominador soma a página inteira. Com zoom num canto, 8 mil traços
    // sobre 2,3 milhões marcariam 0% do começo ao fim do preparo. Denominador
    // honesto só existiria dentro do `pintor.ts`, que é do motor de desenho.
    if (!acabou && Date.now() - inicioDoPreparo > 300) {
      mostrarProgresso("faixa", "Desenhando",
                       { tipo: "indeterminado", desde: inicioDoPreparo });
    } else if (acabou && progressoFaixa?.rotulo === "Desenhando") {
      esconderProgresso("faixa");
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
 * Um relógio só serve aos dois lugares: ele acorda enquanto algum deles for
 * indeterminado e para quando nenhum for.
 */
function sincronizarRelogio(): void {
  const preciso = progressoAviso?.p.tipo === "indeterminado" ||
                  progressoFaixa?.p.tipo === "indeterminado";
  if (preciso && !relogio) {
    relogio = window.setInterval(() => {
      desenharProgresso();
      sincronizarRelogio();
    }, 1000);
  } else if (!preciso && relogio) {
    clearInterval(relogio);
    relogio = 0;
  }
}

function mostrarProgresso(onde: "aviso" | "faixa", rotulo: string, p: Progresso,
                          extra: { podeCancelar?: boolean; detalhe?: string } = {}):
                          void {
  const momento: Momento = { rotulo, p, detalhe: extra.detalhe };
  if (onde === "faixa") {
    progressoFaixa = momento;
  } else {
    progressoAviso = momento;
    if (!extra.podeCancelar) cancelar = null;
  }
  sincronizarRelogio();
  desenharProgresso();
}

/** Esconde **um** lugar. O outro continua exatamente como estava. */
function esconderProgresso(onde: "aviso" | "faixa"): void {
  if (onde === "faixa") {
    progressoFaixa = null;
  } else {
    progressoAviso = null;
    cancelar = null;
  }
  sincronizarRelogio();
  desenharProgresso();
}

/** O que está montado num lugar agora, para não remontar o que não mudou. */
type Montado =
  | { tipo: "aviso"; aviso: Aviso }
  | { tipo: "barra"; rotulo: string; detalhe: string; comBotao: boolean;
      chave: string; el: HTMLElement };
type Lugar = { raiz: HTMLElement; montado: Montado | null };

const lugarDoAviso: Lugar = { raiz: painelAviso, montado: null };
const lugarDaFaixa: Lugar = { raiz: faixaDetalhe, montado: null };

/**
 * O que a barra mostra agora, em uma linha.
 *
 * É a chave da deduplicação, e vale para os cinco momentos: enquanto o rótulo
 * e a porcentagem inteira — ou o segundo inteiro decorrido, no indeterminado —
 * não mudarem, não há nada novo a pintar.
 */
function chaveDoTique(m: Momento, agora: number): string {
  const pct = porcentagem(m.p);
  if (pct !== null) return `d${pct}`;
  if (m.p.tipo === "indeterminado") {
    return `i${Math.floor((agora - m.p.desde) / 1000)}`;
  }
  return "sem";       // determinado sem total: não há número nem relógio
}

function limparLugar(lugar: Lugar): void {
  if (!lugar.montado) return;
  lugar.raiz.replaceChildren();
  lugar.raiz.hidden = true;
  lugar.montado = null;
}

/**
 * Cria a barra uma vez; nos tiques seguintes só atualiza o que muda.
 *
 * Recriar o DOM a cada tique destruía o botão de cancelar entre o `mousedown` e
 * o `mouseup` do usuário — num envio de verdade o navegador dispara progresso a
 * cada ~50 ms, e o clique era engolido. Mesma razão do `montarTudo`, que
 * preserva foco e cursor desde a etapa 3.5.
 */
function pintarBarra(lugar: Lugar, m: Momento, agora: number,
                     comBotao: boolean): void {
  const detalhe = m.detalhe ?? "";
  const chave = chaveDoTique(m, agora);
  const antes = lugar.montado;
  if (antes?.tipo === "barra" && antes.rotulo === m.rotulo &&
      antes.detalhe === detalhe && antes.comBotao === comBotao) {
    if (antes.chave === chave) return;
    antes.chave = chave;
    atualizarBarraDeProgresso(antes.el, m.p, agora);
    return;
  }
  const el = criarBarraDeProgresso(m.p, m.rotulo, agora, m.detalhe);
  lugar.raiz.replaceChildren(el);
  if (comBotao) {
    lugar.raiz.append(criarBotao({
      rotulo: "Cancelar", teste: "cancelar", aoClicar: () => cancelar?.(),
    }));
  }
  lugar.raiz.hidden = false;
  lugar.montado = { tipo: "barra", rotulo: m.rotulo, detalhe, comBotao, chave, el };
}

function pintarAviso(lugar: Lugar, aviso: Aviso): void {
  if (lugar.montado?.tipo === "aviso" && lugar.montado.aviso === aviso) return;
  const titulo = document.createElement("h2");
  titulo.textContent = aviso.titulo;
  const detalhe = document.createElement("p");
  detalhe.textContent = aviso.detalhe;
  lugar.raiz.replaceChildren(titulo, detalhe);
  lugar.raiz.hidden = false;
  lugar.montado = { tipo: "aviso", aviso };
}

/**
 * Desenha **cada lugar a partir do seu próprio slot**, e nunca o outro.
 *
 * Na sobreposição o aviso ganha: enquanto houver um vivo, a barra de lá espera
 * a vez em silêncio, e volta sozinha quando o aviso sair.
 */
function desenharProgresso(): void {
  const agora = Date.now();
  if (progressoFaixa) pintarBarra(lugarDaFaixa, progressoFaixa, agora, false);
  else limparLugar(lugarDaFaixa);

  if (avisoCorrente) pintarAviso(lugarDoAviso, avisoCorrente);
  else if (progressoAviso) {
    pintarBarra(lugarDoAviso, progressoAviso, agora, cancelar !== null);
  } else limparLugar(lugarDoAviso);
}

/**
 * O aviso da sobreposição — instrução ou erro —, ou `null` para tirá-lo.
 *
 * Quem termina um momento esconde o seu próprio progresso; o aviso não faz isso
 * por ninguém, senão voltaria a existir um dono só para dois assuntos.
 */
function mostrarAviso(aviso: Aviso | null): void {
  avisoCorrente = aviso;
  desenharProgresso();
}

async function abrir(arquivo: File): Promise<void> {
  // O teto do plano, conferido **antes** de subir um byte. A spec pede assim, e
  // a razão é simples: subir 40 MB para receber 413 no fim é gastar o tempo do
  // usuário para dizer o que já se sabia quando ele escolheu o arquivo.
  if (cota && arquivo.size > cota.teto_bytes) {
    const mb = Math.floor(cota.teto_bytes / (1024 * 1024));
    mostrarAviso({
      titulo: "O arquivo passa do tamanho permitido",
      detalhe: `Este arquivo tem ${(arquivo.size / (1024 * 1024)).toFixed(1)} ` +
               `MB e o limite é de ${mb} MB.` +
               (cota.tipo === "visitante"
                 ? " Com uma conta gratuita o limite sobe para 100 MB."
                 : ""),
      podeTentarDeNovo: false,
    });
    return;
  }
  // Trocar de planta ou de página aborta o que estiver em voo: sem isso, o
  // detalhe da página anterior chega depois e contamina o canvas.
  controle.abort();
  controle = new AbortController();
  const sinal = controle.signal;
  const meuControle = controle;
  const meuEnvio = ++envioEmCurso;

  try {
    // O controlador é capturado, e não lido do topo: uma chamada mais nova a
    // `abrir()` já trocou `controle`, e o botão cancelaria o envio errado.
    cancelar = () => meuControle.abort();
    // Indeterminada até o primeiro tique de verdade, e não "0% de arquivo.size".
    // O navegador só relata bytes quando o evento traz `lengthComputable`; sem
    // ele a barra ficaria parada em 0% até o fim, que é pior do que não ter
    // barra. Assim a falta de tique degrada sozinha para indeterminado.
    const inicioDoEnvio = Date.now();
    mostrarProgresso("aviso", "Enviando o PDF",
                     { tipo: "indeterminado", desde: inicioDoEnvio },
                     { podeCancelar: true });
    const ficha = await enviarPdf(arquivo, sinal, (feito, total) =>
      mostrarProgresso("aviso", "Enviando o PDF", total > 0
        ? { tipo: "determinado", feito, total }
        : { tipo: "indeterminado", desde: inicioDoEnvio },
        { podeCancelar: true }));
    esconderProgresso("aviso");
    // O envio acabou de consumir uma vaga: o canto tem de dizer isso agora, e
    // não daqui a alguns minutos, quando a extração terminar.
    void atualizarCota();
    nomeDoArquivo = arquivo.name;
    job = ficha.job_id;
    nPaginas = ficha.n_paginas;
    pagina = 1;
    await carregarPagina();
  } catch (erro) {
    if (sinal.aborted) {
      // O clique em "Cancelar" aborta de verdade — sem isto, a barra ficava
      // presa na tela para sempre, com um botão que já não fazia nada. Só
      // esconde se este ainda for o envio corrente: um `abrir()` mais novo já
      // pôs a barra dele na tela, e apagá-la seria pior que não esconder nada.
      if (meuEnvio === envioEmCurso) esconderProgresso("aviso");
      return;
    }
    esconderProgresso("aviso");
    mostrarAviso(avisoDoErro(erro));
    // Também na recusa: um 429 de cota é justamente o momento em que o saldo
    // do canto ficou desatualizado.
    void atualizarCota();
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
  // troca de página e reapareceria sozinha no próximo tique. Os dois lugares,
  // porque a página anterior pode ter deixado coisa nos dois.
  esconderProgresso("aviso");
  esconderProgresso("faixa");
  // O aviso da página anterior não pode ficar por cima da espera desta.
  mostrarAviso(null);
  // Sem remontar aqui, numa planta de várias páginas o "Exportar DXF" continua
  // habilitado com a estimativa da página anterior — e o clique exportaria uma
  // página que ainda não foi extraída.
  montarTudo();

  try {
    await pedirExtracao(job, pagina, sinal);
    // Um instante de início por momento: com um só, o relógio do download
    // começaria a contar desde a extração e o primeiro pedaço da geometria já
    // anunciaria "4 min" numa planta que levou 4 minutos para ser extraída.
    const inicioDaExtracao = Date.now();
    const final = await esperarPagina(job, pagina, sinal, (e) => {
      // Só a espera vira barra: "erro" também tem texto em `avisoDaSituacao`,
      // e ele é aviso, não progresso — quem o mostra é o `mostrarAviso` abaixo.
      if (e.situacao !== "na_fila" && e.situacao !== "extraindo") return;
      // O texto da espera vem de `avisoDaSituacao`, e é ele que explica por que
      // isto demora — "Plantas grandes levam alguns minutos". Uma barra sozinha
      // numa espera de minutos não diz nada a quem está esperando.
      const espera = avisoDaSituacao(e.situacao);
      if (espera) {
        mostrarProgresso("aviso", espera.titulo,
                         { tipo: "indeterminado", desde: inicioDaExtracao },
                         { detalhe: espera.detalhe });
      }
    });
    esconderProgresso("aviso");
    if (final.situacao === "erro") {
      mostrarAviso(avisoDaSituacao("erro", final.codigo, final.mensagem));
      return;
    }

    meta = await lerMeta(job, pagina, sinal);
    estado.layersDesligados.clear();
    camadas = [];

    // A barra nasce antes do primeiro pedaço, indeterminada: entre o pedido e a
    // resposta não se sabe nem o tamanho, e ficar sem indicador nenhum nessa
    // janela é o que fazia o download parecer travado.
    const inicioDoEsqueleto = Date.now();
    mostrarProgresso("faixa", "Carregando o desenho",
                     { tipo: "indeterminado", desde: inicioDoEsqueleto });
    const cruEsqueleto = await lerGeometriaBruta(
      job, pagina, "esqueleto", sinal, (lidos, total) =>
        mostrarProgresso("faixa", "Carregando o desenho", total
          ? { tipo: "determinado", feito: lidos, total }
          : { tipo: "indeterminado", desde: inicioDoEsqueleto }));
    esconderProgresso("faixa");
    if (sinal.aborted) return;
    const esqueleto = lerGeometria(cruEsqueleto, meta.layers, 0);
    esqueleto.n_groups = contarGrupos(esqueleto);
    estado.parcial = meta.partes.detalhe > 0;

    ajustarTamanho();
    vista = enquadrar(meta.largura_pt, meta.altura_pt, tela.width, tela.height);
    trocarGeometria(esqueleto);

    if (estado.parcial) {
      const inicioDoDetalhe = Date.now();
      mostrarProgresso("faixa", "Carregando o detalhe do desenho",
                       { tipo: "indeterminado", desde: inicioDoDetalhe });
      const cruDetalhe = await lerGeometriaBruta(
        job, pagina, "detalhe", sinal, (lidos, total) =>
          mostrarProgresso("faixa", "Carregando o detalhe do desenho", total
            ? { tipo: "determinado", feito: lidos, total }
            : { tipo: "indeterminado", desde: inicioDoDetalhe }));
      esconderProgresso("faixa");
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
    // A checagem vem antes de esconder: quem abortou foi uma troca de página, e
    // a chamada nova já pôs a barra dela na tela — apagá-la aqui deixaria a
    // página nova carregando sem indicador nenhum.
    if (sinal.aborted) return;
    esconderProgresso("aviso");
    esconderProgresso("faixa");
    mostrarAviso(avisoDoErro(erro));
  }
}

// --- conta e cota -----------------------------------------------------------

let cota: Cota | null = null;
let modoDaConta: ModoDaCaixa = null;
let recadoDaConta = "";
let erroDaConta = "";
// O token do modo `nova-senha`, lido da URL e nunca digitado: é ele que
// identifica a conta, e é por isso que a caixa daquele modo não pede e-mail.
let tokenDeSenha = "";
// Uma vez por carga: repetir o aviso a cada leitura de cota cobriria a planta
// a cada envio, e a conta não confirmada não é um erro novo a cada tique.
let jaAvisouDaConfirmacao = false;

/**
 * Relê a cota e remonta o topo.
 *
 * Falha aqui **não vira aviso na tela**: a cota é informação de canto, e um
 * erro de rede ao lê-la não pode cobrir a planta com um painel. O canto
 * simplesmente não mostra saldo até a próxima leitura dar certo.
 */
async function atualizarCota(): Promise<void> {
  try {
    cota = await lerCota();
  } catch {
    cota = null;
  }
  // Aviso, e não erro: a conta funciona, só não destravou a cota maior. Uma
  // vez por carga — repetir a cada leitura cobriria a planta a cada envio. E
  // só quando a sobreposição está livre: se um aviso alheio já estiver na
  // tela (por exemplo, de um envio que terminou entre o pedido e a resposta
  // desta releitura), `jaAvisouDaConfirmacao` fica falso e este aviso espera
  // a próxima leitura de cota em vez de atropelar o que já está visível.
  if (cota && cota.tipo === "logado" && !cota.confirmado &&
      !jaAvisouDaConfirmacao && !avisoCorrente) {
    jaAvisouDaConfirmacao = true;
    mostrarAviso(avisoDoErro(new ErroDaApi(403, "", "conta_nao_confirmada")));
  }
  montarTudo();
}

/**
 * Sai e relê a cota.
 *
 * O `try` não é zelo: `sair().then(atualizarCota)` sem `catch` deixa uma
 * promessa rejeitada solta quando a rede cai — e a falha não pode virar aviso
 * na tela, pela mesma razão de `atualizarCota`. Se o servidor não confirmou, a
 * releitura da cota conta a verdade: o canto continua mostrando o e-mail.
 */
async function encerrarSessao(): Promise<void> {
  try {
    await sair();
  } catch { /* a releitura abaixo é que diz se a sessão caiu mesmo */ }
  await atualizarCota();
}

function abrirConta(modo: ModoDaCaixa): void {
  modoDaConta = modo;
  recadoDaConta = "";
  erroDaConta = "";
  montarConta();
}

function montarConta(): void {
  montarCaixaDeConta(caixaDaConta, modoDaConta, {
    recado: recadoDaConta,
    erro: erroDaConta,
    aoTrocarModo: (m) => abrirConta(m),
    aoFechar: () => abrirConta(null),
    aoConfirmar: (modo, email, senha) => void confirmarConta(modo, email, senha),
  });
}

async function confirmarConta(modo: Exclude<ModoDaCaixa, null>,
                              email: string, senha: string): Promise<void> {
  erroDaConta = "";
  recadoDaConta = "";
  try {
    if (modo === "entrar") {
      await entrar(email, senha);
      modoDaConta = null;
    } else if (modo === "cadastrar") {
      recadoDaConta = (await registrar(email, senha)).mensagem;
    } else if (modo === "senha") {
      recadoDaConta = (await pedirSenha(email)).mensagem;
    } else {
      // `nova-senha`: o token veio da URL, não do formulário — a caixa
      // daquele modo não tem campo de e-mail nem de token para digitar.
      await concluirSenha(tokenDeSenha, senha);
      modoDaConta = null;
      // O recado vai para a tela, e não para a caixa: ela está fechando.
      mostrarAviso({
        titulo: "Senha alterada",
        detalhe: "Sua senha foi trocada. Entre com a senha nova.",
        podeTentarDeNovo: false,
      });
    }
  } catch (erro) {
    // `avisoDoErro` e não o texto cru: é ele que garante a regra de "diga o que
    // houve e o que fazer" — e é o mesmo vocabulário do resto da tela. No modo
    // `nova-senha`, um token vencido ou já usado vira `400 token_invalido`, e a
    // mensagem do servidor ("Este link não vale mais. Peça outro.") já é a
    // oferta de pedir outro link; a própria caixa continua com o botão
    // "Esqueci a senha" entre as alternativas.
    erroDaConta = avisoDoErro(erro).detalhe;
  }
  montarConta();
  await atualizarCota();
}

function montarTopo(): void {
  montarBarra(barra, {
    estado,
    nomeDoArquivo,
    pagina,
    nPaginas,
    temGeometria: Boolean(geometria),
    mostrarMenu: painel.modo === "gaveta",
    cota,
    acoesDaConta: {
      aoEntrar: () => abrirConta("entrar"),
      aoCadastrar: () => abrirConta("cadastrar"),
      aoSair: () => void encerrarSessao(),
    },
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
 * O painel é reconstruído do zero a cada mudança, e um campo perderia o foco
 * a cada `change` sem isto — trocar de camada ou digitar num campo não pode
 * devolver o painel inteiro em branco, com o cursor em lugar nenhum.
 * Reencontrar o elemento pelo `data-teste` é mais barato do que remontar por
 * partes, e resolve todos os campos de uma vez — inclusive a busca de camadas.
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
  limparMarcasDeCalibracao();
  calibragem = iniciarCalibragem();
  mostrarAviso({ titulo: "Calibração", podeTentarDeNovo: false,
                 detalhe: "Toque nas duas extremidades de uma medida " +
                          "conhecida da planta." });
  montarTudo();
}

async function baixar(): Promise<void> {
  // Cinto de segurança: com as guardas de `calibrate.ts` e do campo "Escala
  // 1:" a interface não deveria deixar `escala` sair de `NaN` ou infinito,
  // mas "não deveria" não é "não pode" — e um `JSON.stringify` de `NaN` vira
  // `null` em silêncio, que o servidor só recusa com um 422 sem contexto.
  if (!escalaValidaParaExportar(estado.escala)) {
    mostrarAviso({
      titulo: "A escala ainda não é válida",
      detalhe: "Calibre ou digite a escala de plotagem antes de exportar.",
      podeTentarDeNovo: true,
    });
    return;
  }
  const inicio = Date.now();
  try {
    mostrarProgresso("aviso", "Gerando o DXF", { tipo: "indeterminado", desde: inicio });
    const r = await exportar(job, pagina, {
      escala: estado.escala, unidade: estado.unidade,
      opcoes: opcoesEfetivas(estado),
    });
    esconderProgresso("aviso");
    const link = document.createElement("a");
    link.href = r.url;
    link.download = "";
    link.id = "link-do-dxf";
    document.body.append(link);
    link.click();
    link.remove();
  } catch (erro) {
    esconderProgresso("aviso");
    mostrarAviso(avisoDoErro(erro));
  } finally {
    // Nos dois desfechos: o DXF gerado consumiu uma vaga de download, e a
    // recusa por cota é a outra metade da mesma notícia. Fora do `try` de
    // propósito — uma falha ao reler a cota não pode virar aviso na tela.
    void atualizarCota();
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
  // As marcas de calibração são de papel; sem isto, um zoom entre um clique e
  // o outro deixaria a marca do primeiro ponto flutuando fora do lugar.
  redesenharMarcasDeCalibracao();
  // O preparo que este gesto pode disparar começa agora.
  //
  // Sem isto, `inicioDoPreparo` só era gravado em `recalcular()` e, num arrasto
  // ou num zoom — o gesto mais comum da tela —, `Date.now() - inicioDoPreparo`
  // já valia minutos: o limiar de 300 ms passava de primeira e a barra piscava
  // em dois quadros. Gravando aqui, ela só aparece se o preparo realmente
  // demorar depois de a mão parar.
  inicioDoPreparo = Date.now();
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
  redesenharMarcasDeCalibracao();
  if (calibragem.ativa) return;

  // Provisório e feio de propósito: uma caixa própria é trabalho de acabamento,
  // e está registrado como dívida no fim da etapa.
  const medida = window.prompt(
    `Quanto mede essa distância na planta, em ${estado.unidade}?`, "1");
  if (medida === null) {
    calibragem = null;
    limparMarcasDeCalibracao();
    mostrarAviso(null);
    return;
  }
  try {
    estado.escala = escalaPorDoisPontos(calibragem.pontos[0]!,
                                        calibragem.pontos[1]!,
                                        medidaDigitada(medida));
    mostrarAviso(null);
  } catch (erro) {
    mostrarAviso({ titulo: "Não deu para calibrar", podeTentarDeNovo: true,
                   detalhe: erro instanceof Error ? erro.message : "" });
  }
  calibragem = null;
  limparMarcasDeCalibracao();
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
// A cota chega depois, e o canto nasce sem saldo até ela voltar: mostrar um
// número palpitado enquanto o servidor não respondeu seria inventar número.
void atualizarCota();

// --- os dois parâmetros de URL que os e-mails produzem ----------------------

/**
 * `?senha=<token>` (link de "esqueci a senha") e `?confirmado=1` (para onde
 * `GET /api/auth/confirmar/{token}` redireciona desde a tarefa 7) só existem
 * no primeiro carregamento: o parâmetro sai da URL assim que lido, com
 * `history.replaceState`. Um token de senha que fica na barra de endereços
 * entra no histórico do navegador, no título da aba e em qualquer captura de
 * tela — e ele é utilizável até vencer. O `?confirmado=1` sai pelo mesmo
 * motivo, mais simples: recarregar a página não pode repetir o aviso.
 */
const acao = acaoDaUrl(window.location.search);
if (acao) {
  // Só os dois parâmetros lidos saem — `window.location.pathname` puro
  // descartaria o resto da query e o hash, que não têm nada a ver com isto.
  const url = new URL(window.location.href);
  url.searchParams.delete("senha");
  url.searchParams.delete("confirmado");
  history.replaceState(null, "", url);
}
if (acao?.tipo === "nova-senha") {
  tokenDeSenha = acao.token;
  abrirConta("nova-senha");
} else if (acao?.tipo === "confirmado") {
  mostrarAviso({
    titulo: "E-mail confirmado",
    detalhe: "Seu endereço foi confirmado e a cota maior já está valendo.",
    podeTentarDeNovo: false,
  });
}
