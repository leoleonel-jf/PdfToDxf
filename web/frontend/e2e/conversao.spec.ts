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

/**
 * As duas barras têm o mesmo `data-teste` e lugares diferentes na tela.
 *
 * São dois indicadores independentes — a sobreposição para envio, extração e
 * exportação; a faixa de baixo para o download e o desenho —, e podem estar
 * vivos ao mesmo tempo. Um seletor solto acharia os dois e o Playwright
 * recusaria a asserção por ambiguidade, então cada asserção diz de qual fala.
 */
const barraDoAviso = (page: Page) => page.locator('#aviso [data-teste="progresso"]');
const barraDaFaixa = (page: Page) =>
  page.locator('#faixa-detalhe [data-teste="progresso"]');

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

/**
 * O defeito de verdade: `Number("0,50")` é `NaN`, e vírgula é como um usuário
 * brasileiro digita decimal. Antes da correção o `NaN` atravessava a guarda
 * de `escalaPorDoisPontos`, virava a escala da tela e derrubava a exportação
 * com um 422 que a tela mostrava como "[object Object]". Este teste prova a
 * cadeia inteira corrigida: vírgula funciona, e a escala muda de verdade.
 */
test("calibrar por 2 pontos aceita vírgula na medida", async ({ page }) => {
  await abrirPlanta(page);

  const escalaAntes = await t(page, "escala-atual").textContent();

  await t(page, "calibrar").click();
  const tela = page.locator("#desenho");
  const caixa = (await tela.boundingBox())!;
  await tela.click({ position: { x: caixa.width * 0.3, y: caixa.height * 0.5 } });

  page.once("dialog", (dialog) => void dialog.accept("0,50"));
  await tela.click({ position: { x: caixa.width * 0.7, y: caixa.height * 0.5 } });

  // A calibração fechou sem erro: o aviso de instrução some, e não aparece
  // nenhum "Não deu para calibrar" no lugar dele.
  await expect(page.locator("#aviso")).toBeHidden();
  await expect(t(page, "escala-atual")).not.toHaveText(escalaAntes!);
});

/**
 * O mesmo defeito, do outro lado: uma medida que não dá para ler nenhum jeito
 * ("abc") tem de mostrar a mensagem própria da guarda — "positiva" — e nunca
 * "[object Object]", que era o que a tela mostrava quando o `NaN` da
 * calibração chegava a atravessar até a resposta do servidor.
 */
test("calibrar com medida inválida mostra mensagem própria, não [object Object]", async ({ page }) => {
  await abrirPlanta(page);

  await t(page, "calibrar").click();
  const tela = page.locator("#desenho");
  const caixa = (await tela.boundingBox())!;
  await tela.click({ position: { x: caixa.width * 0.3, y: caixa.height * 0.5 } });

  page.once("dialog", (dialog) => void dialog.accept("abc"));
  await tela.click({ position: { x: caixa.width * 0.7, y: caixa.height * 0.5 } });

  const aviso = page.locator("#aviso");
  await expect(aviso).toContainText(/positiva/i);
  await expect(aviso).not.toContainText("[object Object]");
});

/**
 * O primeiro clique da calibração precisa deixar rastro na tela — hoje nada
 * marcava o ponto, e o usuário não sabia se o clique tinha pegado.
 */
test("o primeiro clique da calibração marca o ponto na tela", async ({ page }) => {
  await abrirPlanta(page);

  await t(page, "calibrar").click();
  const tela = page.locator("#desenho");
  const caixa = (await tela.boundingBox())!;
  await expect(page.locator(".marca-calibracao")).toHaveCount(0);

  await tela.click({ position: { x: caixa.width * 0.3, y: caixa.height * 0.5 } });
  await expect(page.locator(".marca-calibracao")).toHaveCount(1);

  page.once("dialog", (dialog) => void dialog.accept("1"));
  await tela.click({ position: { x: caixa.width * 0.7, y: caixa.height * 0.5 } });

  // Calibração encerrada: as marcas somem, e não ficam órfãs na tela.
  await expect(page.locator(".marca-calibracao")).toHaveCount(0);
});

/**
 * "Descartar abaixo de N mm" perdia casa decimal e as setinhas nativas de
 * `type="number"` cobriam o texto. Sem `type="number"` não há setinhas, e o
 * campo mostra pelo menos 2 casas.
 */
