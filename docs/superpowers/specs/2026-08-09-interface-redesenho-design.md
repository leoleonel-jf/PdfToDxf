# Etapa 3.5 — redesenho da interface

Data: 2026-08-09

Esta etapa não estava no plano de cinco etapas. Ela entrou depois de a interface
da etapa 3 ser vista com uma planta real na tela, e é **anterior à etapa 4**: as
tarefas de tela da etapa 4 (o canto da conta, o indicador de cota, as cinco
linhas de erro) serão construídas sobre o layout definido aqui, e não sobre o
cabeçalho antigo.

Escrito para bastar por si.

## O problema

O cabeçalho de duas faixas entregue na etapa 3 funciona e é ininteligível. Seis
defeitos, todos observados na tela:

1. **Opções de compactação e camadas são o mesmo botão azul.** "Remover
   duplicados" e "PISO CMC" têm forma, cor e peso idênticos. Nada distingue uma
   opção de exportação de um layer do desenho.
2. **Nada indica ligado ou desligado.** Todos os botões são azuis preenchidos, o
   que lê como "tudo ligado".
3. **O campo numérico solto** — um `0` sem rótulo e sem unidade — é "descartar
   segmentos abaixo de N mm".
4. **Camadas chamadas `0`, `8` e `COR_000000`** não significam nada sem uma
   amostra da cor e a contagem de entidades ao lado.
5. **`1 pt = 0.01 m` e `≈ 4,1 MB`** são números sem legenda, e o segundo não diz
   comparado a quê.
6. **O seletor de arquivo é o nativo do navegador**, e por isso aparece escrito
   "Escolher ficheiro / Nenhum ficheiro selecionado" — português de Portugal,
   que nem é a localização do usuário.

Somado a isso, a queixa de aparência: sem hierarquia, azul chapado, nenhum
ícone, espaçamento irregular.

Nenhum desses defeitos é de renderização. O desenho está certo desde que o eixo
Y e os arcos foram corrigidos; o que está errado é a moldura em volta dele.

## A decisão

**Painel lateral recolhível**, escolhido entre três direções desenhadas e
comparadas em 2026-08-09:

| Direção | Por que não foi escolhida |
|---|---|
| Duas faixas organizadas (evolução do atual) | Menor mudança, mas não tem onde escrever a linha que explica cada opção, e com 30 camadas a faixa horizontal volta a estourar no menu "+N" |
| Barra enxuta com painéis flutuantes | Mais planta na tela, porém esconde as opções atrás de um clique — o oposto do "todas as opções à vista" da spec geral, e o valor do app é ver o desenho mudar enquanto se mexe nelas |
| **Painel lateral recolhível** | **Escolhida.** É a única com espaço para explicar cada opção em uma linha, e a única que aguenta lista longa de camadas rolando |

E **paleta e tipografia refeitas**, mantendo a moldura escura estilo CAD que a
spec geral fixou. Não é identidade visual nova: não entra marca, logo nem tela
de boas-vindas.

## Layout

### Barra superior

Uma faixa fina, com o essencial e nada mais:

`[Abrir PDF]` · nome do arquivo · seletor de página · … · estimativa ·
`[Exportar DXF]`

O botão de abrir é próprio, com o `<input type="file">` escondido atrás dele —
é o que elimina o "Escolher ficheiro" do navegador.

O canto direito desta barra é onde a **etapa 4** encaixa o indicador de cota e o
botão de entrar. O espaço fica reservado desde já.

### Painel lateral

260 px à esquerda, com três seções: **Escala**, **Compactação**, **Camadas**.

- **Recolhe para uma faixa de 48 px** só com os ícones das três seções. Clicar
  num ícone reabre o painel já naquela seção. Sumir por completo economizaria
  mais 48 px e faria o usuário perder a orientação de onde as coisas estão.
- O estado (aberto ou recolhido) é guardado no `localStorage` e vale para a
  visita seguinte.
- **Abaixo de 900 px de largura o painel vira gaveta** sobre o desenho, aberta
  por um botão na barra superior. Isso resolve, de brinde, o cabeçalho espremido
  em tela estreita que a spec geral tentava resolver com rolagem horizontal.

### Seção Escala

- A escala em destaque (`1:100`) e, abaixo, a leitura por extenso: "1 pt de
  papel = 1 cm real". O número de hoje aparece sem legenda; aqui ele ganha uma.
