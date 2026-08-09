# Etapa 3.5 — interface redesenhada: plano de implementação

> **Para quem executa com agentes:** SUB-SKILL OBRIGATÓRIA: use
> `superpowers:subagent-driven-development` (recomendada) ou
> `superpowers:executing-plans` para executar tarefa a tarefa. Os passos usam
> caixas (`- [ ]`) para acompanhamento.

**Objetivo:** trocar o cabeçalho de duas faixas por uma barra superior fina mais
um painel lateral recolhível, com rótulos, estados visíveis, explicação por
opção, camadas com cor e contagem, e a estimativa mostrando o tamanho antes e
depois da compactação.

**Arquitetura:** o motor de desenho não é tocado. Toda lógica nova que dá para
testar sem navegador sai como função pura em módulo próprio (`camadas.ts`, a
comparação em `toolbar.ts`, a máquina de estado em `painel.ts`); a montagem do
DOM fica em módulos finos (`barra.ts`, `secoes.ts`, `ui/controles.ts`) cobertos
pelo Playwright. É a divisão que o projeto já usa — o vitest deste repositório
roda com `environment: "node"` e **não tem `document`**.

**Tecnologias:** TypeScript puro, Canvas 2D, Vite 5, vitest 2, Playwright.
Sem framework e sem biblioteca de componentes.

**Documento que governa:** `docs/superpowers/specs/2026-08-09-interface-redesenho-design.md`

## Restrições globais

Valem para todas as tarefas, sem repetição em cada uma:

- **Nenhuma dependência nova**, nem de runtime nem de desenvolvimento.
  `web/frontend/package.json`, `requirements.txt` e `web/requirements.txt`
  terminam a etapa com exatamente as linhas que têm hoje.
- **Sem framework, sem biblioteca de componentes, sem fonte baixada.** Ícones em
  SVG inline, só os poucos necessários.
- **O vitest roda com `environment: "node"`** (`web/frontend/vite.config.ts:14`).
  Não existe `document` nos testes de unidade. Só código puro entra em
  `testes/`; o que monta DOM é coberto pelo Playwright.
- **Nada de Python muda.** Nem `classify()`, nem `meta.json`, nem rota alguma.
- **O motor de desenho não é tocado:** `canvas.ts`, `pintor.ts`, `lista.ts`,
  `ordem.ts`, `formato.ts`, `select.ts`, `estimativa.ts`, `api.ts`, `gestos.ts`
  e `calibrate.ts` ficam como estão. `estimativa.ts` é só *chamado* de um lugar
  novo; seu código não muda.
- **`[hidden] { display: none !important; }` continua no CSS.** Foi correção de
  um defeito real: `display: grid` no `.aviso` atropelava o atributo `hidden` e
  o painel escuro cobria a planta inteira.
- **O fundo do desenho continua numa variável única** (`--fundo-do-desenho`),
  para que invertê-lo siga sendo uma linha.
- **Texto da interface em português do Brasil.**
- Comandos, sempre a partir de `web/frontend`:
  `npm test` · `npm run build` · `npm run e2e`
- Para abrir a tela à mão use `http://localhost:5173`, **não** `127.0.0.1`: o
  Vite escuta em `localhost` (IPv6) por padrão e recusa a conexão no IPv4.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Situação |
|---|---|---|
| `src/camadas.ts` | contagem e cor predominante por camada, a partir da geometria | **novo**, puro |
| `src/painel.ts` | máquina de estado do painel (aberto/recolhido/gaveta, seção ativa) e a montagem dele | **novo**, parte pura + parte DOM |
| `src/secoes.ts` | as três seções: Escala, Compactação, Camadas | **novo**, DOM |
| `src/barra.ts` | a barra superior | **novo**, DOM |
| `src/ui/icones.ts` | os `d` dos ícones, e a busca por nome | **novo**, puro |
| `src/ui/controles.ts` | interruptor, campo com unidade, botão, linha de camada, ícone | **novo**, DOM |
| `src/toolbar.ts` | estado da tela e os textos; perde a montagem da faixa 2 | modificado |
| `src/estilo.css` | paleta, tipografia, espaçamento, componentes | reescrito |
| `src/main.ts` | composição e ligação | modificado |
| `index.html` | esqueleto da tela | modificado |
| `testes/camadas.test.ts` | | **novo** |
| `testes/painel.test.ts` | | **novo** |
| `testes/icones.test.ts` | | **novo** |
| `testes/toolbar.test.ts` | ganha os casos da comparação | modificado |
| `e2e/conversao.spec.ts` | passa a mirar por `data-teste`; ganha casos novos | modificado |

`estados.ts` **não** muda nesta etapa. As cinco linhas de erro novas são da
etapa 4.

---

## Tarefa 1: contagem e cor predominante por camada

**Arquivos:**
- Criar: `web/frontend/src/camadas.ts`
- Teste: `web/frontend/testes/camadas.test.ts`

**Interfaces:**
- Consome: `Geometria` de `./formato.js` (campos `layer_id: Uint32Array`,
  `cor: Uint32Array`, `layers: string[]`).
- Produz: `resumoDasCamadas(g: Geometria): ResumoDeCamada[]`, com
  `ResumoDeCamada = { indice: number; nome: string; n: number; cor: number }`;
  `proporcaoRepetida(g: Geometria): number | null`; e
  `precisaDeBusca(quantasCamadas: number): boolean`.
  A tarefa 6 usa a proporção na linha de apoio do "remover duplicados"; a
  tarefa 7 monta a seção Camadas com as outras duas.

- [ ] **Passo 1: escrever o teste que falha**

Crie `web/frontend/testes/camadas.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { resumoDasCamadas } from "../src/camadas.js";
import type { Geometria } from "../src/formato.js";

/** Geometria mínima: só o que `resumoDasCamadas` lê é significativo. */
function geo(layers: string[], layerId: number[], cor: number[]): Geometria {
  const n = layerId.length;
  return {
    n,
    kind: new Uint8Array(n),
    layer_id: new Uint32Array(layerId),
    is_fill: new Uint8Array(n),
    length_um: new Uint32Array(n),
    dup_group: new Int32Array(n),
    byte_cost: new Uint32Array(n),
    layers,
    n_groups: 1,
    idx: new Uint32Array(n),
    cor: new Uint32Array(cor),
    coord_off: new Uint32Array(n + 1),
    coords: new Float32Array(0),
    texto_off: new Uint32Array(n + 1),
    texto: new Uint8Array(0),
  };
}

describe("camadas.ts", () => {
  it("conta as entidades de cada camada", () => {
    const r = resumoDasCamadas(geo(["A", "B"], [0, 0, 1], [1, 1, 2]));
    expect(r.map((c) => [c.nome, c.n])).toEqual([["A", 2], ["B", 1]]);
  });

  it("a soma das contagens é o total de entidades", () => {
    const r = resumoDasCamadas(geo(["A", "B", "C"], [2, 0, 2, 1, 2], [0, 0, 0, 0, 0]));
    expect(r.reduce((s, c) => s + c.n, 0)).toBe(5);
  });

  it("a cor é a mais frequente da camada, não a primeira", () => {
    const r = resumoDasCamadas(
      geo(["A"], [0, 0, 0], [0xff0000, 0x00ff00, 0x00ff00]));
    expect(r[0]!.cor).toBe(0x00ff00);
  });

  it("empate de frequência resolve pela menor cor, não pela ordem de chegada", () => {
    const a = resumoDasCamadas(geo(["A"], [0, 0], [0xff0000, 0x0000ff]));
    const b = resumoDasCamadas(geo(["A"], [0, 0], [0x0000ff, 0xff0000]));
    expect(a[0]!.cor).toBe(0x0000ff);
    expect(b[0]!.cor).toBe(a[0]!.cor);
  });

  it("camada sem nenhuma entidade não quebra e vem com contagem zero", () => {
    const r = resumoDasCamadas(geo(["A", "VAZIA"], [0], [0x123456]));
    expect(r[1]).toEqual({ indice: 1, nome: "VAZIA", n: 0, cor: 0 });
  });

  it("o índice devolvido é a posição em layers", () => {
    const r = resumoDasCamadas(geo(["A", "B", "C"], [1], [7]));
    expect(r.map((c) => c.indice)).toEqual([0, 1, 2]);
  });

  it("a proporção de repetidos vem dos grupos de duplicata", () => {
    // 5 entidades em 2 grupos: 3 são repetição de alguém.
    const g = geo(["A"], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]);
    g.n_groups = 2;
    expect(proporcaoRepetida(g)).toBe(60);
  });

  it("sem repetição nenhuma, a proporção é zero e não some", () => {
    const g = geo(["A"], [0, 0], [0, 0]);
    g.n_groups = 2;
    expect(proporcaoRepetida(g)).toBe(0);
  });

  it("página vazia não divide por zero", () => {
    const g = geo(["A"], [], []);
    g.n_groups = 0;
    expect(proporcaoRepetida(g)).toBe(null);
  });

  it("a busca de camadas aparece acima de quinze", () => {
    expect(precisaDeBusca(15)).toBe(false);
    expect(precisaDeBusca(16)).toBe(true);
  });
});
```

E troque a linha de importação do topo por:

```ts
import {
  precisaDeBusca, proporcaoRepetida, resumoDasCamadas,
} from "../src/camadas.js";
```

