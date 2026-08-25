/**
 * Os caminhos dos ícones, em dado puro.
 *
 * Dado e não elemento: assim o módulo é testável no vitest, que roda em Node e
 * não tem `document`. Quem monta o `<svg>` é `controles.ts`.
 *
 * Origem: Tabler Icons (MIT), traçado de 24×24 com `stroke-width` 2. Só os onze
 * usados foram copiados — a spec geral pede "ícones desenhados em SVG inline,
 * só os poucos necessários", e trazer o pacote inteiro contrariaria isso.
 */
export const CAMINHOS: Record<string, string> = {
  arquivo:
    "M14 3v4a1 1 0 0 0 1 1h4 M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2 M12 11v6 M9.5 13.5l2.5 -2.5l2.5 2.5",
  regua:
    "M19.875 12c.621 0 1.125 .512 1.125 1.143v5.714c0 .631 -.504 1.143 -1.125 1.143h-15.875a1 1 0 0 1 -1 -1v-5.857c0 -.631 .504 -1.143 1.125 -1.143h15.75 M9 12v2 M6 12v3 M12 12v3 M18 12v3 M15 12v2 M3 3v4 M3 5h18 M21 3v4",
  ajustes:
    "M4 10a2 2 0 1 0 4 0a2 2 0 0 0 -4 0 M6 4v4 M6 12v8 M10 16a2 2 0 1 0 4 0a2 2 0 0 0 -4 0 M12 4v10 M12 18v2 M16 7a2 2 0 1 0 4 0a2 2 0 0 0 -4 0 M18 4v1 M18 9v11",
  camadas: "M12 4l-8 4l8 4l8 -4l-8 -4 M4 12l8 4l8 -4 M4 16l8 4l8 -4",
  olho:
    "M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0 M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6",
  "olho-cortado":
    "M10.585 10.587a2 2 0 0 0 2.829 2.828 M16.681 16.673a8.717 8.717 0 0 1 -4.681 1.327c-3.6 0 -6.6 -2 -9 -6c1.272 -2.12 2.712 -3.678 4.32 -4.674m2.86 -1.146a9.055 9.055 0 0 1 1.82 -.18c3.6 0 6.6 2 9 6c-.666 1.11 -1.379 2.067 -2.138 2.87 M3 3l18 18",
  baixar:
    "M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2 M7 11l5 5l5 -5 M12 4l0 12",
  recolher:
    "M4 6a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2l0 -12 M9 4v16 M15 10l-2 2l2 2",
  menu: "M4 6l16 0 M4 12l16 0 M4 18l16 0",
  busca: "M3 10a7 7 0 1 0 14 0a7 7 0 1 0 -14 0 M21 21l-6 -6",
  usuario:
    "M12 7a4 4 0 1 0 0 8 4 4 0 0 0 0-8M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2",
};

export function caminho(nome: string): string {
  const d = CAMINHOS[nome];
  if (!d) throw new Error(`ícone desconhecido: ${nome}`);
  return d;
}
