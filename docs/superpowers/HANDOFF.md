# Handoff — versão web do PdfToDxf

Estado em 2026-08-03. Leia isto primeiro ao retomar em sessão nova.

## O projeto em uma frase

Transformar o PdfToDxf (app desktop Tkinter que converte plantas em PDF vetorial
para DXF em escala real) numa versão web pública, hospedada em VPS, com paridade
total de recursos. O app desktop continua existindo; as duas interfaces
compartilham o mesmo núcleo.

Documentos que governam o trabalho:

- **Especificação:** `docs/superpowers/specs/2026-08-01-pdftodxf-web-design.md`
- **Plano da etapa 1:** `docs/superpowers/plans/2026-08-01-nucleo-classify-select.md`
- **Plano da etapa 2:** `docs/superpowers/plans/2026-08-03-api-de-conversao.md`

O projeto está dividido em 5 etapas: **1** núcleo, **2** API de conversão,
**3** frontend, **4** contas/cotas/registros, **5** deploy. Cada etapa tem seu
próprio plano; só as etapas 1 e 2 foram planejadas até agora.

## Onde o código está

| Branch | Conteúdo | Situação |
|---|---|---|
| `main` | até o plano da etapa 1 | base |
| `nucleo-classify-select` | etapa 1 inteira + plano da etapa 2 | **pronta, não mesclada** |
| `api-de-conversao` | etapa 2, tarefas 1 a 3 | em andamento |

`api-de-conversao` sai de `nucleo-classify-select`, que sai de `main`. Nada foi
mesclado ainda.

## O que está pronto

### Etapa 1 — núcleo `classify`/`select` (branch `nucleo-classify-select`)

Seis tarefas, todas implementadas e revisadas, mais uma revisão final do branch
cujos quatro achados importantes foram corrigidos.

`pdftodxf/optimize.py` foi dividido em duas fases:

- `classify(entities) -> EntityAttrs` — cara, roda uma vez no servidor. Resume
  cada entidade em números: `kind`, `layer_id`, `is_fill`, `length_um`
  (micrômetros de papel, inteiro), `dup_group`, `byte_cost`.
- `select(attrs, opts) -> list[bool]` — trivial, só comparações. **Será
  reescrita em TypeScript na etapa 3.**

A ideia central: o julgamento caro — quais segmentos são duplicatas entre si —
é feito uma vez, em Python, e vira um inteiro (`dup_group`). Assim o TypeScript
não precisa reimplementar algoritmo nenhum e não pode divergir.

`apply_filters()` foi removida. O app desktop usa o mesmo caminho.

**`tests/casos_select.json` é o contrato** que a implementação TypeScript terá
que obedecer: 1024 casos com tabelas de etiquetas, combinações de opções, a
máscara esperada e o `bytes_esperado`. Gerado por
`tests/gerar_casos_select.py`, verificado por `tests/test_casos_select.py`.
Regenerar é determinístico — se o `git diff` sujar, o comportamento mudou.

### Etapa 2 — API de conversão (branch `api-de-conversao`)

| Tarefa | O que faz | Situação |
|---|---|---|
| 1 | `length_um` inteiro no núcleo | pronta, revisada |
| 2 | serviço, envio do PDF, armazenamento | pronta, revisada |
| 3 | fila de extração em processo separado | pronta, revisada |
| 4 | empacotamento binário da geometria | não começou |
| 5 | divisão esqueleto/detalhe + rotas | não começou |
| 6 | exportação com cache por combinação | não começou |
| 7 | limpeza por prazo e cota de disco | não começou |

Arquivos existentes: `web/api/{__init__,limits,storage,jobs,main}.py`,
`web/requirements.txt`, `tests/test_api_upload.py`, `tests/test_api_extracao.py`.

## O que está verificado

Rodados em 2026-08-03, todos passando com saída limpa:

```
./.venv/Scripts/python.exe tests/test_optimize.py
./.venv/Scripts/python.exe tests/test_roundtrip.py
./.venv/Scripts/python.exe tests/test_preview.py
./.venv/Scripts/python.exe tests/test_casos_select.py
./.venv/Scripts/python.exe tests/test_api_upload.py
./.venv/Scripts/python.exe tests/test_api_extracao.py
```

## O que falta — em ordem

1. **Conferência manual do app desktop.** Só um humano pode fazer. A etapa 1
   mexeu em `pdftodxf/gui.py` e nenhum teste exercita a integração do painel de
   exportação com o canvas.

   ```
   ./.venv/Scripts/python.exe main.py "Input/LAY-1028.26.00_REV 02-31-07-2026.pdf"
   ```

   Conferir: a planta aparece; **Calibrar (2 pontos)** mostra a escala na barra;
   **Exportar DXF…** abre o painel; marcar e desmarcar opções muda a contagem, a
   estimativa e a prévia; desligar um layer some com ele; salvar gera o arquivo;
   o DXF abre no CAD com as medidas certas.