test("o campo de mm não é type=number e mostra 2 casas decimais", async ({ page }) => {
  await abrirPlanta(page);
  const campo = t(page, "min-len");
  await expect(campo).toHaveAttribute("type", "text");
  // Vírgula: é o separador do português, é o que o campo aceita na entrada, e
  // é o que o resto da tela já usa.
  await expect(campo).toHaveValue(/^\d+,\d{2}$/);
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

/**
 * A barra do envio aparece **de verdade** — e só depois some.
 *
 * A versão antiga deste teste só afirmava `toBeHidden()` no fim, e passaria com
 * a funcionalidade inteira arrancada: um locator que não casa com nada também
 * está escondido. Segurar a rota e exigir `toBeVisible()` antes é o que faz o
 * teste morder.
 */
test("o envio mostra a barra de verdade e ela some ao terminar", async ({ page }) => {
  await page.goto("/");

  let liberar = () => {};
  const preso = new Promise<void>((r) => { liberar = r; });
  await page.route("**/api/jobs", async (route) => {
    await preso;
    await route.continue();
  });

  await page.setInputFiles("#escolher-pdf", PLANTA);
  await expect(barraDoAviso(page)).toBeVisible();
  // Enquanto nenhum byte foi contado, a barra é indeterminada — e barra
  // indeterminada não tem `aria-valuenow`, porque não há número a dizer.
  await expect(page.locator('#aviso [role="progressbar"]'))
    .not.toHaveAttribute("aria-valuenow", /.*/);

  liberar();
  await expect(t(page, "exportar")).toBeEnabled({ timeout: 60_000 });
  await expect(barraDoAviso(page)).toBeHidden();
});

/**
 * A porcentagem do envio é a do navegador, e existe no DOM.
 *
 * Segurar a rota não serve aqui: com a requisição presa no proxy nenhum byte
 * sobe e o evento de progresso do XHR não chega — é a mesma razão pela qual o
 * teste de cancelamento com envio andado estreita a banda por CDP. Sem um tique
 * de verdade, a barra fica (corretamente) indeterminada, e `aria-valuenow` só
 * aparece quando há bytes contados.
 */
test("a barra do envio publica aria-valuenow quando há bytes a contar", async ({ page }) => {
  await page.goto("/");

  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false, latency: 20, downloadThroughput: -1,
    uploadThroughput: 40 * 1024,
  });

  const grande = Buffer.alloc(300 * 1024, 0x41);
  await page.setInputFiles("#escolher-pdf",
    { name: "planta-grande.pdf", mimeType: "application/pdf", buffer: grande });

  await expect(barraDoAviso(page)).toBeVisible();
  const trilho = page.locator('#aviso [role="progressbar"]');
  await expect.poll(async () => trilho.getAttribute("aria-valuenow"),
                    { timeout: 20_000 }).not.toBeNull();

  // Cancela em vez de esperar os 300 KB subirem a 40 KB/s: o que este teste
  // tinha a provar já está provado.
  await t(page, "cancelar").click();
  await expect(barraDoAviso(page)).toBeHidden();
});

/**
 * Faz a planta de teste ter uma parte "detalhe", e segura o download dela.
 *
 * A fixture é minúscula: sete entidades cabem inteiras no esqueleto, o servidor
 * não divide nada e o segundo download — o único momento em que a faixa de
 * baixo mostra progresso na vida real — nunca aconteceria. Mentir só no
 * `partes.detalhe` do `meta.json` é o menor empurrão possível: a rota do
 * detalhe existe e responde de verdade, com um pacote de zero entidades.
 *
 * Devolve a função que solta o download.
 */
async function comDetalheSegurado(page: Page): Promise<() => void> {
  let liberar = () => {};
  const preso = new Promise<void>((r) => { liberar = r; });

  await page.route((url) => url.pathname.endsWith("/meta.json"),
    async (route) => {
      const resposta = await route.fetch();
      const meta = await resposta.json();
      meta.partes.detalhe = 1;
      await route.fulfill({ json: meta });
    });
  await page.route(
    (url) => url.pathname.endsWith("/geometry.bin") &&
             url.searchParams.get("parte") === "detalhe",
    async (route) => {
      await preso;
      try { await route.continue(); } catch { /* página trocou antes */ }
    });

  return () => liberar();
}

/**
 * O download tem indicador, e ele vive na faixa de baixo — não na sobreposição.
 *
 * Dos cinco momentos, este e o desenho eram os dois sem cobertura nenhuma, e
 * são justamente os dois que a revisão pegou.
 */
test("a faixa mostra progresso enquanto o detalhe carrega", async ({ page }) => {
  const liberar = await comDetalheSegurado(page);
  await abrirPlanta(page);

  const faixa = barraDaFaixa(page);
  await expect(faixa).toBeVisible();
  await expect(faixa).toContainText("detalhe");
  // Nada de porcentagem inventada enquanto o servidor não disse o tamanho.
  await expect(page.locator('#faixa-detalhe [role="progressbar"]'))
    .not.toHaveAttribute("aria-valuenow", /.*/);

  liberar();
  await expect(faixa).toBeHidden();
});

/**
 * Um tique da faixa não pode apagar o aviso da sobreposição.
 *
 * Havia um slot único para os cinco momentos: a calibração punha a instrução no
 * `#aviso` e o primeiro pedaço do detalhe a varria da tela, deixando o usuário
 * com dois cliques a dar e nenhuma instrução dizendo isso.
 */
