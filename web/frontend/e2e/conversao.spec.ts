import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

const PLANTA = fileURLToPath(
  new URL("../../../tests/fixtures/planta_de_teste.pdf", import.meta.url));

/**
 * Todos os seletores são `data-teste`, e nenhum é por texto.
 *
 * O cabeçalho antigo era procurado por rótulo, e esta etapa muda quase todos:
 * teste que quebra ao trocar uma palavra não estava testando comportamento.
 */
const t = (page: Page, nome: string) => page.locator(`[data-teste="${nome}"]`);

async function abrirPlanta(page: Page): Promise<void> {
  await page.goto("/");
  await page.setInputFiles("#escolher-pdf", PLANTA);
  // Espera por condição: o botão só habilita quando a geometria chegou.
  await expect(t(page, "exportar")).toBeEnabled({ timeout: 60_000 });
  await expect(page.locator("#aviso")).toBeHidden();
}

test("converte uma planta de ponta a ponta", async ({ page }) => {
  await abrirPlanta(page);

  const estimativa = t(page, "estimativa-valor");
  await expect(estimativa).not.toHaveText("");

  // "Unir em polilinhas" abre ligada; desligá-la mexe na estimativa.
  const opcao = t(page, "opcao-join_polylines");
  await expect(opcao).toHaveAttribute("aria-pressed", "true");
  const antes = await estimativa.textContent();
  await opcao.click();
  await expect(opcao).toHaveAttribute("aria-pressed", "false");
  await expect(estimativa).not.toHaveText(antes!);

  // Exporta e o download acontece.
  const download = page.waitForEvent("download");
  await t(page, "exportar").click();
  const arquivo = await download;
  expect(await arquivo.path()).toBeTruthy();
});

test("o desenho aparece no canvas", async ({ page }) => {
  await abrirPlanta(page);

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

test("o painel recolhe, guarda o estado e reabre na seção clicada", async ({ page }) => {
  await abrirPlanta(page);

  await expect(t(page, "secao-compactacao")).toBeVisible();
  await t(page, "recolher-painel").click();
  await expect(page.locator("#painel")).toHaveAttribute("data-modo", "recolhido");
  await expect(t(page, "secao-compactacao")).toBeHidden();

  // A preferência sobrevive ao recarregamento.
  await page.reload();
  await expect(page.locator("#painel")).toHaveAttribute("data-modo", "recolhido");

  // Clicar no atalho reabre já naquela seção.
  await t(page, "atalho-camadas").click();
  await expect(page.locator("#painel")).toHaveAttribute("data-modo", "aberto");
});

test("em tela estreita o painel vira gaveta", async ({ page }) => {
  await page.setViewportSize({ width: 500, height: 800 });
  await page.goto("/");
  await expect(page.locator("#painel")).toHaveAttribute("data-modo", "gaveta");
  await expect(page.locator("#painel")).toBeHidden();

  await t(page, "abrir-painel").click();
  await expect(page.locator("#painel")).toBeVisible();
});

test("camadas mostram contagem e desligar uma muda a estimativa", async ({ page }) => {
  await abrirPlanta(page);

  const camada = t(page, "camada-TEXTO");
  await expect(camada).toBeVisible();
  await expect(camada).toHaveAttribute("aria-pressed", "true");

  const estimativa = t(page, "estimativa-valor");
  const antes = await estimativa.textContent();
  await camada.click();
  await expect(camada).toHaveAttribute("aria-pressed", "false");
  await expect(estimativa).not.toHaveText(antes!);
});

test("a estimativa mostra o tamanho sem compactação ao lado do atual", async ({ page }) => {
  await abrirPlanta(page);
  const estimativa = t(page, "estimativa-valor");

  // Três opções abrem ligadas, então a comparação aparece de saída.
  await expect(estimativa).toContainText("→");
  await expect(estimativa).toContainText("−");

  // Desligando as três, base e atual coincidem: volta a ser um número só.
  await t(page, "opcao-join_polylines").click();
  await t(page, "opcao-round_coords").click();
  await t(page, "opcao-dedup").click();
  await expect(estimativa).not.toContainText("→");
});

test("as três opções que só tiram redundância abrem ligadas", async ({ page }) => {
  await abrirPlanta(page);
  for (const chave of ["join_polylines", "round_coords", "dedup"]) {
    await expect(t(page, `opcao-${chave}`), chave)
      .toHaveAttribute("aria-pressed", "true");
  }
  // Esta apaga desenho de verdade: nunca por padrão.
  await expect(t(page, "opcao-drop_fills"))
    .toHaveAttribute("aria-pressed", "false");
});
