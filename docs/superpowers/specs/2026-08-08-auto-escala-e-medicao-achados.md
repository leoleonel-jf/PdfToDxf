# Auto-escala e ferramentas de medição — achados e decisões

Conversa de 2026-08-08. **Não é uma spec**: é o registro do que se descobriu
sondando uma planta real e das decisões que o usuário tomou. O desenho completo
fica para depois da etapa 3, por decisão dele — a maior parte da medição é
interface, e desenhá-la antes de o canvas web existir seria escrever duas vezes.

Leia isto antes de começar qualquer uma das duas features. Os achados abaixo
custaram sondagem e derrubam premissas que parecem óbvias.

## As duas ideias

1. **Auto-escala na abertura.** O app deduz a escala do desenho e propõe
   aplicá-la, com uma janela de confirmação que mostra de onde tirou o número.
2. **Ferramentas de medição.** "Medir comprimento" (linha, diâmetro, raio) e
   "medir distância" (entre dois contornos, nos eixos X, Y e perpendicular),
   com *snap* a extremidades, vértices, interseções, centro e quadrante, e cota
   desenhada na tela que **não** sai na exportação.

## O que foi decidido

| Decisão | Escolha |
|---|---|
| Fonte da escala | Carimbo **e** cota, comparando os dois — com a cota como estratégia principal, porque a maioria das plantas não tem carimbo |
| Cota sem texto legível | Ler o texto quando houver; medir a geometria e perguntar o valor quando não |
| Onde o código mora | **Núcleo**, como função pura; cada interface só desenha o resultado |
| Ordem | **Etapa 3 primeiro.** Estas duas vêm depois |

A decisão de morar no núcleo não foi debatida porque é o mesmo padrão de
`classify`/`select`: a detecção é `entidades → cotas encontradas`, roda igual
nos três consumidores, e assim a versão web ganha a feature sem reimplementar
nada. O que é específico de cada interface é só a tela de confirmação.

## Achados sobre a planta real

Tudo abaixo foi medido em `LAY-1031.26.00_REV 00.pdf` — 18.860 entidades, 238
textos, 16.963 segmentos.

### A escala está escrita no carimbo

O rótulo `ESCALA:` está em (1317,8, 49,0) e o valor `1:40` logo abaixo,
deslocado de +4,7 pt em X e −12,4 pt em Y. É o **único** texto da folha que casa
com o padrão `1:N`. O carimbo também traz `ÁREA: 29,56m²`, `PÉ DIREITO: 2,41m` e
`FOR. FOLHA: A2`.

Ler o carimbo é o caminho mais barato e confiável **para esta família de
plantas**. Veja a ressalva logo abaixo antes de tratá-lo como estratégia
principal — ele não é.

### A maioria do acervo não tem carimbo padronizado

Informado pelo usuário em 2026-08-08, e é a informação que mais muda o desenho:
**a maior parte das plantas e desenhos técnicos que ele recebe não segue esse
padrão de folha com identificação e escala declarada.** A `LAY-1031` é da
família padronizada da casa; ela é a exceção, não a regra.

Consequência direta: a leitura do carimbo é a estratégia **secundária**, um
atalho ótimo quando existe. A detecção por cota é a **principal**, porque é a
única que funciona em desenho sem carimbo. Isso inverte a recomendação que se
faria olhando só a planta de exemplo — e é o tipo de erro de amostra que uma
sondagem em um arquivo só produz com facilidade.

Segunda consequência: em acervo heterogêneo, heurística rígida quebra mais. É o
cenário em que um modelo de linguagem tem mais valor — ver a seção sobre IA.

### A folha é A2 exata, e isso é um teste de sanidade de graça

1684 × 1191 pt = 594 × 420 mm, que é A2 ao milímetro. Quando o papel bate com um
formato padrão, o desenho foi plotado em tamanho real e a escala nominal do
carimbo vale. Quando **não** bate, é sinal de *fit to page* — exatamente o caso
em que o README já manda desconfiar da escala informada. Essa conferência sai de
graça e deve entrar na feature.

### As cotas viraram desenho, não texto

