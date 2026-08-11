/**
 * O painel lateral: a máquina de estado aqui, o DOM logo abaixo.
 *
 * A parte pura fica separada porque é ela que dá para testar: o vitest deste
 * projeto roda com `environment: "node"` e não tem `document`. O que monta
 * elemento é coberto pelo Playwright.
 */
import { criarIcone } from "./ui/controles.js";

export type Secao = "escala" | "compactacao" | "camadas";
export type ModoDoPainel = "aberto" | "recolhido" | "gaveta";

/**
 * Abaixo disto o painel vira gaveta sobre o desenho.
 *
 * 900 px porque com o painel de 260 px sobra menos de 640 px de planta, que é
 * pouco para enxergar qualquer coisa numa A3 deitada.
 */
export const LARGURA_DA_GAVETA = 900;

export type EstadoDoPainel = {
  modo: ModoDoPainel;
  gavetaAberta: boolean;
  secaoAtiva: Secao;
};

export function estadoInicial(larguraDaJanela: number,
                              guardado: string | null): EstadoDoPainel {
  if (larguraDaJanela < LARGURA_DA_GAVETA) {
    return { modo: "gaveta", gavetaAberta: false, secaoAtiva: "escala" };
  }
  return {
    modo: guardado === "recolhido" ? "recolhido" : "aberto",
    gavetaAberta: false,
    secaoAtiva: "escala",
  };
}

/** O botão do canto: recolhe no desktop, abre e fecha a gaveta no celular. */
export function alternar(e: EstadoDoPainel): EstadoDoPainel {
  if (e.modo === "gaveta") return { ...e, gavetaAberta: !e.gavetaAberta };
  return { ...e, modo: e.modo === "aberto" ? "recolhido" : "aberto" };
}

/**
 * Clicar no ícone de uma seção com o painel recolhido reabre **naquela** seção.
 *
 * É o que justifica o modo recolhido mostrar ícones em vez de sumir: sem eles o
 * usuário perderia a orientação de onde as coisas estão.
 */
export function abrirEm(e: EstadoDoPainel, secao: Secao): EstadoDoPainel {
  if (e.modo === "gaveta") {
    return { ...e, secaoAtiva: secao, gavetaAberta: true };
  }
  return { ...e, secaoAtiva: secao, modo: "aberto" };
}

/**
 * Reage à janela mudando de tamanho, sem esquecer a preferência.
 *
 * Voltar da gaveta para "aberto" fixo apagaria a escolha de quem trabalha
 * recolhido: bastaria girar o tablet para perder o ajuste. Por isso a
 * preferência guardada entra de novo aqui.
 */
export function aoRedimensionar(e: EstadoDoPainel, larguraDaJanela: number,
                                guardado: string | null): EstadoDoPainel {
  const estreito = larguraDaJanela < LARGURA_DA_GAVETA;
  if (estreito) {
    if (e.modo === "gaveta") return e;
    return { ...e, modo: "gaveta", gavetaAberta: false };
  }
  if (e.modo !== "gaveta") return e;
  return {
    ...e,
    modo: guardado === "recolhido" ? "recolhido" : "aberto",
    gavetaAberta: false,
  };
}

/**
 * O que gravar. `null` quer dizer "não grave nada".
 *
 * Gaveta é consequência da largura da tela, não escolha do usuário: gravá-la
 * faria o desktop abrir em gaveta só porque a última visita foi no celular.
 */
export function paraGuardar(e: EstadoDoPainel): string | null {
  return e.modo === "gaveta" ? null : e.modo;
}

// --- o DOM --------------------------------------------------------------

const ICONE_DA_SECAO: Record<Secao, string> = {
  escala: "regua",
  compactacao: "ajustes",
  camadas: "camadas",
};

const NOME_DA_SECAO: Record<Secao, string> = {
  escala: "Escala",
  compactacao: "Compactação",
  camadas: "Camadas",
};

export type ConteudoDasSecoes = Record<Secao, () => HTMLElement>;

export function montarPainel(raiz: HTMLElement, e: EstadoDoPainel,
                             conteudo: ConteudoDasSecoes,
                             aoAlternar: () => void,
                             aoAbrirEm: (s: Secao) => void): void {
  raiz.replaceChildren();
  raiz.dataset["modo"] = e.modo;
  raiz.hidden = e.modo === "gaveta" && !e.gavetaAberta;

  const recolher = document.createElement("button");
  recolher.type = "button";
  recolher.className = "botao discreto";
  recolher.dataset["teste"] = "recolher-painel";
  recolher.setAttribute("aria-label",
                        e.modo === "recolhido" ? "Abrir opções" : "Recolher opções");
  recolher.append(criarIcone("recolher"));
  recolher.addEventListener("click", aoAlternar);
  raiz.append(recolher);

  // No modo recolhido, só os três ícones — e clicar num deles reabre o painel
  // já naquela seção. É o que impede o usuário de perder a orientação.
  for (const secao of ["escala", "compactacao", "camadas"] as Secao[]) {
    const atalho = document.createElement("button");
    atalho.type = "button";
    atalho.className = "botao discreto atalho";
    atalho.dataset["teste"] = `atalho-${secao}`;
    atalho.setAttribute("aria-label", NOME_DA_SECAO[secao]);
    atalho.title = NOME_DA_SECAO[secao];
    atalho.append(criarIcone(ICONE_DA_SECAO[secao]));
    atalho.addEventListener("click", () => aoAbrirEm(secao));
    raiz.append(atalho);

    const bloco = document.createElement("section");
    bloco.className = "secao";
    bloco.dataset["teste"] = `secao-${secao}`;
    const cabecalho = document.createElement("header");
    const titulo = document.createElement("span");
    titulo.className = "rotulo";
    titulo.textContent = NOME_DA_SECAO[secao];
    cabecalho.append(titulo);
    bloco.append(cabecalho, conteudo[secao]());
    raiz.append(bloco);
  }
}
