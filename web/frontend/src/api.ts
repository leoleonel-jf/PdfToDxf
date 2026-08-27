/**
 * Cliente HTTP das rotas da etapa 2.
 *
 * Todo pedido aceita um `AbortSignal`. Não é enfeite: trocar de página no meio
 * do carregamento deixa buscas em voo, e o detalhe da página anterior chegando
 * depois contamina o canvas da página nova — defeito silencioso, que só aparece
 * com rede lenta.
 */

import { coletar } from "./impressao.js";

export class ErroDaApi extends Error {
  constructor(public readonly status: number, mensagem: string,
              public readonly codigo = "") {
    super(mensagem);
    this.name = "ErroDaApi";
  }
}

export type Ficha = { job_id: string; nome: string; n_paginas: number };

export type EstadoPagina = {
  situacao: "na_fila" | "extraindo" | "pronta" | "erro";
  codigo?: string;
  mensagem?: string;
  n_entidades?: number;
};

export type Meta = {
  n_entidades: number;
  layers: string[];
  largura_pt: number;
  altura_pt: number;
  limiar_esqueleto_um: number;
  partes: { esqueleto: number; detalhe: number };
};

export type PedidoDeExportacao = {
  escala: number;
  unidade: "mm" | "cm" | "m";
  opcoes: {
    excluded_layers: string[];
    drop_fills: boolean;
    min_len_mm: number;
    dedup: boolean;
    join_polylines: boolean;
    round_coords: boolean;
  };
};

/**
 * A recusa do servidor virando erro da tela — em um lugar só.
 *
 * O `pedir` e o `enviarPdf` mapeavam isto separado, e o envio é o único caminho
 * por onde o PDF entra: uma recusa nova escrita só no `pedir` deixaria de fora
 * justamente a porta de entrada.
 */
/**
 * As mensagens legíveis de um `detail` de validação (FastAPI/Pydantic).
 *
 * Nesse formato `detail` não é texto, é uma lista de erros — um por campo —,
 * cada um com `msg` explicando o que houve. `String(lista)` não lê nada disso:
 * ele chama `toString()` de cada item, e um objeto sem `toString()` próprio
 * vira literalmente `"[object Object]"`. Devolve `null` quando a lista não tem
 * nenhum `msg` legível, para quem chama cair no status como antes.
 */
function mensagensDaListaDeErros(lista: unknown[]): string | null {
  const msgs = lista
    .map((item) => item && typeof item === "object" && "msg" in item
      ? String((item as { msg: unknown }).msg) : null)
    .filter((m): m is string => Boolean(m));
  return msgs.length > 0 ? msgs.join("; ") : null;
}

function erroDaRecusa(status: number, corpoCru: string): ErroDaApi {
  let detalhe = `HTTP ${status}`;
  // O `codigo` da recusa, quando o servidor mandou um. `ErroDaApi` já tinha o
  // campo desde a etapa 3, com `""` de padrão, esperando alguém preenchê-lo: é
  // por ele que a tela distingue uma recusa da outra sem ler texto de mensagem
  // — texto muda, código não. Sai do mesmo `JSON.parse` do detalhe, porque é o
  // mesmo corpo: `Recusa` põe os dois lado a lado na raiz (`main.py:343`).
  let codigo = "";
  try {
    const corpo = JSON.parse(corpoCru);
    if (Array.isArray(corpo?.detail)) {
      detalhe = mensagensDaListaDeErros(corpo.detail) ?? detalhe;
    } else if (corpo?.detail) {
      detalhe = String(corpo.detail);
    }
    if (typeof corpo?.codigo === "string") codigo = corpo.codigo;
  } catch {
    // Resposta sem JSON: fica o status, que já diz o suficiente.
  }
  return new ErroDaApi(status, detalhe, codigo);
}

async function pedir(caminho: string, init: RequestInit = {}): Promise<Response> {
  const resposta = await fetch(caminho, init);
  if (!resposta.ok) {
    let cru = "";
    try { cru = await resposta.text(); } catch { /* corpo ilegível: fica o status */ }
    throw erroDaRecusa(resposta.status, cru);
  }
  return resposta;
}

/**
 * Envia o PDF, relatando quantos bytes já subiram.
 *
 * É o único pedido deste arquivo que não usa `fetch`, e a razão é única: o
 * `fetch` não expõe progresso de upload em navegador nenhum hoje. O corpo em
 * fluxo com `duplex: "half"` resolveria, e não tem suporte suficiente.
 *
 * Duas coisas não podem regredir aqui, porque já valiam antes: o `AbortSignal`
 * corta o envio em curso, e a recusa do servidor vira `ErroDaApi` com status e
 * detalhe — é por esse caminho que a mensagem de recusa chega à tela.
 */
