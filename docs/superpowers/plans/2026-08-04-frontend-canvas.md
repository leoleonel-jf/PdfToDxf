# Etapa 3 — frontend: canvas, `select.ts` e calibração

> **Para quem executa com agentes:** SUB-SKILL OBRIGATÓRIA: use
> `superpowers:subagent-driven-development` (recomendado) ou
> `superpowers:executing-plans` para implementar tarefa a tarefa. Os passos usam
> caixas (`- [ ]`) para acompanhamento.

**Objetivo:** entregar a tela inteira do conversor — abrir PDF, escolher página,
ver a planta no canvas, calibrar por dois pontos, ligar e desligar opções vendo
a prévia mudar na hora, e exportar o DXF — contra a API que a etapa 2 já serve.

**Arquitetura:** duas threads. A principal cuida de DOM, canvas e gestos e é
dona das coordenadas. Um Web Worker guarda os arrays de decisão e roda o
`select()`, devolvendo a máscara como `Uint8Array` transferível. A intercalação
do esqueleto com o detalhe é função pura, feita uma vez na thread principal.

**Ferramental:** TypeScript, Vite, vitest, Playwright. Em produção, um estágio
do Dockerfile compila e o FastAPI serve os estáticos.

**Desenho que governa:**
`docs/superpowers/specs/2026-08-04-frontend-canvas-design.md`. Ele complementa a
spec geral, `docs/superpowers/specs/2026-08-01-pdftodxf-web-design.md`.

## Restrições globais

Valem para todas as tarefas. Não repetidas em cada uma.

- **Idioma do código:** nomes de função, variável, arquivo e mensagem em
  português, como no resto do projeto. Comentário explica *por quê*, não *o
  quê*.
- **Sem framework de interface e sem biblioteca de componentes.** CSS escrito à
  mão com variáveis. Ícones em SVG embutido. Nada de gradiente, sombra ou
  animação decorativa.
- **Dependências de produção: zero.** Tudo que entra no `package.json` é
  `devDependencies` — Vite, TypeScript, vitest, Playwright. O que vai ao
  navegador é só código deste repositório.
- **Node 22, npm 10.** Já instalados na máquina de desenvolvimento.
- **Python:** sempre `./.venv/Scripts/python.exe`, nunca `python`.
- **Sem pytest.** Os testes Python deste projeto são funções com `assert` e um
  bloco `if __name__ == "__main__":`. Mantenha o padrão nos testes novos.
- **`tests/casos_select.json` não pode ser modificado.** É dado congelado. Se o
  `git diff` dele sujar, alguma coisa quebrou o contrato.
- **Toda espera em teste é por condição, nunca por relógio.** A etapa 2 já
  mostrou o que `sleep` fixo faz com a confiança na bateria.
- **Diretório de trabalho do frontend:** `web/frontend/`. Todo comando `npm`
  roda de lá.

## Constantes que o TypeScript espelha do Python

Copiadas de `pdftodxf/optimize.py`. Errar qualquer uma quebra o contrato.

```
_BYTES = {"Segment": 210, "Arc": 235, "Bezier": 620, "TextItem": 330}
_POLY_BASE   = 180
_POLY_PER_PT = 42
_ROUND_FACTOR = 0.78
cabeçalho fixo da estimativa = 60_000
encadeamento aproximado = 0.85
tamanho médio de cadeia = 12
```

**Regra de arredondamento, e é onde se erra:**

| Python | TypeScript | Onde |
|---|---|---|
| `int(min_len_mm * 1000.0 + 0.5)` | `Math.round(min_len_mm * 1000.0)` | `select` |
| `int(n_seg * 0.85)` | `Math.trunc(n_seg * 0.85)` | `estimativa` |
| `chained // 12` | `Math.floor(chained / 12)` | `estimativa` |
| `int(total * 0.78)` | `Math.trunc(total * 0.78)` | `estimativa` |

O `int()` do Python trunca em direção a zero; o `round()` dele arredonda para o
par mais próximo, que **não** é o que o `Math.round()` faz. Por isso o
`min_len_um` é escrito no Python como `int(x + 0.5)`: para casar com o
JavaScript. Está registrado na docstring do `select()`.

## Códigos do formato binário

De `web/api/packing.py`. O `kind` chega ao TypeScript como número.

```
tipos de seção: IDX=1 KIND=2 LAYER_ID=3 IS_FILL=4 LENGTH_UM=5
                DUP_GROUP=6 BYTE_COST=7 COR=8 COORD_OFF=9 COORDS=10
                TEXTO_OFF=11 TEXTO=12
código de kind: Segment=0 Polyline=1 Arc=2 Bezier=3 TextItem=4
magia "PDXF", versão 1, sem cor = 0xFFFFFFFF, alinhamento de seção = 4
cabeçalho: 4 magia + uint32 versão + uint32 n + uint32 s, depois s×12 da tabela
```

## Estrutura de arquivos

```
web/frontend/
  package.json          devDependencies só; scripts test, dev, build, e2e
  tsconfig.json
  vite.config.ts        proxy de /api para o uvicorn em desenvolvimento
  index.html
  src/
    api.ts              cliente HTTP, com AbortController por página
    formato.ts          leitor de geometry.bin e a intercalação (função pura)
    select.ts           espelho de optimize.select(), sobre arrays numéricos
    estimativa.ts       espelho de optimize.estimate_bytes()
    worker.ts           guarda os arrays de decisão, roda select e estimativa
    canvas.ts           Path2D por (layer, cor), pan e zoom, mouse e toque
    calibrate.ts        dois pontos, com lupa no toque
    toolbar.ts          as duas faixas do cabeçalho
    estados.ts          mensagens de espera e de erro
    main.ts             composição da tela e o estado
    estilo.css
  testes/
    ajuda/contrato.ts   carrega casos_select.json e traduz o kind
    ajuda/canvas2d.ts   contexto 2D falso que grava as chamadas
    select.test.ts      os 1024 casos: máscara e bytes
    formato.test.ts     lê a fixture gerada pelo Python
    intercalar.test.ts  ordem original e o achado do dedup
    canvas.test.ts      o desenhado corresponde à máscara
    calibrate.test.ts   a aritmética da escala
  e2e/
    conversao.spec.ts   Playwright de ponta a ponta

tests/
  gerar_fixture_geometria.py   gera a fixture do formato, determinística
  fixtures/geometria_exemplo.bin
  fixtures/geometria_exemplo.json
  test_fixture_geometria.py    confere que a fixture bate com o packing.py
```

---

### Tarefa 1: medir antes de comprometer a arquitetura

A escolha pelo Web Worker é hipótese fundamentada, não número medido. Esta
tarefa produz o número. Se a reconstrução dos caminhos for barata, o worker
vira simplificação opcional e as tarefas seguintes mudam; se for cara, a medida
confirma a fronteira.

**Arquivos:**
- Criar: `web/frontend/package.json`, `web/frontend/tsconfig.json`,
  `web/frontend/vite.config.ts`, `web/frontend/index.html`
- Criar: `web/frontend/medicao/custo.html`, `web/frontend/medicao/custo.ts`
- Criar: `web/frontend/medicao/RESULTADO.md`

**Interfaces:**
- Consome: nada
- Produz: o andaime do Vite (`npm run dev`, `npm run build`, `npm test`
  funcionando) e um número registrado em `medicao/RESULTADO.md`

- [ ] **Passo 1: criar o projeto**

```bash
cd web/frontend
npm init -y
npm install --save-dev vite typescript vitest @types/node
```

- [ ] **Passo 2: `web/frontend/package.json`**

Substitua o gerado por este. Note `"type": "module"` e a ausência de
`dependencies` — é restrição do projeto, não descuido.

```json
{
  "name": "pdftodxf-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "typescript": "^5.6.0",
    "vite": "^5.4.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Passo 3: `web/frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable", "WebWorker"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "noEmit": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "types": ["vitest/globals"]
  },
  "include": ["src", "testes", "medicao", "e2e", "vite.config.ts"]
}
```

`noUncheckedIndexedAccess` é de propósito: obriga a tratar índice fora de faixa,
que é exatamente o erro que um leitor de formato binário comete.

- [ ] **Passo 4: `web/frontend/vite.config.ts`**

```ts
// De "vitest/config", não de "vite": o `defineConfig` do Vite puro não conhece
// o bloco `test` e o TypeScript recusa o arquivo.
import { defineConfig } from "vitest/config";

export default defineConfig({
  server: {
    // O frontend e a API vivem em portas diferentes em desenvolvimento. Sem
    // este proxy, todo pedido a /api viraria requisição de outra origem e
    // esbarraria em CORS — que não queremos afrouxar no servidor só por causa
    // do ambiente de trabalho.
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "node", include: ["testes/**/*.test.ts"] },
});
```

- [ ] **Passo 5: `web/frontend/index.html`**

Mínimo por enquanto; a tarefa 9 o preenche.

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PdfToDxf</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

Crie também `web/frontend/src/main.ts` com uma linha, só para o build passar:

```ts
document.querySelector("#app")!.textContent = "PdfToDxf";
```

- [ ] **Passo 6: a página de medição, `web/frontend/medicao/custo.html`**

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <title>Medição do custo</title>
  </head>
  <body>
    <pre id="saida">medindo…</pre>
    <script type="module" src="./custo.ts"></script>
  </body>
</html>
```

- [ ] **Passo 7: `web/frontend/medicao/custo.ts`**

Gera 3 milhões de segmentos sintéticos, roda um `select()` grosseiro e
reconstrói os `Path2D` agrupados, medindo cada fase. Não usa o `select.ts` real
— ele ainda não existe, e o que se mede aqui é a ordem de grandeza.

```ts
const N = 3_000_000;

function gerar() {
  const kind = new Uint8Array(N);
  const layerId = new Uint32Array(N);
  const lengthUm = new Uint32Array(N);
  const dupGroup = new Int32Array(N);
  const coords = new Float32Array(N * 4);
  for (let i = 0; i < N; i++) {
    layerId[i] = i % 8;
    lengthUm[i] = (i % 997) + 1;
    dupGroup[i] = i % 500_000;
    const x = (i % 1000) * 0.5;
    const y = Math.floor(i / 1000) * 0.05;
    coords[i * 4] = x;
    coords[i * 4 + 1] = y;
    coords[i * 4 + 2] = x + 3;
    coords[i * 4 + 3] = y + 1;
  }
  return { kind, layerId, lengthUm, dupGroup, coords };
}

function selecionar(d: ReturnType<typeof gerar>, minLenUm: number) {
  const mascara = new Uint8Array(N);
  const emitido = new Uint8Array(500_000);
  for (let i = 0; i < N; i++) {
    if (d.lengthUm[i]! < minLenUm) continue;
    const g = d.dupGroup[i]!;
    if (emitido[g]) continue;
    emitido[g] = 1;
    mascara[i] = 1;
  }
  return mascara;
}

function construirCaminhos(d: ReturnType<typeof gerar>, mascara: Uint8Array) {
  const porGrupo = new Map<number, Path2D>();
  for (let i = 0; i < N; i++) {
    if (!mascara[i]) continue;
    const g = d.layerId[i]!;
    let caminho = porGrupo.get(g);
    if (!caminho) { caminho = new Path2D(); porGrupo.set(g, caminho); }
    caminho.moveTo(d.coords[i * 4]!, d.coords[i * 4 + 1]!);
    caminho.lineTo(d.coords[i * 4 + 2]!, d.coords[i * 4 + 3]!);
  }
  return porGrupo;
}

const linhas: string[] = [];
function cronometrar(nome: string, f: () => unknown) {
  const inicio = performance.now();
  const r = f();
  const gasto = performance.now() - inicio;
  linhas.push(`${nome}: ${gasto.toFixed(0)} ms`);
  document.querySelector("#saida")!.textContent = linhas.join("\n");
  return r;
}

const dados = cronometrar("gerar 3M", gerar) as ReturnType<typeof gerar>;
const mascara = cronometrar("select() cru", () => selecionar(dados, 500)) as Uint8Array;
const caminhos = cronometrar("construir Path2D", () => construirCaminhos(dados, mascara)) as Map<number, Path2D>;
linhas.push(`sobreviventes: ${mascara.reduce((a, b) => a + b, 0)}`);
linhas.push(`grupos de caminho: ${caminhos.size}`);
document.querySelector("#saida")!.textContent = linhas.join("\n");
```

- [ ] **Passo 8: rodar a medição**

```bash
cd web/frontend && npm run dev
```

Abra `http://localhost:5173/medicao/custo.html` e espere os quatro números.
Rode duas vezes e use a segunda, para o JIT já estar aquecido.

- [ ] **Passo 9: registrar o resultado**

Crie `web/frontend/medicao/RESULTADO.md` com os números medidos, a data, o
navegador e a máquina. Depois escreva, em uma frase, qual das três leituras vale:

- `select()` acima de ~50 ms → o worker se justifica, siga o plano como está.
- `select()` abaixo de ~50 ms **e** `Path2D` acima de ~200 ms → o gargalo é o
  desenho, não a decisão. O worker ajuda pouco; **pare e reabra a arquitetura**
  antes da tarefa 5.
- Ambos abaixo desses valores → o worker é desnecessário. **Pare e reabra a
  arquitetura**: as tarefas 5 e 6 encolhem para uma só, sem worker.

Não siga para a tarefa 2 sem essa frase escrita. Ela é o deliverable.

- [ ] **Passo 10: commit**

```bash
git add web/frontend/
git commit -m "Andaime do frontend e a medicao que decide a arquitetura"
```

---

### Tarefa 2: `select.ts` contra os 1024 casos do contrato

A tarefa mais importante da etapa. É ela que sustenta a promessa de que a prévia
é o DXF.

**Arquivos:**
- Criar: `web/frontend/src/select.ts`
- Criar: `web/frontend/testes/ajuda/contrato.ts`
- Testar: `web/frontend/testes/select.test.ts`

**Interfaces:**
- Consome: `tests/casos_select.json` (não modificar)
- Produz:
  - `type Opcoes = { excluded_layers: string[]; drop_fills: boolean; min_len_mm: number; dedup: boolean; join_polylines: boolean; round_coords: boolean }`
  - `type Atributos = { kind: Uint8Array; layer_id: Uint32Array; is_fill: Uint8Array; length_um: Uint32Array; dup_group: Int32Array; byte_cost: Uint32Array; layers: string[]; n_groups: number }`
  - `const SEGMENTO = 0`
  - `function selecionar(attrs: Atributos, opts: Opcoes): Uint8Array`
  - do auxiliar: `function carregarContrato(): { casos: Caso[]; tabelas: Atributos[] }`

- [ ] **Passo 1: escrever o auxiliar do contrato**

`web/frontend/testes/ajuda/contrato.ts`:

```ts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { Atributos, Opcoes } from "../../src/select.js";

/** Código numérico do `kind`, igual ao de web/api/packing.py. */
const CODIGO: Record<string, number> = {
  Segment: 0, Polyline: 1, Arc: 2, Bezier: 3, TextItem: 4,
};

export type Caso = {
  nome: string;
  tabela: number;
  opcoes: Opcoes;
  esperado: string;        // máscara como texto de 0 e 1
  bytes_esperado: number;
};

/**
 * Lê o contrato congelado e traduz o `kind` de string para código.
 *
 * A tradução mora aqui, e só aqui: o `select.ts` compara inteiros porque é isso
 * que chega do `geometry.bin`, e o `casos_select.json` guarda strings porque é
 * assim que o `classify()` do Python as produz. Nenhum dos dois muda por causa
 * do outro.
 */
export function carregarContrato(): { casos: Caso[]; tabelas: Atributos[] } {
  const caminho = fileURLToPath(
    new URL("../../../../tests/casos_select.json", import.meta.url));
  const cru = JSON.parse(readFileSync(caminho, "utf-8"));

  const tabelas: Atributos[] = cru.tabelas.map((t: any) => ({
    kind: Uint8Array.from(t.kind, (nome: string) => {
      const codigo = CODIGO[nome];
      if (codigo === undefined) throw new Error(`kind desconhecido: ${nome}`);
      return codigo;
    }),
    layer_id: Uint32Array.from(t.layer_id),
    is_fill: Uint8Array.from(t.is_fill, (v: boolean) => (v ? 1 : 0)),
    length_um: Uint32Array.from(t.length_um),
    dup_group: Int32Array.from(t.dup_group),
    byte_cost: Uint32Array.from(t.byte_cost),
    layers: t.layers,
    n_groups: t.n_groups,
  }));

  return { casos: cru.casos, tabelas };
}

/** Converte a máscara em texto de 0 e 1, como o contrato a guarda. */
export function comoTexto(mascara: Uint8Array): string {
  let saida = "";
  for (const v of mascara) saida += v ? "1" : "0";
  return saida;
}
```

