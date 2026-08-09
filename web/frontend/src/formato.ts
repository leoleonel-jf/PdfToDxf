/**
 * Leitor do `geometry.bin`, e a intercalação das duas partes.
 *
 * As `TypedArray` são montadas **sobre** o buffer recebido, sem copiar: numa
 * planta no teto são dezenas de megabytes, e copiar seria pagar duas vezes. É
 * por isso que o formato enche cada seção até um múltiplo de 4 — sem
 * alinhamento, `new Uint32Array(buffer, desloc, n)` levanta `RangeError`.
 */
import type { Atributos } from "./select.js";

// "PDXF" lido como uint32 little-endian: P=0x50 D=0x44 X=0x58 F=0x46,
// portanto 0x46 << 24 | 0x58 << 16 | 0x44 << 8 | 0x50.
const MAGICO = 0x46584450;
const VERSAO = 1;

const IDX = 1, KIND = 2, LAYER_ID = 3, IS_FILL = 4, LENGTH_UM = 5;
const DUP_GROUP = 6, BYTE_COST = 7, COR = 8, COORD_OFF = 9, COORDS = 10;
const TEXTO_OFF = 11, TEXTO = 12;

export const SEM_COR = 0xffffffff;

export type Geometria = Atributos & {
  n: number;
  idx: Uint32Array;
  cor: Uint32Array;
  coord_off: Uint32Array;
  coords: Float32Array;
  texto_off: Uint32Array;
  texto: Uint8Array;
};

export function lerGeometria(buffer: ArrayBuffer, layers: string[],
                             nGroups: number): Geometria {
  if (buffer.byteLength < 16) throw new Error("formato: arquivo curto demais");
  const cabecalho = new DataView(buffer);
  if (cabecalho.getUint32(0, true) !== MAGICO) {
    throw new Error("formato: não é um arquivo de geometria do PdfToDxf");
  }
  const versao = cabecalho.getUint32(4, true);
  if (versao !== VERSAO) throw new Error(`formato: versão ${versao} desconhecida`);
  const n = cabecalho.getUint32(8, true);
  const s = cabecalho.getUint32(12, true);
  if (buffer.byteLength < 16 + 12 * s) {
    throw new Error("formato: tabela de seções cortada");
  }

  const tabela = new Map<number, { desloc: number; tamanho: number }>();
  for (let k = 0; k < s; k++) {
    const base = 16 + 12 * k;
    const tipo = cabecalho.getUint32(base, true);
    const desloc = cabecalho.getUint32(base + 4, true);
    const tamanho = cabecalho.getUint32(base + 8, true);
    if (desloc + tamanho > buffer.byteLength) {
      throw new Error(`formato: seção ${tipo} passa do fim do arquivo`);
    }
    tabela.set(tipo, { desloc, tamanho });
  }

  function secao(tipo: number): { desloc: number; tamanho: number } {
    const s = tabela.get(tipo);
    if (!s) throw new Error(`formato: falta a seção ${tipo}`);
    return s;
  }
  const u32 = (tipo: number, quantos: number) =>
    new Uint32Array(buffer, secao(tipo).desloc, quantos);
  const u8 = (tipo: number, quantos: number) =>
    new Uint8Array(buffer, secao(tipo).desloc, quantos);

  const coords = secao(COORDS);
  const texto = secao(TEXTO);

  return {
    n,
    layers,
    n_groups: nGroups,
    idx: u32(IDX, n),
    kind: u8(KIND, n),
    layer_id: u32(LAYER_ID, n),
    is_fill: u8(IS_FILL, n),
    length_um: u32(LENGTH_UM, n),
    dup_group: new Int32Array(buffer, secao(DUP_GROUP).desloc, n),
    byte_cost: u32(BYTE_COST, n),
    cor: u32(COR, n),
    coord_off: u32(COORD_OFF, n + 1),
    coords: new Float32Array(buffer, coords.desloc, coords.tamanho / 4),
    texto_off: u32(TEXTO_OFF, n + 1),
    texto: new Uint8Array(buffer, texto.desloc, texto.tamanho),
  };
}

export function coordenadasDe(g: Geometria, i: number): Float32Array {
  return g.coords.subarray(g.coord_off[i]!, g.coord_off[i + 1]!);
}

const DECODIFICADOR = new TextDecoder("utf-8");

export function textoDe(g: Geometria, i: number): string {
  const inicio = g.texto_off[i]!;
  const fim = g.texto_off[i + 1]!;
  if (inicio === fim) return "";
  return DECODIFICADOR.decode(g.texto.subarray(inicio, fim));
}
