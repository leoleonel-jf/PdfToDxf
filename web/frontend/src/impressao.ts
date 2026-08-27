/**
 * A impressão do navegador — só o hash sai daqui.
 *
 * Os sinais crus **nunca deixam o navegador**: o que vai no cabeçalho
 * `X-Impressao` é o SHA-256 deles. O servidor ainda aplica `hmac` com o
 * segredo dele antes de guardar, então nem este hash aparece no banco.
 *
 * Duas coisas que isto compra, e vale escrever para ninguém esperar mais: aba
 * anônima e cookie apagado **mantêm** a mesma impressão, que é o caso comum de
 * quem quer mais cota; e trocar de navegador, de máquina ou usar um bloqueador
 * muda tudo. Por isso ela é teto folgado, e não a identidade principal.
 *
 * Falhar aqui **nunca bloqueia**: `coletar()` devolve `null` e o pedido segue
 * sem o cabeçalho. Quem escolhe se proteger fica com a cota anunciada.
 *
 * Contexto inseguro (HTTP puro, sem TLS) é uma dessas falhas por projeto:
 * `crypto.subtle` não existe fora de um contexto seguro, então `coletar()`
 * devolve `null` para a sessão inteira e o cabeçalho simplesmente não vai —
 * sem exceção, sem retry, e sem cota reduzida por isso.
 */

export type Sinais = {
  agente: string;
  idioma: string;
  tela: string;
  fuso: string;
  nucleos: number;
  canvas: string;
};

/** Uma linha por sinal, em ordem fixa. Ordem instável mudaria o hash à toa. */
export function sinaisEmTexto(s: Sinais): string {
  return [s.agente, s.idioma, s.tela, s.fuso, String(s.nucleos), s.canvas]
    .join("\n");
}

export async function hashHex(texto: string): Promise<string> {
  const dados = new TextEncoder().encode(texto);
  const bruto = await crypto.subtle.digest("SHA-256", dados);
  return Array.from(new Uint8Array(bruto))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** O desenho de um canvas 2D: o mesmo texto rende pixels diferentes por máquina. */
function assinaturaDoCanvas(): string {
  try {
    const tela = document.createElement("canvas");
    tela.width = 200;
    tela.height = 40;
    const ctx = tela.getContext("2d");
    if (!ctx) return "";
    ctx.textBaseline = "top";
    ctx.font = "14px 'Arial'";
    ctx.fillStyle = "#f60";
    ctx.fillRect(0, 0, 100, 20);
    ctx.fillStyle = "#069";
    ctx.fillText("PdfToDxf — escala real", 2, 4);
    return tela.toDataURL().slice(-64);
  } catch {
    return "";
  }
}

let guardado: string | null | undefined;

export async function coletar(): Promise<string | null> {
  if (guardado !== undefined) return guardado;
  try {
    const s: Sinais = {
      agente: navigator.userAgent,
      idioma: navigator.language,
      tela: `${screen.width}x${screen.height}x${screen.colorDepth}`,
      fuso: Intl.DateTimeFormat().resolvedOptions().timeZone ?? "",
      nucleos: navigator.hardwareConcurrency ?? 0,
      canvas: assinaturaDoCanvas(),
    };
    guardado = await hashHex(sinaisEmTexto(s));
  } catch {
    guardado = null;
  }
  return guardado;
}
