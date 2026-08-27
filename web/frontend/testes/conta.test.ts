import { describe, expect, it, vi } from "vitest";
import {
  acaoDaUrl, horaDeLiberar, montarCaixaDeConta, respostaAindaVale, textoDaCota,
  type AcoesDaCaixa,
} from "../src/conta.js";
import type { Cota } from "../src/api.js";

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
 * `atualizarCota` mora em `main.ts`, que não é importável aqui — o topo do
 * arquivo faz `document.querySelector("#desenho")!` de verdade, e o ambiente
 * de teste roda sem DOM (`vite.config.ts`). A decisão em si, porém, é pura:
 * uma resposta só vale se o número de sequência que ela carrega ainda for o
 * último emitido. É essa função que o teste verifica.
 */
describe("respostaAindaVale", () => {
  it("a sequencia mais nova vale", () => {
    expect(respostaAindaVale(2, 2)).toBe(true);
  });

  it("uma sequencia antiga nao vale mais depois de uma mais nova", () => {
    expect(respostaAindaVale(1, 2)).toBe(false);
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

function instalarDocumentoFalso(): void {
  vi.stubGlobal("document", { createElement: () => new ElementoFalso() });
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
    instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    const aoFechar = vi.fn();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar",
      acoesFalsas({ aoFechar }));

    keydown(raiz.filhos[0]!, "Escape");
    expect(aoFechar).toHaveBeenCalledTimes(1);
  });

  it("I3: uma tecla qualquer nao chama aoFechar", () => {
    instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    const aoFechar = vi.fn();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "entrar",
      acoesFalsas({ aoFechar }));

    keydown(raiz.filhos[0]!, "a");
    expect(aoFechar).not.toHaveBeenCalled();
  });

  it("nova-senha nao tem campo de e-mail, entao o e-mail inicial nao se aplica", () => {
    instalarDocumentoFalso();
    const raiz = new ElementoFalso();
    montarCaixaDeConta(raiz as unknown as HTMLElement, "nova-senha",
      acoesFalsas({ email: "ana@exemplo.com" }));

    expect(raiz.buscar("campo-email")).toBeNull();
  });
});
