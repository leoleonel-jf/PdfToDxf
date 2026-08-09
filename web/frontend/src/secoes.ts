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
  criarBotao, criarCampoComUnidade, criarIcone, criarInterruptor,
} from "./ui/controles.js";
import { precisaDeBusca, type ResumoDeCamada } from "./camadas.js";

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