O achado que derruba a ideia original. A página tem 2.768 caracteres de texto, e
entre eles **não existe `7.06`, `6.06` nem `0.50`** — em nenhuma grafia.
`search_for("J2")` acha 1 ocorrência; `search_for("7.06")` acha zero. As fontes
embutidas são todas TrueType: ArialMT, Verdana, Calibri, Calibri-Light.

A causa é o comportamento clássico do AutoCAD: **o estilo de texto das cotas usa
fonte SHX**, que o PDF não embute como texto, então o plot converte cada número
em geometria. O carimbo usa TrueType e por isso virou texto de verdade. É por
isso que a cota aparece no DXF exportado — está lá, como linhas.

Consequência: **não há número para ler**. Numa planta assim, deduzir o valor da
cota exigiria reconhecer dígitos desenhados. Numa planta plotada com estilo
TrueType, a cota sairia como texto e a leitura direta funcionaria. **Não se sabe
a proporção entre os dois casos no acervo** — e é essa proporção que decide se
vale pagar por OCR algum dia.

### As cotas encadeadas fecham a conta

No print que o usuário mandou: `0,50 + 6,06 + 0,50 = 7,06`. Quando um grupo de
cotas encadeadas fecha, a leitura está quase certamente certa. É um sinal de
confiança muito mais forte do que qualquer heurística isolada, e deve ser usado.

### O texto da cota usa ponto; o carimbo usa vírgula

`7.06` na cota, `29,56m²` no carimbo, na mesma família de desenhos. O leitor
tem de aceitar os dois **no mesmo documento**. O `pdftodxf/numeros.py`, escrito
em 2026-08-08 para as entradas digitadas, já resolve isso: com um separador só e
dois dígitos depois, ele lê como decimal.

### A espessura do contorno já sai resolvida

O usuário pediu "considerar o centro da espessura do contorno". O extrator
guarda o *caminho* do PDF, e o traço é desenhado centrado nele — as coordenadas
que já existem **são** o eixo central. Nada a fazer, exceto quando a parede é
desenhada como dois contornos separados, que é outro problema.

A espessura em si (`width` do path) não é extraída hoje. Se algum dia importar
para desenhar a seleção sob o cursor, é uma linha no `extractor.py`.

### Círculo não existe como entidade

Uma circunferência vira **quatro arcos de 90°**. Cada `Arc` carrega `center` e
`radius`, então medir raio e diâmetro funciona clicando em qualquer pedaço — mas
afirmar "isto é um círculo inteiro" exige juntar os quatro arcos concêntricos.
Vale para o *snap* de centro e de quadrante também.

### Um indício de que o carimbo pode mentir por pouco

Há um segmento horizontal de 504,5 pt que, com o `1:40` do carimbo, daria
**7,119 m** — enquanto o print da cota mostra **7.06**. Se esse segmento for
mesmo aquela cota, a escala real do papel é ~1:39,7, e o carimbo está 0,8%
otimista: 5,6 cm de erro em 7 metros.

**Não está confirmado** que aquele segmento é a cota do print. Trate como
indício, não como fato. Mas é exatamente o tipo de desvio que só a comparação
entre carimbo e cota revela, e é um argumento concreto a favor de fazer as duas
leituras e compará-las, como foi decidido.

## Como ler um número que virou desenho

Três caminhos, do mais adequado ao menos:

1. **Casamento de forma vetorial.** Os glifos são desenhados pelo AutoCAD sempre
   iguais, apenas escalados. Agrupar os traços em caixas do tamanho de um
   dígito, normalizar e comparar com moldes. Determinístico, sem dependência
   nova, e mais preciso que OCR — porque trabalha sobre a forma exata em vez de
   sobre pixels. Dá trabalho, e é o caminho tecnicamente correto.
2. **OCR sobre recorte rasterizado.** Rasteriza o que já se tem em vetor para
   depois adivinhar o que era: perde informação de propósito. Vale como voto
   adicional independente, não como fonte única.
3. **Modelo de linguagem multimodal.** Ver a seção seguinte.

Os números da cota **não** estão em imagem: a página tem 53 imagens
rasterizadas, quase todas de 13 × 42 pt, cobrindo 1,3% da folha — são símbolos,
não o desenho. O que existe é geometria.

