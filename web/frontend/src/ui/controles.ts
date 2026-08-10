/**
 * Os poucos componentes da tela, montados na mão.
 *
 * `document.createElement` e não `innerHTML`: nome de camada vem do PDF do
 * usuário, e montar HTML com string faria de um layer chamado `<img onerror=…>`
 * um vetor de injeção. O texto vai por `textContent`, sempre.
 */
import { caminho } from "./icones.js";
import { medidaDigitada } from "../calibrate.js";
import { porcentagem, tempoDecorrido, type Progresso } from "../progresso.js";

const SVG = "http://www.w3.org/2000/svg";

export function criarIcone(nome: string): SVGSVGElement {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "icone");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(SVG, "path");
  p.setAttribute("d", caminho(nome));
  svg.append(p);
  return svg;
}

export function criarBotao(o: {
  rotulo: string; icone?: string; classe?: string; teste?: string;
  titulo?: string; aoClicar: () => void;
}): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `botao${o.classe ? ` ${o.classe}` : ""}`;
  if (o.teste) b.dataset["teste"] = o.teste;
  if (o.icone) b.append(criarIcone(o.icone));
  const texto = document.createElement("span");
  texto.textContent = o.rotulo;
  b.append(texto);
  if (o.titulo) b.title = o.titulo;
  b.addEventListener("click", o.aoClicar);
  return b;
}

/**
 * Interruptor com nome e uma linha explicando o efeito.
 *
 * É `<button aria-pressed>` e não `<input type=checkbox>` porque o rótulo tem
 * duas linhas com estilos diferentes, e porque `aria-pressed` é o que o resto
 * da tela já usa — um vocabulário só para leitor de tela.
 */
export function criarInterruptor(o: {
  nome: string; explica: string; ligado: boolean; teste: string;
  aoMudar: () => void;
}): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "interruptor";
  b.dataset["teste"] = o.teste;
  b.setAttribute("aria-pressed", String(o.ligado));

  const trilho = document.createElement("span");
  trilho.className = "trilho";
  const botaozinho = document.createElement("span");
  botaozinho.className = "botaozinho";
  trilho.append(botaozinho);

  const textos = document.createElement("span");
  const nome = document.createElement("span");
  nome.className = "nome";
  nome.textContent = o.nome;
  const explica = document.createElement("span");
  explica.className = "explica";
  explica.textContent = o.explica;
  textos.append(nome, explica);

  b.append(trilho, textos);
  b.addEventListener("click", o.aoMudar);
  return b;
}

/**
 * O valor do campo, formatado com o número de casas decimais pedido.
 *
 * Com vírgula, que é como se escreve decimal em português — e é o que o resto
 * da tela já faz ("4,1 MB", "1 pt de papel = 1 cm real"). Mostrar `0.00` num
 * campo que aceita `0,50` seria ensinar o separador errado bem no lugar onde o
 * usuário vai digitar.
 *
 * Extraída como função pura porque é a única parte de `criarCampoComUnidade`
 * capaz de ter teste em Node: o resto usa `document.createElement`, e o
 * ambiente de teste (`vite.config.ts`) roda sem DOM.
 */
export function formatarComCasas(valor: number, casas: number): string {
  return valor.toFixed(casas).replace(".", ",");
}

/**
 * Campo numérico com unidade ao lado.
 *
 * `type="text"` com `inputmode="decimal"`, e não `type="number"`: o campo
 * nativo tem setinhas que cobrem o texto num campo estreito, e não aceita
 * vírgula — o jeito como um usuário brasileiro digita decimal. A leitura
 * reaproveita `medidaDigitada`, que troca a vírgula por ponto antes de
 * `Number()`.
 */
