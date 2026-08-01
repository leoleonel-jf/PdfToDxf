# PdfToDxf Web — especificação de projeto

Data: 2026-08-01

## Objetivo

Uma versão web do PdfToDxf, hospedada numa VPS e aberta ao público, com
**paridade total** de recursos em relação ao app desktop Tkinter existente:
visualizar a planta com pan e zoom, escolher a página, calibrar a escala por
dois cliques, ajustar a compactação com prévia ao vivo, ligar e desligar layers,
ver a estimativa de tamanho e baixar o DXF em escala real.

O app desktop continua existindo. As duas interfaces passam a compartilhar o
mesmo núcleo.

## Decisões tomadas

| Decisão | Escolha |
|---|---|
| Formato | App web completo no navegador (não é só API) |
| Acesso | Público, sem cadastro, protegido por limites técnicos |
| VPS | 8+ vCPU, 16+ GB RAM |
| Onde a geometria vive | No navegador — servidor extrai uma vez e envia |
| Desktop | Continua vivo, mesmo repositório, núcleo compartilhado |
| Backend | Python + FastAPI (reusa o núcleo) |
| Frontend | TypeScript puro + Canvas, compilado com Vite |
| Layout | Cabeçalho de duas faixas com todas as opções à vista |
| Deploy | Docker Compose + Caddy (HTTPS automático) |
| Registro de conversões | Um `.md` por página extraída, em `/registros`, guardado por 1 ano |

## Arquitetura

### O problema central

O app faz três coisas interativas sobre plantas que podem ter milhões de
segmentos: pan/zoom, calibração por dois cliques e prévia ao vivo da
compactação. No desktop isso é instantâneo porque tudo está na memória local.
Renderizar no servidor a cada gesto tornaria cada usuário conectado um custo
permanente de CPU e RAM — inviável para uso público.

A solução é extrair uma vez no servidor e deixar toda a interação no navegador.

### A divisão classify / select

Hoje `pdftodxf/optimize.py::apply_filters` decide e filtra na mesma varredura.
Três dos quatro filtros são triviais (layer, preenchimento, comprimento mínimo);
o quarto — `dedup` — monta um conjunto de hash com chaves arredondadas e depende
da ordem de iteração. Reimplementar o dedup em JavaScript arriscaria divergência
silenciosa entre a prévia e o DXF final.

`optimize.py` passa a expor duas funções:

**`classify(entities) -> EntityAttrs`** — roda uma vez no servidor, logo após a
extração. Produz arrays paralelos à lista de entidades, um número por entidade:

- `length_mm` — comprimento em mm de papel (só para `Segment`; 0 nos demais)
- `is_fill` — flag booleana, já vinda do extrator
- `layer_id` — índice inteiro na lista de layers
- `dup_group` — inteiro identificando o grupo de segmentos idênticos. **Aqui mora
  o trabalho pesado**: o conjunto de hash com as chaves arredondadas
  `(layer, color, p1, p2)` é montado uma vez, em Python, e vira número.
  Segmentos sem duplicata recebem grupo próprio.
- `byte_cost` — custo estimado em bytes no DXF (tabela `_BYTES` de `optimize.py`)

**`select(attrs, opts) -> mask`** — varredura linear, sem hash: compara
`layer_id` com os layers excluídos, `length_mm` com o limite, lê `is_fill`, e
para o dedup marca num vetor de bytes se aquele `dup_group` já emitiu alguém.
São ~30 linhas, escritas em Python e espelhadas em TypeScript.

**Por que isso garante que a prévia é o DXF:** o julgamento difícil — quem é
duplicata de quem — é feito uma única vez, em Python, e vira dado. Não existe
"a versão JS do algoritmo de deduplicação" para divergir. Os dois lados leem os
mesmos números.

**Ordem de eliminação:** hoje o dedup roda depois dos demais filtros, então se
dois segmentos idênticos existem e um é preenchimento, ligar "remover hachuras"
derruba o preenchimento e o outro sobrevive. Guardar apenas "é duplicata sim/não"
faria os dois sumirem. Guardando o **grupo**, o `select()` elege como
sobrevivente o primeiro do grupo que passa nos demais filtros, percorrendo a
ordem original das entidades — comportamento idêntico ao atual.