- [ ] **Passo 2: escrever o teste que falha**

`web/frontend/testes/select.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { carregarContrato, comoTexto } from "./ajuda/contrato.js";
import { selecionar } from "../src/select.js";

const { casos, tabelas } = carregarContrato();

describe("select.ts espelha optimize.select()", () => {
  it("carrega o contrato inteiro", () => {
    expect(casos.length).toBe(1024);
    expect(tabelas.length).toBe(4);
  });

  for (const caso of casos) {
    it(`caso ${caso.nome}`, () => {
      const attrs = tabelas[caso.tabela]!;
      const obtido = comoTexto(selecionar(attrs, caso.opcoes));
      if (obtido !== caso.esperado) {
        // Apontar o primeiro índice divergente: comparar duas strings de 300
        // caracteres a olho não diz nada.
        let i = 0;
        while (i < obtido.length && obtido[i] === caso.esperado[i]) i++;
        throw new Error(
          `divergiu no índice ${i}: esperado ${caso.esperado[i]}, ` +
          `obtido ${obtido[i]} (kind=${attrs.kind[i]}, ` +
          `length_um=${attrs.length_um[i]}, dup_group=${attrs.dup_group[i]})`);
      }
      expect(obtido).toBe(caso.esperado);
    });
  }
});
```

- [ ] **Passo 3: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação — `src/select.ts` ainda não existe.

- [ ] **Passo 4: implementar `web/frontend/src/select.ts`**

```ts
/**
 * Espelho TypeScript de `optimize.select()`.
 *
 * Toda a paridade com o Python está presa por `tests/casos_select.json`. Se
 * mudar qualquer coisa aqui, os 1024 casos dizem se você quebrou o contrato.
 */

export const SEGMENTO = 0;

export type Opcoes = {
  excluded_layers: string[];
  drop_fills: boolean;
  min_len_mm: number;
  dedup: boolean;
  join_polylines: boolean;
  round_coords: boolean;
};

export type Atributos = {
  kind: Uint8Array;
  layer_id: Uint32Array;
  is_fill: Uint8Array;
  length_um: Uint32Array;
  dup_group: Int32Array;
  byte_cost: Uint32Array;
  layers: string[];
  n_groups: number;
};

export function selecionar(attrs: Atributos, opts: Opcoes): Uint8Array {
  const n = attrs.kind.length;

  // Conjunto de layers excluídos montado uma vez, antes do laço: dentro dele
  // seria uma busca por entidade, em até 3 milhões delas.
  const excluidos = new Set<number>();
  const nomesExcluidos = new Set(opts.excluded_layers);
  for (let i = 0; i < attrs.layers.length; i++) {
    if (nomesExcluidos.has(attrs.layers[i]!)) excluidos.add(i);
  }

  // `Math.round` e não `Math.trunc`: o Python escreve `int(x + 0.5)`
  // exatamente para casar com esta linha. Ver a docstring do select().
  const minLenUm = Math.round(opts.min_len_mm * 1000.0);

  const emitido = new Uint8Array(attrs.n_groups);
  const mascara = new Uint8Array(n);

  for (let i = 0; i < n; i++) {
    if (excluidos.has(attrs.layer_id[i]!)) continue;
    if (opts.drop_fills && attrs.is_fill[i]) continue;
    if (attrs.kind[i] === SEGMENTO) {
      // O filtro de comprimento vem antes de reservar o grupo: um segmento
      // curto demais não pode impedir o próximo do mesmo grupo de ser emitido.
      if (minLenUm > 0 && attrs.length_um[i]! < minLenUm) continue;
      if (opts.dedup) {
        const g = attrs.dup_group[i]!;
        if (emitido[g]) continue;
        emitido[g] = 1;
      }
    }
    mascara[i] = 1;
  }

  return mascara;
}
```

- [ ] **Passo 5: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: 1025 testes verdes (os 1024 casos mais o de carga).

- [ ] **Passo 6: provar que o teste pega o defeito**

Troque, temporariamente, `Math.round` por `Math.trunc` no `minLenUm` e rode de
novo. Algum caso tem de falhar — o contrato exercita o limiar de propósito
(commit `dc397fe`). Se **nenhum** falhar, o contrato não está cobrindo o que
promete, e isso é achado a registrar antes de seguir. Desfaça a troca.

- [ ] **Passo 7: commit**

```bash
git add web/frontend/src/select.ts web/frontend/testes/
git commit -m "select.ts espelhando o Python, preso pelos 1024 casos do contrato"
```

---

### Tarefa 3: `estimativa.ts`, o mesmo contrato

**Arquivos:**
- Criar: `web/frontend/src/estimativa.ts`
- Modificar: `web/frontend/testes/select.test.ts`

**Interfaces:**
- Consome: `Atributos`, `Opcoes`, `SEGMENTO` de `src/select.ts`
- Produz: `function estimarBytes(attrs: Atributos, mascara: Uint8Array, opts: Opcoes): number`

- [ ] **Passo 1: acrescentar o teste que falha**

Ao fim do `describe` em `web/frontend/testes/select.test.ts`, dentro do laço
`for (const caso of casos)`, acrescente um segundo `it`:

```ts
    it(`bytes do caso ${caso.nome}`, () => {
      const attrs = tabelas[caso.tabela]!;
      const mascara = selecionar(attrs, caso.opcoes);
      expect(estimarBytes(attrs, mascara, caso.opcoes)).toBe(caso.bytes_esperado);
    });
```

E no topo do arquivo:

```ts
import { estimarBytes } from "../src/estimativa.js";
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/estimativa.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/estimativa.ts`**

```ts
/**
 * Espelho TypeScript de `optimize.estimate_bytes()`.
 *
 * O único número aproximado da tela. A aproximação está no ramo de "unir em
 * polilinhas": quanto os segmentos se encadeiam depende de quais sobreviveram
 * aos filtros, e medir isso de verdade exigiria fazer a junção. O Python aceita
 * estatísticas de uma junção real quando as tem; o navegador nunca tem, então
 * aqui existe só o ramo aproximado — e é esse que o contrato congela.
 */
import { SEGMENTO, type Atributos, type Opcoes } from "./select.js";

const BYTES_SEGMENTO = 210;
const POLI_BASE = 180;
const POLI_POR_PONTO = 42;
const FATOR_ARREDONDAR = 0.78;
const CABECALHO = 60_000;
const FRACAO_ENCADEADA = 0.85;
const SEGMENTOS_POR_CADEIA = 12;

export function estimarBytes(attrs: Atributos, mascara: Uint8Array,
                             opts: Opcoes): number {
  let total = 0;
  let nSeg = 0;
  for (let i = 0; i < mascara.length; i++) {
    if (!mascara[i]) continue;
    if (attrs.kind[i] === SEGMENTO) nSeg += 1;
    else total += attrs.byte_cost[i]!;
  }

  if (opts.join_polylines && nSeg) {
    // `Math.trunc`, não `Math.round`: o Python usa `int()`, que trunca.
    const encadeados = Math.trunc(nSeg * FRACAO_ENCADEADA);
    const sozinhos = nSeg - encadeados;
    const nPoli = Math.max(1, Math.floor(encadeados / SEGMENTOS_POR_CADEIA));
    total += nPoli * POLI_BASE + (encadeados + nPoli) * POLI_POR_PONTO;
    total += sozinhos * BYTES_SEGMENTO;
  } else {
    total += nSeg * BYTES_SEGMENTO;
  }

  total += CABECALHO;
  if (opts.round_coords) total = Math.trunc(total * FATOR_ARREDONDAR);
  return total;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: 2049 testes verdes.

- [ ] **Passo 5: commit**

```bash
git add web/frontend/src/estimativa.ts web/frontend/testes/select.test.ts
git commit -m "estimativa.ts espelhando estimate_bytes, no mesmo contrato"
```

---

### Tarefa 4: `formato.ts`, o leitor do binário

Testado contra uma fixture gerada pelo Python. Testar o TypeScript contra ele
mesmo não provaria nada: o que precisa ficar preso é a ponte entre as duas
implementações do formato.

**Arquivos:**
- Criar: `tests/gerar_fixture_geometria.py`
- Criar: `tests/test_fixture_geometria.py`
- Criar: `tests/fixtures/geometria_exemplo.bin` e `.json` (gerados)
- Criar: `web/frontend/src/formato.ts`
- Testar: `web/frontend/testes/formato.test.ts`

**Interfaces:**
- Consome: `web/api/packing.py`
- Produz:
  - `type Geometria = Atributos & { idx: Uint32Array; cor: Uint32Array; coord_off: Uint32Array; coords: Float32Array; texto_off: Uint32Array; texto: Uint8Array; n: number }`
  - `function lerGeometria(buffer: ArrayBuffer, layers: string[], nGroups: number): Geometria`
  - `function coordenadasDe(g: Geometria, i: number): Float32Array`
  - `function textoDe(g: Geometria, i: number): string`

- [ ] **Passo 1: gerador da fixture, `tests/gerar_fixture_geometria.py`**

```python
"""Gera a fixture que o leitor TypeScript do formato binário confere.

Determinística: regerar não pode sujar o `git diff`. Se sujar, o formato mudou.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.extractor import ExtractionResult
from pdftodxf.geometry import Arc, Bezier, Polyline, Segment, TextItem
from pdftodxf.optimize import classify
from web.api import packing

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def amostra() -> ExtractionResult:
    """Um exemplar de cada tipo, com cor, texto acentuado e preenchimento."""
    ents = [
        Segment(p1=(0.0, 0.0), p2=(30.0, 40.0), layer="PAREDES",
                color=(1.0, 0.0, 0.0)),
        Polyline(points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], closed=True,
                 layer="COTAS", is_fill=True),
        Arc(center=(5.0, 5.0), radius=2.0, start_angle=0.0, end_angle=90.0,
            layer="PAREDES"),
        Bezier(p0=(0.0, 0.0), p1=(1.0, 2.0), p2=(3.0, 4.0), p3=(5.0, 6.0),
               layer="COTAS"),
        TextItem(text="Sala de máquinas", position=(2.0, 3.0), height=4.0,
                 rotation=90.0, width=25.0, layer="TEXTO"),
        Segment(p1=(0.0, 0.0), p2=(30.0, 40.0), layer="PAREDES"),
    ]
    return ExtractionResult(entities=ents, page_width=595.0, page_height=842.0,
                            layers={"PAREDES", "COTAS", "TEXTO"})


def main() -> None:
    os.makedirs(PASTA, exist_ok=True)
    r = amostra()
    a = classify(r.entities)
    indices = list(range(len(r.entities)))
    dados = packing.empacotar(r, a, indices)

    with open(os.path.join(PASTA, "geometria_exemplo.bin"), "wb") as f:
        f.write(dados)

    lido = packing.desempacotar(dados)
    esperado = {
        "n": lido["n"],
        "layers": a.layers,
        "n_groups": a.n_groups,
        "idx": lido["idx"],
        "kind": lido["kind"],
        "layer_id": lido["layer_id"],
        "is_fill": lido["is_fill"],
        "length_um": lido["length_um"],
        "dup_group": lido["dup_group"],
        "byte_cost": lido["byte_cost"],
        "cor": lido["cor"],
        "coordenadas": [[round(v, 4) for v in lido["coords_de"](i)]
                        for i in range(lido["n"])],
        "textos": [lido["texto_de"](i) for i in range(lido["n"])],
    }
    caminho = os.path.join(PASTA, "geometria_exemplo.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(esperado, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"fixture gerada: {lido['n']} entidades, {len(dados)} bytes")


if __name__ == "__main__":
    main()
```

- [ ] **Passo 2: gerar a fixture**

```bash
./.venv/Scripts/python.exe tests/gerar_fixture_geometria.py
```

Esperado: `fixture gerada: 6 entidades, <N> bytes`

- [ ] **Passo 3: teste Python que guarda a fixture, `tests/test_fixture_geometria.py`**

Sem ele, a fixture envelhece em silêncio quando o `packing.py` mudar.

```python
"""A fixture do formato binário continua batendo com o packing.py."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.gerar_fixture_geometria import PASTA, amostra
from pdftodxf.optimize import classify
from web.api import packing


def test_fixture_esta_atualizada():
    r = amostra()
    a = classify(r.entities)
    agora = packing.empacotar(r, a, list(range(len(r.entities))))
    with open(os.path.join(PASTA, "geometria_exemplo.bin"), "rb") as f:
        gravado = f.read()
    assert agora == gravado, (
        "o packing.py mudou e a fixture ficou para trás. Rode "
        "tests/gerar_fixture_geometria.py e confira o git diff: se ele sujar, "
        "o formato mudou e o leitor TypeScript precisa acompanhar.")
    print("OK: a fixture do formato binário está atualizada")


def test_json_descreve_o_bin():
    with open(os.path.join(PASTA, "geometria_exemplo.json"), encoding="utf-8") as f:
        esperado = json.load(f)
    with open(os.path.join(PASTA, "geometria_exemplo.bin"), "rb") as f:
        lido = packing.desempacotar(f.read())
    assert lido["n"] == esperado["n"]
    assert lido["kind"] == esperado["kind"]
    assert lido["cor"] == esperado["cor"]
    print("OK: o JSON da fixture descreve o binário")


if __name__ == "__main__":
    test_fixture_esta_atualizada()
    test_json_descreve_o_bin()
    print("Todos os testes da fixture passaram.")
```

- [ ] **Passo 4: rodar o teste Python**

```bash
./.venv/Scripts/python.exe tests/test_fixture_geometria.py
```

Esperado: as duas linhas `OK:` e `Todos os testes da fixture passaram.`

- [ ] **Passo 5: escrever o teste TypeScript que falha**

`web/frontend/testes/formato.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { coordenadasDe, lerGeometria, textoDe } from "../src/formato.js";

function caminhoFixture(nome: string): string {
  return fileURLToPath(new URL(`../../../tests/fixtures/${nome}`, import.meta.url));
}

const cru = readFileSync(caminhoFixture("geometria_exemplo.bin"));
const buffer = cru.buffer.slice(cru.byteOffset, cru.byteOffset + cru.byteLength);
const esperado = JSON.parse(readFileSync(caminhoFixture("geometria_exemplo.json"), "utf-8"));

describe("formato.ts lê o que o packing.py escreveu", () => {
  const g = lerGeometria(buffer as ArrayBuffer, esperado.layers, esperado.n_groups);

  it("conta as entidades", () => {
    expect(g.n).toBe(esperado.n);
  });

  it("lê os atributos", () => {
    expect([...g.idx]).toEqual(esperado.idx);
    expect([...g.kind]).toEqual(esperado.kind);
    expect([...g.layer_id]).toEqual(esperado.layer_id);
    expect([...g.is_fill]).toEqual(esperado.is_fill);
    expect([...g.length_um]).toEqual(esperado.length_um);
    expect([...g.dup_group]).toEqual(esperado.dup_group);
    expect([...g.byte_cost]).toEqual(esperado.byte_cost);
    expect([...g.cor]).toEqual(esperado.cor);
  });

  it("lê as coordenadas de cada tipo", () => {
    for (let i = 0; i < g.n; i++) {
      const obtido = [...coordenadasDe(g, i)].map((v) => Number(v.toFixed(4)));
      expect(obtido).toEqual(esperado.coordenadas[i]);
    }
  });

  it("lê o texto acentuado", () => {
    for (let i = 0; i < g.n; i++) {
      expect(textoDe(g, i)).toBe(esperado.textos[i]);
    }
  });

  it("recusa um arquivo que não é do formato", () => {
    const lixo = new Uint8Array(64);
    lixo.set([78, 79, 80, 69]);   // "NOPE"
    expect(() => lerGeometria(lixo.buffer, [], 0)).toThrow(/formato/i);
  });
});
```

- [ ] **Passo 6: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/formato.ts`.

- [ ] **Passo 7: implementar `web/frontend/src/formato.ts`**

```ts
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
```

- [ ] **Passo 8: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: todos verdes, incluindo os cinco novos.

- [ ] **Passo 9: commit**

```bash
git add tests/gerar_fixture_geometria.py tests/test_fixture_geometria.py \
        tests/fixtures/ web/frontend/src/formato.ts web/frontend/testes/formato.test.ts
git commit -m "Leitor TypeScript do formato binario, preso por fixture do Python"
```

---

