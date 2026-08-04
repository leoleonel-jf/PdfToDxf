# API de conversão — plano de implementação (etapa 2 de 5)

> **Para trabalhadores agênticos:** SUB-SKILL OBRIGATÓRIO: use
> superpowers:subagent-driven-development (recomendado) ou
> superpowers:executing-plans para executar este plano tarefa a tarefa. Os
> passos usam caixas de seleção (`- [ ]`) para acompanhamento.

**Objetivo:** um serviço HTTP que recebe um PDF, extrai uma página em processo
separado, entrega a geometria em binário (esqueleto primeiro, detalhe depois) e
devolve o DXF exportado — sem contas, sem cotas, sem interface.

**Arquitetura:** FastAPI sobre o núcleo da etapa 1. O upload vai para disco em
pedaços com teto de tamanho; a extração roda num `ProcessPoolExecutor` com
limites de memória e CPU; o resultado (`ExtractionResult` + `EntityAttrs`) fica
em cache no disco e é servido em duas partes binárias. A exportação reaproveita
esse cache e guarda cada combinação de opções pelo hash, para nunca gerar o
mesmo DXF duas vezes.

**Tecnologias:** Python 3.10+, FastAPI, uvicorn, PyMuPDF, ezdxf. Testes com
`fastapi.testclient.TestClient`, no mesmo estilo de `assert` + `if __name__` do
resto do projeto.

## Restrições globais

- Python 3.10+; a sintaxe `X | None` é usada no projeto e deve continuar.
- **O `requirements.txt` da raiz não muda.** O app desktop continua precisando
  só de PyMuPDF, ezdxf e Pillow. As dependências do serviço vivem em
  `web/requirements.txt`.
- **Sem pytest.** Os testes são funções com `assert` e um bloco
  `if __name__ == "__main__":` que as chama em sequência, rodados com
  `python tests/<arquivo>.py`. `TestClient` funciona nesse estilo.