- **`[Calibrar por 2 pontos]`**, que aciona o `calibrate.ts` existente, com a
  lupa do toque intocada.
- **Campo "Escala 1:N"** para digitar direto. A spec geral previa esta
  alternativa desde 2026-08-01 e a tela da etapa 3 nunca a teve.
- Seletor de unidade (mm, cm, m), hoje escondido no fluxo de exportação.

### Seção Compactação

Os cinco controles, cada um com o nome e **uma linha explicando o efeito**:

| Controle | Linha de apoio |
|---|---|
| Unir em polilinhas | junta traços encadeados num só |
| Arredondar coordenadas | menos casas decimais por ponto |
| Remover duplicados | mostra o quanto do desenho é repetido, do dado real |
| Remover preenchimentos | descarta hachuras e áreas pintadas |
| Descartar abaixo de `N` mm | campo numérico com a unidade dentro |

Os quatro booleanos são **interruptores**, não botões — a forma já diz que têm
dois estados. O campo de mm é campo, com rótulo à esquerda e `mm` à direita.

**Três vêm ligadas por padrão:** unir em polilinhas, arredondar coordenadas e
remover duplicados. Remover preenchimentos vem desligada, e o corte por
comprimento fica em 0.

O motivo é que os três só tiram redundância: duplicados são traços exatamente
sobrepostos, unir troca N segmentos encadeados por uma polilinha com os mesmos
vértices, e o arredondamento vai a 4 casas decimais (`dxf_writer.py:135`), o que
com a unidade padrão em metros dá resolução de 0,1 mm — muito abaixo de qualquer
tolerância de projeto. Numa planta do acervo os três juntos derrubam o DXF de
496 MB para algo em torno de 80 MB, sem o usuário precisar descobrir nada.
"Remover preenchimentos" fica desligada porque **apaga desenho de verdade** —
hachuras e áreas pintadas somem da prancha.

Como a linha de base da estimativa é a página sem nenhuma compactação, a barra
já abre mostrando a comparação e a porcentagem, em vez de um número solto. É o
que faz o usuário ver, de entrada, o que o app está fazendo por ele.

"Remover duplicados" mostra a proporção real da planta aberta, calculada dos
`dup_group` que o binário já traz. Numa planta do acervo isso é 60%, e ver o
número é o que faz a opção deixar de ser um palpite.

### Seção Camadas

Lista rolável, uma linha por camada: **olho de ligar/desligar · bolinha da cor
dominante · nome · contagem de entidades**.

- Cor e contagem são calculadas **no navegador**, a partir dos vetores
  `layer_id` e `cor` que o formato binário já carrega. Nada muda no Python, no
  `classify()` nem no `meta.json`.
- Enquanto só o esqueleto chegou, a contagem aparece **marcada como parcial**,
  do mesmo jeito que a estimativa já faz hoje.
- Cabeçalho da seção com "ligar todas" e "desligar todas".
- **Campo de busca aparece acima de 15 camadas**, e não antes: numa planta de
  seis camadas ele seria ruído.

## Estimativa: com e sem compactação

Hoje a barra mostra `≈ 4,1 MB` e não diz comparado a quê. Passa a mostrar os
dois números e a diferença:

```
DXF estimado    12,3 MB → 4,1 MB   −67%
```

- **A linha de base é a página inteira**: todas as camadas ligadas, nenhuma
  opção de compactação marcada.
- A diferença inclui, portanto, **as camadas que o usuário desligou**, e não só
  as opções — que é exatamente "o que está acontecendo" com o arquivo dele.
- **A base não depende de nenhuma escolha do usuário**, então é calculada e
  guardada em cache, e **recalculada exatamente duas vezes**: quando o esqueleto
  chega e quando o detalhe chega. Nenhum clique em opção ou camada a recalcula.
  Custo recorrente zero; sem o cache seriam ~12 ms extras por clique, medidos na
  etapa 3 sobre 3 milhões de entidades.
- Quando só o esqueleto chegou, os dois números são provisórios e aparecem com
  a mesma marca de parcial que a estimativa já usa.

## Paleta e tipografia

Tudo em variáveis CSS, num bloco só no topo do `estilo.css`.

- **Escala de cinza de 8 passos** para as superfícies e as bordas, no lugar do
  azul chapado atual.