2. **Tarefas 4 a 7 da etapa 2**, na ordem do plano.

3. **Mesclar a etapa 1** quando a conferência manual passar.

4. **Planejar as etapas 3, 4 e 5.**

A revisão da tarefa 3 já foi feita (commit de correções `122cc3e`). Achou dois
defeitos graves, ambos corrigidos com teste de regressão: o PDF original era
apagado assim que a fila esvaziava, o que tornava impossível extrair a página 2
de um documento de duas páginas; e `pedir_extracao` conferia o estado fora da
trava, então dois POSTs simultâneos para a mesma página submetiam dois workers
que disputavam o mesmo `cache.pickle`. A spec foi ajustada junto, porque quem
especificou o apagamento errado foi o plano. Detalhe em
`.superpowers/sdd/progress-etapa2.md`.

## Ambiente

- **`.venv` no projeto.** Use sempre `./.venv/Scripts/python.exe`, nunca
  `python`. Está no `.gitignore`.
- Núcleo: PyMuPDF, ezdxf, Pillow (`requirements.txt`, não muda).
- Serviço: FastAPI, uvicorn, python-multipart, httpx2 (`web/requirements.txt`).
- Versões instaladas: FastAPI 0.141.1, Starlette 1.3.1, uvicorn 0.52.1,
  httpx2 2.9.1, Python 3.13.2.
- **`httpx2` é legítimo**, não é typosquat: o Starlette 1.3 o declara no extra
  `full` e `starlette/testclient.py` faz `import httpx2 as httpx`. Verificado.
- **Sem pytest.** Os testes deste projeto são funções com `assert` e um bloco
  `if __name__ == "__main__":`. Mantenha o padrão.

## Dívida conhecida

Nada disso bloqueia; está registrado para não se perder.

- **O contrato congela o `select()`, não o `classify()`.** As tabelas do JSON são
  dado congelado, então mudar o `classify()` não quebra teste nenhum — muda
  silenciosamente o que o servidor manda, e prévia e DXF continuam concordando
  entre si, mas com o comportamento anterior. O controle hoje é de processo
  (regerar e conferir o diff), não de teste.
- **`EntityAttrs.kind` é lista de strings** e o laço quente do `select()` compara
  string por entidade. Em 3 milhões de entidades no navegador isso pesa. O
  formato binário da etapa 2 já grava código numérico; falta reconciliar.
- `"extraindo"` está no contrato de estado da página e nada o escreve: o
  processo pai é o dono do estado e não sabe a hora em que o worker pega o
  trabalho. Quem lê deve tratá-lo como "em andamento", igual a `"na_fila"`.
  Está documentado no topo de `web/api/jobs.py`.
- `web/api/main.py`: `criar_trabalho` fica fora do `try/except` que limpa o
  disco. Se a gravação da ficha falhar, a pasta do trabalho fica para trás.
- `web/api/storage.py`: `gravar_ficha` pode deixar um `.json.tmp` órfão se o
  `json.dump` falhar no meio.
- `tests/test_casos_select.py` já aponta os índices divergentes; a mensagem
  ficou boa, mas o `bytes_esperado` não aponta nada equivalente.

## Como o trabalho vem sendo feito

Processo que vale manter, porque pegou defeitos reais:

1. Um plano por etapa, escrito antes de qualquer código, com o código exato de
   cada passo e ciclo TDD explícito.
2. Execução tarefa a tarefa, cada uma num subagente com contexto limpo,
   recebendo só o seu brief.
3. Revisão por tarefa, num subagente separado, que recebe o brief, o relatório
   do implementador e o diff — e é instruído a **não confiar no relatório**.
4. Revisão final do branch inteiro num modelo mais capaz.
5. Achados menores vão para o ledger; importantes viram correção antes de seguir.

Os ledgers e briefs ficam em `.superpowers/sdd/` (ignorado pelo git, existe só
nesta máquina): `progress.md` para a etapa 1, `progress-etapa2.md` para a etapa 2,
e os briefs em `briefs/` e `briefs-etapa2/`.

**O que esse processo pegou** e um caminho direto não teria: geradores de teste
cuja grade de coordenadas era grande demais e quase não produzia duplicatas
(0 a 8 por amostra, uma amostra com nenhuma), deixando o algoritmo mais delicado
sem cobertura real; um par de coordenadas que não detectava a mudança do
arredondamento da chave; e três variantes erradas do `select()` que passavam no
contrato sem serem notadas.

## Regra do usuário

Perguntas sempre em múltipla escolha, com opções clicáveis, uma pergunta por
vez — inclusive para aprovar seções de plano ou esclarecer respostas genéricas.
