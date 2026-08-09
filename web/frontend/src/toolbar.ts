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
  sobreviventes: number;
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

export function textoDaEstimativa(bytes: number, parcial: boolean): string {
  const mb = bytes / 1_000_000;
  const texto = mb >= 1
    ? `≈ ${mb.toFixed(1).replace(".", ",")} MB`
    : `≈ ${(bytes / 1000).toFixed(1).replace(".", ",")} kB`;
  return parcial ? `${texto} (parcial)` : texto;
}

const OPCOES_DE_COMPACTACAO: Array<{ chave: keyof Opcoes; rotulo: string }> = [
  { chave: "join_polylines", rotulo: "Unir em polilinhas" },
  { chave: "round_coords", rotulo: "Arredondar coordenadas" },
  { chave: "dedup", rotulo: "Remover duplicados" },
  { chave: "drop_fills", rotulo: "Remover preenchimentos" },
];

function botaoLigavel(rotulo: string, ligado: boolean,
                      aoClicar: () => void): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = "botao";
  b.type = "button";
  b.textContent = rotulo;
  b.setAttribute("aria-pressed", String(ligado));
  b.addEventListener("click", aoClicar);
  return b;
}

/** Preenche a faixa 2 com as opções e os chips de layer. */
export function montarFaixaDeOpcoes(raiz: HTMLElement, e: EstadoDaTela,
                                    layers: string[], aoMudar: () => void): void {
  raiz.replaceChildren();

  for (const { chave, rotulo } of OPCOES_DE_COMPACTACAO) {
    raiz.append(botaoLigavel(rotulo, Boolean(e.opcoes[chave]), () => {
      (e.opcoes[chave] as boolean) = !e.opcoes[chave];
      aoMudar();
    }));
  }

  const campo = document.createElement("input");
  campo.type = "number";
  campo.min = "0";
  campo.step = "0.1";
  campo.className = "botao";
  campo.style.width = "8ch";
  campo.value = String(e.opcoes.min_len_mm);
  campo.setAttribute("aria-label", "Descartar segmentos abaixo de N mm");
  campo.addEventListener("change", () => {
    e.opcoes.min_len_mm = Math.max(0, Number(campo.value) || 0);
    aoMudar();
  });
  raiz.append(campo);

  const separador = document.createElement("span");
  separador.className = "separador";
  raiz.append(separador);

  for (const layer of layers) {
    raiz.append(botaoLigavel(layer, !e.layersDesligados.has(layer), () => {
      if (e.layersDesligados.has(layer)) e.layersDesligados.delete(layer);
      else e.layersDesligados.add(layer);
      aoMudar();
    }));
  }
}