- Docstrings, comentários e mensagens de commit em português.
- Coordenadas em pontos de papel (1 pt = 1/72"), Y para cima.
- A ordem original das entidades é significativa e nunca pode ser reordenada.
- **Tudo que o navegador precisa decidir é inteiro.** Nenhuma comparação do
  `select()` pode depender de ponto flutuante, porque o binário trafega
  coordenadas em `Float32Array` e o Python trabalha em float64.
- Nomes de arquivo e identificadores vindos do cliente nunca entram num caminho
  sem validação. `job_id` é hexadecimal de 32 caracteres; qualquer outra coisa é
  recusada antes de tocar o disco.
- Limites desta etapa: PDF até **100 MB**, teto de **3.000.000** de entidades por
  página, **4** extrações simultâneas, arquivos expirando em **4 horas**, cota de
  disco de **40 GB**. Os limites por plano de usuário (20 MB sem conta) são da
  etapa 4 — aqui vale só o teto técnico.
- O serviço roda em Linux (Docker) em produção e em Windows no desenvolvimento.
  Onde a plataforma mudar o comportamento, o código degrada explicitamente e diz
  o que não conseguiu aplicar — nunca finge que aplicou.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `pdftodxf/optimize.py` | `length_um` inteiro no lugar de `length_mm` | Modificar |
| `web/requirements.txt` | dependências só do serviço | Criar |
| `web/api/__init__.py` | pacote | Criar |
| `web/api/limits.py` | os tetos técnicos, num lugar só | Criar |
| `web/api/storage.py` | layout em disco, ciclo de vida e limpeza dos trabalhos | Criar |
| `web/api/jobs.py` | fila de extração em processo separado | Criar |
| `web/api/packing.py` | formato binário da geometria | Criar |
| `web/api/main.py` | rotas FastAPI | Criar |
| `tests/test_api_upload.py` | envio, teto de tamanho, PDF inválido | Criar |
| `tests/test_api_extracao.py` | fila, estados, teto de entidades, sem vetores | Criar |
| `tests/test_packing.py` | ida e volta do binário | Criar |
| `tests/test_api_geometria.py` | esqueleto + detalhe reproduzem a extração | Criar |
| `tests/test_api_export.py` | exportação e cache por combinação | Criar |
| `tests/test_storage.py` | expiração por prazo e cota de disco | Criar |

Cada módulo de `web/api/` tem uma responsabilidade e não importa os outros de
volta: `main` conhece todos, `jobs` conhece `storage` e `limits`, `packing` e
`storage` não conhecem ninguém de `web/`.

---

### Tarefa 1: `length_um` inteiro no núcleo

A revisão final da etapa 1 apontou o risco: o contrato guarda `length_mm` em
float64, mas o binário vai trafegar `Float32Array`. Um segmento perto do limiar
pode ser mantido no servidor e descartado no navegador, ou o contrário, e o teste
de paridade não pegaria — ele roda sobre o JSON, não sobre o binário.

A solução é tirar o ponto flutuante da decisão: o comprimento vira **inteiro em
micrômetros de papel**. Cabe folgado em `uint32` (4,29 km de papel) e é exato nas
duas linguagens.

**Arquivos:**
- Modificar: `pdftodxf/optimize.py`
- Modificar: `tests/test_optimize.py`
- Modificar: `tests/gerar_casos_select.py`
- Regenerar: `tests/casos_select.json`
- Modificar: `docs/superpowers/plans/2026-08-01-nucleo-classify-select.md`

**Interfaces:**
- Consome: `EntityAttrs`, `classify`, `select` da etapa 1
- Produz: `EntityAttrs.length_um: list[int]` no lugar de `length_mm: list[float]`;
  `select()` comparando inteiros; o contrato regenerado com o campo novo

- [ ] **Passo 1: escrever o teste que falha**

Em `tests/test_optimize.py`, substitua `test_classify_length_mm` inteira por:

```python
def test_classify_length_um():
    ents = [seg(0, 0, 1 / PT_TO_MM, 0), TextItem(text="x", position=(0, 0))]
    a = classify(ents)
    assert a.length_um[0] == 1000, a.length_um   # 1 mm = 1000 µm
    assert a.length_um[1] == 0
    print("OK: classify mede comprimento em µm inteiros")


def test_classify_length_um_arredonda_para_cima_no_meio():
    # meio micrômetro tem que subir, não cair para o par mais próximo:
    # o navegador usa Math.round, que arredonda .5 para cima
    ents = [seg(0, 0, 0.0025 / PT_TO_MM, 0)]     # 2,5 µm
    a = classify(ents)
    assert a.length_um[0] == 3, a.length_um
    print("OK: classify arredonda meio µm para cima")
```

E acrescente, depois de `test_select_micro`:

```python
def test_select_micro_limiar_exato():
    """Um segmento com exatamente o comprimento do limiar é mantido."""
    ents = [seg(0, 0, 2.0 / PT_TO_MM, 0)]        # exatamente 2 mm
    out = filtrar(ents, ExportOptions(min_len_mm=2.0))
    assert len(out) == 1, "o limiar é 'menor que', não 'menor ou igual'"
    out = filtrar(ents, ExportOptions(min_len_mm=2.001))
    assert len(out) == 0
    print("OK: select trata o limiar exato como mantido")
```

Troque as chamadas correspondentes no bloco `if __name__ == "__main__":`:
`test_classify_length_mm()` vira as duas novas, e acrescente
`test_select_micro_limiar_exato()`.

- [ ] **Passo 2: rodar e ver falhar**

```bash
python tests/test_optimize.py
```

Esperado: `AttributeError: 'EntityAttrs' object has no attribute 'length_um'`

- [ ] **Passo 3: implementar**

Em `pdftodxf/optimize.py`, na dataclass `EntityAttrs`, troque a linha do campo:

```python
    length_um: list[int] = field(default_factory=list)     # 0 fora de Segment
```

Em `classify()`, troque o cálculo do comprimento:

```python
        if name == "Segment":
            mm = math.hypot(e.p2[0] - e.p1[0], e.p2[1] - e.p1[1]) * PT_TO_MM
            length_um = int(mm * 1000.0 + 0.5)
```

e o `else` correspondente passa a usar `length_um = 0`. Renomeie o `append`:
`attrs.length_um.append(length_um)`.

O `int(x + 0.5)` é arredondamento para cima no meio, não o "para o par mais
próximo" do `round()` embutido. É o que o `Math.round` do JavaScript faz, e
comprimentos são sempre positivos.

Em `select()`, troque a comparação de comprimento por:

```python
        if attrs.kind[i] == "Segment":
            min_len_um = int(opts.min_len_mm * 1000.0 + 0.5)
            if min_len_um > 0 and attrs.length_um[i] < min_len_um:
                continue
```

Tire o cálculo de `min_len_um` de dentro do laço — ele é constante. Calcule-o
junto com `excluded`, antes do `for`, e deixe dentro do laço só a comparação.

Atualize a docstring de `select()` para dizer que a comparação de comprimento é
entre inteiros em micrômetros, e que o limiar é convertido uma vez com
arredondamento para cima no meio — é a frase que a etapa 3 vai ler para escrever
o `select.ts`.

- [ ] **Passo 4: rodar e ver passar**

```bash
python tests/test_optimize.py
```

Esperado: todas as linhas `OK:` e `Todos os testes de otimização passaram.`

- [ ] **Passo 5: atualizar o gerador do contrato**

Em `tests/gerar_casos_select.py`, troque `"length_mm": [round(v, 9) for v in attrs.length_mm]`
por `"length_um": attrs.length_um` — não precisa mais arredondar, já é inteiro.
Ajuste a tabela feita à mão do limiar, se ela nomear o campo. Na docstring do
arquivo, explique que `length_um` é inteiro em micrômetros de papel e que o
limiar do `select()` se converte com `Math.round(min_len_mm * 1000)`.

Em `tests/test_casos_select.py`, troque o nome do campo ao reconstruir a
`EntityAttrs`.

- [ ] **Passo 6: regenerar e conferir**

```bash
python tests/gerar_casos_select.py && python tests/test_casos_select.py
```

Esperado: o número de casos não muda; todos passam.

Confirme que a tabela do limiar continua cumprindo o papel: escreva num script
solto a variante errada de `select()` que reserva o grupo de duplicatas **antes**
de checar o comprimento, rode contra o contrato e confirme que ela ainda falha em
dezenas de casos. Se passar em todos, a mudança para inteiros quebrou a tabela —
ajuste os valores dela até voltar a pegar. Não acrescente essa variante a nenhum
arquivo do projeto.

- [ ] **Passo 7: sincronizar a documentação**

Em `docs/superpowers/plans/2026-08-01-nucleo-classify-select.md`, troque as
menções a `length_mm` nos blocos de código e nas descrições de interface por
`length_um`, com a explicação de micrômetros. O plano da etapa 1 é histórico, mas
descreve a interface que a etapa 3 vai consumir.

- [ ] **Passo 8: rodar a suíte inteira e commitar**

```bash
python tests/test_optimize.py && python tests/test_roundtrip.py && python tests/test_preview.py && python tests/test_casos_select.py
```

```bash
git add pdftodxf/optimize.py tests/ docs/
git commit -m "Troca length_mm por length_um inteiro para tirar float da decisao"
```

---

### Tarefa 2: esqueleto do serviço, envio e armazenamento

**Arquivos:**
- Criar: `web/requirements.txt`, `web/api/__init__.py`, `web/api/limits.py`,
  `web/api/storage.py`, `web/api/main.py`
- Testar: `tests/test_api_upload.py`

**Interfaces:**
- Produz: `limits.TETO_PDF_BYTES`, `limits.TETO_ENTIDADES`,
  `limits.PRAZO_SEGUNDOS`, `limits.COTA_DISCO_BYTES`, `limits.EXTRACOES_SIMULTANEAS`;
  `storage.raiz() -> Path`, `storage.novo_id() -> str`,
  `storage.validar_id(job_id) -> str`, `storage.pasta(job_id) -> Path`,
  `storage.pasta_pagina(job_id, pagina) -> Path`,
  `storage.criar_trabalho(job_id, nome, n_paginas, tamanho, agora=None) -> dict`,
  `storage.caminho_ficha(job_id) -> Path`,
  `storage.ler_ficha(job_id) -> dict | None`,
  `storage.gravar_ficha(job_id, ficha) -> None`; a app FastAPI em `main.app` com
  `POST /api/jobs` e `GET /api/jobs/{job_id}`

- [ ] **Passo 1: declarar as dependências do serviço**

Crie `web/requirements.txt`:

```
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9
```

Instale com `pip install -r web/requirements.txt`. O `requirements.txt` da raiz
não muda.

- [ ] **Passo 2: escrever o teste que falha**

Crie `tests/test_api_upload.py`:

```python
"""Envio do PDF: teto de tamanho, arquivo inválido e ficha do trabalho."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# a raiz dos dados tem que ser definida antes de importar o serviço
os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

from fastapi.testclient import TestClient

from tests.test_roundtrip import make_test_pdf
from web.api import limits
from web.api.main import app

cliente = TestClient(app)


def pdf_de_teste() -> bytes:
    caminho = os.path.join(tempfile.mkdtemp(), "planta.pdf")
    make_test_pdf(caminho)
    with open(caminho, "rb") as f:
        return f.read()


def test_envio_aceito():
    dados = pdf_de_teste()
    r = cliente.post("/api/jobs",
                     files={"arquivo": ("planta.pdf", dados, "application/pdf")})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert len(corpo["job_id"]) == 32
    assert corpo["n_paginas"] == 1, corpo
    assert corpo["nome"] == "planta.pdf"
    print("OK: envio aceito devolve ficha do trabalho")


def test_consulta_do_trabalho():
    dados = pdf_de_teste()
    job = cliente.post("/api/jobs",
                       files={"arquivo": ("planta.pdf", dados, "application/pdf")}).json()
    r = cliente.get(f"/api/jobs/{job['job_id']}")
    assert r.status_code == 200, r.text
    assert r.json()["n_paginas"] == 1
    print("OK: consulta devolve o trabalho")


def test_job_id_invalido_nao_toca_o_disco():
    for ruim in ("../etc", "..", "x" * 32, "a" * 31, "/absoluto"):
        r = cliente.get(f"/api/jobs/{ruim}")
        assert r.status_code in (400, 404), f"{ruim!r} devolveu {r.status_code}"
    print("OK: identificador inválido é recusado")


def test_arquivo_grande_demais():
    entulho = b"%PDF-1.4\n" + b"0" * (limits.TETO_PDF_BYTES + 1024)
    r = cliente.post("/api/jobs",
                     files={"arquivo": ("grande.pdf", entulho, "application/pdf")})
    assert r.status_code == 413, r.status_code
    assert "100" in r.json()["detail"], r.json()
    print("OK: arquivo acima do teto é recusado com 413")


def test_arquivo_que_nao_e_pdf():
    r = cliente.post("/api/jobs",
                     files={"arquivo": ("nao.pdf", b"isto nao e um pdf",
                                        "application/pdf")})
    assert r.status_code == 400, r.status_code
    print("OK: arquivo que não é PDF é recusado com 400")


def test_arquivo_grande_nao_fica_em_disco():
    """O teto é verificado durante a gravação, não depois: nenhum resto
    do envio recusado pode sobrar na pasta de dados."""
    from web.api import storage
    antes = set(p.name for p in storage.raiz().iterdir())
    entulho = b"%PDF-1.4\n" + b"0" * (limits.TETO_PDF_BYTES + 1024)
    cliente.post("/api/jobs",
                 files={"arquivo": ("grande.pdf", entulho, "application/pdf")})
    depois = set(p.name for p in storage.raiz().iterdir())
    assert antes == depois, f"sobrou lixo: {depois - antes}"
    print("OK: envio recusado não deixa resto em disco")


if __name__ == "__main__":
    test_envio_aceito()
    test_consulta_do_trabalho()
    test_job_id_invalido_nao_toca_o_disco()
    test_arquivo_grande_demais()
    test_arquivo_que_nao_e_pdf()
    test_arquivo_grande_nao_fica_em_disco()
    print("Todos os testes de envio passaram.")
```

- [ ] **Passo 3: rodar e ver falhar**

```bash
python tests/test_api_upload.py
```

Esperado: `ModuleNotFoundError: No module named 'web'`

- [ ] **Passo 4: implementar os limites**

Crie `web/api/__init__.py` vazio e `web/api/limits.py`:

```python
"""Tetos técnicos do serviço, num lugar só.

Estes valores valem para todo mundo. Os limites por plano de usuário — 20 MB
sem conta, 100 MB com conta — são da etapa 4 e moram em outro lugar.
"""

from __future__ import annotations

TETO_PDF_BYTES = 100 * 1024 * 1024      # 100 MB
TETO_ENTIDADES = 3_000_000              # por página
EXTRACOES_SIMULTANEAS = 4               # de 8 vCPU
PRAZO_SEGUNDOS = 4 * 60 * 60            # 4 horas
COTA_DISCO_BYTES = 40 * 1024 * 1024 * 1024   # 40 GB

# limites aplicados ao processo que extrai (só POSIX; ver jobs.py)
TETO_MEMORIA_WORKER_BYTES = 6 * 1024 * 1024 * 1024   # 6 GB
TETO_CPU_WORKER_SEGUNDOS = 300
```

- [ ] **Passo 5: implementar o armazenamento**

Crie `web/api/storage.py`:

```python
"""Layout em disco dos trabalhos e ciclo de vida dos arquivos.

    <raiz>/<job_id>/
        origem.pdf        apagado assim que a extração termina
        ficha.json        nome original, páginas, tamanho, hora de criação
        p<N>/             uma pasta por página extraída

`job_id` é hexadecimal de 32 caracteres. Nada que venha do cliente entra num
caminho sem passar por `validar_id`.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

_ID = re.compile(r"^[0-9a-f]{32}$")


def raiz() -> Path:
    """Pasta de dados, de `PDFTODXF_DADOS` ou `./dados`."""
    caminho = Path(os.environ.get("PDFTODXF_DADOS", "dados"))
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def validar_id(job_id: str) -> str:
    """Devolve o id se for válido; levanta ValueError se não for."""
    if not _ID.match(job_id or ""):
        raise ValueError("identificador de trabalho inválido")
    return job_id


def pasta(job_id: str) -> Path:
    return raiz() / validar_id(job_id)


def pasta_pagina(job_id: str, pagina: int) -> Path:
    if not isinstance(pagina, int) or pagina < 1 or pagina > 10_000:
        raise ValueError("número de página inválido")
    return pasta(job_id) / f"p{pagina}"


def novo_id() -> str:
    return uuid.uuid4().hex


def criar_trabalho(job_id: str, nome: str, n_paginas: int, tamanho: int,
                   agora: float | None = None) -> dict:
    """Grava a ficha do trabalho e devolve o que ela contém."""
    ficha = {
        "job_id": job_id,
        "nome": nome,
        "n_paginas": n_paginas,
        "tamanho": tamanho,
        "criado_em": time.time() if agora is None else agora,
        "paginas": {},
    }
    gravar_ficha(job_id, ficha)
    return ficha


def caminho_ficha(job_id: str) -> Path:
    return pasta(job_id) / "ficha.json"


def gravar_ficha(job_id: str, ficha: dict) -> None:
    p = caminho_ficha(job_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    temporario = p.with_suffix(".json.tmp")
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(ficha, f, ensure_ascii=False)
    os.replace(temporario, p)   # troca atômica: nunca deixa ficha pela metade


def ler_ficha(job_id: str) -> dict | None:
    p = caminho_ficha(job_id)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)
```

A gravação passa por um arquivo temporário e um `os.replace` porque a ficha é
lida pela rota de estado enquanto o worker a atualiza; sem isso um leitor pode
pegar um JSON truncado.

- [ ] **Passo 6: implementar as rotas**

Crie `web/api/main.py`:

```python
"""Rotas do serviço de conversão."""

from __future__ import annotations

import os
import shutil

import fitz
from fastapi import FastAPI, File, HTTPException, UploadFile

from . import limits, storage

PEDACO = 1024 * 1024   # 1 MB por leitura do envio

app = FastAPI(title="PdfToDxf", docs_url=None, redoc_url=None)


def _mb(n: int) -> int:
    return n // (1024 * 1024)


@app.post("/api/jobs")
async def enviar(arquivo: UploadFile = File(...)) -> dict:
    """Recebe o PDF, confere o teto de tamanho e conta as páginas."""
    job_id = storage.novo_id()
    destino = storage.pasta(job_id)
    destino.mkdir(parents=True, exist_ok=True)
    origem = destino / "origem.pdf"

    total = 0
    try:
        with open(origem, "wb") as saida:
            while True:
                pedaco = await arquivo.read(PEDACO)
                if not pedaco:
                    break
                total += len(pedaco)
                if total > limits.TETO_PDF_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"O arquivo passa de {_mb(limits.TETO_PDF_BYTES)} MB.")
                saida.write(pedaco)

        if total == 0:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")

        try:
            with fitz.open(origem) as doc:
                n_paginas = doc.page_count
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Não consegui abrir o arquivo como PDF.")
    except Exception:
        shutil.rmtree(destino, ignore_errors=True)
        raise

    nome = os.path.basename(arquivo.filename or "planta.pdf")
    ficha = storage.criar_trabalho(job_id, nome, n_paginas, total)
    return {"job_id": job_id, "n_paginas": n_paginas, "nome": ficha["nome"]}


@app.get("/api/jobs/{job_id}")
def consultar(job_id: str) -> dict:
    try:
        storage.validar_id(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identificador inválido.")
    ficha = storage.ler_ficha(job_id)
    if ficha is None:
        raise HTTPException(status_code=404, detail="Trabalho não encontrado.")
    return ficha
```

O `try`/`except` que apaga a pasta cobre as duas recusas — tamanho e formato — e
qualquer erro inesperado. Sem ele, um envio recusado deixaria o arquivo parcial
ocupando disco, que é exatamente o que o teto existe para impedir.

- [ ] **Passo 7: rodar e ver passar**

```bash
python tests/test_api_upload.py
```

Esperado: as seis linhas `OK:` e `Todos os testes de envio passaram.`

- [ ] **Passo 8: commit**

```bash
git add web/ tests/test_api_upload.py
git commit -m "Cria o servico com envio de PDF, teto de tamanho e ficha do trabalho"
```

---

### Tarefa 3: fila de extração em processo separado

**Arquivos:**
- Criar: `web/api/jobs.py`
- Modificar: `web/api/main.py`
- Testar: `tests/test_api_extracao.py`

**Interfaces:**
- Consome: `storage`, `limits`, `pdftodxf.extractor.extract_page`,
  `pdftodxf.optimize.classify`
- Produz: `jobs.pedir_extracao(job_id, pagina) -> dict` (estado da página),
  `jobs.estado(job_id, pagina) -> dict`, e as rotas
  `POST /api/jobs/{job_id}/pages/{n}` e `GET /api/jobs/{job_id}/pages/{n}`

O estado de uma página é um dicionário com `situacao` em
`"na_fila" | "extraindo" | "pronta" | "erro"`, e quando dá erro um campo `codigo`
em `"entidades_demais" | "sem_vetores" | "recurso" | "interno"` mais uma
`mensagem` em português.

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_api_extracao.py`:

```python
"""Extração de página: fila, estados e recusas."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

import fitz
from fastapi.testclient import TestClient

from tests.test_roundtrip import make_test_pdf
from web.api.main import app

cliente = TestClient(app)


def enviar(dados: bytes, nome: str = "planta.pdf") -> str:
    r = cliente.post("/api/jobs",
                     files={"arquivo": (nome, dados, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def bytes_do_pdf_vetorial() -> bytes:
    caminho = os.path.join(tempfile.mkdtemp(), "planta.pdf")
    make_test_pdf(caminho)
    with open(caminho, "rb") as f:
        return f.read()


def bytes_de_pdf_sem_vetores() -> bytes:
    """Uma página em branco: nenhum desenho, nenhum texto."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    caminho = os.path.join(tempfile.mkdtemp(), "branco.pdf")
    doc.save(caminho)
    doc.close()
    with open(caminho, "rb") as f:
        return f.read()


def esperar(job_id: str, pagina: int, limite: float = 60.0) -> dict:
    """Aguarda a página sair da fila. Devolve o estado final."""
    fim = time.time() + limite
    while time.time() < fim:
        estado = cliente.get(f"/api/jobs/{job_id}/pages/{pagina}").json()
        if estado["situacao"] in ("pronta", "erro"):
            return estado
        time.sleep(0.2)
    raise AssertionError(f"a página {pagina} não terminou em {limite}s")


def test_extracao_completa():
    job = enviar(bytes_do_pdf_vetorial())
    r = cliente.post(f"/api/jobs/{job}/pages/1")
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] in ("na_fila", "extraindo", "pronta")
    estado = esperar(job, 1)
    assert estado["situacao"] == "pronta", estado
    assert estado["n_entidades"] > 0
    assert "TEXTO" in estado["layers"], estado["layers"]
    print("OK: extração de página conclui e informa contagens")


