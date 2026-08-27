import { afterEach, describe, expect, it, vi } from "vitest";
import {
  acaoDaUrl, criarReleitura, horaDeLiberar, montarCaixaDeConta, proximoFocavel,
  textoDaCota, type AcoesDaCaixa,
} from "../src/conta.js";
import type { Cota } from "../src/api.js";

// `instalarDocumentoFalso` (mais abaixo) faz `vi.stubGlobal("document", ...)`
// sem `vi.restoreAllMocks` cobrir — é um stub, não um mock. Sem isto o
// `document` de mentira vazava para os testes seguintes do arquivo, no molde
// que `testes/api.test.ts` já segue para `fetch` e `XMLHttpRequest`.
afterEach(() => vi.unstubAllGlobals());

const AGORA = new Date("2026-08-21T12:00:00").getTime();

function cota(p: Partial<Cota> = {}): Cota {
  return {
    tipo: "visitante", email: "", confirmado: false,
    arquivos: { restam: 3, de: 5, libera_em: null },
    downloads: { restam: 15, de: 15, libera_em: null },
    teto_bytes: 10 * 1024 * 1024,
    ...p,
  };
}

describe("conta.ts", () => {
  it("mostra quantos arquivos restam de quantos", () => {
    expect(textoDaCota(cota(), AGORA)).toBe("3 de 5 arquivos");
  });

  it("no singular não escreve 1 arquivos", () => {
    const c = cota({ arquivos: { restam: 1, de: 5, libera_em: null } });
    expect(textoDaCota(c, AGORA)).toBe("1 de 5 arquivos");
  });

  it("esgotado diz quando libera, e não só que acabou", () => {
    const libera = AGORA / 1000 + 2 * 60 * 60 + 20 * 60;
    const c = cota({ arquivos: { restam: 0, de: 5, libera_em: libera } });
    const texto = textoDaCota(c, AGORA);
    expect(texto).toMatch(/libera/i);
    expect(texto).toMatch(/14[h:]20/);
  });

  it("sem limite não inventa número", () => {
    const c = cota({ arquivos: { restam: null, de: null, libera_em: null } });
    expect(textoDaCota(c, AGORA)).toBe("");
  });

  it("a hora de liberar sai no relógio local", () => {
    const epoch = new Date("2026-08-21T14:05:00").getTime() / 1000;
    expect(horaDeLiberar(epoch, AGORA)).toBe("14h05");
  });

  // I5: uma hora que já passou não pode ser prometida.
  it("hora de liberar no passado nao mostra hora nenhuma", () => {
    const epoch = AGORA / 1000 - 3600;
    expect(horaDeLiberar(epoch, AGORA)).toBe("");
  });

  it("cota esgotada com libera_em no passado nao promete hora que ja passou", () => {
    const epoch = AGORA / 1000 - 3600;
    const c = cota({ arquivos: { restam: 0, de: 5, libera_em: epoch } });
    const texto = textoDaCota(c, AGORA);
    expect(texto).not.toMatch(/libera às/i);
    expect(texto).toBe("sem arquivos por enquanto");
  });
});

/**
 * `acaoDaUrl` é testável em Node porque é pura — o ambiente de teste roda sem
 * DOM (`vite.config.ts`: `environment: "node"`), e ler `window.location` de
 * verdade aqui não seria possível.
 */