## Sobre usar IA neste projeto

Ideia do usuário, discutida em 2026-08-08. Vale, com limites que precisam estar
escritos.

**Onde ajuda de verdade:** desenho heterogêneo, que é a maior parte do acervo.
Carimbo de layout imprevisto, layer com nome bagunçado, texto livre. Situações em
que a heurística rígida quebra e em que errar custa pouco porque revisar é fácil.

**Onde não serve:** como fonte da medida. Escala é medida de engenharia, e
modelo de linguagem não é determinístico — a mesma planta pode dar respostas
diferentes. Ler 7.05 onde estava 7.06 não dispara alarme nenhum, e é a definição
do pior resultado possível: errar em silêncio. Como **voto adicional** ao lado
do carimbo e da geometria, ótimo. Como decisor, não.

**A restrição que derruba a premissa de custo zero:** assinaturas como ChatGPT
Plus/Pro (Codex CLI) e Claude Max dão acesso pessoal e interativo às
ferramentas. Usá-las como motor de um aplicativo — ainda mais um serviço web
público em VPS, servindo terceiros — está fora do que essas assinaturas
permitem, nos dois casos, e arrisca a suspensão da conta pessoal. O caminho
legítimo é API com chave própria, paga por uso. Para este caso o custo é baixo:
manda-se um recorte de cota, não a planta inteira.

**Guarda de segredo** — a proposta original era senha em `.md` dentro de
`secrets/`. Três correções:

- Nada de segredo em arquivo dentro do projeto: um `git add -A` distraído
  publica a chave. O `.gitignore` de hoje **não** cobre `secrets/`.
- A senha do painel vai guardada como **hash**, nunca em claro.
- A chave da API vive em variável de ambiente na VPS, fora do repositório e
  fora do backup do projeto.

O fluxo guiado para obter e colar a chave, com link para a página de origem e
campo de colagem, é bom desenho de interface e não tem objeção.

## O que ainda não se sabe

- **Qual a proporção de plantas com cota em texto de verdade** no acervo. Decide
  se a leitura direta cobre alguma coisa ou quase nada. Uma resposta barata:
  rodar uma sondagem de `search_for` sobre uma pasta inteira de PDFs.
- **Como a linha de cota é desenhada**: um segmento só ou dois com o vão do
  texto no meio; como as setas ou ticks aparecem; a que distância o texto fica.
  Sem isso, a regra de associação é chute. Exige olhar os dados vetoriais de uma
  planta cotada — o print mostra a aparência, não a estrutura.
- **Detalhes ampliados na mesma folha** têm escala diferente do desenho
  principal. Uma detecção que junte tudo num fator só vai errar. O tratamento
  natural é agrupar os fatores encontrados e mostrar quando houver mais de um
  grupo, em vez de escolher sozinho.

## Riscos que a implementação tem de encarar

- **Errar em silêncio é o pior resultado possível.** Uma escala deduzida errada
  entrega um desenho inteiro fora de medida com ar de certeza. Daí a exigência —
  acertada — de confirmação com o recorte visual de onde veio o número.
- Texto de cota com prefixo ou sufixo: `Ø 50`, `R 30`, `2.44 (T)`, `%%c`.
- Cota em unidade diferente da do desenho (planta em metro, cota em centímetro).
- O quadro de esquadrias tem textos que *parecem* cota e não são: nesta planta,
  `1,00X1,00`, `0,80X2,10`, `0,90X2,10` são medidas de porta e janela. Qualquer
  detector ingênuo por texto numérico vai mordê-los.

## Como reproduzir as sondagens

Todas foram feitas com o `.venv` do projeto, extraindo a página e olhando as
entidades. O caminho mais curto para repetir:

```python
from pdftodxf.extractor import extract_page
from pdftodxf.geometry import TextItem
r = extract_page("Input/LAY-1031.26.00_REV 00.pdf")
textos = [e for e in r.entities if isinstance(e, TextItem)]
```

E, para saber se o texto existe mesmo no PDF antes de culpar a extração:

```python
import fitz
pg = fitz.open(caminho)[0]
"7.06" in pg.get_text(), pg.search_for("7.06")
```