def test_pdf_original_e_apagado():
    from web.api import storage
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    assert not (storage.pasta(job) / "origem.pdf").exists(), \
        "o PDF original deveria sumir depois da extração"
    print("OK: PDF original é apagado após a extração")


def test_pagina_inexistente():
    job = enviar(bytes_do_pdf_vetorial())
    r = cliente.post(f"/api/jobs/{job}/pages/99")
    assert r.status_code == 404, r.status_code
    print("OK: página fora do documento é recusada")


def test_pdf_sem_vetores():
    job = enviar(bytes_de_pdf_sem_vetores(), nome="branco.pdf")
    cliente.post(f"/api/jobs/{job}/pages/1")
    estado = esperar(job, 1)
    assert estado["situacao"] == "erro", estado
    assert estado["codigo"] == "sem_vetores", estado
    assert "vetorial" in estado["mensagem"].lower(), estado["mensagem"]
    print("OK: PDF sem vetores dá erro identificável")


def test_teto_de_entidades():
    """Com o teto rebaixado, a mesma planta passa a ser recusada."""
    from web.api import limits
    original = limits.TETO_ENTIDADES
    limits.TETO_ENTIDADES = 3
    try:
        job = enviar(bytes_do_pdf_vetorial())
        cliente.post(f"/api/jobs/{job}/pages/1")
        estado = esperar(job, 1)
        assert estado["situacao"] == "erro", estado
        assert estado["codigo"] == "entidades_demais", estado
    finally:
        limits.TETO_ENTIDADES = original
    print("OK: teto de entidades recusa a página com mensagem clara")


def test_pedir_duas_vezes_nao_duplica():
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    cliente.post(f"/api/jobs/{job}/pages/1")
    estado = esperar(job, 1)
    assert estado["situacao"] == "pronta", estado
    print("OK: pedir a mesma página duas vezes não duplica trabalho")


if __name__ == "__main__":
    test_extracao_completa()
    test_pdf_original_e_apagado()
    test_pagina_inexistente()
    test_pdf_sem_vetores()
    test_teto_de_entidades()
    test_pedir_duas_vezes_nao_duplica()
    print("Todos os testes de extração passaram.")
```

Repare que `test_teto_de_entidades` mexe em `limits.TETO_ENTIDADES` no processo
do teste. Para que isso chegue ao worker, o teto tem que ser **lido pelo processo
pai e passado como argumento** para a função que roda no processo filho — não
lido lá dentro. Isso também é o certo por projeto: o worker não decide política.

- [ ] **Passo 2: rodar e ver falhar**

```bash
python tests/test_api_extracao.py
```

Esperado: `404` na rota `POST /api/jobs/{job}/pages/1`, que ainda não existe.

- [ ] **Passo 3: implementar a fila**

Crie `web/api/jobs.py`:

```python
"""Fila de extração: cada página é extraída num processo separado.

Um `ProcessPoolExecutor` limita quantas extrações rodam ao mesmo tempo. Rodar
fora do processo do serviço é o que permite uma planta monstruosa morrer sozinha
sem levar o site junto: os limites de memória e de CPU são aplicados ao processo
filho.
"""

from __future__ import annotations

import json
import pickle
import sys
import threading
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import limits, storage   # a tarefa 5 acrescenta `packing` aqui


class SemVetores(Exception):
    """A página não tem geometria vetorial (PDF escaneado ou em branco)."""


class EntidadesDemais(Exception):
    """A página passa do teto de entidades.

    Os dois números vão em `args` porque esta exceção atravessa a fronteira de
    processo: o pickle padrão de exceção reconstrói o objeto chamando
    `cls(*args)`. Guardar só a mensagem formatada faria o `unpickle` estourar
    com "faltou argumento", e o erro real chegaria disfarçado de erro interno.
    """

    def __init__(self, quantas: int, teto: int):
        super().__init__(quantas, teto)
        self.quantas = quantas
        self.teto = teto

    def __str__(self) -> str:
        return f"{self.quantas} entidades, teto {self.teto}"


_pool: ProcessPoolExecutor | None = None


def pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=limits.EXTRACOES_SIMULTANEAS)
    return _pool


def _aplicar_limites(memoria: int, cpu: int) -> str:
    """Aplica limites de recurso ao processo atual. Devolve o que conseguiu.

    `resource` só existe em POSIX. Em Windows não há equivalente simples, e
    fingir que aplicou seria pior do que dizer que não aplicou: em produção o
    serviço roda em Linux dentro de contêiner, onde os limites valem.
    """
    try:
        import resource
    except ImportError:
        return "nenhum (plataforma sem resource)"
    resource.setrlimit(resource.RLIMIT_AS, (memoria, memoria))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    return f"memória {memoria} B, CPU {cpu} s"


def _extrair_no_worker(pdf: str, pagina: int, destino: str, teto_entidades: int,
                       teto_memoria: int, teto_cpu: int) -> dict:
    """Roda no processo filho: extrai, classifica e grava o cache.

    Recebe os tetos como argumento, e não os lê de `limits`, para que o processo
    pai continue sendo o único dono da política.
    """
    aplicados = _aplicar_limites(teto_memoria, teto_cpu)

    from pdftodxf.extractor import extract_page
    from pdftodxf.optimize import classify

    resultado = extract_page(pdf, page_number=pagina - 1)
    if not resultado.entities:
        raise SemVetores()
    if len(resultado.entities) > teto_entidades:
        raise EntidadesDemais(len(resultado.entities), teto_entidades)

    attrs = classify(resultado.entities)

    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / "cache.pickle", "wb") as f:
        pickle.dump({"resultado": resultado, "attrs": attrs}, f,
                    protocol=pickle.HIGHEST_PROTOCOL)

    return {
        "situacao": "pronta",
        "n_entidades": len(resultado.entities),
        "contagem": resultado.counts(),
        "layers": attrs.layers,
        "largura_pt": resultado.page_width,
        "altura_pt": resultado.page_height,
        "limites_aplicados": aplicados,
    }


_trava = threading.Lock()


def _gravar_estado(job_id: str, pagina: int, estado: dict) -> None:
    """Atualiza o estado de uma página dentro da ficha do trabalho.

    A trava é obrigatória: com 4 workers, dois callbacks podem entrar aqui ao
    mesmo tempo, e sem ela o segundo leria a ficha antes de o primeiro gravar —
    o estado de uma das páginas sumiria.
    """
    with _trava:
        ficha = storage.ler_ficha(job_id) or {}
        ficha.setdefault("paginas", {})[str(pagina)] = estado
        storage.gravar_ficha(job_id, ficha)