describe("acaoDaUrl", () => {
  it("?senha=abc devolve o token", () => {
    expect(acaoDaUrl("?senha=abc")).toEqual({ tipo: "nova-senha", token: "abc" });
  });

  it("?confirmado=1 devolve confirmado", () => {
    expect(acaoDaUrl("?confirmado=1")).toEqual({ tipo: "confirmado" });
  });

  it("string vazia devolve null", () => {
    expect(acaoDaUrl("")).toBeNull();
  });

  it("?senha= vazio devolve null", () => {
    expect(acaoDaUrl("?senha=")).toBeNull();
  });

  it("um token com caracteres de escape volta decodificado", () => {
    expect(acaoDaUrl("?senha=a%2Fb%20c")).toEqual(
      { tipo: "nova-senha", token: "a/b c" });
  });

  // Os dois juntos: `senha` ganha. É o token sensível — precisa sair da URL e
  // ser tratado agora, ou fica ali, utilizável, até vencer. `confirmado` é só
  // um aviso; perdê-lo custa uma frase, não uma conta que ninguém troca de
  // senha. Ver o comentário em `acaoDaUrl`.
  it("com os dois juntos, senha ganha de confirmado", () => {
    expect(acaoDaUrl("?senha=abc&confirmado=1")).toEqual(
      { tipo: "nova-senha", token: "abc" });
  });
});

/**
 * I4: a guarda de "em voo" da releitura de cota.
 *
 * `main.ts` chama `criarReleitura` uma vez, na carga do módulo, e usa a
 * função devolvida como `atualizarCota` — testar `criarReleitura` diretamente
 * é testar o código de produção, não uma cópia dele.
 *
 * `respostaAindaVale(sequencia, ultimoEmitido)` sozinha (`sequencia ===
 * ultimoEmitido`) não pega corrida nenhuma: qualquer implementação que
 * comparasse dois números do jeito errado passaria por `(2,2) → true` e
 * `(1,2) → false` igual. É por isso que os dois testes abaixo montam a
 * corrida de verdade — com promessas resolvidas fora de ordem — e exigem que
 * o `++` da sequência aconteça **antes** do `await`: movê-lo para depois faz
 * os dois falharem.
 */
describe("criarReleitura", () => {
  it("duas chamadas concorrentes em que a primeira resolve por ultimo: o estado final e o da segunda", async () => {
    const resolvedores: Array<(v: string) => void> = [];
    const ler = () => new Promise<string>((r) => { resolvedores.push(r); });
    const chamadas: string[] = [];
    const releitura = criarReleitura(ler, (v) => chamadas.push(v));

    // As duas chamadas começam sem esperar uma pela outra — é essa a corrida:
    // a sequência de cada uma precisa estar travada antes de qualquer `await`
    // resolver, e não no momento em que a resposta chega.
    const p1 = releitura();
    const p2 = releitura();

    // A mais nova (segunda) resolve primeiro; a mais velha (primeira) chega
    // por último — o cenário real do I4 (login aterrissando antes da leitura
    // de visitante disparada no carregamento).
    resolvedores[1]!("segunda");
    await p2;
    resolvedores[0]!("primeira");
    await p1;

    expect(chamadas).toEqual(["segunda"]);
  });

  it("uma leitura antiga que falhou (convertida em null) nao apaga o estado novo", async () => {
    const resolvedores: Array<(v: string | null) => void> = [];
    const ler = () => new Promise<string | null>((r) => { resolvedores.push(r); });
    const chamadas: Array<string | null> = [];
    const releitura = criarReleitura(ler, (v) => chamadas.push(v));

    const p1 = releitura();
    const p2 = releitura();

    resolvedores[1]!("logado");
    await p2;
    // A releitura velha (disparada antes do login) só chega depois, e o
    // servidor caiu para ela — quem chama já converteu isso em `null`. Sem a
    // guarda, este `null` sobrescreveria a conta que acabou de logar.
    resolvedores[0]!(null);
    await p1;

    expect(chamadas).toEqual(["logado"]);
  });
});

/**
 * I3 (`aria-modal="true"`): a armadilha de foco. Pura — sem DOM, com listas
 * de números — porque o único trabalho de `proximoFocavel` é decidir a borda
 * e o alvo do salto; achar os elementos focáveis de verdade é trabalho do
 * `querySelectorAll` dentro de `montarCaixaDeConta`, que só um navegador (ou
 * o e2e) exercita.
 */