O desktop também passa a usar `classify()` + `select()`. `apply_filters` é
removido. Um caminho só, exercitado pelas duas interfaces.

### Fluxo de uma conversão

1. Usuário escolhe o PDF. Upload em pedaços (o limite é 100 MB). O servidor
   devolve `job_id` e o número de páginas.
2. Usuário escolhe a página. O servidor enfileira a extração.
3. Um processo worker roda `extractor.extract_page()` e depois `classify()`,
   grava o resultado no cache em disco e escreve o registro em `/registros`
   (ver seção própria). O PDF original é apagado assim que todas as páginas
   pedidas foram extraídas ou o trabalho expira.
4. O navegador baixa `geometry.bin` (coordenadas e atributos) e `meta.json`
   (layers, limites do desenho, contagens, dimensões da página).
5. O canvas desenha. Pan e zoom são transformação de matriz — não vão ao servidor.
6. **Calibrar:** dois cliques no canvas, converte pixels para pontos de papel,
   aplica a mesma fórmula de `calibration.scale_from_two_points`, mostra a escala
   deduzida na barra. Alternativa "Escala 1:N" também disponível, como no desktop.
7. **Opções e layers:** cada clique roda `select()` em TypeScript, redesenha e
   soma os `byte_cost` sobreviventes. Instantâneo, sem rede.
8. **Exportar:** envia escala, unidade e opções. O servidor recupera a extração
   do cache, roda `select()` (versão Python), `join_segments()` e
   `dxf_writer.write_dxf()`, e devolve o DXF para download.

### Formato binário da geometria

`geometry.bin` é uma concatenação de seções, uma por tipo de entidade
(`Segment`, `Polyline`, `Arc`, `Bezier`, `TextItem`), cada uma com arrays
paralelos de `Float32Array` para coordenadas e `Int32Array`/`Uint8Array` para os
atributos vindos do `classify()`. Os textos vão num bloco UTF-8 separado com
índices de deslocamento. O deslocamento e o comprimento de cada seção ficam no
`meta.json`. A resposta é comprimida com gzip pelo Caddy.

Ordem de leitura no cliente = ordem de escrita no servidor = ordem original das
entidades, que é o que faz o `select()` das duas pontas concordar.

### Renderização no canvas

Canvas 2D com `Path2D` agrupado por (layer, cor) — um caminho por grupo, não um
por entidade. O caminho é reconstruído quando a seleção muda; pan e zoom apenas
alteram a transformação.

Durante um gesto de pan ou zoom, o desenho é feito sobre um canvas
pré-renderizado transformado, e o redesenho em fidelidade plena acontece quando o
gesto termina — a mesma estratégia que o desktop usa hoje para não piscar.

### Estimativa de tamanho

O único número aproximado é a estimativa com "unir em polilinhas" marcado, porque
o quanto os segmentos se encadeiam depende de quais sobreviveram aos filtros. As
duas pontas usam a mesma fórmula de aproximação já presente em
`optimize.estimate_bytes`, e o valor aparece prefixado por "≈", como já aparece
no desktop.

## Interface

Layout de duas faixas no cabeçalho, com o desenho ocupando todo o resto da tela.

**Faixa 1:** abrir PDF · seletor de página · calibrar (2 pontos) · escala e
unidade atuais · estimativa de tamanho · botão Exportar DXF.

**Faixa 2:** opções de compactação como botões ligáveis (unir em polilinhas,
arredondar coordenadas, remover duplicados, remover preenchimentos, descartar
segmentos abaixo de N mm) e os layers como chips ligáveis, com um menu "+N" para
os excedentes quando a planta tiver muitos layers.

Todo clique nas faixas atualiza a prévia e a estimativa na hora.

**Rodapé:** uma linha fixa informando que o texto das plantas e o endereço IP
são registrados por 1 ano, com link para a página de privacidade.

