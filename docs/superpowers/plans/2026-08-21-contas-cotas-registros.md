# Etapa 4 — contas, cotas e registros: plano de implementação

> **Para quem executa com agentes:** SUB-HABILIDADE OBRIGATÓRIA — use
> `superpowers:subagent-driven-development` (recomendado) ou
> `superpowers:executing-plans` para executar tarefa a tarefa. Os passos usam
> caixas (`- [ ]`) para acompanhamento.

**Objetivo:** fechar o que falta para o serviço ficar de pé em público —
registros de conversão por 1 ano, cotas de uso por janela deslizante, contas por
e-mail e senha, e a parte da tela que fala disso.

**Arquitetura:** seis módulos novos em `web/api/`, cada um com uma pergunta só —
`db.py` guarda, `identidade.py` responde "quem é", `quotas.py` responde "pode?",
`auth.py` responde "é mesmo quem diz ser", `registros.py` escreve um arquivo, e
`enviador.py` manda e-mail. O código da etapa 2 não é reescrito: `main.py` e
`jobs.py` ganham chamadas nas bordas, `storage.py` e `exportacao.py` não são
tocados. **O worker nunca abre o banco** — recebe o que precisa por argumento e
grava um arquivo; toda escrita em SQLite acontece no processo do serviço.

**Pilha:** Python 3.13 + FastAPI (já instalados) e **só biblioteca padrão** para
o que é novo: `sqlite3`, `hmac`, `hashlib.scrypt`, `secrets`, `smtplib`,
`email.message`, `base64`. No frontend, TypeScript + Vite + Vitest, sem
dependência nova.

## Restrições globais

Valem para **todas** as tarefas; cada tarefa herda esta seção inteira.

- **Nenhuma dependência nova.** `web/requirements.txt` e
  `web/frontend/package.json` terminam a etapa com exatamente as linhas que já
  têm. Isso é item da definição de pronto.
- **Sem pytest.** Testes são funções com `assert` e um bloco
  `if __name__ == "__main__":` que as chama e imprime `OK: ...`. Rodam com
  `./.venv/Scripts/python.exe tests/test_x.py`. Nunca use `python` puro.
- **Antes de escrever qualquer conversão, procure se ela já existe no núcleo.**
  Foi o erro mais caro da etapa 3.5: duas conversões reimplementadas à mão e
  erradas as duas. `PT_TO_MM` está em `pdftodxf/calibration.py:7`;
  `INSUNITS` está na linha 10 do mesmo arquivo.
- **Nada que venha do cliente entra num caminho sem higienização**, e a
  conferência final é sempre contra a pasta resolvida, não contra o nome cru.
- **Texto da tela vai por `textContent`**, nunca `innerHTML`: nome de camada e
  e-mail vêm do usuário.
- **`0` numa chave de cota significa "sem limite"**; chave ausente cai no padrão
  da tabela, e o padrão é seguro, não é ilimitado.
- **Toda mensagem de erro diz o que houve e o que fazer.** "Erro ao processar"
  não é mensagem.
- **Commit ao fim de cada tarefa**, com mensagem em português, sem acentos no
  assunto (o console do Windows é cp1252).
- **A mensagem de recusa de cota é a mesma nos três baldes.** Dizer qual balde
  estourou conta a quem tenta burlar exatamente o que ele precisa saber.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `pdftodxf/geometry.py` (modificar) | ganha `limites(entities)` — os limites do desenho em pontos de papel |
| `web/api/registros.py` (criar) | monta o `.md` de uma página, higieniza o nome, resolve colisão, expurga o que passou de 1 ano |
| `web/api/db.py` (criar) | SQLite: caminho, conexão por thread, esquema, e o segredo com `marca`/`assinar`/`conferir` |
| `web/api/identidade.py` (criar) | resolve quem está pedindo e quais baldes ele consome |
| `web/api/quotas.py` (criar) | janela deslizante, reserva, confirmação, soltura, leitura das chaves |
| `web/api/auth.py` (criar) | senha, cadastro, confirmação, sessão, redefinição, teto por IP |
| `web/api/enviador.py` (criar) | manda e-mail: arquivo em desenvolvimento, SMTP em produção |
| `web/api/jobs.py` (modificar) | passa IP e conta ao worker; confirma ou solta a reserva |
| `web/api/main.py` (modificar) | rotas novas de conta e cota; cota no envio e na exportação |
| `web/frontend/src/conta.ts` (criar) | canto da conta, caixas de entrar e cadastrar, cota restante |
| `web/frontend/src/impressao.ts` (criar) | coleta os sinais do navegador e devolve só o hash |
| `web/frontend/public/privacidade.html` (criar) | o que é guardado, por quê e por quanto tempo |

**Por que `marca()` e `assinar()` moram em `db.py`:** o segredo é a chave dos
`hmac` que formam `consumo.balde` e `usuarios.criado_de` — duas **colunas do
banco**. A spec já diz que trocar o segredo zera as cotas em andamento e a
contagem de contas do dia. O segredo pertence a quem guarda.

**Por que `identidade.py` não importa `auth.py`:** ela precisa saber se há
sessão, e `auth` precisa do IP para o teto de contas por dia — isso seria um
ciclo. A saída é `resolver(request, dono=None)`: quem chama (a rota) resolve a
sessão e passa o resultado. Nas tarefas 4 a 7 ninguém passa `dono`; a tarefa 8 é
que liga o fio.

---

### Tarefa 1: `registros.py` — o `.md` de uma página

**Arquivos:**
- Modificar: `pdftodxf/geometry.py` (acrescentar `limites` ao fim)
- Criar: `web/api/registros.py`
- Testar: `tests/test_registros.py`

**Interfaces:**
- Consome: `ExtractionResult` (`pdftodxf/extractor.py:18`) com `entities`,
  `page_width`, `page_height`, `counts()`; `EntityAttrs`
  (`pdftodxf/optimize.py:36`) com `layer_id`, `layers`; `PT_TO_MM`
  (`pdftodxf/calibration.py:7`).
- Produz, e as tarefas 2 e 11 dependem destes nomes exatos:
  - `pdftodxf.geometry.limites(entities: list[Entity]) -> tuple[float, float, float, float] | None`
  - `registros.pasta() -> Path`
  - `registros.PRAZO_S: int`
  - `registros.montar(dados: dict, resultado, attrs) -> str`
  - `registros.gravar(dados: dict, resultado, attrs) -> Path`
  - `registros.expurgar(agora: float | None = None) -> list[str]`
  - A chave `dados` tem exatamente: `ip`, `conta`, `nome`, `pagina`, `job_id`,
    `tamanho_pdf`, `segundos`, `quando` (epoch UTC).

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_registros.py`:

```python
"""O registro .md de uma página: conteúdo, nome de arquivo e expurgo."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")

from pdftodxf.geometry import Segment, TextItem, limites
from pdftodxf.optimize import classify
from web.api import registros


class ResultadoFalso:
    """Um `ExtractionResult` de mentira, com o mínimo que `montar` lê."""

    def __init__(self, entidades, largura=841.89, altura=595.28):
        self.entities = entidades
        self.page_width = largura
        self.page_height = altura
        self.layers = {e.layer for e in entidades}

    def counts(self):
        saida = {}
        for e in self.entities:
            nome = type(e).__name__
            saida[nome] = saida.get(nome, 0) + 1
        return saida


def cenario():
    entidades = [
        Segment(p1=(10.0, 20.0), p2=(110.0, 20.0), layer="PAREDE"),
        Segment(p1=(110.0, 20.0), p2=(110.0, 220.0), layer="PAREDE"),
        TextItem(text="SALA 01", position=(50.0, 60.0), height=3.5,
                 rotation=0.0, layer="TEXTO"),
        TextItem(text="6,06", position=(70.0, 30.0), height=2.5,
                 rotation=90.0, layer="TEXTO"),
    ]
    resultado = ResultadoFalso(entidades)
    return resultado, classify(entidades)


DADOS = {
    "ip": "192.168.0.7",
    "conta": "",
    "nome": "LAY-1031.26.00_REV 00.pdf",
    "pagina": 1,
    "job_id": "a" * 32,
    "tamanho_pdf": 750_000,
    "segundos": 0.42,
    "quando": 1_755_000_000.0,
}


def test_limites_do_desenho():
    entidades = cenario()[0].entities
    assert limites([]) is None, "sem entidade não há limites"
    assert limites(entidades) == (10.0, 20.0, 110.0, 220.0)
    print("OK: os limites do desenho saem certos")


def test_o_md_traz_os_textos_e_os_numeros():
    resultado, attrs = cenario()
    texto = registros.montar(DADOS, resultado, attrs)

    assert texto.startswith("---\n"), "tem que abrir com frontmatter"
    assert 'ip: "192.168.0.7"' in texto
    assert 'nome: "LAY-1031.26.00_REV 00.pdf"' in texto
    assert "pagina: 1" in texto
    assert "tamanho_pdf: 750000" in texto
    assert "segundos: 0.42" in texto

    # Todo texto da planta tem que estar no registro: é para isso que ele existe.
    assert "SALA 01" in texto
    assert "6,06" in texto

    assert "PAREDE" in texto and "TEXTO" in texto
    assert "Segment" in texto and "TextItem" in texto
    # Folha em pt e em mm, e os limites do desenho.
    assert "841.9" in texto or "841,9" in texto
    assert "297" in texto, "595,28 pt = 210 mm e 841,89 pt = 297 mm"
    print("OK: o .md traz os textos, os layers e as dimensões")


def test_nome_com_travessia_e_higienizado():
    ruim = {**DADOS, "nome": "../../etc/passwd.pdf", "ip": "2001:db8::1"}
    nome = registros.nome_do_arquivo(ruim["ip"], ruim["nome"], 1, DADOS["quando"])
    assert "/" not in nome and "\\" not in nome, nome
    assert ".." not in nome.replace("_", ""), nome
    assert nome.endswith(".md")
    assert ":" not in nome, "dois-pontos não pode: o Windows recusa no nome"
    print("OK: nome com travessia é higienizado")


def test_gravar_nao_escapa_da_pasta():
    resultado, attrs = cenario()
    caminho = registros.gravar({**DADOS, "nome": "../../fora.pdf"},
                               resultado, attrs)
    assert caminho.resolve().is_relative_to(registros.pasta().resolve())
    assert caminho.exists()
    print("OK: o arquivo gravado não escapa da pasta de registros")


def test_dois_iguais_no_mesmo_segundo_nao_se_sobrescrevem():
    resultado, attrs = cenario()
    a = registros.gravar(DADOS, resultado, attrs)
    b = registros.gravar(DADOS, resultado, attrs)
    assert a != b, "o segundo tinha que ganhar sufixo"
    assert a.exists() and b.exists()
    print("OK: dois registros do mesmo segundo não se sobrescrevem")


def test_expurgo_de_um_ano():
    resultado, attrs = cenario()
    novo = registros.gravar(DADOS, resultado, attrs)
    velho = registros.pasta() / "velho.md"
    velho.write_text("registro antigo", encoding="utf-8")
    antigo = time.time() - registros.PRAZO_S - 60
    os.utime(velho, (antigo, antigo))

    apagados = registros.expurgar()
    assert "velho.md" in apagados, apagados
    assert not velho.exists()
    assert novo.exists(), "o registro novo tem que ficar"
    print("OK: o expurgo apaga o que passou de 1 ano e poupa o resto")


if __name__ == "__main__":
    test_limites_do_desenho()
    test_o_md_traz_os_textos_e_os_numeros()
    test_nome_com_travessia_e_higienizado()
    test_gravar_nao_escapa_da_pasta()
    test_dois_iguais_no_mesmo_segundo_nao_se_sobrescrevem()
    test_expurgo_de_um_ano()
    print("Todos os testes de registros passaram.")
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_registros.py
```

Esperado: `ImportError: cannot import name 'limites' from 'pdftodxf.geometry'`.

- [ ] **Passo 3: acrescentar `limites` ao núcleo**

Ao fim de `pdftodxf/geometry.py`:

```python
def limites(entities: list[Entity]) -> tuple[float, float, float, float] | None:
    """Caixa envolvente do desenho, em pontos de papel: `(x0, y0, x1, y1)`.

    Devolve `None` para lista vazia — e não uma caixa de área zero na origem,
    que mentiria dizendo que há desenho no canto da folha.

    Mora aqui, e não em quem chama, porque só este módulo conhece a forma de
    cada entidade. Arco entra pela caixa do círculo inteiro: é aproximação por
    excesso, honesta para o que o registro faz com o número.
    """
    xs: list[float] = []
    ys: list[float] = []
    for e in entities:
        if isinstance(e, Segment):
            xs += [e.p1[0], e.p2[0]]
            ys += [e.p1[1], e.p2[1]]
        elif isinstance(e, Polyline):
            xs += [p[0] for p in e.points]
            ys += [p[1] for p in e.points]
        elif isinstance(e, Bezier):
            xs += [e.p0[0], e.p1[0], e.p2[0], e.p3[0]]
            ys += [e.p0[1], e.p1[1], e.p2[1], e.p3[1]]
        elif isinstance(e, Arc):
            xs += [e.center[0] - e.radius, e.center[0] + e.radius]
            ys += [e.center[1] - e.radius, e.center[1] + e.radius]
        elif isinstance(e, TextItem):
            xs.append(e.position[0])
            ys.append(e.position[1])
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))
```

- [ ] **Passo 4: escrever `registros.py`**

Crie `web/api/registros.py`:

```python
"""O registro em Markdown de uma página extraída.

Este módulo monta um texto e grava um arquivo. Ele **não sabe** o que é conta
nem o que é cota: recebe tudo pronto em `dados`. É o que permite chamá-lo de
dentro do worker, que nunca abre o banco.

O IP aqui é o real, e não o `hmac` que a cota guarda. Não é contradição: a cota
só precisa saber "é o mesmo?"; o registro existe justamente para ser
rastreável. Os dois usos estão declarados na página de privacidade, com prazos
diferentes — 2 horas e 1 ano.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from pdftodxf.calibration import PT_TO_MM
from pdftodxf.geometry import limites

PRAZO_S = 365 * 24 * 60 * 60      # 1 ano
LIMITE_DO_NOME = 60
_PROIBIDO = re.compile(r"[^A-Za-z0-9_-]")


def pasta() -> Path:
    """Pasta dos registros, de `PDFTODXF_REGISTROS` ou `./registros`.

    Fora da pasta de trabalhos de propósito, e nunca servida pela web.
    """
    caminho = Path(os.environ.get("PDFTODXF_REGISTROS", "registros"))
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def _limpo(texto: str, limite: int) -> str:
    """Troca por `_` tudo que não for letra, número, hífen ou sublinhado.

    Aplicado à string **inteira**, e não só ao `basename`: um nome com `..\\`
    sobrevive ao `os.path.basename` em POSIX, e o barato aqui é não depender
    de qual separador a plataforma reconhece.
    """
    return _PROIBIDO.sub("_", texto or "")[:limite]


def nome_do_arquivo(ip: str, nome_pdf: str, pagina: int, quando: float) -> str:
    """`{ip}-{nome}-p{pagina}-{AAAAMMDD-HHMMSS}.md`, tudo higienizado."""
    sem_extensao = os.path.splitext(nome_pdf or "")[0]
    base = _limpo(sem_extensao, LIMITE_DO_NOME) or "planta"
    marca_tempo = time.strftime("%Y%m%d-%H%M%S", time.gmtime(quando))
    return f"{_limpo(ip, 45)}-{base}-p{int(pagina)}-{marca_tempo}.md"


def _yaml(valor) -> str:
    """Um escalar YAML seguro. JSON é YAML válido, e o `json` já escapa."""
    return json.dumps(valor, ensure_ascii=False)


def montar(dados: dict, resultado, attrs) -> str:
    por_layer: dict[str, int] = {}
    for i in range(len(attrs.layer_id)):
        nome = attrs.layers[attrs.layer_id[i]]
        por_layer[nome] = por_layer.get(nome, 0) + 1

    quando = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(dados["quando"]))
    linhas = [
        "---",
        f"ip: {_yaml(dados['ip'])}",
        f"conta: {_yaml(dados['conta'])}",
        f"nome: {_yaml(dados['nome'])}",
        f"pagina: {int(dados['pagina'])}",
        f"quando: {_yaml(quando + ' UTC')}",
        f"job_id: {_yaml(dados['job_id'])}",
        f"tamanho_pdf: {int(dados['tamanho_pdf'])}",
        f"segundos: {round(float(dados['segundos']), 2)}",
        "---",
        "",
        f"# {dados['nome']} — página {dados['pagina']}",
        "",
        "## Folha",
        "",
        f"- {resultado.page_width:.1f} x {resultado.page_height:.1f} pt",
        f"- {resultado.page_width * PT_TO_MM:.0f} x "
        f"{resultado.page_height * PT_TO_MM:.0f} mm",
    ]

    caixa = limites(resultado.entities)
    if caixa is None:
        linhas.append("- limites do desenho: nenhum (página sem geometria)")
    else:
        x0, y0, x1, y1 = caixa
        linhas.append(f"- limites do desenho: ({x0:.1f}, {y0:.1f}) a "
                      f"({x1:.1f}, {y1:.1f}) pt")

    linhas += ["", "## Entidades", "", "| tipo | quantidade |", "|---|---:|"]
    contagem = resultado.counts()
    for tipo in sorted(contagem):
        linhas.append(f"| {tipo} | {contagem[tipo]} |")

    linhas += ["", "## Layers", "", "| layer | entidades |", "|---|---:|"]
    for nome in sorted(por_layer, key=lambda n: (-por_layer[n], n)):
        linhas.append(f"| {nome} | {por_layer[nome]} |")

    linhas += ["", "## Textos da planta", "",
               "| texto | x | y | altura | rotação |", "|---|---:|---:|---:|---:|"]
    for e in resultado.entities:
        texto = getattr(e, "text", None)
        if texto is None:
            continue
        # `|` dentro do texto quebraria a tabela; a barra escapada é o que o
        # Markdown entende, e o texto vem do PDF do usuário.
        seguro = texto.replace("|", "\\|")
        linhas.append(f"| {seguro} | {e.position[0]:.1f} | {e.position[1]:.1f} "
                      f"| {e.height:.2f} | {e.rotation:.1f} |")

    return "\n".join(linhas) + "\n"


def gravar(dados: dict, resultado, attrs) -> Path:
    """Grava o registro e devolve o caminho. Nunca sobrescreve.

    O caminho final é conferido contra a pasta **depois** de resolvido, e não
    antes: a higienização do nome já deveria bastar, e esta é a rede de
    segurança de quem esqueceu um caso.
    """
    destino = pasta()
    nome = nome_do_arquivo(dados["ip"], dados["nome"], dados["pagina"],
                           dados["quando"])
    texto = montar(dados, resultado, attrs).encode("utf-8")

    raiz = destino.resolve()
    sufixo = 0
    while True:
        tentativa = nome if sufixo == 0 else f"{nome[:-3]}-{sufixo}.md"
        caminho = (destino / tentativa)
        if not caminho.resolve().is_relative_to(raiz):
            raise ValueError("o registro escaparia da pasta de registros")
        try:
            # `O_EXCL`: dois workers no mesmo segundo não podem se sobrescrever,
            # e conferir com `exists()` antes de abrir seria justamente a
            # corrida que se quer evitar.
            fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            sufixo += 1
            continue
        with os.fdopen(fd, "wb") as f:
            f.write(texto)
        return caminho


def expurgar(agora: float | None = None) -> list[str]:
    """Apaga o que passou de 1 ano. Devolve os nomes apagados."""
    agora = time.time() if agora is None else agora
    apagados = []
    for arquivo in pasta().iterdir():
        if not arquivo.is_file():
            continue
        try:
            if agora - arquivo.stat().st_mtime <= PRAZO_S:
                continue
            arquivo.unlink()
        except OSError:
            continue        # sumiu no meio da varredura, ou está preso: fica
        apagados.append(arquivo.name)
    return apagados
```

- [ ] **Passo 5: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_registros.py
```

Esperado: seis linhas `OK: ...` e `Todos os testes de registros passaram.`

- [ ] **Passo 6: conferir que não quebrou o núcleo**

```bash
./.venv/Scripts/python.exe tests/test_optimize.py && ./.venv/Scripts/python.exe tests/test_roundtrip.py
```

Esperado: as duas baterias passam com saída limpa.

- [ ] **Passo 7: commit**

```bash
git add pdftodxf/geometry.py web/api/registros.py tests/test_registros.py
git commit -m "Registro em Markdown de cada pagina extraida"
```

---

### Tarefa 2: ligar o registro ao worker e o expurgo à limpeza

**Arquivos:**
- Modificar: `web/api/jobs.py` (`_extrair_no_worker`, `pedir_extracao`)
- Modificar: `web/api/main.py` (`_limpeza_periodica`, `extrair_pagina`)
- Testar: `tests/test_registros_no_worker.py`

