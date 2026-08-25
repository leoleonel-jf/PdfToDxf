/**
 * A barra superior: abrir, página, escala, estimativa, exportar e a conta.
 *
 * Fina de propósito. O que exige explicação mora no painel lateral; aqui fica
 * só o que precisa estar sempre à vista.
 *
 * O `<div class="direita">` nasceu na etapa 3.5 esperando o canto da conta; a
 * etapa 4 o encaixou ali, depois do "Exportar DXF".
 */
import { criarBotao } from "./ui/controles.js";
import { textoDaComparacao, type EstadoDaTela } from "./toolbar.js";
import { cantoDaConta, type AcoesDaConta } from "./conta.js";
import type { Cota } from "./api.js";

export type ContextoDaBarra = {
  estado: EstadoDaTela;
  nomeDoArquivo: string;
  pagina: number;
  nPaginas: number;
  temGeometria: boolean;
  /** Só em tela estreita: o botão que abre a gaveta. */
  mostrarMenu: boolean;
  /** `null` enquanto a leitura da cota não voltou — ou quando ela falhou. */
  cota: Cota | null;
  acoesDaConta: AcoesDaConta;
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

  direita.append(cantoDaConta(c.cota, c.acoesDaConta));

  raiz.append(direita);
}