describe("proximoFocavel", () => {
  const lista = [1, 2, 3];

  it("Tab no ultimo elemento volta ao primeiro", () => {
    expect(proximoFocavel(lista, 3, false)).toBe(1);
  });

  it("Shift+Tab no primeiro elemento vai ao ultimo", () => {
    expect(proximoFocavel(lista, 1, true)).toBe(3);
  });

  it("Tab fora da borda nao interfere", () => {
    expect(proximoFocavel(lista, 2, false)).toBeNull();
    expect(proximoFocavel(lista, 2, true)).toBeNull();
  });

  it("lista vazia nao interfere", () => {
    expect(proximoFocavel([], 1, false)).toBeNull();
  });

  it("elemento atual fora da lista nao interfere", () => {
    expect(proximoFocavel(lista, 9, false)).toBeNull();
  });
});

/**
 * I2 e I3 precisam montar a caixa de verdade, e `montarCaixaDeConta` usa
 * `document.createElement` sem parar — inclusive por dentro de `criarBotao`
 * (`ui/controles.ts`). Sem DOM no ambiente de teste e sem poder acrescentar
 * jsdom como dependência nova, o dublê abaixo cobre só o que a caixa usa:
 * criar elemento, `dataset`, atributos, filhos, valor de campo, foco e o
 * evento de teclado que I3 exige. Mesmo espírito do `XhrFalso` em
 * `testes/api.test.ts`.
 */
class ElementoFalso extends EventTarget {
  readonly filhos: ElementoFalso[] = [];
  readonly dataset: Record<string, string> = {};
  private readonly atributos: Record<string, string> = {};
  className = "";
  textContent = "";
  value = "";
  id = "";
  hidden = false;
  focos = 0;

  append(...nos: ElementoFalso[]): void { this.filhos.push(...nos); }
  replaceChildren(...nos: ElementoFalso[]): void {
    this.filhos.length = 0;
    this.filhos.push(...nos);
  }
  setAttribute(nome: string, valor: string): void { this.atributos[nome] = valor; }
  getAttribute(nome: string): string | null { return this.atributos[nome] ?? null; }
  focus(): void { this.focos++; }

  /** Acha um filho, em qualquer profundidade, pelo `data-teste`. */
  buscar(teste: string): ElementoFalso | null {
    for (const f of this.filhos) {
      if (f.dataset["teste"] === teste) return f;
      const achado = f.buscar(teste);
      if (achado) return achado;
    }
    return null;
  }
}

/**
 * O `document` de mentira precisa ser um `EventTarget` de verdade — desde a
 * correção do achado do Importante 1, o ouvinte de `Escape`/`Tab` mora em
 * `document`, não mais no painel, para sobreviver a um clique no véu que tira
 * o foco de dentro do formulário.
 */
class DocumentoFalso extends EventTarget {
  createElement(): ElementoFalso { return new ElementoFalso(); }
}

function instalarDocumentoFalso(): DocumentoFalso {
  const documento = new DocumentoFalso();
  vi.stubGlobal("document", documento);
  return documento;
}

function acoesFalsas(extra: Partial<AcoesDaCaixa> = {}): AcoesDaCaixa {
  return {
    aoConfirmar: () => {}, aoTrocarModo: () => {}, aoFechar: () => {},
    recado: "", erro: "", ...extra,
  };
}

function keydown(alvo: EventTarget, key: string): void {
  const e = new Event("keydown");
  Object.assign(e, { key });
  alvo.dispatchEvent(e);
}