def _quando_terminar(job_id: str, pagina: int, futuro) -> None:
    try:
        estado = futuro.result()
    except SemVetores:
        estado = {"situacao": "erro", "codigo": "sem_vetores",
                  "mensagem": "Esta página não tem desenho vetorial. "
                              "Só funcionam PDFs gerados pelo CAD, não escaneados."}
    except EntidadesDemais as e:
        quantas = f"{e.quantas:,}".replace(",", ".")
        teto = f"{e.teto:,}".replace(",", ".")
        estado = {"situacao": "erro", "codigo": "entidades_demais",
                  "mensagem": f"A planta tem {quantas} elementos e o limite "
                              f"é {teto}."}
    except Exception as e:
        estado = {"situacao": "erro", "codigo": "recurso",
                  "mensagem": "Não consegui processar esta planta: ela passou do "
                              "limite de memória ou de tempo do servidor."}
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
    _gravar_estado(job_id, pagina, estado)
    _apagar_origem_se_ocioso(job_id)
```

O `except Exception` no fim é largo de propósito. Quando o worker morre por
`RLIMIT_AS` ou `RLIMIT_CPU`, o processo é derrubado pelo sistema e não levanta
exceção lá dentro — o que chega aqui é `BrokenProcessPool`, vindo do executor.
Separá-lo dos demais erros não mudaria nada para o usuário, e a mensagem é a
mesma. O que **não** pode acontecer é o erro ser engolido em silêncio, deixando a
página presa em `"extraindo"` para sempre; por isso o traço vai para o log.

Complete o módulo com:

```python
def _apagar_origem_se_ocioso(job_id: str) -> None:
    """Apaga o PDF original quando nenhuma página está mais na fila."""
    ficha = storage.ler_ficha(job_id)
    if not ficha:
        return
    pendentes = [p for p in ficha.get("paginas", {}).values()
                 if p.get("situacao") in ("na_fila", "extraindo")]
    if pendentes:
        return
    origem = storage.pasta(job_id) / "origem.pdf"
    if origem.exists():
        origem.unlink()


def estado(job_id: str, pagina: int) -> dict | None:
    ficha = storage.ler_ficha(job_id)
    if ficha is None:
        return None
    return ficha.get("paginas", {}).get(str(pagina))


def pedir_extracao(job_id: str, pagina: int) -> dict:
    """Enfileira a extração da página, se ela já não estiver em andamento."""
    atual = estado(job_id, pagina)
    if atual and atual.get("situacao") in ("na_fila", "extraindo", "pronta"):
        return atual

    inicial = {"situacao": "na_fila"}
    _gravar_estado(job_id, pagina, inicial)

    origem = storage.pasta(job_id) / "origem.pdf"
    destino = storage.pasta_pagina(job_id, pagina)
    futuro = pool().submit(
        _extrair_no_worker, str(origem), pagina, str(destino),
        limits.TETO_ENTIDADES, limits.TETO_MEMORIA_WORKER_BYTES,
        limits.TETO_CPU_WORKER_SEGUNDOS)
    futuro.add_done_callback(
        lambda f: _quando_terminar(job_id, pagina, f))
    return inicial