export function criarCampoComUnidade(o: {
  valor: number; unidade: string; rotulo: string; teste: string;
  casas?: number; aoMudar: (v: number) => void;
}): HTMLElement {
  const casas = o.casas ?? 0;
  const caixa = document.createElement("label");
  caixa.className = "com-unidade apoio";

  const rotulo = document.createElement("span");
  rotulo.textContent = o.rotulo;

  const campo = document.createElement("input");
  campo.type = "text";
  campo.inputMode = "decimal";
  campo.className = "campo";
  campo.value = formatarComCasas(o.valor, casas);
  campo.dataset["teste"] = o.teste;
  campo.addEventListener("change", () => {
    // Entrada vazia ou inválida cai para 0, como o campo `type="number"` já
    // fazia: `medidaDigitada` devolve `NaN`, e `NaN || 0` é `0`.
    o.aoMudar(Math.max(0, medidaDigitada(campo.value) || 0));
  });

  const unidade = document.createElement("span");
  unidade.textContent = o.unidade;

  caixa.append(rotulo, campo, unidade);
  return caixa;
}

/**
 * A barra, determinada ou não.
 *
 * `<div role="progressbar">` e não `<progress>`: o elemento nativo não aceita o
 * tratamento visual do resto da tela sem gambiarra por navegador, e os
 * atributos `aria-value*` dão ao leitor de tela exatamente a mesma informação.
 *
 * Sem porcentagem, o rótulo mostra o tempo decorrido — que é verdade, ao
 * contrário de qualquer previsão que se pudesse inventar.
 *
 * O `detalhe` é a linha que explica a espera ("Plantas grandes levam alguns
 * minutos"): numa espera de minutos, uma barra sozinha não diz por quê.
 */
export function criarBarraDeProgresso(p: Progresso, rotulo: string,
                                      agora: number,
                                      detalhe?: string): HTMLElement {
  const caixa = document.createElement("div");
  caixa.className = "progresso";
  caixa.dataset["teste"] = "progresso";

  const linha = document.createElement("div");
  linha.className = "apoio";
  const texto = document.createElement("span");
  texto.textContent = rotulo;
  const valor = document.createElement("span");
  valor.className = "secundario";
  linha.append(texto, valor);

  const trilho = document.createElement("div");
  trilho.className = "progresso-trilho";
  trilho.setAttribute("role", "progressbar");
  trilho.setAttribute("aria-label", rotulo);
  const trecho = document.createElement("div");
  trecho.className = "progresso-trecho";
  trilho.append(trecho);

  caixa.append(linha, trilho);
  if (detalhe) {
    const explica = document.createElement("p");
    explica.className = "explica";
    explica.textContent = detalhe;
    caixa.append(explica);
  }
  atualizarBarraDeProgresso(caixa, p, agora);
  return caixa;
}

/**
 * O tique seguinte, escrito nos nós que já existem.
 *
 * Recriar a barra a cada tique é o que arrancava o botão de cancelar debaixo do
 * dedo: num envio de verdade o navegador dispara progresso a cada ~50 ms, e
 * entre o `mousedown` e o `mouseup` de um clique humano — 60 a 120 ms — o nó
 * seria trocado e o clique morreria no elemento antigo. Aqui só mudam a
 * largura do trecho, o texto da porcentagem e o `aria-valuenow`.
 */
export function atualizarBarraDeProgresso(caixa: HTMLElement, p: Progresso,
                                          agora: number): void {
  const valor = caixa.querySelector<HTMLElement>(".secundario");
  const trilho = caixa.querySelector<HTMLElement>(".progresso-trilho");
  const trecho = caixa.querySelector<HTMLElement>(".progresso-trecho");
  if (!valor || !trilho || !trecho) return;

  const pct = porcentagem(p);
  valor.textContent = pct !== null
    ? `${pct}%`
    : p.tipo === "indeterminado" ? tempoDecorrido(p.desde, agora) : "";

  if (pct !== null) {
    trilho.setAttribute("aria-valuemin", "0");
    trilho.setAttribute("aria-valuemax", "100");
    trilho.setAttribute("aria-valuenow", String(pct));
    trecho.className = "progresso-trecho";
    trecho.style.width = `${pct}%`;
    return;
  }
  // Sem porcentagem não há `aria-valuenow`: um leitor de tela que ouvisse "0%"
  // de uma barra indeterminada estaria ouvindo um número inventado.
  trilho.removeAttribute("aria-valuemin");
  trilho.removeAttribute("aria-valuemax");
  trilho.removeAttribute("aria-valuenow");
  trecho.className = "progresso-trecho indeterminado";
  trecho.style.width = "";
}