## Estrutura do repositório

```
pdftodxf/            núcleo compartilhado
  extractor.py       inalterado
  geometry.py        inalterado
  calibration.py     inalterado
  dxf_writer.py      inalterado
  optimize.py        ganha classify() e select(); apply_filters() sai
  gui.py             desktop Tkinter, passa a usar classify/select
  export_dialog.py   idem
web/api/
  main.py            rotas FastAPI
  jobs.py            fila em ProcessPoolExecutor, estado dos trabalhos
  packing.py         serialização de geometry.bin e meta.json
  limits.py          limites de tamanho, cota por IP, tetos de recurso
  storage.py         cache em disco, prazos e limpeza
  registros.py       geração dos .md de registro e expurgo de 1 ano
web/frontend/src/
  main.ts            composição da tela
  canvas.ts          renderizador
  select.ts          espelho TypeScript de optimize.select()
  calibrate.ts       calibração por dois pontos
  toolbar.ts         as duas faixas do cabeçalho
  api.ts             cliente HTTP
  privacidade.html   página de privacidade, linkada no rodapé
tests/               testes do núcleo, de paridade e de API
deploy/              Dockerfile, docker-compose.yml, Caddyfile
```

## API

| Rota | Efeito |
|---|---|
| `POST /api/jobs` | Recebe o PDF (em pedaços). Devolve `job_id` e número de páginas. |
| `GET /api/jobs/{id}` | Estado: na fila, extraindo, pronto ou erro. |
| `POST /api/jobs/{id}/pages/{n}` | Enfileira a extração daquela página. |
| `GET /api/jobs/{id}/pages/{n}/geometry.bin` | Geometria binária. |
| `GET /api/jobs/{id}/pages/{n}/meta.json` | Layers, limites, contagens. |
| `POST /api/jobs/{id}/pages/{n}/export` | Recebe escala, unidade e opções. Devolve link do DXF. |
| `GET /api/download/{token}` | Entrega o DXF gerado. |

Páginas são extraídas sob demanda: abrir um caderno de 40 folhas processa apenas
as folhas efetivamente visitadas, e custa um único envio na cota do visitante.

## Limites de uso público

| Limite | Valor |
|---|---|
| Tamanho máximo do PDF | 100 MB |
| Teto de entidades por página | 3.000.000 (acima disso, recusa explicando o motivo) |
| Extrações simultâneas | 4 (de 8 vCPU) |
| Envios por IP | 3 por hora |
| Exportações por IP | 10 por hora |
| Prazo dos arquivos | 4 horas |
| Cota total de disco | 40 GB, com limpeza do mais antigo quando estourar |

A extração roda em **processo separado**, com limite de memória e de tempo de
CPU aplicados ao processo. Uma planta monstruosa mata o próprio worker e vira
uma mensagem de erro clara na tela, sem derrubar o serviço.

A fila usa `ProcessPoolExecutor`: é um servidor só, os trabalhos são curtos e
descartáveis, e reiniciar o serviço perdendo trabalhos em andamento é aceitável
dado o prazo de 4 horas. Se um dia forem necessárias várias máquinas, troca-se a
fila sem mexer no restante.

O PDF original é apagado logo após a extração. Geometria e DXF expiram em 4
horas. Nenhum arquivo enviado é indexado, listado publicamente ou reaproveitado.
O registro descrito na seção seguinte é a única coisa que sobrevive a esse prazo.

## Registro de conversões

Cada página extraída gera um arquivo Markdown em `/registros`. O registro é
gravado no fim da extração, junto com o `classify()`, e não depende de o usuário
chegar a exportar o DXF.

### Nome do arquivo

`{ip}-{nome-do-pdf}-p{pagina}-{timestamp}.md`

- `ip` — endereço de origem com pontos e dois-pontos trocados por `_`, para ser
  nome de arquivo válido em qualquer sistema (`192_168_0_10`). Atrás do Caddy, o
  endereço real vem do cabeçalho `X-Forwarded-For`.
