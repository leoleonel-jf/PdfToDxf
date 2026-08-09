/**
 * As duas faixas do cabeçalho.
 *
 * Sem framework: os elementos são criados na mão e o estado mora num objeto só.
 * A lista de componentes é curta demais para justificar dependência.
 */
import type { Unidade } from "./calibrate.js";
import type { Opcoes } from "./select.js";

export type EstadoDaTela = {
  opcoes: Opcoes;
  layersDesligados: Set<string>;
  escala: number;
  unidade: Unidade;
  parcial: boolean;
  bytes: number;
  /** A página inteira, sem nenhuma compactação e com todas as camadas. */
  bytesBase: number;
};

/**
 * As opções como o servidor as espera.
 *
 * `sort()` não é enfeite: o servidor ordena os layers ao montar a chave do
 * cache de exportação. Mandar em outra ordem geraria a mesma planta duas vezes
 * no disco — e, na etapa 4, dois downloads na cota.
 */
export function opcoesEfetivas(e: EstadoDaTela): Opcoes {
  return { ...e.opcoes, excluded_layers: [...e.layersDesligados].sort() };
}

export function formatarBytes(bytes: number): string {
  const mb = bytes / 1_000_000;
  return mb >= 1
    ? `${mb.toFixed(1).replace(".", ",")} MB`
    : `${(bytes / 1000).toFixed(1).replace(".", ",")} kB`;
}

/**
 * O tamanho sem compactação, o tamanho atual e o quanto encolheu.
 *
 * A base é a página inteira — todas as camadas, nenhuma opção — então a
 * diferença inclui também as camadas que o usuário desligou. É de propósito:
 * ele quer saber o que aconteceu com o arquivo dele, e desligar camada é uma
 * das coisas que aconteceram.
 *
 * Abaixo de 1% a redução some da barra em vez de virar "−0%", que só ocupa
 * espaço e não informa nada.
 */
export function textoDaComparacao(bytesBase: number, bytesAtual: number,
                                  parcial: boolean): string {
  const reducao = bytesBase > 0
    ? Math.round((1 - bytesAtual / bytesBase) * 100)
    : 0;
  const texto = reducao >= 1
    ? `${formatarBytes(bytesBase)} → ${formatarBytes(bytesAtual)} · −${reducao}%`
    : formatarBytes(bytesAtual);
  return parcial ? `${texto} (parcial)` : texto;
}

