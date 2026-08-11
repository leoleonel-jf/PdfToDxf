/**
 * A lista do que desenhar, preparada uma vez.
 *
 * A regra que este arquivo serve: nada proporcional ao número de entidades pode
 * acontecer a cada quadro. Preparar a lista **é** proporcional, e é caro — por
 * isso acontece uma vez, fatiado entre quadros, e não a cada quadro.
 *
 * Duas escolhas que parecem detalhe e não são:
 *
 * - **A lista cobre uma janela, não a folha inteira.** Com regiões do tamanho
 *   de poucos pixels, a folha inteira no zoom fechado teria mais regiões do que
 *   entidades: o teto não cortaria nada e a lista voltaria ao tamanho da planta.
 * - **A ordem de percurso é a de comprimento decrescente.** É o que faz o traço
 *   que mais se vê ocupar a vaga da região, em vez de quem chegar primeiro.
 */
import { coordenadasDe, type Geometria } from "./formato.js";
import { SEGMENTO } from "./select.js";
import { janelaVisivel, type Retangulo, type Vista } from "./canvas.js";

/**
 * Os três números que trocam qualidade de desenho por velocidade.
 *
 * Escolhidos medindo, em 2026-08-09 — a varredura completa está em
 * `medicao/RESULTADO.md`. O spec tinha fixado 4 px e teto 4 a partir de um
 * protótipo; medido com a implementação de verdade, esse par dá 143 ms por
 * quadro com a folha à vista, e este dá 31 ms.
 *
 * Não são ótimos, e o RESULTADO explica por quê: o custo do quadro segue a
 * **tinta** rasterizada, não a contagem de entidades, e estes três parâmetros
 * só controlam contagem. Teto 1 seria mais rápido (10 ms) e mostraria 7.100 de
 * 3 milhões de entidades — rápido demais para ser bonito. O ajuste fino espera
 * planta real na tela, que é quando qualidade pode ser vista em vez de suposta.
 */
export const LADO_REGIAO_PX = 8;
export const TETO_POR_REGIAO = 2;
export const FOLGA_DA_JANELA = 0.25;
export const FATOR_DE_ZOOM = 2;

/** 1 pt = 1/72 pol = 25,4/72 mm. `length_um` está em micrômetros de papel. */
export const UM_POR_PONTO = (25.4 / 72) * 1000;

export type Preparo = {
  janela: Retangulo;
  escala: number;
  lista: Uint32Array;
  quantos: number;
  cursor: number;
  pronto: boolean;
  // Privados na prática; ficam no objeto para o preparo ser retomável sem que
  // `lista.ts` guarde estado próprio entre chamadas.
  ocupacao: Uint8Array;
  colunas: number;
  linhas: number;
  ladoPt: number;
  tetoPorRegiao: number;
};

/**
 * O lado da região e o teto são parâmetros, não constantes fixas no laço,
 * porque a página de medição varre combinações numa carga só. Comparar entre
 * cargas diferentes não presta numa máquina ocupada — e foi o que aconteceu na
 * primeira tentativa, registrada no RESULTADO.md.
 */
export function iniciarPreparo(g: Geometria, janela: Retangulo, escala: number,
                               ladoPx = LADO_REGIAO_PX,
                               tetoPorRegiao = TETO_POR_REGIAO): Preparo {
  const ladoPt = ladoPx / escala;
  const colunas = Math.max(1, Math.ceil((janela.x1 - janela.x0) / ladoPt));
  const linhas = Math.max(1, Math.ceil((janela.y1 - janela.y0) / ladoPt));
  const teto = colunas * linhas * tetoPorRegiao;
  return {
    janela, escala,
    // A lista nunca passa de `teto`, e nunca precisa de mais vagas que
    // entidades. `Math.min` evita reservar dezenas de megabytes numa página
    // pequena vista de muito perto.
    lista: new Uint32Array(Math.min(teto, g.n)),
    quantos: 0,
    cursor: 0,
    pronto: g.n === 0,
    ocupacao: new Uint8Array(colunas * linhas),
    colunas, linhas, ladoPt, tetoPorRegiao,
  };
}

