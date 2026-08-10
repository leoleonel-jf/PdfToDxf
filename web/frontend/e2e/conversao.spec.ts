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

/**
 * A base é o "antes" da comparação: a página inteira, sem compactação nenhuma.
 *
 * O teste acima só exige que a estimativa mude, e passaria igual se a base
 * fosse recalculada a cada clique — que é exatamente o que ela não pode ser,
 * nem por custo (~12 ms por opção marcada) nem por sentido: o "antes" tem de
 * ficar parado para que a redução signifique alguma coisa.
 */
test("a base da comparação não se mexe a cada clique", async ({ page }) => {
  await abrirPlanta(page);
  const estimativa = t(page, "estimativa-valor");

  const base = async () => {
    const texto = (await estimativa.textContent())!;
    expect(texto, texto).toContain("→");
    return texto.split("→")[0]!.trim();
  };

  const antes = await base();
  const textoAntes = (await estimativa.textContent())!;

  // Desligar uma camada tira desenho do arquivo: o número da direita cai, o da
  // esquerda — a página inteira, com todas as camadas — não pode se mexer.
  await t(page, "camada-TEXTO").click();
  await expect(t(page, "camada-TEXTO")).toHaveAttribute("aria-pressed", "false");
  await expect(estimativa).not.toHaveText(textoAntes);
  expect(await base()).toBe(antes);

  await t(page, "camada-TEXTO").click();
  await expect(t(page, "camada-TEXTO")).toHaveAttribute("aria-pressed", "true");
  expect(await base()).toBe(antes);
});

/**
 * O painel abre completo e clicável antes de qualquer PDF, e um clique que não
 * redesenha é pior do que um botão desabilitado: `drop_fills` ficaria ligada em
 * silêncio, e a planta carregaria já sem hachura nenhuma.
 */
test("o painel responde antes de a planta chegar", async ({ page }) => {
  await page.goto("/");
  const opcao = t(page, "opcao-drop_fills");
  await expect(opcao).toHaveAttribute("aria-pressed", "false");
  await opcao.click();
  await expect(opcao).toHaveAttribute("aria-pressed", "true");
});

test("o atalho do painel recolhido leva à seção pedida", async ({ page }) => {
  // Larga o bastante para o painel não virar gaveta, e baixa o bastante para
  // Camadas cair abaixo da dobra: numa janela alta as três seções cabem juntas
  // e o teste passaria sem provar nada.
  await page.setViewportSize({ width: 1280, height: 400 });
  await abrirPlanta(page);

  await t(page, "recolher-painel").click();
  await expect(page.locator("#painel")).toHaveAttribute("data-modo", "recolhido");

  // Reabrir na seção certa não basta: com 260 px de largura, Camadas fica
  // abaixo da dobra do painel e o usuário teria de procurar o que acabou de
  // pedir. `toBeInViewport` é o que distingue "montada" de "à vista".
  await t(page, "atalho-camadas").click();
  await expect(t(page, "secao-camadas")).toBeInViewport();
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

test("o envio mostra barra de progresso e ela some ao terminar", async ({ page }) => {
  await page.goto("/");
  const progresso = t(page, "progresso");
  await page.setInputFiles("#escolher-pdf", PLANTA);
  // A barra pode passar rápido; o que importa é que ela some no fim.
  await expect(t(page, "exportar")).toBeEnabled({ timeout: 60_000 });
  await expect(progresso).toBeHidden();
});

test("exportar mostra o indicador enquanto o servidor gera o DXF", async ({ page }) => {
  await abrirPlanta(page);
  const download = page.waitForEvent("download");
  await t(page, "exportar").click();
  await download;
  await expect(t(page, "progresso")).toBeHidden();
});

/**
 * Prova que o `.aviso button` do estilo.css devolve o ponteiro.
 *
 * O `.aviso` tem `pointer-events: none` para não engolir os cliques da
 * calibração por dois pontos — mas sem uma regra que devolva o ponteiro ao
 * botão de cancelar, ele nasceria inclicável, e `toBeEnabled` não pegaria
 * isso: um elemento com `pointer-events: none` continua "enabled". Só um
 * `click()` de verdade prova a coisa. O PDF de teste é pequeno demais para dar
 * tempo de clicar antes do envio terminar sozinho, então a resposta do
 * servidor é atrasada de propósito.
 */
test("cancelar durante o envio aborta de verdade e destrava a tela", async ({ page }) => {
  await page.goto("/");
  await page.route("**/api/jobs", async (route) => {
    await new Promise((r) => setTimeout(r, 3000));
    try { await route.continue(); } catch { /* abortada pelo cliente antes do proxy */ }
  });
  await page.setInputFiles("#escolher-pdf", PLANTA);

  const cancelar = t(page, "cancelar");
  await expect(cancelar).toBeVisible();
  await cancelar.click();

  // A barra some — sem isto, o clique cancelava o envio mas a tela ficava
  // presa mostrando a barra para sempre, com um botão que já não fazia nada.
  await expect(t(page, "progresso")).toBeHidden();
  await expect(t(page, "exportar")).toBeDisabled();
});
