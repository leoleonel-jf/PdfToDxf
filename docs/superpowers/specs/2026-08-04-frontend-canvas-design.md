# Etapa 3 — o frontend: canvas, `select.ts` e calibração

Desenho validado em 2026-08-04. Complementa
`docs/superpowers/specs/2026-08-01-pdftodxf-web-design.md`, que continua sendo a
especificação geral do projeto; onde os dois discordarem sobre a etapa 3, vale
este documento. As correções que ele impõe à spec geral estão na última seção.

## O que esta etapa entrega

A tela inteira do conversor, funcionando ponta a ponta contra a API da etapa 2:
abrir um PDF, escolher a página, ver a planta no canvas, calibrar por dois
pontos, ligar e desligar opções de compactação e layers vendo a prévia mudar na
hora, e exportar o DXF.

**Fica de fora, para a etapa 4:** o canto da conta na faixa 1, o indicador de
cota restante e as cinco linhas de erro sobre cota esgotada. O canto fica vazio
— sem botão falso, sem dado inventado. Um placeholder que mente atrapalha a
conferência manual mais do que ajuda.

## A decisão que governa a arquitetura

Cada clique numa opção de compactação re-executa o `select()` sobre até 3
milhões de entidades e reconstrói os `Path2D`. A spec geral promete que "todo
clique nas faixas atualiza a prévia e a estimativa na hora". Se esse trabalho
rodar na thread da interface, a tela congela a cada clique.

Por isso: **o `select()` roda num Web Worker; o desenho fica na thread
principal.** O worker guarda os arrays da geometria e devolve a máscara como
`Uint8Array` transferível — cópia zero. A thread principal reconstrói os
`Path2D` e desenha.

A divisão cai no ponto natural: o julgamento sai da thread da interface, o
desenho fica onde o canvas está. E casa com o contrato, porque o `select.ts` é
função pura sobre arrays — que é exatamente o que se testa bem, dentro ou fora
de um worker.

**Isto é uma hipótese, não uma medida.** A primeira tarefa do plano mede, no
navegador, o custo do `select()` e o da reconstrução dos caminhos em 3 milhões
de entidades. Se a reconstrução for barata, o worker vira simplificação
opcional; se for cara, a medida confirma a fronteira. Comprometer o desenho
inteiro com um palpite seria o tipo de erro que só aparece tarde.

## A divisão em duas partes não é neutra para o `select()`

Achado do desenho, e a razão de o worker precisar fazer mais do que só chamar
uma função pura.

O `select()` do Python, com `dedup` ligado, guarda um sobrevivente por
`dup_group` e elege **o primeiro em ordem original** — o `emitted` é marcado
conforme o laço varre os índices. O esqueleto leva os segmentos longos e o
detalhe leva os curtos, então duas entidades do mesmo grupo caem em partes
diferentes com facilidade.

Daí duas coisas que parecem óbvias e estão erradas:

- **Rodar o `select()` sobre cada parte isolada.** Cada uma elegeria o seu
  sobrevivente, e a tela mostraria uma duplicata que o DXF não tem.
- **Concatenar esqueleto e detalhe.** A concatenação não é ordem original: é
  "longos, depois curtos". O sobrevivente eleito seria outro.

**Portanto:** as duas partes são intercaladas de volta em ordem de índice antes
de qualquer decisão. As duas já chegam ordenadas — o `dividir()` da etapa 2
preserva a ordem original em cada lista —, então é uma intercalação de uma
passada só. É para isto que a seção `idx` do formato binário existe.

**Quem intercala é a thread principal, não o worker.** O worker precisa dos
atributos de decisão; o canvas precisa das coordenadas. Transferir o buffer ao
worker deixaria a thread principal sem o que desenhar, e copiar tudo para os
dois lados custaria dezenas de megabytes à toa. Então a intercalação é função
pura no `formato.ts`, chamada uma vez pela thread principal, que fica com as
coordenadas e manda ao worker uma cópia apenas dos seis arrays que o `select()`
lê: `kind`, `layer_id`, `is_fill`, `length_um`, `dup_group` e `byte_cost`.

**Consequência para a interface:** enquanto o detalhe não chegou, a prévia é
provisória **no desenho**, não só na estimativa. Com dedup ligado, o esqueleto
sozinho pode mostrar um traço que o DXF final descarta. A faixa de "carregando
detalhe" cobre esse período, e a estimativa continua marcada como parcial.

## Ferramental