**Interfaces:**
- Consome: `registros.gravar`, `registros.expurgar`, `registros.pasta` da tarefa 1.
- Produz, e a tarefa 6 depende desta assinatura:
  - `jobs.pedir_extracao(job_id: str, pagina: int, ip: str = "", conta: str = "") -> dict`
  - `_extrair_no_worker` ganha, ao fim, os argumentos
    `pasta_registros: str, ip: str, conta: str, nome_original: str,
    tamanho_pdf: int, job_id: str`.

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_registros_no_worker.py`:

```python
"""A extração de verdade grava o registro, e o serviço não o entrega pela web."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Como no test_api_extracao: no Windows o worker reimporta este arquivo, e
# reatribuir a variável faria o filho apontar para outra pasta.
if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
if "PDFTODXF_REGISTROS" not in os.environ:
    os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")

from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial, enviar, esperar
from web.api import registros
from web.api.main import app

cliente = TestClient(app)


def test_extracao_grava_o_registro():
    antes = {p.name for p in registros.pasta().iterdir()}
    job = enviar(bytes_do_pdf_vetorial())
    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "pronta"

    novos = [p for p in registros.pasta().iterdir() if p.name not in antes]
    assert len(novos) == 1, [p.name for p in novos]
    texto = novos[0].read_text(encoding="utf-8")
    assert texto.startswith("---\n")
    assert job in texto, "o job_id tem que estar no frontmatter"
    assert "## Textos da planta" in texto
    print("OK: a extração de verdade grava o registro")


def test_falha_ao_gravar_o_registro_nao_derruba_a_pagina():
    """Perder um registro não pode custar ao usuário a planta que ele veio converter."""
    from web.api import jobs

    original = os.environ["PDFTODXF_REGISTROS"]
    # Um arquivo no lugar da pasta: `mkdir` estoura e a gravação falha.
    impossivel = os.path.join(tempfile.mkdtemp(), "nao-e-pasta")
    with open(impossivel, "w") as f:
        f.write("x")
    os.environ["PDFTODXF_REGISTROS"] = impossivel
    try:
        job = enviar(bytes_do_pdf_vetorial())
        cliente.post(f"/api/jobs/{job}/pages/1")
        final = esperar(job, 1)
    finally:
        os.environ["PDFTODXF_REGISTROS"] = original

    assert final["situacao"] == "pronta", final
    print("OK: falha ao gravar o registro não impede a página de ficar pronta")


def test_nenhuma_rota_alcanca_a_pasta_de_registros():
    caminhos = [
        "/registros/",
        "/registros/qualquer.md",
        "/api/registros",
        "/../registros/qualquer.md",
        "/api/download/" + "a" * 32 + "/../../../registros/qualquer.md",
    ]
    for caminho in caminhos:
        r = cliente.get(caminho)
        assert r.status_code in (400, 404), (caminho, r.status_code)
    print("OK: nenhuma rota do serviço alcança a pasta de registros")


if __name__ == "__main__":
    test_extracao_grava_o_registro()
    test_falha_ao_gravar_o_registro_nao_derruba_a_pagina()
    test_nenhuma_rota_alcanca_a_pasta_de_registros()
    print("Todos os testes de registro no worker passaram.")
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_registros_no_worker.py
```

Esperado: FALHA em `test_extracao_grava_o_registro`, com `len(novos) == 0` —
nada grava registro ainda.

- [ ] **Passo 3: o worker grava o registro**

Em `web/api/jobs.py`, troque a assinatura e o corpo de `_extrair_no_worker`.
A linha do `def` passa a ser:

```python
def _extrair_no_worker(pdf: str, pagina: int, destino: str, teto_entidades: int,
                       teto_memoria: int, teto_cpu: int,
                       alvo_minimo_esqueleto: int,
                       pasta_registros: str, ip: str, conta: str,
                       nome_original: str, tamanho_pdf: int,
                       job_id: str) -> dict:
```

Logo depois de `aplicados = _aplicar_limites(teto_memoria, teto_cpu)`,
acrescente:

```python
    import time as _time
    comeco = _time.time()
```

E, imediatamente **antes** do `return` final (depois de gravar o `meta.json`),
acrescente:

```python
    # O registro é o último passo, e falhar aqui não pode custar a página. Ele
    # roda no worker, e não no processo pai, para não mandar todos os TextItem
    # de volta pela fronteira de processo só para escrevê-los num arquivo.
    try:
        os.environ["PDFTODXF_REGISTROS"] = pasta_registros
        from . import registros
        registros.gravar({
            "ip": ip, "conta": conta, "nome": nome_original,
            "pagina": pagina, "job_id": job_id,
            "tamanho_pdf": tamanho_pdf,
            "segundos": _time.time() - comeco,
            "quando": _time.time(),
        }, resultado, attrs)
    except Exception:
        traceback.print_exc()
```

- [ ] **Passo 4: `pedir_extracao` passa o que o worker não tem como saber**

Em `web/api/jobs.py`, troque a assinatura de `pedir_extracao` para:

```python
def pedir_extracao(job_id: str, pagina: int, ip: str = "",
                   conta: str = "") -> dict:
```

e a chamada de `pool().submit(...)` para:

```python
        ficha = storage.ler_ficha(job_id) or {}
        try:
            futuro = pool().submit(
                _extrair_no_worker, str(origem), pagina, str(destino),
                limits.TETO_ENTIDADES, limits.TETO_MEMORIA_WORKER_BYTES,
                limits.TETO_CPU_WORKER_SEGUNDOS, packing.ALVO_MINIMO,
                str(registros.pasta()), ip, conta,
                ficha.get("nome", "planta.pdf"), int(ficha.get("tamanho", 0)),
                job_id)
```

E acrescente `registros` ao import do topo do arquivo:

```python
from . import limits, packing, registros, storage
```

- [ ] **Passo 5: a rota passa o IP, e a limpeza expurga**

Em `web/api/main.py`, troque `extrair_pagina` por:

```python
@app.post("/api/jobs/{job_id}/pages/{pagina}")
def extrair_pagina(job_id: str, pagina: int, request: Request) -> dict:
    ficha = _ficha_ou_404(job_id)
    if pagina < 1 or pagina > ficha["n_paginas"]:
        raise HTTPException(
            status_code=404,
            detail=f"O documento tem {ficha['n_paginas']} página(s).")
    ip = request.client.host if request.client else ""
    return jobs.pedir_extracao(job_id, pagina, ip=ip, conta="")
```

> O IP honesto — com `X-Forwarded-For` e `PDFTODXF_PROXIES` — chega na tarefa 4,
> quando `identidade.ip_do_pedido` existir. Aqui vai o endereço da conexão, que
> é o certo em desenvolvimento e o que a tarefa 4 vai substituir numa linha.

No mesmo arquivo, dentro de `_limpeza_periodica`, logo depois do `print` do
relato, acrescente:

```python
            apagados = await asyncio.to_thread(registros.expurgar)
            if apagados:
                print(f"limpeza: {len(apagados)} registros com mais de 1 ano")
```

e acrescente `registros` ao import:

```python
from . import exportacao, jobs, limits, registros, storage
```

- [ ] **Passo 6: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_registros_no_worker.py
```

Esperado: três linhas `OK: ...`.

- [ ] **Passo 7: a etapa 2 não pode ter regredido**

```bash
./.venv/Scripts/python.exe tests/test_api_extracao.py && ./.venv/Scripts/python.exe tests/test_api_geometria.py && ./.venv/Scripts/python.exe tests/test_api_export.py
```

Esperado: as três baterias passam. São elas que exercitam o worker de ponta a
ponta, e a assinatura dele acabou de mudar.

- [ ] **Passo 8: commit**

```bash
git add web/api/jobs.py web/api/main.py tests/test_registros_no_worker.py
git commit -m "Grava o registro no worker e expurga o que passou de 1 ano"
```

---

### Tarefa 3: `db.py` — SQLite, esquema e o segredo

**Arquivos:**
- Criar: `web/api/db.py`
- Modificar: `web/api/main.py` (criar as tabelas na subida; limpar na periódica)
- Testar: `tests/test_db.py`

**Interfaces:**
- Consome: nada do projeto.
- Produz, e as tarefas 4, 5, 7, 8 e 9 dependem destes nomes exatos:
  - `db.caminho() -> Path`
  - `db.conexao() -> sqlite3.Connection` (uma por thread, `row_factory=sqlite3.Row`)
  - `db.criar_tabelas(con) -> None`
  - `db.segredo() -> bytes`
  - `db.marca(valor: str) -> str` (hex de 64)
  - `db.assinar(dados: str) -> str`
  - `db.conferir(assinado: str) -> str | None`
  - `db.limpar(agora: float | None = None) -> dict` com as chaves
    `consumo` e `tokens`
  - `db.fechar() -> None` (só para teste)

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_db.py`:

```python
"""O banco: esquema, conexão por thread, segredo e limpeza."""

import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from web.api import db


def test_as_tabelas_nascem_na_primeira_conexao():
    con = db.conexao()
    nomes = {linha["name"] for linha in
             con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"usuarios", "tokens", "consumo"} <= nomes, nomes
    modo = con.execute("PRAGMA journal_mode").fetchone()[0]
    assert modo.lower() == "wal", modo
    print("OK: as três tabelas nascem na primeira conexão, com WAL")


def test_email_e_unico():
    import sqlite3
    con = db.conexao()
    con.execute("INSERT INTO usuarios (email, senha, criado_em, criado_de) "
                "VALUES (?, ?, ?, ?)", ("a@b.c", "x", time.time(), "ip"))
    con.commit()
    try:
        con.execute("INSERT INTO usuarios (email, senha, criado_em, criado_de) "
                    "VALUES (?, ?, ?, ?)", ("a@b.c", "y", time.time(), "ip"))
        con.commit()
        raise AssertionError("o e-mail repetido tinha que ser recusado")
    except sqlite3.IntegrityError:
        con.rollback()
    print("OK: o e-mail é único")


def test_uma_conexao_por_thread():
    """Sem `check_same_thread=False`: cada fio abre a sua."""
    daqui = db.conexao()
    de_la = []
    fio = threading.Thread(target=lambda: de_la.append(db.conexao()))
    fio.start()
    fio.join()
    assert de_la and de_la[0] is not daqui
    assert db.conexao() is daqui, "no mesmo fio, a conexão se repete"
    print("OK: uma conexão por thread, criada sob demanda")


def test_marca_e_estavel_e_depende_do_segredo():
    a = db.marca("192.168.0.1")
    assert a == db.marca("192.168.0.1")
    assert len(a) == 64 and a != "192.168.0.1"
    os.environ["PDFTODXF_SEGREDO"] = "outro-segredo"
    try:
        assert db.marca("192.168.0.1") != a, "trocar o segredo tem que mudar a marca"
    finally:
        os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"
    print("OK: a marca é estável e muda com o segredo")


def test_assinar_e_conferir():
    assinado = db.assinar("42|1700000000")
    assert db.conferir(assinado) == "42|1700000000"
    corpo, _, assinatura = assinado.partition(".")
    assert db.conferir(corpo + ".00" + assinatura[2:]) is None, "assinatura mexida"
    assert db.conferir("") is None
    assert db.conferir("sem-ponto") is None
    os.environ["PDFTODXF_SEGREDO"] = "outro-segredo"
    try:
        assert db.conferir(assinado) is None, "trocar o segredo invalida"
    finally:
        os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"
    print("OK: assinar e conferir, e a troca do segredo invalida")


def test_limpeza_apaga_consumo_velho_e_token_vencido():
    con = db.conexao()
    agora = time.time()
    con.execute("INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
                "VALUES (?,?,?,?,?)", ("b", "arquivo", "confirmado",
                                       agora - 25 * 3600, "velho"))
    con.execute("INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
                "VALUES (?,?,?,?,?)", ("b", "arquivo", "confirmado",
                                       agora - 60, "novo"))
    con.execute("INSERT INTO tokens (valor, tipo, usuario, expira_em) "
                "VALUES (?,?,?,?)", ("t-velho", "confirmacao", 1, agora - 10))
    con.execute("INSERT INTO tokens (valor, tipo, usuario, expira_em) "
                "VALUES (?,?,?,?)", ("t-novo", "confirmacao", 1, agora + 3600))
    con.commit()

    relato = db.limpar(agora)
    assert relato["consumo"] == 1 and relato["tokens"] == 1, relato
    restantes = {l["referencia"] for l in con.execute("SELECT referencia FROM consumo")}
    assert restantes == {"novo"}, restantes
    vivos = {l["valor"] for l in con.execute("SELECT valor FROM tokens")}
    assert vivos == {"t-novo"}, vivos
    print("OK: a limpeza apaga consumo de mais de 24 h e token vencido")


if __name__ == "__main__":
    test_as_tabelas_nascem_na_primeira_conexao()
    test_email_e_unico()
    test_uma_conexao_por_thread()
    test_marca_e_estavel_e_depende_do_segredo()
    test_assinar_e_conferir()
    test_limpeza_apaga_consumo_velho_e_token_vencido()
    print("Todos os testes do banco passaram.")
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_db.py
```

Esperado: `ModuleNotFoundError: No module named 'web.api.db'`.

- [ ] **Passo 3: escrever `db.py`**

Crie `web/api/db.py`:

```python
"""O banco de contas e consumo, e o segredo que torna suas linhas comparáveis.

SQLite num arquivo só, com WAL. As rotas do FastAPI deste projeto são
síncronas e rodam num pool de threads, então a conexão é **por thread**, criada
sob demanda — `check_same_thread=False` está fora de cogitação: ele silencia o
aviso sem resolver a corrida.

O segredo mora aqui porque ele é a chave dos `hmac` que formam duas **colunas
deste banco**: `consumo.balde` e `usuarios.criado_de`. Trocá-lo derruba as
sessões, zera as cotas de visitante em andamento e a contagem de contas por IP
do dia — nada se perde, as linhas antigas apenas deixam de casar e saem na
limpeza de 24 horas.
"""

from __future__ import annotations

import base64
import hmac
import os
import secrets
import sqlite3
import threading
import time
from hashlib import sha256
from pathlib import Path

PRAZO_DO_CONSUMO_S = 24 * 60 * 60

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    senha         TEXT NOT NULL,
    confirmado_em REAL,
    criado_em     REAL NOT NULL,
    criado_de     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    valor     TEXT PRIMARY KEY,
    tipo      TEXT NOT NULL,
    usuario   INTEGER NOT NULL,
    expira_em REAL NOT NULL,
    usado_em  REAL
);
CREATE TABLE IF NOT EXISTS consumo (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    balde      TEXT NOT NULL,
    tipo       TEXT NOT NULL,
    estado     TEXT NOT NULL,
    quando     REAL NOT NULL,
    referencia TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS i_consumo_janela
    ON consumo (balde, tipo, quando);
CREATE INDEX IF NOT EXISTS i_consumo_referencia
    ON consumo (referencia, estado);
CREATE INDEX IF NOT EXISTS i_usuarios_criado
    ON usuarios (criado_de, criado_em);
"""

_local = threading.local()
_segredo_gerado: bytes | None = None
_avisou = False


