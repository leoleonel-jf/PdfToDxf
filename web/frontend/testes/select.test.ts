import { describe, expect, it } from "vitest";
import { carregarContrato, comoTexto } from "./ajuda/contrato.js";
import { selecionar } from "../src/select.js";

const { casos, tabelas } = carregarContrato();

describe("select.ts espelha optimize.select()", () => {
  it("carrega o contrato inteiro", () => {
    expect(casos.length).toBe(1024);
    expect(tabelas.length).toBe(4);
  });

  for (const caso of casos) {
    it(`caso ${caso.nome}`, () => {
      const attrs = tabelas[caso.tabela]!;
      const obtido = comoTexto(selecionar(attrs, caso.opcoes));
      if (obtido !== caso.esperado) {
        // Apontar o primeiro índice divergente: comparar duas strings de 300
        // caracteres a olho não diz nada.
        let i = 0;
        while (i < obtido.length && obtido[i] === caso.esperado[i]) i++;
        throw new Error(
          `divergiu no índice ${i}: esperado ${caso.esperado[i]}, ` +
          `obtido ${obtido[i]} (kind=${attrs.kind[i]}, ` +
          `length_um=${attrs.length_um[i]}, dup_group=${attrs.dup_group[i]})`);
      }
      expect(obtido).toBe(caso.esperado);
    });
  }
});