**Vite com TypeScript**, e o `vitest` — que é construído sobre o Vite — para os
testes. O `vitest` entraria de qualquer forma, porque a spec geral exige que os
1024 casos do contrato rodem em TypeScript; o Vite vem junto.

Em desenvolvimento, o Vite serve o frontend e faz proxy de `/api` para o
uvicorn, o que evita dois servidores em portas diferentes brigando com CORS.

Em produção, **um estágio do Dockerfile compila o frontend** e o estágio final
carrega só Python e os estáticos prontos. A VPS nunca instala `node` nem vê
`node_modules`, e o que roda é exatamente o que o build gerou — não há como
subir um `dist/` desatualizado. O FastAPI serve os estáticos.

## O `kind` em dois idiomas

O contrato `tests/casos_select.json` traz `kind` como lista de strings
(`"Segment"`, `"Arc"`…). O `geometry.bin` grava código numérico de 0 a 4. O
`select.ts` fica entre os dois, e o laço dele roda uma vez por entidade.

**O `select.ts` compara inteiros**, que é o que chega do binário. O carregador
do teste traduz as strings do contrato para código antes de comparar — uma
tradução curta, num lugar só, exercitada pelos 1024 casos.

O `casos_select.json` **não é tocado**. Ele continua sendo dado congelado, e o
`git diff` dele continua sendo o alarme que é hoje. Isso encerra a dívida
"`kind` é lista de strings e o binário grava código numérico; falta reconciliar"
sem mexer no artefato mais protegido do projeto.

## Arquivos

Em `web/frontend/src/`:

| Arquivo | Responsabilidade |
|---|---|
| `api.ts` | Cliente HTTP: envio, consulta de estado, `meta.json`, `geometry.bin`, exportação |
| `formato.ts` | Leitor do binário: confere a magia, lê a tabela de seções, monta as `TypedArray` sobre o buffer sem copiar. Também a **intercalação** das duas partes em ordem de índice, como função pura |
| `select.ts` | Espelho de `optimize.select()`, sobre arrays numéricos. Função pura |
| `estimativa.ts` | Espelho de `optimize.estimate_bytes`. Função pura |
| `worker.ts` | Guarda os arrays **de decisão** já intercalados; chama `select` e `estimativa`; devolve máscara e bytes |
| `canvas.ts` | `Path2D` agrupado por (layer, cor); a transformação papel↔tela; pintura |
| `gestos.ts` | A aritmética de pan e zoom, como função pura sobre a transformação |
| `calibrate.ts` | Calibração por dois pontos, com lupa no toque |
| `toolbar.ts` | As duas faixas do cabeçalho |
| `estados.ts` | Mensagens de espera e de erro |
| `main.ts` | Composição da tela e o estado |
| `estilo.css` | Variáveis de cor e os poucos componentes, escrito à mão |

Três arquivos a mais do que a lista da spec geral: `formato.ts`, para separar a
leitura do binário de quem o consome; `estimativa.ts`; e `gestos.ts`, que tira a
aritmética do gesto de dentro do renderizador. Essa última separação é o que
permite **provar** que o zoom mantém parado o ponto sob o dedo — função pura se
testa sem navegador, e o que sobra para a conferência manual é o tato, não a
conta.

O `select.ts` e o `estimativa.ts` são conferidos pelo **mesmo** teste de
paridade, porque o contrato congela a máscara e o `bytes_esperado` lado a lado
em cada caso. O carregador que lê o `casos_select.json` e traduz o `kind` vive
num auxiliar único, usado por esse teste e pelo da intercalação; ele existe só
nos testes.

`conta.ts` não entra nesta etapa.

## Fluxo

1. Envio do PDF → `job_id` e número de páginas.
2. Escolha da página → enfileira a extração.
3. Consulta do estado **com recuo crescente**: 300 ms subindo até 2 s. Uma
   planta pesada leva minutos, e bater a cada 300 ms por minutos é ruído à toa.
4. `meta.json` → layers, dimensões da folha, contagens, tamanho das duas partes.
5. Esqueleto → worker → máscara → o canvas desenha e enquadra a folha.
6. Detalhe em segundo plano → o worker intercala em ordem de índice → máscara
   nova → o canvas reconstrói e a faixa de carregamento some.
7. Clique em opção ou layer → o worker devolve máscara e bytes → o canvas
   reconstrói e a estimativa atualiza.
8. Calibrar → dois pontos no desenho → escala e unidade na faixa.
9. Exportar → o servidor gera → link de download.

### Trocar de página no meio do carregamento