describe("montarCaixaDeConta", () => {
  it("I2: o e-mail inicial vem preenchido e a senha vem vazia", () => {
    instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar",
      acoesFalsas({ email: "ana@exemplo.com" }));

    expect(raiz.buscar("campo-email")?.value).toBe("ana@exemplo.com");
    expect(raiz.buscar("campo-senha")?.value).toBe("");
  });

  it("I2: sem e-mail inicial o campo vem vazio", () => {
    instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar", acoesFalsas());

    expect(raiz.buscar("campo-email")?.value).toBe("");
  });

  it("I3: o painel é um dialog modal ligado ao título", () => {
    instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar", acoesFalsas());

    const painel = raiz.filhos[0]!;
    expect(painel.getAttribute("role")).toBe("dialog");
    expect(painel.getAttribute("aria-modal")).toBe("true");
    expect(painel.getAttribute("aria-labelledby")).toBeTruthy();
  });

  it("I3: Escape chama aoFechar", () => {
    const documento = instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    const aoFechar = vi.fn();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar",
      acoesFalsas({ aoFechar }));

    keydown(documento, "Escape");
    expect(aoFechar).toHaveBeenCalledTimes(1);
  });

  it("I3: uma tecla qualquer nao chama aoFechar", () => {
    const documento = instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    const aoFechar = vi.fn();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar",
      acoesFalsas({ aoFechar }));

    keydown(documento, "a");
    expect(aoFechar).not.toHaveBeenCalled();
  });

  // Importante 1: o ouvinte mora em `document`, não mais no painel — um
  // clique no véu (`.sobre-conta`, sem `tabindex`) tira o foco de dentro do
  // formulário, e um ouvinte só no painel para de ouvir exatamente aí.
  it("I3/Importante 1: Escape fecha mesmo sem foco dentro do painel", () => {
    const documento = instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    const aoFechar = vi.fn();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar",
      acoesFalsas({ aoFechar }));

    // Nada dentro do painel recebeu o evento — só `document`, como um clique
    // no véu deixaria.
    keydown(documento, "Escape");
    expect(aoFechar).toHaveBeenCalledTimes(1);
  });

  it("Importante 1: remontar N vezes nao acumula ouvintes de Escape", () => {
    const documento = instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    const aoFechar = vi.fn();
    for (let i = 0; i < 5; i++) {
      montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar",
        acoesFalsas({ aoFechar }));
    }

    keydown(documento, "Escape");
    expect(aoFechar).toHaveBeenCalledTimes(1);
  });

  it("Importante 1: Escape continua fechando depois de varias remontagens com modos diferentes", () => {
    const documento = instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    const aoFechar = vi.fn();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar", acoesFalsas({ aoFechar }));
    montarCaixaDeConta(raiz as unknown as HTMLElement, "cadastrar", acoesFalsas({ aoFechar }));
    montarCaixaDeConta(raiz as unknown as HTMLElement, "senha", acoesFalsas({ aoFechar }));

    keydown(documento, "Escape");
    expect(aoFechar).toHaveBeenCalledTimes(1);
  });

  it("Importante 1: fechar a caixa (modo null) deixa sem ouvinte de Escape nenhum", () => {
    const documento = instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    const aoFechar = vi.fn();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar", acoesFalsas({ aoFechar }));
    montarCaixaDeConta(raiz as unknown as HTMLElement, null, acoesFalsas({ aoFechar }));

    keydown(documento, "Escape");
    expect(aoFechar).not.toHaveBeenCalled();
  });

  // Menor 6: quem digita o e-mail e troca de modo sem submeter não pode
  // perder o que digitou — a mensagem "Esqueci a senha" preservando o e-mail
  // é o cenário concreto do achado.
  it("Menor 6: trocar de modo leva o e-mail digitado, nao so o submetido", () => {
    instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    const aoTrocarModo = vi.fn();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar",
      acoesFalsas({ aoTrocarModo }));

    const campoEmail = raiz.buscar("campo-email")!;
    campoEmail.value = "ana@exemplo.com";
    const irParaSenha = raiz.buscar("ir-para-senha")!;
    irParaSenha.dispatchEvent(new Event("click"));

    expect(aoTrocarModo).toHaveBeenCalledWith("senha", "ana@exemplo.com");
  });

  it("nova-senha nao tem campo de e-mail, entao o e-mail inicial nao se aplica", () => {
    instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "nova-senha",
      acoesFalsas({ email: "ana@exemplo.com" }));

    expect(raiz.buscar("campo-email")).toBeNull();
  });
});