### Tarefa 5: intercalar as duas partes, e o achado do dedup

A tarefa que impede o defeito mais sutil desta etapa. Leia a seção "A divisão em
duas partes não é neutra para o `select()`" do desenho antes de começar.

Em uma frase: com dedup ligado, o `select()` elege **o primeiro de cada grupo de
duplicatas em ordem original**. O esqueleto leva os segmentos longos e o detalhe
os curtos, então dois do mesmo grupo caem em partes diferentes. Decidir por
parte elege dois sobreviventes; concatenar as partes elege o errado, porque
"longos depois curtos" não é ordem original.

**Arquivos:**
- Modificar: `web/frontend/src/formato.ts`
- Criar: `tests/gerar_fixture_intercalacao.py`
- Criar: `tests/fixtures/intercalacao.json` (gerado)
- Testar: `web/frontend/testes/intercalar.test.ts`

**Interfaces:**
- Consome: `lerGeometria`, `coordenadasDe` de `src/formato.ts`; `selecionar` de
  `src/select.ts`
- Produz: `function intercalar(a: Geometria, b: Geometria): Geometria`

- [ ] **Passo 1: gerar a fixture pelo Python, `tests/gerar_fixture_intercalacao.py`**

```python
"""Gera a fixture que prova a intercalação do frontend.

A pergunta que ela responde: dividir em esqueleto e detalhe, intercalar de volta
e rodar o select() dá o mesmo que rodar o select() sobre a lista inteira? Com
dedup ligado, só dá se a intercalação restaurar a ordem original.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.geometry import Segment, TextItem
from pdftodxf.optimize import ExportOptions, classify, select
from web.api import packing

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def amostra():
    """Segmentos com comprimentos variados e duplicatas fartas.

    Os comprimentos alternam para que o `dividir()` espalhe membros do mesmo
    grupo de duplicatas entre as duas partes — que é o caso que interessa.
    """
    ents = []
    for i in range(400):
        comprido = (i % 3 == 0)
        alvo = 40.0 if comprido else 2.0
        # `i % 40` faz pares distantes na lista compartilharem coordenadas,
        # e portanto o grupo de duplicatas.
        x = float(i % 40)
        ents.append(Segment(p1=(x, 0.0), p2=(x, alvo), layer="PAREDES"))
    ents.append(TextItem(text="planta", position=(1.0, 1.0), layer="TEXTO"))
    return ents


def main() -> None:
    os.makedirs(PASTA, exist_ok=True)
    ents = amostra()
    a = classify(ents)
    esqueleto, detalhe, limiar = packing.dividir(a, alvo=60)
    assert esqueleto and detalhe, "a divisão precisa produzir as duas partes"

    opcoes = {"excluded_layers": [], "drop_fills": False, "min_len_mm": 0.0,
              "dedup": True, "join_polylines": False, "round_coords": False}
    opts = ExportOptions(excluded_layers=set(), drop_fills=False,
                         min_len_mm=0.0, dedup=True, join_polylines=False,
                         round_coords=False)
    mascara = select(a, opts)

    fixture = {
        "layers": a.layers,
        "n_groups": a.n_groups,
        "limiar_um": limiar,
        "esqueleto": esqueleto,
        "detalhe": detalhe,
        "opcoes": opcoes,
        "mascara_esperada": "".join("1" if v else "0" for v in mascara),
        "kind": a.kind,
        "layer_id": a.layer_id,
        "is_fill": [bool(v) for v in a.is_fill],
        "length_um": a.length_um,
        "dup_group": a.dup_group,
        "byte_cost": a.byte_cost,
    }
    with open(os.path.join(PASTA, "intercalacao.json"), "w",
              encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=1, sort_keys=True)

    cruzam = sum(1 for g in set(a.dup_group) if g >= 0
                 and any(a.dup_group[i] == g for i in esqueleto)
                 and any(a.dup_group[i] == g for i in detalhe))
    print(f"fixture gerada: {len(ents)} entidades, esqueleto {len(esqueleto)}, "
          f"detalhe {len(detalhe)}, {cruzam} grupos atravessando as duas partes")
    assert cruzam > 0, (
        "nenhum grupo de duplicatas ficou dividido entre as partes: a fixture "
        "não exercita o que se propõe a exercitar")


if __name__ == "__main__":
    main()
```

- [ ] **Passo 2: gerar e conferir que a fixture morde**

```bash
./.venv/Scripts/python.exe tests/gerar_fixture_intercalacao.py
```

Esperado: a contagem de grupos atravessando as duas partes tem de ser **maior
que zero**. Se for zero, o `assert` para a geração — e é o certo: uma fixture
que não cruza grupos passaria com qualquer implementação errada.

- [ ] **Passo 3: escrever o teste que falha**

`web/frontend/testes/intercalar.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { intercalar, type Geometria } from "../src/formato.js";
import { selecionar } from "../src/select.js";
import { comoTexto } from "./ajuda/contrato.js";

const f = JSON.parse(readFileSync(
  fileURLToPath(new URL("../../../tests/fixtures/intercalacao.json", import.meta.url)),
  "utf-8"));

const CODIGO: Record<string, number> = {
  Segment: 0, Polyline: 1, Arc: 2, Bezier: 3, TextItem: 4,
};

/** Monta uma parte a partir dos índices que o dividir() escolheu. */
function parte(indices: number[]): Geometria {
  const n = indices.length;
  const g: Geometria = {
    n,
    layers: f.layers,
    n_groups: f.n_groups,
    idx: Uint32Array.from(indices),
    kind: Uint8Array.from(indices, (i) => CODIGO[f.kind[i]]!),
    layer_id: Uint32Array.from(indices, (i) => f.layer_id[i]),
    is_fill: Uint8Array.from(indices, (i) => (f.is_fill[i] ? 1 : 0)),
    length_um: Uint32Array.from(indices, (i) => f.length_um[i]),
    dup_group: Int32Array.from(indices, (i) => f.dup_group[i]),
    byte_cost: Uint32Array.from(indices, (i) => f.byte_cost[i]),
    cor: Uint32Array.from(indices, () => 0xffffffff),
    // Duas coordenadas por entidade, só para a intercalação ter o que mover.
    coord_off: Uint32Array.from({ length: n + 1 }, (_, k) => k * 2),
    coords: Float32Array.from(indices.flatMap((i) => [i, i + 0.5])),
    texto_off: new Uint32Array(n + 1),
    texto: new Uint8Array(0),
  };
  return g;
}

describe("intercalar devolve a ordem original", () => {
  const juntos = intercalar(parte(f.esqueleto), parte(f.detalhe));

  it("cobre tudo, uma vez só, em ordem crescente", () => {
    expect(juntos.n).toBe(f.esqueleto.length + f.detalhe.length);
    expect([...juntos.idx]).toEqual([...juntos.idx].sort((a, b) => a - b));
    expect(new Set(juntos.idx).size).toBe(juntos.n);
  });

  it("carrega as coordenadas junto com a entidade certa", () => {
    for (let k = 0; k < juntos.n; k++) {
      const original = juntos.idx[k]!;
      const c = juntos.coords.subarray(juntos.coord_off[k]!, juntos.coord_off[k + 1]!);
      expect([...c]).toEqual([original, original + 0.5]);
    }
  });

  it("com dedup ligado, bate com o select() do Python sobre a lista inteira", () => {
    expect(comoTexto(selecionar(juntos, f.opcoes))).toBe(f.mascara_esperada);
  });

  it("decidir por parte separada erra — é por isso que a intercalação existe", () => {
    const soEsqueleto = comoTexto(selecionar(parte(f.esqueleto), f.opcoes));
    const soDetalhe = comoTexto(selecionar(parte(f.detalhe), f.opcoes));
    const sobreviventesSeparados =
      [...soEsqueleto, ...soDetalhe].filter((c) => c === "1").length;
    const sobreviventesCertos = [...f.mascara_esperada].filter((c) => c === "1").length;
    expect(sobreviventesSeparados).toBeGreaterThan(sobreviventesCertos);
  });
});
```

O último teste é o que documenta o defeito: decidir por parte produz **mais**
sobreviventes do que o certo, porque cada parte elege o seu.

- [ ] **Passo 4: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `intercalar`.

- [ ] **Passo 5: implementar, ao fim de `web/frontend/src/formato.ts`**

```ts
/**
 * Junta esqueleto e detalhe de volta em ordem de índice original.
 *
 * Não é conveniência: o `select()` com dedup elege o primeiro de cada grupo de
 * duplicatas **em ordem original**, e a divisão separa longos de curtos. Sem
 * restaurar a ordem, a prévia mostra um traço que o DXF descarta. As duas
 * partes já chegam ordenadas, então uma passada basta.
 */
export function intercalar(a: Geometria, b: Geometria): Geometria {
  const n = a.n + b.n;
  const idx = new Uint32Array(n);
  const kind = new Uint8Array(n);
  const layer_id = new Uint32Array(n);
  const is_fill = new Uint8Array(n);
  const length_um = new Uint32Array(n);
  const dup_group = new Int32Array(n);
  const byte_cost = new Uint32Array(n);
  const cor = new Uint32Array(n);
  const coords = new Float32Array(a.coords.length + b.coords.length);
  const coord_off = new Uint32Array(n + 1);
  const texto = new Uint8Array(a.texto.length + b.texto.length);
  const texto_off = new Uint32Array(n + 1);

  let ia = 0, ib = 0, cursorCoord = 0, cursorTexto = 0;
  for (let k = 0; k < n; k++) {
    const daPrimeira = ib >= b.n || (ia < a.n && a.idx[ia]! < b.idx[ib]!);
    const g = daPrimeira ? a : b;
    const i = daPrimeira ? ia++ : ib++;

    idx[k] = g.idx[i]!;
    kind[k] = g.kind[i]!;
    layer_id[k] = g.layer_id[i]!;
    is_fill[k] = g.is_fill[i]!;
    length_um[k] = g.length_um[i]!;
    dup_group[k] = g.dup_group[i]!;
    byte_cost[k] = g.byte_cost[i]!;
    cor[k] = g.cor[i]!;

    const c = g.coords.subarray(g.coord_off[i]!, g.coord_off[i + 1]!);
    coords.set(c, cursorCoord);
    cursorCoord += c.length;
    coord_off[k + 1] = cursorCoord;

    const t = g.texto.subarray(g.texto_off[i]!, g.texto_off[i + 1]!);
    if (t.length) {
      texto.set(t, cursorTexto);
      cursorTexto += t.length;
    }
    texto_off[k + 1] = cursorTexto;
  }

  return {
    n, layers: a.layers, n_groups: a.n_groups,
    idx, kind, layer_id, is_fill, length_um, dup_group, byte_cost, cor,
    coord_off, coords, texto_off, texto,
  };
}
```

- [ ] **Passo 6: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os quatro testes novos verdes.

- [ ] **Passo 7: provar que o teste pega o defeito**

Troque, temporariamente, a linha da escolha por `const daPrimeira = ia < a.n;` —
que concatena em vez de intercalar. O teste da ordem e o do dedup têm de falhar.
Desfaça.

- [ ] **Passo 8: commit**

```bash
git add tests/gerar_fixture_intercalacao.py tests/fixtures/intercalacao.json \
        web/frontend/src/formato.ts web/frontend/testes/intercalar.test.ts
git commit -m "Intercala esqueleto e detalhe em ordem original, com o dedup preso por fixture"
```

---

### Tarefa 6: `worker.ts`

**Arquivos:**
- Criar: `web/frontend/src/worker.ts`
- Testar: `web/frontend/testes/worker.test.ts`

**Interfaces:**
- Consome: `selecionar` de `src/select.ts`, `estimarBytes` de `src/estimativa.ts`
- Produz:
  - `type PedidoWorker = { tipo: "carregar"; decisao: ArraysDeDecisao } | { tipo: "decidir"; opcoes: Opcoes }`
  - `type RespostaWorker = { tipo: "mascara"; mascara: Uint8Array; bytes: number; sobreviventes: number }`
  - `type ArraysDeDecisao = { kind: Uint8Array; layer_id: Uint32Array; is_fill: Uint8Array; length_um: Uint32Array; dup_group: Int32Array; byte_cost: Uint32Array; layers: string[]; n_groups: number }`
  - `function tratarPedido(pedido: PedidoWorker, guardado: { atual: ArraysDeDecisao | null }): RespostaWorker | null`

O `tratarPedido` é separado do `onmessage` de propósito: função pura, testável
no vitest sem subir um worker de verdade.

- [ ] **Passo 1: escrever o teste que falha**

`web/frontend/testes/worker.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { tratarPedido, type ArraysDeDecisao } from "../src/worker.js";
import { carregarContrato, comoTexto } from "./ajuda/contrato.js";

const { casos, tabelas } = carregarContrato();

function decisaoDe(t: (typeof tabelas)[number]): ArraysDeDecisao {
  return {
    kind: t.kind, layer_id: t.layer_id, is_fill: t.is_fill,
    length_um: t.length_um, dup_group: t.dup_group, byte_cost: t.byte_cost,
    layers: t.layers, n_groups: t.n_groups,
  };
}

describe("worker", () => {
  it("guarda os arrays e decide sobre eles", () => {
    const caso = casos[0]!;
    const guardado: { atual: ArraysDeDecisao | null } = { atual: null };

    expect(tratarPedido({ tipo: "carregar", decisao: decisaoDe(tabelas[caso.tabela]!) },
                        guardado)).toBeNull();
    expect(guardado.atual).not.toBeNull();

    const r = tratarPedido({ tipo: "decidir", opcoes: caso.opcoes }, guardado);
    expect(r).not.toBeNull();
    expect(comoTexto(r!.mascara)).toBe(caso.esperado);
    expect(r!.bytes).toBe(caso.bytes_esperado);
    expect(r!.sobreviventes).toBe([...caso.esperado].filter((c) => c === "1").length);
  });

  it("recusa decidir antes de ter recebido a geometria", () => {
    const guardado: { atual: ArraysDeDecisao | null } = { atual: null };
    expect(() => tratarPedido({ tipo: "decidir", opcoes: casos[0]!.opcoes }, guardado))
      .toThrow(/geometria/i);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/worker.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/worker.ts`**