O fixture `geo` devolve `n_groups: 1`; os casos acima o sobrescrevem, e por isso
o campo precisa ser gravável — ele já é, porque `Geometria` não é `readonly`.

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npx vitest run testes/camadas.test.ts
```

Esperado: FALHA, com erro de resolução do módulo `../src/camadas.js`.

- [ ] **Passo 3: implementar**

Crie `web/frontend/src/camadas.ts`:

```ts
/**
 * Resumo por camada: quantas entidades tem e qual a cor predominante.
 *
 * Calculado no navegador, dos vetores `layer_id` e `cor` que o binário já
 * carrega. Nada disso vem do `meta.json` — e não precisa vir: o dado já está
 * aqui, e pedi-lo ao servidor seria fazer o Python calcular duas vezes o que o
 * cliente tem em mãos.
 */
import type { Geometria } from "./formato.js";

export type ResumoDeCamada = {
  indice: number;
  nome: string;
  n: number;
  /** 0xRRGGBB. Zero quando a camada não tem nenhuma entidade. */
  cor: number;
};

export function resumoDasCamadas(g: Geometria): ResumoDeCamada[] {
  const contagem = new Uint32Array(g.layers.length);
  const cores: Array<Map<number, number>> = [];
  for (let i = 0; i < g.layers.length; i++) cores.push(new Map());

  const n = g.layer_id.length;
  for (let i = 0; i < n; i++) {
    const lid = g.layer_id[i]!;
    // Layer fora da tabela seria arquivo corrompido; ignorar é melhor do que
    // estourar e deixar a tela sem lista nenhuma.
    if (lid >= contagem.length) continue;
    contagem[lid]!++;
    const tabela = cores[lid]!;
    const c = g.cor[i]!;
    tabela.set(c, (tabela.get(c) ?? 0) + 1);
  }

  return g.layers.map((nome, indice) => ({
    indice,
    nome,
    n: contagem[indice]!,
    cor: predominante(cores[indice]!),
  }));
}

/**
 * A cor mais frequente; empate resolve pela menor.
 *
 * O desempate não é capricho. Sem ele o vencedor sairia da ordem de iteração do
 * `Map`, que é a ordem de inserção — e a mesma planta é carregada duas vezes,
 * primeiro só o esqueleto e depois inteira. A bolinha da camada mudaria de cor
 * sozinha entre uma carga e outra, o que parece defeito.
 */
function predominante(tabela: Map<number, number>): number {
  let melhor = 0;
  let quantas = -1;
  for (const [cor, n] of tabela) {
    if (n > quantas || (n === quantas && cor < melhor)) {
      melhor = cor;
      quantas = n;
    }
  }
  return melhor;
}

/**
 * Quanto da página é repetição, em porcentagem inteira. `null` se não há nada.
 *
 * Sai de graça: o `classify()` já agrupou as duplicatas em `dup_group`, e
 * `n_groups` é quantos grupos existem. Entidades menos grupos é quanta coisa é
 * cópia de alguém.
 *
 * Numa planta do acervo isto dá 60%, e é esse número que faz "remover
 * duplicados" deixar de ser um palpite para quem olha a tela.
 */
export function proporcaoRepetida(g: Geometria): number | null {
  const n = g.layer_id.length;
  if (n === 0 || g.n_groups <= 0) return null;
  return Math.round((1 - g.n_groups / n) * 100);
}

/** Acima disto a busca de camadas aparece. Abaixo, seria só ruído. */
export const CAMADAS_PARA_BUSCA = 15;

