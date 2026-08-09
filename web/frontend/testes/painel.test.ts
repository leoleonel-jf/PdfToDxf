import { describe, expect, it } from "vitest";
import {
  abrirEm, alternar, aoRedimensionar, estadoInicial, LARGURA_DA_GAVETA,
  paraGuardar,
} from "../src/painel.js";

const LARGO = LARGURA_DA_GAVETA + 100;
const ESTREITO = LARGURA_DA_GAVETA - 1;

describe("painel.ts", () => {
  it("em tela larga sem preferência guardada, abre", () => {
    expect(estadoInicial(LARGO, null).modo).toBe("aberto");
  });

  it("em tela larga respeita a preferência guardada", () => {
    expect(estadoInicial(LARGO, "recolhido").modo).toBe("recolhido");
  });

  it("em tela estreita é gaveta, e a gaveta começa fechada", () => {
    const e = estadoInicial(ESTREITO, "recolhido");
    expect(e.modo).toBe("gaveta");
    expect(e.gavetaAberta).toBe(false);
  });

  it("alternar troca aberto e recolhido", () => {
    const a = estadoInicial(LARGO, null);
    expect(alternar(a).modo).toBe("recolhido");
    expect(alternar(alternar(a)).modo).toBe("aberto");
  });

  it("alternar na gaveta abre e fecha a gaveta, sem mudar o modo", () => {
    const g = estadoInicial(ESTREITO, null);
    expect(alternar(g)).toMatchObject({ modo: "gaveta", gavetaAberta: true });
    expect(alternar(alternar(g))).toMatchObject({ gavetaAberta: false });
  });

  it("abrir numa seção reabre o painel recolhido naquela seção", () => {
    const recolhido = alternar(estadoInicial(LARGO, null));
    const e = abrirEm(recolhido, "camadas");
    expect(e.modo).toBe("aberto");
    expect(e.secaoAtiva).toBe("camadas");
  });

  it("abrir numa seção na gaveta abre a gaveta naquela seção", () => {
    const e = abrirEm(estadoInicial(ESTREITO, null), "compactacao");
    expect(e).toMatchObject({ modo: "gaveta", gavetaAberta: true,
                              secaoAtiva: "compactacao" });
  });

  it("estreitar a janela vira gaveta e fecha o que estava aberto", () => {
    const e = aoRedimensionar(estadoInicial(LARGO, null), ESTREITO, null);
    expect(e).toMatchObject({ modo: "gaveta", gavetaAberta: false });
  });

  it("alargar de volta restaura a preferência guardada, não o padrão", () => {
    const g = alternar(estadoInicial(ESTREITO, null));   // gaveta aberta
    expect(aoRedimensionar(g, LARGO, "recolhido").modo).toBe("recolhido");
    expect(aoRedimensionar(g, LARGO, null).modo).toBe("aberto");
  });

  it("redimensionar sem cruzar o limiar não mexe em nada", () => {
    const a = estadoInicial(LARGO, null);
    expect(aoRedimensionar(a, LARGO + 1, null)).toBe(a);
  });

  it("gaveta não é preferência: não vai para o armazenamento", () => {
    expect(paraGuardar(estadoInicial(ESTREITO, null))).toBe(null);
    expect(paraGuardar(estadoInicial(LARGO, null))).toBe("aberto");
    expect(paraGuardar(alternar(estadoInicial(LARGO, null)))).toBe("recolhido");
  });
});