```ts
/**
 * Web Worker que decide quem entra no desenho.
 *
 * Recebe só os arrays que o `select()` lê — não as coordenadas. Quem desenha é
 * a thread principal, e ela precisa das coordenadas; mandá-las também para cá
 * seria pagar dezenas de megabytes de cópia por nada.
 */
import { estimarBytes } from "./estimativa.js";
import { selecionar, type Atributos, type Opcoes } from "./select.js";

export type ArraysDeDecisao = {
  kind: Uint8Array;
  layer_id: Uint32Array;
  is_fill: Uint8Array;
  length_um: Uint32Array;
  dup_group: Int32Array;
  byte_cost: Uint32Array;
  layers: string[];
  n_groups: number;
};

export type PedidoWorker =
  | { tipo: "carregar"; decisao: ArraysDeDecisao }
  | { tipo: "decidir"; opcoes: Opcoes };

export type RespostaWorker = {
  tipo: "mascara";
  mascara: Uint8Array;
  bytes: number;
  sobreviventes: number;
};

/** Separado do `onmessage` para ser função pura e testável sem subir worker. */
export function tratarPedido(pedido: PedidoWorker,
                             guardado: { atual: ArraysDeDecisao | null }):
                             RespostaWorker | null {
  if (pedido.tipo === "carregar") {
    guardado.atual = pedido.decisao;
    return null;
  }
  const d = guardado.atual;
  if (!d) throw new Error("worker: pediram decisão antes de mandar a geometria");

  const attrs = d as Atributos;
  const mascara = selecionar(attrs, pedido.opcoes);
  let sobreviventes = 0;
  for (const v of mascara) if (v) sobreviventes += 1;
  return {
    tipo: "mascara",
    mascara,
    bytes: estimarBytes(attrs, mascara, pedido.opcoes),
    sobreviventes,
  };
}

// Só quando de fato roda como worker: no vitest este módulo é importado como
// biblioteca, e `self.onmessage` não existe.
if (typeof self !== "undefined" && "onmessage" in self) {
  // O `tsconfig` carrega as bibliotecas DOM e WebWorker ao mesmo tempo, então o
  // TypeScript tipa `self` como `Window`. O molde diz a ele o que este arquivo
  // de fato é quando roda de verdade.
  const escopo = self as unknown as DedicatedWorkerGlobalScope;
  const guardado: { atual: ArraysDeDecisao | null } = { atual: null };
  escopo.onmessage = (evento: MessageEvent<PedidoWorker>) => {
    const resposta = tratarPedido(evento.data, guardado);
    // A máscara vai transferida: numa planta no teto são 3 MB por clique, e
    // copiá-los a cada opção ligada seria desperdício visível.
    if (resposta) escopo.postMessage(resposta, [resposta.mascara.buffer]);
  };
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os dois testes novos verdes.

- [ ] **Passo 5: commit**

```bash
git add web/frontend/src/worker.ts web/frontend/testes/worker.test.ts
git commit -m "Worker que roda o select e a estimativa fora da thread da interface"
```

---

### Tarefa 7: `api.ts`, o cliente HTTP

**Arquivos:**
- Criar: `web/frontend/src/api.ts`
- Testar: `web/frontend/testes/api.test.ts`

**Interfaces:**
- Consome: as rotas da etapa 2 (ver `web/README.md`)
- Produz:
  - `type Ficha = { job_id: string; nome: string; n_paginas: number }`
  - `type EstadoPagina = { situacao: "na_fila" | "extraindo" | "pronta" | "erro"; codigo?: string; mensagem?: string }`
  - `type Meta = { n_entidades: number; layers: string[]; largura_pt: number; altura_pt: number; limiar_esqueleto_um: number; partes: { esqueleto: number; detalhe: number } }`
  - `class ErroDaApi extends Error { codigo: string; status: number }`
  - `function enviarPdf(arquivo: File, sinal?: AbortSignal): Promise<Ficha>`
  - `function pedirExtracao(job: string, pagina: number, sinal?: AbortSignal): Promise<EstadoPagina>`
  - `function lerEstado(job: string, pagina: number, sinal?: AbortSignal): Promise<EstadoPagina>`
  - `function esperarPagina(job: string, pagina: number, sinal: AbortSignal, aoMudar: (e: EstadoPagina) => void): Promise<EstadoPagina>`
  - `function lerMeta(job: string, pagina: number, sinal?: AbortSignal): Promise<Meta>`
  - `function lerGeometriaBruta(job: string, pagina: number, parte: "esqueleto" | "detalhe", sinal?: AbortSignal): Promise<ArrayBuffer>`
  - `function exportar(job: string, pagina: number, pedido: PedidoDeExportacao, sinal?: AbortSignal): Promise<{ chave: string; url: string; cache: boolean; entidades: number }>`

- [ ] **Passo 1: escrever o teste que falha**

`web/frontend/testes/api.test.ts`. Usa um `fetch` de mentira: o que se testa
aqui é o comportamento do cliente, não o servidor — esse já tem os testes da
etapa 2.

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErroDaApi, esperarPagina, lerEstado } from "../src/api.js";

function respostaDe(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), {
    status, headers: { "content-type": "application/json" },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("api.ts", () => {
  it("converte erro do servidor em ErroDaApi com o status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      respostaDe({ detail: "Trabalho não encontrado." }, 404)));
    await expect(lerEstado("a".repeat(32), 1)).rejects.toSatisfy(
      (e: unknown) => e instanceof ErroDaApi && e.status === 404);
  });

  it("espera a página sair da fila e avisa a cada mudança", async () => {
    const sequencia = [
      { situacao: "na_fila" },
      { situacao: "extraindo" },
      { situacao: "pronta", n_entidades: 8 },
    ];
    let chamada = 0;
    vi.stubGlobal("fetch", vi.fn(async () =>
      respostaDe(sequencia[Math.min(chamada++, sequencia.length - 1)])));

    const vistos: string[] = [];
    const controle = new AbortController();
    const final = await esperarPagina("a".repeat(32), 1, controle.signal,
                                      (e) => vistos.push(e.situacao));
    expect(final.situacao).toBe("pronta");
    expect(vistos).toEqual(["na_fila", "extraindo", "pronta"]);
  });

  it("para de esperar quando o sinal é abortado", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => respostaDe({ situacao: "na_fila" })));
    const controle = new AbortController();
    const promessa = esperarPagina("a".repeat(32), 1, controle.signal, () => {});
    controle.abort();
    await expect(promessa).rejects.toThrow(/abort/i);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/api.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/api.ts`**

```ts
/**
 * Cliente HTTP das rotas da etapa 2.
 *
 * Todo pedido aceita um `AbortSignal`. Não é enfeite: trocar de página no meio
 * do carregamento deixa buscas em voo, e o detalhe da página anterior chegando
 * depois contamina o canvas da página nova — defeito silencioso, que só aparece
 * com rede lenta.
 */

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

async function pedir(caminho: string, init: RequestInit = {}): Promise<Response> {
  const resposta = await fetch(caminho, init);
  if (!resposta.ok) {
    let detalhe = `HTTP ${resposta.status}`;
    try {
      const corpo = await resposta.json();
      if (corpo?.detail) detalhe = String(corpo.detail);
    } catch {
      // Resposta sem JSON: fica o status, que já diz o suficiente.
    }
    throw new ErroDaApi(resposta.status, detalhe);
  }
  return resposta;
}

export async function enviarPdf(arquivo: File, sinal?: AbortSignal): Promise<Ficha> {
  const forma = new FormData();
  forma.append("arquivo", arquivo);
  const r = await pedir("/api/jobs", { method: "POST", body: forma, signal: sinal });
  return r.json();
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

export async function lerGeometriaBruta(job: string, pagina: number,
                                        parte: "esqueleto" | "detalhe",
                                        sinal?: AbortSignal): Promise<ArrayBuffer> {
  const r = await pedir(
    `/api/jobs/${job}/pages/${pagina}/geometry.bin?parte=${parte}`,
    { signal: sinal });
  return r.arrayBuffer();
}

export async function exportar(job: string, pagina: number,
                               pedido: PedidoDeExportacao, sinal?: AbortSignal) {
  const r = await pedir(`/api/jobs/${job}/pages/${pagina}/export`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(pedido),
    signal: sinal,
  });
  return r.json() as Promise<{ chave: string; url: string; cache: boolean;
                               entidades: number }>;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os três testes novos verdes.

- [ ] **Passo 5: commit**

```bash
git add web/frontend/src/api.ts web/frontend/testes/api.test.ts
git commit -m "Cliente HTTP com recuo crescente e aborto por troca de pagina"
```

---

### Tarefa 8: `canvas.ts`, o renderizador

O elo que a promessa central atravessa: o que aparece na tela tem de ser
exatamente o que a máscara escolheu.

**Arquivos:**
- Criar: `web/frontend/src/canvas.ts`
- Criar: `web/frontend/testes/ajuda/canvas2d.ts`
- Testar: `web/frontend/testes/canvas.test.ts`

**Interfaces:**
- Consome: `Geometria`, `coordenadasDe`, `textoDe`, `SEM_COR` de `src/formato.ts`
- Produz:
  - `interface CaminhoDesenhavel { moveTo(x,y): void; lineTo(x,y): void; arc(cx,cy,r,a0,a1): void; bezierCurveTo(x1,y1,x2,y2,x3,y3): void; closePath(): void }`
  - `type Grupo = { layerId: number; cor: number; caminho: CaminhoDesenhavel }`
  - `type TextoDesenhavel = { x: number; y: number; altura: number; rotacao: number; texto: string; cor: number }`
  - `type Desenho = { grupos: Grupo[]; textos: TextoDesenhavel[] }`
  - `type Vista = { escala: number; dx: number; dy: number }`
  - `function montarDesenho(g: Geometria, mascara: Uint8Array, criarCaminho: () => CaminhoDesenhavel): Desenho`
  - `function enquadrar(larguraPt: number, alturaPt: number, larguraTela: number, alturaTela: number): Vista`
  - `function pontoDaTela(v: Vista, x: number, y: number): { x: number; y: number }`
  - `function pontoDoPapel(v: Vista, x: number, y: number): { x: number; y: number }`
  - `function pintar(ctx: CanvasRenderingContext2D, d: Desenho, v: Vista, fundo: string): void`

`montarDesenho` recebe a fábrica de caminhos em vez de usar `new Path2D()`
direto. Não é abstração gratuita: no vitest não existe `Path2D`, e injetar a
fábrica é o que permite gravar o que foi desenhado sem subir navegador.

- [ ] **Passo 1: o contexto de mentira, `web/frontend/testes/ajuda/canvas2d.ts`**

```ts
/** Caminho que grava o que mandaram desenhar, no lugar do Path2D do navegador. */
export class CaminhoGravado {
  readonly chamadas: Array<[string, ...number[]]> = [];
  moveTo(x: number, y: number) { this.chamadas.push(["moveTo", x, y]); }
  lineTo(x: number, y: number) { this.chamadas.push(["lineTo", x, y]); }
  arc(cx: number, cy: number, r: number, a0: number, a1: number) {
    this.chamadas.push(["arc", cx, cy, r, a0, a1]);
  }
  bezierCurveTo(x1: number, y1: number, x2: number, y2: number,
                x3: number, y3: number) {
    this.chamadas.push(["bezierCurveTo", x1, y1, x2, y2, x3, y3]);
  }
  closePath() { this.chamadas.push(["closePath"]); }

  /** Quantos traços começaram: um `moveTo` por entidade desenhada. */
  get inicios(): number {
    return this.chamadas.filter((c) => c[0] === "moveTo" || c[0] === "arc").length;
  }
}

export const criarCaminhoGravado = () => new CaminhoGravado();
```

- [ ] **Passo 2: escrever o teste que falha**

`web/frontend/testes/canvas.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { montarDesenho, enquadrar, pontoDoPapel, pontoDaTela } from "../src/canvas.js";
import { lerGeometria } from "../src/formato.js";
import { CaminhoGravado, criarCaminhoGravado } from "./ajuda/canvas2d.js";

function fixture(nome: string) {
  return fileURLToPath(new URL(`../../../tests/fixtures/${nome}`, import.meta.url));
}
const cru = readFileSync(fixture("geometria_exemplo.bin"));
const buffer = cru.buffer.slice(cru.byteOffset, cru.byteOffset + cru.byteLength);
const esperado = JSON.parse(readFileSync(fixture("geometria_exemplo.json"), "utf-8"));
const g = lerGeometria(buffer as ArrayBuffer, esperado.layers, esperado.n_groups);

describe("canvas.ts desenha exatamente o que a máscara escolheu", () => {
  it("desenha tudo quando a máscara é toda 1", () => {
    const mascara = new Uint8Array(g.n).fill(1);
    const d = montarDesenho(g, mascara, criarCaminhoGravado);
    const inicios = d.grupos.reduce(
      (soma, gr) => soma + (gr.caminho as CaminhoGravado).inicios, 0);
    const textos = d.textos.length;
    expect(inicios + textos).toBe(g.n);
  });

  it("não desenha nada quando a máscara é toda 0", () => {
    const d = montarDesenho(g, new Uint8Array(g.n), criarCaminhoGravado);
    expect(d.grupos).toEqual([]);
    expect(d.textos).toEqual([]);
  });

  it("desenha só o que a máscara marcou", () => {
    const mascara = new Uint8Array(g.n);
    mascara[0] = 1;                       // o primeiro segmento, vermelho
    const d = montarDesenho(g, mascara, criarCaminhoGravado);
    const inicios = d.grupos.reduce(
      (soma, gr) => soma + (gr.caminho as CaminhoGravado).inicios, 0);
    expect(inicios + d.textos.length).toBe(1);
    expect(d.grupos[0]!.cor).toBe(0xff0000);
  });

  it("agrupa por (layer, cor), não uma entidade por caminho", () => {
    const mascara = new Uint8Array(g.n).fill(1);
    const d = montarDesenho(g, mascara, criarCaminhoGravado);
    const chaves = new Set(d.grupos.map((gr) => `${gr.layerId}|${gr.cor}`));
    expect(chaves.size).toBe(d.grupos.length);
    expect(d.grupos.length).toBeLessThan(g.n);
  });

  it("enquadra a folha inteira e inverte o eixo Y", () => {
    const v = enquadrar(595, 842, 1000, 800);
    const canto = pontoDaTela(v, 0, 0);          // origem do PDF: canto de baixo
    const topo = pontoDaTela(v, 0, 842);
    expect(canto.y).toBeGreaterThan(topo.y);
    expect(v.escala).toBeCloseTo(800 / 842, 5);
  });

  it("converter tela → papel → tela devolve o mesmo ponto", () => {
    const v = enquadrar(595, 842, 1000, 800);
    const papel = pontoDoPapel(v, 321, 456);
    const volta = pontoDaTela(v, papel.x, papel.y);
    expect(volta.x).toBeCloseTo(321, 6);
    expect(volta.y).toBeCloseTo(456, 6);
  });
});
```

- [ ] **Passo 3: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/canvas.ts`.

- [ ] **Passo 4: implementar `web/frontend/src/canvas.ts`**

```ts
/**
 * Renderizador do canvas.
 *
 * Um caminho por grupo de (layer, cor), não um por entidade: numa planta no
 * teto seriam 3 milhões de objetos de caminho, e o navegador não aguenta. O
 * caminho é reconstruído quando a seleção muda; pan e zoom só mexem na
 * transformação.
 */
import { SEM_COR, coordenadasDe, textoDe, type Geometria } from "./formato.js";

const SEGMENTO = 0, POLILINHA = 1, ARCO = 2, BEZIER = 3, TEXTO = 4;

/** O mínimo do Path2D que este módulo usa — e o que o teste consegue gravar. */
export interface CaminhoDesenhavel {
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  arc(cx: number, cy: number, r: number, a0: number, a1: number): void;
  bezierCurveTo(x1: number, y1: number, x2: number, y2: number,
                x3: number, y3: number): void;
  closePath(): void;
}

export type Grupo = { layerId: number; cor: number; caminho: CaminhoDesenhavel };
export type TextoDesenhavel = {
  x: number; y: number; altura: number; rotacao: number;
  texto: string; cor: number;
};
export type Desenho = { grupos: Grupo[]; textos: TextoDesenhavel[] };

const GRAU = Math.PI / 180;

export function montarDesenho(g: Geometria, mascara: Uint8Array,
                              criarCaminho: () => CaminhoDesenhavel): Desenho {
  const porChave = new Map<string, Grupo>();
  const textos: TextoDesenhavel[] = [];

  for (let i = 0; i < g.n; i++) {
    if (!mascara[i]) continue;
    const tipo = g.kind[i]!;
    const cor = g.cor[i]!;

    if (tipo === TEXTO) {
      const c = coordenadasDe(g, i);
      textos.push({
        x: c[0]!, y: c[1]!, altura: c[2]!, rotacao: c[3]!,
        texto: textoDe(g, i), cor,
      });
      continue;
    }

    const chave = `${g.layer_id[i]}|${cor}`;
    let grupo = porChave.get(chave);
    if (!grupo) {
      grupo = { layerId: g.layer_id[i]!, cor, caminho: criarCaminho() };
      porChave.set(chave, grupo);
    }
    const p = grupo.caminho;
    const c = coordenadasDe(g, i);

    if (tipo === SEGMENTO) {
      p.moveTo(c[0]!, c[1]!);
      p.lineTo(c[2]!, c[3]!);
    } else if (tipo === POLILINHA) {
      // O primeiro float diz se a polilinha é fechada; os pares vêm depois.
      p.moveTo(c[1]!, c[2]!);
      for (let k = 3; k + 1 < c.length; k += 2) p.lineTo(c[k]!, c[k + 1]!);
      if (c[0] === 1) p.closePath();
    } else if (tipo === ARCO) {
      p.arc(c[0]!, c[1]!, c[2]!, c[3]! * GRAU, c[4]! * GRAU);
    } else if (tipo === BEZIER) {
      p.moveTo(c[0]!, c[1]!);
      p.bezierCurveTo(c[2]!, c[3]!, c[4]!, c[5]!, c[6]!, c[7]!);
    }
  }

  return { grupos: [...porChave.values()], textos };
}

/** Transformação papel → tela. `escala` em pixels por ponto de papel. */
export type Vista = { escala: number; dx: number; dy: number };

/**
 * Enquadra a folha com uma folga, invertendo o eixo Y.
 *
 * O PDF tem origem no canto de baixo e Y crescendo para cima; o canvas tem
 * origem no topo e Y crescendo para baixo. A inversão mora aqui, num lugar só.
 */
export function enquadrar(larguraPt: number, alturaPt: number,
                          larguraTela: number, alturaTela: number): Vista {
  const escala = Math.min(larguraTela / larguraPt, alturaTela / alturaPt);
  return {
    escala,
    dx: (larguraTela - larguraPt * escala) / 2,
    dy: (alturaTela - alturaPt * escala) / 2 + alturaPt * escala,
  };
}

export function pontoDaTela(v: Vista, x: number, y: number) {
  return { x: x * v.escala + v.dx, y: v.dy - y * v.escala };
}

export function pontoDoPapel(v: Vista, x: number, y: number) {
  return { x: (x - v.dx) / v.escala, y: (v.dy - y) / v.escala };
}

const COR_DO_TRACO = "#000000";

/** Aplica a vista e traça o desenho. Só chamado no navegador. */
export function pintar(ctx: CanvasRenderingContext2D, d: Desenho, v: Vista,
                       fundo: string): void {
  const { width, height } = ctx.canvas;
  ctx.save();
  ctx.fillStyle = fundo;
  ctx.fillRect(0, 0, width, height);
  ctx.setTransform(v.escala, 0, 0, -v.escala, v.dx, v.dy);
  // Traço de 1 pixel na tela, independente do zoom: dividir pela escala desfaz
  // o efeito da transformação sobre a espessura.
  ctx.lineWidth = 1 / v.escala;
  for (const grupo of d.grupos) {
    ctx.strokeStyle = grupo.cor === SEM_COR
      ? COR_DO_TRACO
      : `#${grupo.cor.toString(16).padStart(6, "0")}`;
    ctx.stroke(grupo.caminho as unknown as Path2D);
  }
  ctx.restore();

  // O texto é desenhado fora da transformação: escalar a fonte junto com o
  // desenho a deixaria ilegível no zoom de fora.
  ctx.save();
  ctx.fillStyle = COR_DO_TRACO;
  ctx.textBaseline = "alphabetic";
  for (const t of d.textos) {
    const p = pontoDaTela(v, t.x, t.y);
    const altura = Math.max(1, t.altura * v.escala);
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(-t.rotacao * GRAU);
    ctx.font = `${altura}px system-ui, sans-serif`;
    ctx.fillText(t.texto, 0, 0);
    ctx.restore();
  }
  ctx.restore();
}
```

- [ ] **Passo 5: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os seis testes novos verdes.

- [ ] **Passo 6: commit**

```bash
git add web/frontend/src/canvas.ts web/frontend/testes/canvas.test.ts \
        web/frontend/testes/ajuda/canvas2d.ts