```

- [ ] **Passo 4: acrescentar as rotas**

Em `web/api/main.py`, importe `jobs` e acrescente:

```python
def _ficha_ou_404(job_id: str) -> dict:
    try:
        storage.validar_id(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identificador inválido.")
    ficha = storage.ler_ficha(job_id)
    if ficha is None:
        raise HTTPException(status_code=404, detail="Trabalho não encontrado.")
    return ficha


@app.post("/api/jobs/{job_id}/pages/{pagina}")
def extrair_pagina(job_id: str, pagina: int) -> dict:
    ficha = _ficha_ou_404(job_id)
    if pagina < 1 or pagina > ficha["n_paginas"]:
        raise HTTPException(
            status_code=404,
            detail=f"O documento tem {ficha['n_paginas']} página(s).")
    return jobs.pedir_extracao(job_id, pagina)


@app.get("/api/jobs/{job_id}/pages/{pagina}")
def estado_da_pagina(job_id: str, pagina: int) -> dict:
    _ficha_ou_404(job_id)
    atual = jobs.estado(job_id, pagina)
    if atual is None:
        raise HTTPException(status_code=404, detail="Página não solicitada.")
    return atual
```

Troque também a função `consultar` para usar `_ficha_ou_404`, eliminando a
repetição.

- [ ] **Passo 5: rodar e ver passar**

```bash
python tests/test_api_extracao.py
```

Esperado: as seis linhas `OK:` e `Todos os testes de extração passaram.`

No Windows, o campo `limites_aplicados` do estado vai dizer
`nenhum (plataforma sem resource)`. Isso é esperado e não falha nenhum teste.

- [ ] **Passo 6: commit**

```bash
git add web/api/jobs.py web/api/main.py tests/test_api_extracao.py
git commit -m "Extrai paginas em processo separado com tetos de recurso"
```

---

### Tarefa 4: formato binário da geometria

**Arquivos:**
- Criar: `web/api/packing.py`
- Testar: `tests/test_packing.py`

**Interfaces:**
- Consome: `pdftodxf.geometry`, `EntityAttrs`
- Produz: `packing.empacotar(resultado, attrs, indices) -> bytes` e
  `packing.desempacotar(dados) -> dict`

**O formato.** Tudo little-endian. O arquivo se descreve sozinho, para que o
leitor TypeScript da etapa 3 não precise de um segundo arquivo para saber onde
cada coisa começa:

```
 0  4 bytes   b"PDXF"
 4  uint32    versão do formato (1)
 8  uint32    n = quantidade de entidades nesta parte
12  uint32    s = quantidade de seções
16  s * 12    tabela de seções: tipo uint32, deslocamento uint32, tamanho uint32
...           os dados das seções, na ordem da tabela
```

Toda seção começa em deslocamento múltiplo de 4; quando a anterior não termina
redonda, entram zeros de enchimento entre as duas. O `tamanho` da tabela é o
real, sem o enchimento. Isso não é enfeite: `new Uint32Array(buffer, desloc, n)`
levanta `RangeError` se `desloc` não for múltiplo de 4, e as seções `kind` e
`is_fill` são uint8 — ocupam exatamente `n` bytes, então qualquer página cuja
contagem fuja da tabuada do 4 desalinharia tudo o que vem depois. Como o leitor
usa os deslocamentos da tabela, o enchimento é invisível para ele.

Seções, todas com `n` elementos exceto onde dito:

| Tipo | Nome | Formato | Conteúdo |
|---|---|---|---|
| 1 | `idx` | uint32 | índice da entidade na extração completa |
| 2 | `kind` | uint8 | 0 Segment · 1 Polyline · 2 Arc · 3 Bezier · 4 TextItem |
| 3 | `layer_id` | uint32 | índice na lista de layers do `meta.json` |
| 4 | `is_fill` | uint8 | 0 ou 1 |
| 5 | `length_um` | uint32 | comprimento em micrômetros de papel |
| 6 | `dup_group` | int32 | grupo de duplicatas; −1 fora de `Segment` |
| 7 | `byte_cost` | uint32 | custo estimado no DXF |
| 8 | `cor` | uint32 | `0xRRGGBB`, ou `0xFFFFFFFF` quando não há cor |
| 9 | `coord_off` | uint32, n+1 | onde cada entidade começa em `coords`, contado em floats |
| 10 | `coords` | float32 | as coordenadas, conforme o tipo |
| 11 | `texto_off` | uint32, n+1 | onde o texto de cada entidade começa em `texto`, em bytes |
| 12 | `texto` | bytes | UTF-8 concatenado |

Coordenadas por tipo, em `coords`:

- Segment: `x1 y1 x2 y2`
- Polyline: `fechada x1 y1 x2 y2 …` (o primeiro float é 0 ou 1)
- Arc: `cx cy raio ângulo_inicial ângulo_final`
- Bezier: `x0 y0 x1 y1 x2 y2 x3 y3`
- TextItem: `x y altura rotação largura`

`float32` guarda ~7 dígitos significativos. Numa folha de 5000 pt isso dá
precisão de meio milésimo de ponto — invisível na tela, e a exportação não usa
esses números: ela roda no servidor sobre o `float64` original.

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_packing.py`:

```python
"""Ida e volta do formato binário da geometria."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.extractor import ExtractionResult
from pdftodxf.geometry import Arc, Bezier, Polyline, Segment, TextItem
from pdftodxf.optimize import classify
from web.api import packing


def amostra() -> ExtractionResult:
    ents = [
        Segment(p1=(0.0, 0.0), p2=(30.0, 40.0), layer="PAREDES",
                color=(1.0, 0.0, 0.0)),
        Polyline(points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], closed=True,
                 layer="COTAS", is_fill=True),
        Arc(center=(5.0, 5.0), radius=2.0, start_angle=0.0, end_angle=90.0,
            layer="PAREDES"),
        Bezier(p0=(0.0, 0.0), p1=(1.0, 2.0), p2=(3.0, 4.0), p3=(5.0, 6.0),
               layer="COTAS"),
        TextItem(text="Sala de máquinas", position=(2.0, 3.0), height=4.0,
                 rotation=90.0, width=25.0, layer="TEXTO"),
    ]
    return ExtractionResult(entities=ents, page_width=595.0, page_height=842.0,
                            layers={"PAREDES", "COTAS", "TEXTO"})


def test_ida_e_volta_completa():
    r = amostra()
    a = classify(r.entities)
    dados = packing.empacotar(r, a, list(range(len(r.entities))))
    lido = packing.desempacotar(dados)

    assert lido["n"] == 5, lido["n"]
    assert lido["idx"] == [0, 1, 2, 3, 4]
    assert lido["kind"] == [0, 1, 2, 3, 4]
    assert lido["layer_id"] == a.layer_id
    assert lido["is_fill"] == [1 if v else 0 for v in a.is_fill]
    assert lido["length_um"] == a.length_um
    assert lido["dup_group"] == a.dup_group
    assert lido["byte_cost"] == a.byte_cost
    print("OK: atributos sobrevivem à ida e volta")


def test_coordenadas():
    r = amostra()
    a = classify(r.entities)
    lido = packing.desempacotar(packing.empacotar(r, a, list(range(5))))

    seg = lido["coords_de"](0)
    assert [round(v, 3) for v in seg] == [0.0, 0.0, 30.0, 40.0], seg
    poly = lido["coords_de"](1)
    assert poly[0] == 1.0, "primeiro float da polilinha é o 'fechada'"
    assert [round(v, 3) for v in poly[1:]] == [0.0, 0.0, 1.0, 0.0, 1.0, 1.0]
    arco = lido["coords_de"](2)
    assert [round(v, 3) for v in arco] == [5.0, 5.0, 2.0, 0.0, 90.0], arco
    texto = lido["coords_de"](4)
    assert [round(v, 3) for v in texto] == [2.0, 3.0, 4.0, 90.0, 25.0], texto
    print("OK: coordenadas de cada tipo saem na ordem certa")


def test_texto_e_cor():
    r = amostra()
    a = classify(r.entities)
    lido = packing.desempacotar(packing.empacotar(r, a, list(range(5))))

    assert lido["texto_de"](4) == "Sala de máquinas"
    assert lido["texto_de"](0) == ""
    assert lido["cor"][0] == 0xFF0000, hex(lido["cor"][0])
    assert lido["cor"][2] == 0xFFFFFFFF, hex(lido["cor"][2])
    print("OK: texto acentuado e cor sobrevivem")


def test_subconjunto_preserva_indice_global():
    r = amostra()
    a = classify(r.entities)
    lido = packing.desempacotar(packing.empacotar(r, a, [1, 3]))
    assert lido["n"] == 2
    assert lido["idx"] == [1, 3], lido["idx"]
    assert lido["kind"] == [1, 3]
    assert lido["texto_de"](0) == ""
    print("OK: parte com subconjunto guarda o índice global")


def test_cabecalho_rejeita_lixo():
    try:
        packing.desempacotar(b"NOPE" + b"\0" * 32)
    except ValueError:
        print("OK: cabeçalho inválido é recusado")
        return
    raise AssertionError("deveria ter recusado o cabeçalho")


if __name__ == "__main__":
    test_ida_e_volta_completa()
    test_coordenadas()
    test_texto_e_cor()
    test_subconjunto_preserva_indice_global()
    test_cabecalho_rejeita_lixo()
    print("Todos os testes de empacotamento passaram.")
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
python tests/test_packing.py
```

Esperado: `ImportError: cannot import name 'packing' from 'web.api'`

- [ ] **Passo 3: implementar**

Crie `web/api/packing.py`:

```python
"""Formato binário da geometria enviada ao navegador.

O arquivo se descreve sozinho: um cabeçalho com a tabela de seções e, em
seguida, os dados. O leitor TypeScript da etapa 3 monta as `TypedArray`
apontando direto para o buffer, sem copiar nada.

Tudo little-endian. Ver a tabela de seções no plano da etapa 2.
"""

from __future__ import annotations

import struct

MAGICO = b"PDXF"
VERSAO = 1

IDX, KIND, LAYER_ID, IS_FILL, LENGTH_UM = 1, 2, 3, 4, 5
DUP_GROUP, BYTE_COST, COR, COORD_OFF, COORDS = 6, 7, 8, 9, 10
TEXTO_OFF, TEXTO = 11, 12

SEM_COR = 0xFFFFFFFF

_CODIGO_TIPO = {"Segment": 0, "Polyline": 1, "Arc": 2, "Bezier": 3,
                "TextItem": 4}


def _cor_para_inteiro(rgb) -> int:
    if rgb is None:
        return SEM_COR
    r, g, b = (max(0, min(255, int(c * 255 + 0.5))) for c in rgb)
    return (r << 16) | (g << 8) | b


def _coordenadas(e) -> list[float]:
    nome = type(e).__name__
    if nome == "Segment":
        return [e.p1[0], e.p1[1], e.p2[0], e.p2[1]]
    if nome == "Polyline":
        saida = [1.0 if e.closed else 0.0]
        for x, y in e.points:
            saida.append(x)
            saida.append(y)
        return saida
    if nome == "Arc":
        return [e.center[0], e.center[1], e.radius, e.start_angle, e.end_angle]
    if nome == "Bezier":
        return [e.p0[0], e.p0[1], e.p1[0], e.p1[1],
                e.p2[0], e.p2[1], e.p3[0], e.p3[1]]
    if nome == "TextItem":
        return [e.position[0], e.position[1], e.height, e.rotation, e.width]
    raise ValueError(f"tipo de entidade desconhecido: {nome}")


def empacotar(resultado, attrs, indices: list[int]) -> bytes:
    """Monta o binário com as entidades de `indices`, nessa ordem.

    `indices` são posições na lista completa de entidades da extração. Elas vão
    gravadas na seção `idx` para que o navegador possa reunir esqueleto e
    detalhe sem ambiguidade.
    """
    n = len(indices)
    idx, kind, layer_id, is_fill = [], [], [], []
    length_um, dup_group, byte_cost, cor = [], [], [], []
    coords: list[float] = []
    coord_off = [0]
    texto = bytearray()
    texto_off = [0]

    for i in indices:
        e = resultado.entities[i]
        idx.append(i)
        kind.append(_CODIGO_TIPO[attrs.kind[i]])
        layer_id.append(attrs.layer_id[i])
        is_fill.append(1 if attrs.is_fill[i] else 0)
        length_um.append(attrs.length_um[i])
        dup_group.append(attrs.dup_group[i])
        byte_cost.append(attrs.byte_cost[i])
        cor.append(_cor_para_inteiro(e.color))

        coords.extend(_coordenadas(e))
        coord_off.append(len(coords))

        if attrs.kind[i] == "TextItem":
            texto.extend(e.text.encode("utf-8"))
        texto_off.append(len(texto))

    secoes = [
        (IDX, struct.pack(f"<{n}I", *idx)),
        (KIND, struct.pack(f"<{n}B", *kind)),
        (LAYER_ID, struct.pack(f"<{n}I", *layer_id)),
        (IS_FILL, struct.pack(f"<{n}B", *is_fill)),
        (LENGTH_UM, struct.pack(f"<{n}I", *length_um)),
        (DUP_GROUP, struct.pack(f"<{n}i", *dup_group)),
        (BYTE_COST, struct.pack(f"<{n}I", *byte_cost)),
        (COR, struct.pack(f"<{n}I", *cor)),
        (COORD_OFF, struct.pack(f"<{n + 1}I", *coord_off)),
        (COORDS, struct.pack(f"<{len(coords)}f", *coords)),
        (TEXTO_OFF, struct.pack(f"<{n + 1}I", *texto_off)),
        (TEXTO, bytes(texto)),
    ]

    cabecalho = bytearray()
    cabecalho += MAGICO
    cabecalho += struct.pack("<III", VERSAO, n, len(secoes))
    inicio_dados = len(cabecalho) + 12 * len(secoes)

    tabela = bytearray()
    deslocamento = inicio_dados
    for tipo, dados in secoes:
        tabela += struct.pack("<III", tipo, deslocamento, len(dados))
        deslocamento += len(dados)

    saida = bytearray()
    saida += cabecalho
    saida += tabela
    for _, dados in secoes:
        saida += dados
    return bytes(saida)


def desempacotar(dados: bytes) -> dict:
    """Lê o binário de volta. Existe para os testes: em produção quem lê é o TS."""
    if len(dados) < 16 or dados[:4] != MAGICO:
        raise ValueError("não é um arquivo de geometria do PdfToDxf")
    versao, n, s = struct.unpack_from("<III", dados, 4)
    if versao != VERSAO:
        raise ValueError(f"versão {versao} desconhecida")

    tabela = {}
    for k in range(s):
        tipo, desloc, tamanho = struct.unpack_from("<III", dados, 16 + 12 * k)
        tabela[tipo] = (desloc, tamanho)

    def inteiros(tipo, formato, quantos):
        desloc, _ = tabela[tipo]
        return list(struct.unpack_from(f"<{quantos}{formato}", dados, desloc))

    coord_off = inteiros(COORD_OFF, "I", n + 1)
    texto_off = inteiros(TEXTO_OFF, "I", n + 1)
    desloc_coords, tam_coords = tabela[COORDS]
    coords = list(struct.unpack_from(f"<{tam_coords // 4}f", dados,
                                     desloc_coords))
    desloc_texto, tam_texto = tabela[TEXTO]
    blob = dados[desloc_texto:desloc_texto + tam_texto]

    return {
        "n": n,
        "idx": inteiros(IDX, "I", n),
        "kind": inteiros(KIND, "B", n),
        "layer_id": inteiros(LAYER_ID, "I", n),
        "is_fill": inteiros(IS_FILL, "B", n),
        "length_um": inteiros(LENGTH_UM, "I", n),
        "dup_group": inteiros(DUP_GROUP, "i", n),
        "byte_cost": inteiros(BYTE_COST, "I", n),
        "cor": inteiros(COR, "I", n),
        "coords_de": lambda i: coords[coord_off[i]:coord_off[i + 1]],
        "texto_de": lambda i: blob[texto_off[i]:texto_off[i + 1]].decode("utf-8"),
    }
```

- [ ] **Passo 4: rodar e ver passar**

```bash
python tests/test_packing.py
```

Esperado: as cinco linhas `OK:` e `Todos os testes de empacotamento passaram.`

- [ ] **Passo 5: commit**

```bash
git add web/api/packing.py tests/test_packing.py
git commit -m "Cria o formato binario da geometria com tabela de secoes"
```

---

### Tarefa 5: divisão em esqueleto e detalhe, e as rotas de geometria

**Arquivos:**
- Modificar: `web/api/packing.py` (acrescenta a divisão)
- Modificar: `web/api/jobs.py` (grava as duas partes e o `meta.json`)
- Modificar: `web/api/main.py` (duas rotas)
- Testar: `tests/test_api_geometria.py`

**Interfaces:**
- Produz: `packing.dividir(attrs, alvo) -> tuple[list[int], list[int], int]`
  devolvendo `(esqueleto, detalhe, limiar_um)`; as rotas
  `GET /api/jobs/{job_id}/pages/{n}/geometry.bin?parte=esqueleto|detalhe` e
  `GET /api/jobs/{job_id}/pages/{n}/meta.json`

**A regra da divisão.** O esqueleto tem tudo que não é `Segment` (textos, arcos,
polilinhas, curvas — poucos e estruturais) mais os segmentos mais longos, até
chegar perto do alvo. O alvo é `max(20_000, n // 20)`, ou seja 5% das entidades
com um piso. Se a página inteira couber no alvo, não há divisão: tudo vai no
esqueleto e o detalhe fica vazio. O mesmo vale para uma página sem segmento
nenhum — só polilinhas e texto, como uma planta de hachura pesada: a regra só
sabe cortar por comprimento de segmento, então não há o que mandar ao detalhe.

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_api_geometria.py`:

```python
"""Divisão em esqueleto e detalhe, e as rotas que servem as duas partes."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

from fastapi.testclient import TestClient

from pdftodxf.geometry import Segment, TextItem
from pdftodxf.optimize import classify
from tests.test_api_extracao import bytes_do_pdf_vetorial, enviar, esperar
from web.api import packing
from web.api.main import app

cliente = TestClient(app)


def test_divisao_cobre_tudo_sem_repetir():
    ents = [Segment(p1=(0.0, 0.0), p2=(float(i % 50 + 1), 0.0))
            for i in range(1000)]
    ents.append(TextItem(text="x", position=(0.0, 0.0)))
    a = classify(ents)
    esqueleto, detalhe, limiar = packing.dividir(a, alvo=100)

    assert set(esqueleto) & set(detalhe) == set(), "entidade em duas partes"
    assert sorted(esqueleto + detalhe) == list(range(len(ents))), \
        "juntas, as partes têm que dar a lista inteira"
    assert esqueleto == sorted(esqueleto), "o esqueleto perdeu a ordem original"
    assert detalhe == sorted(detalhe), "o detalhe perdeu a ordem original"
    assert len(ents) - 1 in esqueleto, "o texto tem que estar no esqueleto"
    assert limiar > 0
    print("OK: divisão cobre tudo, sem repetir e sem reordenar")


def test_pagina_pequena_nao_divide():
    ents = [Segment(p1=(0.0, 0.0), p2=(1.0, 0.0)) for _ in range(10)]
    a = classify(ents)
    esqueleto, detalhe, limiar = packing.dividir(a, alvo=100)
    assert len(esqueleto) == 10 and detalhe == []
    assert limiar == 0, "sem divisão, não há limiar"
    print("OK: página pequena vai inteira no esqueleto")


def test_esqueleto_fica_com_os_segmentos_mais_longos():
    ents = [Segment(p1=(0.0, 0.0), p2=(float(i + 1), 0.0)) for i in range(100)]
    a = classify(ents)
    esqueleto, detalhe, limiar = packing.dividir(a, alvo=10)
    assert all(a.length_um[i] >= limiar for i in esqueleto)
    assert all(a.length_um[i] < limiar for i in detalhe)
    print("OK: o esqueleto fica com os segmentos mais longos")


def test_rotas_servem_as_duas_partes():
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)

    meta = cliente.get(f"/api/jobs/{job}/pages/1/meta.json")
    assert meta.status_code == 200, meta.text
    m = meta.json()
    assert m["n_entidades"] > 0
    assert m["largura_pt"] > 0 and m["altura_pt"] > 0
    assert isinstance(m["layers"], list) and m["layers"]
    assert m["partes"]["esqueleto"] + m["partes"]["detalhe"] == m["n_entidades"]

    esq = cliente.get(f"/api/jobs/{job}/pages/1/geometry.bin?parte=esqueleto")
    assert esq.status_code == 200
    assert esq.headers["content-type"] == "application/octet-stream"
    lido = packing.desempacotar(esq.content)
    assert lido["n"] == m["partes"]["esqueleto"]

    det = cliente.get(f"/api/jobs/{job}/pages/1/geometry.bin?parte=detalhe")
    assert det.status_code == 200
    lido_det = packing.desempacotar(det.content)
    assert lido_det["n"] == m["partes"]["detalhe"]

    juntos = sorted(lido["idx"] + lido_det["idx"])
    assert juntos == list(range(m["n_entidades"])), \
        "esqueleto + detalhe não reproduzem a extração"
    print("OK: as rotas servem as duas partes e juntas reproduzem tudo")


def test_parte_invalida():
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    r = cliente.get(f"/api/jobs/{job}/pages/1/geometry.bin?parte=inventada")
    assert r.status_code == 400, r.status_code
    print("OK: parte desconhecida é recusada")


if __name__ == "__main__":
    test_divisao_cobre_tudo_sem_repetir()
    test_pagina_pequena_nao_divide()
    test_esqueleto_fica_com_os_segmentos_mais_longos()
    test_rotas_servem_as_duas_partes()
    test_parte_invalida()
    print("Todos os testes de geometria passaram.")
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
python tests/test_api_geometria.py
```

Esperado: `AttributeError: module 'web.api.packing' has no attribute 'dividir'`

- [ ] **Passo 3: implementar a divisão**

Acrescente a `web/api/packing.py`:

```python
ALVO_MINIMO = 20_000
FRACAO_ESQUELETO = 20   # 1/20 = 5% das entidades


def alvo_padrao(n: int) -> int:
    return max(ALVO_MINIMO, n // FRACAO_ESQUELETO)


def dividir(attrs, alvo: int | None = None) -> tuple[list[int], list[int], int]:
    """Separa as entidades em esqueleto e detalhe.

    O esqueleto leva tudo que não é `Segment` — textos, arcos, polilinhas e
    curvas, que são poucos e dão a leitura do desenho — mais os segmentos mais
    longos, até chegar perto do alvo. Devolve `(esqueleto, detalhe, limiar_um)`,
    com as duas listas em ordem original e o limiar de comprimento usado.

    Quando a página inteira cabe no alvo, não há divisão: tudo vai no esqueleto,
    o detalhe volta vazio e o limiar é 0.
    """
    n = len(attrs)
    if alvo is None:
        alvo = alvo_padrao(n)
    if n <= alvo:
        return list(range(n)), [], 0

    segmentos = [i for i in range(n) if attrs.kind[i] == "Segment"]
    outros = n - len(segmentos)
    vagas = alvo - outros
    if vagas <= 0:
        # há mais não-segmentos que o alvo: o esqueleto é só eles
        limiar = max(attrs.length_um[i] for i in segmentos) + 1
    else:
        ordenados = sorted((attrs.length_um[i] for i in segmentos), reverse=True)
        if vagas >= len(ordenados):
            return list(range(n)), [], 0
        limiar = ordenados[vagas - 1]

    esqueleto, detalhe = [], []
    for i in range(n):
        if attrs.kind[i] != "Segment" or attrs.length_um[i] >= limiar:
            esqueleto.append(i)
        else:
            detalhe.append(i)
    return esqueleto, detalhe, limiar
```

O limiar é o comprimento do último segmento que coube, e a comparação é
`>=` — então empates entram todos no esqueleto, que pode passar um pouco do
alvo. Passar um pouco é melhor do que cortar arbitrariamente no meio de um
empate: a divisão fica determinística e não depende da ordem do `sorted`.

- [ ] **Passo 4: gravar as partes na extração**

Em `web/api/jobs.py`, dentro de `_extrair_no_worker`, depois de gravar o
`cache.pickle`, acrescente:

Acrescente `packing` à linha de import do topo do módulo
(`from . import limits, packing, storage`) e, dentro do worker:

```python
    esqueleto, detalhe, limiar = packing.dividir(attrs)
    with open(pasta / "esqueleto.bin", "wb") as f:
        f.write(packing.empacotar(resultado, attrs, esqueleto))
    with open(pasta / "detalhe.bin", "wb") as f:
        f.write(packing.empacotar(resultado, attrs, detalhe))

    meta = {
        "pagina": pagina,
        "n_entidades": len(resultado.entities),
        "contagem": resultado.counts(),
        "layers": attrs.layers,
        "largura_pt": resultado.page_width,
        "altura_pt": resultado.page_height,
        "limiar_esqueleto_um": limiar,
        "partes": {"esqueleto": len(esqueleto), "detalhe": len(detalhe)},
    }
    with open(pasta / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
```

e faça o `return` do worker devolver `{"situacao": "pronta", **meta,
"limites_aplicados": aplicados}`, eliminando a duplicação de campos que existia
antes.

- [ ] **Passo 5: acrescentar as rotas**

Em `web/api/main.py`:

```python
from fastapi.responses import FileResponse, JSONResponse


def _pagina_pronta(job_id: str, pagina: int):
    _ficha_ou_404(job_id)
    atual = jobs.estado(job_id, pagina)
    if atual is None:
        raise HTTPException(status_code=404, detail="Página não solicitada.")
    if atual.get("situacao") != "pronta":
        raise HTTPException(status_code=409,
                            detail="A página ainda não está pronta.")
    return storage.pasta_pagina(job_id, pagina)


@app.get("/api/jobs/{job_id}/pages/{pagina}/meta.json")
def meta_da_pagina(job_id: str, pagina: int) -> JSONResponse:
    caminho = _pagina_pronta(job_id, pagina) / "meta.json"
    return FileResponse(caminho, media_type="application/json")


@app.get("/api/jobs/{job_id}/pages/{pagina}/geometry.bin")
def geometria(job_id: str, pagina: int, parte: str = "esqueleto") -> FileResponse:
    if parte not in ("esqueleto", "detalhe"):
        raise HTTPException(status_code=400,
                            detail="A parte tem que ser 'esqueleto' ou 'detalhe'.")
    caminho = _pagina_pronta(job_id, pagina) / f"{parte}.bin"
    return FileResponse(caminho, media_type="application/octet-stream")
```

- [ ] **Passo 6: rodar e ver passar**

```bash
python tests/test_api_geometria.py
```

Esperado: as cinco linhas `OK:` e `Todos os testes de geometria passaram.`

- [ ] **Passo 7: commit**

```bash
git add web/api/ tests/test_api_geometria.py
git commit -m "Divide a geometria em esqueleto e detalhe e serve as duas partes"
```

---

### Tarefa 6: exportação do DXF com cache por combinação

**Arquivos:**
- Criar: `web/api/exportacao.py`
- Modificar: `web/api/main.py`
- Testar: `tests/test_api_export.py`

**Interfaces:**
- Consome: `pdftodxf.dxf_writer.export_dxf` (que desde a etapa 1 aceita
  `attrs` pronto), o `cache.pickle` gravado pelo worker
- Produz: `exportacao.chave(pagina, escala, unidade, opcoes) -> str`,
  `exportacao.caminho_do_dxf(job_id, pagina, chave) -> Path`,
  `exportacao.gerar(job_id, pagina, escala, unidade, opcoes) ->
  tuple[str, Path, bool, int]` — a chave, o caminho, se veio do cache e quantas
  entidades foram escritas; as rotas
  `POST /api/jobs/{job_id}/pages/{n}/export` e
  `GET /api/download/{job_id}/{chave}`

A chave é o SHA-256 de um JSON canônico do pedido. Duas exportações com a mesma
página, escala, unidade e opções produzem a mesma chave, e a segunda devolve o
arquivo já gerado. É isso que, na etapa 4, vai permitir repetir um download sem
gastar cota.

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_api_export.py`:

```python
"""Exportação do DXF e o cache por combinação de opções."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

import ezdxf
from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial, enviar, esperar
from web.api.main import app

cliente = TestClient(app)

PEDIDO = {
    "escala": 0.01,
    "unidade": "m",
    "opcoes": {
        "excluded_layers": [],
        "drop_fills": False,
        "min_len_mm": 0.0,
        "dedup": False,
        "join_polylines": False,
        "round_coords": False,
    },
}


def preparar() -> str:
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    return job


def test_exportacao_gera_dxf_valido():
    job = preparar()
    r = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["cache"] is False
    assert corpo["entidades"] > 0

    baixado = cliente.get(corpo["url"])
    assert baixado.status_code == 200, baixado.text
    assert baixado.headers["content-type"] == "application/dxf"

    caminho = os.path.join(tempfile.mkdtemp(), "saida.dxf")
    with open(caminho, "wb") as f:
        f.write(baixado.content)
    doc = ezdxf.readfile(caminho)
    assert not doc.audit().has_errors
    assert doc.header["$INSUNITS"] == 6, "unidade metros"
    print("OK: exportação gera um DXF válido em metros")


def test_mesma_combinacao_reaproveita():
    job = preparar()
    primeiro = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO).json()
    segundo = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO).json()
    assert primeiro["url"] == segundo["url"]
    assert segundo["cache"] is True, "a segunda vez tinha que vir do cache"
    print("OK: repetir a mesma combinação reaproveita o arquivo")


