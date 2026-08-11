/**
 * Resumo por camada: quantas entidades tem e qual a cor predominante.
 *
 * Calculado no navegador, dos vetores `layer_id` e `cor` que o binário já
 * carrega. Nada disso vem do `meta.json` — e não precisa vir: o dado já está
 * aqui, e pedi-lo ao servidor seria fazer o Python calcular duas vezes o que o
 * cliente tem em mãos.
 */
import type { Geometria } from "./formato.js";

export type ResumoDeCamada = {
  indice: number;
  nome: string;
  n: number;
  /** 0xRRGGBB. Zero quando a camada não tem nenhuma entidade. */
  cor: number;
};

export function resumoDasCamadas(g: Geometria): ResumoDeCamada[] {
  const contagem = new Uint32Array(g.layers.length);
  const cores: Array<Map<number, number>> = [];
  for (let i = 0; i < g.layers.length; i++) cores.push(new Map());

  const n = g.layer_id.length;
  for (let i = 0; i < n; i++) {
    const lid = g.layer_id[i]!;
    // Layer fora da tabela seria arquivo corrompido; ignorar é melhor do que
    // estourar e deixar a tela sem lista nenhuma.
    if (lid >= contagem.length) continue;
    contagem[lid]!++;
    const tabela = cores[lid]!;
    const c = g.cor[i]!;
    tabela.set(c, (tabela.get(c) ?? 0) + 1);
  }

  return g.layers.map((nome, indice) => ({
    indice,
    nome,
    n: contagem[indice]!,
    cor: predominante(cores[indice]!),
  }));
}

/**
 * A cor mais frequente; empate resolve pela menor.
 *
 * O desempate não é capricho. Sem ele o vencedor sairia da ordem de iteração do
 * `Map`, que é a ordem de inserção — e a mesma planta é carregada duas vezes,
 * primeiro só o esqueleto e depois inteira. A bolinha da camada mudaria de cor
 * sozinha entre uma carga e outra, o que parece defeito.
 */
function predominante(tabela: Map<number, number>): number {
  let melhor = 0;
  let quantas = -1;
  for (const [cor, n] of tabela) {
    if (n > quantas || (n === quantas && cor < melhor)) {
      melhor = cor;
      quantas = n;
    }
  }
  return melhor;
}

/**
 * Quanto da página é repetição, em porcentagem inteira. `null` se não há nada.
 *
 * Sai de graça: o `classify()` já agrupou as duplicatas em `dup_group`, e
 * `n_groups` é quantos grupos existem. Entidades menos grupos é quanta coisa é
 * cópia de alguém.
 *
 * Numa planta do acervo isto dá 60%, e é esse número que faz "remover
 * duplicados" deixar de ser um palpite para quem olha a tela.
 */
export function proporcaoRepetida(g: Geometria): number | null {
  const n = g.layer_id.length;
  if (n === 0 || g.n_groups <= 0) return null;
  return Math.round((1 - g.n_groups / n) * 100);
}

/** Acima disto a busca de camadas aparece. Abaixo, seria só ruído. */
export const CAMADAS_PARA_BUSCA = 15;

export function precisaDeBusca(quantasCamadas: number): boolean {
  return quantasCamadas > CAMADAS_PARA_BUSCA;
}
