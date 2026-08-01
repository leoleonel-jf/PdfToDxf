# Núcleo classify/select — plano de implementação (etapa 1 de 5)

> **Para trabalhadores agênticos:** SUB-SKILL OBRIGATÓRIO: use
> superpowers:subagent-driven-development (recomendado) ou
> superpowers:executing-plans para executar este plano tarefa a tarefa. Os
> passos usam caixas de seleção (`- [ ]`) para acompanhamento.

**Objetivo:** separar `pdftodxf/optimize.py` em uma fase cara que roda uma vez
(`classify()`) e uma fase trivial que roda a cada mudança de opção (`select()`),
para que o navegador possa filtrar sem reimplementar nenhum algoritmo.

**Arquitetura:** `classify()` percorre as entidades uma vez e devolve arrays
paralelos de números — comprimento em mm, layer, preenchimento, grupo de
duplicatas e custo em bytes. `select()` recebe esses arrays e as opções e
devolve uma máscara de quem entra, usando só comparações. O julgamento caro
(quais segmentos são duplicatas entre si) vira dado, então a futura versão
TypeScript do `select()` não pode divergir do Python. O app desktop passa a usar
o mesmo caminho e `apply_filters()` é removido.

**Tecnologias:** Python 3.10+, biblioteca padrão apenas. Sem dependências novas.

## Restrições globais

- Python 3.10+; sintaxe `X | None` já é usada no projeto e deve continuar.
- Nenhuma dependência nova. `requirements.txt` continua com PyMuPDF, ezdxf e
  Pillow. Nada de pytest: os testes deste projeto são funções com `assert` e um
  bloco `if __name__ == "__main__":` que as chama em sequência.