def test_combinacao_diferente_gera_outro():
    job = preparar()
    a = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO).json()
    outro = {**PEDIDO, "opcoes": {**PEDIDO["opcoes"], "dedup": True}}
    b = cliente.post(f"/api/jobs/{job}/pages/1/export", json=outro).json()
    assert a["url"] != b["url"], "opções diferentes têm que dar chaves diferentes"
    assert b["cache"] is False
    print("OK: combinação diferente gera arquivo novo")


def test_ordem_dos_layers_nao_muda_a_chave():
    job = preparar()
    um = {**PEDIDO, "opcoes": {**PEDIDO["opcoes"],
                               "excluded_layers": ["TEXTO", "COR_FF0000"]}}
    dois = {**PEDIDO, "opcoes": {**PEDIDO["opcoes"],
                                 "excluded_layers": ["COR_FF0000", "TEXTO"]}}
    a = cliente.post(f"/api/jobs/{job}/pages/1/export", json=um).json()
    b = cliente.post(f"/api/jobs/{job}/pages/1/export", json=dois).json()
    assert a["url"] == b["url"], "a chave não pode depender da ordem da lista"
    assert b["cache"] is True
    print("OK: a chave não depende da ordem dos layers excluídos")


def test_pedido_invalido():
    job = preparar()
    ruim = {**PEDIDO, "unidade": "polegadas"}
    r = cliente.post(f"/api/jobs/{job}/pages/1/export", json=ruim)
    assert r.status_code == 422, r.status_code
    ruim = {**PEDIDO, "escala": 0.0}
    r = cliente.post(f"/api/jobs/{job}/pages/1/export", json=ruim)
    assert r.status_code == 422, r.status_code
    print("OK: pedido inválido é recusado antes de gerar")