export function enviarPdf(arquivo: File, sinal?: AbortSignal,
                          aoProgredir?: (enviados: number, total: number) => void):
                          Promise<Ficha> {
  return new Promise((resolve, reject) => {
    if (sinal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }

    const forma = new FormData();
    forma.append("arquivo", arquivo);

    const x = new XMLHttpRequest();
    x.open("POST", "/api/jobs");

    x.upload.addEventListener("progress", (e) => {
      const p = e as ProgressEvent;
      if (p.lengthComputable) aoProgredir?.(p.loaded, p.total);
    });

    const desistir = () => x.abort();
    sinal?.addEventListener("abort", desistir, { once: true });
    const limpar = () => sinal?.removeEventListener("abort", desistir);

    x.addEventListener("abort", () => {
      limpar();
      reject(new DOMException("Aborted", "AbortError"));
    });

    x.addEventListener("error", () => {
      limpar();
      reject(new TypeError("Não consegui falar com o servidor."));
    });

    x.addEventListener("load", () => {
      limpar();
      if (x.status >= 200 && x.status < 300) {
        try {
          resolve(JSON.parse(x.responseText) as Ficha);
        } catch {
          reject(new ErroDaApi(x.status, "O servidor respondeu algo que não entendi."));
        }
        return;
      }
      // Mesmo mapeamento do `pedir`, e literalmente o mesmo código.
      reject(erroDaRecusa(x.status, x.responseText));
    });

    // `void` e não `await`: `enviarPdf` devolve `Promise` mas não é `async`, e
    // a coleta é rápida. Se ela falhar, o envio segue sem o cabeçalho — a
    // impressão nunca pode impedir alguém de converter uma planta.
    //
    // Entre `x.open()` (acima) e `x.send()` (aqui dentro) existe uma janela em
    // que o XHR está aberto mas não enviado: um `x.abort()` nesse estado não
    // dispara evento nenhum (é o que `desistir` faria via o `sinal`), então
    // sem reconferir `sinal?.aborted` aqui o envio subiria mesmo cancelado. E
    // sem o `.catch()` externo, uma exceção de `setRequestHeader`/`send`
    // sumiria no `void` e a promessa de `enviarPdf` nunca liquidaria.
    //
    // O `.catch(() => null)` logo após `coletar()` é outra coisa: sem ele, uma
    // rejeição de `coletar()` cairia no `.catch()` externo e bloquearia o
    // envio — contrariando o "falhar nunca bloqueia" documentado em
    // `impressao.ts`. `coletar()` já não deveria rejeitar (ela própria tem
    // `try/catch`), mas o contrato do envio não pode depender disso.
    void coletar().catch(() => null).then((impressao) => {
      if (sinal?.aborted) {
        limpar();
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      if (impressao) x.setRequestHeader("X-Impressao", impressao);
      x.send(forma);
    }).catch((erro: unknown) => {
      limpar();
      reject(erro instanceof Error ? erro : new Error(String(erro)));
    });
  });
}

export async function pedirExtracao(job: string, pagina: number,
                                    sinal?: AbortSignal): Promise<EstadoPagina> {
  const r = await pedir(`/api/jobs/${job}/pages/${pagina}`,
                        { method: "POST", signal: sinal });
  return r.json();
}

export async function lerEstado(job: string, pagina: number,
                                sinal?: AbortSignal): Promise<EstadoPagina> {
  const r = await pedir(`/api/jobs/${job}/pages/${pagina}`, { signal: sinal });
  return r.json();
}

const ESPERA_INICIAL = 300;
const ESPERA_MAXIMA = 2000;

function dormir(ms: number, sinal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    sinal.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

/**
 * Consulta até a página sair da fila, com recuo crescente.
 *
 * Uma planta pesada leva minutos; bater a cada 300 ms por minutos é ruído à
 * toa, e um intervalo fixo longo faria a planta leve parecer lenta.
 */
export async function esperarPagina(job: string, pagina: number,
                                    sinal: AbortSignal,
                                    aoMudar: (e: EstadoPagina) => void):
                                    Promise<EstadoPagina> {
  let espera = ESPERA_INICIAL;
  let anterior = "";
  for (;;) {
    if (sinal.aborted) throw new DOMException("Aborted", "AbortError");
    const estado = await lerEstado(job, pagina, sinal);
    if (estado.situacao !== anterior) {
      anterior = estado.situacao;
      aoMudar(estado);
    }
    if (estado.situacao === "pronta" || estado.situacao === "erro") return estado;
    await dormir(espera, sinal);
    espera = Math.min(espera * 2, ESPERA_MAXIMA);
  }
}

export async function lerMeta(job: string, pagina: number,
                              sinal?: AbortSignal): Promise<Meta> {
  const r = await pedir(`/api/jobs/${job}/pages/${pagina}/meta.json`,
                        { signal: sinal });
  return r.json();
}

/**
 * Baixa a geometria lendo o corpo em pedaços, para poder relatar progresso.
 *
 * O buffer devolvido tem de ser byte a byte o mesmo que `arrayBuffer()`
 * devolvia: é sobre ele que o leitor do formato monta as `TypedArray` sem
 * copiar, e é por isso que as seções são enchidas até múltiplo de 4.
 */
export async function lerGeometriaBruta(job: string, pagina: number,
                                        parte: "esqueleto" | "detalhe",
                                        sinal?: AbortSignal,
                                        aoProgredir?: (lidos: number,
                                                       total: number | null) => void):
                                        Promise<ArrayBuffer> {
  const r = await pedir(
    `/api/jobs/${job}/pages/${pagina}/geometry.bin?parte=${parte}`,
    { signal: sinal });

  const declarado = Number(r.headers.get("content-length"));
  // Sem tamanho declarado — resposta comprimida, por exemplo — o progresso sai
  // indeterminado, e não com uma porcentagem inventada.
  const total = Number.isFinite(declarado) && declarado > 0 ? declarado : null;

  // Ambiente sem corpo em fluxo: cai no caminho antigo em vez de estourar.
  if (!r.body) return r.arrayBuffer();

  const leitor = r.body.getReader();
  const pedacos: Uint8Array[] = [];
  let lidos = 0;
  for (;;) {
    const { done, value } = await leitor.read();
    if (done) break;
    pedacos.push(value);
    lidos += value.byteLength;
    aoProgredir?.(lidos, total);
  }

  // Uma cópia só, no fim. Concatenar a cada pedaço seria quadrático, e numa
  // planta no teto são dezenas de megabytes.
  const inteiro = new Uint8Array(lidos);
  let onde = 0;
  for (const p of pedacos) {
    inteiro.set(p, onde);
    onde += p.byteLength;
  }
  return inteiro.buffer;
}

export async function exportar(job: string, pagina: number,
                               pedido: PedidoDeExportacao, sinal?: AbortSignal) {
  const impressao = await coletar();
  const cabecalhos: Record<string, string> = {
    "content-type": "application/json",
  };
  if (impressao) cabecalhos["X-Impressao"] = impressao;
  const r = await pedir(`/api/jobs/${job}/pages/${pagina}/export`, {
    method: "POST", headers: cabecalhos, body: JSON.stringify(pedido),
    signal: sinal,
  });
  return r.json() as Promise<{ chave: string; url: string; cache: boolean;
                               entidades: number }>;
}

// --- conta e cota (etapa 4) --------------------------------------------------

/**
 * O saldo de um balde. `null` nos três campos é **sem limite**, e não zero:
 * quem lê tem de mostrar texto nenhum em vez de inventar um número.
 */
export type Saldo = {
  restam: number | null;
  de: number | null;
  libera_em: number | null;
};

export type Cota = {
  tipo: "visitante" | "logado";
  email: string;
  confirmado: boolean;
  arquivos: Saldo;
  downloads: Saldo;
  teto_bytes: number;
};

/**
 * A leitura da cota também manda `X-Impressao` (dívida da revisão da tarefa
 * 11): o servidor só soma o balde da impressão ao saldo quando o cabeçalho
 * chega (`web/api/identidade.py`), e sem ele o canto mostra vaga justo no
 * caso em que a impressão importa — cookie apagado ou IP trocado, mesma
 * máquina. Mesma forma de `exportar`: `coletar()` é cacheado, então isto não
 * custa nada a partir da segunda chamada.
 */
export async function lerCota(sinal?: AbortSignal): Promise<Cota> {
  const impressao = await coletar();
  const cabecalhos: Record<string, string> = {};
  if (impressao) cabecalhos["X-Impressao"] = impressao;
  const r = await pedir("/api/cota", { headers: cabecalhos, signal: sinal });
  return r.json();
}

function corpoJson(dados: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(dados),
  };
}

export async function entrar(email: string, senha: string) {
  const r = await pedir("/api/auth/entrar", corpoJson({ email, senha }));
  return r.json() as Promise<{ email: string; confirmado: boolean }>;
}

export async function sair(): Promise<void> {
  await pedir("/api/auth/sair", { method: "POST" });
}

export async function registrar(email: string, senha: string) {
  const r = await pedir("/api/auth/registro", corpoJson({ email, senha }));
  return r.json() as Promise<{ mensagem: string }>;
}

export async function pedirSenha(email: string) {
  const r = await pedir("/api/auth/senha", corpoJson({ email }));
  return r.json() as Promise<{ mensagem: string }>;
}

export async function concluirSenha(token: string, senha: string) {
  const r = await pedir(`/api/auth/senha/${encodeURIComponent(token)}`,
                        corpoJson({ senha }));
  return r.json() as Promise<{ ok: boolean }>;
}