git commit -m "Renderizador com Path2D por grupo, preso ao que a mascara escolheu"
```

---

### Tarefa 9: `calibrate.ts`

**Arquivos:**
- Criar: `web/frontend/src/calibrate.ts`
- Testar: `web/frontend/testes/calibrate.test.ts`

**Interfaces:**
- Consome: nada
- Produz:
  - `const PT_PARA_MM = 25.4 / 72.0`
  - `const MM_POR_UNIDADE = { mm: 1.0, cm: 10.0, m: 1000.0 }`
  - `type Unidade = "mm" | "cm" | "m"`
  - `function escalaPorDoisPontos(p1: [number, number], p2: [number, number], medidaReal: number): number`
  - `function escalaPorEscalaDePlotagem(razao: number, unidade: Unidade): number`

Espelha `pdftodxf/calibration.py`. Os mesmos erros, com as mesmas mensagens.

- [ ] **Passo 1: escrever o teste que falha**

`web/frontend/testes/calibrate.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { escalaPorDoisPontos, escalaPorEscalaDePlotagem } from "../src/calibrate.js";

describe("calibrate.ts espelha calibration.py", () => {
  it("dois pontos: fator é medida real dividida pela distância no papel", () => {
    // 300 pt no papel medindo 3,00 m na planta
    expect(escalaPorDoisPontos([0, 0], [300, 0], 3.0)).toBeCloseTo(0.01, 12);
    // distância na diagonal: 3-4-5
    expect(escalaPorDoisPontos([0, 0], [30, 40], 5.0)).toBeCloseTo(0.1, 12);
  });

  it("recusa dois pontos coincidentes", () => {
    expect(() => escalaPorDoisPontos([7, 7], [7, 7], 1.0))
      .toThrow(/coincidem/i);
  });

  it("recusa medida real não positiva", () => {
    expect(() => escalaPorDoisPontos([0, 0], [10, 0], 0)).toThrow(/positiva/i);
    expect(() => escalaPorDoisPontos([0, 0], [10, 0], -2)).toThrow(/positiva/i);
  });

  it("escala de plotagem 1:50 em metros", () => {
    // 1 pt = 25.4/72 mm de papel = 0.352777… mm; ×50 = 17.638… mm reais.
    // O esperado precisa de dígitos suficientes para a precisão pedida: com
    // `0.0176388888` e 10 casas o teste falha por 8,9e-11, e o culpado é o
    // literal truncado, não a conta. Corrigido em 2026-08-09, ao executar.
    expect(escalaPorEscalaDePlotagem(50, "m")).toBeCloseTo(0.0176388888888889, 10);
    expect(escalaPorEscalaDePlotagem(50, "mm")).toBeCloseTo(17.6388888888889, 8);
  });

  it("recusa razão não positiva", () => {
    expect(() => escalaPorEscalaDePlotagem(0, "m")).toThrow(/positiva/i);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/calibrate.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/calibrate.ts`**

```ts
/**
 * Cálculo do fator de escala: pontos de papel (1/72") → unidade real.
 *
 * Espelho de `pdftodxf/calibration.py`. Aritmética simples, mas é ela que
 * decide se a planta sai com as medidas certas no CAD — por isso vive num
 * arquivo próprio, com teste próprio, em vez de espalhada pela interface.
 */

export const PT_PARA_MM = 25.4 / 72.0;

export type Unidade = "mm" | "cm" | "m";

export const MM_POR_UNIDADE: Record<Unidade, number> = {
  mm: 1.0, cm: 10.0, m: 1000.0,
};

/** Código $INSUNITS do DXF, para exibição; quem grava o DXF é o servidor. */
export const INSUNITS: Record<Unidade, number> = { mm: 4, cm: 5, m: 6 };

export function escalaPorDoisPontos(p1: [number, number], p2: [number, number],
                                    medidaReal: number): number {
  const papel = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
  if (papel < 1e-9) throw new Error("Os dois pontos de calibração coincidem.");
  if (medidaReal <= 0) throw new Error("A medida real deve ser positiva.");
  return medidaReal / papel;
}

export function escalaPorEscalaDePlotagem(razao: number,
                                          unidade: Unidade = "m"): number {
  if (razao <= 0) throw new Error("A escala deve ser positiva (ex.: 50 para 1:50).");
  return (PT_PARA_MM * razao) / MM_POR_UNIDADE[unidade];
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os cinco testes novos verdes.

- [ ] **Passo 5: commit**

```bash
git add web/frontend/src/calibrate.ts web/frontend/testes/calibrate.test.ts
git commit -m "Calibracao por dois pontos, espelhando calibration.py"
```

---

### Tarefa 10: `gestos.ts`, pan e zoom de mouse e de toque

Separado do renderizador de propósito: a matemática do gesto é função pura sobre
a `Vista`, e função pura se testa sem navegador. O que sobra para a conferência
manual é o tato, não a aritmética.

**Arquivos:**
- Criar: `web/frontend/src/gestos.ts`
- Testar: `web/frontend/testes/gestos.test.ts`

**Interfaces:**
- Consome: `Vista`, `pontoDoPapel`, `pontoDaTela` de `src/canvas.ts`
- Produz:
  - `function aplicarZoom(v: Vista, fator: number, telaX: number, telaY: number): Vista`
  - `function aplicarArrasto(v: Vista, dx: number, dy: number): Vista`
  - `function fatorDaRoda(deltaY: number): number`
  - `function distancia(a: {x,y}, b: {x,y}): number`
  - `function centro(a: {x,y}, b: {x,y}): {x,y}`

- [ ] **Passo 1: escrever o teste que falha**

`web/frontend/testes/gestos.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { enquadrar, pontoDoPapel } from "../src/canvas.js";
import { aplicarArrasto, aplicarZoom, fatorDaRoda } from "../src/gestos.js";

const base = enquadrar(595, 842, 1000, 800);

describe("gestos.ts", () => {
  it("zoom mantém parado o ponto sob o cursor", () => {
    const antes = pontoDoPapel(base, 321, 456);
    const depois = pontoDoPapel(aplicarZoom(base, 1.25, 321, 456), 321, 456);
    expect(depois.x).toBeCloseTo(antes.x, 6);
    expect(depois.y).toBeCloseTo(antes.y, 6);
  });

  it("zoom para fora também mantém o ponto", () => {
    const antes = pontoDoPapel(base, 10, 790);
    const depois = pontoDoPapel(aplicarZoom(base, 0.5, 10, 790), 10, 790);
    expect(depois.x).toBeCloseTo(antes.x, 6);
    expect(depois.y).toBeCloseTo(antes.y, 6);
  });

  it("arrastar move o desenho exatamente o que o dedo andou", () => {
    const v = aplicarArrasto(base, 40, -25);
    expect(v.dx).toBeCloseTo(base.dx + 40, 9);
    expect(v.dy).toBeCloseTo(base.dy - 25, 9);
    expect(v.escala).toBe(base.escala);
  });

  it("roda para cima aproxima e para baixo afasta", () => {
    expect(fatorDaRoda(-100)).toBeGreaterThan(1);
    expect(fatorDaRoda(100)).toBeLessThan(1);
    // Um passo para cada lado devolve ao ponto de partida.
    expect(fatorDaRoda(-100) * fatorDaRoda(100)).toBeCloseTo(1, 9);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/gestos.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/gestos.ts`**

```ts
/**
 * A matemática dos gestos, separada de quem escuta os eventos.
 *
 * Tudo aqui é função pura sobre a `Vista`: dá para provar que o zoom mantém o
 * ponto sob o dedo parado sem abrir navegador. O que fica para a conferência
 * manual é o tato — se o gesto *parece* certo —, não a aritmética.
 */
import type { Vista } from "./canvas.js";

const PASSO_DA_RODA = 1.0015;

export function fatorDaRoda(deltaY: number): number {
  // Exponencial, não linear: assim dois passos seguidos multiplicam o zoom, e
  // um passo para cada lado volta exatamente ao ponto de partida.
  return Math.pow(PASSO_DA_RODA, -deltaY);
}

/**
 * Aplica zoom mantendo fixo o ponto de papel que está sob (telaX, telaY).
 *
 * Sem isso o desenho foge do cursor e a navegação vira perseguição.
 */
export function aplicarZoom(v: Vista, fator: number,
                            telaX: number, telaY: number): Vista {
  const escala = v.escala * fator;
  return {
    escala,
    dx: telaX - (telaX - v.dx) * fator,
    dy: telaY + (v.dy - telaY) * fator,
  };
}

export function aplicarArrasto(v: Vista, dx: number, dy: number): Vista {
  return { escala: v.escala, dx: v.dx + dx, dy: v.dy + dy };
}

export function distancia(a: { x: number; y: number },
                          b: { x: number; y: number }): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

export function centro(a: { x: number; y: number }, b: { x: number; y: number }) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os quatro testes novos verdes.

- [ ] **Passo 5: commit**

```bash
git add web/frontend/src/gestos.ts web/frontend/testes/gestos.test.ts
git commit -m "Matematica de pan e zoom como funcao pura, com o ponto sob o dedo parado"
```

---

### Tarefa 11: `estados.ts` e `estilo.css`

**Arquivos:**
- Criar: `web/frontend/src/estados.ts`
- Criar: `web/frontend/src/estilo.css`
- Testar: `web/frontend/testes/estados.test.ts`

**Interfaces:**
- Consome: `ErroDaApi` de `src/api.ts`
- Produz:
  - `type Aviso = { titulo: string; detalhe: string; podeTentarDeNovo: boolean }`
  - `function avisoDoErro(erro: unknown): Aviso`
  - `function avisoDaSituacao(situacao: string, codigo?: string, mensagem?: string): Aviso | null`

- [ ] **Passo 1: escrever o teste que falha**

`web/frontend/testes/estados.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { ErroDaApi } from "../src/api.js";
import { avisoDaSituacao, avisoDoErro } from "../src/estados.js";

describe("estados.ts", () => {
  it("página pronta não gera aviso", () => {
    expect(avisoDaSituacao("pronta")).toBeNull();
  });

  it("na fila e extraindo dizem a mesma coisa", () => {
    // "extraindo" está no contrato da API e hoje nada o escreve; quem lê tem
    // de tratá-lo como "ainda em andamento".
    expect(avisoDaSituacao("extraindo")).toEqual(avisoDaSituacao("na_fila"));
  });

  it("cada código de erro tem mensagem própria e acionável", () => {
    for (const codigo of ["sem_vetores", "entidades_demais", "recurso", "interno"]) {
      const aviso = avisoDaSituacao("erro", codigo, "mensagem do servidor")!;
      expect(aviso.titulo.length).toBeGreaterThan(0);
      expect(aviso.detalhe.length).toBeGreaterThan(0);
    }
    expect(avisoDaSituacao("erro", "sem_vetores")!.detalhe).toMatch(/vetorial/i);
    expect(avisoDaSituacao("erro", "entidades_demais")!.detalhe).toMatch(/grande/i);
  });

  it("erro desconhecido não fica sem mensagem", () => {
    const aviso = avisoDaSituacao("erro", "codigo_que_nao_existe")!;
    expect(aviso.detalhe.length).toBeGreaterThan(0);
  });

  it("404 vira 'a planta expirou' e 413 vira 'grande demais'", () => {
    expect(avisoDoErro(new ErroDaApi(404, "não achei")).detalhe).toMatch(/expir/i);
    expect(avisoDoErro(new ErroDaApi(413, "grande")).detalhe).toMatch(/tamanho|limite/i);
  });

  it("queda de rede não vira tela em branco", () => {
    const aviso = avisoDoErro(new TypeError("Failed to fetch"));
    expect(aviso.detalhe.length).toBeGreaterThan(0);
    expect(aviso.podeTentarDeNovo).toBe(true);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/estados.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/estados.ts`**

```ts
/**
 * O que a tela diz em cada situação.
 *
 * Uma mensagem só serve se disser o que houve **e** o que fazer. "Erro ao
 * processar" não é mensagem, é desculpa.
 */
import { ErroDaApi } from "./api.js";

export type Aviso = {
  titulo: string;
  detalhe: string;
  podeTentarDeNovo: boolean;
};

const POR_CODIGO: Record<string, Aviso> = {
  sem_vetores: {
    titulo: "Esta página não tem desenho vetorial",
    detalhe: "Só funcionam PDFs gerados pelo CAD. Um PDF escaneado é uma " +
             "imagem: não há linhas para converter, só pixels.",
    podeTentarDeNovo: false,
  },
  entidades_demais: {
    titulo: "A planta é grande demais",
    detalhe: "Esta página passa do limite de elementos que o servidor " +
             "processa. Tente exportar do CAD apenas as camadas necessárias.",
    podeTentarDeNovo: false,
  },
  recurso: {
    titulo: "Não consegui processar esta planta",
    detalhe: "Ela passou do limite de memória ou de tempo do servidor.",
    podeTentarDeNovo: true,
  },
  interno: {
    titulo: "Alguma coisa deu errado aqui do meu lado",
    detalhe: "A falha foi registrada no servidor. Tente de novo em instantes.",
    podeTentarDeNovo: true,
  },
};

const NA_FILA: Aviso = {
  titulo: "Processando a planta",
  detalhe: "A extração já começou. Plantas grandes levam alguns minutos.",
  podeTentarDeNovo: false,
};

export function avisoDaSituacao(situacao: string, codigo?: string,
                                mensagem?: string): Aviso | null {
  if (situacao === "pronta") return null;
  // "extraindo" está no contrato da API e hoje nada o escreve: o processo pai
  // é o dono do estado e não sabe quando o worker pega o trabalho.
  if (situacao === "na_fila" || situacao === "extraindo") return NA_FILA;

  const conhecido = codigo ? POR_CODIGO[codigo] : undefined;
  if (conhecido) return conhecido;
  return {
    titulo: "Não consegui processar esta planta",
    detalhe: mensagem || "O servidor não explicou o motivo. Tente de novo.",
    podeTentarDeNovo: true,
  };
}

export function avisoDoErro(erro: unknown): Aviso {
  if (erro instanceof ErroDaApi) {
    if (erro.status === 404) {
      return {
        titulo: "Esta planta expirou",
        detalhe: "Os arquivos enviados são apagados depois de 4 horas. " +
                 "Envie o PDF de novo para continuar.",
        podeTentarDeNovo: false,
      };
    }
    if (erro.status === 413) {
      return {
        titulo: "O arquivo passa do tamanho permitido",
        detalhe: erro.message || "Escolha um PDF menor.",
        podeTentarDeNovo: false,
      };
    }
    if (erro.status === 409) {
      return {
        titulo: "A página ainda não está pronta",
        detalhe: "Espere a extração terminar.",
        podeTentarDeNovo: true,
      };
    }
    return {
      titulo: "O servidor recusou o pedido",
      detalhe: erro.message,
      podeTentarDeNovo: true,
    };
  }
  return {
    titulo: "Não consegui falar com o servidor",
    detalhe: "Confira a conexão e tente de novo.",
    podeTentarDeNovo: true,
  };
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os seis testes novos verdes.

- [ ] **Passo 5: escrever `web/frontend/src/estilo.css`**

Moldura escura, papel claro — a área do desenho imita a folha impressa, para
quem confere com o papel na mão ver a mesma coisa nos dois lugares.

```css
/* Moldura escura, papel claro: as faixas não competem com o desenho. */
:root {
  --fundo-moldura: #1e2126;
  --fundo-faixa: #262a31;
  --borda: #383e47;
  --texto: #e6e9ee;
  --texto-fraco: #9aa3b0;
  --ligado: #3d7eff;
  --ligado-texto: #ffffff;
  --alerta: #d9534f;

  /* Uma variável só: inverter o desenho depois é uma linha. */
  --fundo-do-desenho: #f7f7f5;

  --raio: 6px;
  --gap: 8px;
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  height: 100%;
  background: var(--fundo-moldura);
  color: var(--texto);
  font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
}

#app { display: flex; flex-direction: column; height: 100%; }

.faixa {
  display: flex;
  align-items: center;
  gap: var(--gap);
  padding: 8px 12px;
  background: var(--fundo-faixa);
  border-bottom: 1px solid var(--borda);
  /* Em tela estreita as faixas rolam na horizontal, em vez de espremer os
     botões até ninguém conseguir acertar um. */
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: thin;
}

.botao, .chip {
  font: inherit;
  color: var(--texto);
  background: transparent;
  border: 1px solid var(--borda);
  border-radius: var(--raio);
  padding: 6px 12px;
  cursor: pointer;
  /* Alvo de toque confortável no celular. */
  min-height: 36px;
}
.botao:hover, .chip:hover { border-color: var(--texto-fraco); }
.botao[aria-pressed="true"], .chip[aria-pressed="true"] {
  background: var(--ligado);
  border-color: var(--ligado);
  color: var(--ligado-texto);
}
.botao:disabled { opacity: 0.45; cursor: default; }

.principal { color: var(--ligado); border-color: var(--ligado); }
.separador { width: 1px; align-self: stretch; background: var(--borda); }
.fraco { color: var(--texto-fraco); }

.area-do-desenho { position: relative; flex: 1; min-height: 0; }
#desenho {
  display: block;
  width: 100%;
  height: 100%;
  background: var(--fundo-do-desenho);
  touch-action: none;   /* os gestos são nossos, não do navegador */
}

.aviso {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  gap: var(--gap);
  text-align: center;
  padding: 24px;
  background: color-mix(in srgb, var(--fundo-moldura) 88%, transparent);
}
.aviso h2 { margin: 0; font-size: 18px; }
.aviso p { margin: 0; max-width: 46ch; color: var(--texto-fraco); }

.faixa-detalhe {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  padding: 4px 12px;
  font-size: 12px;
  color: var(--texto-fraco);
  background: var(--fundo-faixa);
  border-top: 1px solid var(--borda);
}

.rodape {
  padding: 6px 12px;
  font-size: 12px;
  color: var(--texto-fraco);
  background: var(--fundo-faixa);
  border-top: 1px solid var(--borda);
}
.rodape a { color: var(--texto-fraco); }

.lupa {
  position: absolute;
  width: 120px; height: 120px;
  border: 2px solid var(--ligado);
  border-radius: 50%;
  overflow: hidden;
  pointer-events: none;
  background: var(--fundo-do-desenho);
}
```

- [ ] **Passo 6: commit**

```bash
git add web/frontend/src/estados.ts web/frontend/src/estilo.css \
        web/frontend/testes/estados.test.ts
git commit -m "Mensagens de espera e erro, e o estilo da moldura escura"
```

---

### Tarefa 12: `toolbar.ts` e `main.ts`, a tela montada

A tarefa que junta tudo. Depois dela a etapa funciona de ponta a ponta no
navegador.

**Arquivos:**
- Criar: `web/frontend/src/toolbar.ts`
- Substituir: `web/frontend/src/main.ts`
- Modificar: `web/frontend/index.html`
- Testar: `web/frontend/testes/toolbar.test.ts`

**Interfaces:**
- Consome: tudo das tarefas 2 a 11
- Produz:
  - `type EstadoDaTela = { opcoes: Opcoes; layersDesligados: Set<string>; escala: number; unidade: Unidade; parcial: boolean; bytes: number; sobreviventes: number }`
  - `function opcoesEfetivas(e: EstadoDaTela): Opcoes`
  - `function textoDaEstimativa(bytes: number, parcial: boolean): string`
  - `function montarFaixaDeOpcoes(raiz: HTMLElement, e: EstadoDaTela, layers: string[], aoMudar: () => void): void`

- [ ] **Passo 1: escrever o teste que falha**

`web/frontend/testes/toolbar.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { opcoesEfetivas, textoDaEstimativa } from "../src/toolbar.js";

const base = {
  opcoes: {
    excluded_layers: [], drop_fills: false, min_len_mm: 0,
    dedup: false, join_polylines: false, round_coords: false,
  },
  layersDesligados: new Set<string>(),
  escala: 0.01,
  unidade: "m" as const,
  parcial: false,
  bytes: 0,
  sobreviventes: 0,
};

describe("toolbar.ts", () => {
  it("layers desligados viram excluded_layers, em ordem estável", () => {
    const e = { ...base, layersDesligados: new Set(["TEXTO", "COTAS"]) };
    expect(opcoesEfetivas(e).excluded_layers).toEqual(["COTAS", "TEXTO"]);
  });

  it("a chave da exportação não muda por causa da ordem dos cliques", () => {
    const a = opcoesEfetivas({ ...base, layersDesligados: new Set(["A", "B"]) });
    const b = opcoesEfetivas({ ...base, layersDesligados: new Set(["B", "A"]) });
    expect(a.excluded_layers).toEqual(b.excluded_layers);
  });

  it("a estimativa parcial vem marcada", () => {
    expect(textoDaEstimativa(1_500_000, false)).toBe("≈ 1,4 MB");
    expect(textoDaEstimativa(1_500_000, true)).toBe("≈ 1,4 MB (parcial)");
    expect(textoDaEstimativa(2048, false)).toBe("≈ 2,0 kB");
  });
});
```

O segundo teste não é preciosismo: o servidor ordena os layers ao montar a chave
do cache, e se o cliente mandar em ordem diferente a mesma exportação vira duas
no disco — e, na etapa 4, dois downloads na cota.

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `src/toolbar.ts`.

- [ ] **Passo 3: implementar `web/frontend/src/toolbar.ts`**

```ts
/**
 * As duas faixas do cabeçalho.
 *
 * Sem framework: os elementos são criados na mão e o estado mora num objeto só.
 * A lista de componentes é curta demais para justificar dependência.
 */
import type { Unidade } from "./calibrate.js";
import type { Opcoes } from "./select.js";

export type EstadoDaTela = {
  opcoes: Opcoes;
  layersDesligados: Set<string>;
  escala: number;
  unidade: Unidade;
  parcial: boolean;
  bytes: number;
  sobreviventes: number;
};

/**
 * As opções como o servidor as espera.
 *
 * `sort()` não é enfeite: o servidor ordena os layers ao montar a chave do
 * cache de exportação. Mandar em outra ordem geraria a mesma planta duas vezes
 * no disco — e, na etapa 4, dois downloads na cota.
 */
export function opcoesEfetivas(e: EstadoDaTela): Opcoes {
  return { ...e.opcoes, excluded_layers: [...e.layersDesligados].sort() };
}

export function textoDaEstimativa(bytes: number, parcial: boolean): string {
  const mb = bytes / 1_000_000;
  const texto = mb >= 1
    ? `≈ ${mb.toFixed(1).replace(".", ",")} MB`
    : `≈ ${(bytes / 1000).toFixed(1).replace(".", ",")} kB`;
  return parcial ? `${texto} (parcial)` : texto;
}

const OPCOES_DE_COMPACTACAO: Array<{ chave: keyof Opcoes; rotulo: string }> = [
  { chave: "join_polylines", rotulo: "Unir em polilinhas" },
  { chave: "round_coords", rotulo: "Arredondar coordenadas" },
  { chave: "dedup", rotulo: "Remover duplicados" },
  { chave: "drop_fills", rotulo: "Remover preenchimentos" },
];

function botaoLigavel(rotulo: string, ligado: boolean,
                      aoClicar: () => void): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = "botao";
  b.type = "button";
  b.textContent = rotulo;
  b.setAttribute("aria-pressed", String(ligado));
  b.addEventListener("click", aoClicar);
  return b;
}

/** Preenche a faixa 2 com as opções e os chips de layer. */
export function montarFaixaDeOpcoes(raiz: HTMLElement, e: EstadoDaTela,
                                    layers: string[], aoMudar: () => void): void {
  raiz.replaceChildren();

  for (const { chave, rotulo } of OPCOES_DE_COMPACTACAO) {
    raiz.append(botaoLigavel(rotulo, Boolean(e.opcoes[chave]), () => {
      (e.opcoes[chave] as boolean) = !e.opcoes[chave];
      aoMudar();
    }));
  }

  const campo = document.createElement("input");
  campo.type = "number";
  campo.min = "0";
  campo.step = "0.1";
  campo.className = "botao";
  campo.style.width = "8ch";
  campo.value = String(e.opcoes.min_len_mm);
  campo.setAttribute("aria-label", "Descartar segmentos abaixo de N mm");
  campo.addEventListener("change", () => {
    e.opcoes.min_len_mm = Math.max(0, Number(campo.value) || 0);
    aoMudar();
  });
  raiz.append(campo);

  const separador = document.createElement("span");
  separador.className = "separador";
  raiz.append(separador);

  for (const layer of layers) {
    raiz.append(botaoLigavel(layer, !e.layersDesligados.has(layer), () => {
      if (e.layersDesligados.has(layer)) e.layersDesligados.delete(layer);
      else e.layersDesligados.add(layer);
      aoMudar();
    }));
  }
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os três testes novos verdes.

- [ ] **Passo 5: `web/frontend/index.html`**

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PdfToDxf — planta em PDF para DXF em escala real</title>
    <link rel="stylesheet" href="/src/estilo.css" />
  </head>
  <body>
    <div id="app">
      <div class="faixa" id="faixa-principal"></div>
      <div class="faixa" id="faixa-opcoes"></div>
      <div class="area-do-desenho">
        <canvas id="desenho"></canvas>
        <div class="aviso" id="aviso" hidden></div>
        <div class="faixa-detalhe" id="faixa-detalhe" hidden></div>
      </div>
      <div class="rodape">
        O texto das plantas e o endereço IP são registrados por 1 ano.
        <a href="/privacidade.html">Como tratamos seus dados</a>
      </div>
    </div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Passo 6: implementar `web/frontend/src/main.ts`**

```ts
/**
 * Composição da tela.
 *
 * Aqui mora o estado e o `redesenhar()`. Todo o resto é módulo com uma
 * responsabilidade só; este arquivo é o único que os conhece todos.
 */
import {
  ErroDaApi, enviarPdf, esperarPagina, exportar, lerGeometriaBruta, lerMeta,
  pedirExtracao, type Meta,
} from "./api.js";
import { montarDesenho, enquadrar, pintar, pontoDoPapel,
         type Desenho, type Vista } from "./canvas.js";
import { intercalar, lerGeometria, type Geometria } from "./formato.js";
import { aplicarArrasto, aplicarZoom, centro, distancia,
         fatorDaRoda } from "./gestos.js";
import { avisoDaSituacao, avisoDoErro, type Aviso } from "./estados.js";
import { montarFaixaDeOpcoes, opcoesEfetivas, textoDaEstimativa,
         type EstadoDaTela } from "./toolbar.js";
import type { RespostaWorker } from "./worker.js";

const tela = document.querySelector<HTMLCanvasElement>("#desenho")!;
const ctx = tela.getContext("2d")!;
const faixaPrincipal = document.querySelector<HTMLElement>("#faixa-principal")!;
const faixaOpcoes = document.querySelector<HTMLElement>("#faixa-opcoes")!;
const painelAviso = document.querySelector<HTMLElement>("#aviso")!;
const faixaDetalhe = document.querySelector<HTMLElement>("#faixa-detalhe")!;

const estado: EstadoDaTela = {
  opcoes: {
    excluded_layers: [], drop_fills: false, min_len_mm: 0,
    dedup: false, join_polylines: false, round_coords: false,
  },
  layersDesligados: new Set(),
  escala: 0.01,
  unidade: "m",
  parcial: false,
  bytes: 0,
  sobreviventes: 0,
};

let job = "";
let pagina = 1;
let nPaginas = 1;
let meta: Meta | null = null;
let geometria: Geometria | null = null;
let desenho: Desenho | null = null;
let vista: Vista = { escala: 1, dx: 0, dy: 0 };
let controle = new AbortController();

const worker = new Worker(new URL("./worker.ts", import.meta.url),
                          { type: "module" });

worker.onmessage = (evento: MessageEvent<RespostaWorker>) => {
  const r = evento.data;
  estado.bytes = r.bytes;
  estado.sobreviventes = r.sobreviventes;
  if (geometria) {
    desenho = montarDesenho(geometria, r.mascara, () => new Path2D());
    redesenhar();
  }
  montarFaixaPrincipal();
};

function ajustarTamanho(): void {
  const proporcao = window.devicePixelRatio || 1;
  tela.width = Math.round(tela.clientWidth * proporcao);
  tela.height = Math.round(tela.clientHeight * proporcao);
}

function redesenhar(): void {
  if (!desenho) return;
  const fundo = getComputedStyle(document.documentElement)
    .getPropertyValue("--fundo-do-desenho").trim() || "#ffffff";
  pintar(ctx, desenho, vista, fundo);
}

function mostrarAviso(aviso: Aviso | null): void {
  if (!aviso) { painelAviso.hidden = true; return; }
  painelAviso.hidden = false;
  painelAviso.replaceChildren();
  const titulo = document.createElement("h2");
  titulo.textContent = aviso.titulo;
  const detalhe = document.createElement("p");
  detalhe.textContent = aviso.detalhe;
  painelAviso.append(titulo, detalhe);
}

function pedirDecisao(): void {
  worker.postMessage({ tipo: "decidir", opcoes: opcoesEfetivas(estado) });
}

async function abrir(arquivo: File): Promise<void> {
  // Trocar de planta ou de página aborta o que estiver em voo: sem isso, o
  // detalhe da página anterior chega depois e contamina o canvas.
  controle.abort();
  controle = new AbortController();
  const sinal = controle.signal;

  try {
    mostrarAviso({ titulo: "Enviando o PDF", detalhe: "Um instante.",
                   podeTentarDeNovo: false });
    const ficha = await enviarPdf(arquivo, sinal);
    job = ficha.job_id;
    nPaginas = ficha.n_paginas;
    pagina = 1;
    await carregarPagina();
  } catch (erro) {
    if (sinal.aborted) return;
    mostrarAviso(avisoDoErro(erro));
  }
}

async function carregarPagina(): Promise<void> {
  controle.abort();
  controle = new AbortController();
  const sinal = controle.signal;

  geometria = null;
  desenho = null;
  faixaDetalhe.hidden = true;

  try {
    await pedirExtracao(job, pagina, sinal);
    const final = await esperarPagina(job, pagina, sinal, (e) =>
      mostrarAviso(avisoDaSituacao(e.situacao, e.codigo, e.mensagem)));
    if (final.situacao === "erro") {
      mostrarAviso(avisoDaSituacao("erro", final.codigo, final.mensagem));
      return;
    }

    meta = await lerMeta(job, pagina, sinal);
    mostrarAviso(null);
    estado.layersDesligados.clear();
    montarFaixaDeOpcoes(faixaOpcoes, estado, meta.layers, aoMudarOpcoes);

    const cruEsqueleto = await lerGeometriaBruta(job, pagina, "esqueleto", sinal);
    geometria = lerGeometria(cruEsqueleto, meta.layers, 0);
    estado.parcial = meta.partes.detalhe > 0;
    faixaDetalhe.hidden = !estado.parcial;
    faixaDetalhe.textContent = "Carregando o detalhe do desenho…";

    ajustarTamanho();
    vista = enquadrar(meta.largura_pt, meta.altura_pt, tela.width, tela.height);
    enviarAoWorker();

    if (estado.parcial) {
      const cruDetalhe = await lerGeometriaBruta(job, pagina, "detalhe", sinal);
      if (sinal.aborted) return;
      const parteDetalhe = lerGeometria(cruDetalhe, meta.layers, 0);
      // A intercalação restaura a ordem original. Sem ela, o dedup elegeria um
      // sobrevivente por parte e a tela mostraria duplicata que o DXF não tem.
      geometria = intercalar(geometria, parteDetalhe);
      estado.parcial = false;
      faixaDetalhe.hidden = true;
      enviarAoWorker();
    }
  } catch (erro) {
    if (sinal.aborted) return;
    mostrarAviso(avisoDoErro(erro));
  }
}

function enviarAoWorker(): void {
  if (!geometria || !meta) return;
  // Só os arrays de decisão vão ao worker: as coordenadas ficam aqui, porque
  // é aqui que se desenha. `n_groups` vem do maior grupo visto, já que o
  // meta.json não o traz.
  let nGroups = 0;
  for (const g of geometria.dup_group) if (g + 1 > nGroups) nGroups = g + 1;
  worker.postMessage({
    tipo: "carregar",
    decisao: {
      kind: geometria.kind.slice(),
      layer_id: geometria.layer_id.slice(),
      is_fill: geometria.is_fill.slice(),
      length_um: geometria.length_um.slice(),
      dup_group: geometria.dup_group.slice(),
      byte_cost: geometria.byte_cost.slice(),
      layers: meta.layers,
      n_groups: nGroups,
    },
  });
  pedirDecisao();
}

function aoMudarOpcoes(): void {
  montarFaixaDeOpcoes(faixaOpcoes, estado, meta?.layers ?? [], aoMudarOpcoes);
  pedirDecisao();
}

function montarFaixaPrincipal(): void {
  faixaPrincipal.replaceChildren();

  const escolher = document.createElement("input");
  escolher.type = "file";
  escolher.accept = "application/pdf";
  escolher.id = "escolher-pdf";
  escolher.addEventListener("change", () => {
    const arquivo = escolher.files?.[0];
    if (arquivo) void abrir(arquivo);
  });
  faixaPrincipal.append(escolher);

  if (nPaginas > 1) {
    const seletor = document.createElement("select");
    seletor.className = "botao";
    seletor.id = "seletor-pagina";
    for (let p = 1; p <= nPaginas; p++) {
      const opcao = document.createElement("option");
      opcao.value = String(p);
      opcao.textContent = `Página ${p}`;
      opcao.selected = p === pagina;
      seletor.append(opcao);
    }
    seletor.addEventListener("change", () => {
      pagina = Number(seletor.value);
      void carregarPagina();
    });
    faixaPrincipal.append(seletor);
  }

  const escala = document.createElement("span");
  escala.className = "fraco";
  escala.id = "escala-atual";
  escala.textContent = `1 pt = ${estado.escala} ${estado.unidade}`;
  faixaPrincipal.append(escala);

  const estimativa = document.createElement("span");
  estimativa.className = "fraco";
  estimativa.id = "estimativa";
  estimativa.textContent = textoDaEstimativa(estado.bytes, estado.parcial);
  faixaPrincipal.append(estimativa);

  const exportarBotao = document.createElement("button");
  exportarBotao.className = "botao principal";
  exportarBotao.id = "exportar";
  exportarBotao.type = "button";
  exportarBotao.textContent = "Exportar DXF";
  exportarBotao.disabled = !geometria;
  exportarBotao.addEventListener("click", () => void baixar());
  faixaPrincipal.append(exportarBotao);
}

async function baixar(): Promise<void> {
  try {
    const r = await exportar(job, pagina, {
      escala: estado.escala, unidade: estado.unidade,
      opcoes: opcoesEfetivas(estado),
    });
    const link = document.createElement("a");
    link.href = r.url;
    link.download = "";
    link.id = "link-do-dxf";
    document.body.append(link);
    link.click();
    link.remove();
  } catch (erro) {
    mostrarAviso(avisoDoErro(erro));
  }
}

// --- gestos -----------------------------------------------------------------

let arrastando = false;
let ultimoX = 0, ultimoY = 0;
let pinca: { distancia: number } | null = null;

tela.addEventListener("pointerdown", (e) => {
  arrastando = true;
  ultimoX = e.clientX;
  ultimoY = e.clientY;
  tela.setPointerCapture(e.pointerId);
});
tela.addEventListener("pointermove", (e) => {
  if (!arrastando) return;
  const proporcao = window.devicePixelRatio || 1;
  vista = aplicarArrasto(vista, (e.clientX - ultimoX) * proporcao,
                         (e.clientY - ultimoY) * proporcao);
  ultimoX = e.clientX;
  ultimoY = e.clientY;
  redesenhar();
});
tela.addEventListener("pointerup", () => { arrastando = false; });
tela.addEventListener("pointercancel", () => { arrastando = false; });

tela.addEventListener("wheel", (e) => {
  e.preventDefault();
  const proporcao = window.devicePixelRatio || 1;
  const caixa = tela.getBoundingClientRect();
  vista = aplicarZoom(vista, fatorDaRoda(e.deltaY),
                      (e.clientX - caixa.left) * proporcao,
                      (e.clientY - caixa.top) * proporcao);
  redesenhar();
}, { passive: false });

tela.addEventListener("touchmove", (e) => {
  if (e.touches.length !== 2) return;
  e.preventDefault();
  const proporcao = window.devicePixelRatio || 1;
  const caixa = tela.getBoundingClientRect();
  const a = { x: (e.touches[0]!.clientX - caixa.left) * proporcao,
              y: (e.touches[0]!.clientY - caixa.top) * proporcao };
  const b = { x: (e.touches[1]!.clientX - caixa.left) * proporcao,
              y: (e.touches[1]!.clientY - caixa.top) * proporcao };
  const agora = distancia(a, b);
  if (pinca) {
    const meio = centro(a, b);
    vista = aplicarZoom(vista, agora / pinca.distancia, meio.x, meio.y);
    redesenhar();
  }
  pinca = { distancia: agora };
}, { passive: false });
tela.addEventListener("touchend", () => { pinca = null; });

tela.addEventListener("dblclick", () => {
  if (!meta) return;
  ajustarTamanho();
  vista = enquadrar(meta.largura_pt, meta.altura_pt, tela.width, tela.height);
  redesenhar();
});

window.addEventListener("resize", () => {
  ajustarTamanho();
  redesenhar();
});

ajustarTamanho();
montarFaixaPrincipal();
```

- [ ] **Passo 7: subir e conferir a olho**

Num terminal:

```bash
./.venv/Scripts/python.exe -m uvicorn web.api.main:app --port 8000
```

Noutro:

```bash
cd web/frontend && npm run dev
```

Abra `http://localhost:5173`, envie a planta que estiver em `Input/`
e confira: a planta aparece; a roda dá zoom no ponto sob o cursor; arrastar move;
duplo clique enquadra; ligar e desligar opções muda a estimativa e o desenho;
desligar um layer some com ele; **Exportar DXF** baixa um arquivo que abre no CAD.

- [ ] **Passo 8: conferir que o build de produção passa**

```bash
cd web/frontend && npm run build
```

Esperado: `tsc --noEmit` sem erro e `dist/` gerado. O `tsc` roda antes do Vite
de propósito: o Vite compila TypeScript sem conferir tipo nenhum.

- [ ] **Passo 9: commit**

```bash
git add web/frontend/src/toolbar.ts web/frontend/src/main.ts \
        web/frontend/index.html web/frontend/testes/toolbar.test.ts
git commit -m "Monta a tela: as duas faixas, os gestos e a composicao"
```

---

### Tarefa 13: calibração na tela, com lupa no toque

A aritmética já existe (tarefa 9). Falta o gesto: marcar dois pontos no desenho
e informar a medida real.

**Arquivos:**
- Modificar: `web/frontend/src/calibrate.ts`
- Modificar: `web/frontend/src/main.ts`
- Testar: `web/frontend/testes/calibrate.test.ts`

**Interfaces:**
- Consome: `Vista`, `pontoDoPapel` de `src/canvas.ts`
- Produz:
  - `type Calibragem = { pontos: Array<[number, number]>; ativa: boolean }`
  - `function iniciarCalibragem(): Calibragem`
  - `function marcarPonto(c: Calibragem, v: Vista, telaX: number, telaY: number): Calibragem`
  - `function posicaoDaLupa(telaX: number, telaY: number, larguraTela: number, alturaTela: number, lado: number): { x: number; y: number }`

- [ ] **Passo 1: acrescentar o teste que falha**

Ao fim de `web/frontend/testes/calibrate.test.ts`:

```ts
import { enquadrar } from "../src/canvas.js";
import { iniciarCalibragem, marcarPonto, posicaoDaLupa } from "../src/calibrate.js";

describe("gesto da calibração", () => {
  const v = enquadrar(595, 842, 1000, 800);

  it("dois cliques fecham a calibragem, em coordenadas de papel", () => {
    let c = iniciarCalibragem();
    expect(c.ativa).toBe(true);
    c = marcarPonto(c, v, 100, 200);
    expect(c.pontos.length).toBe(1);
    expect(c.ativa).toBe(true);
    c = marcarPonto(c, v, 400, 200);
    expect(c.pontos.length).toBe(2);
    expect(c.ativa).toBe(false);
    // Mesmo Y de tela, então mesmo Y de papel: a distância é só horizontal.
    expect(c.pontos[0]![1]).toBeCloseTo(c.pontos[1]![1], 9);
  });

  it("um terceiro clique não entra", () => {
    let c = iniciarCalibragem();
    c = marcarPonto(c, v, 10, 10);
    c = marcarPonto(c, v, 20, 20);
    c = marcarPonto(c, v, 30, 30);
    expect(c.pontos.length).toBe(2);
  });

  it("a lupa foge do dedo e não sai da tela", () => {
    // Perto do canto superior esquerdo, a lupa vai para a direita e para baixo.
    const perto = posicaoDaLupa(10, 10, 1000, 800, 120);
    expect(perto.x).toBeGreaterThanOrEqual(0);
    expect(perto.y).toBeGreaterThanOrEqual(0);
    // Perto do canto oposto, ela cabe inteira dentro da tela.
    const longe = posicaoDaLupa(995, 795, 1000, 800, 120);
    expect(longe.x + 120).toBeLessThanOrEqual(1000);
    expect(longe.y + 120).toBeLessThanOrEqual(800);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npm test
```

Esperado: erro de importação de `iniciarCalibragem`.

- [ ] **Passo 3: acrescentar ao fim de `web/frontend/src/calibrate.ts`**

```ts
import { pontoDoPapel, type Vista } from "./canvas.js";

export type Calibragem = {
  pontos: Array<[number, number]>;
  ativa: boolean;
};

export function iniciarCalibragem(): Calibragem {
  return { pontos: [], ativa: true };
}

/** Guarda o ponto em coordenadas de papel — nunca de tela, que muda com o zoom. */
export function marcarPonto(c: Calibragem, v: Vista,
                            telaX: number, telaY: number): Calibragem {
  if (!c.ativa || c.pontos.length >= 2) return c;
  const p = pontoDoPapel(v, telaX, telaY);
  const pontos: Array<[number, number]> = [...c.pontos, [p.x, p.y]];
  return { pontos, ativa: pontos.length < 2 };
}

const FOLGA_DA_LUPA = 24;

/**
 * Onde desenhar a lupa, dado onde está o dedo.
 *
 * No toque o dedo cobre exatamente o que precisa ser mirado — a extremidade de
 * uma cota — e sem a lupa ninguém acerta. Ela fica ao lado do dedo, e vira para
 * o outro lado quando esbarraria na borda.
 */
export function posicaoDaLupa(telaX: number, telaY: number,
                              larguraTela: number, alturaTela: number,
                              lado: number): { x: number; y: number } {
  let x = telaX + FOLGA_DA_LUPA;
  let y = telaY - lado - FOLGA_DA_LUPA;
  if (x + lado > larguraTela) x = telaX - lado - FOLGA_DA_LUPA;
  if (y < 0) y = telaY + FOLGA_DA_LUPA;
  x = Math.max(0, Math.min(x, larguraTela - lado));
  y = Math.max(0, Math.min(y, alturaTela - lado));
  return { x, y };
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npm test
```

Esperado: os três testes novos verdes.

- [ ] **Passo 5: ligar na tela, em `web/frontend/src/main.ts`**

Acrescente aos imports:

```ts
import { escalaPorDoisPontos, iniciarCalibragem, marcarPonto, posicaoDaLupa,
         type Calibragem } from "./calibrate.js";
```

Declare o estado junto dos outros `let` do módulo:

```ts
let calibragem: Calibragem | null = null;
```

Acrescente o botão em `montarFaixaPrincipal()`, antes do de exportar:

```ts
  const calibrar = document.createElement("button");
  calibrar.className = "botao";
  calibrar.id = "calibrar";
  calibrar.type = "button";
  calibrar.textContent = "Calibrar (2 pontos)";
  calibrar.disabled = !geometria;
  calibrar.setAttribute("aria-pressed", String(Boolean(calibragem?.ativa)));
  calibrar.addEventListener("click", () => {
    calibragem = iniciarCalibragem();
    mostrarAviso({ titulo: "Calibração", podeTentarDeNovo: false,
                   detalhe: "Toque nas duas extremidades de uma medida " +
                            "conhecida da planta." });
    montarFaixaPrincipal();
  });
  faixaPrincipal.append(calibrar);
```

E a captura dos pontos, junto dos outros ouvintes do canvas:

```ts
tela.addEventListener("click", (e) => {
  if (!calibragem?.ativa) return;
  const proporcao = window.devicePixelRatio || 1;
  const caixa = tela.getBoundingClientRect();
  calibragem = marcarPonto(calibragem, vista,
                           (e.clientX - caixa.left) * proporcao,
                           (e.clientY - caixa.top) * proporcao);
  if (calibragem.ativa) return;

  const medida = window.prompt(
    `Quanto mede essa distância na planta, em ${estado.unidade}?`, "1");
  if (medida === null) { calibragem = null; mostrarAviso(null); return; }
  try {
    estado.escala = escalaPorDoisPontos(calibragem.pontos[0]!,
                                        calibragem.pontos[1]!, Number(medida));
    mostrarAviso(null);
  } catch (erro) {
    mostrarAviso({ titulo: "Não deu para calibrar", podeTentarDeNovo: true,
                   detalhe: erro instanceof Error ? erro.message : "" });
  }
  calibragem = null;
  montarFaixaPrincipal();
});
```

O `window.prompt` é provisório e feio de propósito: trocá-lo por uma caixa
própria é trabalho de acabamento, e prendê-lo aqui deixaria a tarefa grande
demais para uma revisão só. Registre como dívida no fim da etapa.

- [ ] **Passo 6: ligar a lupa, ainda em `web/frontend/src/main.ts`**

Sem este passo a `posicaoDaLupa` teria teste e nenhum uso — e no celular o dedo
cobre exatamente a extremidade que precisa ser mirada.

Acrescente o elemento logo abaixo da declaração de `tela`:

```ts
const lupa = document.createElement("canvas");
lupa.className = "lupa";
lupa.width = 120;
lupa.height = 120;
lupa.hidden = true;
document.querySelector(".area-do-desenho")!.append(lupa);
const AUMENTO_DA_LUPA = 3;
```

E o ouvinte que a acompanha, junto dos outros do canvas:

```ts
function moverLupa(clienteX: number, clienteY: number): void {
  if (!calibragem?.ativa) { lupa.hidden = true; return; }
  const caixa = tela.getBoundingClientRect();
  const proporcao = window.devicePixelRatio || 1;
  const x = (clienteX - caixa.left) * proporcao;
  const y = (clienteY - caixa.top) * proporcao;

  const ctxLupa = lupa.getContext("2d")!;
  const lado = lupa.width / AUMENTO_DA_LUPA;
  ctxLupa.clearRect(0, 0, lupa.width, lupa.height);
  // Recorta um pedaço do próprio canvas e o amplia: não redesenha nada, então
  // custa o mesmo em qualquer planta.
  ctxLupa.drawImage(tela, x - lado / 2, y - lado / 2, lado, lado,
                    0, 0, lupa.width, lupa.height);
  // Cruz no centro, para mirar o que o dedo esconde.
  ctxLupa.strokeStyle = "#3d7eff";
  ctxLupa.beginPath();
  ctxLupa.moveTo(lupa.width / 2, 0);
  ctxLupa.lineTo(lupa.width / 2, lupa.height);
  ctxLupa.moveTo(0, lupa.height / 2);
  ctxLupa.lineTo(lupa.width, lupa.height / 2);
  ctxLupa.stroke();

  const onde = posicaoDaLupa(clienteX - caixa.left, clienteY - caixa.top,
                             caixa.width, caixa.height, lupa.width);
  lupa.style.left = `${onde.x}px`;
  lupa.style.top = `${onde.y}px`;
  lupa.hidden = false;
}

tela.addEventListener("pointermove", (e) => {
  if (e.pointerType === "touch") moverLupa(e.clientX, e.clientY);
});
tela.addEventListener("pointerup", () => { lupa.hidden = true; });
```

- [ ] **Passo 7: conferir a olho**

Com os dois servidores no ar, calibre pela linha de 300 pt do PDF de teste
informando 3 e a unidade em metros; a faixa tem de passar a mostrar
`1 pt = 0.01 m`.

No celular, ou com a emulação de toque do navegador, confira que a lupa aparece
ao arrastar o dedo durante a calibração, foge do dedo e não sai da tela.

- [ ] **Passo 8: commit**

```bash
git add web/frontend/src/calibrate.ts web/frontend/src/main.ts \
        web/frontend/testes/calibrate.test.ts
git commit -m "Calibracao por dois pontos na tela, com a lupa fugindo do dedo"
```

---

### Tarefa 14: Playwright de ponta a ponta

**Arquivos:**
- Criar: `web/frontend/playwright.config.ts`
- Criar: `web/frontend/e2e/conversao.spec.ts`
- Modificar: `web/frontend/package.json`
- Criar: `tests/gerar_pdf_de_teste.py`

**Interfaces:**
- Consome: a aplicação inteira
- Produz: `npm run e2e`

**Atenção antes de começar:** `*.pdf` está no `.gitignore` deste repositório, e
com razão — plantas de cliente não vão para o GitHub. Então o PDF que o teste
envia **não é versionado**: ele é gerado a cada execução, por um `globalSetup`
do Playwright. Versioná-lo com `git add -f` funcionaria e seria errado: abriria
exceção na regra que protege os arquivos dos seus clientes.

- [ ] **Passo 1: gerar o PDF que o teste envia, `tests/gerar_pdf_de_teste.py`**

```python
"""Grava em disco o PDF sintético que o teste de ponta a ponta envia."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_roundtrip import make_test_pdf

DESTINO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "planta_de_teste.pdf")

if __name__ == "__main__":
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    make_test_pdf(DESTINO)
    print(f"PDF de teste gravado em {DESTINO}")
```

Confira que ele roda:

```bash
./.venv/Scripts/python.exe tests/gerar_pdf_de_teste.py
```

- [ ] **Passo 2: instalar o Playwright**

```bash
cd web/frontend
npm install --save-dev @playwright/test
npx playwright install chromium
```

- [ ] **Passo 3: `web/frontend/playwright.config.ts`**

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // O PDF de teste é gerado a cada execução, não versionado: `*.pdf` está no
  // .gitignore para que planta de cliente nunca vá ao GitHub, e abrir exceção
  // com `git add -f` enfraqueceria justamente a regra que protege os arquivos
  // do usuário.
  globalSetup: "./e2e/preparar.ts",
  // Sem repetição automática: um teste que só passa na segunda tentativa está
  // escondendo um defeito. A etapa 2 já mostrou o preço disso.
  retries: 0,
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:5173", trace: "retain-on-failure" },
  webServer: [
    {
      // O caminho é relativo ao `cwd` abaixo, que já é a raiz do repositório.
      command: ".venv/Scripts/python.exe -m uvicorn web.api.main:app --port 8000",
      cwd: "../..",
      url: "http://127.0.0.1:8000/docs",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 5173 --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
```

O `url:` de cada servidor é o que faz o Playwright **esperar por condição**: ele
só começa quando o endereço responde. Nada de `sleep`.

- [ ] **Passo 4: acrescentar o script ao `package.json`**

```json
    "e2e": "playwright test",
```

- [ ] **Passo 5: o preparo, `web/frontend/e2e/preparar.ts`**

```ts
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

/**
 * Gera o PDF sintético antes da suíte.
 *
 * Ele não é versionado: `*.pdf` está no .gitignore para impedir que planta de
 * cliente vá parar no GitHub, e forçar exceção para este arquivo enfraqueceria
 * a regra inteira. Gerar custa milissegundos.
 */
export default function preparar(): void {
  const raiz = fileURLToPath(new URL("../../..", import.meta.url));
  execFileSync(".venv/Scripts/python.exe",
               ["tests/gerar_pdf_de_teste.py"],
               { cwd: raiz, stdio: "inherit" });
}
```

- [ ] **Passo 6: escrever o teste, `web/frontend/e2e/conversao.spec.ts`**

```ts
import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const PLANTA = fileURLToPath(
  new URL("../../../tests/fixtures/planta_de_teste.pdf", import.meta.url));

test("converte uma planta de ponta a ponta", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles("#escolher-pdf", PLANTA);

  // Espera por condição: o botão só habilita quando a geometria chegou.
  await expect(page.locator("#exportar")).toBeEnabled({ timeout: 60_000 });
  await expect(page.locator("#aviso")).toBeHidden();

  // A estimativa apareceu e não é zero.
  const estimativa = page.locator("#estimativa");
  await expect(estimativa).toContainText("≈");

  // Um chip de layer existe e desligá-lo muda a estimativa.
  const antes = await estimativa.textContent();
  const chip = page.locator("#faixa-opcoes button", { hasText: "TEXTO" });
  await chip.click();
  await expect(estimativa).not.toHaveText(antes!);
  await expect(chip).toHaveAttribute("aria-pressed", "false");

  // Ligar "unir em polilinhas" também mexe na estimativa.
  const depoisDoLayer = await estimativa.textContent();
  await page.locator("#faixa-opcoes button", { hasText: "Unir em polilinhas" }).click();
  await expect(estimativa).not.toHaveText(depoisDoLayer!);

  // Exporta e o download acontece.
  const download = page.waitForEvent("download");
  await page.locator("#exportar").click();
  const arquivo = await download;
  expect(await arquivo.path()).toBeTruthy();
});

test("o desenho aparece no canvas", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles("#escolher-pdf", PLANTA);
  await expect(page.locator("#exportar")).toBeEnabled({ timeout: 60_000 });

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
```

- [ ] **Passo 7: rodar**

```bash
cd web/frontend && npm run e2e
```

Esperado: dois testes verdes. O `globalSetup` gera o PDF antes de começar.

- [ ] **Passo 8: apagar o PDF gerado e rodar de novo**

```bash
rm tests/fixtures/planta_de_teste.pdf
cd web/frontend && npm run e2e
```

Tem de passar igual. É assim que se confirma que a suíte não depende de um
arquivo que só existe na sua máquina — que era exatamente o defeito de
versionar o PDF num repositório que ignora `*.pdf`.

- [ ] **Passo 9: rodar três vezes seguidas**

```bash
cd web/frontend && npm run e2e && npm run e2e && npm run e2e
```

As três têm de passar. Uma falha em três é teste intermitente, não azar — e
intermitência não entra no repositório. Se falhar, o conserto é substituir a
espera por uma condição melhor, nunca aumentar o tempo limite.

- [ ] **Passo 10: commit**

O PDF gerado **não** entra: `*.pdf` está no `.gitignore`, e é assim que fica.

```bash
git add web/frontend/playwright.config.ts web/frontend/e2e/ \
        web/frontend/package.json web/frontend/package-lock.json \
        tests/gerar_pdf_de_teste.py
git commit -m "Teste de ponta a ponta no Playwright, esperando por condicao"
```

---

### Tarefa 15: servir os estáticos e compilar no Docker

Fecha a etapa: o frontend passa a ser servido pelo próprio FastAPI, e o build
acontece dentro do contêiner — a VPS nunca instala `node`.

**Arquivos:**
- Modificar: `web/api/main.py`
- Criar: `deploy/Dockerfile`
- Criar: `.dockerignore`
- Modificar: `web/README.md`
- Testar: `tests/test_api_estaticos.py`

**Interfaces:**
- Consome: `web/frontend/dist/` (gerado por `npm run build`)
- Produz: a aplicação servindo `/` e mantendo `/api/...`

- [ ] **Passo 1: escrever o teste que falha, `tests/test_api_estaticos.py`**

```python
"""O serviço entrega o frontend compilado, sem atrapalhar as rotas da API."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

from fastapi.testclient import TestClient

from web.api.main import PASTA_ESTATICOS, app

cliente = TestClient(app)


def test_api_continua_respondendo():
    """A montagem dos estáticos não pode engolir /api."""
    r = cliente.get("/api/jobs/" + "z" * 32)
    assert r.status_code == 400, r.status_code
    print("OK: as rotas da API continuam antes dos estáticos")


def test_raiz_serve_o_index_quando_existe():
    if not (PASTA_ESTATICOS / "index.html").exists():
        print("OK: sem dist/ compilado, a raiz é opcional (pulado)")
        return
    r = cliente.get("/")
    assert r.status_code == 200, r.status_code
    assert "<html" in r.text.lower()
    print("OK: a raiz serve o index compilado")


def test_sem_dist_o_servico_ainda_sobe():
    """Sem o frontend compilado, a API tem de subir do mesmo jeito.

    É o caso de todo desenvolvedor que só mexe no Python, e do teste de API.
    """
    r = cliente.post("/api/jobs")
    assert r.status_code == 422, r.status_code
    print("OK: o serviço sobe mesmo sem o frontend compilado")


if __name__ == "__main__":
    test_api_continua_respondendo()
    test_raiz_serve_o_index_quando_existe()
    test_sem_dist_o_servico_ainda_sobe()
    print("Todos os testes de estáticos passaram.")
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_api_estaticos.py
```

Esperado: `ImportError: cannot import name 'PASTA_ESTATICOS'`.

- [ ] **Passo 3: montar os estáticos, ao fim de `web/api/main.py`**

```python
from fastapi.staticfiles import StaticFiles

PASTA_ESTATICOS = Path(__file__).resolve().parents[1] / "frontend" / "dist"

# A montagem vem por último de propósito: o FastAPI resolve as rotas na ordem
# em que foram declaradas, e um `/` montado antes engoliria `/api/...`.
#
# `check_dir=False` porque quem mexe só no Python não compila o frontend, e o
# serviço tem de subir do mesmo jeito — inclusive nos testes de API.
if PASTA_ESTATICOS.is_dir():
    app.mount("/", StaticFiles(directory=PASTA_ESTATICOS, html=True),
              name="frontend")
```

- [ ] **Passo 4: rodar e ver passar**

```bash
./.venv/Scripts/python.exe tests/test_api_estaticos.py
```

Esperado: as três linhas `OK:`.

- [ ] **Passo 5: compilar e conferir servindo de verdade**

```bash
cd web/frontend && npm run build && cd ../..
./.venv/Scripts/python.exe tests/test_api_estaticos.py
```

Agora a segunda linha tem de dizer "a raiz serve o index compilado", não
"pulado". Suba o uvicorn sozinho, sem o Vite, e abra `http://localhost:8000`:
a tela tem de funcionar igual.

- [ ] **Passo 6: `.dockerignore` na raiz do repositório**

```
.git
.venv
venv
__pycache__
*.pyc
node_modules
web/frontend/dist
web/frontend/node_modules
dados
Input
.superpowers
```

`web/frontend/dist` está na lista de propósito: quem compila é o contêiner, e
copiar um `dist/` da máquina de desenvolvimento é exatamente o jeito de subir
uma versão que não corresponde ao fonte.

- [ ] **Passo 7: `deploy/Dockerfile`**

```dockerfile
# Estágio 1: compilar o frontend. Fica aqui, e só aqui, o node.
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY web/frontend/package*.json ./
RUN npm ci
COPY web/frontend/ ./
COPY tests/casos_select.json /tests/casos_select.json
COPY tests/fixtures/ /tests/fixtures/
# O build roda os testes antes: uma imagem não deve nascer de código que
# desobedece ao contrato do select().
RUN npm test && npm run build

# Estágio 2: o que de fato vai ao ar. Sem node, sem node_modules.
FROM python:3.13-slim
WORKDIR /app
RUN adduser --system --group --no-create-home servico

COPY requirements.txt web/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r web/requirements.txt

COPY pdftodxf/ ./pdftodxf/
COPY web/api/ ./web/api/
COPY --from=frontend /frontend/dist ./web/frontend/dist

ENV PDFTODXF_DADOS=/dados
RUN mkdir -p /dados && chown servico:servico /dados
USER servico
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "web.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Passo 8: conferir que a imagem sobe**

```bash
docker build -f deploy/Dockerfile -t pdftodxf .
docker run --rm -p 8000:8000 pdftodxf
```

Abra `http://localhost:8000`: a tela tem de aparecer e converter. Se o `docker`
não estiver na sua máquina, deixe este passo registrado como pendente para a
etapa 5 — mas **não marque a tarefa como concluída sem ele**.

- [ ] **Passo 9: atualizar `web/README.md`**

Acrescente, depois da seção de rotas:

````markdown
## Frontend

Em desenvolvimento, dois servidores:

```powershell
./.venv/Scripts/python.exe -m uvicorn web.api.main:app --port 8000
cd web/frontend; npm run dev
```

O Vite serve em `http://localhost:5173` e repassa `/api` para o uvicorn.

Em produção não há Vite: o `npm run build` gera `web/frontend/dist` e o próprio
FastAPI o serve. O `deploy/Dockerfile` compila num estágio à parte, então a
máquina de produção nunca instala `node`.

```powershell
cd web/frontend; npm test        # vitest: contrato, formato, canvas
cd web/frontend; npm run e2e     # Playwright de ponta a ponta
```
````

- [ ] **Passo 10: rodar a bateria inteira, Python e TypeScript**

```bash
cd "C:/Users/leole/Programas/PdfToDxf"
for t in test_optimize test_roundtrip test_preview test_casos_select \
         test_packing test_api_upload test_api_extracao test_api_geometria \
         test_api_export test_storage test_fixture_geometria test_api_estaticos; do
  ./.venv/Scripts/python.exe tests/$t.py >/dev/null 2>&1 \
    && echo "ok  $t" || echo "FALHOU  $t"
done
cd web/frontend && npm test && npm run e2e
```

Esperado: doze `ok` e as duas suítes de TypeScript verdes.

- [ ] **Passo 11: commit**

```bash
git add web/api/main.py tests/test_api_estaticos.py deploy/Dockerfile \
        .dockerignore web/README.md
git commit -m "Serve o frontend compilado e compila num estagio do Docker"
```

---

## Definição de pronto

Ao fim da etapa 3, tudo abaixo é verdade:

- `npm test` passa, incluindo os 1024 casos do contrato conferindo máscara e
  bytes, e `tests/casos_select.json` está intocado no `git diff`.
- `npm run e2e` passa três vezes seguidas, sem repetição automática.
- Os testes Python continuam passando, mais os três novos
  (`test_fixture_geometria`, `test_api_estaticos`) — doze arquivos ao todo.
- Um PDF vetorial sobe, desenha, calibra, muda com as opções e volta como DXF
  válido, tudo pelo navegador.
- Esqueleto e detalhe intercalados dão o mesmo que o `select()` do Python sobre
  a lista inteira, **com dedup ligado**.
- `npm run build` roda `tsc --noEmit` sem erro.
- A imagem Docker sobe e serve a tela sem `node` no contêiner final.
- A medição da tarefa 1 está registrada em `medicao/RESULTADO.md`.

## O que fica para as etapas seguintes

- Conta, cota e o canto direito da faixa 1 — etapa 4
- `privacidade.html`, ligada no rodapé — etapa 4, junto do registro
- Caddy, HTTPS, volumes e `docker-compose.yml` — etapa 5
- A caixa de diálogo da calibração, hoje um `window.prompt` — dívida registrada
  na tarefa 13
- Canvas pré-renderizado durante o gesto: a spec geral o descreve, e ele só se
  justifica se a medição da tarefa 1 mostrar que redesenhar a cada quadro pesa.
  Decida com o número na mão, não antes.
