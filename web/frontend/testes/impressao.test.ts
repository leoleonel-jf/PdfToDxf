import { describe, expect, it } from "vitest";
import { hashHex, sinaisEmTexto } from "../src/impressao.js";

const SINAIS = {
  agente: "Mozilla/5.0 (Windows NT 10.0)",
  idioma: "pt-BR",
  tela: "1920x1080x24",
  fuso: "America/Sao_Paulo",
  nucleos: 8,
  canvas: "abc123",
};

describe("impressao.ts", () => {
  it("o texto dos sinais é estável e determinístico", () => {
    expect(sinaisEmTexto(SINAIS)).toBe(sinaisEmTexto({ ...SINAIS }));
    expect(sinaisEmTexto(SINAIS)).toContain("pt-BR");
  });

  it("mudar qualquer sinal muda o texto", () => {
    expect(sinaisEmTexto({ ...SINAIS, nucleos: 4 }))
      .not.toBe(sinaisEmTexto(SINAIS));
  });

  it("o hash sai com 64 hexadecimais minúsculos", async () => {
    const h = await hashHex(sinaisEmTexto(SINAIS));
    expect(h).toMatch(/^[0-9a-f]{64}$/);
    expect(await hashHex(sinaisEmTexto(SINAIS))).toBe(h);
  });

  it("o mesmo hash conhecido, para o formato não mudar por acidente", async () => {
    // SHA-256 de "abc" — se este valor mudar, `hashHex` mudou de algoritmo ou
    // de codificação, e todo balde de impressão do servidor viraria outro.
    expect(await hashHex("abc")).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});
