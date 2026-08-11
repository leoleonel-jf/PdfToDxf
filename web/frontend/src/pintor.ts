/**
 * O laço de quadro: quem decide preparar, continuar ou só re-traçar.
 *
 * É o único arquivo desta parte com estado temporal, e é pequeno de propósito.
 * Tudo o que ele coordena — ordenar, preparar, traçar — é função pura em outro
 * lugar, testável sem relógio e sem navegador.
 */
import {
  desenharLote, janelaVisivel, type CaminhoDesenhavel,
  type ContextoDesenhavel, type Vista,
} from "./canvas.js";
import type { Geometria } from "./formato.js";
import {
  avancarPreparo, iniciarPreparo, precisaPreparar, FOLGA_DA_JANELA,
  type Preparo,
} from "./lista.js";

export type Cena = {
  g: Geometria;
  mascara: Uint8Array;
  ordem: Uint32Array;
  v: Vista;
  larguraTela: number;
  alturaTela: number;
  /** Sobe quando a máscara ou a geometria mudam. Quem muda incrementa. */
  geracao: number;
};

export type Pintor = {
  preparo: Preparo | null;
  desenhadas: number;
  geracao: number;
};

export function criarPintor(): Pintor {
  return { preparo: null, desenhadas: 0, geracao: -1 };
}

/**
 * Um quadro. Devolve `true` quando não há mais nada pendente — o preparo
 * terminou e tudo o que a lista escolheu já foi traçado ao menos uma vez.
 *
 * O `orcamento` limita as entidades processadas no preparo, não o traçado: o
 * traçado é barato justamente porque a lista já está pronta.
 */
export function passo(p: Pintor, cena: Cena, ctx: ContextoDesenhavel,
                      criarCaminho: () => CaminhoDesenhavel,
                      orcamento: number): boolean {
  const mudou = p.geracao !== cena.geracao;
  const saiu = p.preparo !== null &&
    precisaPreparar(p.preparo, cena.v, cena.larguraTela, cena.alturaTela);

  if (p.preparo === null || mudou || saiu) {
    const janela = janelaVisivel(cena.v, cena.larguraTela, cena.alturaTela,
                                 FOLGA_DA_JANELA);
    p.preparo = iniciarPreparo(cena.g, janela, cena.v.escala);
    p.geracao = cena.geracao;
    p.desenhadas = 0;
  }

  const preparo = p.preparo;
  if (!preparo.pronto) {
    avancarPreparo(preparo, cena.g, cena.mascara, cena.ordem, orcamento);
  }

  const limites = janelaVisivel(cena.v, cena.larguraTela, cena.alturaTela, 0);
  ctx.clearRect(0, 0, cena.larguraTela, cena.alturaTela);
  p.desenhadas = desenharLote(ctx, cena.g, preparo.lista, preparo.quantos,
                              cena.v, criarCaminho, limites);
  return preparo.pronto;
}