def test_download_com_chave_inventada():
    job = preparar()
    r = cliente.get(f"/api/download/{job}/{'a' * 64}")
    assert r.status_code == 404, r.status_code
    r = cliente.get(f"/api/download/{job}/../../etc/passwd")
    assert r.status_code in (400, 404), r.status_code
    print("OK: chave inventada ou maliciosa não entrega arquivo")


if __name__ == "__main__":
    test_exportacao_gera_dxf_valido()
    test_mesma_combinacao_reaproveita()
    test_combinacao_diferente_gera_outro()
    test_ordem_dos_layers_nao_muda_a_chave()
    test_pedido_invalido()
    test_download_com_chave_inventada()
    print("Todos os testes de exportação passaram.")
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
python tests/test_api_export.py
```

Esperado: `404` na rota de exportação, que ainda não existe.

- [ ] **Passo 3: implementar**

Crie `web/api/exportacao.py`:

```python
"""Geração do DXF a partir do cache da extração, com reaproveitamento.

Cada combinação de página, escala, unidade e opções vira uma chave. O arquivo
gerado fica guardado sob essa chave, então pedir a mesma combinação de novo não
gera nada — só devolve o que já existe. Na etapa 4 é isso que vai permitir
repetir um download sem gastar cota.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

from pdftodxf.dxf_writer import export_dxf
from pdftodxf.optimize import ExportOptions

from . import storage

UNIDADES = ("mm", "cm", "m")


def chave(pagina: int, escala: float, unidade: str, opcoes: dict) -> str:
    """SHA-256 de um JSON canônico do pedido.

    Os layers excluídos são ordenados: quem exclui A e B tem que cair na mesma
    chave de quem exclui B e A.
    """
    canonico = {
        "pagina": pagina,
        "escala": repr(float(escala)),
        "unidade": unidade,
        "excluded_layers": sorted(opcoes.get("excluded_layers", [])),
        "drop_fills": bool(opcoes.get("drop_fills", False)),
        "min_len_mm": repr(float(opcoes.get("min_len_mm", 0.0))),
        "dedup": bool(opcoes.get("dedup", False)),
        "join_polylines": bool(opcoes.get("join_polylines", False)),
        "round_coords": bool(opcoes.get("round_coords", False)),
    }
    texto = json.dumps(canonico, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def pasta_export(job_id: str, pagina: int) -> Path:
    p = storage.pasta_pagina(job_id, pagina) / "export"
    p.mkdir(parents=True, exist_ok=True)
    return p


def caminho_do_dxf(job_id: str, pagina: int, ch: str) -> Path:
    if len(ch) != 64 or any(c not in "0123456789abcdef" for c in ch):
        raise ValueError("chave inválida")
    return pasta_export(job_id, pagina) / f"{ch}.dxf"


def gerar(job_id: str, pagina: int, escala: float, unidade: str,
          opcoes: dict) -> tuple[str, Path, bool, int]:
    """Devolve `(chave, caminho, veio_do_cache, entidades_escritas)`."""
    ch = chave(pagina, escala, unidade, opcoes)
    destino = caminho_do_dxf(job_id, pagina, ch)
    if destino.exists():
        return ch, destino, True, _contar(destino)

    cache = storage.pasta_pagina(job_id, pagina) / "cache.pickle"
    with open(cache, "rb") as f:
        guardado = pickle.load(f)

    opts = ExportOptions(
        excluded_layers=set(opcoes.get("excluded_layers", [])),
        drop_fills=bool(opcoes.get("drop_fills", False)),
        min_len_mm=float(opcoes.get("min_len_mm", 0.0)),
        dedup=bool(opcoes.get("dedup", False)),
        join_polylines=bool(opcoes.get("join_polylines", False)),
        round_coords=bool(opcoes.get("round_coords", False)),
    )
    contagem = export_dxf(guardado["resultado"], str(destino), escala, unidade,
                          opts, attrs=guardado["attrs"])
    _gravar_contagem(destino, contagem)
    return ch, destino, False, sum(contagem.values())


def _arquivo_de_contagem(dxf: Path) -> Path:
    return dxf.with_suffix(".contagem.json")


def _gravar_contagem(dxf: Path, contagem: dict) -> None:
    with open(_arquivo_de_contagem(dxf), "w", encoding="utf-8") as f:
        json.dump(contagem, f)


def _contar(dxf: Path) -> int:
    arquivo = _arquivo_de_contagem(dxf)
    if not arquivo.exists():
        return 0
    with open(arquivo, encoding="utf-8") as f:
        return sum(json.load(f).values())
```

O `repr(float(...))` na chave é de propósito: `0.01` e `0.010` viram a mesma
string, e `1e-2` também, então pedidos equivalentes não geram arquivos
duplicados. Usar o float direto no JSON daria o mesmo resultado, mas depender da
formatação de float do `json` é frágil — `repr` é estável e documentado.

Em `web/api/main.py`, acrescente o modelo do pedido e as rotas:

```python
from pydantic import BaseModel, Field

from . import exportacao


class Opcoes(BaseModel):
    excluded_layers: list[str] = Field(default_factory=list)
    drop_fills: bool = False
    min_len_mm: float = Field(default=0.0, ge=0.0, le=1000.0)
    dedup: bool = False
    join_polylines: bool = False
    round_coords: bool = False


class PedidoDeExportacao(BaseModel):
    escala: float = Field(gt=0.0)
    unidade: str = Field(pattern="^(mm|cm|m)$")
    opcoes: Opcoes = Field(default_factory=Opcoes)


@app.post("/api/jobs/{job_id}/pages/{pagina}/export")
def exportar(job_id: str, pagina: int, pedido: PedidoDeExportacao) -> dict:
    _pagina_pronta(job_id, pagina)
    ch, _caminho, do_cache, entidades = exportacao.gerar(
        job_id, pagina, pedido.escala, pedido.unidade, pedido.opcoes.model_dump())
    return {
        "chave": ch,
        "url": f"/api/download/{job_id}/{ch}",
        "cache": do_cache,
        "entidades": entidades,
    }


@app.get("/api/download/{job_id}/{ch}")
def baixar(job_id: str, ch: str) -> FileResponse:
    ficha = _ficha_ou_404(job_id)
    for pagina in ficha.get("paginas", {}):
        try:
            caminho = exportacao.caminho_do_dxf(job_id, int(pagina), ch)
        except ValueError:
            raise HTTPException(status_code=400, detail="Chave inválida.")
        if caminho.exists():
            nome = os.path.splitext(ficha["nome"])[0] + ".dxf"
            return FileResponse(caminho, media_type="application/dxf",
                                filename=nome)
    raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
```

A rota de download procura a chave em todas as páginas do trabalho, o que evita
carregar o número da página na URL — a chave já é única por combinação, e a
página faz parte dela.

- [ ] **Passo 4: rodar e ver passar**

```bash
python tests/test_api_export.py
```

Esperado: as seis linhas `OK:` e `Todos os testes de exportação passaram.`

- [ ] **Passo 5: commit**

```bash
git add web/api/exportacao.py web/api/main.py tests/test_api_export.py
git commit -m "Exporta o DXF a partir do cache, com reaproveitamento por combinacao"
```

---

### Tarefa 7: expiração por prazo e cota de disco

**Arquivos:**
- Modificar: `web/api/storage.py`
- Modificar: `web/api/main.py` (tarefa periódica)
- Testar: `tests/test_storage.py`

**Interfaces:**
- Produz: `storage.tamanho_total() -> int`,
  `storage.limpar(agora: float) -> dict` devolvendo
  `{"expirados": [ids], "por_cota": [ids], "bytes_livres": int}`

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_storage.py`:

```python
"""Expiração por prazo e cota de disco."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")