- Docstrings, comentários e mensagens de commit em português.
- Coordenadas em pontos de papel (1 pt = 1/72"), com Y para cima. `PT_TO_MM`
  vem de `pdftodxf/calibration.py`.
- As funções de `optimize.py` são puras: recebem e devolvem dados, não mexem em
  estado global nem tocam em arquivos.
- A ordem original das entidades é significativa e nunca pode ser reordenada —
  é ela que faz o `select()` do Python e o do navegador concordarem.
- `PT_TO_MM = 25.4 / 72.0`, `_BYTES = {"Segment": 210, "Arc": 235,
  "Bezier": 620, "TextItem": 330}`, `_POLY_BASE = 180`, `_POLY_PER_PT = 42`,
  `_ROUND_FACTOR = 0.78`. Estes valores foram medidos em arquivos reais e não
  devem ser alterados.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `pdftodxf/optimize.py` | `ExportOptions`, `EntityAttrs`, `classify`, `select`, `apply_selection`, `join_segments`, `estimate_bytes` | Modificar |
| `pdftodxf/dxf_writer.py` | `export_dxf` passa a usar classify/select | Modificar (linhas 121-131) |
| `pdftodxf/export_dialog.py` | prévia e estimativa passam a usar attrs em cache | Modificar (linhas 46, 163-186) |
| `tests/test_optimize.py` | testes de `classify`, `select`, junção e estimativa | Modificar |
| `tests/test_equivalencia.py` | prova que `select` reproduz `apply_filters` | Criar, remover na tarefa 5 |
| `tests/gerar_casos_select.py` | gera o arquivo de casos de paridade | Criar |
| `tests/casos_select.json` | casos compartilhados com o vitest da etapa 3 | Criar (gerado) |
| `tests/test_casos_select.py` | roda os casos contra o `select()` do Python | Criar |

`optimize.py` termina com cerca de 260 linhas e uma responsabilidade só —
reduzir o DXF. Não há motivo para dividi-lo.

---

### Tarefa 1: `EntityAttrs` e `classify()`

**Arquivos:**
- Modificar: `pdftodxf/optimize.py`
- Testar: `tests/test_optimize.py`

**Interfaces:**
- Consome: `pdftodxf.geometry.Entity` e subclasses; `pdftodxf.calibration.PT_TO_MM`
- Produz: `EntityAttrs` (dataclass) e `classify(entities: list[Entity]) -> EntityAttrs`

- [ ] **Passo 1: mover o bloco de constantes de custo para o topo do módulo**

Hoje `_BYTES`, `_POLY_BASE`, `_POLY_PER_PT` e `_ROUND_FACTOR` estão nas linhas
140-144, depois de `join_segments`. `classify()` precisa delas e vai ficar antes.
Recorte este bloco de `pdftodxf/optimize.py:140-144`:

```python
# bytes aproximados por entidade em DXF ASCII (medidos em arquivos reais)
_BYTES = {"Segment": 210, "Arc": 235, "Bezier": 620, "TextItem": 330}
_POLY_BASE = 180
_POLY_PER_PT = 42
_ROUND_FACTOR = 0.78  # arredondar coordenadas corta ~22% do tamanho
```

e cole logo abaixo da classe `ExportOptions` (depois da linha 25, antes de
`_seg_len`).

- [ ] **Passo 2: escrever o teste que falha**

Acrescente ao topo de `tests/test_optimize.py`, na linha de import, `classify` e
`EntityAttrs`:

```python
from pdftodxf.optimize import (EntityAttrs, ExportOptions, apply_filters,
                               classify, estimate_bytes, join_segments)
```

e acrescente estas funções de teste antes do bloco `if __name__`:

```python
def test_classify_layers():
    ents = [seg(0, 0, 1, 0, layer="A"), seg(0, 0, 1, 0, layer="B"),
            seg(0, 0, 1, 0, layer="A")]
    a = classify(ents)
    assert a.layers == ["A", "B"], a.layers
    assert a.layer_id == [0, 1, 0], a.layer_id
    print("OK: classify indexa layers")


def test_classify_length_mm():
    ents = [seg(0, 0, 1 / PT_TO_MM, 0), TextItem(text="x", position=(0, 0))]
    a = classify(ents)
    assert abs(a.length_mm[0] - 1.0) < 1e-9, a.length_mm
    assert a.length_mm[1] == 0.0
    print("OK: classify mede comprimento em mm")


def test_classify_dup_group():
    ents = [seg(0, 0, 1, 1),                    # 0
            seg(0, 0, 1, 1),                    # 1 duplicado exato
            seg(1, 1, 0, 0),                    # 2 duplicado invertido
            seg(0, 0, 2, 2),                    # 3 diferente
            seg(0, 0, 1, 1, layer="X"),         # 4 outro layer
            seg(0, 0, 1, 1, color=(1, 0, 0))]   # 5 outra cor
    a = classify(ents)
    assert a.dup_group[0] == a.dup_group[1] == a.dup_group[2]
    assert len({a.dup_group[0], a.dup_group[3], a.dup_group[4],
                a.dup_group[5]}) == 4
    assert a.n_groups == 4, a.n_groups
    print("OK: classify agrupa duplicatas")


def test_classify_nao_segmento_sem_grupo():
    ents = [TextItem(text="x", position=(0, 0)), seg(0, 0, 1, 0)]
    a = classify(ents)
    assert a.dup_group[0] == -1
    assert a.dup_group[1] >= 0
    print("OK: classify não agrupa quem não é segmento")


def test_classify_byte_cost():
    ents = [seg(0, 0, 1, 0),
            Polyline(points=[(0, 0), (1, 0), (1, 1)]),
            TextItem(text="x", position=(0, 0))]
    a = classify(ents)
    assert a.byte_cost[0] == 210, a.byte_cost
    assert a.byte_cost[1] == 180 + 42 * 3, a.byte_cost
    assert a.byte_cost[2] == 330, a.byte_cost
    print("OK: classify calcula custo em bytes")
```

O `TextItem` e o `Polyline` já estão importados no arquivo de testes; `PT_TO_MM`
também.

Acrescente as chamadas no bloco `if __name__ == "__main__":`, logo depois de
`test_filter_layers()`:

```python
    test_classify_layers()
    test_classify_length_mm()
    test_classify_dup_group()
    test_classify_nao_segmento_sem_grupo()
    test_classify_byte_cost()
```

- [ ] **Passo 3: rodar e ver falhar**

```bash
python tests/test_optimize.py
```

Esperado: `ImportError: cannot import name 'EntityAttrs' from 'pdftodxf.optimize'`

- [ ] **Passo 4: implementar**

Em `pdftodxf/optimize.py`, logo abaixo do bloco de constantes que você moveu no
passo 1, acrescente:

```python
@dataclass
class EntityAttrs:
    """Etiquetas pré-calculadas, em arrays paralelos à lista de entidades.

    Produzidas uma única vez por `classify()` e consumidas por `select()` —
    tanto aqui quanto na versão TypeScript que roda no navegador. Guardar o
    julgamento caro como número é o que impede as duas implementações de
    divergirem.
    """

    kind: list[str] = field(default_factory=list)         # "Segment", "Arc", ...
    layer_id: list[int] = field(default_factory=list)     # índice em `layers`
    is_fill: list[bool] = field(default_factory=list)
    length_mm: list[float] = field(default_factory=list)  # 0.0 fora de Segment
    dup_group: list[int] = field(default_factory=list)    # -1 fora de Segment
    byte_cost: list[int] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    n_groups: int = 0

    def __len__(self) -> int:
        return len(self.kind)


def classify(entities: list[Entity]) -> EntityAttrs:
    """Fase cara: percorre as entidades uma vez e resume cada uma em números.

    O trabalho pesado é o `dup_group`: o conjunto de hash que descobre quais
    segmentos são o mesmo traço é montado aqui, uma única vez, e vira um
    inteiro por entidade.
    """
    attrs = EntityAttrs()
    layer_index: dict[str, int] = {}
    group_index: dict[tuple, int] = {}

    for e in entities:
        name = type(e).__name__

        lid = layer_index.get(e.layer)
        if lid is None:
            lid = len(attrs.layers)
            layer_index[e.layer] = lid
            attrs.layers.append(e.layer)

        if name == "Segment":
            length_mm = math.hypot(e.p2[0] - e.p1[0], e.p2[1] - e.p1[1]) * PT_TO_MM
            a = (round(e.p1[0], 3), round(e.p1[1], 3))
            b = (round(e.p2[0], 3), round(e.p2[1], 3))
            key = (e.layer, e.color, a, b) if a <= b else (e.layer, e.color, b, a)
            gid = group_index.get(key)
            if gid is None:
                gid = len(group_index)
                group_index[key] = gid
        else:
            length_mm = 0.0
            gid = -1

        if name == "Polyline":
            cost = _POLY_BASE + _POLY_PER_PT * len(e.points)
        else:
            cost = _BYTES.get(name, 300)

        attrs.kind.append(name)
        attrs.layer_id.append(lid)
        attrs.is_fill.append(e.is_fill)
        attrs.length_mm.append(length_mm)
        attrs.dup_group.append(gid)
        attrs.byte_cost.append(cost)

    attrs.n_groups = len(group_index)
    return attrs
```

A chave de duplicata é idêntica à de `apply_filters` — mesmo arredondamento de 3
casas, mesma normalização de ponta invertida, e `layer` e `color` dentro da
chave. Qualquer diferença aqui muda o resultado do dedup.

- [ ] **Passo 5: rodar e ver passar**

```bash
python tests/test_optimize.py
```

Esperado: as cinco linhas `OK: classify ...` e, no fim,
`Todos os testes de otimização passaram.`

- [ ] **Passo 6: commit**

```bash
git add pdftodxf/optimize.py tests/test_optimize.py
git commit -m "Adiciona classify() e a tabela de etiquetas EntityAttrs"
```

---

### Tarefa 2: `select()` e `apply_selection()`

**Arquivos:**
- Modificar: `pdftodxf/optimize.py`
- Testar: `tests/test_optimize.py`

**Interfaces:**
- Consome: `EntityAttrs` e `ExportOptions` da tarefa 1
- Produz: `select(attrs: EntityAttrs, opts: ExportOptions) -> list[bool]` e
  `apply_selection(entities: list[Entity], mask: list[bool]) -> list[Entity]`

- [ ] **Passo 1: escrever o teste que falha**

Acrescente `select` e `apply_selection` à linha de import de
`tests/test_optimize.py` e acrescente estas funções:

```python
def filtrar(ents, opts):
    """Atalho: classifica, seleciona e devolve as entidades que sobraram."""
    a = classify(ents)
    return apply_selection(ents, select(a, opts))


def test_select_layers():
    ents = [seg(0, 0, 1, 0, layer="A"), seg(0, 0, 1, 0, layer="B")]
    out = filtrar(ents, ExportOptions(excluded_layers={"B"}))
    assert len(out) == 1 and out[0].layer == "A"
    print("OK: select exclui layers")


def test_select_fills():
    ents = [seg(0, 0, 1, 0), seg(0, 0, 2, 0, is_fill=True)]
    out = filtrar(ents, ExportOptions(drop_fills=True))
    assert len(out) == 1 and not out[0].is_fill
    print("OK: select remove preenchimentos")


def test_select_micro():
    small = 0.05 / PT_TO_MM
    big = 5.0 / PT_TO_MM
    ents = [seg(0, 0, small, 0), seg(0, 0, big, 0)]
    out = filtrar(ents, ExportOptions(min_len_mm=0.1))
    assert len(out) == 1 and out[0].p2[0] == big
    out = filtrar(ents, ExportOptions(min_len_mm=0.0))
    assert len(out) == 2
    print("OK: select descarta micro-segmentos")


def test_select_dedup():
    ents = [seg(0, 0, 1, 1), seg(0, 0, 1, 1), seg(1, 1, 0, 0),
            seg(0, 0, 2, 2), seg(0, 0, 1, 1, layer="X")]
    out = filtrar(ents, ExportOptions(dedup=True))
    assert len(out) == 3, f"esperava 3, veio {len(out)}"
    print("OK: select deduplica sobrepostos")


def test_select_dedup_elege_o_primeiro_sobrevivente():
    # o primeiro do grupo é preenchimento; com drop_fills ligado quem deve
    # sobreviver é o segundo, e não os dois nem nenhum
    ents = [seg(0, 0, 1, 1, is_fill=True), seg(0, 0, 1, 1)]
    out = filtrar(ents, ExportOptions(dedup=True, drop_fills=True))
    assert len(out) == 1 and not out[0].is_fill
    # sem drop_fills, o primeiro do grupo é que fica
    out = filtrar(ents, ExportOptions(dedup=True))
    assert len(out) == 1 and out[0].is_fill
    print("OK: select elege o primeiro sobrevivente do grupo")


def test_select_dedup_nao_afeta_outros_tipos():
    t1 = TextItem(text="x", position=(0, 0))
    t2 = TextItem(text="x", position=(0, 0))
    out = filtrar([t1, t2], ExportOptions(dedup=True))
    assert len(out) == 2
    print("OK: dedup não mexe em quem não é segmento")


def test_select_preserva_ordem():
    ents = [seg(i, 0, i + 1, 0) for i in range(5)]
    out = filtrar(ents, ExportOptions())
    assert [e.p1[0] for e in out] == [0, 1, 2, 3, 4]
    print("OK: select preserva a ordem original")
```

Acrescente as sete chamadas ao bloco `if __name__ == "__main__":`.

- [ ] **Passo 2: rodar e ver falhar**

```bash
python tests/test_optimize.py
```

Esperado: `ImportError: cannot import name 'select' from 'pdftodxf.optimize'`

- [ ] **Passo 3: implementar**

Em `pdftodxf/optimize.py`, logo abaixo de `classify()`:

```python
def select(attrs: EntityAttrs, opts: ExportOptions) -> list[bool]:
    """Fase barata: decide quem entra, só comparando os números do classify().

    Sem hash e sem alocação por entidade — é esta função que é espelhada em
    TypeScript para a prévia do navegador. A ordem de varredura importa: dentro
    de um grupo de duplicatas, quem sobrevive é o primeiro que passa nos demais
    filtros.
    """
    excluded = {i for i, name in enumerate(attrs.layers)
                if name in opts.excluded_layers}
    emitted = bytearray(attrs.n_groups)
    mask = [False] * len(attrs)

    for i in range(len(attrs)):
        if attrs.layer_id[i] in excluded:
            continue
        if opts.drop_fills and attrs.is_fill[i]:
            continue
        if attrs.kind[i] == "Segment":
            if opts.min_len_mm > 0.0 and attrs.length_mm[i] < opts.min_len_mm:
                continue
            if opts.dedup:
                g = attrs.dup_group[i]
                if emitted[g]:
                    continue
                emitted[g] = 1
        mask[i] = True

    return mask


def apply_selection(entities: list[Entity], mask: list[bool]) -> list[Entity]:
    """Aplica a máscara do select() à lista original de entidades."""
    return [e for e, keep in zip(entities, mask) if keep]
```

- [ ] **Passo 4: rodar e ver passar**

```bash
python tests/test_optimize.py
```

Esperado: as sete linhas `OK: select ...` e `Todos os testes de otimização passaram.`

- [ ] **Passo 5: commit**

```bash
git add pdftodxf/optimize.py tests/test_optimize.py
git commit -m "Adiciona select() sobre as etiquetas do classify()"
```

---

### Tarefa 3: provar que `select()` reproduz `apply_filters()`

Esta é a tarefa que autoriza remover o código antigo. Ela gera entidades
aleatórias com semente fixa e compara as duas implementações em todas as
combinações de opções.

**Arquivos:**
- Criar: `tests/test_equivalencia.py`

**Interfaces:**
- Consome: `classify`, `select`, `apply_selection`, `apply_filters`, `ExportOptions`
- Produz: nada de código de produção; é uma trava temporária, removida na tarefa 5

- [ ] **Passo 1: escrever o teste que falha**

Crie `tests/test_equivalencia.py` com exatamente este conteúdo:

```python
"""Prova que classify()+select() reproduz apply_filters() em todos os casos.

Trava temporária: existe só para autorizar a remoção de apply_filters() na
tarefa 5 do plano do núcleo. Removida junto com ela.
"""

import itertools
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.geometry import Arc, Polyline, Segment, TextItem
from pdftodxf.optimize import (ExportOptions, apply_filters, apply_selection,
                               classify, select)

LAYERS = ["0", "PAREDES", "COTAS", "HACHURA"]
CORES = [None, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]


def gerar_entidades(n, semente):
    """Entidades aleatórias numa grade de 3x3, para o dedup ter o que fazer.

    A grade precisa ser pequena de propósito: 9 pontos dão 36 pares não
    ordenados que, com 4 layers e 3 cores, somam 432 chaves possíveis para
    ~225 segmentos — dezenas de duplicatas por semente. Numa grade de 6x6 as
    colisões caem para menos de 4% e o dedup mal é exercitado.
    """
    rnd = random.Random(semente)
    ents = []
    for _ in range(n):
        layer = rnd.choice(LAYERS)
        cor = rnd.choice(CORES)
        fill = rnd.random() < 0.3
        tipo = rnd.random()
        if tipo < 0.75:
            x1, y1, x2, y2 = (rnd.randrange(0, 3) for _ in range(4))
            if rnd.random() < 0.5:
                x1, y1, x2, y2 = x2, y2, x1, y1  # ponta invertida
            ents.append(Segment(p1=(float(x1), float(y1)), p2=(float(x2), float(y2)),
                                layer=layer, color=cor, is_fill=fill))
        elif tipo < 0.85:
            pts = [(float(rnd.randrange(0, 6)), float(rnd.randrange(0, 6)))
                   for _ in range(rnd.randrange(2, 6))]
            ents.append(Polyline(points=pts, layer=layer, color=cor, is_fill=fill))
        elif tipo < 0.95:
            ents.append(Arc(center=(0.0, 0.0), radius=float(rnd.randrange(1, 9)),
                            start_angle=0.0, end_angle=90.0,
                            layer=layer, color=cor, is_fill=fill))
        else:
            ents.append(TextItem(text="T", position=(0.0, 0.0), height=2.0,
                                 layer=layer, color=cor, is_fill=fill))
    return ents


def todas_as_opcoes():
    """Produto cartesiano dos filtros que select() e apply_filters() cobrem."""
    excluidos = [set(), {"HACHURA"}, {"COTAS", "HACHURA"}, set(LAYERS)]
    for exc, fills, micro, dedup in itertools.product(
            excluidos, [False, True], [0.0, 0.5, 2.0], [False, True]):
        yield ExportOptions(excluded_layers=exc, drop_fills=fills,
                            min_len_mm=micro, dedup=dedup)


def test_equivalencia():
    total = 0
    for semente in range(20):
        ents = gerar_entidades(300, semente)
        attrs = classify(ents)
        for opts in todas_as_opcoes():
            antigo = apply_filters(ents, opts)
            novo = apply_selection(ents, select(attrs, opts))
            assert len(antigo) == len(novo), (
                f"semente {semente} opts {opts}: "
                f"apply_filters deu {len(antigo)}, select deu {len(novo)}")
            for a, b in zip(antigo, novo):
                assert a is b, (
                    f"semente {semente} opts {opts}: entidades diferentes")
            total += 1
    print(f"OK: equivalência em {total} combinações")


if __name__ == "__main__":
    test_equivalencia()
    print("select() reproduz apply_filters() exatamente.")
```

O `assert a is b` compara identidade de objeto, não igualdade — garante que as
duas implementações escolheram as **mesmas** entidades, e não apenas entidades
equivalentes.

- [ ] **Passo 2: rodar**

```bash
python tests/test_equivalencia.py
```

Esperado: `OK: equivalência em 960 combinações` e
`select() reproduz apply_filters() exatamente.`

Se falhar, o defeito está no `classify()` ou no `select()`, não no teste. Os dois
pontos onde a divergência costuma nascer: a chave de duplicata (arredondamento,
normalização da ponta, presença de `layer` e `color`) e a comparação de
comprimento — `apply_filters` compara em pts contra `min_len_mm / PT_TO_MM`,
`select` compara em mm contra `min_len_mm`. Nas coordenadas inteiras usadas aqui
as duas formas coincidem; se aparecer divergência só em `min_len_mm`, é aí.

- [ ] **Passo 3: commit**

```bash
git add tests/test_equivalencia.py
git commit -m "Prova que select() reproduz apply_filters() em 960 combinacoes"
```

---

### Tarefa 4: `estimate_bytes()` sobre a máscara

**Arquivos:**
- Modificar: `pdftodxf/optimize.py:147-182` (a função `estimate_bytes` atual)
- Testar: `tests/test_optimize.py`

**Interfaces:**
- Consome: `EntityAttrs` e a máscara de `select()`
- Produz: `estimate_bytes(attrs: EntityAttrs, mask: list[bool],
  opts: ExportOptions, joined_stats: tuple[int, int, int] | None = None) -> int`

A assinatura muda: antes recebia a lista de entidades já filtrada, agora recebe
as etiquetas e a máscara. É essa forma que o navegador consegue calcular somando
`byte_cost`.

- [ ] **Passo 1: escrever o teste que falha**

Em `tests/test_optimize.py`, substitua a função `test_estimate_monotonic`
inteira por:

```python
def estimar(ents, opts):
    a = classify(ents)
    return estimate_bytes(a, select(a, opts), opts)


def test_estimate_monotonic():
    ents = [seg(i, 0, i + 1, 0) for i in range(1000)]
    base = estimar(ents, ExportOptions())
    joined = estimar(ents, ExportOptions(join_polylines=True))
    rounded = estimar(ents, ExportOptions(round_coords=True))
    both = estimar(ents, ExportOptions(join_polylines=True, round_coords=True))
    assert joined < base and rounded < base and both < joined
    print("OK: estimativa monotônica")


def test_estimate_ignora_descartados():
    ents = [seg(0, 0, 1, 0, layer="A"), seg(0, 0, 1, 0, layer="B")]
    inteiro = estimar(ents, ExportOptions())
    metade = estimar(ents, ExportOptions(excluded_layers={"B"}))
    assert metade == inteiro - 210, (inteiro, metade)
    print("OK: estimativa ignora quem foi descartado")


def test_estimate_soma_custo_de_polilinha():
    ents = [Polyline(points=[(0, 0), (1, 0), (1, 1)])]
    a = classify(ents)
    vazio = estimate_bytes(a, [False], ExportOptions())
    cheio = estimate_bytes(a, [True], ExportOptions())
    assert cheio - vazio == 180 + 42 * 3, (vazio, cheio)
    print("OK: estimativa cobra polilinha por vértice")
```

Acrescente `test_estimate_ignora_descartados()` e
`test_estimate_soma_custo_de_polilinha()` ao bloco `if __name__ == "__main__":`.

- [ ] **Passo 2: rodar e ver falhar**

```bash
python tests/test_optimize.py
```

Esperado: `TypeError` em `estimate_bytes`, porque ela ainda espera uma lista de
entidades.

- [ ] **Passo 3: implementar**

Substitua a função `estimate_bytes` inteira em `pdftodxf/optimize.py` por:

```python
def estimate_bytes(attrs: EntityAttrs, mask: list[bool], opts: ExportOptions,
                   joined_stats: tuple[int, int, int] | None = None) -> int:
    """Estimativa do tamanho do DXF, em bytes, para a seleção dada.

    joined_stats: (n_polilinhas, total_de_vértices, n_segmentos_isolados) medidos
    de uma junção real, se disponível; senão usa a aproximação de 85% de
    encadeamento. É o único número aproximado da estimativa, e é o mesmo cálculo
    feito no navegador.
    """
    total = 0
    n_seg = 0
    for i, keep in enumerate(mask):
        if not keep:
            continue
        if attrs.kind[i] == "Segment":
            n_seg += 1
        else:
            total += attrs.byte_cost[i]

    if opts.join_polylines and n_seg:
        if joined_stats:
            n_poly, n_pts, n_alone = joined_stats
            total += n_poly * _POLY_BASE + n_pts * _POLY_PER_PT + n_alone * _BYTES["Segment"]
        else:
            # aproximação: ~85% dos segmentos se encadeiam em polilinhas
            chained = int(n_seg * 0.85)
            alone = n_seg - chained
            n_poly = max(1, chained // 12)  # cadeias médias de ~12 segmentos
            total += n_poly * _POLY_BASE + (chained + n_poly) * _POLY_PER_PT
            total += alone * _BYTES["Segment"]
    else:
        total += n_seg * _BYTES["Segment"]

    total += 60_000  # cabeçalho/tabelas
    if opts.round_coords:
        total = int(total * _ROUND_FACTOR)
    return total
```

O corpo do cálculo é o mesmo de antes; só a origem dos números mudou — vem das
etiquetas em vez de reexaminar as entidades.

- [ ] **Passo 4: rodar e ver passar**

```bash
python tests/test_optimize.py
```

Esperado: `OK: estimativa monotônica`, `OK: estimativa ignora quem foi
descartado`, `OK: estimativa cobra polilinha por vértice` e
`Todos os testes de otimização passaram.`

- [ ] **Passo 5: commit**

```bash
git add pdftodxf/optimize.py tests/test_optimize.py
git commit -m "estimate_bytes passa a somar o custo das etiquetas"
```

---

### Tarefa 5: migrar os consumidores e remover `apply_filters()`

**Arquivos:**
- Modificar: `pdftodxf/dxf_writer.py:121-131`
- Modificar: `pdftodxf/export_dialog.py:14,46,163-186`
- Modificar: `pdftodxf/optimize.py` (remover `apply_filters` e `_seg_len`)
- Modificar: `tests/test_optimize.py` (remover os testes de `apply_filters`)
- Remover: `tests/test_equivalencia.py`

**Interfaces:**
- Consome: `classify`, `select`, `apply_selection`, `estimate_bytes`
- Produz: `export_dxf` com a mesma assinatura de hoje; `ExportDialog` guardando
  `self.attrs` calculado uma vez

- [ ] **Passo 1: migrar `export_dxf`**

Em `pdftodxf/dxf_writer.py`, substitua o corpo de `export_dxf` (linhas 123-131):

```python
    """Pipeline completo: filtros -> junção -> escrita, conforme ExportOptions."""
    from .optimize import apply_selection, classify, join_segments, select

    attrs = classify(result.entities)
    entities = apply_selection(result.entities, select(attrs, opts))
    if opts.join_polylines:
        entities = join_segments(entities)
    decimals = 4 if opts.round_coords else None
    return write_dxf(result, output_path, scale=scale, unit=unit,
                     entities=entities, round_decimals=decimals)
```

- [ ] **Passo 2: migrar o diálogo de exportação**

Em `pdftodxf/export_dialog.py`, troque a linha 14:

```python
from .optimize import ExportOptions, classify, estimate_bytes, select
```

Na linha 46, o `_baseline` passa a calcular as etiquetas uma vez só. Substitua:

```python
        self._baseline = estimate_bytes(result.entities, ExportOptions())
```

por:

```python
        self.attrs = classify(result.entities)
        self._baseline = estimate_bytes(
            self.attrs, [True] * len(self.attrs), ExportOptions())
```

Substitua o método `_kept_entities` (linhas 163-165) por:

```python
    def _kept_mask(self, opts: ExportOptions):
        return select(self.attrs, opts)
```

E dentro de `_recompute`, substitua o corpo de `work()` (linhas 178-186):

```python
        def work():
            mask = self._kept_mask(opts)
            kept = [e for e, k in zip(self.result.entities, mask) if k]
            est = estimate_bytes(self.attrs, mask, opts)
            if token != self._render_token:
                return
            self.app.ui(lambda: self._show_estimate(len(kept), est))
            self.app.set_preview(kept if preview_on else None)
```

- [ ] **Passo 3: remover o código antigo**

Em `pdftodxf/optimize.py`, apague a função `apply_filters` inteira e a função
auxiliar `_seg_len`, que só ela usava. Confirme que nada mais as referencia:

```bash
grep -rn "apply_filters\|_seg_len" pdftodxf/ tests/
```

Esperado: nenhuma linha, exceto as de `tests/test_equivalencia.py` e
`tests/test_optimize.py`, que você remove nos passos seguintes.

- [ ] **Passo 4: remover os testes que exercitavam o código removido**

Em `tests/test_optimize.py`, apague as funções `test_filter_layers`,
`test_filter_fills`, `test_filter_micro` e `test_dedup` — os equivalentes
`test_select_*` da tarefa 2 cobrem o mesmo comportamento. Apague também as
quatro chamadas correspondentes no bloco `if __name__ == "__main__":` e retire
`apply_filters` da linha de import.

Apague o arquivo de trava, que já cumpriu o papel:

```bash
git rm tests/test_equivalencia.py
```

- [ ] **Passo 5: rodar toda a suíte**

```bash
python tests/test_optimize.py && python tests/test_roundtrip.py && python tests/test_preview.py
```

Esperado: os três terminam com a respectiva linha de sucesso e sem exceção.

- [ ] **Passo 6: abrir o app desktop e conferir na mão**

```bash
python main.py "Input/LAY-1028.26.00_REV 02-31-07-2026.pdf"
```

Confirme, nesta ordem: a planta aparece; **Calibrar (2 pontos)** funciona e a
barra mostra a escala; **Exportar DXF…** abre o painel; marcar e desmarcar
opções muda a contagem de entidades, a estimativa e a prévia na tela; desligar
um layer some com ele na prévia; salvar gera o arquivo. Este passo é manual e
não pode ser pulado — é o único que exercita a integração do diálogo com o
canvas.

- [ ] **Passo 7: commit**

```bash
git add -A pdftodxf/ tests/
git commit -m "Migra desktop e exportacao para classify/select e remove apply_filters"
```

---

### Tarefa 6: arquivo de casos de paridade

O arquivo gerado aqui é o contrato entre o `select()` do Python e o `select.ts`
do navegador, que será escrito na etapa 3. Ele precisa existir antes, para que a
etapa 3 não tenha liberdade de inventar comportamento.

**Arquivos:**
- Criar: `tests/gerar_casos_select.py`
- Criar: `tests/casos_select.json` (gerado, versionado)
- Criar: `tests/test_casos_select.py`

**Interfaces:**
- Consome: `classify`, `select`, `ExportOptions`
- Produz: `tests/casos_select.json` com a forma
  `{"tabelas": [attrs, ...], "casos": [{"nome": str, "tabela": int,
  "opcoes": {...}, "esperado": [bool], "bytes_esperado": int}]}`, lido na etapa
  3 pelo vitest. As tabelas de etiquetas ficam separadas dos casos porque as
  mesmas 300 entidades são reaproveitadas por dezenas de combinações de opções
  — repeti-las inflaria o arquivo sem acrescentar cobertura.

> **Revisão final.** O contrato foi ampliado depois da revisão do branch e hoje
> tem 1024 casos, não os 144 dos passos abaixo. Mudou o seguinte, e o arquivo
> `tests/gerar_casos_select.py` no repositório é a fonte da verdade:
> `bytes_esperado` congela também o `estimate_bytes()` (a divisão inteira e o
> truncamento dele não existem em JavaScript); `join_polylines` e `round_coords`
> entraram no produto cartesiano das opções porque mudam a estimativa; a lista
> de `min_len_mm` ganhou um limiar exatamente igual ao comprimento de um
> segmento de 1 pt, para que trocar `<` por `<=` no `select()` seja detectado; e
> uma quarta tabela, escrita à mão, traz duplicatas do mesmo `dup_group` com
> comprimentos dos dois lados de um limiar, para que a ordem "comprimento antes
> de reservar o grupo" também seja detectada.

- [ ] **Passo 1: escrever o gerador**

Crie `tests/gerar_casos_select.py`:

```python
"""Gera tests/casos_select.json, o contrato entre o select() do Python e o do
navegador.

Rode depois de qualquer mudança em select() ou classify():

    python tests/gerar_casos_select.py

O arquivo gerado é versionado. Se ele mudar num commit que não pretendia mudar
comportamento, isso é um alerta, não um detalhe.
"""

import itertools
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.geometry import Arc, Polyline, Segment, TextItem
from pdftodxf.optimize import ExportOptions, classify, select

SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "casos_select.json")

LAYERS = ["0", "PAREDES", "COTAS", "HACHURA"]
CORES = [None, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]


def gerar_entidades(n, semente):
    """Entidades numa grade de 3x3, para produzir duplicatas em quantidade.

    A grade precisa ser pequena de propósito: 9 pontos dão 36 pares não
    ordenados que, multiplicados pelos 4 layers e 3 cores, somam 432 chaves
    possíveis para ~225 segmentos — dezenas de duplicatas por tabela. Numa
    grade de 6x6 as colisões ficam raras e o caminho do dedup mal é
    exercitado.
    """
    rnd = random.Random(semente)
    ents = []
    for _ in range(n):
        layer = rnd.choice(LAYERS)
        cor = rnd.choice(CORES)
        fill = rnd.random() < 0.3
        tipo = rnd.random()
        if tipo < 0.75:
            x1, y1, x2, y2 = (float(rnd.randrange(0, 3)) for _ in range(4))
            if rnd.random() < 0.5:
                x1, y1, x2, y2 = x2, y2, x1, y1
            ents.append(Segment(p1=(x1, y1), p2=(x2, y2), layer=layer,
                                color=cor, is_fill=fill))
        elif tipo < 0.85:
            pts = [(float(rnd.randrange(0, 6)), float(rnd.randrange(0, 6)))
                   for _ in range(rnd.randrange(2, 6))]
            ents.append(Polyline(points=pts, layer=layer, color=cor, is_fill=fill))
        elif tipo < 0.95:
            ents.append(Arc(center=(0.0, 0.0), radius=3.0, start_angle=0.0,
                            end_angle=90.0, layer=layer, color=cor, is_fill=fill))
        else:
            ents.append(TextItem(text="T", position=(0.0, 0.0), height=2.0,
                                 layer=layer, color=cor, is_fill=fill))
    return ents


def opcoes_variadas():
    excluidos = [[], ["HACHURA"], ["COTAS", "HACHURA"], list(LAYERS)]
    for exc, fills, micro, dedup in itertools.product(
            excluidos, [False, True], [0.0, 0.5, 2.0], [False, True]):
        yield exc, fills, micro, dedup


def main():
    tabelas = []
    casos = []
    for semente in range(3):
        ents = gerar_entidades(300, semente)
        attrs = classify(ents)
        tabelas.append({
            "kind": attrs.kind,
            "layer_id": attrs.layer_id,
            "is_fill": attrs.is_fill,
            "length_mm": [round(v, 9) for v in attrs.length_mm],
            "dup_group": attrs.dup_group,
            "byte_cost": attrs.byte_cost,
            "layers": attrs.layers,
            "n_groups": attrs.n_groups,
        })
        for i, (exc, fills, micro, dedup) in enumerate(opcoes_variadas()):
            opts = ExportOptions(excluded_layers=set(exc), drop_fills=fills,
                                 min_len_mm=micro, dedup=dedup)
            casos.append({
                "nome": f"semente{semente}-opcao{i}",
                "tabela": semente,
                "opcoes": {
                    "excluded_layers": exc,
                    "drop_fills": fills,
                    "min_len_mm": micro,
                    "dedup": dedup,
                },
                "esperado": select(attrs, opts),
            })

    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump({"tabelas": tabelas, "casos": casos}, f, ensure_ascii=False,
                  indent=1, sort_keys=True)
        f.write("\n")
    print(f"{len(casos)} casos gravados em {SAIDA}")


if __name__ == "__main__":
    main()
```

`sort_keys=True` e o `round(v, 9)` deixam o arquivo estável entre execuções:
rodar o gerador duas vezes sem mudar o código produz bytes idênticos, então
qualquer diferença no `git diff` significa mudança de comportamento de verdade.

- [ ] **Passo 2: gerar o arquivo**

```bash
python tests/gerar_casos_select.py
```

Esperado: `144 casos gravados em .../tests/casos_select.json` (depois da revisão
final do branch são `1024 casos gravados em ...`)

- [ ] **Passo 3: escrever o teste que consome os casos**

Crie `tests/test_casos_select.py`:

```python
"""Roda os casos de tests/casos_select.json contra o select() do Python.

O mesmo arquivo é lido pelo vitest na etapa 3. Se as duas implementações
divergirem em qualquer caso, um dos dois lados quebra aqui.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdftodxf.optimize import EntityAttrs, ExportOptions, select

CASOS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "casos_select.json")


def test_casos():
    with open(CASOS, encoding="utf-8") as f:
        dados = json.load(f)

    tabelas = []
    for a in dados["tabelas"]:
        tabelas.append(EntityAttrs(
            kind=a["kind"], layer_id=a["layer_id"], is_fill=a["is_fill"],
            length_mm=a["length_mm"], dup_group=a["dup_group"],
            byte_cost=a["byte_cost"], layers=a["layers"],
            n_groups=a["n_groups"]))

    for caso in dados["casos"]:
        attrs = tabelas[caso["tabela"]]
        o = caso["opcoes"]
        opts = ExportOptions(excluded_layers=set(o["excluded_layers"]),
                             drop_fills=o["drop_fills"],
                             min_len_mm=o["min_len_mm"],
                             dedup=o["dedup"])
        obtido = select(attrs, opts)
        assert obtido == caso["esperado"], f"divergência em {caso['nome']}"

    print(f"OK: {len(dados['casos'])} casos de paridade")


if __name__ == "__main__":
    test_casos()
    print("Todos os casos de paridade passaram.")
```

- [ ] **Passo 4: rodar e ver passar**

```bash
python tests/test_casos_select.py
```

Esperado: `OK: 144 casos de paridade` e `Todos os casos de paridade passaram.`
(depois da revisão final do branch, `OK: 1024 casos de paridade`)

- [ ] **Passo 5: confirmar que o gerador é determinístico**

```bash
python tests/gerar_casos_select.py && git status --short tests/casos_select.json
```

Esperado: nenhuma linha de modificação — o arquivo regenerado é idêntico ao que
está no disco.

- [ ] **Passo 6: documentar no README**

Acrescente ao final da seção **Testes** do `README.md`:

````markdown
Os demais testes rodam do mesmo jeito:

```powershell
python tests/test_optimize.py
python tests/test_casos_select.py
```

`tests/casos_select.json` é o contrato entre o `select()` do Python e a versão
que roda no navegador. Se você mudar `classify()` ou `select()`, regenere com
`python tests/gerar_casos_select.py` e confira o diff: mudança nesse arquivo
significa mudança de comportamento visível na prévia.
````

(As três crases de fora delimitam o trecho aqui no plano; no `README.md` entram
só as linhas de dentro, com o bloco `powershell` mantendo as três crases
normais.)

- [ ] **Passo 7: commit**

```bash
git add tests/gerar_casos_select.py tests/casos_select.json tests/test_casos_select.py README.md
git commit -m "Cria o arquivo de casos de paridade do select()"
```

---

## Definição de pronto

Ao fim da etapa 1, tudo abaixo é verdade:

- `python tests/test_optimize.py`, `python tests/test_roundtrip.py`,
  `python tests/test_preview.py` e `python tests/test_casos_select.py` passam.
- `grep -rn "apply_filters" pdftodxf/ tests/` não devolve nada.
- O app desktop abre, calibra, mostra prévia e exporta igual a antes.
- `tests/casos_select.json` existe, é determinístico e está versionado.
- Nenhuma dependência nova em `requirements.txt`.
