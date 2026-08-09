# Etapa 3.6 — indicadores de progresso

Data: 2026-08-09

Etapa curta, decidida depois da 3.5 e **antes** da etapa 4. Escrita para bastar
por si.

## O problema

A tela não conta ao usuário o que está acontecendo. Nos cinco momentos em que
ela pode ficar parada, isto é o que ele vê hoje:

| Momento | Hoje | Quanto pode durar |
|---|---|---|
| Enviando o PDF | "Enviando o PDF · Um instante." | um PDF de 100 MB numa conexão doméstica leva minutos |
| Na fila / extraindo | "Processando a planta · A extração já começou." | a planta de 2,3 M entidades leva o que levar |
| Baixando o desenho | faixa fixa "Carregando o detalhe do desenho…" | dezenas de MB |
| Desenhando na tela | **nada** | de 300 a 840 ms por preparo, medido |
| Gerando o DXF | **nada** | a exportação carrega o cache inteiro e escreve o arquivo |

Os dois piores são o primeiro e o último: uma barra de progresso do envio **já
estava na spec geral** desde 2026-08-01, com botão de cancelar, e nunca foi
entregue; e clicar em "Exportar DXF" numa planta grande deixa a tela
absolutamente parada, sem um pixel dizendo que alguma coisa está em curso.

## O princípio

**Nunca inventar porcentagem.** Onde existe número real, barra determinada com o
valor. Onde não existe, barra indeterminada com o tempo decorrido — que é
informação verdadeira e suficiente para o usuário saber que não travou.

A spec geral já dizia isso para a extração: "indicador de trabalho em andamento,
**sem prazo falso**". Esta etapa estende a regra aos cinco momentos.

## Os cinco momentos

| Momento | Barra | De onde vem o número |
|---|---|---|
| Enviando o PDF | **determinada** + cancelar | bytes enviados / tamanho do arquivo |
| Na fila / extraindo | indeterminada + tempo | o servidor só informa o estado |
| Baixando esqueleto e detalhe | **determinada** | `Content-Length` e a leitura do corpo em pedaços |
| Desenhando na tela | **determinada** | entidades desenhadas / sobreviventes |
| Gerando o DXF | indeterminada + tempo | a rota é síncrona e não reporta nada |

Dar porcentagem aos dois indeterminados exigiria o servidor passar a reportar
progresso — mudança no worker Python, no formato da ficha e no contrato das
rotas. É trabalho de servidor, não de tela, e fica fora desta etapa.

## Onde cada um aparece

Dois lugares, os que já existem:

- **O painel de aviso** (`.aviso`, a sobreposição sobre o desenho) recebe a
  barra do **envio**, da **extração** e da **exportação**. São os três momentos
  em que não há nada de útil a fazer na tela.
- **A faixa discreta do rodapé do desenho** (`.faixa-detalhe`) recebe a barra do
  **download da geometria** e da **pintura**. Nesses dois o desenho já está
  utilizável, e uma sobreposição seria estorvo.

**A pintura só mostra barra se passar de 300 ms.** Ela roda a cada mudança de
opção e a cada gesto que obrigue a refazer a lista; numa planta leve isso é
instantâneo, e piscar uma barra a cada clique seria pior do que não ter nenhuma.

## O envio por `XMLHttpRequest`

`fetch` não expõe progresso de upload nos navegadores — o corpo em fluxo com
`duplex: "half"` não tem suporte suficiente. `enviarPdf` passa a usar
`XMLHttpRequest`, que tem `upload.onprogress` desde sempre.

Duas coisas não podem regredir nessa troca, porque já valem hoje:

- **O `AbortSignal` continua funcionando.** Trocar de planta no meio do envio
  aborta o que está em voo; sem isso, a resposta antiga chega depois e
  contamina a tela.
- **O erro do servidor continua virando `ErroDaApi` com o status e o detalhe.**
  É o que faz as mensagens de recusa aparecerem com texto próprio em vez de um
  "HTTP 413" seco — e, na etapa 4, é por esse caminho que a recusa por cota vai
  chegar à tela.