export function precisaDeBusca(quantasCamadas: number): boolean {
  return quantasCamadas > CAMADAS_PARA_BUSCA;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npx vitest run testes/camadas.test.ts
```

Esperado: PASSA, 10 testes.

- [ ] **Passo 5: provar que o teste do desempate morde**

Troque, temporariamente, `n === quantas && cor < melhor` por `false` em
`predominante`. Rode de novo: o teste "empate de frequência resolve pela menor
cor" deve **falhar**. Desfaça a alteração e confirme que volta a passar.

Isto não é teatro: o projeto já pegou três variantes erradas do `select()` que
passavam no contrato sem serem notadas.

- [ ] **Passo 6: commitar**

```bash
git add web/frontend/src/camadas.ts web/frontend/testes/camadas.test.ts
git commit -m "Contagem e cor predominante por camada, calculadas no cliente"
```

---

## Tarefa 2: a linha de base da estimativa e o texto comparado

**Arquivos:**
- Modificar: `web/frontend/src/toolbar.ts`
- Teste: `web/frontend/testes/toolbar.test.ts`

**Interfaces:**
- Consome: nada novo.
- Produz: `formatarBytes(bytes: number): string`,
  `textoDaComparacao(bytesBase: number, bytesAtual: number, parcial: boolean): string`,
  e o campo `bytesBase: number` em `EstadoDaTela`. A tarefa 5 mostra esse texto
  na barra; a tarefa 7 calcula a base.
- `textoDaEstimativa` continua exportada com a mesma assinatura e o mesmo
  resultado — há teste que a prende, e `main.ts` ainda a usa até a tarefa 5.

- [ ] **Passo 1: escrever os testes que falham**

Acrescente ao fim de `web/frontend/testes/toolbar.test.ts`, dentro do
`describe` existente:

```ts
  it("a comparação mostra base, atual e a redução", () => {
    expect(textoDaComparacao(12_300_000, 4_100_000, false))
      .toBe("12,3 MB → 4,1 MB · −67%");
  });

  it("sem redução, mostra um número só", () => {
    expect(textoDaComparacao(4_100_000, 4_100_000, false)).toBe("4,1 MB");
  });

  it("redução abaixo de 1% não vira ruído na barra", () => {
    expect(textoDaComparacao(1_000_000, 999_000, false)).toBe("1,0 MB");
  });

  it("a comparação parcial vem marcada", () => {
    expect(textoDaComparacao(12_300_000, 4_100_000, true))
      .toBe("12,3 MB → 4,1 MB · −67% (parcial)");
  });

  it("base zero não divide por zero", () => {
    expect(textoDaComparacao(0, 0, false)).toBe("0,0 kB");
  });

  it("formatarBytes vira kB abaixo de 1 MB", () => {
    expect(formatarBytes(2048)).toBe("2,0 kB");
    expect(formatarBytes(1_500_000)).toBe("1,5 MB");
  });
```

E troque a linha de importação do topo do arquivo por:

```ts
import {
  formatarBytes, opcoesEfetivas, textoDaComparacao, textoDaEstimativa,
} from "../src/toolbar.js";
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npx vitest run testes/toolbar.test.ts
```

Esperado: FALHA, com `textoDaComparacao is not a function` (ou erro de tipo no
`tsc`).

- [ ] **Passo 3: implementar**

Em `web/frontend/src/toolbar.ts`, acrescente `bytesBase` ao tipo:

```ts
export type EstadoDaTela = {
  opcoes: Opcoes;
  layersDesligados: Set<string>;
  escala: number;
  unidade: Unidade;
  parcial: boolean;
  bytes: number;
  /** A página inteira, sem nenhuma compactação e com todas as camadas. */
  bytesBase: number;
  sobreviventes: number;
};
```

E troque `textoDaEstimativa` por este bloco:

```ts
export function formatarBytes(bytes: number): string {
  const mb = bytes / 1_000_000;
  return mb >= 1
    ? `${mb.toFixed(1).replace(".", ",")} MB`
    : `${(bytes / 1000).toFixed(1).replace(".", ",")} kB`;
}

export function textoDaEstimativa(bytes: number, parcial: boolean): string {
  const texto = `≈ ${formatarBytes(bytes)}`;
  return parcial ? `${texto} (parcial)` : texto;
}

/**
 * O tamanho sem compactação, o tamanho atual e o quanto encolheu.
 *
 * A base é a página inteira — todas as camadas, nenhuma opção — então a
 * diferença inclui também as camadas que o usuário desligou. É de propósito:
 * ele quer saber o que aconteceu com o arquivo dele, e desligar camada é uma
 * das coisas que aconteceram.
 *
 * Abaixo de 1% a redução some da barra em vez de virar "−0%", que só ocupa
 * espaço e não informa nada.
 */
export function textoDaComparacao(bytesBase: number, bytesAtual: number,
                                  parcial: boolean): string {
  const reducao = bytesBase > 0
    ? Math.round((1 - bytesAtual / bytesBase) * 100)
    : 0;
  const texto = reducao >= 1
    ? `${formatarBytes(bytesBase)} → ${formatarBytes(bytesAtual)} · −${reducao}%`
    : formatarBytes(bytesAtual);
  return parcial ? `${texto} (parcial)` : texto;
}
```

Acrescente `bytesBase: 0,` ao objeto `base` no topo de
`web/frontend/testes/toolbar.test.ts`, junto de `bytes: 0,`, senão o `tsc`
recusa o literal.

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npx vitest run testes/toolbar.test.ts && npm run build
```

Esperado: vitest PASSA (9 testes) e o `tsc --noEmit` do `build` reclama de
`bytesBase` faltando em `main.ts`. Corrija acrescentando `bytesBase: 0,` ao
objeto `estado` em `web/frontend/src/main.ts:53`, junto de `bytes: 0,`. Rode de
novo: build limpo.

- [ ] **Passo 5: commitar**

```bash
git add web/frontend/src/toolbar.ts web/frontend/testes/toolbar.test.ts web/frontend/src/main.ts
git commit -m "Estimativa comparada: tamanho sem compactacao ao lado do atual"
```

---

## Tarefa 3: a máquina de estado do painel

**Arquivos:**
- Criar: `web/frontend/src/painel.ts`
- Teste: `web/frontend/testes/painel.test.ts`

**Interfaces:**
- Consome: nada.
- Produz: `Secao`, `ModoDoPainel`, `EstadoDoPainel`, `LARGURA_DA_GAVETA`,
  `estadoInicial`, `alternar`, `abrirEm`, `aoRedimensionar`, `paraGuardar`.
  A tarefa 6 monta o DOM em cima disso, no mesmo arquivo.

Esta tarefa entrega **só as funções puras**. A parte de DOM entra na tarefa 6,
no mesmo arquivo — é a mesma responsabilidade, e separá-la em dois arquivos
espalharia o painel sem ganho.

- [ ] **Passo 1: escrever o teste que falha**

Crie `web/frontend/testes/painel.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  abrirEm, alternar, aoRedimensionar, estadoInicial, LARGURA_DA_GAVETA,
  paraGuardar,
} from "../src/painel.js";

const LARGO = LARGURA_DA_GAVETA + 100;
const ESTREITO = LARGURA_DA_GAVETA - 1;

describe("painel.ts", () => {
  it("em tela larga sem preferência guardada, abre", () => {
    expect(estadoInicial(LARGO, null).modo).toBe("aberto");
  });

  it("em tela larga respeita a preferência guardada", () => {
    expect(estadoInicial(LARGO, "recolhido").modo).toBe("recolhido");
  });

  it("em tela estreita é gaveta, e a gaveta começa fechada", () => {
    const e = estadoInicial(ESTREITO, "recolhido");
    expect(e.modo).toBe("gaveta");
    expect(e.gavetaAberta).toBe(false);
  });

  it("alternar troca aberto e recolhido", () => {
    const a = estadoInicial(LARGO, null);
    expect(alternar(a).modo).toBe("recolhido");
    expect(alternar(alternar(a)).modo).toBe("aberto");
  });

  it("alternar na gaveta abre e fecha a gaveta, sem mudar o modo", () => {
    const g = estadoInicial(ESTREITO, null);
    expect(alternar(g)).toMatchObject({ modo: "gaveta", gavetaAberta: true });
    expect(alternar(alternar(g))).toMatchObject({ gavetaAberta: false });
  });

  it("abrir numa seção reabre o painel recolhido naquela seção", () => {
    const recolhido = alternar(estadoInicial(LARGO, null));
    const e = abrirEm(recolhido, "camadas");
    expect(e.modo).toBe("aberto");
    expect(e.secaoAtiva).toBe("camadas");
  });

  it("abrir numa seção na gaveta abre a gaveta naquela seção", () => {
    const e = abrirEm(estadoInicial(ESTREITO, null), "compactacao");
    expect(e).toMatchObject({ modo: "gaveta", gavetaAberta: true,
                              secaoAtiva: "compactacao" });
  });

  it("estreitar a janela vira gaveta e fecha o que estava aberto", () => {
    const e = aoRedimensionar(estadoInicial(LARGO, null), ESTREITO, null);
    expect(e).toMatchObject({ modo: "gaveta", gavetaAberta: false });
  });

  it("alargar de volta restaura a preferência guardada, não o padrão", () => {
    const g = alternar(estadoInicial(ESTREITO, null));   // gaveta aberta
    expect(aoRedimensionar(g, LARGO, "recolhido").modo).toBe("recolhido");
    expect(aoRedimensionar(g, LARGO, null).modo).toBe("aberto");
  });

  it("redimensionar sem cruzar o limiar não mexe em nada", () => {
    const a = estadoInicial(LARGO, null);
    expect(aoRedimensionar(a, LARGO + 1, null)).toBe(a);
  });

  it("gaveta não é preferência: não vai para o armazenamento", () => {
    expect(paraGuardar(estadoInicial(ESTREITO, null))).toBe(null);
    expect(paraGuardar(estadoInicial(LARGO, null))).toBe("aberto");
    expect(paraGuardar(alternar(estadoInicial(LARGO, null)))).toBe("recolhido");
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npx vitest run testes/painel.test.ts
```

Esperado: FALHA, com erro de resolução do módulo `../src/painel.js`.

- [ ] **Passo 3: implementar**

Crie `web/frontend/src/painel.ts`:

```ts
/**
 * O painel lateral: a máquina de estado aqui, o DOM logo abaixo.
 *
 * A parte pura fica separada porque é ela que dá para testar: o vitest deste
 * projeto roda com `environment: "node"` e não tem `document`. O que monta
 * elemento é coberto pelo Playwright.
 */

export type Secao = "escala" | "compactacao" | "camadas";
export type ModoDoPainel = "aberto" | "recolhido" | "gaveta";

/**
 * Abaixo disto o painel vira gaveta sobre o desenho.
 *
 * 900 px porque com o painel de 260 px sobra menos de 640 px de planta, que é
 * pouco para enxergar qualquer coisa numa A3 deitada.
 */
export const LARGURA_DA_GAVETA = 900;

export type EstadoDoPainel = {
  modo: ModoDoPainel;
  gavetaAberta: boolean;
  secaoAtiva: Secao;
};

export function estadoInicial(larguraDaJanela: number,
                              guardado: string | null): EstadoDoPainel {
  if (larguraDaJanela < LARGURA_DA_GAVETA) {
    return { modo: "gaveta", gavetaAberta: false, secaoAtiva: "escala" };
  }
  return {
    modo: guardado === "recolhido" ? "recolhido" : "aberto",
    gavetaAberta: false,
    secaoAtiva: "escala",
  };
}

/** O botão do canto: recolhe no desktop, abre e fecha a gaveta no celular. */
export function alternar(e: EstadoDoPainel): EstadoDoPainel {
  if (e.modo === "gaveta") return { ...e, gavetaAberta: !e.gavetaAberta };
  return { ...e, modo: e.modo === "aberto" ? "recolhido" : "aberto" };
}

/**
 * Clicar no ícone de uma seção com o painel recolhido reabre **naquela** seção.
 *
 * É o que justifica o modo recolhido mostrar ícones em vez de sumir: sem eles o
 * usuário perderia a orientação de onde as coisas estão.
 */
export function abrirEm(e: EstadoDoPainel, secao: Secao): EstadoDoPainel {
  if (e.modo === "gaveta") {
    return { ...e, secaoAtiva: secao, gavetaAberta: true };
  }
  return { ...e, secaoAtiva: secao, modo: "aberto" };
}

/**
 * Reage à janela mudando de tamanho, sem esquecer a preferência.
 *
 * Voltar da gaveta para "aberto" fixo apagaria a escolha de quem trabalha
 * recolhido: bastaria girar o tablet para perder o ajuste. Por isso a
 * preferência guardada entra de novo aqui.
 */
export function aoRedimensionar(e: EstadoDoPainel, larguraDaJanela: number,
                                guardado: string | null): EstadoDoPainel {
  const estreito = larguraDaJanela < LARGURA_DA_GAVETA;
  if (estreito) {
    if (e.modo === "gaveta") return e;
    return { ...e, modo: "gaveta", gavetaAberta: false };
  }
  if (e.modo !== "gaveta") return e;
  return {
    ...e,
    modo: guardado === "recolhido" ? "recolhido" : "aberto",
    gavetaAberta: false,
  };
}

/**
 * O que gravar. `null` quer dizer "não grave nada".
 *
 * Gaveta é consequência da largura da tela, não escolha do usuário: gravá-la
 * faria o desktop abrir em gaveta só porque a última visita foi no celular.
 */
export function paraGuardar(e: EstadoDoPainel): string | null {
  return e.modo === "gaveta" ? null : e.modo;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npx vitest run testes/painel.test.ts
```

Esperado: PASSA, 11 testes.

- [ ] **Passo 5: commitar**

```bash
git add web/frontend/src/painel.ts web/frontend/testes/painel.test.ts
git commit -m "Maquina de estado do painel lateral: aberto, recolhido e gaveta"
```

---

## Tarefa 4: paleta, tipografia e ícones

**Arquivos:**
- Criar: `web/frontend/src/ui/icones.ts`
- Reescrever: `web/frontend/src/estilo.css`
- Teste: `web/frontend/testes/icones.test.ts`

**Interfaces:**
- Produz: `CAMINHOS: Record<string, string>` e `caminho(nome: string): string`.
  As tarefas 5, 6 e 7 pedem ícones por nome.
- Produz também o vocabulário de CSS (variáveis e classes) que as tarefas
  seguintes usam. Os nomes de classe estão na tabela do passo 5.

- [ ] **Passo 1: escrever o teste que falha**

Crie `web/frontend/testes/icones.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { CAMINHOS, caminho } from "../src/ui/icones.js";

const NECESSARIOS = [
  "arquivo", "regua", "ajustes", "camadas", "olho", "olho-cortado",
  "baixar", "recolher", "menu", "busca",
];

describe("icones.ts", () => {
  it("tem exatamente os ícones que a tela usa, e nenhum a mais", () => {
    expect(Object.keys(CAMINHOS).sort()).toEqual([...NECESSARIOS].sort());
  });

  it("todo caminho é dado de path SVG começando por M", () => {
    for (const [nome, d] of Object.entries(CAMINHOS)) {
      expect(d.startsWith("M"), `${nome} não começa com M`).toBe(true);
      expect(d.length).toBeGreaterThan(10);
    }
  });

  it("pedir um ícone que não existe estoura com o nome dentro", () => {
    expect(() => caminho("inexistente")).toThrow(/inexistente/);
  });
});
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
cd web/frontend && npx vitest run testes/icones.test.ts
```

Esperado: FALHA, com erro de resolução do módulo `../src/ui/icones.js`.

- [ ] **Passo 3: implementar**

Crie `web/frontend/src/ui/icones.ts`. **O dado de cada `d` deve ser copiado do
arquivo correspondente do Tabler Icons** (licença MIT), e não inventado —
caminho inventado renderiza rabisco. Os arquivos, em
`tabler-icons/icons/outline/`:

| Nome aqui | Arquivo do Tabler | Onde é usado |
|---|---|---|
| `arquivo` | `file-upload.svg` | botão Abrir PDF |
| `regua` | `ruler-measure.svg` | seção Escala e botão Calibrar |
| `ajustes` | `adjustments.svg` | seção Compactação |
| `camadas` | `stack-2.svg` | seção Camadas |
| `olho` | `eye.svg` | camada ligada |
| `olho-cortado` | `eye-off.svg` | camada desligada |
| `baixar` | `download.svg` | botão Exportar DXF |
| `recolher` | `layout-sidebar-left-collapse.svg` | recolher o painel |
| `menu` | `menu-2.svg` | abrir a gaveta no celular |
| `busca` | `search.svg` | busca de camadas |

Cada `.svg` do Tabler tem um ou mais `<path d="…">`; junte os `d` de um mesmo
ícone num só, separados por espaço, e descarte os `<path stroke="none" d="M0
0h24v24H0z" fill="none"/>`, que são só a moldura invisível.

```ts
/**
 * Os caminhos dos ícones, em dado puro.
 *
 * Dado e não elemento: assim o módulo é testável no vitest, que roda em Node e
 * não tem `document`. Quem monta o `<svg>` é `controles.ts`.
 *
 * Origem: Tabler Icons (MIT), traçado de 24×24 com `stroke-width` 2. Só os dez
 * usados foram copiados — a spec geral pede "ícones desenhados em SVG inline,
 * só os poucos necessários", e trazer o pacote inteiro contrariaria isso.
 */
export const CAMINHOS: Record<string, string> = {
  arquivo: "…",
  regua: "…",
  ajustes: "…",
  camadas: "…",
  olho: "…",
  "olho-cortado": "…",
  baixar: "…",
  recolher: "…",
  menu: "…",
  busca: "…",
};

export function caminho(nome: string): string {
  const d = CAMINHOS[nome];
  if (!d) throw new Error(`ícone desconhecido: ${nome}`);
  return d;
}
```

- [ ] **Passo 4: rodar e ver passar**

```bash
cd web/frontend && npx vitest run testes/icones.test.ts
```

Esperado: PASSA, 3 testes. Se o primeiro falhar, faltou ou sobrou ícone; se o
segundo falhar, algum `d` foi copiado com a moldura invisível junto ou veio
vazio.

- [ ] **Passo 5: reescrever o CSS**

Substitua **todo** o conteúdo de `web/frontend/src/estilo.css` por:

```css
/* Moldura escura, papel claro: a interface não compete com o desenho.

   Uma escala de cinza de verdade no lugar de dois tons chapados, e o azul de
   destaque em exatamente três lugares — controle ligado, botão principal e anel
   de foco. Fora daí, cinza. */
:root {
  --c0: #101216;   /* fundo mais fundo: campos e recuos */
  --c1: #171a1f;   /* fundo da moldura */
  --c2: #1e2128;   /* barra e painel */
  --c3: #262a32;   /* controle em repouso */
  --c4: #333945;   /* borda */
  --c5: #49515f;   /* borda em foco do mouse */
  --c6: #7b8492;   /* texto de apoio */
  --c7: #b9c0cb;   /* texto secundário */
  --c8: #e8ebf0;   /* texto principal */

  --destaque: #3d7eff;
  --destaque-fundo: #1d3563;
  --destaque-texto: #cfe0fb;
  --alerta: #e2564f;

  /* Uma variável só: inverter o desenho depois é uma linha. */
  --fundo-do-desenho: #f7f7f5;

  --t-menor: 11px;
  --t-apoio: 12px;
  --t-corpo: 13px;
  --t-maior: 18px;

  --e1: 4px;
  --e2: 8px;
  --e3: 12px;
  --e4: 16px;

  --raio: 6px;
  --painel: 260px;
  --painel-recolhido: 48px;
}

* { box-sizing: border-box; }

/* O atributo `hidden` precisa ganhar de qualquer `display` do autor. A regra do
   navegador para `[hidden]` é fraca, e o `display: grid` do `.aviso` a
   atropelava em silêncio: o painel ficava sempre visível e, tendo fundo escuro
   semitransparente, cobria a planta inteira. */
[hidden] { display: none !important; }

html, body {
  margin: 0;
  height: 100%;
  background: var(--c1);
  color: var(--c8);
  font: var(--t-corpo)/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
}

#app { display: flex; flex-direction: column; height: 100%; }

/* --- barra superior ------------------------------------------------------ */

.barra {
  display: flex;
  align-items: center;
  gap: var(--e3);
  padding: var(--e2) var(--e3);
  background: var(--c2);
  border-bottom: 1px solid var(--c4);
  min-height: 48px;
}
.barra .direita { margin-left: auto; display: flex; align-items: center; gap: var(--e3); }

/* --- controles ----------------------------------------------------------- */

.botao {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: inherit;
  color: var(--c8);
  background: var(--c3);
  border: 1px solid var(--c4);
  border-radius: var(--raio);
  padding: 6px 10px;
  min-height: 32px;
  cursor: pointer;
}
.botao:hover { border-color: var(--c5); }
.botao:disabled { opacity: 0.4; cursor: default; }
.botao.principal {
  background: var(--destaque);
  border-color: var(--destaque);
  color: #fff;
}
.botao.discreto { background: transparent; border-color: transparent; }
.botao.discreto:hover { background: var(--c3); }

/* Alvo de toque confortável: no celular tudo cresce. */
@media (pointer: coarse) {
  .botao { min-height: 40px; padding: 8px 12px; }
}

:where(button, input, select, [tabindex]):focus-visible {
  outline: 2px solid var(--destaque);
  outline-offset: 1px;
}

.icone { width: 16px; height: 16px; flex: none; }

.rotulo {
  font-size: var(--t-menor);
  color: var(--c6);
  letter-spacing: 0.02em;
}
.apoio { font-size: var(--t-apoio); color: var(--c6); }
.secundario { color: var(--c7); }
.destaque-numero { font-size: var(--t-maior); }

.campo {
  font: inherit;
  color: var(--c8);
  background: var(--c0);
  border: 1px solid var(--c4);
  border-radius: var(--raio);
  padding: 5px 8px;
  min-height: 32px;
  width: 6ch;
}
.campo-largo { width: 100%; }
.com-unidade { display: inline-flex; align-items: center; gap: 6px; }

/* Interruptor: a forma já diz que tem dois estados, o que o botão azul chapado
   do cabeçalho antigo não dizia. */
.interruptor {
  display: flex;
  align-items: flex-start;
  gap: var(--e2);
  background: none;
  border: none;
  padding: var(--e1) 0;
  font: inherit;
  color: var(--c8);
  text-align: left;
  cursor: pointer;
  width: 100%;
}
.interruptor .trilho {
  position: relative;
  width: 28px; height: 16px;
  flex: none;
  margin-top: 2px;
  border-radius: 8px;
  background: var(--c4);
  transition: background 120ms;
}
.interruptor .botaozinho {
  position: absolute;
  top: 2px; left: 2px;
  width: 12px; height: 12px;
  border-radius: 50%;
  background: var(--c6);
  transition: transform 120ms, background 120ms;
}
.interruptor[aria-pressed="true"] .trilho { background: var(--destaque); }
.interruptor[aria-pressed="true"] .botaozinho {
  transform: translateX(12px);
  background: #fff;
}
.interruptor[aria-pressed="false"] .nome { color: var(--c7); }
.interruptor .explica {
  display: block;
  font-size: var(--t-menor);
  color: var(--c6);
}

/* --- painel lateral ------------------------------------------------------ */

.corpo { display: flex; flex: 1; min-height: 0; }

.painel {
  width: var(--painel);
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--e4);
  padding: var(--e3);
  background: var(--c2);
  border-right: 1px solid var(--c4);
  overflow-y: auto;
}
.painel[data-modo="recolhido"] {
  width: var(--painel-recolhido);
  padding: var(--e2) 0;
  align-items: center;
  gap: var(--e2);
  overflow: hidden;
}
.painel[data-modo="recolhido"] .secao { display: none; }
.painel[data-modo="recolhido"] .atalho { display: flex; }
.atalho { display: none; justify-content: center; width: 32px; height: 32px; }

.secao { display: flex; flex-direction: column; gap: var(--e2); }
.secao > header {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: space-between;
}

.lista-de-camadas {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 40vh;
  overflow-y: auto;
}
.camada {
  display: flex;
  align-items: center;
  gap: var(--e2);
  background: none;
  border: none;
  border-radius: var(--raio);
  padding: 5px 6px;
  font: inherit;
  color: var(--c8);
  cursor: pointer;
  width: 100%;
  text-align: left;
}
.camada:hover { background: var(--c3); }
.camada[aria-pressed="false"] { color: var(--c6); }
.camada .cor {
  width: 9px; height: 9px;
  flex: none;
  border-radius: 50%;
  border: 1px solid var(--c4);
}
.camada .nome {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.camada .quantas { font-size: var(--t-menor); color: var(--c6); }

/* Gaveta: em tela estreita o painel flutua sobre o desenho em vez de espremer
   tudo. Não é `position: fixed` — dentro do fluxo do `.corpo` basta absoluto. */
.corpo { position: relative; }
.painel[data-modo="gaveta"] {
  position: absolute;
  top: 0; bottom: 0; left: 0;
  z-index: 2;
  box-shadow: 0 0 0 100vmax rgb(0 0 0 / 0.45);
}

/* --- área do desenho ----------------------------------------------------- */

.area-do-desenho { position: relative; flex: 1; min-width: 0; min-height: 0; }
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
  gap: var(--e2);
  text-align: center;
  padding: var(--e4);
  background: color-mix(in srgb, var(--c1) 88%, transparent);
}
.aviso h2 { margin: 0; font-size: var(--t-maior); font-weight: 500; }
.aviso p { margin: 0; max-width: 46ch; color: var(--c7); }

.faixa-detalhe {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  padding: var(--e1) var(--e3);
  font-size: var(--t-apoio);
  color: var(--c7);
  background: var(--c2);
  border-top: 1px solid var(--c4);
}

.rodape {
  padding: 6px var(--e3);
  font-size: var(--t-apoio);
  color: var(--c6);
  background: var(--c2);
  border-top: 1px solid var(--c4);
}
.rodape a { color: var(--c6); }

.lupa {
  position: absolute;
  width: 120px; height: 120px;
  border: 2px solid var(--destaque);
  border-radius: 50%;
  overflow: hidden;
  pointer-events: none;
  background: var(--fundo-do-desenho);
}
```

Vocabulário que as tarefas seguintes usam:

| Classe | Para quê |
|---|---|
| `.barra`, `.barra .direita` | barra superior; `.direita` empurra o resto |
| `.botao`, `.botao.principal`, `.botao.discreto` | botões |
| `.campo`, `.campo-largo`, `.com-unidade` | entrada de número e texto |
| `.interruptor` com `.trilho`, `.botaozinho`, `.nome`, `.explica` | opção de compactação |
| `.painel[data-modo]`, `.secao`, `.atalho` | painel e modos |
| `.lista-de-camadas`, `.camada` com `.cor`, `.nome`, `.quantas` | camadas |
| `.rotulo`, `.apoio`, `.secundario`, `.destaque-numero`, `.icone` | texto e ícone |

- [ ] **Passo 6: conferir que nada quebrou ainda**

```bash
cd web/frontend && npm test && npm run build
```

Esperado: tudo PASSA. A tela ainda usa o cabeçalho antigo — as classes velhas
(`.faixa`, `.chip`, `.separador`, `.fraco`) sumiram, então **a tela fica feia
até a tarefa 5**. É esperado; não conserte no meio.

- [ ] **Passo 7: commitar**

```bash
git add web/frontend/src/ui/icones.ts web/frontend/testes/icones.test.ts web/frontend/src/estilo.css
git commit -m "Paleta, tipografia e os dez icones inline"
```

---

## Tarefa 5: a barra superior

**Arquivos:**
- Criar: `web/frontend/src/ui/controles.ts`
- Criar: `web/frontend/src/barra.ts`
- Modificar: `web/frontend/index.html`
- Modificar: `web/frontend/src/main.ts`
- Teste: `web/frontend/e2e/conversao.spec.ts`

**Interfaces:**
- `ui/controles.ts` produz: `criarIcone(nome: string): SVGSVGElement`,
  `criarBotao(o: {rotulo: string; icone?: string; classe?: string; teste?: string; titulo?: string; aoClicar: () => void}): HTMLButtonElement`,
  `criarInterruptor(o: {nome: string; explica: string; ligado: boolean; teste: string; aoMudar: () => void}): HTMLButtonElement`,
  `criarCampoComUnidade(o: {valor: number; unidade: string; rotulo: string; teste: string; passo?: string; aoMudar: (v: number) => void}): HTMLElement`.
  As tarefas 6 e 7 usam todos.
- `barra.ts` produz: `montarBarra(raiz: HTMLElement, c: ContextoDaBarra): void`.
- Todo elemento que o Playwright procura ganha `data-teste`. **Nenhum seletor
  novo por texto.**

- [ ] **Passo 1: escrever os controles**

Crie `web/frontend/src/ui/controles.ts`:

```ts
/**
 * Os poucos componentes da tela, montados na mão.
 *
 * `document.createElement` e não `innerHTML`: nome de camada vem do PDF do
 * usuário, e montar HTML com string faria de um layer chamado `<img onerror=…>`
 * um vetor de injeção. O texto vai por `textContent`, sempre.
 */
import { caminho } from "./icones.js";

const SVG = "http://www.w3.org/2000/svg";

export function criarIcone(nome: string): SVGSVGElement {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "icone");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(SVG, "path");
  p.setAttribute("d", caminho(nome));
  svg.append(p);
  return svg;
}

export function criarBotao(o: {
  rotulo: string; icone?: string; classe?: string; teste?: string;
  titulo?: string; aoClicar: () => void;
}): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `botao${o.classe ? ` ${o.classe}` : ""}`;
  if (o.teste) b.dataset["teste"] = o.teste;
  if (o.icone) b.append(criarIcone(o.icone));
  const texto = document.createElement("span");
  texto.textContent = o.rotulo;
  b.append(texto);
  if (o.titulo) b.title = o.titulo;
  b.addEventListener("click", o.aoClicar);
  return b;
}

/**
 * Interruptor com nome e uma linha explicando o efeito.
 *
 * É `<button aria-pressed>` e não `<input type=checkbox>` porque o rótulo tem
 * duas linhas com estilos diferentes, e porque `aria-pressed` é o que o resto
 * da tela já usa — um vocabulário só para leitor de tela.
 */
export function criarInterruptor(o: {
  nome: string; explica: string; ligado: boolean; teste: string;
  aoMudar: () => void;
}): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "interruptor";
  b.dataset["teste"] = o.teste;
  b.setAttribute("aria-pressed", String(o.ligado));

  const trilho = document.createElement("span");
  trilho.className = "trilho";
  const botaozinho = document.createElement("span");
  botaozinho.className = "botaozinho";
  trilho.append(botaozinho);

  const textos = document.createElement("span");
  const nome = document.createElement("span");
  nome.className = "nome";
  nome.textContent = o.nome;
  const explica = document.createElement("span");
  explica.className = "explica";
  explica.textContent = o.explica;
  textos.append(nome, explica);

  b.append(trilho, textos);
  b.addEventListener("click", o.aoMudar);
  return b;
}

export function criarCampoComUnidade(o: {
  valor: number; unidade: string; rotulo: string; teste: string;
  passo?: string; aoMudar: (v: number) => void;
}): HTMLElement {
  const caixa = document.createElement("label");
  caixa.className = "com-unidade apoio";

  const rotulo = document.createElement("span");
  rotulo.textContent = o.rotulo;

  const campo = document.createElement("input");
  campo.type = "number";
  campo.className = "campo";
  campo.min = "0";
  campo.step = o.passo ?? "0.1";
  campo.value = String(o.valor);
  campo.dataset["teste"] = o.teste;
  campo.addEventListener("change", () => {
    o.aoMudar(Math.max(0, Number(campo.value) || 0));
  });

  const unidade = document.createElement("span");
  unidade.textContent = o.unidade;

  caixa.append(rotulo, campo, unidade);
  return caixa;
}
```

- [ ] **Passo 2: escrever a barra**

Crie `web/frontend/src/barra.ts`:

```ts
/**
 * A barra superior: abrir, página, escala, estimativa e exportar.
 *
 * Fina de propósito. O que exige explicação mora no painel lateral; aqui fica
 * só o que precisa estar sempre à vista.
 *
 * O canto direito é onde a **etapa 4** encaixa o indicador de cota e o botão de
 * entrar. O `<div class="direita">` já existe para isso.
 */
import { criarBotao, criarIcone } from "./ui/controles.js";
import { textoDaComparacao, type EstadoDaTela } from "./toolbar.js";

export type ContextoDaBarra = {
  estado: EstadoDaTela;
  nomeDoArquivo: string;
  pagina: number;
  nPaginas: number;
  temGeometria: boolean;
  /** Só em tela estreita: o botão que abre a gaveta. */
  mostrarMenu: boolean;
  aoAbrirArquivo: (arquivo: File) => void;
  aoTrocarPagina: (pagina: number) => void;
  aoAlternarPainel: () => void;
  aoExportar: () => void;
};

export function montarBarra(raiz: HTMLElement, c: ContextoDaBarra): void {
  raiz.replaceChildren();

  if (c.mostrarMenu) {
    const menu = criarBotao({
      rotulo: "", icone: "menu", classe: "discreto", teste: "abrir-painel",
      titulo: "Opções", aoClicar: c.aoAlternarPainel,
    });
    menu.setAttribute("aria-label", "Opções");
    raiz.append(menu);
  }

  // O `<input type=file>` nativo escreve "Escolher ficheiro / Nenhum ficheiro
  // selecionado" com o idioma do navegador — foi o que apareceu em português de
  // Portugal na tela do usuário. Escondê-lo atrás de um botão nosso resolve o
  // texto e a aparência de uma vez.
  const escolher = document.createElement("input");
  escolher.type = "file";
  escolher.accept = "application/pdf";
  escolher.id = "escolher-pdf";
  escolher.hidden = true;
  escolher.addEventListener("change", () => {
    const arquivo = escolher.files?.[0];
    if (arquivo) c.aoAbrirArquivo(arquivo);
  });
  raiz.append(escolher, criarBotao({
    rotulo: "Abrir PDF", icone: "arquivo", teste: "abrir-pdf",
    aoClicar: () => escolher.click(),
  }));

  if (c.nomeDoArquivo) {
    const nome = document.createElement("span");
    nome.className = "apoio";
    nome.dataset["teste"] = "nome-do-arquivo";
    nome.textContent = c.nomeDoArquivo;
    raiz.append(nome);
  }

  if (c.nPaginas > 1) {
    const seletor = document.createElement("select");
    seletor.className = "botao";
    seletor.dataset["teste"] = "seletor-pagina";
    seletor.setAttribute("aria-label", "Página");
    for (let p = 1; p <= c.nPaginas; p++) {
      const opcao = document.createElement("option");
      opcao.value = String(p);
      opcao.textContent = `Página ${p} de ${c.nPaginas}`;
      opcao.selected = p === c.pagina;
      seletor.append(opcao);
    }
    seletor.addEventListener("change", () =>
      c.aoTrocarPagina(Number(seletor.value)));
    raiz.append(seletor);
  }

  const direita = document.createElement("div");
  direita.className = "direita";

  const estimativa = document.createElement("div");
  estimativa.dataset["teste"] = "estimativa";
  const rotulo = document.createElement("div");
  rotulo.className = "rotulo";
  rotulo.textContent = "DXF estimado";
  const valor = document.createElement("div");
  valor.className = "apoio secundario";
  valor.dataset["teste"] = "estimativa-valor";
  valor.textContent = textoDaComparacao(c.estado.bytesBase, c.estado.bytes,
                                        c.estado.parcial);
  estimativa.append(rotulo, valor);
  direita.append(estimativa);

  const exportar = criarBotao({
    rotulo: "Exportar DXF", icone: "baixar", classe: "principal",
    teste: "exportar", aoClicar: c.aoExportar,
  });
  exportar.disabled = !c.temGeometria;
  direita.append(exportar);

  raiz.append(direita);
}
```

- [ ] **Passo 3: trocar o esqueleto da página**

Substitua o `<body>` de `web/frontend/index.html` por:

```html
  <body>
    <div id="app">
      <div class="barra" id="barra"></div>
      <div class="corpo">
        <aside class="painel" id="painel" data-modo="aberto"></aside>
        <div class="area-do-desenho">
          <canvas id="desenho"></canvas>
          <div class="aviso" id="aviso" hidden></div>
          <div class="faixa-detalhe" id="faixa-detalhe" hidden></div>
        </div>
      </div>
      <div class="rodape">
        O texto das plantas e o endereço IP são registrados por 1 ano.
        <a href="/privacidade.html">Como tratamos seus dados</a>
      </div>
    </div>
    <script type="module" src="/src/main.ts"></script>
  </body>
```

- [ ] **Passo 4: ligar em `main.ts`**

Em `web/frontend/src/main.ts`:

1. Troque as duas linhas que pegam as faixas antigas (`#faixa-principal` e
   `#faixa-opcoes`, hoje nas linhas 38–39) por:

```ts
const barra = document.querySelector<HTMLElement>("#barra")!;
const painelRaiz = document.querySelector<HTMLElement>("#painel")!;
```

2. Troque o import de `toolbar.js` por:

```ts
import { opcoesEfetivas, type EstadoDaTela } from "./toolbar.js";
import { montarBarra } from "./barra.js";
```

3. Substitua a função `montarFaixaPrincipal()` inteira (hoje linhas 247–314)
   por:

```ts
function montarTopo(): void {
  montarBarra(barra, {
    estado,
    nomeDoArquivo,
    pagina,
    nPaginas,
    temGeometria: Boolean(geometria),
    mostrarMenu: false,          // a tarefa 6 liga isto ao modo do painel
    aoAbrirArquivo: (arquivo) => void abrir(arquivo),
    aoTrocarPagina: (p) => { pagina = p; void carregarPagina(); },
    aoAlternarPainel: () => {},  // a tarefa 6 liga isto
    aoExportar: () => void baixar(),
  });
}
```

4. Declare `let nomeDoArquivo = "";` junto das outras variáveis de topo (perto
   de `let job = "";`), e grave-o em `abrir()`, logo depois de
   `const ficha = await enviarPdf(...)`:

```ts
    nomeDoArquivo = arquivo.name;
```

5. Troque **todas** as chamadas de `montarFaixaPrincipal()` por `montarTopo()`
   (há uma em `recalcular`, uma no clique de `calibrar`, uma no fim do clique do
   canvas e a última linha do arquivo).

6. O botão **Calibrar** e a **escala** saem da barra e entram no painel, na
   tarefa 6. Até lá a calibração fica sem botão — é esperado, e o teste de ponta
   a ponta não a exercita.

7. Em `carregarPagina()`, troque a chamada
   `montarFaixaDeOpcoes(faixaOpcoes, estado, meta.layers, aoMudarOpcoes);` por
   nada (apague a linha), e apague a função `aoMudarOpcoes` — a tarefa 6 traz o
   substituto. Apague também `montarFaixaDeOpcoes` e `botaoLigavel` de
   `src/toolbar.ts`, junto do `OPCOES_DE_COMPACTACAO`, que a tarefa 6 recria em
   `secoes.ts`.

- [ ] **Passo 5: reescrever o teste de ponta a ponta**

Substitua **todo** o conteúdo de `web/frontend/e2e/conversao.spec.ts` por:

```ts
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

  // Ligar "unir em polilinhas" mexe na estimativa.
  const antes = await estimativa.textContent();
  await t(page, "opcao-join_polylines").click();
  await expect(estimativa).not.toHaveText(antes!);
  await expect(t(page, "opcao-join_polylines"))
    .toHaveAttribute("aria-pressed", "true");

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
```

O seletor `opcao-join_polylines` só existe depois da tarefa 6. **Este passo
deixa o primeiro teste vermelho de propósito** — é o que garante que a tarefa 6
seja escrita para satisfazê-lo, e não o contrário.

- [ ] **Passo 6: rodar**

```bash
cd web/frontend && npm test && npm run build && npm run e2e
```

Esperado: `npm test` e `npm run build` PASSAM. No `e2e`, "o desenho aparece no
canvas" PASSA e "converte uma planta de ponta a ponta" FALHA em
`opcao-join_polylines`. Confirme que a falha é essa, e não outra.

- [ ] **Passo 7: commitar**

```bash
git add web/frontend/src/ui/controles.ts web/frontend/src/barra.ts web/frontend/index.html web/frontend/src/main.ts web/frontend/src/toolbar.ts web/frontend/e2e/conversao.spec.ts
git commit -m "Barra superior fina, com botao de abrir proprio"
```

---

## Tarefa 6: o painel lateral e as seções Escala e Compactação

**Arquivos:**
- Modificar: `web/frontend/src/painel.ts` (acrescenta a parte de DOM)
- Criar: `web/frontend/src/secoes.ts`
- Modificar: `web/frontend/src/main.ts`
- Teste: `web/frontend/e2e/conversao.spec.ts`

**Interfaces:**
- `painel.ts` passa a produzir também
  `montarPainel(raiz: HTMLElement, e: EstadoDoPainel, secoes: ConteudoDasSecoes, aoAlternar: () => void, aoAbrirEm: (s: Secao) => void): void`,
  com `ConteudoDasSecoes = Record<Secao, () => HTMLElement>`.
- `secoes.ts` produz
  `secaoEscala(e: EstadoDaTela, temGeometria: boolean, aoCalibrar: () => void, aoMudar: () => void): HTMLElement`
  e
  `secaoCompactacao(e: EstadoDaTela, repetidos: number | null, aoMudar: () => void): HTMLElement`;
  a tarefa 7 acrescenta
  `secaoCamadas(e: EstadoDaTela, resumo: ResumoDeCamada[], parcial: boolean, aoMudar: () => void): HTMLElement`.
- Cada interruptor de compactação ganha `data-teste="opcao-<chave>"`, com a
  chave sendo o campo de `Opcoes` (`join_polylines`, `round_coords`, `dedup`,
  `drop_fills`). É o seletor que a tarefa 5 já usa no teste.

- [ ] **Passo 1: montar o DOM do painel**

Acrescente `import { criarIcone } from "./ui/controles.js";` ao **topo** de
`web/frontend/src/painel.ts` — importação no fim do arquivo funciona, porque o
ES module a iça, mas mistura leitura e não é o padrão do repositório. O resto
vai no fim do arquivo:

```ts
const ICONE_DA_SECAO: Record<Secao, string> = {
  escala: "regua",
  compactacao: "ajustes",
  camadas: "camadas",
};

const NOME_DA_SECAO: Record<Secao, string> = {
  escala: "Escala",
  compactacao: "Compactação",
  camadas: "Camadas",
};

export type ConteudoDasSecoes = Record<Secao, () => HTMLElement>;

export function montarPainel(raiz: HTMLElement, e: EstadoDoPainel,
                             conteudo: ConteudoDasSecoes,
                             aoAlternar: () => void,
                             aoAbrirEm: (s: Secao) => void): void {
  raiz.replaceChildren();
  raiz.dataset["modo"] = e.modo;
  raiz.hidden = e.modo === "gaveta" && !e.gavetaAberta;

  const recolher = document.createElement("button");
  recolher.type = "button";
  recolher.className = "botao discreto";
  recolher.dataset["teste"] = "recolher-painel";
  recolher.setAttribute("aria-label",
                        e.modo === "recolhido" ? "Abrir opções" : "Recolher opções");
  recolher.append(criarIcone("recolher"));
  recolher.addEventListener("click", aoAlternar);
  raiz.append(recolher);

  // No modo recolhido, só os três ícones — e clicar num deles reabre o painel
  // já naquela seção. É o que impede o usuário de perder a orientação.
  for (const secao of ["escala", "compactacao", "camadas"] as Secao[]) {
    const atalho = document.createElement("button");
    atalho.type = "button";
    atalho.className = "botao discreto atalho";
    atalho.dataset["teste"] = `atalho-${secao}`;
    atalho.setAttribute("aria-label", NOME_DA_SECAO[secao]);
    atalho.title = NOME_DA_SECAO[secao];
    atalho.append(criarIcone(ICONE_DA_SECAO[secao]));
    atalho.addEventListener("click", () => aoAbrirEm(secao));
    raiz.append(atalho);

    const bloco = document.createElement("section");
    bloco.className = "secao";
    bloco.dataset["teste"] = `secao-${secao}`;
    const cabecalho = document.createElement("header");
    const titulo = document.createElement("span");
    titulo.className = "rotulo";
    titulo.textContent = NOME_DA_SECAO[secao];
    cabecalho.append(titulo);
    bloco.append(cabecalho, conteudo[secao]());
    raiz.append(bloco);
  }
}
```

- [ ] **Passo 2: escrever as seções**

Crie `web/frontend/src/secoes.ts`:

```ts
/**
 * O conteúdo das seções do painel.
 *
 * Cada opção de compactação vem com uma linha explicando o efeito. Era o que
 * faltava: no cabeçalho antigo "Remover duplicados" era um botão azul sem
 * nenhuma pista do que faria com o desenho.
 */
import type { Unidade } from "./calibrate.js";
import type { Opcoes } from "./select.js";
import type { EstadoDaTela } from "./toolbar.js";
import {
  criarBotao, criarCampoComUnidade, criarInterruptor,
} from "./ui/controles.js";

const COMPACTACAO: Array<{ chave: keyof Opcoes; nome: string; explica: string }> = [
  { chave: "join_polylines", nome: "Unir em polilinhas",
    explica: "junta traços encadeados num só" },
  { chave: "round_coords", nome: "Arredondar coordenadas",
    explica: "menos casas decimais por ponto" },
  { chave: "dedup", nome: "Remover duplicados",
    explica: "descarta traços idênticos sobrepostos" },
  { chave: "drop_fills", nome: "Remover preenchimentos",
    explica: "descarta hachuras e áreas pintadas" },
];

/**
 * O "remover duplicados" fala da planta aberta, não em tese.
 *
 * "60% do desenho é repetido" é o que transforma a opção de palpite em decisão.
 * O número vem do `dup_group` que o binário já traz; quando a página está vazia
 * ou a proporção é zero, volta a frase genérica.
 */
function explicacao(chave: keyof Opcoes, repetidos: number | null): string {
  const padrao = COMPACTACAO.find((o) => o.chave === chave)!.explica;
  if (chave !== "dedup" || repetidos === null || repetidos <= 0) return padrao;
  return `${repetidos}% do desenho é repetido`;
}

const UNIDADES: Unidade[] = ["mm", "cm", "m"];

export function secaoEscala(e: EstadoDaTela, temGeometria: boolean,
                            aoCalibrar: () => void,
                            aoMudar: () => void): HTMLElement {
  const caixa = document.createElement("div");
  caixa.className = "secao";

  const valor = document.createElement("div");
  valor.className = "destaque-numero";
  valor.dataset["teste"] = "escala-atual";
  valor.textContent = `1:${Math.round(1 / e.escala)}`;

  const leitura = document.createElement("div");
  leitura.className = "apoio";
  leitura.textContent = `1 pt de papel = ${e.escala} ${e.unidade} reais`;

  // Alternativa que a spec geral previa desde 2026-08-01 e que a tela da etapa
  // 3 nunca teve: quem já sabe a escala de plotagem não precisa calibrar.
  const porNumero = criarCampoComUnidade({
    valor: Math.round(1 / e.escala), unidade: "", rotulo: "Escala 1:",
    teste: "escala-1n", passo: "1",
    aoMudar: (v) => { if (v > 0) { e.escala = 1 / v; aoMudar(); } },
  });

  const unidade = document.createElement("select");
  unidade.className = "botao";
  unidade.dataset["teste"] = "unidade";
  unidade.setAttribute("aria-label", "Unidade do DXF");
  for (const u of UNIDADES) {
    const o = document.createElement("option");
    o.value = u;
    o.textContent = u;
    o.selected = u === e.unidade;
    unidade.append(o);
  }
  unidade.addEventListener("change", () => {
    e.unidade = unidade.value as Unidade;
    aoMudar();
  });

  const calibrar = criarBotao({
    rotulo: "Calibrar por 2 pontos", icone: "regua", teste: "calibrar",
    aoClicar: aoCalibrar,
  });
  calibrar.disabled = !temGeometria;
  calibrar.classList.add("campo-largo");

  caixa.append(valor, leitura, porNumero, unidade, calibrar);
  return caixa;
}

export function secaoCompactacao(e: EstadoDaTela, repetidos: number | null,
                                 aoMudar: () => void): HTMLElement {
  const caixa = document.createElement("div");
  caixa.className = "secao";

  for (const { chave, nome } of COMPACTACAO) {
    caixa.append(criarInterruptor({
      nome,
      explica: explicacao(chave, repetidos),
      ligado: Boolean(e.opcoes[chave]),
      teste: `opcao-${chave}`,
      aoMudar: () => {
        (e.opcoes[chave] as boolean) = !e.opcoes[chave];
        aoMudar();
      },
    }));
  }

  caixa.append(criarCampoComUnidade({
    valor: e.opcoes.min_len_mm, unidade: "mm",
    rotulo: "Descartar abaixo de", teste: "min-len",
    aoMudar: (v) => { e.opcoes.min_len_mm = v; aoMudar(); },
  }));

  return caixa;
}
```

- [ ] **Passo 3: ligar em `main.ts`**

Em `web/frontend/src/main.ts`:

1. Acrescente aos imports:

```ts
import {
  abrirEm, alternar, aoRedimensionar, estadoInicial, montarPainel,
  paraGuardar, type EstadoDoPainel, type Secao,
} from "./painel.js";
import { proporcaoRepetida } from "./camadas.js";
import { secaoCompactacao, secaoEscala } from "./secoes.js";
```

2. Declare o estado do painel junto das outras variáveis de topo:

```ts
const CHAVE_DO_PAINEL = "pdftodxf.painel";

function guardado(): string | null {
  try { return localStorage.getItem(CHAVE_DO_PAINEL); } catch { return null; }
}

let painel: EstadoDoPainel = estadoInicial(window.innerWidth, guardado());
```

O `try` não é zelo excessivo: em navegação privativa de alguns navegadores
`localStorage` estoura ao ser lido, e a tela inteira morreria por causa de uma
preferência de layout.

3. Acrescente a montagem do painel e troque `montarTopo` para refletir o modo:

```ts
function montarPainelLateral(): void {
  montarPainel(painelRaiz, painel, {
    escala: () => secaoEscala(estado, Boolean(geometria), iniciarCalibracao,
                              aoMudarOpcoes),
    compactacao: () => secaoCompactacao(
      estado, geometria ? proporcaoRepetida(geometria) : null, aoMudarOpcoes),
    camadas: () => document.createElement("div"),   // tarefa 7
  }, () => {
    painel = alternar(painel);
    const g = paraGuardar(painel);
    try { if (g) localStorage.setItem(CHAVE_DO_PAINEL, g); } catch { /* ignora */ }
    montarTudo();
  }, (s: Secao) => {
    painel = abrirEm(painel, s);
    montarTudo();
  });
}

function montarTudo(): void {
  montarTopo();
  montarPainelLateral();
}

function aoMudarOpcoes(): void {
  recalcular();          // recalcular já chama montarTudo pelo caminho abaixo
}
```

4. Em `montarTopo()`, troque as duas linhas provisórias da tarefa 5 por:

```ts
    mostrarMenu: painel.modo === "gaveta",
    aoAlternarPainel: () => {
      painel = alternar(painel);
      montarTudo();
    },
```

5. Em `recalcular()`, troque `montarFaixaPrincipal();` por `montarTudo();`.

6. Extraia o corpo do clique de calibrar (hoje dentro de
   `montarFaixaPrincipal`) para uma função de topo, já que agora quem o dispara
   é a seção:

```ts
function iniciarCalibracao(): void {
  calibragem = iniciarCalibragem();
  mostrarAviso({ titulo: "Calibração", podeTentarDeNovo: false,
                 detalhe: "Toque nas duas extremidades de uma medida " +
                          "conhecida da planta." });
  montarTudo();
}
```

7. No `resize`, reaja ao limiar da gaveta:

```ts
window.addEventListener("resize", () => {
  const novo = aoRedimensionar(painel, window.innerWidth, guardado());
  if (novo !== painel) { painel = novo; montarTudo(); }
  ajustarTamanho();
  aoMexer(vista);
});
```

8. Troque a última linha do arquivo, `montarFaixaPrincipal();`, por
   `montarTudo();`. E troque as demais chamadas remanescentes de `montarTopo()`
   por `montarTudo()`.

- [ ] **Passo 4: acrescentar os casos de ponta a ponta**

Acrescente ao fim de `web/frontend/e2e/conversao.spec.ts`:

```ts
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
```

- [ ] **Passo 5: rodar**

```bash
cd web/frontend && npm test && npm run build && npm run e2e
```

Esperado: tudo PASSA, inclusive o "converte uma planta de ponta a ponta" que a
tarefa 5 deixou vermelho.

- [ ] **Passo 6: conferir com planta real, na tela**

```bash
cd web/frontend && npm run dev
```

Abra `http://localhost:5173` (com `localhost`, **não** `127.0.0.1`), suba
`Input/LAY-1031.26.00_REV 00.pdf` e confira à mão: o painel abre e recolhe; os
interruptores mostram estado; a linha de apoio de cada opção aparece; o campo de
mm tem unidade; a escala mostra `1:N` e a leitura por extenso; o botão Exportar
funciona.

Isto não é opcional. Dos três defeitos que a etapa 3 só descobriu com planta
real, dois passaram por toda a suíte de testes.

- [ ] **Passo 7: commitar**

```bash
git add web/frontend/src/painel.ts web/frontend/src/secoes.ts web/frontend/src/main.ts web/frontend/e2e/conversao.spec.ts
git commit -m "Painel lateral com as secoes de escala e compactacao"
```

---

## Tarefa 7: a seção Camadas e a estimativa comparada

**Arquivos:**
- Modificar: `web/frontend/src/secoes.ts`
- Modificar: `web/frontend/src/main.ts`
- Teste: `web/frontend/e2e/conversao.spec.ts`

**Interfaces:**
- Consome: `resumoDasCamadas` da tarefa 1, `textoDaComparacao` da tarefa 2.
- Produz: `secaoCamadas(...)`, e o cálculo da linha de base em `main.ts`.
- Cada linha de camada ganha `data-teste="camada-<nome>"`.

- [ ] **Passo 1: escrever a seção**

Acrescente a `web/frontend/src/secoes.ts`:

```ts
import { precisaDeBusca, type ResumoDeCamada } from "./camadas.js";

function corEmHex(cor: number): string {
  return `#${cor.toString(16).padStart(6, "0")}`;
}

