/**
 * O painel lateral: a máquina de estado aqui, o DOM logo abaixo.
 *
 * A parte pura fica separada porque é ela que dá para testar: o vitest deste
 * projeto roda com `environment: "node"` e não tem `document`. O que monta
 * elemento é coberto pelo Playwright.
 */

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