def caminho() -> Path:
    p = Path(os.environ.get("PDFTODXF_BANCO", "dados/contas.db"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def criar_tabelas(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)
    con.commit()


def conexao() -> sqlite3.Connection:
    """A conexão deste fio, criada na primeira vez que ele pede.

    O caminho é guardado junto: nos testes o `PDFTODXF_BANCO` muda entre
    arquivos, e uma conexão presa ao banco anterior daria falha muda.
    """
    atual = str(caminho())
    con = getattr(_local, "con", None)
    if con is not None and getattr(_local, "onde", None) == atual:
        return con
    if con is not None:
        con.close()

    con = sqlite3.connect(atual)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    # Escrita curta com WAL basta nesta escala; o `busy_timeout` é o que faz um
    # segundo escritor esperar em vez de voltar "database is locked" na cara do
    # usuário.
    con.execute("PRAGMA busy_timeout=5000")
    criar_tabelas(con)
    _local.con = con
    _local.onde = atual
    return con


def fechar() -> None:
    """Fecha a conexão deste fio. Existe para o teste, não para o serviço."""
    con = getattr(_local, "con", None)
    if con is not None:
        con.close()
        _local.con = None


def segredo() -> bytes:
    """A chave dos `hmac`, de `PDFTODXF_SEGREDO` ou aleatória por subida.

    Ausente, gera uma aleatória e avisa no log. Isso derruba as sessões a cada
    reinício — irrelevante em desenvolvimento, ruim em produção — mas nunca
    entrega um serviço com segredo fixo conhecido, que é o modo de falhar que
    importa.
    """
    global _segredo_gerado, _avisou
    do_ambiente = os.environ.get("PDFTODXF_SEGREDO")
    if do_ambiente:
        return do_ambiente.encode("utf-8")
    if _segredo_gerado is None:
        _segredo_gerado = secrets.token_bytes(32)
    if not _avisou:
        print("PDFTODXF_SEGREDO ausente: usando um segredo aleatorio desta "
              "subida. As sessoes caem a cada reinicio.")
        _avisou = True
    return _segredo_gerado


def marca(valor: str) -> str:
    """`hmac` hexadecimal do valor. É o que vai ao banco no lugar do dado cru."""
    return hmac.new(segredo(), (valor or "").encode("utf-8"), sha256).hexdigest()


def assinar(dados: str) -> str:
    """`<corpo em base64url>.<assinatura>` — o formato dos cookies."""
    corpo = base64.urlsafe_b64encode(dados.encode("utf-8")).decode().rstrip("=")
    return f"{corpo}.{marca(corpo)}"


def conferir(assinado: str) -> str | None:
    """O conteúdo, se a assinatura casar. `None` em qualquer outro caso."""
    corpo, ponto, assinatura = (assinado or "").partition(".")
    if not ponto or not assinatura:
        return None
    # `compare_digest` e não `==`: a comparação byte a byte que sai no primeiro
    # erro conta, pelo tempo, quantos caracteres já estavam certos.
    if not hmac.compare_digest(assinatura, marca(corpo)):
        return None
    try:
        recheio = "=" * (-len(corpo) % 4)
        return base64.urlsafe_b64decode(corpo + recheio).decode("utf-8")
    except Exception:
        return None


def limpar(agora: float | None = None) -> dict:
    """Apaga consumo de mais de 24 h e token vencido. Devolve quantos saíram."""
    agora = time.time() if agora is None else agora
    con = conexao()
    c1 = con.execute("DELETE FROM consumo WHERE quando < ?",
                     (agora - PRAZO_DO_CONSUMO_S,)).rowcount
    c2 = con.execute("DELETE FROM tokens WHERE expira_em < ?", (agora,)).rowcount
    con.commit()
    return {"consumo": c1, "tokens": c2}
```

- [ ] **Passo 4: ligar à subida e à limpeza periódica**

Em `web/api/main.py`, acrescente `db` ao import:

```python
from . import db, exportacao, jobs, limits, registros, storage
```

E, dentro de `ciclo_de_vida`, antes de criar a tarefa:

```python
async def ciclo_de_vida(_app: FastAPI):
    # As tabelas nascem na subida, e não no primeiro pedido: assim um erro de
    # permissão no arquivo do banco aparece ao subir, e não na cara do primeiro
    # usuário.
    await asyncio.to_thread(lambda: db.criar_tabelas(db.conexao()))
    tarefa = asyncio.create_task(_limpeza_periodica())
```

E, dentro de `_limpeza_periodica`, depois do expurgo dos registros:

```python
            do_banco = await asyncio.to_thread(db.limpar)
            if do_banco["consumo"] or do_banco["tokens"]:
                print(f"limpeza: {do_banco['consumo']} consumos e "
                      f"{do_banco['tokens']} tokens vencidos")
```

- [ ] **Passo 5: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_db.py
```

Esperado: seis linhas `OK: ...`.

- [ ] **Passo 6: o serviço ainda sobe**

```bash
./.venv/Scripts/python.exe tests/test_api_estaticos.py && ./.venv/Scripts/python.exe tests/test_api_upload.py
```

Esperado: as duas passam. O `ciclo_de_vida` acabou de ganhar um passo novo, e é
o `TestClient` que o exercita.

- [ ] **Passo 7: commit**

```bash
git add web/api/db.py web/api/main.py tests/test_db.py
git commit -m "Banco SQLite com esquema, conexao por thread e o segredo"
```

---

### Tarefa 4: `identidade.py` — quem está pedindo

**Arquivos:**
- Criar: `web/api/identidade.py`
- Modificar: `web/api/main.py` (`extrair_pagina` passa a usar o IP honesto)
- Testar: `tests/test_identidade.py`

**Interfaces:**
- Consome: `db.marca`, `db.assinar`, `db.conferir` da tarefa 3.
- Produz, e as tarefas 5, 6, 8 e 10 dependem destes nomes exatos:
  - `identidade.COOKIE = "pdftodxf_visitante"`
  - `identidade.Balde` — `NamedTuple(chave: str, folga: int)`
  - `identidade.Dono` — `NamedTuple(id: int, confirmado: bool)`
  - `identidade.Identidade` — `NamedTuple(tipo: str, usuario_id: int | None,
    confirmado: bool, baldes: tuple[Balde, ...], cookie_novo: str | None)`
  - `identidade.ip_do_pedido(request) -> str`
  - `identidade.impressao_do_pedido(request) -> str | None`
  - `identidade.resolver(request, dono: Dono | None = None) -> Identidade`
  - `identidade.gravar_cookie(resposta, ident, seguro=False) -> None`

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_identidade.py`:

```python
"""Quem está pedindo: cookie anônimo, IP com proxies e impressão do navegador."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from web.api import db, identidade


class PedidoFalso:
    """O mínimo de um `Request` que `identidade` lê."""

    def __init__(self, cabecalhos=None, cookies=None, cliente="203.0.113.9"):
        self.headers = {k.lower(): v for k, v in (cabecalhos or {}).items()}
        self.cookies = cookies or {}
        self.client = type("C", (), {"host": cliente})()


def chaves(ident):
    return {b.chave for b in ident.baldes}


def test_visitante_novo_ganha_tres_baldes_e_um_cookie():
    p = PedidoFalso(cabecalhos={"X-Impressao": "b" * 64})
    ident = identidade.resolver(p)
    assert ident.tipo == "visitante"
    assert len(ident.baldes) == 3, ident.baldes
    assert ident.cookie_novo, "visitante sem cookie tem que ganhar um"
    folgas = sorted(b.folga for b in ident.baldes)
    assert folgas[0] == 1 and folgas[1] > 1 and folgas[2] > 1, folgas
    print("OK: visitante novo ganha três baldes e um cookie")


def test_o_mesmo_cookie_da_o_mesmo_balde():
    p = PedidoFalso()
    primeiro = identidade.resolver(p)
    devolta = PedidoFalso(cookies={identidade.COOKIE: primeiro.cookie_novo})
    segundo = identidade.resolver(devolta)
    assert segundo.cookie_novo is None, "cookie válido não é reemitido"
    assert chaves(primeiro) & chaves(segundo), "o balde do cookie tem que casar"
    print("OK: o mesmo cookie devolve o mesmo balde")


def test_cookie_forjado_e_descartado():
    p = PedidoFalso(cookies={identidade.COOKIE: "eu-inventei-isto"})
    ident = identidade.resolver(p)
    assert ident.cookie_novo, "cookie sem assinatura válida vira cookie novo"
    print("OK: cookie forjado é descartado e substituído")


def test_x_forwarded_for_e_ignorado_sem_proxies():
    os.environ["PDFTODXF_PROXIES"] = "0"
    p = PedidoFalso(cabecalhos={"X-Forwarded-For": "1.2.3.4"},
                    cliente="203.0.113.9")
    assert identidade.ip_do_pedido(p) == "203.0.113.9"
    print("OK: X-Forwarded-For forjado é ignorado com PDFTODXF_PROXIES=0")


def test_x_forwarded_for_com_um_proxy():
    os.environ["PDFTODXF_PROXIES"] = "1"
    try:
        p = PedidoFalso(cabecalhos={"X-Forwarded-For": "9.9.9.9, 198.51.100.4"},
                        cliente="127.0.0.1")
        # Com um proxy confiável à frente, o cliente é o último da lista — os
        # anteriores foram escritos por quem quis.
        assert identidade.ip_do_pedido(p) == "198.51.100.4"
        vazio = PedidoFalso(cliente="127.0.0.1")
        assert identidade.ip_do_pedido(vazio) == "127.0.0.1", \
            "sem cabeçalho, sobra o endereço da conexão"
    finally:
        os.environ["PDFTODXF_PROXIES"] = "0"
    print("OK: com um proxy, o IP sai da posição certa")


def test_impressao_malformada_e_ignorada_sem_erro():
    for ruim in ["", "curta", "z" * 64, "A" * 65, "../etc/passwd"]:
        p = PedidoFalso(cabecalhos={"X-Impressao": ruim})
        assert identidade.impressao_do_pedido(p) is None, ruim
        ident = identidade.resolver(p)
        assert len(ident.baldes) == 2, "sem impressão sobram cookie e IP"
    print("OK: impressão malformada é ignorada sem erro e sem bloquear")


def test_logado_tem_um_balde_so():
    p = PedidoFalso(cabecalhos={"X-Impressao": "c" * 64})
    ident = identidade.resolver(p, dono=identidade.Dono(id=7, confirmado=True))
    assert ident.tipo == "logado"
    assert ident.usuario_id == 7 and ident.confirmado is True
    assert len(ident.baldes) == 1 and ident.baldes[0].folga == 1
    assert ident.baldes[0].chave == db.marca("usuario:7")
    print("OK: logado consome um balde só; IP e impressão não entram")


def test_conta_sem_confirmar_continua_identificada():
    p = PedidoFalso()
    ident = identidade.resolver(p, dono=identidade.Dono(id=7, confirmado=False))
    assert ident.tipo == "logado" and ident.confirmado is False
    print("OK: conta sem confirmar continua identificada, mas não confirmada")


if __name__ == "__main__":
    test_visitante_novo_ganha_tres_baldes_e_um_cookie()
    test_o_mesmo_cookie_da_o_mesmo_balde()
    test_cookie_forjado_e_descartado()
    test_x_forwarded_for_e_ignorado_sem_proxies()
    test_x_forwarded_for_com_um_proxy()
    test_impressao_malformada_e_ignorada_sem_erro()
    test_logado_tem_um_balde_so()
    test_conta_sem_confirmar_continua_identificada()
    print("Todos os testes de identidade passaram.")
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_identidade.py
```

Esperado: `ModuleNotFoundError: No module named 'web.api.identidade'`.

- [ ] **Passo 3: escrever `identidade.py`**

Crie `web/api/identidade.py`:

```python
"""Quem está pedindo, e quais baldes de cota aquele pedido consome.

Logado é **um balde só** — a conta já é a identidade, e consultar IP e
impressão faria dois colegas do mesmo escritório dividirem a cota que cada um
pagou com um cadastro.

Visitante são **três**, com tetos diferentes: o cookie carrega a cota
anunciada, e IP e impressão são tetos folgados (`PDFTODXF_COTA_FOLGA`, padrão
4). O pedido passa se os três couberem, e o consumo é gravado nos três. O
cookie sozinho não tapa o furo de limpar o cookie e repetir; o IP sozinho faria
o escritório inteiro dividir cinco arquivos.

**Este módulo não importa `auth`.** Ele precisa saber se há sessão, e `auth`
precisa do IP para o teto de contas por dia — seria um ciclo. Quem chama
resolve a sessão e passa o `dono`.
"""

from __future__ import annotations

import os
import re
import secrets
from typing import NamedTuple

from . import db

COOKIE = "pdftodxf_visitante"
PRAZO_DO_COOKIE_S = 365 * 24 * 60 * 60
FOLGA_PADRAO = 4
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Balde(NamedTuple):
    chave: str          # já com `db.marca` aplicada
    folga: int          # multiplicador do teto deste balde


class Dono(NamedTuple):
    id: int
    confirmado: bool


class Identidade(NamedTuple):
    tipo: str                       # "logado" | "visitante"
    usuario_id: int | None
    confirmado: bool
    baldes: tuple[Balde, ...]
    cookie_novo: str | None         # a gravar na resposta, se houver


def _folga() -> int:
    try:
        valor = int(os.environ.get("PDFTODXF_COTA_FOLGA", FOLGA_PADRAO))
    except ValueError:
        valor = FOLGA_PADRAO
    return max(1, valor)


def ip_do_pedido(request) -> str:
    """O endereço do cliente, contando `X-Forwarded-For` da direita para a esquerda.

    `PDFTODXF_PROXIES` diz quantos proxies confiáveis estão à frente. O padrão
    é `0`: **não confie no cabeçalho**, use o endereço da conexão. Sem esse
    contador qualquer um manda `X-Forwarded-For: 1.2.3.4` e a cota do IP vira
    decorativa — e o erro é silencioso, porque tudo continua funcionando.
    """
    cliente = getattr(request, "client", None)
    direto = cliente.host if cliente else ""
    try:
        proxies = int(os.environ.get("PDFTODXF_PROXIES", "0"))
    except ValueError:
        proxies = 0
    if proxies <= 0:
        return direto
    cru = request.headers.get("x-forwarded-for", "")
    lista = [p.strip() for p in cru.split(",") if p.strip()]
    if len(lista) >= proxies:
        return lista[-proxies]
    return direto


def impressao_do_pedido(request) -> str | None:
    """O hash que o navegador mandou em `X-Impressao`, se for o formato certo.

    Qualquer outro formato é ignorado **sem erro**: navegador com JS desligado,
    extensão de privacidade ou cliente que não manda o cabeçalho ficam com a
    cota do cookie e do IP, que é a cota anunciada. Quem escolhe se proteger
    não pode ser barrado por isso.
    """
    valor = (request.headers.get("x-impressao") or "").strip().lower()
    return valor if _HEX64.match(valor) else None


def _cookie_valido(request) -> str | None:
    guardado = request.cookies.get(COOKIE)
    return db.conferir(guardado) if guardado else None


def resolver(request, dono: Dono | None = None) -> Identidade:
    if dono is not None:
        return Identidade(tipo="logado", usuario_id=dono.id,
                          confirmado=dono.confirmado,
                          baldes=(Balde(db.marca(f"usuario:{dono.id}"), 1),),
                          cookie_novo=None)

    valor = _cookie_valido(request)
    cookie_novo = None
    if valor is None:
        valor = secrets.token_urlsafe(24)
        cookie_novo = db.assinar(valor)

    folga = _folga()
    baldes = [Balde(db.marca(f"cookie:{valor}"), 1)]
    ip = ip_do_pedido(request)
    if ip:
        baldes.append(Balde(db.marca(f"ip:{ip}"), folga))
    impressao = impressao_do_pedido(request)
    if impressao:
        baldes.append(Balde(db.marca(f"impressao:{impressao}"), folga))

    return Identidade(tipo="visitante", usuario_id=None, confirmado=False,
                      baldes=tuple(baldes), cookie_novo=cookie_novo)


def gravar_cookie(resposta, ident: Identidade, seguro: bool = False) -> None:
    """Grava o cookie do visitante, se ele for novo. Idempotente."""
    if not ident.cookie_novo:
        return
    resposta.set_cookie(COOKIE, ident.cookie_novo, max_age=PRAZO_DO_COOKIE_S,
                        httponly=True, samesite="lax", secure=seguro, path="/")
```

- [ ] **Passo 4: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_identidade.py
```

Esperado: oito linhas `OK: ...`.

- [ ] **Passo 5: o IP honesto entra na rota de extração**

Em `web/api/main.py`, acrescente `identidade` ao import:

```python
from . import db, exportacao, identidade, jobs, limits, registros, storage
```

e troque a linha do IP em `extrair_pagina`:

```python
    ip = identidade.ip_do_pedido(request)
```

- [ ] **Passo 6: conferir que a extração continua inteira**

```bash
./.venv/Scripts/python.exe tests/test_registros_no_worker.py && ./.venv/Scripts/python.exe tests/test_api_extracao.py
```

Esperado: as duas passam.

- [ ] **Passo 7: commit**

```bash
git add web/api/identidade.py web/api/main.py tests/test_identidade.py
git commit -m "Identidade: cookie anonimo, IP com proxies e impressao"
```

---

### Tarefa 5: `quotas.py` — janela deslizante, reserva e confirmação

**Arquivos:**
- Criar: `web/api/quotas.py`
- Testar: `tests/test_quotas.py`

**Interfaces:**
- Consome: `db.conexao`, `db.marca` (tarefa 3); `identidade.Identidade` e
  `identidade.Balde` (tarefa 4); `limits.TETO_PDF_BYTES` (`web/api/limits.py:9`).
- Produz, e as tarefas 6 e 10 dependem destes nomes exatos:
  - `quotas.SemVaga(Exception)` com `.tipo: str` e `.libera_em: float | None`
  - `quotas.janela_s() -> int`
  - `quotas.limites(ident) -> dict` com `arquivos`, `downloads`, `bytes`
  - `quotas.reservar(ident, tipo, referencia, agora=None) -> None`
  - `quotas.cobrar(ident, tipo, referencia, agora=None) -> None`
  - `quotas.confirmar(referencia) -> None`
  - `quotas.soltar(referencia) -> None`
  - `quotas.restante(ident, tipo, agora=None) -> tuple[int | None, float | None]`
  - `tipo` vale `"arquivo"` ou `"download"`, e nada mais.

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_quotas.py`:

```python
"""A cota: janela deslizante, reserva, confirmação e as chaves de configuração."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from web.api import db, identidade, limits, quotas

AGORA = 1_755_000_000.0


def visitante(cookie: str, ip: str = "198.51.100.1") -> identidade.Identidade:
    return identidade.Identidade(
        tipo="visitante", usuario_id=None, confirmado=False,
        baldes=(identidade.Balde(db.marca(f"cookie:{cookie}"), 1),
                identidade.Balde(db.marca(f"ip:{ip}"), 4)),
        cookie_novo=None)


def logado(uid: int, confirmado: bool = True) -> identidade.Identidade:
    return identidade.Identidade(
        tipo="logado", usuario_id=uid, confirmado=confirmado,
        baldes=(identidade.Balde(db.marca(f"usuario:{uid}"), 1),),
        cookie_novo=None)


def limpar_tudo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def test_visitante_envia_cinco_e_para_no_sexto():
    limpar_tudo()
    quem = visitante("c1")
    for i in range(5):
        quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
    try:
        quotas.reservar(quem, "arquivo", "job5", AGORA)
        raise AssertionError("o sexto tinha que ser recusado")
    except quotas.SemVaga as e:
        assert e.tipo == "arquivo"
        assert e.libera_em and e.libera_em > AGORA
    print("OK: visitante envia 5 arquivos e é barrado no sexto")


def test_limpar_o_cookie_nao_devolve_cota():
    """O balde do IP continua contando, e é ele que tapa o furo do cookie."""
    limpar_tudo()
    for i in range(5):
        quotas.reservar(visitante("c1"), "arquivo", f"job{i}", AGORA)
    # Cookie novo, mesmo IP: cabe, porque o IP tem folga de 4x (teto 20).
    quotas.reservar(visitante("c2"), "arquivo", "job5", AGORA)

    for i in range(6, 20):
        quotas.reservar(visitante(f"c{i}"), "arquivo", f"job{i}", AGORA)
    try:
        quotas.reservar(visitante("c-final"), "arquivo", "job20", AGORA)
        raise AssertionError("o vigésimo primeiro tinha que ser recusado")
    except quotas.SemVaga:
        pass
    print("OK: limpar o cookie não devolve cota; o IP barra no 21º")


def test_a_janela_desliza():
    limpar_tudo()
    quem = visitante("c1")
    velho = AGORA - quotas.janela_s() - 1
    for i in range(5):
        quotas.reservar(quem, "arquivo", f"job{i}", velho)
    quotas.reservar(quem, "arquivo", "novo", AGORA)
    restam, _ = quotas.restante(quem, "arquivo", AGORA)
    assert restam == 4, restam
    print("OK: a janela desliza — consumo de 2 h e 1 s atrás não conta")


def test_confirmar_e_soltar_sao_de_mao_unica():
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "arquivo", "jobA", AGORA)

    # Página ruim antes de qualquer boa: solta.
    quotas.soltar("jobA")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 5

    # Boa e depois ruim: a ruim não desfaz.
    quotas.reservar(quem, "arquivo", "jobB", AGORA)
    quotas.confirmar("jobB")
    quotas.soltar("jobB")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4, "confirmado não solta"

    quotas.confirmar("jobB")
    assert quotas.restante(quem, "arquivo", AGORA)[0] == 4, "confirmar não cobra"
    print("OK: confirmar e soltar são de mão única e idempotentes")


def test_a_mesma_referencia_nao_cobra_duas_vezes():
    limpar_tudo()
    quem = visitante("c1")
    quotas.reservar(quem, "download", "jobA:chave1", AGORA)
    quotas.reservar(quem, "download", "jobA:chave1", AGORA)
    restam, _ = quotas.restante(quem, "download", AGORA)
    assert restam == 14, restam
    print("OK: a mesma referência não cobra duas vezes")


def test_downloads_do_visitante_param_no_decimo_sexto():
    limpar_tudo()
    quem = visitante("c1")
    for i in range(15):
        quotas.cobrar(quem, "download", f"jobA:{i}", AGORA)
    try:
        quotas.cobrar(quem, "download", "jobA:16", AGORA)
        raise AssertionError("o décimo sexto tinha que ser recusado")
    except quotas.SemVaga as e:
        assert e.tipo == "download"
    print("OK: visitante baixa 15 combinações inéditas e para na décima sexta")


def test_logado_tem_o_triplo():
    limpar_tudo()
    quem = logado(1)
    assert quotas.limites(quem)["arquivos"] == 15
    assert quotas.limites(quem)["downloads"] == 45
    for i in range(15):
        quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
    try:
        quotas.reservar(quem, "arquivo", "job15", AGORA)
        raise AssertionError("o décimo sexto tinha que ser recusado")
    except quotas.SemVaga:
        pass
    print("OK: logado tem o triplo da cota do visitante")


def test_chave_em_zero_nao_limita_e_ausente_cai_no_padrao():
    limpar_tudo()
    quem = visitante("c1")
    os.environ["PDFTODXF_COTA_ARQUIVOS"] = "0"
    try:
        for i in range(30):
            quotas.reservar(quem, "arquivo", f"job{i}", AGORA)
        restam, libera = quotas.restante(quem, "arquivo", AGORA)
        assert restam is None and libera is None, (restam, libera)
    finally:
        del os.environ["PDFTODXF_COTA_ARQUIVOS"]
    assert quotas.limites(visitante("c9"))["arquivos"] == 5, "ausente cai no padrão"
    print("OK: chave em 0 não limita; chave ausente cai no padrão")


def test_teto_de_mb_do_logado_e_truncado_no_teto_tecnico():
    os.environ["PDFTODXF_COTA_MB_LOGADO"] = "500"
    try:
        assert quotas.limites(logado(1))["bytes"] == limits.TETO_PDF_BYTES
    finally:
        del os.environ["PDFTODXF_COTA_MB_LOGADO"]
    assert quotas.limites(visitante("c1"))["bytes"] == 10 * 1024 * 1024
    print("OK: o teto de MB do logado nunca passa do teto técnico")


def test_conta_sem_confirmar_tem_cota_de_visitante():
    quem = logado(3, confirmado=False)
    assert quotas.limites(quem)["arquivos"] == 5
    assert quotas.limites(quem)["bytes"] == 10 * 1024 * 1024
    print("OK: conta sem confirmar fica com a cota de visitante")


if __name__ == "__main__":
    test_visitante_envia_cinco_e_para_no_sexto()
    test_limpar_o_cookie_nao_devolve_cota()
    test_a_janela_desliza()
    test_confirmar_e_soltar_sao_de_mao_unica()
    test_a_mesma_referencia_nao_cobra_duas_vezes()
    test_downloads_do_visitante_param_no_decimo_sexto()
    test_logado_tem_o_triplo()
    test_chave_em_zero_nao_limita_e_ausente_cai_no_padrao()
    test_teto_de_mb_do_logado_e_truncado_no_teto_tecnico()
    test_conta_sem_confirmar_tem_cota_de_visitante()
    print("Todos os testes de cota passaram.")
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_quotas.py
```

Esperado: `ModuleNotFoundError: No module named 'web.api.quotas'`.

- [ ] **Passo 3: escrever `quotas.py`**

Crie `web/api/quotas.py`:

```python
"""Pode? — a cota por janela deslizante.

Um registro por consumo, com a hora. A cota disponível é o limite menos o que
foi consumido na janela: **não existe virada em horário fixo**, e por isso não
existe a meia-noite em que todo mundo volta a enviar de uma vez.

Reservar e confirmar são coisas separadas porque PDF sem vetores e worker morto
por recurso não podem consumir cota. A transição é de mão única e idempotente,
e é isso que faz o caso misto sair certo: num documento em que a página 1 é
escaneada e a página 2 tem vetores, a página 1 solta e a página 2 cobra; na
ordem inversa, a página 2 confirma e a página 1 não desfaz.

Reserva nunca confirmada **continua contando** até sair da janela. Quem envia e
fecha a aba consumiu banda e disco; não há varredura de reserva órfã, porque a
janela deslizante já é o prazo.
"""

from __future__ import annotations

import os
import time

from . import db, limits

PADROES = {
    "arquivos": 5,
    "downloads": 15,
    "mb": 10,
    "arquivos_logado": 15,
    "downloads_logado": 45,
    "mb_logado": 100,
    "janela_h": 2,
}


class SemVaga(Exception):
    """Não cabe nesta janela. `libera_em` é quando a próxima vaga abre."""

    def __init__(self, tipo: str, libera_em: float | None):
        super().__init__(tipo, libera_em)
        self.tipo = tipo
        self.libera_em = libera_em


def _chave(nome: str) -> int:
    """O valor de `PDFTODXF_COTA_<NOME>`, ou o padrão. `0` é sem limite."""
    cru = os.environ.get(f"PDFTODXF_COTA_{nome.upper()}")
    if cru is None or cru.strip() == "":
        return PADROES[nome]
    try:
        return max(0, int(cru))
    except ValueError:
        # Chave escrita errada cai no padrão, que é seguro — e não em
        # "sem limite", que seria o modo de falhar caro.
        return PADROES[nome]


def janela_s() -> int:
    horas = _chave("janela_h") or PADROES["janela_h"]
    return horas * 60 * 60


def limites(ident) -> dict:
    """Os tetos do plano de quem está pedindo.

    Conta sem o endereço confirmado tem cota de visitante — é o que faz a
    confirmação valer alguma coisa.
    """
    if ident.tipo == "logado" and ident.confirmado:
        mb = _chave("mb_logado")
        return {
            "arquivos": _chave("arquivos_logado"),
            "downloads": _chave("downloads_logado"),
            # Nunca acima do teto técnico: a chave é do plano, o teto é do
            # servidor. Deixar a chave passar por cima abriria um caminho de
            # derrubar o site por configuração.
            "bytes": min(mb * 1024 * 1024, limits.TETO_PDF_BYTES),
        }
    mb = _chave("mb")
    return {
        "arquivos": _chave("arquivos"),
        "downloads": _chave("downloads"),
        "bytes": min(mb * 1024 * 1024, limits.TETO_PDF_BYTES),
    }


def _teto(ident, tipo: str, balde) -> int:
    base = limites(ident)["arquivos" if tipo == "arquivo" else "downloads"]
    return 0 if base == 0 else base * balde.folga


def _contar(con, balde: str, tipo: str, desde: float) -> int:
    linha = con.execute(
        "SELECT count(*) AS n FROM consumo "
        "WHERE balde = ? AND tipo = ? AND quando > ?",
        (balde, tipo, desde)).fetchone()
    return int(linha["n"])


def _libera_em(con, balde: str, tipo: str, desde: float) -> float | None:
    """Quando abre a próxima vaga: a linha mais antiga da janela + a janela."""
    linha = con.execute(
        "SELECT min(quando) AS q FROM consumo "
        "WHERE balde = ? AND tipo = ? AND quando > ?",
        (balde, tipo, desde)).fetchone()
    return None if linha["q"] is None else float(linha["q"]) + janela_s()


def _consumir(ident, tipo: str, referencia: str, estado: str,
              agora: float | None) -> None:
    agora = time.time() if agora is None else agora
    desde = agora - janela_s()
    con = db.conexao()

    # `BEGIN IMMEDIATE`: contar e inserir têm de ser um passo só. Sem isso dois
    # envios simultâneos do mesmo visitante contam 4 cada um e gravam os dois,
    # e a sexta vaga aparece do nada.
    con.execute("BEGIN IMMEDIATE")
    try:
        ja = con.execute(
            "SELECT count(*) AS n FROM consumo WHERE referencia = ? AND tipo = ?",
            (referencia, tipo)).fetchone()
        if int(ja["n"]) > 0:
            # Referência já cobrada: repetir o pedido não custa de novo. É o
            # que faz clique duplicado e reenvio saírem de graça.
            con.execute("COMMIT")
            return

        for balde in ident.baldes:
            teto = _teto(ident, tipo, balde)
            if teto == 0:
                continue
            if _contar(con, balde.chave, tipo, desde) >= teto:
                libera = _libera_em(con, balde.chave, tipo, desde)
                con.execute("ROLLBACK")
                # Qual balde estourou não sai daqui: dizer isso conta a quem
                # tenta burlar exatamente o que ele precisa saber.
                raise SemVaga(tipo, libera)

        con.executemany(
            "INSERT INTO consumo (balde, tipo, estado, quando, referencia) "
            "VALUES (?, ?, ?, ?, ?)",
            [(b.chave, tipo, estado, agora, referencia) for b in ident.baldes])
        con.execute("COMMIT")
    except SemVaga:
        raise
    except Exception:
        con.execute("ROLLBACK")
        raise


def reservar(ident, tipo: str, referencia: str, agora=None) -> None:
    """Guarda a vaga. Levanta `SemVaga` se não couber."""
    _consumir(ident, tipo, referencia, "reservado", agora)


def cobrar(ident, tipo: str, referencia: str, agora=None) -> None:
    """Consome de vez, sem passar por reserva. Levanta `SemVaga` se não couber."""
    _consumir(ident, tipo, referencia, "confirmado", agora)


def confirmar(referencia: str) -> None:
    """Promove as reservas daquela referência. Uma vez confirmado, nada solta."""
    con = db.conexao()
    con.execute("UPDATE consumo SET estado = 'confirmado' "
                "WHERE referencia = ? AND estado = 'reservado'", (referencia,))
    con.commit()


def soltar(referencia: str) -> None:
    """Devolve as vagas ainda reservadas. Não mexe no que já foi confirmado."""
    con = db.conexao()
    con.execute("DELETE FROM consumo "
                "WHERE referencia = ? AND estado = 'reservado'", (referencia,))
    con.commit()


def restante(ident, tipo: str, agora=None) -> tuple[int | None, float | None]:
    """`(quantas vagas restam, quando libera a próxima)`.

    `(None, None)` quando o tipo está sem limite — e não um número grande, que
    a tela mostraria como se fosse cota. O balde mais apertado é o que manda,
    porque é ele que vai recusar.
    """
    agora = time.time() if agora is None else agora
    desde = agora - janela_s()
    con = db.conexao()

    sobra: int | None = None
    libera: float | None = None
    for balde in ident.baldes:
        teto = _teto(ident, tipo, balde)
        if teto == 0:
            continue
        livre = max(0, teto - _contar(con, balde.chave, tipo, desde))
        if sobra is None or livre < sobra:
            sobra = livre
            libera = (_libera_em(con, balde.chave, tipo, desde)
                      if livre == 0 else None)
    return sobra, libera
```

- [ ] **Passo 4: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_quotas.py
```

Esperado: dez linhas `OK: ...`.

- [ ] **Passo 5: commit**

```bash
git add web/api/quotas.py tests/test_quotas.py
git commit -m "Cota por janela deslizante, com reserva e confirmacao"
```

---

### Tarefa 6: ligar a cota ao envio e à exportação

**Arquivos:**
- Modificar: `web/api/main.py` (`enviar`, `exportar`, e a exceção `Recusa`)
- Modificar: `web/api/jobs.py` (`_quando_terminar` confirma ou solta)
- Testar: `tests/test_api_cotas.py`

**Interfaces:**
- Consome: `identidade.resolver`, `identidade.gravar_cookie` (tarefa 4);
  `quotas.reservar`, `quotas.cobrar`, `quotas.confirmar`, `quotas.soltar`,
  `quotas.limites`, `quotas.SemVaga` (tarefa 5); `exportacao.chave` e
  `exportacao.caminho_do_dxf` (`web/api/exportacao.py:29` e `:55`).
- Produz, e as tarefas 10 e 12 dependem disto:
  - `main.Recusa(Exception)` com `status`, `detail`, `codigo` e `extra: dict`
  - O corpo de toda recusa de cota: `{"detail": …, "codigo": "cota_arquivos" |
    "cota_downloads", "libera_em": <epoch ou null>}`
  - O corpo da recusa por tamanho: `{"detail": …, "codigo": "tamanho",
    "teto_bytes": <int>}`

> **A ordem no `export` é lei, e está aqui a razão de cada passo:** calcula a
> chave, olha se o arquivo já existe, e **só então** consulta a cota. Combinação
> já gerada nem chega a perguntar se há vaga — é isso que faz repetir sair de
> graça, e é por isso que conexão que cai, clique duplicado e download perdido
> não custam nada. Gerar primeiro e cobrar depois faria uma planta grande
> queimar CPU para terminar em 429.

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_api_cotas.py`:

```python
"""A cota vista pelas rotas: 429 no envio, 429 no download, 413 por tamanho."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
if "PDFTODXF_REGISTROS" not in os.environ:
    os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial, esperar
from web.api import db, quotas
from web.api.main import app

PEDIDO = {"escala": 0.01, "unidade": "m", "opcoes": {}}


def cliente_novo() -> TestClient:
    """Cliente com pote de cookies próprio: é um visitante diferente."""
    return TestClient(app)


def limpar_consumo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def enviar_com(cliente, dados=None):
    return cliente.post("/api/jobs", files={
        "arquivo": ("planta.pdf", dados or bytes_do_pdf_vetorial(),
                    "application/pdf")})


def test_visitante_e_barrado_no_sexto_envio():
    limpar_consumo()
    cliente = cliente_novo()
    for i in range(5):
        r = enviar_com(cliente)
        assert r.status_code == 200, (i, r.status_code, r.text)

    r = enviar_com(cliente)
    assert r.status_code == 429, r.status_code
    corpo = r.json()
    assert corpo["codigo"] == "cota_arquivos", corpo
    assert corpo["libera_em"], corpo
    # A mensagem não conta qual balde estourou.
    assert "cookie" not in r.text.lower() and "ip" not in corpo["detail"].lower()
    print("OK: o sexto envio do visitante responde 429 com codigo e libera_em")


def test_o_cookie_do_visitante_e_gravado_no_primeiro_envio():
    limpar_consumo()
    cliente = cliente_novo()
    r = enviar_com(cliente)
    assert r.status_code == 200
    from web.api.identidade import COOKIE
    assert COOKIE in cliente.cookies, dict(cliente.cookies)
    print("OK: o cookie do visitante é gravado no primeiro envio")


def test_pdf_sem_vetores_solta_a_reserva():
    limpar_consumo()
    cliente = cliente_novo()
    # Um PDF válido e sem desenho vetorial: a extração falha com sem_vetores.
    import fitz
    doc = fitz.open()
    doc.new_page()
    vazio = doc.tobytes()
    doc.close()

    r = enviar_com(cliente, vazio)
    assert r.status_code == 200, r.text
    job = r.json()["job_id"]
    cliente.post(f"/api/jobs/{job}/pages/1")
    final = esperar(job, 1)
    assert final["situacao"] == "erro" and final["codigo"] == "sem_vetores", final

    # A vaga voltou: cinco envios bons ainda cabem.
    for i in range(5):
        assert enviar_com(cliente).status_code == 200, i
    print("OK: PDF sem vetores solta a reserva")


def test_pagina_boa_confirma_e_pagina_ruim_depois_nao_desfaz():
    limpar_consumo()
    cliente = cliente_novo()
    r = enviar_com(cliente)
    job = r.json()["job_id"]
    cliente.post(f"/api/jobs/{job}/pages/1")
    assert esperar(job, 1)["situacao"] == "pronta"

    # Uma página inexistente não solta nada — e nem chega ao worker.
    cliente.post(f"/api/jobs/{job}/pages/99")

    con = db.conexao()
    estados = {l["estado"] for l in con.execute(
        "SELECT estado FROM consumo WHERE referencia = ?", (job,))}
    assert estados == {"confirmado"}, estados
    print("OK: a página boa confirma, e o que vem depois não desfaz")


def test_combinacao_repetida_nao_consome_download():
    limpar_consumo()
    cliente = cliente_novo()
    job = enviar_com(cliente).json()["job_id"]
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)

    a = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
    assert a.status_code == 200 and a.json()["cache"] is False
    b = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
    assert b.status_code == 200 and b.json()["cache"] is True

    con = db.conexao()
    n = con.execute("SELECT count(*) AS n FROM consumo WHERE tipo = 'download'"
                    ).fetchone()["n"]
    # Dois baldes (cookie e IP), um consumo só: a segunda vez não cobrou.
    assert n == 2, n

    # Mudar qualquer campo cobra de novo.
    outro = {**PEDIDO, "unidade": "cm"}
    c = cliente.post(f"/api/jobs/{job}/pages/1/export", json=outro)
    assert c.status_code == 200 and c.json()["cache"] is False
    n2 = con.execute("SELECT count(*) AS n FROM consumo WHERE tipo = 'download'"
                     ).fetchone()["n"]
    assert n2 == 4, n2
    print("OK: repetir a combinação não consome; mudar um campo consome")


def test_baixar_o_arquivo_nunca_cobra():
    limpar_consumo()
    cliente = cliente_novo()
    job = enviar_com(cliente).json()["job_id"]
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    url = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO).json()["url"]

    con = db.conexao()
    antes = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]
    for _ in range(3):
        assert cliente.get(url).status_code == 200
    depois = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]
    assert antes == depois, (antes, depois)
    print("OK: GET /api/download nunca cobra")


def test_navegar_e_extrair_nao_consomem():
    limpar_consumo()
    cliente = cliente_novo()
    job = enviar_com(cliente).json()["job_id"]
    con = db.conexao()
    antes = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]

    cliente.get(f"/api/jobs/{job}")
    cliente.post(f"/api/jobs/{job}/pages/1")
    esperar(job, 1)
    cliente.get(f"/api/jobs/{job}/pages/1")
    cliente.get(f"/api/jobs/{job}/pages/1/meta.json")
    cliente.get(f"/api/jobs/{job}/pages/1/geometry.bin?parte=esqueleto")

    depois = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]
    assert antes == depois, (antes, depois)
    print("OK: navegar, extrair e baixar geometria não consomem cota")


def test_pdf_acima_do_teto_do_plano_e_recusado_com_o_numero():
    limpar_consumo()
    cliente = cliente_novo()
    os.environ["PDFTODXF_COTA_MB"] = "1"
    try:
        grande = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)
        r = cliente.post("/api/jobs", files={
            "arquivo": ("grande.pdf", grande, "application/pdf")})
        assert r.status_code == 413, r.status_code
        corpo = r.json()
        assert corpo["codigo"] == "tamanho", corpo
        assert corpo["teto_bytes"] == 1024 * 1024, corpo
    finally:
        del os.environ["PDFTODXF_COTA_MB"]
    # Recusado antes de reservar: nenhuma linha de consumo foi gravada.
    con = db.conexao()
    n = con.execute("SELECT count(*) AS n FROM consumo").fetchone()["n"]
    assert n == 0, n
    print("OK: PDF acima do teto do plano é 413 com o teto em bytes, sem cobrar")


def test_download_esgotado_responde_429():
    limpar_consumo()
    cliente = cliente_novo()
    os.environ["PDFTODXF_COTA_DOWNLOADS"] = "1"
    try:
        job = enviar_com(cliente).json()["job_id"]
        cliente.post(f"/api/jobs/{job}/pages/1")
        esperar(job, 1)
        assert cliente.post(f"/api/jobs/{job}/pages/1/export",
                            json=PEDIDO).status_code == 200
        r = cliente.post(f"/api/jobs/{job}/pages/1/export",
                         json={**PEDIDO, "unidade": "cm"})
        assert r.status_code == 429, r.status_code
        assert r.json()["codigo"] == "cota_downloads", r.json()

        # Repetir a combinação já gerada continua livre, mesmo sem vaga.
        de_novo = cliente.post(f"/api/jobs/{job}/pages/1/export", json=PEDIDO)
        assert de_novo.status_code == 200 and de_novo.json()["cache"] is True
    finally:
        del os.environ["PDFTODXF_COTA_DOWNLOADS"]
    print("OK: download esgotado é 429, e repetir o que já existe continua livre")


if __name__ == "__main__":
    test_visitante_e_barrado_no_sexto_envio()
    test_o_cookie_do_visitante_e_gravado_no_primeiro_envio()
    test_pdf_sem_vetores_solta_a_reserva()
    test_pagina_boa_confirma_e_pagina_ruim_depois_nao_desfaz()
    test_combinacao_repetida_nao_consome_download()
    test_baixar_o_arquivo_nunca_cobra()
    test_navegar_e_extrair_nao_consomem()
    test_pdf_acima_do_teto_do_plano_e_recusado_com_o_numero()
    test_download_esgotado_responde_429()
    print("Todos os testes de cota nas rotas passaram.")
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_api_cotas.py
```

Esperado: FALHA no primeiro teste — o sexto envio responde 200, porque ninguém
consulta cota ainda.

- [ ] **Passo 3: a recusa com corpo próprio**

Em `web/api/main.py`, logo depois do `_erro_de_validacao`, acrescente:

```python
class Recusa(Exception):
    """Recusa com `codigo` no corpo, e não só `detail`.

    O `HTTPException` do FastAPI só sabe pôr `detail`, e a tela precisa
    distinguir "cota de arquivos" de "cota de downloads" sem ler texto — texto
    muda, código não. O `extra` é o que cada recusa acrescenta: `libera_em` na
    cota, `teto_bytes` no tamanho.
    """

    def __init__(self, status: int, detail: str, codigo: str, **extra):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.codigo = codigo
        self.extra = extra


@app.exception_handler(Recusa)
def _recusa(request: Request, exc: Recusa):
    return JSONResponse(status_code=exc.status,
                        content={"detail": exc.detail, "codigo": exc.codigo,
                                 **exc.extra})


def _sem_vaga(e: quotas.SemVaga) -> Recusa:
    quando = ""
    if e.libera_em:
        # Hora local do servidor, que é a do usuário nesta implantação. A tela
        # reformata a partir de `libera_em`; este texto é o que sobra para quem
        # lê a resposta crua.
        quando = time.strftime(" A próxima vaga abre às %H:%M.",
                               time.localtime(e.libera_em))
    if e.tipo == "arquivo":
        detalhe = ("Você já enviou o máximo de arquivos permitido nas últimas "
                   "horas." + quando)
        return Recusa(429, detalhe, "cota_arquivos", libera_em=e.libera_em)
    detalhe = ("Você já gerou o máximo de arquivos DXF permitido nas últimas "
               "horas. Baixar de novo um DXF que você já gerou continua "
               "liberado." + quando)
    return Recusa(429, detalhe, "cota_downloads", libera_em=e.libera_em)
```

Acrescente ao topo do arquivo `import time` e o import dos módulos novos:

```python
from . import (db, exportacao, identidade, jobs, limits, quotas, registros,
               storage)
```

- [ ] **Passo 4: o envio resolve identidade, confere o tamanho e reserva**

Em `web/api/main.py`, substitua a rota `enviar` inteira por:

```python
@app.post("/api/jobs")
async def enviar(request: Request, resposta: Response,
                 arquivo: UploadFile = File(...)) -> dict:
    """Recebe o PDF, confere o teto do plano, reserva a vaga e conta as páginas."""
    ident = identidade.resolver(request)
    identidade.gravar_cookie(resposta, ident,
                             seguro=request.url.scheme == "https")
    teto = quotas.limites(ident)["bytes"]

    # O `content-length` primeiro, e o teto de novo durante a leitura. O
    # primeiro recusa sem receber byte nenhum, que é o que a spec pede; o
    # segundo é a rede de segurança para quem mente no cabeçalho ou não o
    # manda.
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > teto:
        raise Recusa(413, f"O arquivo passa de {_mb(teto)} MB.", "tamanho",
                     teto_bytes=teto)

    job_id = storage.novo_id()
    try:
        quotas.reservar(ident, "arquivo", job_id)
    except quotas.SemVaga as e:
        raise _sem_vaga(e)

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
                if total > teto:
                    raise Recusa(413, f"O arquivo passa de {_mb(teto)} MB.",
                                 "tamanho", teto_bytes=teto)
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
        # O envio não virou trabalho nenhum: nada foi extraído, e a reserva não
        # tem mais o que confirmar. A vaga volta. Reserva que **fica** contando
        # é a de quem enviou um PDF bom e sumiu — essa consumiu disco e fila.
        quotas.soltar(job_id)
        raise

    nome = os.path.basename(arquivo.filename or "planta.pdf")
    ficha = storage.criar_trabalho(job_id, nome, n_paginas, total)
    return {"job_id": job_id, "n_paginas": n_paginas, "nome": ficha["nome"]}
```

E acrescente `Response` ao import do FastAPI:

```python
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
```

- [ ] **Passo 5: o resultado da página confirma ou solta**

Em `web/api/jobs.py`, dentro de `_quando_terminar`, logo depois do bloco de
`except` e **antes** do `try` que grava o estado, acrescente:

```python
    # A primeira página boa promove a reserva; a primeira ruim a solta — e
    # `soltar` não mexe no que já foi confirmado. É de mão única e idempotente
    # de propósito: num documento com uma página escaneada e outra vetorial, a
    # ordem em que elas terminam não pode mudar o que o usuário paga.
    try:
        if estado.get("situacao") == "pronta":
            quotas.confirmar(job_id)
        else:
            quotas.soltar(job_id)
    except Exception as e:
        # A cota não pode derrubar a entrega da página. Uma reserva que ficou
        # em pé custa uma vaga por 2 horas; uma página perdida custa a planta.
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
```

e acrescente `quotas` ao import do topo:

```python
from . import limits, packing, quotas, registros, storage
```

- [ ] **Passo 6: a exportação cobra só a combinação inédita**

Em `web/api/main.py`, substitua a rota `exportar` inteira por:

```python
@app.post("/api/jobs/{job_id}/pages/{pagina}/export")
def exportar(job_id: str, pagina: int, pedido: PedidoDeExportacao,
             request: Request, resposta: Response) -> dict:
    # Pelo cache.pickle e não pela pasta: é dele que a exportação vive, e sem a
    # conferência o `pickle.load` estouraria num 500 sem explicação.
    _arquivo_da_pagina(job_id, pagina, "cache.pickle")

    opcoes = pedido.opcoes.model_dump()
    ch = exportacao.chave(pagina, pedido.escala, pedido.unidade, opcoes)

    # A ordem é lei: chave, arquivo, e só então cota. Combinação já gerada nem
    # pergunta se há vaga — é o que faz repetir sair de graça. Consultar a cota
    # antes recusaria a reexportação de quem está sem vaga, contrariando a
    # promessa; gerar antes queimaria CPU para terminar em 429.
    ja_existe = exportacao.caminho_do_dxf(job_id, pagina, ch).exists()
    referencia = f"{job_id}:{ch}"

    if not ja_existe:
        ident = identidade.resolver(request)
        identidade.gravar_cookie(resposta, ident,
                                 seguro=request.url.scheme == "https")
        try:
            quotas.reservar(ident, "download", referencia)
        except quotas.SemVaga as e:
            raise _sem_vaga(e)

    try:
        ch, _caminho, do_cache, entidades = exportacao.gerar(
            job_id, pagina, pedido.escala, pedido.unidade, opcoes)
    except Exception:
        # Falhou ao gerar: o usuário não levou DXF nenhum, e não paga por isso.
        quotas.soltar(referencia)
        raise

    if not ja_existe:
        quotas.confirmar(referencia)
    return {
        "chave": ch,
        "url": f"/api/download/{job_id}/{ch}",
        "cache": do_cache,
        "entidades": entidades,
    }
```

- [ ] **Passo 7: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_api_cotas.py
```

Esperado: nove linhas `OK: ...`.

- [ ] **Passo 8: a etapa 2 inteira não pode ter regredido**

```bash
./.venv/Scripts/python.exe tests/test_api_upload.py && ./.venv/Scripts/python.exe tests/test_api_extracao.py && ./.venv/Scripts/python.exe tests/test_api_geometria.py && ./.venv/Scripts/python.exe tests/test_api_export.py && ./.venv/Scripts/python.exe tests/test_registros_no_worker.py
```

Esperado: as cinco passam. `test_api_upload.py` e `test_api_export.py` enviam
vários arquivos numa mesma execução — se a cota padrão de 5 barrar algum deles,
**não afrouxe o padrão**: ponha `os.environ["PDFTODXF_COTA_ARQUIVOS"] = "0"` e
`PDFTODXF_COTA_DOWNLOADS = "0"` no topo daqueles dois arquivos, junto do
`PDFTODXF_DADOS`, com um comentário dizendo que ali se testa outra coisa.

- [ ] **Passo 9: commit**

```bash
git add web/api/main.py web/api/jobs.py tests/test_api_cotas.py tests/test_api_upload.py tests/test_api_export.py
git commit -m "Cobra cota no envio e na exportacao, com 429 e 413 explicados"
```

---

### Tarefa 7: `enviador.py` e o cadastro com confirmação

**Arquivos:**
- Criar: `web/api/enviador.py`
- Criar: `web/api/auth.py`
- Modificar: `web/api/main.py` (rotas `POST /api/auth/registro` e
  `GET /api/auth/confirmar/{token}`)
- Testar: `tests/test_auth_cadastro.py`

**Interfaces:**
- Consome: `db.conexao`, `db.marca` (tarefa 3).
- Produz, e as tarefas 8, 9 e 10 dependem destes nomes exatos:
  - `enviador.enviar(para: str, assunto: str, corpo: str) -> None`
  - `enviador.pasta_de_emails() -> Path`
  - `auth.hash_senha(senha: str) -> str`
  - `auth.conferir_senha(senha: str, guardado: str) -> bool`
  - `auth.precisa_reescrever(guardado: str) -> bool`
  - `auth.normalizar(email: str) -> str`
  - `auth.por_email(email: str) -> sqlite3.Row | None`
  - `auth.por_id(uid: int) -> sqlite3.Row | None`
  - `auth.criar_conta(email, senha, ip) -> int | None`
  - `auth.novo_token(usuario: int, tipo: str, prazo_s: int) -> str`
  - `auth.usar_token(valor: str, tipo: str) -> int | None`
  - `auth.url_base() -> str`
  - `auth.PRAZO_CONFIRMACAO_S`, `auth.PRAZO_SENHA_S`

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_auth_cadastro.py`:

```python
"""Cadastro, senha e confirmação de endereço."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from web.api import auth, db, enviador
from web.api.main import app

cliente = TestClient(app)


def emails_novos(desde: float) -> list[str]:
    saida = []
    for p in enviador.pasta_de_emails().iterdir():
        if p.is_file() and p.stat().st_mtime >= desde:
            saida.append(p.read_text(encoding="utf-8"))
    return saida


def test_a_senha_nunca_aparece_em_texto():
    guardado = auth.hash_senha("umaSenhaBoa123")
    assert "umaSenhaBoa123" not in guardado
    assert guardado.startswith("scrypt$"), guardado
    # Os parâmetros vão junto: endurecer os custos depois não invalida senha
    # nenhuma.
    assert len(guardado.split("$")) == 6, guardado
    assert auth.conferir_senha("umaSenhaBoa123", guardado)
    assert not auth.conferir_senha("outra", guardado)
    # Dois hashes da mesma senha diferem: o sal é por senha.
    assert auth.hash_senha("umaSenhaBoa123") != guardado
    print("OK: a senha vira scrypt com sal e parâmetros gravados")


def test_hash_de_parametros_antigos_e_reconhecido_e_marcado():
    fraco = auth.hash_senha("abc12345", n=2 ** 12)
    assert auth.conferir_senha("abc12345", fraco), "tem que continuar entrando"
    assert auth.precisa_reescrever(fraco), "e ser marcado para reescrita"
    assert not auth.precisa_reescrever(auth.hash_senha("abc12345"))
    print("OK: hash de parâmetros antigos entra e é marcado para reescrita")


def test_cadastro_cria_a_conta_e_manda_o_link():
    marco = time.time()
    r = cliente.post("/api/auth/registro",
                     json={"email": "Ana@Exemplo.COM", "senha": "abc12345"})
    assert r.status_code == 200, r.text

    linha = auth.por_email("ana@exemplo.com")
    assert linha is not None, "o e-mail é guardado em minúsculas"
    assert linha["confirmado_em"] is None
    assert "abc12345" not in linha["senha"]

    corpos = emails_novos(marco)
    assert len(corpos) == 1, corpos
    assert "/api/auth/confirmar/" in corpos[0], corpos[0]
    print("OK: o cadastro cria a conta e manda o link de confirmação")


def test_cadastro_com_email_existente_responde_igual_e_avisa_o_dono():
    primeiro = cliente.post("/api/auth/registro",
                            json={"email": "bia@exemplo.com", "senha": "abc12345"})
    marco = time.time()
    segundo = cliente.post("/api/auth/registro",
                           json={"email": "bia@exemplo.com", "senha": "outra999"})
    assert primeiro.status_code == segundo.status_code == 200
    assert primeiro.json() == segundo.json(), \
        "resposta diferente transformaria o cadastro numa sonda de quem tem conta"

    corpos = emails_novos(marco)
    assert len(corpos) == 1
    assert "/api/auth/confirmar/" not in corpos[0], \
        "quem já tem conta recebe aviso, não link de confirmação"
    assert "alguém" in corpos[0].lower() or "alguem" in corpos[0].lower()

    # E a senha da conta existente não pode ter sido trocada.
    linha = auth.por_email("bia@exemplo.com")
    assert auth.conferir_senha("abc12345", linha["senha"])
    print("OK: cadastro repetido responde igual e não conta quem tem conta")


def test_confirmar_liga_a_conta_e_o_token_so_serve_uma_vez():
    marco = time.time()
    cliente.post("/api/auth/registro",
                 json={"email": "caio@exemplo.com", "senha": "abc12345"})
    corpo = emails_novos(marco)[0]
    token = corpo.split("/api/auth/confirmar/")[1].split()[0].strip()

    r = cliente.get(f"/api/auth/confirmar/{token}", follow_redirects=False)
    assert r.status_code in (302, 303, 307), r.status_code
    assert auth.por_email("caio@exemplo.com")["confirmado_em"] is not None

    de_novo = cliente.get(f"/api/auth/confirmar/{token}", follow_redirects=False)
    assert de_novo.status_code == 400, de_novo.status_code
    print("OK: confirmar liga a conta, e o token não serve duas vezes")


def test_token_vencido_e_recusado():
    uid = auth.criar_conta("dan@exemplo.com", "abc12345", "ip")
    token = auth.novo_token(uid, "confirmacao", prazo_s=-1)
    r = cliente.get(f"/api/auth/confirmar/{token}", follow_redirects=False)
    assert r.status_code == 400, r.status_code
    assert auth.por_email("dan@exemplo.com")["confirmado_em"] is None
    print("OK: token vencido é recusado")


def test_o_token_vai_ao_banco_como_marca():
    uid = auth.criar_conta("eva@exemplo.com", "abc12345", "ip")
    token = auth.novo_token(uid, "confirmacao", prazo_s=3600)
    con = db.conexao()
    guardados = {l["valor"] for l in con.execute(
        "SELECT valor FROM tokens WHERE usuario = ?", (uid,))}
    assert token not in guardados, \
        "vazamento do banco não pode entregar tokens utilizáveis"
    assert db.marca(token) in guardados
    print("OK: o token vai ao banco como marca, não em claro")


def test_senha_curta_e_email_invalido_sao_recusados():
    r = cliente.post("/api/auth/registro",
                     json={"email": "fim@exemplo.com", "senha": "123"})
    assert r.status_code == 422, r.status_code
    r = cliente.post("/api/auth/registro",
                     json={"email": "nao-e-email", "senha": "abc12345"})
    assert r.status_code == 422, r.status_code
    print("OK: senha curta e e-mail inválido são recusados")


if __name__ == "__main__":
    test_a_senha_nunca_aparece_em_texto()
    test_hash_de_parametros_antigos_e_reconhecido_e_marcado()
    test_cadastro_cria_a_conta_e_manda_o_link()
    test_cadastro_com_email_existente_responde_igual_e_avisa_o_dono()
    test_confirmar_liga_a_conta_e_o_token_so_serve_uma_vez()
    test_token_vencido_e_recusado()
    test_o_token_vai_ao_banco_como_marca()
    test_senha_curta_e_email_invalido_sao_recusados()
    print("Todos os testes de cadastro passaram.")
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_auth_cadastro.py
```

Esperado: `ModuleNotFoundError: No module named 'web.api.auth'`.

- [ ] **Passo 3: escrever `enviador.py`**

Crie `web/api/enviador.py`:

```python
"""Manda e-mail: arquivo em desenvolvimento, SMTP em produção.

Sem `PDFTODXF_SMTP_SERVIDOR`, o e-mail vira um arquivo em `dados/emails/`. É o
que permite confirmar uma conta à mão e testar o fluxo inteiro **sem servidor
de e-mail nenhum** — inclusive no CI.
"""

from __future__ import annotations

import os
import smtplib
import time
import traceback
from email.message import EmailMessage
from pathlib import Path

from . import storage


def pasta_de_emails() -> Path:
    caminho = storage.raiz() / "emails"
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def remetente() -> str:
    return os.environ.get("PDFTODXF_SMTP_REMETENTE", "nao-responda@pdftodxf")


def _gravar_em_arquivo(para: str, assunto: str, corpo: str) -> None:
    seguro = "".join(c if c.isalnum() or c in "-_.@" else "_" for c in para)
    nome = f"{time.strftime('%Y%m%d-%H%M%S')}-{seguro[:60]}.txt"
    caminho = pasta_de_emails() / nome
    sufixo = 0
    while caminho.exists():
        sufixo += 1
        caminho = pasta_de_emails() / f"{nome[:-4]}-{sufixo}.txt"
    caminho.write_text(f"Para: {para}\nAssunto: {assunto}\n\n{corpo}\n",
                       encoding="utf-8")


def enviar(para: str, assunto: str, corpo: str) -> None:
    """Manda, ou grava em arquivo. **Nunca levanta.**

    Uma falha de SMTP não pode derrubar o cadastro: a conta já existe, e o
    usuário pode pedir o link de novo. Estourar aqui devolveria 500 para quem
    acabou de se cadastrar com sucesso.
    """
    servidor = os.environ.get("PDFTODXF_SMTP_SERVIDOR")
    if not servidor:
        _gravar_em_arquivo(para, assunto, corpo)
        return

    msg = EmailMessage()
    msg["From"] = remetente()
    msg["To"] = para
    msg["Subject"] = assunto
    msg.set_content(corpo)
    porta = int(os.environ.get("PDFTODXF_SMTP_PORTA", "587"))
    usuario = os.environ.get("PDFTODXF_SMTP_USUARIO")
    senha = os.environ.get("PDFTODXF_SMTP_SENHA")
    try:
        with smtplib.SMTP(servidor, porta, timeout=20) as s:
            s.starttls()
            if usuario and senha:
                s.login(usuario, senha)
            s.send_message(msg)
    except Exception:
        traceback.print_exc()
```

- [ ] **Passo 4: escrever `auth.py`**

Crie `web/api/auth.py`:

```python
"""É mesmo quem diz ser: senha, cadastro, confirmação, sessão e redefinição.

Três decisões que parecem detalhe e não são:

- **A recusa nunca distingue "não existe" de "está errado".** Nem no cadastro,
  nem no login, nem na redefinição. Um formulário que responde diferente para
  e-mail cadastrado vira uma sonda para descobrir quem usa o serviço.
- **O caminho do e-mail inexistente executa um `scrypt` de mentira**, para que o
  tempo de resposta não conte a diferença que a mensagem se recusou a contar.
- **Os parâmetros do `scrypt` vão gravados junto do hash.** Endurecer os custos
  depois não invalida senha nenhuma: quem entra com um hash antigo é reescrito
  com os novos naquele momento.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time

from . import db

N = 2 ** 15
R = 8
P = 1
TAMANHO = 32
PRAZO_CONFIRMACAO_S = 48 * 60 * 60
PRAZO_SENHA_S = 60 * 60
SENHA_MINIMA = 8

_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
# Hash descartável, com custo real, para o caminho do e-mail inexistente.
_DE_MENTIRA = None


def normalizar(email: str) -> str:
    return (email or "").strip().lower()


def email_valido(email: str) -> bool:
    return bool(_EMAIL.match(normalizar(email))) and len(email) <= 254


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode()


def hash_senha(senha: str, n: int = N, r: int = R, p: int = P) -> str:
    """`scrypt$n$r$p$sal$hash`, tudo em base64, com os parâmetros junto."""
    sal = secrets.token_bytes(16)
    bruto = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=n, r=r, p=p,
                           dklen=TAMANHO, maxmem=2 * n * r * 64 + 1024 * 1024)
    return f"scrypt${n}${r}${p}${_b64(sal)}${_b64(bruto)}"


def _partes(guardado: str):
    marca, n, r, p, sal, bruto = guardado.split("$")
    if marca != "scrypt":
        raise ValueError("formato desconhecido")
    return (int(n), int(r), int(p), base64.b64decode(sal),
            base64.b64decode(bruto))


def conferir_senha(senha: str, guardado: str) -> bool:
    try:
        n, r, p, sal, bruto = _partes(guardado)
    except Exception:
        return False
    calculado = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=n, r=r, p=p,
                              dklen=len(bruto),
                              maxmem=2 * n * r * 64 + 1024 * 1024)
    return hmac.compare_digest(calculado, bruto)


def precisa_reescrever(guardado: str) -> bool:
    """O hash foi feito com parâmetros mais fracos do que os de hoje?"""
    try:
        n, r, p, _sal, _bruto = _partes(guardado)
    except Exception:
        return True
    return (n, r, p) != (N, R, P)


def queimar_tempo() -> None:
    """Gasta o mesmo `scrypt` de um login de verdade, e joga fora.

    Sem isto, "e-mail não existe" responde em microssegundos e "senha errada"
    em dezenas de milissegundos — e o cronômetro conta o que a mensagem calou.
    """
    global _DE_MENTIRA
    if _DE_MENTIRA is None:
        _DE_MENTIRA = hash_senha("uma senha que ninguem usa")
    conferir_senha("tentativa", _DE_MENTIRA)


def por_email(email: str):
    return db.conexao().execute(
        "SELECT * FROM usuarios WHERE email = ?", (normalizar(email),)
    ).fetchone()


def por_id(uid: int):
    return db.conexao().execute(
        "SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone()


def criar_conta(email: str, senha: str, ip: str) -> int | None:
    """Cria a conta. Devolve `None` se o e-mail já existe."""
    import sqlite3
    con = db.conexao()
    try:
        cursor = con.execute(
            "INSERT INTO usuarios (email, senha, criado_em, criado_de) "
            "VALUES (?, ?, ?, ?)",
            (normalizar(email), hash_senha(senha), time.time(), db.marca(ip)))
        con.commit()
        return int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        con.rollback()
        return None


def reescrever_senha(uid: int, senha: str) -> None:
    con = db.conexao()
    con.execute("UPDATE usuarios SET senha = ? WHERE id = ?",
                (hash_senha(senha), uid))
    con.commit()


def novo_token(usuario: int, tipo: str, prazo_s: int) -> str:
    """Gera o token, guarda a **marca** dele e devolve o valor original.

    O valor só existe dentro do e-mail: vazamento do banco não entrega tokens
    utilizáveis.
    """
    valor = secrets.token_urlsafe(32)
    con = db.conexao()
    con.execute("INSERT INTO tokens (valor, tipo, usuario, expira_em) "
                "VALUES (?, ?, ?, ?)",
                (db.marca(valor), tipo, usuario, time.time() + prazo_s))
    con.commit()
    return valor


def usar_token(valor: str, tipo: str) -> int | None:
    """Consome o token e devolve o usuário. `None` se vencido, usado ou falso.

    O consumo é um `UPDATE` condicional, e não leitura-e-escrita: dois cliques
    no mesmo link chegam juntos, e só um pode valer.
    """
    con = db.conexao()
    agora = time.time()
    cursor = con.execute(
        "UPDATE tokens SET usado_em = ? "
        "WHERE valor = ? AND tipo = ? AND usado_em IS NULL AND expira_em > ?",
        (agora, db.marca(valor), tipo, agora))
    con.commit()
    if cursor.rowcount == 0:
        return None
    linha = con.execute("SELECT usuario FROM tokens WHERE valor = ?",
                        (db.marca(valor),)).fetchone()
    return int(linha["usuario"]) if linha else None


def confirmar_conta(uid: int) -> None:
    con = db.conexao()
    con.execute("UPDATE usuarios SET confirmado_em = ? WHERE id = ?",
                (time.time(), uid))
    con.commit()


def url_base() -> str:
    return os.environ.get("PDFTODXF_URL_BASE", "http://localhost:8000").rstrip("/")
```

- [ ] **Passo 5: as duas rotas de cadastro**

Em `web/api/main.py`, acrescente `auth` e `enviador` ao import, e as rotas —
antes da montagem dos estáticos, que tem de continuar por último:

```python
class PedidoDeRegistro(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    senha: str = Field(min_length=8, max_length=200)


@app.post("/api/auth/registro")
def registrar(pedido: PedidoDeRegistro, request: Request) -> dict:
    """Cria a conta e dispara o link. **A resposta é a mesma nos dois casos.**

    E-mail já cadastrado recebe um aviso, e não o link — assim o dono do
    endereço fica sabendo, e quem sondou não descobre nada.
    """
    if not auth.email_valido(pedido.email):
        raise HTTPException(status_code=422, detail="E-mail inválido.")

    ip = identidade.ip_do_pedido(request)
    uid = auth.criar_conta(pedido.email, pedido.senha, ip)
    if uid is None:
        auth.queimar_tempo()
        enviador.enviar(
            auth.normalizar(pedido.email),
            "Tentativa de cadastro no PdfToDxf",
            "Alguém tentou criar uma conta no PdfToDxf com este endereço, que "
            "já tem cadastro.\n\nSe foi você, entre normalmente em "
            f"{auth.url_base()}/ — e use 'Esqueci a senha' se precisar.\n\n"
            "Se não foi você, pode ignorar esta mensagem: nada mudou na sua "
            "conta.")
    else:
        token = auth.novo_token(uid, "confirmacao", auth.PRAZO_CONFIRMACAO_S)
        enviador.enviar(
            auth.normalizar(pedido.email),
            "Confirme seu endereço no PdfToDxf",
            "Para ativar a cota maior da sua conta, confirme este endereço:\n\n"
            f"{auth.url_base()}/api/auth/confirmar/{token}\n\n"
            "O link vale por 48 horas. Se você não pediu isto, ignore.")

    return {"ok": True,
            "mensagem": "Se este endereço puder receber, o e-mail já saiu. "
                        "Confira a caixa de entrada."}


@app.get("/api/auth/confirmar/{token}")
def confirmar(token: str):
    uid = auth.usar_token(token, "confirmacao")
    if uid is None:
        raise Recusa(400, "Este link não vale mais. Peça outro entrando na sua "
                          "conta.", "token_invalido")
    auth.confirmar_conta(uid)
    return RedirectResponse(url="/?confirmado=1", status_code=303)
```

Acrescente ao import do FastAPI o `RedirectResponse`:

```python
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
```

e aos módulos:

```python
from . import (auth, db, enviador, exportacao, identidade, jobs, limits,
               quotas, registros, storage)
```

- [ ] **Passo 6: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_auth_cadastro.py
```

Esperado: oito linhas `OK: ...`.

- [ ] **Passo 7: commit**

```bash
git add web/api/auth.py web/api/enviador.py web/api/main.py tests/test_auth_cadastro.py
git commit -m "Cadastro por e-mail com confirmacao, e o enviador"
```

---

### Tarefa 8: entrar, sair e a sessão em cookie assinado

**Arquivos:**
- Modificar: `web/api/auth.py` (sessão)
- Modificar: `web/api/main.py` (rotas `entrar` e `sair`; `dono` nas rotas de cota)
- Testar: `tests/test_auth_sessao.py`

**Interfaces:**
- Consome: tudo da tarefa 7; `identidade.Dono` (tarefa 4).
- Produz, e as tarefas 9, 10 e 11 dependem destes nomes exatos:
  - `auth.COOKIE_SESSAO = "pdftodxf_sessao"`
  - `auth.PRAZO_SESSAO_S: int`
  - `auth.criar_sessao(uid: int, agora: float | None = None) -> str`
  - `auth.dono_da_sessao(request) -> identidade.Dono | None`
  - `auth.precisa_renovar(request) -> bool`
  - `main.quem_pede(request, resposta) -> identidade.Identidade`

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_auth_sessao.py`:

```python
"""Entrar, sair, e o que a sessão muda na cota."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
if "PDFTODXF_REGISTROS" not in os.environ:
    os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial
from web.api import auth, db
from web.api.main import app


def cliente_novo() -> TestClient:
    return TestClient(app)


def limpar_consumo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def conta_pronta(email: str, senha: str = "abc12345") -> int:
    uid = auth.criar_conta(email, senha, "127.0.0.1")
    auth.confirmar_conta(uid)
    return uid


def test_entrar_e_sair():
    conta_pronta("gil@exemplo.com")
    cliente = cliente_novo()
    r = cliente.post("/api/auth/entrar",
                     json={"email": "GIL@exemplo.com", "senha": "abc12345"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "gil@exemplo.com"
    assert auth.COOKIE_SESSAO in cliente.cookies

    r = cliente.post("/api/auth/sair")
    assert r.status_code == 200
    assert not cliente.cookies.get(auth.COOKIE_SESSAO)
    print("OK: entrar grava a sessão e sair a apaga")


def test_email_inexistente_e_senha_errada_respondem_igual():
    conta_pronta("hel@exemplo.com")
    cliente = cliente_novo()
    a = cliente.post("/api/auth/entrar",
                     json={"email": "hel@exemplo.com", "senha": "errada!!"})
    b = cliente.post("/api/auth/entrar",
                     json={"email": "ninguem@exemplo.com", "senha": "errada!!"})
    assert a.status_code == b.status_code == 401, (a.status_code, b.status_code)
    assert a.json() == b.json(), (a.json(), b.json())
    print("OK: e-mail inexistente e senha errada devolvem a mesma coisa")


def test_o_cookie_de_sessao_e_httponly_e_samesite():
    conta_pronta("ines@exemplo.com")
    cliente = cliente_novo()
    r = cliente.post("/api/auth/entrar",
                     json={"email": "ines@exemplo.com", "senha": "abc12345"})
    bruto = r.headers.get("set-cookie", "")
    assert "httponly" in bruto.lower(), bruto
    assert "samesite=lax" in bruto.lower(), bruto
    print("OK: o cookie de sessão é HttpOnly e SameSite=Lax")


def test_sessao_forjada_e_vencida_nao_valem():
    class P:
        def __init__(self, valor):
            self.cookies = {auth.COOKIE_SESSAO: valor}
            self.headers = {}
            self.client = type("C", (), {"host": "127.0.0.1"})()

    uid = conta_pronta("joa@exemplo.com")
    assert auth.dono_da_sessao(P("inventado")) is None
    assert auth.dono_da_sessao(P("")) is None
    velha = auth.criar_sessao(uid, agora=time.time() - auth.PRAZO_SESSAO_S - 10)
    assert auth.dono_da_sessao(P(velha)) is None, "sessão vencida não vale"
    boa = auth.criar_sessao(uid)
    assert auth.dono_da_sessao(P(boa)) == (uid, True)
    print("OK: sessão forjada ou vencida não vale")


def test_trocar_o_segredo_invalida_as_sessoes():
    uid = conta_pronta("kai@exemplo.com")
    valor = auth.criar_sessao(uid)

    class P:
        cookies = {auth.COOKIE_SESSAO: valor}
        headers = {}
        client = type("C", (), {"host": "127.0.0.1"})()

    assert auth.dono_da_sessao(P()) is not None
    os.environ["PDFTODXF_SEGREDO"] = "outro-segredo"
    try:
        assert auth.dono_da_sessao(P()) is None
    finally:
        os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"
    print("OK: trocar o segredo invalida as sessões emitidas antes")


def test_logado_confirmado_envia_mais_que_visitante():
    limpar_consumo()
    conta_pronta("lia@exemplo.com")
    cliente = cliente_novo()
    cliente.post("/api/auth/entrar",
                 json={"email": "lia@exemplo.com", "senha": "abc12345"})
    for i in range(15):
        r = cliente.post("/api/jobs", files={
            "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
        assert r.status_code == 200, (i, r.status_code)
    r = cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    assert r.status_code == 429, r.status_code
    print("OK: logado confirmado envia 15 e é barrado no décimo sexto")


def test_conta_sem_confirmar_fica_com_cota_de_visitante():
    limpar_consumo()
    auth.criar_conta("mar@exemplo.com", "abc12345", "127.0.0.1")
    cliente = cliente_novo()
    cliente.post("/api/auth/entrar",
                 json={"email": "mar@exemplo.com", "senha": "abc12345"})
    for i in range(5):
        r = cliente.post("/api/jobs", files={
            "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
        assert r.status_code == 200, (i, r.status_code)
    r = cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    assert r.status_code == 429, r.status_code

    # E passa à cota cheia depois de confirmar.
    auth.confirmar_conta(auth.por_email("mar@exemplo.com")["id"])
    r = cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    assert r.status_code == 200, r.status_code
    print("OK: sem confirmar é cota de visitante; confirmar destrava a cheia")


def test_pdf_de_40_mb_e_recusado_ao_visitante_e_aceito_ao_logado():
    limpar_consumo()
    grande = b"%PDF-1.4\n" + b"0" * (40 * 1024 * 1024)

    visitante = cliente_novo()
    r = visitante.post("/api/jobs", files={
        "arquivo": ("g.pdf", grande, "application/pdf")})
    assert r.status_code == 413, r.status_code
    assert r.json()["teto_bytes"] == 10 * 1024 * 1024, r.json()

    conta_pronta("nel@exemplo.com")
    logado = cliente_novo()
    logado.post("/api/auth/entrar",
                json={"email": "nel@exemplo.com", "senha": "abc12345"})
    r = logado.post("/api/jobs", files={
        "arquivo": ("g.pdf", grande, "application/pdf")})
    # Passa do teto de tamanho e morre no `fitz` — que é 400, não 413.
    assert r.status_code == 400, r.status_code
    print("OK: 40 MB é recusado ao visitante por tamanho e aceito ao logado")


if __name__ == "__main__":
    test_entrar_e_sair()
    test_email_inexistente_e_senha_errada_respondem_igual()
    test_o_cookie_de_sessao_e_httponly_e_samesite()
    test_sessao_forjada_e_vencida_nao_valem()
    test_trocar_o_segredo_invalida_as_sessoes()
    test_logado_confirmado_envia_mais_que_visitante()
    test_conta_sem_confirmar_fica_com_cota_de_visitante()
    test_pdf_de_40_mb_e_recusado_ao_visitante_e_aceito_ao_logado()
    print("Todos os testes de sessão passaram.")
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_auth_sessao.py
```

Esperado: `AttributeError: module 'web.api.auth' has no attribute 'COOKIE_SESSAO'`.

- [ ] **Passo 3: a sessão em `auth.py`**

Acrescente ao fim de `web/api/auth.py`:

```python
COOKIE_SESSAO = "pdftodxf_sessao"
PRAZO_SESSAO_S = 30 * 24 * 60 * 60


def criar_sessao(uid: int, agora: float | None = None) -> str:
    """`<id>|<emitida em>`, assinado.

    **Sem tabela de sessões.** Nesta escala o cookie assinado basta, e trocar o
    segredo derruba todas as sessões de uma vez — que é justamente o botão de
    emergência que se quer ter.
    """
    agora = time.time() if agora is None else agora
    return db.assinar(f"{int(uid)}|{agora:.0f}")


def _sessao(request):
    valor = request.cookies.get(COOKIE_SESSAO)
    conteudo = db.conferir(valor) if valor else None
    if not conteudo:
        return None
    uid, _, emitida = conteudo.partition("|")
    try:
        return int(uid), float(emitida)
    except ValueError:
        return None


def dono_da_sessao(request):
    """Quem é o dono desta sessão, se ela existe e vale. `None` se não."""
    from . import identidade
    lido = _sessao(request)
    if lido is None:
        return None
    uid, emitida = lido
    if time.time() - emitida > PRAZO_SESSAO_S:
        return None
    linha = por_id(uid)
    if linha is None:
        return None      # a conta sumiu; o cookie não pode ressuscitá-la
    return identidade.Dono(id=uid, confirmado=linha["confirmado_em"] is not None)


def precisa_renovar(request) -> bool:
    """Passou da metade do prazo? Então vale reemitir o cookie."""
    lido = _sessao(request)
    if lido is None:
        return False
    return time.time() - lido[1] > PRAZO_SESSAO_S / 2
```

> `auth` importa `identidade` **dentro da função**, e não no topo. É a única
> volta do ciclo, e ela existe só para nomear a tupla `Dono`. No topo, o import
> circular estouraria na subida.

- [ ] **Passo 4: as rotas de entrar e sair, e `quem_pede`**

Em `web/api/main.py`, acrescente:

```python
def quem_pede(request: Request, resposta: Response) -> identidade.Identidade:
    """A identidade do pedido, com a sessão já resolvida e o cookie renovado.

    Um lugar só. Cada rota resolvendo sessão por conta própria seria a receita
    para uma delas esquecer, e a cota do logado virar cota de visitante em
    silêncio — defeito que nenhum teste de unidade pega.
    """
    seguro = request.url.scheme == "https"
    dono = auth.dono_da_sessao(request)
    if dono is not None and auth.precisa_renovar(request):
        _gravar_sessao(resposta, dono.id, seguro)
    ident = identidade.resolver(request, dono=dono)
    identidade.gravar_cookie(resposta, ident, seguro=seguro)
    return ident


def _gravar_sessao(resposta: Response, uid: int, seguro: bool) -> None:
    resposta.set_cookie(auth.COOKIE_SESSAO, auth.criar_sessao(uid),
                        max_age=auth.PRAZO_SESSAO_S, httponly=True,
                        samesite="lax", secure=seguro, path="/")


class PedidoDeEntrada(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    senha: str = Field(min_length=1, max_length=200)


@app.post("/api/auth/entrar")
def entrar(pedido: PedidoDeEntrada, request: Request,
           resposta: Response) -> dict:
    linha = auth.por_email(pedido.email)
    if linha is None:
        # `scrypt` de mentira: sem ele, "não existe" responde em microssegundos
        # e "senha errada" em dezenas de milissegundos, e o cronômetro conta o
        # que a mensagem calou.
        auth.queimar_tempo()
        raise Recusa(401, "E-mail ou senha não conferem.", "credenciais")

    if not auth.conferir_senha(pedido.senha, linha["senha"]):
        raise Recusa(401, "E-mail ou senha não conferem.", "credenciais")

    if auth.precisa_reescrever(linha["senha"]):
        auth.reescrever_senha(linha["id"], pedido.senha)

    _gravar_sessao(resposta, int(linha["id"]), request.url.scheme == "https")
    return {"email": linha["email"],
            "confirmado": linha["confirmado_em"] is not None}


@app.post("/api/auth/sair")
def sair(resposta: Response) -> dict:
    resposta.delete_cookie(auth.COOKIE_SESSAO, path="/")
    return {"ok": True}
```

- [ ] **Passo 5: as rotas de cota passam a usar `quem_pede`**

Em `enviar`, troque as duas primeiras linhas por:

```python
    ident = quem_pede(request, resposta)
```

(apagando o `identidade.resolver` e o `identidade.gravar_cookie` que estavam
ali). Em `exportar`, dentro do `if not ja_existe:`, troque as duas linhas
equivalentes por:

```python
        ident = quem_pede(request, resposta)
```

- [ ] **Passo 6: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_auth_sessao.py && ./.venv/Scripts/python.exe tests/test_api_cotas.py
```

Esperado: oito linhas `OK: ...` no primeiro, nove no segundo.

- [ ] **Passo 7: commit**

```bash
git add web/api/auth.py web/api/main.py tests/test_auth_sessao.py
git commit -m "Sessao em cookie assinado, entrar e sair"
```

---

### Tarefa 9: redefinição de senha e o teto de contas por IP

**Arquivos:**
- Modificar: `web/api/auth.py` (`contas_do_ip_hoje`)
- Modificar: `web/api/main.py` (rotas `POST /api/auth/senha` e
  `POST /api/auth/senha/{token}`; teto no registro)
- Testar: `tests/test_auth_senha.py`

**Interfaces:**
- Consome: tudo das tarefas 7 e 8.
- Produz:
  - `auth.contas_do_ip_hoje(ip: str, agora: float | None = None) -> int`
  - `auth.teto_de_contas_por_ip() -> int`

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_auth_senha.py`:

```python
"""Redefinição de senha e o teto de contas por IP por dia."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from web.api import auth, db, enviador
from web.api.main import app

cliente = TestClient(app)


def emails_novos(desde: float) -> list[str]:
    return [p.read_text(encoding="utf-8")
            for p in enviador.pasta_de_emails().iterdir()
            if p.is_file() and p.stat().st_mtime >= desde]


def test_pedir_redefinicao_manda_o_link():
    auth.criar_conta("ola@exemplo.com", "senhaVelha1", "127.0.0.1")
    marco = time.time()
    r = cliente.post("/api/auth/senha", json={"email": "ola@exemplo.com"})
    assert r.status_code == 200, r.text
    corpos = emails_novos(marco)
    assert len(corpos) == 1 and "/api/auth/senha/" in corpos[0]
    print("OK: pedir redefinição manda o link")


def test_email_inexistente_responde_igual_e_nao_manda_nada():
    marco = time.time()
    a = cliente.post("/api/auth/senha", json={"email": "ola@exemplo.com"})
    b = cliente.post("/api/auth/senha", json={"email": "ninguem@exemplo.com"})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    # O inexistente não gera e-mail nenhum, mas responde igual.
    assert len(emails_novos(marco)) == 1
    print("OK: e-mail inexistente responde igual e não manda nada")


def test_concluir_a_redefinicao_troca_a_senha():
    auth.criar_conta("pat@exemplo.com", "senhaVelha1", "127.0.0.1")
    marco = time.time()
    cliente.post("/api/auth/senha", json={"email": "pat@exemplo.com"})
    corpo = [c for c in emails_novos(marco) if "pat@" in c][0]
    token = corpo.split("/api/auth/senha/")[1].split()[0].strip()

    r = cliente.post(f"/api/auth/senha/{token}", json={"senha": "senhaNova99"})
    assert r.status_code == 200, r.text

    linha = auth.por_email("pat@exemplo.com")
    assert auth.conferir_senha("senhaNova99", linha["senha"])
    assert not auth.conferir_senha("senhaVelha1", linha["senha"])

    de_novo = cliente.post(f"/api/auth/senha/{token}",
                           json={"senha": "outraAinda1"})
    assert de_novo.status_code == 400, "o token não serve duas vezes"
    print("OK: concluir a redefinição troca a senha, e o token só vale uma vez")


def test_token_de_confirmacao_nao_serve_para_redefinir_senha():
    uid = auth.criar_conta("qua@exemplo.com", "senhaVelha1", "127.0.0.1")
    token = auth.novo_token(uid, "confirmacao", auth.PRAZO_CONFIRMACAO_S)
    r = cliente.post(f"/api/auth/senha/{token}", json={"senha": "senhaNova99"})
    assert r.status_code == 400, r.status_code
    assert auth.conferir_senha("senhaVelha1", auth.por_email("qua@exemplo.com")["senha"])
    print("OK: token de um tipo não serve para o outro")


def test_teto_de_contas_por_ip_por_dia():
    con = db.conexao()
    con.execute("DELETE FROM usuarios")
    con.commit()
    for i in range(5):
        r = cliente.post("/api/auth/registro",
                         json={"email": f"serie{i}@exemplo.com",
                               "senha": "abc12345"})
        assert r.status_code == 200, (i, r.text)
    r = cliente.post("/api/auth/registro",
                     json={"email": "serie5@exemplo.com", "senha": "abc12345"})
    assert r.status_code == 429, r.status_code
    assert r.json()["codigo"] == "contas_demais", r.json()
    assert auth.por_email("serie5@exemplo.com") is None, "não pode ter criado"
    print("OK: o teto de contas por IP barra a sexta do dia")


def test_conta_de_ontem_nao_conta_para_hoje():
    con = db.conexao()
    con.execute("DELETE FROM usuarios")
    con.commit()
    ontem = time.time() - 25 * 60 * 60
    for i in range(5):
        con.execute("INSERT INTO usuarios (email, senha, criado_em, criado_de) "
                    "VALUES (?, ?, ?, ?)",
                    (f"velho{i}@exemplo.com", "x", ontem, db.marca("testclient")))
    con.commit()
    assert auth.contas_do_ip_hoje("testclient") == 0
    print("OK: conta de mais de 24 h não conta para o teto de hoje")


if __name__ == "__main__":
    test_pedir_redefinicao_manda_o_link()
    test_email_inexistente_responde_igual_e_nao_manda_nada()
    test_concluir_a_redefinicao_troca_a_senha()
    test_token_de_confirmacao_nao_serve_para_redefinir_senha()
    test_teto_de_contas_por_ip_por_dia()
    test_conta_de_ontem_nao_conta_para_hoje()
    print("Todos os testes de redefinição de senha passaram.")
```

> **`db.marca("testclient")` não é chute:** o `TestClient` do Starlette usa
> `testclient` como host do cliente, e é ele que `ip_do_pedido` devolve com
> `PDFTODXF_PROXIES=0`. Se o teste falhar aqui, imprima
> `identidade.ip_do_pedido` uma vez e ajuste — não relaxe o teto.

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_auth_senha.py
```

Esperado: 404 na rota `/api/auth/senha`, que ainda não existe.

- [ ] **Passo 3: o teto por IP em `auth.py`**

Acrescente ao fim de `web/api/auth.py`:

```python
UM_DIA_S = 24 * 60 * 60


def teto_de_contas_por_ip() -> int:
    try:
        return max(0, int(os.environ.get("PDFTODXF_CONTAS_POR_IP_DIA", "5")))
    except ValueError:
        return 5


def contas_do_ip_hoje(ip: str, agora: float | None = None) -> int:
    """Quantas contas saíram deste IP nas últimas 24 h.

    Sem isto, fabricar contas em série multiplica a cota sem esforço nenhum.
    O IP vai na coluna como `marca`, e a conta é feita sobre ela.
    """
    agora = time.time() if agora is None else agora
    linha = db.conexao().execute(
        "SELECT count(*) AS n FROM usuarios "
        "WHERE criado_de = ? AND criado_em > ?",
        (db.marca(ip), agora - UM_DIA_S)).fetchone()
    return int(linha["n"])
```

- [ ] **Passo 4: o teto entra na rota de registro**

Em `web/api/main.py`, dentro de `registrar`, logo depois da linha do `ip`:

```python
    teto = auth.teto_de_contas_por_ip()
    if teto and auth.contas_do_ip_hoje(ip) >= teto:
        raise Recusa(429, "Muitas contas criadas deste endereço hoje. "
                          "Tente amanhã.", "contas_demais")
```

- [ ] **Passo 5: as duas rotas de senha**

Ainda em `web/api/main.py`:

```python
class PedidoDeSenha(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class NovaSenha(BaseModel):
    senha: str = Field(min_length=8, max_length=200)


@app.post("/api/auth/senha")
def pedir_senha(pedido: PedidoDeSenha) -> dict:
    """Manda o link de redefinição. Responde igual para e-mail inexistente."""
    linha = auth.por_email(pedido.email)
    if linha is not None:
        token = auth.novo_token(linha["id"], "senha", auth.PRAZO_SENHA_S)
        enviador.enviar(
            linha["email"], "Redefinir a senha do PdfToDxf",
            "Para escolher uma senha nova, abra:\n\n"
            f"{auth.url_base()}/?senha={token}\n\n"
            "O link vale por 1 hora. Se você não pediu isto, ignore — nada "
            "mudou na sua conta.")
    else:
        auth.queimar_tempo()
    return {"ok": True,
            "mensagem": "Se este endereço tiver conta, o e-mail já saiu."}


@app.post("/api/auth/senha/{token}")
def concluir_senha(token: str, pedido: NovaSenha) -> dict:
    uid = auth.usar_token(token, "senha")
    if uid is None:
        raise Recusa(400, "Este link não vale mais. Peça outro.",
                     "token_invalido")
    auth.reescrever_senha(uid, pedido.senha)
    return {"ok": True}
```

> O link do e-mail aponta para `/?senha=<token>` — a **tela**, não a API. É a
> tela que pede a senha nova e faz o `POST`. Um `GET` que já trocasse a senha
> seria trocado por qualquer pré-carregador de link do cliente de e-mail.

- [ ] **Passo 6: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_auth_senha.py && ./.venv/Scripts/python.exe tests/test_auth_cadastro.py
```

Esperado: seis linhas `OK:` no primeiro, oito no segundo. Se
`test_auth_cadastro` passar a esbarrar no teto de contas por IP, ponha
`os.environ["PDFTODXF_CONTAS_POR_IP_DIA"] = "0"` no topo dele — ali se testa
outra coisa.

- [ ] **Passo 7: commit**

```bash
git add web/api/auth.py web/api/main.py tests/test_auth_senha.py tests/test_auth_cadastro.py
git commit -m "Redefinicao de senha e teto de contas por IP por dia"
```

---

### Tarefa 10: `GET /api/cota`

**Arquivos:**
- Modificar: `web/api/main.py`
- Testar: `tests/test_api_cota_rota.py`

**Interfaces:**
- Consome: `quem_pede` (tarefa 8), `quotas.restante` e `quotas.limites` (tarefa 5).
- Produz, e as tarefas 11 e 12 consomem exatamente este corpo:

```json
{
  "tipo": "visitante",
  "email": "",
  "confirmado": false,
  "arquivos": {"restam": 3, "de": 5, "libera_em": null},
  "downloads": {"restam": 15, "de": 15, "libera_em": null},
  "teto_bytes": 10485760
}
```

`restam` e `de` valem `null` quando a chave está em `0` (sem limite).

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_api_cota_rota.py`:

```python
"""GET /api/cota: o que a tela mostra no canto direito."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "PDFTODXF_DADOS" not in os.environ:
    os.environ["PDFTODXF_DADOS"] = tempfile.mkdtemp(prefix="pdftodxf-teste-")
if "PDFTODXF_REGISTROS" not in os.environ:
    os.environ["PDFTODXF_REGISTROS"] = tempfile.mkdtemp(prefix="pdftodxf-reg-")
os.environ["PDFTODXF_BANCO"] = os.path.join(
    tempfile.mkdtemp(prefix="pdftodxf-db-"), "contas.db")
os.environ["PDFTODXF_SEGREDO"] = "segredo-de-teste"

from fastapi.testclient import TestClient

from tests.test_api_extracao import bytes_do_pdf_vetorial
from web.api import auth, db
from web.api.main import app


def cliente_novo() -> TestClient:
    return TestClient(app)


def limpar_consumo():
    con = db.conexao()
    con.execute("DELETE FROM consumo")
    con.commit()


def test_visitante_novo_ve_a_cota_cheia():
    limpar_consumo()
    r = cliente_novo().get("/api/cota")
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["tipo"] == "visitante" and c["email"] == ""
    assert c["arquivos"] == {"restam": 5, "de": 5, "libera_em": None}, c
    assert c["downloads"] == {"restam": 15, "de": 15, "libera_em": None}, c
    assert c["teto_bytes"] == 10 * 1024 * 1024
    print("OK: visitante novo vê a cota cheia")


def test_a_cota_cai_a_cada_envio():
    limpar_consumo()
    cliente = cliente_novo()
    cliente.post("/api/jobs", files={
        "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    c = cliente.get("/api/cota").json()
    assert c["arquivos"]["restam"] == 4, c
    print("OK: a cota cai a cada envio")


def test_consultar_a_cota_nao_consome_cota():
    limpar_consumo()
    cliente = cliente_novo()
    for _ in range(10):
        cliente.get("/api/cota")
    assert cliente.get("/api/cota").json()["arquivos"]["restam"] == 5
    print("OK: consultar a cota não consome cota")


def test_esgotado_traz_o_libera_em():
    limpar_consumo()
    cliente = cliente_novo()
    for _ in range(5):
        cliente.post("/api/jobs", files={
            "arquivo": ("p.pdf", bytes_do_pdf_vetorial(), "application/pdf")})
    c = cliente.get("/api/cota").json()
    assert c["arquivos"]["restam"] == 0
    assert c["arquivos"]["libera_em"], c
    print("OK: cota esgotada traz quando a próxima vaga abre")


def test_logado_ve_o_proprio_email_e_a_cota_maior():
    limpar_consumo()
    uid = auth.criar_conta("rui@exemplo.com", "abc12345", "127.0.0.1")
    auth.confirmar_conta(uid)
    cliente = cliente_novo()
    cliente.post("/api/auth/entrar",
                 json={"email": "rui@exemplo.com", "senha": "abc12345"})
    c = cliente.get("/api/cota").json()
    assert c["tipo"] == "logado" and c["email"] == "rui@exemplo.com"
    assert c["confirmado"] is True
    assert c["arquivos"]["de"] == 15 and c["downloads"]["de"] == 45
    assert c["teto_bytes"] == 100 * 1024 * 1024
    print("OK: logado vê o próprio e-mail e a cota maior")


def test_sem_limite_devolve_nulo_e_nao_um_numero_grande():
    limpar_consumo()
    os.environ["PDFTODXF_COTA_ARQUIVOS"] = "0"
    try:
        c = cliente_novo().get("/api/cota").json()
        assert c["arquivos"] == {"restam": None, "de": None, "libera_em": None}, c
    finally:
        del os.environ["PDFTODXF_COTA_ARQUIVOS"]
    print("OK: sem limite devolve nulo, e não um número grande")


if __name__ == "__main__":
    test_visitante_novo_ve_a_cota_cheia()
    test_a_cota_cai_a_cada_envio()
    test_consultar_a_cota_nao_consome_cota()
    test_esgotado_traz_o_libera_em()
    test_logado_ve_o_proprio_email_e_a_cota_maior()
    test_sem_limite_devolve_nulo_e_nao_um_numero_grande()
    print("Todos os testes da rota de cota passaram.")
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
./.venv/Scripts/python.exe tests/test_api_cota_rota.py
```

Esperado: 404 em `/api/cota`.

- [ ] **Passo 3: escrever a rota**

Em `web/api/main.py`, antes da montagem dos estáticos:

```python
def _saldo(ident, tipo: str, de: int) -> dict:
    restam, libera = quotas.restante(ident, tipo)
    return {"restam": restam, "de": de or None, "libera_em": libera}


@app.get("/api/cota")
def cota(request: Request, resposta: Response) -> dict:
    """Quanto sobra, e quando libera. **Não consome nada.**"""
    ident = quem_pede(request, resposta)
    tetos = quotas.limites(ident)
    email = ""
    if ident.usuario_id is not None:
        linha = auth.por_id(ident.usuario_id)
        email = linha["email"] if linha else ""
    return {
        "tipo": ident.tipo,
        "email": email,
        "confirmado": ident.confirmado,
        "arquivos": _saldo(ident, "arquivo", tetos["arquivos"]),
        "downloads": _saldo(ident, "download", tetos["downloads"]),
        "teto_bytes": tetos["bytes"],
    }
```

- [ ] **Passo 4: rodar para ver passar**

```bash
./.venv/Scripts/python.exe tests/test_api_cota_rota.py
```

Esperado: seis linhas `OK: ...`.

- [ ] **Passo 5: a bateria Python inteira, de uma vez**

```bash
for t in tests/test_*.py; do echo "== $t"; ./.venv/Scripts/python.exe "$t" || break; done
```

Esperado: todos os arquivos passam. São 21 agora — os 15 da etapa 3 mais os seis
desta etapa.

- [ ] **Passo 6: commit**

```bash
git add web/api/main.py tests/test_api_cota_rota.py
git commit -m "Rota GET /api/cota com o saldo e quando libera"
```

---

### Tarefa 11: tela — canto da conta, caixas de entrar e cadastrar

**Arquivos:**
- Criar: `web/frontend/src/conta.ts`
- Criar: `web/frontend/testes/conta.test.ts`
- Modificar: `web/frontend/src/api.ts` (cliente das rotas de conta e cota)
- Modificar: `web/frontend/src/barra.ts` (o `<div class="direita">`)
- Modificar: `web/frontend/src/main.ts` (estado da conta e remontagem)
- Modificar: `web/frontend/src/estilo.css` (caixa modal e canto da conta)

**Interfaces:**
- Consome: `GET /api/cota`, `POST /api/auth/entrar`, `POST /api/auth/sair`,
  `POST /api/auth/registro`, `POST /api/auth/senha` das tarefas 7 a 10;
  `criarBotao` (`web/frontend/src/ui/controles.ts:30`).
- Produz, e a tarefa 12 depende destes nomes exatos:
  - `api.lerCota(sinal?) -> Promise<Cota>` e o tipo `Cota`
  - `api.entrar(email, senha) -> Promise<{email: string; confirmado: boolean}>`
  - `api.sair() -> Promise<void>`
  - `api.registrar(email, senha) -> Promise<{mensagem: string}>`
  - `api.pedirSenha(email) -> Promise<{mensagem: string}>`
  - `conta.textoDaCota(c: Cota, agora: number) -> string`
  - `conta.horaDeLiberar(epoch: number, agora: number) -> string`
  - `conta.cantoDaConta(c: Cota | null, acoes) -> HTMLElement`
  - `conta.montarCaixaDeConta(raiz, modo, acoes) -> void`

> **O canto vai no `<div class="direita">` que a barra já tem.** Ele foi criado
> na etapa 3.5 exatamente para isto — ver o comentário no topo de `barra.ts`.
> Não construa sobre o cabeçalho de duas faixas da etapa 3: ele não existe mais.

- [ ] **Passo 1: escrever o teste que falha**

Crie `web/frontend/testes/conta.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { horaDeLiberar, textoDaCota } from "../src/conta.js";
import type { Cota } from "../src/api.js";

const AGORA = new Date("2026-08-21T12:00:00").getTime();

function cota(p: Partial<Cota> = {}): Cota {
  return {
    tipo: "visitante", email: "", confirmado: false,
    arquivos: { restam: 3, de: 5, libera_em: null },
    downloads: { restam: 15, de: 15, libera_em: null },
    teto_bytes: 10 * 1024 * 1024,
    ...p,
  };
}

describe("conta.ts", () => {
  it("mostra quantos arquivos restam de quantos", () => {
    expect(textoDaCota(cota(), AGORA)).toBe("3 de 5 arquivos");
  });

  it("no singular não escreve 1 arquivos", () => {
    const c = cota({ arquivos: { restam: 1, de: 5, libera_em: null } });
    expect(textoDaCota(c, AGORA)).toBe("1 de 5 arquivos");
  });

  it("esgotado diz quando libera, e não só que acabou", () => {
    const libera = AGORA / 1000 + 2 * 60 * 60 + 20 * 60;
    const c = cota({ arquivos: { restam: 0, de: 5, libera_em: libera } });
    const texto = textoDaCota(c, AGORA);
    expect(texto).toMatch(/libera/i);
    expect(texto).toMatch(/14[h:]20/);
  });

  it("sem limite não inventa número", () => {
    const c = cota({ arquivos: { restam: null, de: null, libera_em: null } });
    expect(textoDaCota(c, AGORA)).toBe("");
  });

  it("a hora de liberar sai no relógio local", () => {
    const epoch = new Date("2026-08-21T14:05:00").getTime() / 1000;
    expect(horaDeLiberar(epoch, AGORA)).toBe("14h05");
  });
});
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
cd web/frontend && npx vitest run testes/conta.test.ts
```

Esperado: `Cannot find module '../src/conta.js'`.

- [ ] **Passo 3: o cliente HTTP das rotas novas**

Ao fim de `web/frontend/src/api.ts`:

```typescript
export type Saldo = {
  restam: number | null;
  de: number | null;
  libera_em: number | null;
};

export type Cota = {
  tipo: "visitante" | "logado";
  email: string;
  confirmado: boolean;
  arquivos: Saldo;
  downloads: Saldo;
  teto_bytes: number;
};

export async function lerCota(sinal?: AbortSignal): Promise<Cota> {
  const r = await pedir("/api/cota", { signal: sinal });
  return r.json();
}

function corpoJson(dados: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(dados),
  };
}

export async function entrar(email: string, senha: string) {
  const r = await pedir("/api/auth/entrar", corpoJson({ email, senha }));
  return r.json() as Promise<{ email: string; confirmado: boolean }>;
}

export async function sair(): Promise<void> {
  await pedir("/api/auth/sair", { method: "POST" });
}

export async function registrar(email: string, senha: string) {
  const r = await pedir("/api/auth/registro", corpoJson({ email, senha }));
  return r.json() as Promise<{ mensagem: string }>;
}

export async function pedirSenha(email: string) {
  const r = await pedir("/api/auth/senha", corpoJson({ email }));
  return r.json() as Promise<{ mensagem: string }>;
}
```

E, para que a tarefa 12 possa distinguir as recusas por código, troque o `return`
de `erroDaRecusa` por:

```typescript
  let codigo = "";
  try {
    const corpo = JSON.parse(corpoCru);
    if (typeof corpo?.codigo === "string") codigo = corpo.codigo;
  } catch { /* já tratado acima */ }
  return new ErroDaApi(status, detalhe, codigo);
```

> `ErroDaApi` já tem o campo `codigo`, com `""` de padrão (`api.ts:10`). Ele
> nasceu vazio na etapa 3 esperando esta etapa — só faltava alguém preenchê-lo.

- [ ] **Passo 4: escrever `conta.ts`**

Crie `web/frontend/src/conta.ts`:

```typescript
/**
 * O canto da conta e as caixas de entrar e cadastrar.
 *
 * Nada de biblioteca: são dois formulários e um menu. O CSS é o mesmo do resto
 * da tela.
 *
 * A regra que governa o texto da cota é a mesma do progresso: **não inventar
 * número**. Sem limite não vira "∞ arquivos", vira texto nenhum.
 */
import { criarBotao } from "./ui/controles.js";
import type { Cota } from "./api.js";

export type AcoesDaConta = {
  aoEntrar: () => void;
  aoSair: () => void;
  aoCadastrar: () => void;
};

/** `14h05` — hora local, que é a que o usuário lê no relógio dele. */
export function horaDeLiberar(epoch: number, _agora: number): string {
  const d = new Date(epoch * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}h${mm}`;
}

export function textoDaCota(c: Cota, agora: number): string {
  const a = c.arquivos;
  if (a.restam === null || a.de === null) return "";
  if (a.restam === 0 && a.libera_em) {
    return `sem arquivos — libera às ${horaDeLiberar(a.libera_em, agora)}`;
  }
  return `${a.restam} de ${a.de} arquivos`;
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

export type ModoDaCaixa = "entrar" | "cadastrar" | "senha" | null;

export type AcoesDaCaixa = {
  aoConfirmar: (modo: Exclude<ModoDaCaixa, null>,
                email: string, senha: string) => void;
  aoTrocarModo: (modo: Exclude<ModoDaCaixa, null>) => void;
  aoFechar: () => void;
  recado: string;
  erro: string;
};

const TITULOS: Record<Exclude<ModoDaCaixa, null>, string> = {
  entrar: "Entrar",
  cadastrar: "Criar conta",
  senha: "Recuperar a senha",
};

export function montarCaixaDeConta(raiz: HTMLElement, modo: ModoDaCaixa,
                                   acoes: AcoesDaCaixa): void {
  raiz.replaceChildren();
  raiz.hidden = modo === null;
  if (modo === null) return;

  const painel = document.createElement("form");
  painel.className = "caixa-de-conta";
  painel.dataset["teste"] = `caixa-${modo}`;

  const titulo = document.createElement("h2");
  titulo.textContent = TITULOS[modo];

  const email = document.createElement("input");
  email.type = "email";
  email.className = "campo";
  email.required = true;
  email.autocomplete = "email";
  email.placeholder = "seu@email.com";
  email.dataset["teste"] = "campo-email";

  const senha = document.createElement("input");
  senha.type = "password";
  senha.className = "campo";
  senha.required = true;
  senha.minLength = 8;
  senha.autocomplete = modo === "entrar" ? "current-password" : "new-password";
  senha.placeholder = "sua senha";
  senha.dataset["teste"] = "campo-senha";
  senha.hidden = modo === "senha";

  painel.append(titulo, email);
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

  raiz.append(painel);
  email.focus();
}
```

- [ ] **Passo 5: o ícone e o CSS**

Em `web/frontend/src/ui/icones.ts`, acrescente ao mapa a entrada `usuario` —
o traçado do Tabler `user`, no mesmo formato das outras:

```typescript
  usuario: "M12 7a4 4 0 1 0 0 8 4 4 0 0 0 0-8M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2",
```

Em `web/frontend/src/estilo.css`, ao fim:

```css
/* O canto da conta vive no `.direita` da barra, ao lado da estimativa. */
.canto-da-conta { display: flex; align-items: center; gap: .5rem; }

/* A sobreposição das caixas de conta. `[hidden]` já é `display: none
   !important` no topo deste arquivo — sem isso o `display: flex` daqui
   atropelaria o atributo, que foi o defeito do painel de aviso na etapa 3. */
.sobre-conta {
  position: fixed; inset: 0; z-index: 20;
  display: flex; align-items: center; justify-content: center;
  background: rgb(0 0 0 / 45%);
}
.caixa-de-conta {
  display: flex; flex-direction: column; gap: .75rem;
  min-width: min(22rem, 90vw); padding: 1.5rem;
  background: var(--fundo); border: 1px solid var(--borda);
  border-radius: .75rem;
}
.caixa-de-conta h2 { margin: 0; font-size: 1.1rem; }
.caixa-de-conta .erro { color: var(--perigo); }
```

> Confira os nomes `--fundo`, `--borda` e `--perigo` contra o `:root` que já
> está no topo de `estilo.css` e use os que existirem — a paleta é da etapa 3.5,
> e inventar variável aqui daria cor transparente sem aviso nenhum.

- [ ] **Passo 6: ligar em `barra.ts` e `main.ts`**

Em `barra.ts`, acrescente ao `ContextoDaBarra`:

```typescript
  cota: Cota | null;
  acoesDaConta: AcoesDaConta;
```

e, dentro de `montarBarra`, logo antes de `raiz.append(direita)`:

```typescript
  direita.append(cantoDaConta(c.cota, c.acoesDaConta));
```

com os imports `import { cantoDaConta, type AcoesDaConta } from "./conta.js";`
e `import type { Cota } from "./api.js";`.

Em `index.html`, acrescente dentro de `#app`, antes do `.rodape`:

```html
      <div class="sobre-conta" id="conta" hidden></div>
```

Em `main.ts`, junto das outras constantes de elemento:

```typescript
const caixaDaConta = document.querySelector<HTMLElement>("#conta")!;
```

e o estado e as ações:

```typescript
let cota: Cota | null = null;
let modoDaConta: ModoDaCaixa = null;
let recadoDaConta = "";
let erroDaConta = "";

/**
 * Relê a cota e remonta o topo.
 *
 * Falha aqui **não vira aviso na tela**: a cota é informação de canto, e um
 * erro de rede ao lê-la não pode cobrir a planta com um painel. O canto
 * simplesmente não mostra saldo até a próxima leitura dar certo.
 */
async function atualizarCota(): Promise<void> {
  try {
    cota = await lerCota();
  } catch {
    cota = null;
  }
  montarTudo();
}

function abrirConta(modo: ModoDaCaixa): void {
  modoDaConta = modo;
  recadoDaConta = "";
  erroDaConta = "";
  montarConta();
}

function montarConta(): void {
  montarCaixaDeConta(caixaDaConta, modoDaConta, {
    recado: recadoDaConta,
    erro: erroDaConta,
    aoTrocarModo: (m) => abrirConta(m),
    aoFechar: () => abrirConta(null),
    aoConfirmar: (modo, email, senha) => void confirmarConta(modo, email, senha),
  });
}

async function confirmarConta(modo: "entrar" | "cadastrar" | "senha",
                              email: string, senha: string): Promise<void> {
  erroDaConta = "";
  recadoDaConta = "";
  try {
    if (modo === "entrar") {
      await entrar(email, senha);
      modoDaConta = null;
    } else if (modo === "cadastrar") {
      recadoDaConta = (await registrar(email, senha)).mensagem;
    } else {
      recadoDaConta = (await pedirSenha(email)).mensagem;
    }
  } catch (erro) {
    erroDaConta = avisoDoErro(erro).detalhe;
  }
  montarConta();
  await atualizarCota();
}
```

Em `montarTopo()`, acrescente ao objeto passado a `montarBarra`:

```typescript
    cota,
    acoesDaConta: {
      aoEntrar: () => abrirConta("entrar"),
      aoCadastrar: () => abrirConta("cadastrar"),
      aoSair: () => void sair().then(atualizarCota),
    },
```

Os imports que estas linhas exigem, no topo de `main.ts`:

```typescript
import {
  entrar, lerCota, pedirSenha, registrar, sair, type Cota,
} from "./api.js";
import {
  montarCaixaDeConta, type ModoDaCaixa,
} from "./conta.js";
```

E chame `void atualizarCota();` uma vez na inicialização (junto do
`montarTudo()` de partida) e ao fim de `abrir()` e de `baixar()` — são os dois
momentos em que o saldo muda.

- [ ] **Passo 7: rodar para ver passar**

```bash
cd web/frontend && npm test && npm run build
```

Esperado: os 2174 testes anteriores mais os 5 novos, e o build limpo. O
`tsc --noEmit` do build é o que pega tipo errado nos objetos que a barra recebe.

- [ ] **Passo 8: commit**

```bash
git add web/frontend/src web/frontend/testes/conta.test.ts web/frontend/index.html
git commit -m "Tela: canto da conta, cota restante e as caixas de entrar e cadastrar"
```

---

### Tarefa 12: tela — as cinco linhas de erro, `impressao.ts` e a privacidade

**Arquivos:**
- Criar: `web/frontend/src/impressao.ts`
- Criar: `web/frontend/testes/impressao.test.ts`
- Criar: `web/frontend/public/privacidade.html`
- Modificar: `web/frontend/src/estados.ts` (as cinco linhas)
- Modificar: `web/frontend/testes/estados.test.ts`
- Modificar: `web/frontend/src/api.ts` (manda `X-Impressao`)
- Modificar: `web/frontend/src/main.ts` (recusa por tamanho antes do envio)
- Modificar: `web/frontend/e2e/conversao.spec.ts` (um caminho de conta)

**Interfaces:**
- Consome: `ErroDaApi.codigo` (preenchido na tarefa 11), `Cota.teto_bytes`
  (tarefa 10).
- Produz:
  - `impressao.sinaisEmTexto(s: Sinais) -> string`
  - `impressao.hashHex(texto: string) -> Promise<string>`
  - `impressao.coletar() -> Promise<string | null>`
  - `estados.avisoDoErro` passa a tratar `cota_arquivos`, `cota_downloads`,
    `tamanho` e `conta_nao_confirmada`.

- [ ] **Passo 1: escrever os testes que falham**

Crie `web/frontend/testes/impressao.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { hashHex, sinaisEmTexto } from "../src/impressao.js";

const SINAIS = {
  agente: "Mozilla/5.0 (Windows NT 10.0)",
  idioma: "pt-BR",
  tela: "1920x1080x24",
  fuso: "America/Sao_Paulo",
  nucleos: 8,
  canvas: "abc123",
};

describe("impressao.ts", () => {
  it("o texto dos sinais é estável e determinístico", () => {
    expect(sinaisEmTexto(SINAIS)).toBe(sinaisEmTexto({ ...SINAIS }));
    expect(sinaisEmTexto(SINAIS)).toContain("pt-BR");
  });

  it("mudar qualquer sinal muda o texto", () => {
    expect(sinaisEmTexto({ ...SINAIS, nucleos: 4 }))
      .not.toBe(sinaisEmTexto(SINAIS));
  });

  it("o hash sai com 64 hexadecimais minúsculos", async () => {
    const h = await hashHex(sinaisEmTexto(SINAIS));
    expect(h).toMatch(/^[0-9a-f]{64}$/);
    expect(await hashHex(sinaisEmTexto(SINAIS))).toBe(h);
  });

  it("o mesmo hash conhecido, para o formato não mudar por acidente", async () => {
    // SHA-256 de "abc" — se este valor mudar, `hashHex` mudou de algoritmo ou
    // de codificação, e todo balde de impressão do servidor viraria outro.
    expect(await hashHex("abc")).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});
```

E acrescente a `web/frontend/testes/estados.test.ts`:

```typescript
  it("as cinco linhas de erro da etapa 4 existem e são acionáveis", () => {
    const cota = avisoDoErro(new ErroDaApi(429, "sem vaga", "cota_arquivos"));
    expect(tudo(cota)).toMatch(/conta/i);   // oferece o cadastro ao visitante

    const baixar = avisoDoErro(new ErroDaApi(429, "sem vaga", "cota_downloads"));
    expect(tudo(baixar)).toMatch(/já gerou|de novo|liberado/i);

    const tamanho = avisoDoErro(new ErroDaApi(413, "grande", "tamanho"));
    expect(tudo(tamanho)).toMatch(/tamanho|MB/i);

    const naoConfirmada = avisoDoErro(
      new ErroDaApi(403, "confirme", "conta_nao_confirmada"));
    expect(tudo(naoConfirmada)).toMatch(/confirm/i);

    // A quinta é o trabalho expirado, que a etapa 3 já tinha.
    expect(tudo(avisoDoErro(new ErroDaApi(404, "sumiu")))).toMatch(/expir/i);
  });

  it("cota esgotada não conta qual balde estourou", () => {
    const a = avisoDoErro(new ErroDaApi(429, "sem vaga", "cota_arquivos"));
    expect(tudo(a).toLowerCase()).not.toMatch(/cookie|endereço ip|impressão/);
  });
```

- [ ] **Passo 2: rodar para ver falhar**

```bash
cd web/frontend && npx vitest run testes/impressao.test.ts testes/estados.test.ts
```

Esperado: `Cannot find module '../src/impressao.js'` e falha nas duas asserções
novas de `estados`.

- [ ] **Passo 3: escrever `impressao.ts`**

Crie `web/frontend/src/impressao.ts`:

```typescript
/**
 * A impressão do navegador — só o hash sai daqui.
 *
 * Os sinais crus **nunca deixam o navegador**: o que vai no cabeçalho
 * `X-Impressao` é o SHA-256 deles. O servidor ainda aplica `hmac` com o
 * segredo dele antes de guardar, então nem este hash aparece no banco.
 *
 * Duas coisas que isto compra, e vale escrever para ninguém esperar mais: aba
 * anônima e cookie apagado **mantêm** a mesma impressão, que é o caso comum de
 * quem quer mais cota; e trocar de navegador, de máquina ou usar um bloqueador
 * muda tudo. Por isso ela é teto folgado, e não a identidade principal.
 *
 * Falhar aqui **nunca bloqueia**: `coletar()` devolve `null` e o pedido segue
 * sem o cabeçalho. Quem escolhe se proteger fica com a cota anunciada.
 */

export type Sinais = {
  agente: string;
  idioma: string;
  tela: string;
  fuso: string;
  nucleos: number;
  canvas: string;
};

/** Uma linha por sinal, em ordem fixa. Ordem instável mudaria o hash à toa. */
export function sinaisEmTexto(s: Sinais): string {
  return [s.agente, s.idioma, s.tela, s.fuso, String(s.nucleos), s.canvas]
    .join("\n");
}

export async function hashHex(texto: string): Promise<string> {
  const dados = new TextEncoder().encode(texto);
  const bruto = await crypto.subtle.digest("SHA-256", dados);
  return Array.from(new Uint8Array(bruto))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** O desenho de um canvas 2D: o mesmo texto rende pixels diferentes por máquina. */
function assinaturaDoCanvas(): string {
  try {
    const tela = document.createElement("canvas");
    tela.width = 200;
    tela.height = 40;
    const ctx = tela.getContext("2d");
    if (!ctx) return "";
    ctx.textBaseline = "top";
    ctx.font = "14px 'Arial'";
    ctx.fillStyle = "#f60";
    ctx.fillRect(0, 0, 100, 20);
    ctx.fillStyle = "#069";
    ctx.fillText("PdfToDxf — escala real", 2, 4);
    return tela.toDataURL().slice(-64);
  } catch {
    return "";
  }
}

let guardado: string | null | undefined;

export async function coletar(): Promise<string | null> {
  if (guardado !== undefined) return guardado;
  try {
    const s: Sinais = {
      agente: navigator.userAgent,
      idioma: navigator.language,
      tela: `${screen.width}x${screen.height}x${screen.colorDepth}`,
      fuso: Intl.DateTimeFormat().resolvedOptions().timeZone ?? "",
      nucleos: navigator.hardwareConcurrency ?? 0,
      canvas: assinaturaDoCanvas(),
    };
    guardado = await hashHex(sinaisEmTexto(s));
  } catch {
    guardado = null;
  }
  return guardado;
}
```

- [ ] **Passo 4: as cinco linhas de erro**

Em `web/frontend/src/estados.ts`, acrescente dentro de `avisoDoErro`, **antes**
do teste de `erro.status === 404`:

```typescript
    if (erro.codigo === "cota_arquivos") {
      return {
        titulo: "Você chegou ao limite de arquivos por enquanto",
        detalhe: erro.message + " Com uma conta gratuita o limite sobe de 5 " +
                 "para 15 arquivos, e o tamanho máximo de 10 MB para 100 MB.",
        podeTentarDeNovo: false,
      };
    }
    if (erro.codigo === "cota_downloads") {
      return {
        titulo: "Você chegou ao limite de DXF gerados por enquanto",
        detalhe: erro.message + " Baixar de novo um DXF que você já gerou " +
                 "continua liberado — só combinações novas contam.",
        podeTentarDeNovo: false,
      };
    }
    if (erro.codigo === "tamanho") {
      return {
        titulo: "O arquivo passa do tamanho permitido",
        detalhe: erro.message + " Com uma conta gratuita o limite sobe para " +
                 "100 MB.",
        podeTentarDeNovo: false,
      };
    }
    if (erro.codigo === "conta_nao_confirmada") {
      return {
        titulo: "Falta confirmar seu e-mail",
        detalhe: "Enquanto o endereço não for confirmado, a conta fica com a " +
                 "cota de visitante. Procure a mensagem que enviamos — o link " +
                 "vale por 48 horas.",
        podeTentarDeNovo: false,
      };
    }
    if (erro.codigo === "contas_demais") {
      return {
        titulo: "Muitas contas criadas deste endereço hoje",
        detalhe: "Tente amanhã, ou entre na conta que você já tem.",
        podeTentarDeNovo: false,
      };
    }
```

- [ ] **Passo 5: mandar a impressão e recusar o tamanho antes de subir**

Em `web/frontend/src/api.ts`, dentro de `enviarPdf`, logo depois de
`x.open("POST", "/api/jobs")`, o envio passa a esperar a impressão. Troque a
montagem do `XMLHttpRequest` por uma função assíncrona que a colete primeiro:

```typescript
    // `void` e não `await`: `enviarPdf` devolve `Promise` mas não é `async`, e
    // a coleta é rápida. Se ela falhar, o envio segue sem o cabeçalho — a
    // impressão nunca pode impedir alguém de converter uma planta.
    void coletar().then((impressao) => {
      if (impressao) x.setRequestHeader("X-Impressao", impressao);
      x.send(forma);
    });
```

apagando o `x.send(forma)` que estava no fim, e acrescentando ao topo
`import { coletar } from "./impressao.js";`.

Em `exportar`, acrescente o mesmo cabeçalho:

```typescript
export async function exportar(job: string, pagina: number,
                               pedido: PedidoDeExportacao, sinal?: AbortSignal) {
  const impressao = await coletar();
  const cabecalhos: Record<string, string> = {
    "content-type": "application/json",
  };
  if (impressao) cabecalhos["X-Impressao"] = impressao;
  const r = await pedir(`/api/jobs/${job}/pages/${pagina}/export`, {
    method: "POST", headers: cabecalhos, body: JSON.stringify(pedido),
    signal: sinal,
  });
  return r.json() as Promise<{ chave: string; url: string; cache: boolean;
                               entidades: number }>;
}
```

Em `main.ts`, no começo de `abrir(arquivo)`, antes de qualquer coisa:

```typescript
  // O teto do plano, conferido **antes** de subir um byte. A spec pede assim, e
  // a razão é simples: subir 40 MB para receber 413 no fim é gastar o tempo do
  // usuário para dizer o que já se sabia quando ele escolheu o arquivo.
  if (cota && arquivo.size > cota.teto_bytes) {
    const mb = Math.floor(cota.teto_bytes / (1024 * 1024));
    mostrarAviso({
      titulo: "O arquivo passa do tamanho permitido",
      detalhe: `Este arquivo tem ${(arquivo.size / (1024 * 1024)).toFixed(1)} ` +
               `MB e o limite é de ${mb} MB.` +
               (cota.tipo === "visitante"
                 ? " Com uma conta gratuita o limite sobe para 100 MB."
                 : ""),
      podeTentarDeNovo: false,
    });
    return;
  }
```

> **Quem dispara "conta ainda não confirmada":** nenhuma rota devolve esse
> código — a conta sem confirmar não é recusada, ela apenas fica com a cota de
> visitante. Quem mostra a linha é a **tela**, a partir de
> `cota.tipo === "logado" && !cota.confirmado`. O ramo em `avisoDoErro` existe
> para o caso de uma rota futura precisar recusar por isso, e o teste dele é o
> contrato dessa mensagem.

- [ ] **Passo 5b: a linha da conta não confirmada, onde ela de fato aparece**

Em `main.ts`, dentro de `atualizarCota()`, depois de `cota = await lerCota()`:

```typescript
    // Aviso, e não erro: a conta funciona, só não destravou a cota maior. Uma
    // vez por carga — repetir a cada leitura cobriria a planta a cada envio.
    if (cota.tipo === "logado" && !cota.confirmado && !jaAvisouDaConfirmacao) {
      jaAvisouDaConfirmacao = true;
      mostrarAviso(avisoDoErro(
        new ErroDaApi(403, "", "conta_nao_confirmada")));
    }
```

com `let jaAvisouDaConfirmacao = false;` junto das outras variáveis de estado e
`ErroDaApi` acrescentado ao import de `./api.js`.

- [ ] **Passo 6: escrever `privacidade.html`**

Crie `web/frontend/public/privacidade.html` — o rodapé já aponta para ela desde
a etapa 3:

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Privacidade — PdfToDxf</title>
    <link rel="stylesheet" href="/assets/estilo.css" />
    <style>
      body { max-width: 42rem; margin: 0 auto; padding: 2rem 1rem;
             line-height: 1.6; }
      h1 { font-size: 1.5rem; }
      h2 { font-size: 1.1rem; margin-top: 2rem; }
      table { border-collapse: collapse; width: 100%; }
      th, td { text-align: left; padding: .4rem .6rem;
               border-bottom: 1px solid #ddd; vertical-align: top; }
    </style>
  </head>
  <body>
    <h1>Como tratamos seus dados</h1>

    <p>
      O PdfToDxf converte plantas em PDF vetorial para DXF em escala real.
      Esta página diz o que fica guardado, por quê e por quanto tempo.
    </p>

    <h2>O que guardamos</h2>
    <table>
      <thead>
        <tr><th>Dado</th><th>Para quê</th><th>Por quanto tempo</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>O PDF enviado e os arquivos gerados a partir dele</td>
          <td>Fazer a conversão que você pediu</td>
          <td>4 horas</td>
        </tr>
        <tr>
          <td>
            Os textos escritos na planta, o nome do arquivo, a página e o seu
            endereço IP
          </td>
          <td>
            Registro de uso, para responder por conversões feitas pelo serviço
          </td>
          <td>1 ano</td>
        </tr>
        <tr>
          <td>
            Um código derivado do seu endereço IP, de um cookie e de
            características do seu navegador — nunca os valores originais
          </td>
          <td>Contar quanto você já usou, para aplicar o limite de uso</td>
          <td>2 horas</td>
        </tr>
        <tr>
          <td>Seu e-mail e uma versão embaralhada da sua senha, se criar conta</td>
          <td>Entrar na conta e liberar o limite maior</td>
          <td>Enquanto a conta existir</td>
        </tr>
      </tbody>
    </table>

    <h2>As características do navegador</h2>
    <p>
      Para aplicar o limite de uso a quem não tem conta, o site calcula um
      código a partir do seu navegador — versão, idioma, tamanho da tela, fuso
      horário e como ele desenha um texto de teste. <strong>Esses dados não
      saem do seu navegador:</strong> o que é enviado é só o código calculado a
      partir deles, e o servidor ainda o embaralha de novo antes de guardar,
      por 2 horas. Se o seu navegador bloquear essa coleta, nada acontece — o
      limite continua valendo pelo cookie e pelo endereço IP.
    </p>

    <h2>O que não fazemos</h2>
    <ul>
      <li>Não guardamos o desenho da sua planta — só os textos dela.</li>
      <li>Não usamos publicidade nem rastreadores de terceiros.</li>
      <li>Não vendemos nem compartilhamos nada disso com ninguém.</li>
    </ul>

    <h2>Como pedir a remoção</h2>
    <p>
      Escreva para o endereço de contato do serviço dizendo qual arquivo ou
      qual conta, e apagamos os registros correspondentes. Os arquivos enviados
      já somem sozinhos em 4 horas.
    </p>

    <p><a href="/">Voltar para o conversor</a></p>
  </body>
</html>
```

> **Confira o `href` da folha de estilo depois de compilar.** O Vite renomeia o
> CSS com hash em `dist/assets/`, e um caminho errado só aparece na tela — o
> `npm run build` não reclama. Se não bater, tire o `<link>`: o `<style>` embutido
> já basta para esta página.

- [ ] **Passo 7: um caminho de conta no Playwright**

Acrescente a `web/frontend/e2e/conversao.spec.ts`:

```typescript
test("o canto da conta mostra a cota e a caixa de entrar abre", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('[data-teste="cota"]')).toContainText("arquivos");
  await page.locator('[data-teste="entrar"]').click();
  await expect(page.locator('[data-teste="caixa-entrar"]')).toBeVisible();
  await page.locator('[data-teste="ir-para-cadastrar"]').click();
  await expect(page.locator('[data-teste="caixa-cadastrar"]')).toBeVisible();
  await page.locator('[data-teste="fechar-conta"]').click();
  await expect(page.locator('[data-teste="caixa-cadastrar"]')).toBeHidden();
});
```

- [ ] **Passo 8: rodar tudo**

```bash
cd web/frontend && npm test && npm run build && npm run e2e
```

Esperado: os testes de unidade passam, o build sai limpo, e o Playwright passa.
Se o e2e travar esperando o servidor, confira antes se a porta 8000 é a nossa —
é a armadilha de ambiente registrada no handoff:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/openapi.json
```

- [ ] **Passo 9: a bateria inteira, Python e frontend**

```bash
for t in tests/test_*.py; do echo "== $t"; ./.venv/Scripts/python.exe "$t" || break; done
```

Esperado: 21 arquivos, todos passando.

- [ ] **Passo 10: commit**

```bash
git add web/frontend/src web/frontend/testes web/frontend/public web/frontend/e2e
git commit -m "Tela: cinco linhas de erro, impressao do navegador e privacidade"
```

---

## Definição de pronto da etapa 4

Confira **item a item**, como a etapa 2 foi conferida. Marcar sem rodar não
prova nada.

- [ ] `web/requirements.txt` tem exatamente as linhas que tinha antes desta
      etapa, e `web/frontend/package.json` também. Confira com
      `git diff main -- web/requirements.txt web/frontend/package.json` — a
      saída tem que ser vazia.
- [ ] Os 21 arquivos de `tests/test_*.py` passam, um por vez.
- [ ] `npm test`, `npm run build` e `npm run e2e` passam, e o e2e passa **três
      vezes seguidas** — foi assim que a intermitência da etapa 3 apareceu.
- [ ] A integração contínua está verde no GitHub. Ela roda em Linux; o
      `resource` dos limites do worker e as permissões de arquivo se comportam
      diferente lá, e é para isso que ela serve.
- [ ] Um visitante envia 5 arquivos e é barrado no sexto, com a mensagem
      oferecendo o cadastro.
- [ ] Um cadastro completo — registro, e-mail em `dados/emails/`, confirmação,
      entrada — destrava a cota de 15.
- [ ] A pasta de registros tem um `.md` por página extraída, com os textos da
      planta, e **nenhuma rota do serviço a alcança**.
- [ ] `PDFTODXF_SEGREDO` ausente avisa no log ao subir.

## Conferência na tela, que só o humano faz

A etapa 3 provou que isto vale mais do que qualquer suíte: dos três defeitos que
a planta real revelou, **dois passaram por 2174 testes verdes**. Suba os dois
servidores com `preview_start` (`pdftodxf-api` e depois `pdftodxf-web`), abra
`http://localhost:5173` — com `localhost`, nunca `127.0.0.1` — e confira:

1. O canto direito mostra "5 de 5 arquivos" e o botão **Entrar**.
2. Enviar uma planta faz o número cair para 4, sem recarregar a página.
3. **Entrar** abre a caixa; **Criar uma conta** troca de caixa sem fechar;
   **Fechar** some com ela e devolve o clique ao canvas — este último é o
   defeito exato que a etapa 3.5 teve com `pointer-events`.
4. Cadastrar mostra o recado; o arquivo em `dados/emails/` traz o link;
   abrir o link confirma e volta para a tela.
5. Depois de entrar, o e-mail aparece no canto e o saldo vira 15.
6. Escolher um PDF acima do teto mostra a recusa **antes** de a barra de envio
   aparecer.
7. O rodapé leva à `privacidade.html`, e ela abre com estilo.

## O que este plano deixa de fora, e por quê

- **Entrada pelo Google** — etapa 5, quando houver domínio e credenciais.
- **Planos pagos, cobrança, painel administrativo, verificação anti-robô** —
  fora do escopo da spec.
- **Alterar e-mail e apagar a própria conta pela tela** — a remoção é por
  pedido, como a página de privacidade explica.
- **A exportação continua rodando no processo do site.** Dívida herdada da
  etapa 2, registrada no handoff. A cota limita quantas exportações acontecem,
  o que reduz a exposição sem eliminá-la. Resolver muda o contrato da rota —
  viraria assíncrona, com polling — e isso é decisão de projeto, não conserto.

