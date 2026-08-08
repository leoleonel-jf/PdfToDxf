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
| Fonte da escala | Carimbo **e** cota, comparando os dois |
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

Ler o carimbo é, disparado, o caminho mais barato e mais confiável para esta
família de plantas.

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
