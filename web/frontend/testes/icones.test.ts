import { describe, expect, it } from "vitest";
import { CAMINHOS, caminho } from "../src/ui/icones.js";

const NECESSARIOS = [
  "arquivo", "regua", "ajustes", "camadas", "olho", "olho-cortado",
  "baixar", "recolher", "menu", "busca", "usuario",
];

describe("icones.ts", () => {
  it("tem exatamente os ícones que a tela usa, e nenhum a mais", () => {
    expect(Object.keys(CAMINHOS).sort()).toEqual([...NECESSARIOS].sort());
  });

  it("todo caminho é dado de path SVG começando por M", () => {
    for (const [nome, d] of Object.entries(CAMINHOS)) {
      expect(d.startsWith("M"), `${nome} não começa com M`).toBe(true);
      expect(d.length).toBeGreaterThan(10);
    }
  });

  it("pedir um ícone que não existe estoura com o nome dentro", () => {
    expect(() => caminho("inexistente")).toThrow(/inexistente/);
  });
});