- `nome-do-pdf` — nome enviado, sem a extensão, higienizado (apenas letras,
  números, hífen e sublinhado) e truncado em 60 caracteres.
- `pagina` — número da página extraída, começando em 1. Necessário porque um
  mesmo envio pode gerar vários registros.
- `timestamp` — `YYYYMMDD-HHMMSS` em UTC.

Se o nome resultante já existir, um sufixo numérico é acrescentado. O caminho
final é sempre validado para ficar dentro de `/registros`, para que um nome de
arquivo malicioso não consiga escrever fora da pasta.

### Conteúdo

Cabeçalho de identificação em frontmatter YAML: IP, nome original do PDF, página,
data e hora, `job_id`, tamanho do PDF em bytes e tempo de extração em segundos.

Corpo do documento:

- **Textos da planta** — todos os `TextItem` extraídos, em tabela, com o texto,
  a posição, a altura e a rotação de cada um, na ordem em que o extrator os
  encontrou.
- **Layers** — lista dos layers detectados e quantas entidades cada um tem.
- **Contagem de entidades** — total por tipo (`Segment`, `Polyline`, `Arc`,
  `Bezier`, `TextItem`).
- **Geometria da folha** — dimensões da página em pontos e em mm, e os limites
  do desenho.

Não é gravada a geometria em si — apenas texto e números agregados.

### Prazo e transparência

Os registros são apagados automaticamente após **1 ano**, pela mesma tarefa
periódica que limpa os arquivos temporários. A pasta `/registros` fica em volume
próprio, fora do volume de arquivos temporários, e nunca é servida pela web.

Como o registro guarda conteúdo de documentos de terceiros associado a um
endereço IP, a interface traz uma linha fixa no rodapé informando isso, com link
para uma página de privacidade que explica o que é guardado, por quanto tempo e
como pedir a remoção.

## Deploy

Docker Compose com dois contêineres:

- **app** — uvicorn servindo o FastAPI e os arquivos estáticos do frontend já
  compilados
- **caddy** — proxy reverso na frente, resolvendo HTTPS e certificado sozinho

Dois volumes: um para os arquivos temporários (prazo de 4 horas) e outro para
`/registros` (prazo de 1 ano). A limpeza dos dois roda como tarefa periódica
dentro do app. O volume de registros não é servido pela web em nenhuma rota.

## Testes

**1. Núcleo.** O `tests/test_roundtrip.py` existente continua valendo, adaptado
para `classify`/`select`. Acrescenta-se um teste de equivalência que compara a
saída de `select()` com a do `apply_filters()` original sobre um PDF sintético,
garantindo que a refatoração não muda comportamento. Esse teste é removido
depois que `apply_filters` sair.

**2. Paridade Python ↔ TypeScript.** Um arquivo de casos em JSON contendo tabelas
de atributos e combinações de opções, com a máscara de sobreviventes esperada.
O mesmo arquivo é executado pelo pytest e pelo vitest. Qualquer divergência entre
as duas implementações do `select()` quebra a suíte. É o teste que sustenta a
promessa de que a prévia é o DXF.

**3. API.** PDF sintético convertido de ponta a ponta; arquivo acima de 100 MB é
recusado; página acima do teto de entidades é recusada com mensagem; a cota por
IP bloqueia o quarto envio na mesma hora; arquivos expirados somem do disco.

**4. Registros.** A extração de um PDF sintético gera o `.md` esperado em
`/registros`, com todos os textos da planta presentes; um nome de arquivo com
caracteres de caminho (`../`, barras) é higienizado e o arquivo não escapa da
pasta; dois envios do mesmo arquivo pelo mesmo IP no mesmo segundo não se
sobrescrevem; registros com mais de 1 ano são apagados pelo expurgo e os mais
novos permanecem.

## Fora de escopo

- Cadastro de usuários, contas e cotas por conta
- Verificação anti-robô (captcha)
- Saída em DWG
- PDFs escaneados (vetorização por visão computacional)
- Detecção automática da escala pelas cotas do desenho
