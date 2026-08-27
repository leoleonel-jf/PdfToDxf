import { describe, expect, it } from "vitest";
import { horaDeLiberar, textoDaCota } from "../src/conta.js";
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
});