- **Um azul de destaque**, usado em exatamente três lugares: controle ligado,
  botão Exportar, anel de foco. Não em botão comum, não em camada, não em
  borda.
- **Três tamanhos de texto e dois pesos.** Rótulo de seção é o menor, em cinza
  claro; nome de controle é o corpo; a escala e o total são o maior.
- **Espaçamento e cantos de uma escala só**, em vez de valores avulsos.
- **Ícones Tabler colados inline como SVG**, só os usados — cerca de doze.
  Nenhuma dependência em runtime, nenhuma fonte baixada; é o que a spec geral
  pede ("ícones desenhados em SVG inline, só os poucos necessários").
- O fundo do desenho continua claro, controlado pela variável única que já
  existe — inverter segue sendo uma linha.

## O que não muda

O motor de desenho fica intocado. Isso é deliberado: ele foi refeito em
2026-08-09 depois de três medições derrubarem três arquiteturas, e mexer nele
junto com CSS misturaria dois riscos que não têm relação.

| Intocado | Redesenhado |
|---|---|
| `canvas.ts`, `pintor.ts`, `lista.ts`, `ordem.ts` | `toolbar.ts` |
| `formato.ts`, `select.ts`, `estimativa.ts` | `estilo.css` |
| `api.ts`, `gestos.ts`, `calibrate.ts` | `main.ts` |
| todo o Python | `estados.ts` |

`estimativa.ts` ganha só a chamada da linha de base; a fórmula não muda, e o
contrato com o Python continua o mesmo.

## Testes

**Os dois testes de ponta a ponta existentes passam a mirar por
`data-teste`**, e não por texto visível. Hoje eles procuram rótulos; qualquer
mudança de palavra os quebra, e esta etapa muda quase todas. É uma correção de
método, não acomodação: teste que quebra com troca de rótulo não está testando o
comportamento.

Casos novos, no padrão do projeto (`vitest` do lado TypeScript):

- Recolher e reabrir preserva o estado entre recarregamentos.
- Clicar no ícone de uma seção com o painel recolhido reabre naquela seção.
- Abaixo de 900 px o painel vira gaveta e o botão que a abre existe.
- A contagem por camada soma exatamente o número de entidades do binário.
- A cor dominante de uma camada é a cor mais frequente entre as entidades dela.
- Desligar uma camada muda a contagem de sobreviventes e a estimativa.
- A linha de base da estimativa é a página inteira, e não a seleção corrente.
- A busca de camadas aparece com 16 e não aparece com 15.
- Enquanto só o esqueleto chegou, contagem e estimativa saem marcadas como
  parciais.

## Ordem de implementação

| # | Tarefa |
|---|---|
| 1 | Variáveis de CSS: paleta, tipografia, espaçamento, cantos |
| 2 | Ícones inline e os componentes de interruptor, chip e campo com unidade |
| 3 | Barra superior fina, com o botão de abrir próprio |
| 4 | Painel lateral: esqueleto, recolher e expandir, gaveta em tela estreita |
| 5 | Seções Escala e Compactação, com as linhas de apoio |
| 6 | Seção Camadas, com cor e contagem calculadas no cliente |
| 7 | Estimativa com linha de base em cache, e os testes de ponta a ponta por `data-teste` |

## Fora de escopo

- Marca, logo, cor própria e tela de boas-vindas
- Tema claro para a moldura (o fundo do desenho já é claro)
- Qualquer mudança no motor de desenho ou no Python
- O canto da conta, o indicador de cota e a `privacidade.html` — são da etapa 4,
  e encaixam no espaço reservado da barra superior
- Trocar o `window.prompt` da calibração por caixa própria; continua na dívida
  registrada no handoff

## Riscos

- **A lateral custa 260 px de largura**, e plantas A3 são deitadas. O recolher
  para 48 px é a resposta, e é por isso que ele não some por completo: quem
  trabalha recolhido precisa saber onde reabrir.
- **A cor dominante por camada é uma aproximação.** Uma camada com entidades de
  várias cores mostra a mais frequente. É rótulo de orientação, não informação
  exata — e o desenho na tela continua sendo a fonte da verdade.
- **Contagem parcial enquanto o detalhe carrega** pode confundir quem não vê a
  marca de parcial. A marca é a mesma que a estimativa já usa, então é um
  vocabulário só, e não dois.
