/**
 * Os poucos componentes da tela, montados na mão.
 *
 * `document.createElement` e não `innerHTML`: nome de camada vem do PDF do
 * usuário, e montar HTML com string faria de um layer chamado `<img onerror=…>`
 * um vetor de injeção. O texto vai por `textContent`, sempre.
 */
import { caminho } from "./icones.js";
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

export function criarCampoComUnidade(o: {
  valor: number; unidade: string; rotulo: string; teste: string;
  passo?: string; aoMudar: (v: number) => void;
}): HTMLElement {
  const caixa = document.createElement("label");
  caixa.className = "com-unidade apoio";

  const rotulo = document.createElement("span");
  rotulo.textContent = o.rotulo;

  const campo = document.createElement("input");
  campo.type = "number";
  campo.className = "campo";
  campo.min = "0";
  campo.step = o.passo ?? "0.1";
  campo.value = String(o.valor);
  campo.dataset["teste"] = o.teste;
  campo.addEventListener("change", () => {
    o.aoMudar(Math.max(0, Number(campo.value) || 0));
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
 */
export function criarBarraDeProgresso(p: Progresso, rotulo: string,
                                      agora: number): HTMLElement {
  const caixa = document.createElement("div");
  caixa.className = "progresso";
  caixa.dataset["teste"] = "progresso";

  const linha = document.createElement("div");
  linha.className = "apoio";
  const texto = document.createElement("span");
  texto.textContent = rotulo;
  const valor = document.createElement("span");
  valor.className = "secundario";
  const pct = porcentagem(p);
  valor.textContent = pct !== null
    ? `${pct}%`
    : p.tipo === "indeterminado" ? tempoDecorrido(p.desde, agora) : "";
  linha.append(texto, valor);

  const trilho = document.createElement("div");
  trilho.className = "progresso-trilho";
  trilho.setAttribute("role", "progressbar");
  trilho.setAttribute("aria-label", rotulo);
  const trecho = document.createElement("div");
  if (pct !== null) {
    trilho.setAttribute("aria-valuemin", "0");
    trilho.setAttribute("aria-valuemax", "100");
    trilho.setAttribute("aria-valuenow", String(pct));
    trecho.className = "progresso-trecho";
    trecho.style.width = `${pct}%`;
  } else {
    trecho.className = "progresso-trecho indeterminado";
  }
  trilho.append(trecho);

  caixa.append(linha, trilho);
  return caixa;
}
