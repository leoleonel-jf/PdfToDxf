/**
 * Ordem das entidades por comprimento decrescente.
 *
 * Existe por um motivo só: quando a lista de desenho preenche as vagas de cada
 * região, quem entra primeiro é o traço mais longo — o que mais se vê. Sem essa
 * ordem, o teto por região escolheria por acaso qual traço sobrevive.
 *
 * Radix de 16 bits em duas passadas, e não `sort` com comparador: o comparador
 * é uma chamada de função por comparação, e são dezenas de milhões delas em 3
 * milhões de entidades. Medido em ~250 ms.
 */

const BALDES = 65536;

export function ordenarPorComprimento(lengthUm: Uint32Array): Uint32Array {
  const n = lengthUm.length;
  let atual = new Uint32Array(n);
  for (let i = 0; i < n; i++) atual[i] = i;
  if (n === 0) return atual;

  // Ordenar pelo complemento e não inverter no fim: inverter destruiria a
  // estabilidade, e os empates sairiam em ordem inversa da original. Como a
  // lista de desenho é comparada em teste, isso viraria intermitência.
  const chave = new Uint32Array(n);
  for (let i = 0; i < n; i++) chave[i] = (0xffffffff - lengthUm[i]!) >>> 0;

  let outro = new Uint32Array(n);
  const contagem = new Uint32Array(BALDES);
  for (let passada = 0; passada < 2; passada++) {
    const deslocamento = passada * 16;
    contagem.fill(0);
    for (let i = 0; i < n; i++) {
      contagem[(chave[atual[i]!]! >>> deslocamento) & 0xffff]!++;
    }
    let soma = 0;
    for (let b = 0; b < BALDES; b++) {
      const c = contagem[b]!;
      contagem[b] = soma;
      soma += c;
    }
    for (let i = 0; i < n; i++) {
      const v = atual[i]!;
      outro[contagem[(chave[v]! >>> deslocamento) & 0xffff]!++] = v;
    }
    const troca = atual; atual = outro; outro = troca;
  }
  return atual;
}
