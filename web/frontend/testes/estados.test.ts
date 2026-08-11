import { describe, expect, it } from "vitest";
import { ErroDaApi } from "../src/api.js";
import { avisoDaSituacao, avisoDoErro } from "../src/estados.js";

/**
 * A mensagem inteira, que é o que o usuário lê.
 *
 * Verificar só o `detalhe` deixaria passar um aviso cuja informação está toda
 * no título — e era esse o defeito dos testes como vieram escritos no plano de
 * 2026-08-04: procuravam "expirou" no detalhe, onde está escrito "4 horas".
 */
function tudo(a: { titulo: string; detalhe: string }): string {
  return `${a.titulo} ${a.detalhe}`;
}

describe("estados.ts", () => {
  it("página pronta não gera aviso", () => {
    expect(avisoDaSituacao("pronta")).toBeNull();
  });

  it("na fila e extraindo dizem a mesma coisa", () => {
    // "extraindo" está no contrato da API e hoje nada o escreve; quem lê tem
    // de tratá-lo como "ainda em andamento".
    expect(avisoDaSituacao("extraindo")).toEqual(avisoDaSituacao("na_fila"));
  });

  it("cada código de erro tem mensagem própria e acionável", () => {
    for (const codigo of ["sem_vetores", "entidades_demais", "recurso", "interno"]) {
      const aviso = avisoDaSituacao("erro", codigo, "mensagem do servidor")!;
      expect(aviso.titulo.length).toBeGreaterThan(0);
      expect(aviso.detalhe.length).toBeGreaterThan(0);
    }
    expect(tudo(avisoDaSituacao("erro", "sem_vetores")!)).toMatch(/vetorial/i);
    expect(tudo(avisoDaSituacao("erro", "entidades_demais")!)).toMatch(/grande/i);
  });

  it("erro desconhecido não fica sem mensagem", () => {
    const aviso = avisoDaSituacao("erro", "codigo_que_nao_existe")!;
    expect(aviso.detalhe.length).toBeGreaterThan(0);
  });

  it("404 vira 'a planta expirou' e 413 vira 'grande demais'", () => {
    expect(tudo(avisoDoErro(new ErroDaApi(404, "não achei")))).toMatch(/expir/i);
    expect(tudo(avisoDoErro(new ErroDaApi(413, "grande")))).toMatch(/tamanho|limite/i);
  });

  it("queda de rede não vira tela em branco", () => {
    const aviso = avisoDoErro(new TypeError("Failed to fetch"));
    expect(aviso.detalhe.length).toBeGreaterThan(0);
    expect(aviso.podeTentarDeNovo).toBe(true);
  });
});
