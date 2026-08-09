import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const PLANTA = fileURLToPath(
  new URL("../../../tests/fixtures/planta_de_teste.pdf", import.meta.url));

test("converte uma planta de ponta a ponta", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles("#escolher-pdf", PLANTA);

  // Espera por condição: o botão só habilita quando a geometria chegou.
  await expect(page.locator('[data-teste="exportar"]'))
    .toBeEnabled({ timeout: 60_000 });
  await expect(page.locator("#aviso")).toBeHidden();

  // A estimativa apareceu e não é zero.
  const estimativa = page.locator('[data-teste="estimativa-valor"]');
  await expect(estimativa).not.toHaveText("");

  // Exporta e o download acontece.
  const download = page.waitForEvent("download");
  await page.locator('[data-teste="exportar"]').click();
  const arquivo = await download;
  expect(await arquivo.path()).toBeTruthy();
});

test("o desenho aparece no canvas", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles("#escolher-pdf", PLANTA);
  await expect(page.locator('[data-teste="exportar"]'))
    .toBeEnabled({ timeout: 60_000 });

  // Espera por condição, e não por relógio: com o preparo fatiado entre
  // quadros, quantos quadros passam até o desenho ficar pronto depende da
  // máquina. O `main.ts` publica a contagem no próprio canvas.
  await expect
    .poll(async () => Number(await page.locator("#desenho")
                                       .getAttribute("data-desenhadas")),
          { timeout: 30_000 })
    .toBeGreaterThan(0);

  // Um canvas todo do fundo é canvas vazio. Conta quantas cores distintas há:
  // com desenho, há mais de uma.
  const cores = await page.locator("#desenho").evaluate((tela) => {
    const c = tela as HTMLCanvasElement;
    const ctx = c.getContext("2d")!;
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    const vistas = new Set<number>();
    for (let i = 0; i < d.length; i += 4) {
      vistas.add((d[i]! << 16) | (d[i + 1]! << 8) | d[i + 2]!);
      if (vistas.size > 1) break;
    }
    return vistas.size;
  });
  expect(cores).toBeGreaterThan(1);
});
