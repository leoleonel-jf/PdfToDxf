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

  it("as cinco linhas de erro da etapa 4 existem e são acionáveis", () => {
    const cota = avisoDoErro(new ErroDaApi(429, "sem vaga", "cota_arquivos"));
    expect(tudo(cota)).toMatch(/conta/i);   // oferece o cadastro ao visitante

    const baixar = avisoDoErro(new ErroDaApi(429, "sem vaga", "cota_downloads"));
    expect(tudo(baixar)).toMatch(/já gerou|de novo|liberado/i);

    const tamanho = avisoDoErro(new ErroDaApi(413, "grande", "tamanho"));
    expect(tudo(tamanho)).toMatch(/tamanho|MB/i);

    const naoConfirmada = avisoDoErro(
      new ErroDaApi(403, "confirme", "conta_nao_confirmada"));
    expect(tudo(naoConfirmada)).toMatch(/confirm/i);

    // A quinta é o trabalho expirado, que a etapa 3 já tinha.
    expect(tudo(avisoDoErro(new ErroDaApi(404, "sumiu")))).toMatch(/expir/i);
  });

  it("cota esgotada não conta qual balde estourou", () => {
    const a = avisoDoErro(new ErroDaApi(429, "sem vaga", "cota_arquivos"));
    expect(tudo(a).toLowerCase()).not.toMatch(/cookie|endereço ip|impressão/);
  });

  it("cota e tamanho não oferecem conta a quem já está logado", () => {
    // O conselho tem que ser possível de seguir: quem já tem conta não pode
    // ouvir "crie uma conta".
    const confirmado = { tipo: "logado" as const, confirmado: true };
    const cota = avisoDoErro(
      new ErroDaApi(429, "sem vaga", "cota_arquivos"), confirmado);
    expect(tudo(cota).toLowerCase()).not.toMatch(/conta gratuita/);
    expect(tudo(cota)).toMatch(/mais tarde|libera/i);

    const tamanho = avisoDoErro(
      new ErroDaApi(413, "grande", "tamanho"), confirmado);
    expect(tudo(tamanho).toLowerCase()).not.toMatch(/conta gratuita/);
    expect(tudo(tamanho)).toMatch(/menor|divida/i);

    // Logado sem confirmar: o que destrava o limite é a confirmação.
    const pendente = { tipo: "logado" as const, confirmado: false };
    expect(tudo(avisoDoErro(
      new ErroDaApi(429, "sem vaga", "cota_arquivos"), pendente)))
      .toMatch(/confirm/i);
    expect(tudo(avisoDoErro(
      new ErroDaApi(413, "grande", "tamanho"), pendente)))
      .toMatch(/confirm/i);

    // Visitante explícito continua recebendo a oferta, como o padrão sem cota.
    const visitante = { tipo: "visitante" as const, confirmado: false };
    expect(tudo(avisoDoErro(
      new ErroDaApi(429, "sem vaga", "cota_arquivos"), visitante)))
      .toMatch(/conta/i);
  });
});