/**
 * Consome no máximo `orcamento` entidades da ordem e devolve o preparo
 * adiantado. O resultado não depende de como o orçamento foi dividido: o
 * percurso é sempre o mesmo e o cursor só anda para a frente.
 */
export function avancarPreparo(p: Preparo, g: Geometria, mascara: Uint8Array,
                               ordem: Uint32Array, orcamento: number): Preparo {
  const fim = Math.min(ordem.length, p.cursor + orcamento);
  for (let k = p.cursor; k < fim; k++) {
    const i = ordem[k]!;
    if (!mascara[i]) continue;
    const c = coordenadasDe(g, i);
    if (c.length < 2) continue;

    // O ponto de referência é o primeiro da entidade. Basta: a região existe
    // para espalhar o traço pela folha, não para recortá-lo com precisão — quem
    // recorta é o `desenharLote`, pela caixa inteira.
    const x = c[0]!, y = c[1]!;
    if (x < p.janela.x0 || x > p.janela.x1 ||
        y < p.janela.y0 || y > p.janela.y1) continue;

    if (p.quantos >= p.lista.length) continue;

    // Quem não é segmento entra sempre, sem disputar vaga: texto, arco,
    // polilinha e curva são poucos e são a leitura do desenho. Deixá-los
    // competir faria uma cota sumir junto de mil tracinhos de hachura.
    if (g.kind[i] !== SEGMENTO) {
      p.lista[p.quantos++] = i;
      continue;
    }

    let coluna = Math.floor((x - p.janela.x0) / p.ladoPt);
    let linha = Math.floor((y - p.janela.y0) / p.ladoPt);
    if (coluna < 0) coluna = 0; else if (coluna >= p.colunas) coluna = p.colunas - 1;
    if (linha < 0) linha = 0; else if (linha >= p.linhas) linha = p.linhas - 1;

    const regiao = linha * p.colunas + coluna;
    if (p.ocupacao[regiao]! >= p.tetoPorRegiao) continue;
    p.ocupacao[regiao]!++;
    p.lista[p.quantos++] = i;
  }
  p.cursor = fim;
  p.pronto = fim >= ordem.length;
  return p;
}

/** O preparo inteiro, de uma vez. O teste compara este com o fatiado. */
export function prepararTudo(g: Geometria, mascara: Uint8Array,
                             ordem: Uint32Array, janela: Retangulo,
                             escala: number, ladoPx = LADO_REGIAO_PX,
                             tetoPorRegiao = TETO_POR_REGIAO): Preparo {
  const p = iniciarPreparo(g, janela, escala, ladoPx, tetoPorRegiao);
  return avancarPreparo(p, g, mascara, ordem, ordem.length);
}

/**
 * A vista saiu do que a lista cobre?
 *
 * Duas razões, e as duas importam: o zoom passou da faixa do fator 2, ou o
 * retângulo visível deixou de caber na janela preparada.
 */
export function precisaPreparar(p: Preparo, v: Vista, larguraTela: number,
                                alturaTela: number): boolean {
  const razao = v.escala / p.escala;
  if (razao >= FATOR_DE_ZOOM || razao <= 1 / FATOR_DE_ZOOM) return true;
  // Pelo `janelaVisivel`, e não por uma conta própria: a versão que refazia a
  // aritmética aqui ficou para trás quando o eixo Y passou a ser invertido, e
  // o defeito só apareceu porque três testes o pegaram. Uma conta, um lugar.
  const agora = janelaVisivel(v, larguraTela, alturaTela, 0);
  return agora.x0 < p.janela.x0 || agora.y0 < p.janela.y0 ||
         agora.x1 > p.janela.x1 || agora.y1 > p.janela.y1;
}