Sem cuidado, o detalhe da página anterior chega depois da troca e contamina o
canvas da página nova. É um defeito silencioso, que só aparece com rede lenta e
que nenhum teste de unidade pega por acaso.

Toda busca fica sob um `AbortController` amarrado à página corrente. Trocar de
página aborta o que estiver em voo.

## Estados e erros

Mapeados dos códigos que a API da etapa 2 já devolve:

| Vindo do servidor | O que a tela mostra |
|---|---|
| `na_fila` / `extraindo` | Indicador de trabalho em andamento, sem prazo falso |
| `sem_vetores` | Só PDFs vetoriais funcionam, e por quê |
| `entidades_demais` | A planta é grande demais, e qual é o limite |
| `recurso` | Não pôde ser processada: passou de memória ou de tempo |
| `interno` | Falha registrada no servidor |
| 404 no trabalho | A planta expirou; reenvie |
| 413 no envio | Maior que o teto, avisado antes de o envio começar |
| Detalhe carregando | Faixa discreta; o desenho já é utilizável, mas provisório |

O estado `"extraindo"` está no contrato da API e hoje nada o escreve — o
processo pai é o dono do estado e não sabe a hora em que o worker pega o
trabalho. O frontend trata `"extraindo"` como sinônimo de `"na_fila"`.

## Testes

**1. Paridade.** Os 1024 casos do contrato no `vitest`, conferindo a máscara e o
`bytes_esperado`. É o teste que sustenta a promessa de que a prévia é o DXF.

Um ponto exige cuidado cirúrgico: o Python calcula
`min_len_um = int(min_len_mm * 1000.0 + 0.5)` e o TypeScript precisa usar
`Math.round(min_len_mm * 1000.0)`. A docstring do `select()` já registra que
essa é a regra — o `round()` do Python arredonda para o par mais próximo e
discordaria de um comprimento exatamente em cima do limiar.

**2. Leitor do formato.** Um teste Python gera um `.bin` de exemplo e o `.json`
do que se espera ler dele; o `vitest` lê os dois e compara. Testar o TypeScript
contra ele mesmo não provaria nada: o que precisa ficar preso é a ponte entre as
duas implementações do formato.

**3. Intercalação.** Esqueleto e detalhe intercalados reproduzem a ordem
original; e com dedup ligado, o resultado sobre o conjunto intercalado é igual
ao `select()` do Python sobre a lista inteira. É o teste que prende o achado
descrito acima.

**4. Canvas contra contexto 2D falso.** Um contexto de mentira grava as chamadas
de desenho, e o teste afirma que o que foi traçado corresponde exatamente à
máscara devolvida pelo `select()`, agrupado por (layer, cor). Prende a promessa
central sem navegador e sem comparar pixel.

**5. Ponta a ponta no Playwright.** Sobe o uvicorn e o Vite, envia um PDF
sintético, espera o desenho aparecer, clica nas opções, calibra, exporta e
confere que o DXF baixou. **Espera por condição, nunca por tempo** — a etapa 2
já mostrou o que uma espera por relógio faz com a confiança na bateria.

Gestos de toque e a lupa da calibração ficam para a conferência manual.

## Correções que este desenho impõe à spec geral

A spec de 2026-08-01 ficou para trás em três pontos. Serão corrigidos nela.

1. **Formato binário.** Ela descreve "uma seção por tipo de entidade" com "o
   deslocamento e o comprimento de cada seção no `meta.json`". O que a etapa 2
   construiu é o oposto: seções por **atributo**, com a tabela de deslocamentos
   dentro do próprio arquivo, que se descreve sozinho, e enchimento para toda
   seção começar em múltiplo de 4.

2. **Limiar do esqueleto.** Ela diz "um percentil dos `length_mm`". É um alvo de
   contagem com piso, sobre `length_um` inteiro, e os que empatam com o limiar
   entram só até o alvo encher.

3. **Prévia provisória.** Ela marca como parcial apenas a estimativa. Com dedup
   ligado, o **desenho** também é provisório até o detalhe chegar.

A lista de arquivos da spec geral ganha `formato.ts` e `estimativa.ts`.

## Fora de escopo desta etapa

- Tudo de conta, cota e registro — etapa 4
- Docker, Caddy e o deploy em si — etapa 5, embora o estágio de build do
  frontend seja desenhado aqui para que a etapa 5 só o encaixe
- Vetorização de PDF escaneado, saída em DWG, detecção automática de escala —
  fora de escopo do projeto
