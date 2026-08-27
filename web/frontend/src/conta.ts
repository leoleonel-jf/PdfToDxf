/**
 * O canto da conta e as caixas de entrar e cadastrar.
 *
 * Nada de biblioteca: são dois formulários e um menu. O CSS é o mesmo do resto
 * da tela.
 *
 * A regra que governa o texto da cota é a mesma do progresso: **não inventar
 * número**. Sem limite não vira "∞ arquivos", vira texto nenhum.
 *
 * `document.createElement` e nunca `innerHTML`: o e-mail sai do que o usuário
 * digitou e volta do servidor, e montar HTML com string faria dele um vetor de
 * injeção. Mesma razão de `ui/controles.ts`.
 */
import { criarBotao } from "./ui/controles.js";
import type { Cota } from "./api.js";

export type AcoesDaConta = {
  aoEntrar: () => void;
  aoSair: () => void;
  aoCadastrar: () => void;
};

/**
 * `14h05` — hora local, que é a que o usuário lê no relógio dele.
 *
 * `""` quando `epoch` já passou de `agora`: a tela não pode prometer uma hora
 * que já ficou para trás. É `textoDaCota` que decide o texto de reserva —
 * aqui só se decide se há hora para mostrar.
 */
export function horaDeLiberar(epoch: number, agora: number): string {
  if (epoch * 1000 <= agora) return "";
  const d = new Date(epoch * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}h${mm}`;
}

export function textoDaCota(c: Cota, agora: number): string {
  const a = c.arquivos;
  if (a.restam === null || a.de === null) return "";
  if (a.restam === 0 && a.libera_em) {
    const hora = horaDeLiberar(a.libera_em, agora);
    return hora ? `sem arquivos — libera às ${hora}` : "sem arquivos por enquanto";
  }
  return `${a.restam} de ${a.de} arquivos`;
}

/**
 * A guarda de "em voo" das releituras de cota (I4).
 *
 * `main.ts` pega um número de sequência antes de cada `await lerCota()`; ao
 * voltar, a resposta só vale se `sequencia` ainda for o último número emitido
 * — senão uma leitura mais nova já saiu e chegou primeiro, e escrever por
 * cima dela deixaria o canto mostrando um estado velho. Extraída como função
 * pura porque `atualizarCota` mora em `main.ts`, que não é importável sem DOM
 * — o topo do arquivo lê `document.querySelector("#desenho")!` de verdade.
 */
export function respostaAindaVale(sequencia: number, ultimoEmitido: number): boolean {
  return sequencia === ultimoEmitido;
}

export function cantoDaConta(c: Cota | null, acoes: AcoesDaConta): HTMLElement {
  const caixa = document.createElement("div");
  caixa.className = "canto-da-conta";
  caixa.dataset["teste"] = "canto-da-conta";

  if (c) {
    const texto = textoDaCota(c, Date.now());
    if (texto) {
      const saldo = document.createElement("span");
      saldo.className = "apoio secundario";
      saldo.dataset["teste"] = "cota";
      saldo.textContent = texto;
      caixa.append(saldo);
    }
  }

  if (c && c.tipo === "logado") {
    const email = document.createElement("span");
    email.className = "apoio";
    email.dataset["teste"] = "email-da-conta";
    email.textContent = c.email;
    caixa.append(email, criarBotao({
      rotulo: "Sair", classe: "discreto", teste: "sair", aoClicar: acoes.aoSair,
    }));
    return caixa;
  }

  caixa.append(criarBotao({
    rotulo: "Entrar", icone: "usuario", classe: "discreto", teste: "entrar",
    aoClicar: acoes.aoEntrar,
  }));
  return caixa;
}

export type ModoDaCaixa = "entrar" | "cadastrar" | "senha" | "nova-senha" | null;

/**
 * Os dois parâmetros de URL que os e-mails produzem.
 *
 * `?senha=<token>` vem do link de "esqueci a senha" (`/?senha=<token>`);
 * `?confirmado=1` é para onde `GET /api/auth/confirmar/{token}` redireciona.
 * Pura, e não lida de `window.location` diretamente: o ambiente de teste roda
 * sem DOM (`vite.config.ts`), e é assim que ela fica testável em Node.
 */
export type AcaoDaUrl =
  | { tipo: "nova-senha"; token: string }
  | { tipo: "confirmado" }
  | null;

export function acaoDaUrl(busca: string): AcaoDaUrl {
  const params = new URLSearchParams(busca);
  const token = params.get("senha");
  // Se os dois parâmetros vierem juntos, `senha` ganha. É o token sensível: já
  // saiu do e-mail, e uma vez lido precisa sumir da barra de endereço agora —
  // se `confirmado` ganhasse, o link de redefinição ficaria ali, utilizável,
  // até vencer. Perder o aviso de "confirmado" custa uma frase; perder a
  // janela de trocar a senha é o usuário ter de pedir outro link.
  if (token) return { tipo: "nova-senha", token };
  if (params.get("confirmado") === "1") return { tipo: "confirmado" };
  return null;
}

export type AcoesDaCaixa = {
  aoConfirmar: (modo: Exclude<ModoDaCaixa, null>,
                email: string, senha: string) => void;
  aoTrocarModo: (modo: Exclude<ModoDaCaixa, null>) => void;
  aoFechar: () => void;
  recado: string;
  erro: string;
  /**
   * O e-mail com que a caixa nasce preenchida (I2).
   *
   * A caixa não guarda estado próprio: `main.ts` remonta ela inteira a cada
   * erro de submit, e sem isto o `replaceChildren` levava junto o e-mail que
   * o usuário tinha acabado de digitar — não só a senha errada, que é o único
   * campo que **deve** ser apagado depois de uma tentativa que falhou.
   */
  email?: string;
};

const TITULOS: Record<Exclude<ModoDaCaixa, null>, string> = {
  entrar: "Entrar",
  cadastrar: "Criar conta",
  senha: "Recuperar a senha",
  "nova-senha": "Nova senha",
};

/**
 * Monta a caixa dentro da sobreposição, ou a esconde com `modo === null`.
 *
 * O `hidden` não é enfeite: a sobreposição é `position: fixed; inset: 0` e
 * cobre a tela inteira, inclusive o canvas. Fechada, ela **precisa** sair do
 * fluxo — é o `[hidden] { display: none !important }` do topo do `estilo.css`
 * que garante isso contra o `display: flex` da própria regra da sobreposição.
 * Foi assim que o painel de aviso da etapa 3 engolia a planta.
 */
export function montarCaixaDeConta(raiz: HTMLElement, modo: ModoDaCaixa,
                                   acoes: AcoesDaCaixa): void {
  raiz.replaceChildren();
  raiz.hidden = modo === null;
  if (modo === null) return;

  const painel = document.createElement("form");
  painel.className = "caixa-de-conta";
  painel.dataset["teste"] = `caixa-${modo}`;
  // I3: a caixa é um diálogo modal, não um painel qualquer sobre a planta —
  // quem navega por teclado ou leitor de tela precisa saber que entrou nela.
  painel.setAttribute("role", "dialog");
  painel.setAttribute("aria-modal", "true");

  const titulo = document.createElement("h2");
  titulo.id = "titulo-caixa-de-conta";
  titulo.textContent = TITULOS[modo];
  painel.setAttribute("aria-labelledby", titulo.id);

  const email = document.createElement("input");
  email.type = "email";
  email.className = "campo campo-largo";
  email.required = true;
  email.autocomplete = "email";
  email.placeholder = "seu@email.com";
  email.dataset["teste"] = "campo-email";
  // I2: o valor inicial que `main.ts` guarda entre montagens — nunca a senha,
  // que é apagada de propósito a cada remontagem.
  email.value = acoes.email ?? "";

  const senha = document.createElement("input");
  senha.type = "password";
  senha.className = "campo campo-largo";
  senha.required = true;
  senha.minLength = 8;
  senha.autocomplete = modo === "entrar" ? "current-password" : "new-password";
  senha.placeholder = "sua senha";
  senha.dataset["teste"] = "campo-senha";

  painel.append(titulo);
  // Os dois campos são **omitidos**, não escondidos, quando não fazem sentido
  // no modo: um `required` invisível travaria o `submit` sem dizer por quê.
  // "Recuperar a senha" manda só o e-mail; "nova-senha" — a caixa que abre a
  // partir de `?senha=<token>` — não pede e-mail nenhum, porque o token já
  // identifica a conta.
  if (modo !== "nova-senha") painel.append(email);
  if (modo !== "senha") painel.append(senha);

  if (modo === "cadastrar") {
    const explica = document.createElement("p");
    explica.className = "explica";
    explica.textContent = "Com conta você envia 15 arquivos por vez em vez de " +
      "5, gera 45 DXF em vez de 15, e o limite de tamanho sobe de 10 MB para " +
      "100 MB.";
    painel.append(explica);
  }

  if (acoes.erro) {
    const erro = document.createElement("p");
    erro.className = "explica erro";
    erro.dataset["teste"] = "erro-da-conta";
    erro.textContent = acoes.erro;
    painel.append(erro);
  }
  if (acoes.recado) {
    const recado = document.createElement("p");
    recado.className = "explica";
    recado.dataset["teste"] = "recado-da-conta";
    recado.textContent = acoes.recado;
    painel.append(recado);
  }

  const confirmar = document.createElement("button");
  confirmar.type = "submit";
  confirmar.className = "botao principal";
  confirmar.dataset["teste"] = "confirmar-conta";
  confirmar.textContent = TITULOS[modo];
  painel.append(confirmar);

  const outros = document.createElement("div");
  outros.className = "apoio";
  const alternativas: Array<[Exclude<ModoDaCaixa, null>, string]> = [
    ["entrar", "Já tenho conta"],
    ["cadastrar", "Criar uma conta"],
    ["senha", "Esqueci a senha"],
  ];
  for (const [alvo, rotulo] of alternativas) {
    if (alvo === modo) continue;
    outros.append(criarBotao({
      rotulo, classe: "discreto", teste: `ir-para-${alvo}`,
      aoClicar: () => acoes.aoTrocarModo(alvo),
    }));
  }
  painel.append(outros, criarBotao({
    rotulo: "Fechar", classe: "discreto", teste: "fechar-conta",
    aoClicar: acoes.aoFechar,
  }));

  painel.addEventListener("submit", (e) => {
    e.preventDefault();
    acoes.aoConfirmar(modo, email.value.trim(), senha.value);
  });
  // I3: Escape fecha a caixa, como o botão "Fechar". Registrado no próprio
  // painel — o `keydown` de qualquer campo focado sobe até aqui —, e não em
  // `document`: a caixa é remontada a cada mudança de estado, e um ouvinte em
  // `document` teria de ser removido a mão para não vazar. Este morre sozinho
  // com o `replaceChildren` que troca o painel antigo pelo novo.
  painel.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Escape") acoes.aoFechar();
  });

  raiz.append(painel);
  (modo === "nova-senha" ? senha : email).focus();
}