test("um aviso vivo não é apagado por um tique da faixa", async ({ page }) => {
  const liberar = await comDetalheSegurado(page);
  await abrirPlanta(page);
  await expect(barraDaFaixa(page)).toBeVisible();

  await t(page, "calibrar").click();
  const aviso = page.locator("#aviso");
  await expect(aviso).toContainText("extremidades");

  // Agora o download anda: chegam pedaços, o progresso é redesenhado, e a
  // instrução tem de continuar exatamente onde estava.
  liberar();
  await expect(barraDaFaixa(page)).toBeHidden();
  await expect(aviso).toContainText("extremidades");
});

test("exportar mostra o indicador enquanto o servidor gera o DXF", async ({ page }) => {
  await abrirPlanta(page);
  // Segura a resposta do servidor: sem isto, o teste só prova que a barra
  // está escondida no fim, e uma regressão que apagasse a chamada de
  // `mostrarProgresso` inteira passaria do mesmo jeito.
  await page.route("**/api/jobs/*/pages/*/export", async (route) => {
    await new Promise((r) => setTimeout(r, 800));
    await route.continue();
  });

  const progresso = t(page, "progresso");
  const download = page.waitForEvent("download");
  await t(page, "exportar").click();
  await expect(progresso).toBeVisible();

  await download;
  await expect(progresso).toBeHidden();
});

/**
 * Prova que o `.aviso button` do estilo.css devolve o ponteiro.
 *
 * O `.aviso` tem `pointer-events: none` para não engolir os cliques da
 * calibração por dois pontos — mas sem uma regra que devolva o ponteiro ao
 * botão de cancelar, ele nasceria inclicável, e `toBeEnabled` não pegaria
 * isso: um elemento com `pointer-events: none` continua "enabled". Só um
 * `click()` de verdade prova a coisa.
 */
test("cancelar durante o envio aborta de verdade e destrava a tela", async ({ page }) => {
  await page.goto("/");

  // Segura a resposta do servidor antes de qualquer byte subir: aqui não
  // importa que o envio progrida, só que o clique em Cancelar aconteça antes
  // do fim natural do envio.
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

/**
 * O caso em que uma barra de progresso importa de verdade: um arquivo grande,
 * cancelado depois de o envio já ter andado — não no primeiro tique.
 *
 * A guarda antiga comparava a identidade do objeto de progresso, e esse
 * objeto é recriado a cada tique de `mostrarProgresso`. Interceptar a rota e
 * segurar a resposta, como o teste acima, não pega isso: a requisição fica
 * presa antes de qualquer byte subir, então só o tique inicial (feito: 0)
 * roda, e por acidente a comparação de identidade ainda vale. É preciso um
 * segundo tique de verdade, com `feito > 0`, para que os objetos divirjam.
 *
 * Por isso o envio real acontece — sem `page.route` — mas com a banda de
 * upload propositalmente estreitada via CDP: no loopback um arquivo pequeno
 * sobe inteiro num só tique, e o defeito não apareceria.
 */
test("cancelar depois de o envio progredir esconde a barra e destrava a tela", async ({ page }) => {
  await page.goto("/");

  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 20,
    downloadThroughput: -1,
    // 40 KB/s: estreito o bastante para um arquivo de algumas centenas de KB
    // render mais de um tique de progresso antes de terminar sozinho.
    uploadThroughput: 40 * 1024,
  });

  const grande = Buffer.alloc(300 * 1024, 0x41);
  await page.setInputFiles("#escolher-pdf",
    { name: "planta-grande.pdf", mimeType: "application/pdf", buffer: grande });

  const progresso = t(page, "progresso");
  await expect(progresso).toBeVisible();

  // Espera um tique de verdade, com `feito > 0` — o que a barra "importa"
  // significa aqui — antes de cancelar.
  const percentual = progresso.locator(".secundario");
  await expect.poll(async () => {
    const texto = (await percentual.textContent()) ?? "";
    const n = Number(texto.replace("%", ""));
    return Number.isFinite(n) ? n : 0;
  }, { timeout: 15_000 }).toBeGreaterThan(0);

  const cancelar = t(page, "cancelar");
  await expect(cancelar).toBeVisible();
  await cancelar.click();

  await expect(progresso).toBeHidden();
  await expect(t(page, "exportar")).toBeDisabled();
});

test("o canto da conta mostra a cota e a caixa de entrar abre", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('[data-teste="cota"]')).toContainText("arquivos");
  await page.locator('[data-teste="entrar"]').click();
  await expect(page.locator('[data-teste="caixa-entrar"]')).toBeVisible();
  await page.locator('[data-teste="ir-para-cadastrar"]').click();
  await expect(page.locator('[data-teste="caixa-cadastrar"]')).toBeVisible();
  await page.locator('[data-teste="fechar-conta"]').click();
  await expect(page.locator('[data-teste="caixa-cadastrar"]')).toBeHidden();
  // I3.3: o foco volta para quem abriu a caixa — sem isto, quem navega por
  // teclado fica largado no `<body>` depois de fechar o diálogo.
  await expect(page.locator('[data-teste="entrar"]')).toBeFocused();
});
