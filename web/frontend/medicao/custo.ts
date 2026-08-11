// Marca o arquivo como módulo. Sem isto o TypeScript o trata como script
// global, e as declarações de topo colidem com as do `desenho.ts` — que o
// navegador nunca veria, porque os dois são carregados como `type="module"`.
export {};

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
function mostrar() {
  document.querySelector("#saida")!.textContent = linhas.join("\n");
}

/**
 * Cronometra a mesma fase três vezes e registra as três.
 *
 * Recarregar a página não aquece o JIT — cada carga é um contexto novo, e as
 * duas primeiras passagens deste arquivo variaram por um fator de dois. Repetir
 * dentro da mesma carga é o que dá um número em que se pode confiar; a decisão
 * de arquitetura se apoia nele.
 */
function cronometrar<T>(nome: string, f: () => T): T {
  const gastos: number[] = [];
  let r: T = undefined as T;
  for (let k = 0; k < 3; k++) {
    const inicio = performance.now();
    r = f();
    gastos.push(performance.now() - inicio);
  }
  linhas.push(`${nome}: ${gastos.map((g) => g.toFixed(0)).join(" / ")} ms`);
  mostrar();
  return r;
}

const dados = cronometrar("gerar 3M", gerar);

// Cenário do plano: min_len corta e o dedup colapsa — sobram 500 mil.
const mascara = cronometrar("select() cru", () => selecionar(dados, 500));
cronometrar("construir Path2D (500 mil sobreviventes)",
            () => construirCaminhos(dados, mascara));

// O cenário que o plano não mede, e que é o pior caso do desenho: sem dedup e
// sem filtro de comprimento, as 3 milhões de entidades sobrevivem e viram
// caminho. É essa a conta que decide se o gargalo é a decisão ou o desenho.
const tudo = new Uint8Array(N).fill(1);
const caminhos = cronometrar("construir Path2D (3 milhoes sobreviventes)",
                             () => construirCaminhos(dados, tudo));

let vivos = 0;
for (const v of mascara) vivos += v;
linhas.push(`sobreviventes com dedup: ${vivos}`);
linhas.push(`grupos de caminho: ${caminhos.size}`);
linhas.push(`navegador: ${navigator.userAgent}`);
linhas.push(`nucleos logicos: ${navigator.hardwareConcurrency}`);
mostrar();