O botão **Cancelar** aparece ao lado da barra e chama o mesmo `abort` que a
troca de planta já usa.

## O download da geometria em pedaços

`lerGeometriaBruta` passa a ler `response.body` com um leitor, acumulando os
pedaços e somando os bytes. O total vem do cabeçalho `Content-Length`.

Quando o cabeçalho não vem — resposta comprimida sem tamanho declarado, por
exemplo —, a barra fica **indeterminada** em vez de mostrar uma porcentagem
inventada. O buffer devolvido tem de ser byte a byte idêntico ao que
`arrayBuffer()` devolvia; é sobre ele que o leitor do formato monta as
`TypedArray` sem copiar.

## O tempo decorrido

Formato curto e em português: `8 s`, `1 min 20 s`, `12 min`. Atualiza a cada
segundo, e some quando o trabalho termina. Abaixo de um segundo não aparece —
piscar "0 s" é ruído.

## Componentes

- `web/frontend/src/progresso.ts` — **puro**: o modelo do indicador
  (determinado com fração, ou indeterminado com instante de início) e a
  formatação de porcentagem e de tempo decorrido. É onde mora tudo o que dá
  para testar sem navegador.
- `web/frontend/src/ui/controles.ts` — ganha `criarBarraDeProgresso`, no mesmo
  lugar dos outros componentes montados à mão.
- `web/frontend/src/estilo.css` — a classe da barra, no vocabulário que a etapa
  3.5 estabeleceu.

Nada de `<progress>` nativo: ele não aceita o tratamento visual do resto da
tela sem gambiarra por navegador, e a barra é uma `<div>` com `role="progressbar"`
e os atributos `aria-valuenow`/`aria-valuemin`/`aria-valuemax` — que é o que
leitor de tela lê.

## Testes

**Puros, no vitest:** a formatação de tempo nas fronteiras (0, 1 s, 59 s, 60 s,
61 s, 3600 s); a porcentagem arredondada e presa entre 0 e 100; o indicador
indeterminado não expondo porcentagem nenhuma.

**`api.ts`, com `XMLHttpRequest` e corpo em pedaços forjados** — o arquivo já
usa `vi.stubGlobal` para o `fetch`, e o mesmo vale aqui: o envio reporta
progresso crescente e termina em 100%; abortar no meio rejeita com
`AbortError`; um 413 do servidor continua virando `ErroDaApi` com status e
detalhe; o download em pedaços devolve exatamente os mesmos bytes que a resposta
tinha, e reporta progresso; sem `Content-Length`, o progresso sai indeterminado
em vez de com porcentagem falsa.

**Ponta a ponta:** a barra de envio aparece com `aria-valuenow` e some ao
terminar; exportar mostra o indicador e ele some quando o download começa; a
faixa do rodapé mostra progresso enquanto o detalhe carrega.

## Ordem de implementação

| # | Tarefa |
|---|---|
| 1 | `progresso.ts`: o modelo puro e a formatação |
| 2 | `enviarPdf` por `XMLHttpRequest`, com progresso e cancelamento |
| 3 | `lerGeometriaBruta` em pedaços, com progresso |
| 4 | A barra na tela, ligada nos cinco momentos |

## Fora de escopo

- O servidor reportar progresso de extração ou de exportação
- Estimativa de tempo restante — seria previsão, e previsão errada é pior que
  nenhuma
- Retomar envio interrompido
- Progresso do envio em pedaços com retomada (a rota recebe o arquivo inteiro)

## Riscos

- **A troca de `fetch` por `XMLHttpRequest` é a parte perigosa.** Ela mexe no
  único caminho por onde o PDF entra no serviço, e o tratamento de erro dele é o
  que a etapa 4 vai usar para a recusa por cota. Os testes de `ErroDaApi` e de
  aborto existem para prender isso.
- **A pintura publica progresso a cada quadro.** Escrever no DOM a cada quadro
  custaria justamente no momento em que o quadro está apertado; a barra é
  atualizada por tempo, não por quadro.