export function secaoCamadas(e: EstadoDaTela, resumo: ResumoDeCamada[],
                             parcial: boolean, aoMudar: () => void): HTMLElement {
  const caixa = document.createElement("div");
  caixa.className = "secao";

  const cabecalho = document.createElement("div");
  cabecalho.className = "apoio";
  cabecalho.dataset["teste"] = "camadas-total";
  cabecalho.textContent = parcial
    ? `${resumo.length} camadas (contagem parcial)`
    : `${resumo.length} camadas`;

  const todas = document.createElement("div");
  todas.append(
    criarBotao({
      rotulo: "Ligar todas", classe: "discreto apoio", teste: "ligar-todas",
      aoClicar: () => { e.layersDesligados.clear(); aoMudar(); },
    }),
    criarBotao({
      rotulo: "Desligar todas", classe: "discreto apoio", teste: "desligar-todas",
      aoClicar: () => {
        for (const c of resumo) e.layersDesligados.add(c.nome);
        aoMudar();
      },
    }),
  );

  caixa.append(cabecalho, todas);

  const lista = document.createElement("div");
  lista.className = "lista-de-camadas";

  const desenhar = (filtro: string) => {
    lista.replaceChildren();
    const alvo = filtro.trim().toLowerCase();
    for (const c of resumo) {
      if (alvo && !c.nome.toLowerCase().includes(alvo)) continue;
      const ligada = !e.layersDesligados.has(c.nome);

      const linha = document.createElement("button");
      linha.type = "button";
      linha.className = "camada";
      linha.dataset["teste"] = `camada-${c.nome}`;
      linha.setAttribute("aria-pressed", String(ligada));

      const olho = criarIcone(ligada ? "olho" : "olho-cortado");
      const cor = document.createElement("span");
      cor.className = "cor";
      cor.style.background = corEmHex(c.cor);
      const nome = document.createElement("span");
      nome.className = "nome";
      nome.textContent = c.nome;
      nome.title = c.nome;      // nome longo é cortado por ellipsis
      const quantas = document.createElement("span");
      quantas.className = "quantas";
      quantas.textContent = c.n.toLocaleString("pt-BR");

      linha.append(olho, cor, nome, quantas);
      linha.addEventListener("click", () => {
        if (e.layersDesligados.has(c.nome)) e.layersDesligados.delete(c.nome);
        else e.layersDesligados.add(c.nome);
        aoMudar();
      });
      lista.append(linha);
    }
  };

  if (precisaDeBusca(resumo.length)) {
    const busca = document.createElement("input");
    busca.type = "search";
    busca.className = "campo campo-largo";
    busca.placeholder = "Filtrar camadas";
    busca.dataset["teste"] = "busca-camadas";
    // Filtra sem remontar o painel: remontar perderia o foco a cada tecla.
    busca.addEventListener("input", () => desenhar(busca.value));
    caixa.append(busca);
  }

  desenhar("");
  caixa.append(lista);
  return caixa;
}
```

Acrescente `criarIcone` à importação de `./ui/controles.js` no topo do arquivo.

- [ ] **Passo 2: calcular a linha de base e ligar a seção**

Em `web/frontend/src/main.ts`:

1. Acrescente aos imports:

```ts
import { resumoDasCamadas, type ResumoDeCamada } from "./camadas.js";
import { secaoCamadas } from "./secoes.js";
```

2. Declare, junto das outras variáveis de topo:

```ts
let camadas: ResumoDeCamada[] = [];

