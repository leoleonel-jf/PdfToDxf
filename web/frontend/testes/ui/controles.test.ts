import { describe, expect, it } from "vitest";
import { formatarComCasas } from "../../src/ui/controles.js";

/**
 * Só `formatarComCasas` tem teste aqui: o resto de `controles.ts` usa
 * `document.createElement`, e `vite.config.ts` roda os testes em `node`, sem
 * DOM. Importar o módulo não estoura porque nenhuma dessas chamadas acontece
 * no topo do arquivo — só dentro das funções que montam elementos.
 */
describe("formatarComCasas", () => {
  it("o campo de mm quer no mínimo 2 casas", () => {
    expect(formatarComCasas(0.5, 2)).toBe("0,50");
    expect(formatarComCasas(0, 2)).toBe("0,00");
    expect(formatarComCasas(1.005, 2)).toMatch(/^1,0[01]$/); // ponto flutuante
  });

  it("o separador é vírgula, e não ponto", () => {
    // O campo aceita "0,50" na entrada. Mostrar "0.50" na saída ensinaria o
    // separador errado bem no lugar onde o usuário vai digitar, e destoaria do
    // resto da tela, que já formata com vírgula ("4,1 MB").
    expect(formatarComCasas(0.5, 2)).not.toContain(".");
  });

  it("a escala 1:N quer inteiro, sem casa nem separador", () => {
    expect(formatarComCasas(50, 0)).toBe("50");
    expect(formatarComCasas(27.6, 0)).toBe("28");
  });
});