from web.api import limits, storage

AGORA = 1_800_000_000.0   # instante fixo, para o teste não depender do relógio


def trabalho(idade_segundos: float, bytes_de_lixo: int = 1024) -> str:
    job_id = storage.novo_id()
    storage.criar_trabalho(job_id, "planta.pdf", 1, bytes_de_lixo,
                           agora=AGORA - idade_segundos)
    with open(storage.pasta(job_id) / "lixo.bin", "wb") as f:
        f.write(b"0" * bytes_de_lixo)
    return job_id


def limpar_tudo():
    for p in storage.raiz().iterdir():
        if p.is_dir():
            import shutil
            shutil.rmtree(p, ignore_errors=True)


def test_expira_por_prazo():
    limpar_tudo()
    velho = trabalho(limits.PRAZO_SEGUNDOS + 60)
    novo = trabalho(60)
    relato = storage.limpar(agora=AGORA)
    assert velho in relato["expirados"], relato
    assert novo not in relato["expirados"], relato
    assert not storage.pasta(velho).exists()
    assert storage.pasta(novo).exists()
    print("OK: trabalho vencido é apagado, o recente fica")


def test_cota_apaga_o_mais_antigo_primeiro():
    limpar_tudo()
    original = limits.COTA_DISCO_BYTES
    limits.COTA_DISCO_BYTES = 5000
    try:
        antigo = trabalho(300, bytes_de_lixo=3000)
        recente = trabalho(60, bytes_de_lixo=3000)
        relato = storage.limpar(agora=AGORA)
        assert antigo in relato["por_cota"], relato
        assert recente not in relato["por_cota"], relato
        assert not storage.pasta(antigo).exists()
        assert storage.pasta(recente).exists()
    finally:
        limits.COTA_DISCO_BYTES = original
    print("OK: a cota apaga do mais antigo para o mais novo")


def test_limpeza_ignora_pasta_estranha():
    limpar_tudo()
    (storage.raiz() / "nao-e-um-trabalho").mkdir()
    relato = storage.limpar(agora=AGORA)
    assert relato["expirados"] == [] and relato["por_cota"] == []
    assert (storage.raiz() / "nao-e-um-trabalho").exists()
    print("OK: a limpeza não mexe em pasta que não é trabalho")


def test_limpeza_sobrevive_a_ficha_corrompida():
    limpar_tudo()
    job = trabalho(60)
    with open(storage.caminho_ficha(job), "w", encoding="utf-8") as f:
        f.write("{isto nao e json")
    relato = storage.limpar(agora=AGORA)
    assert job in relato["expirados"], "ficha ilegível deve ser tratada como lixo"
    print("OK: ficha corrompida não trava a limpeza")


if __name__ == "__main__":
    test_expira_por_prazo()
    test_cota_apaga_o_mais_antigo_primeiro()
    test_limpeza_ignora_pasta_estranha()
    test_limpeza_sobrevive_a_ficha_corrompida()
    print("Todos os testes de armazenamento passaram.")
```

- [ ] **Passo 2: rodar e ver falhar**

```bash
python tests/test_storage.py
```

Esperado: `AttributeError: module 'web.api.storage' has no attribute 'limpar'`

- [ ] **Passo 3: implementar**

Acrescente `import shutil` e `from . import limits` ao topo de
`web/api/storage.py`, junto dos imports que já existem, e o resto ao fim do
arquivo:

```python
def _tamanho(pasta: Path) -> int:
    total = 0
    for raiz_atual, _dirs, arquivos in os.walk(pasta):
        for nome in arquivos:
            try:
                total += os.path.getsize(os.path.join(raiz_atual, nome))
            except OSError:
                pass   # o arquivo pode sumir durante a varredura
    return total


def tamanho_total() -> int:
    return sum(_tamanho(p) for p in raiz().iterdir() if p.is_dir())


def _trabalhos() -> list[tuple[str, float, int]]:
    """Lista `(job_id, criado_em, tamanho)`. Ficha ilegível vira idade zero
    absoluta, o que faz a limpeza tratar a pasta como lixo a remover."""
    saida = []
    for p in raiz().iterdir():
        if not p.is_dir():
            continue
        try:
            validar_id(p.name)
        except ValueError:
            continue        # pasta que não é trabalho: não é nossa, não mexe
        try:
            ficha = ler_ficha(p.name)
            criado = float(ficha["criado_em"]) if ficha else 0.0
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            criado = 0.0
        saida.append((p.name, criado, _tamanho(p)))
    return saida


def apagar(job_id: str) -> None:
    shutil.rmtree(pasta(job_id), ignore_errors=True)


def limpar(agora: float | None = None) -> dict:
    """Apaga o que venceu e, se ainda estourar a cota, o mais antigo."""
    agora = time.time() if agora is None else agora
    trabalhos = _trabalhos()

    expirados = []
    vivos = []
    for job_id, criado, tamanho in trabalhos:
        if agora - criado > limits.PRAZO_SEGUNDOS:
            apagar(job_id)
            expirados.append(job_id)
        else:
            vivos.append((job_id, criado, tamanho))

    total = sum(t for _, _, t in vivos)
    por_cota = []
    for job_id, _criado, tamanho in sorted(vivos, key=lambda t: t[1]):
        if total <= limits.COTA_DISCO_BYTES:
            break
        apagar(job_id)
        por_cota.append(job_id)
        total -= tamanho

    return {"expirados": expirados, "por_cota": por_cota,
            "bytes_livres": max(0, limits.COTA_DISCO_BYTES - total)}
```

- [ ] **Passo 4: rodar a limpeza periodicamente**

Em `web/api/main.py`, acrescente:

```python
import asyncio
import contextlib

INTERVALO_LIMPEZA = 10 * 60   # 10 minutos


async def _limpeza_periodica() -> None:
    while True:
        await asyncio.sleep(INTERVALO_LIMPEZA)
        try:
            relato = await asyncio.to_thread(storage.limpar)
            if relato["expirados"] or relato["por_cota"]:
                print(f"limpeza: {len(relato['expirados'])} vencidos, "
                      f"{len(relato['por_cota'])} por cota")
        except Exception:
            traceback.print_exc()   # a limpeza nunca pode derrubar o serviço


@contextlib.asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    tarefa = asyncio.create_task(_limpeza_periodica())
    try:
        yield
    finally:
        tarefa.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarefa
```

E troque a criação da app, lá no topo do arquivo, para registrar o ciclo de vida:

```python
app = FastAPI(title="PdfToDxf", docs_url=None, redoc_url=None,
              lifespan=ciclo_de_vida)
```

Como `ciclo_de_vida` é usada na criação da app, ela precisa estar **definida
antes** da linha do `app = FastAPI(...)`. Ponha a função e o `_limpeza_periodica`
logo abaixo dos imports, no começo do arquivo.

Importe `traceback` no topo. Use `lifespan=` e não `@app.on_event`: os decoradores
de evento estão obsoletos desde o FastAPI 0.109 e emitem `DeprecationWarning`, o
que sujaria a saída dos testes.

O `asyncio.to_thread` é necessário porque `storage.limpar` percorre o disco e
bloquearia o laço de eventos.

- [ ] **Passo 5: rodar e ver passar**

```bash
python tests/test_storage.py
```

Esperado: as quatro linhas `OK:` e `Todos os testes de armazenamento passaram.`

- [ ] **Passo 6: documentar como subir o serviço**

Crie `web/README.md`:

````markdown
# Serviço de conversão

```powershell
pip install -r web/requirements.txt
$env:PDFTODXF_DADOS = "C:\caminho\para\dados"
python -m uvicorn web.api.main:app --reload
```

Sem `PDFTODXF_DADOS`, os arquivos vão para `./dados`.

## Rotas

| Rota | Efeito |
|---|---|
| `POST /api/jobs` | Envia o PDF. Devolve `job_id` e número de páginas. |
| `GET /api/jobs/{id}` | Ficha do trabalho e estado de cada página pedida. |
| `POST /api/jobs/{id}/pages/{n}` | Enfileira a extração da página. |
| `GET /api/jobs/{id}/pages/{n}` | Estado da página. |
| `GET /api/jobs/{id}/pages/{n}/meta.json` | Layers, contagens, limites da folha. |
| `GET /api/jobs/{id}/pages/{n}/geometry.bin?parte=esqueleto\|detalhe` | Geometria binária. |
| `POST /api/jobs/{id}/pages/{n}/export` | Gera o DXF. Devolve a URL de download. |
| `GET /api/download/{id}/{chave}` | Entrega o DXF. |

## Testes

```powershell
python tests/test_api_upload.py
python tests/test_api_extracao.py
python tests/test_packing.py
python tests/test_api_geometria.py
python tests/test_api_export.py
python tests/test_storage.py
```

## Limites de recurso

A extração roda em processo separado com `RLIMIT_AS` e `RLIMIT_CPU`. Esses
limites **só existem em POSIX**: no Windows o campo `limites_aplicados` do estado
da página diz `nenhum (plataforma sem resource)`. Em produção o serviço roda em
Linux dentro de contêiner, onde valem.
````

- [ ] **Passo 7: commit**

```bash
git add web/ tests/test_storage.py
git commit -m "Limpa trabalhos vencidos e por cota de disco, com tarefa periodica"
```

---

## Definição de pronto

Ao fim da etapa 2, tudo abaixo é verdade:

- Os seis arquivos de teste novos passam, além dos quatro da etapa 1.
- `requirements.txt` da raiz continua com três dependências; as do serviço estão
  em `web/requirements.txt`.
- Um PDF vetorial sobe, extrai, entrega geometria em duas partes e volta como DXF
  válido, tudo por HTTP.
- Esqueleto e detalhe somados reproduzem exatamente a lista de entidades da
  extração, sem faltar nem repetir.
- Repetir uma exportação com a mesma combinação não gera arquivo novo.
- PDF grande demais, sem vetores ou acima do teto de entidades produzem erro
  identificável, e o envio recusado não deixa resto em disco.
- Trabalhos vencem em 4 horas e a cota de disco apaga do mais antigo.
- `select()` decide comprimento comparando inteiros, sem ponto flutuante.

## O que fica para a etapa 3

- O `select.ts`, espelhando `optimize.select()` e verificado contra
  `tests/casos_select.json` pelo vitest.
- O leitor TypeScript do formato binário descrito na tarefa 4.
- O canvas, a calibração, as duas faixas do cabeçalho e os estados de espera e
  erro que a especificação descreve.