/**
 * A página inteira: todas as camadas, nenhuma compactação.
 *
 * É o "antes" que a barra mostra ao lado do "depois". Calculado só quando a
 * geometria troca — duas vezes por página, no esqueleto e no detalhe — e nunca
 * a cada clique: seriam ~12 ms jogados fora por opção marcada.
 */
const SEM_COMPACTACAO: Opcoes = {
  excluded_layers: [], drop_fills: false, min_len_mm: 0,
  dedup: false, join_polylines: false, round_coords: false,
};
```

E acrescente `import type { Opcoes } from "./select.js";` — o arquivo já importa
`selecionar` desse módulo; junte o tipo na mesma linha.

3. Em `trocarGeometria(nova)`, antes de `recalcular()`:

```ts
  camadas = resumoDasCamadas(nova);
  estado.bytesBase = estimarBytes(nova, selecionar(nova, SEM_COMPACTACAO),
                                  SEM_COMPACTACAO);
```

4. Em `montarPainelLateral()`, troque a linha provisória da seção camadas por:

```ts
    camadas: () => secaoCamadas(estado, camadas, estado.parcial, aoMudarOpcoes),
```

5. Em `carregarPagina()`, onde hoje há `estado.layersDesligados.clear();`,
   acrescente logo abaixo `camadas = [];` — trocar de página não pode carregar a
   lista da página anterior.

- [ ] **Passo 3: acrescentar os casos de ponta a ponta**

Acrescente ao fim de `web/frontend/e2e/conversao.spec.ts`:

```ts
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

  // Sem nada marcado, base e atual coincidem: um número só.
  await expect(estimativa).not.toContainText("→");

  // Com "remover duplicados" ligado, aparecem os dois e a redução.
  await t(page, "opcao-dedup").click();
  await expect(estimativa).toContainText("→");
  await expect(estimativa).toContainText("−");
});
```

- [ ] **Passo 4: rodar**

```bash
cd web/frontend && npm test && npm run build && npm run e2e
```

Esperado: tudo PASSA. Se "camada-TEXTO" não existir, confira o nome dos layers
da planta de teste com:

```bash
./.venv/Scripts/python.exe -m pdftodxf inspecionar "Input/LAY-1031.26.00_REV 00.pdf"
```

e use um nome que exista, ajustando o teste.

- [ ] **Passo 5: rodar a bateria três vezes**

```bash
cd web/frontend && npm run e2e && npm run e2e && npm run e2e
```

Esperado: PASSA nas três. É o mesmo rito da etapa 3, e ele existe porque a
bateria já foi intermitente uma vez: uma página ficava presa em `na_fila` e a
espera estourava. Se falhar em alguma, o suspeito é a troca atômica da ficha, e
não lentidão — a extração leva 0,5 s.

- [ ] **Passo 6: conferir com planta real**

```bash
cd web/frontend && npm run dev
```

Em `http://localhost:5173`, com `Input/LAY-1031.26.00_REV 00.pdf`, confira: a
bolinha de cor de cada camada bate com o que se vê no desenho; a contagem soma
o total da planta; desligar uma camada some com ela na tela; a estimativa mostra
os dois números e a porcentagem; recolher e reabrir preserva tudo.

- [ ] **Passo 7: commitar**

```bash
git add web/frontend/src/secoes.ts web/frontend/src/main.ts web/frontend/e2e/conversao.spec.ts
git commit -m "Secao de camadas com cor e contagem, e a estimativa comparada"
```

---

## Definição de pronto da etapa

- [ ] `npm test` verde, com os arquivos novos: `camadas.test.ts`,
      `painel.test.ts`, `icones.test.ts`, e `toolbar.test.ts` ampliado
- [ ] `npm run build` limpo (o `tsc --noEmit` faz parte dele)
- [ ] `npm run e2e` verde **três vezes seguidas**, com os seis testes
- [ ] Os quinze arquivos de teste Python continuam passando — nada de Python
      mudou, mas conferir custa um comando e prova que não mudou mesmo
- [ ] `web/frontend/package.json` sem dependência nova; `git diff` das
      dependências vazio
- [ ] Conferência à mão com a planta real, na tela, feita e relatada
- [ ] Nenhum arquivo do motor de desenho no `git diff` da etapa:
      `canvas.ts`, `pintor.ts`, `lista.ts`, `ordem.ts`, `formato.ts`,
      `select.ts`, `estimativa.ts`, `api.ts`, `gestos.ts`, `calibrate.ts`
- [ ] `HANDOFF.md` atualizado com o estado e com o que "continuar" passa a
      significar

## O que fica para a etapa 4

Reservado e não construído aqui: o canto direito da barra (`<div class="direita">`)
recebe o indicador de cota e o botão de entrar; as cinco linhas de erro novas
entram em `estados.ts`; a `privacidade.html` que o rodapé já referencia
continua não existindo.
