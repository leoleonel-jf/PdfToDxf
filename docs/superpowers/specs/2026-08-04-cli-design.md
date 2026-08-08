# Etapa 2.5 — a linha de comando

Desenho validado em 2026-08-04. Etapa curta, encaixada entre a API (etapa 2) e o
frontend (etapa 3).

## Por que ela existe

Duas razões, e a segunda é a que importa.

**A imediata:** hoje não há como converter uma planta sem abrir a janela do
Tkinter ou fazer ginástica com `curl` contra a API. Uma CLI permite jogar
plantas reais contra o sistema — inclusive na VPS, onde não há tela — antes de
o frontend existir.

**A estrutural:** o projeto inteiro aposta em "um caminho só, exercitado pelas
duas interfaces". O `classify()` decide, o `select()` filtra, e desktop e web
apenas consomem. Só que os dois consumidores foram escritos por quem conhece as
tripas do núcleo. Um terceiro consumidor, que enxerga apenas a superfície
pública, é o que de fato testa se essa fronteira existe ou se é conversa.

Daí uma regra que vale como critério de aceitação, não como estilo: **a CLI só
pode importar da superfície pública** — `extractor.extract_page`,
`optimize.classify`, `optimize.select`, `optimize.ExportOptions`,
`optimize.estimate_bytes`, `dxf_writer.export_dxf` e `calibration`. Se ela
precisar de qualquer outra coisa, isso é um achado sobre o núcleo, e deve ser
registrado antes de contornado.

## Como se invoca

O projeto não tem empacotamento — nem `pyproject.toml`, nem `setup.py`. Então a
CLI entra como módulo executável, sem configuração nova:

```
./.venv/Scripts/python.exe -m pdftodxf inspecionar planta.pdf
./.venv/Scripts/python.exe -m pdftodxf converter planta.pdf --plotagem 50 --unidade m --dedup --unir
```

## Arquivos

| Arquivo | Responsabilidade |
|---|---|
| `pdftodxf/cli.py` | Os argumentos e os dois comandos |
| `pdftodxf/__main__.py` | Três linhas: chama `cli.main()` |
| `tests/test_cli.py` | Os testes |

E `dxf_writer.convert()` **sai**. Ninguém a chama — conferido em todo o
repositório — e ela pula `classify`/`select` inteiro, exportando sem filtro
nenhum. Construir a CLI em cima dela pareceria certo e estaria errado: é a única
função do projeto que produz um DXF sem passar pelo julgamento compartilhado.

## Os dois comandos

### `converter`

Grava o DXF. Argumento posicional: o PDF de entrada.

| Opção | Efeito |
|---|---|
| `--pagina N` | Página a converter, começando em 1. Padrão: 1 |
| `--escala F` | Fator direto: 1 pt de papel vale F unidades |
| `--plotagem R` | Escala de plotagem 1:R, convertida por `scale_from_plot_scale` |
| `--unidade mm\|cm\|m` | Unidade de saída. Padrão: `m` |
| `-o, --saida CAMINHO` | Onde gravar. Padrão: ao lado do original, com `.dxf` |
| `--forcar` | Permite sobrescrever um arquivo existente |

Exatamente um entre `--escala` e `--plotagem` é obrigatório. A calibração por
dois pontos precisa de tela e fica fora da CLI.

**Sem `--forcar`, um arquivo existente não é sobrescrito.** Apagar em silêncio o
DXF que alguém acabou de ajustar no CAD é o tipo de estrago que não se desfaz, e
o ganho de conveniência não paga por isso.

### As opções de compactação

Uma flag por campo de `ExportOptions`, e nada além:

| Flag | Campo |
|---|---|
| `--unir` | `join_polylines` |
| `--arredondar` | `round_coords` |
| `--dedup` | `dedup` |
| `--sem-preenchimento` | `drop_fills` |
| `--min-mm N` | `min_len_mm` |
| `--excluir-layer NOME` | `excluded_layers` (repetível) |

O risco desta etapa é **deriva de opções**: um terceiro lugar nomeando e
defaultando as mesmas coisas, que com o tempo discorda dos outros dois. A
defesa é um teste que afirma que o conjunto de flags é exatamente o conjunto de
campos do `ExportOptions`. Acrescentar um campo ao núcleo sem expor na CLI
quebra a bateria — e é assim que se descobre, em vez de anos depois.

### `inspecionar`

Não grava nada. Imprime o retrato da planta:

- quantas páginas o documento tem;
- por página: contagem por tipo de entidade, total, e a lista de layers com
  quantas entidades cada um;
- a estimativa de tamanho do DXF para quatro combinações: nenhuma opção, só
  `dedup`, só `unir`, e `dedup` + `unir` + `arredondar`.

É o que diz se os tetos técnicos da etapa 2 — 3 milhões de entidades por página,
6 GB de memória no worker — servem para o acervo real de quem usa. Adivinhar
isso a partir de PDFs sintéticos é adivinhar.

## Códigos de saída

| Código | Quando |
|---|---|
| 0 | Deu certo |
| 1 | Erro de uso: falta argumento, escala ausente ou duplicada, arquivo de saída já existe |
| 2 | Problema com o arquivo: não abre como PDF, página não existe, página sem vetores |

A separação existe para a CLI ser usável em script: "o meu comando está errado"
e "esta planta não serve" pedem tratamentos diferentes.

## Testes

Padrão do projeto: funções com `assert` e um bloco `if __name__ == "__main__":`.
Sem pytest.

1. **Deriva das flags** — o conjunto de flags de compactação é exatamente o
   conjunto de campos de `ExportOptions`. É o teste que sustenta a etapa.
2. **Fronteira pública** — um teste lê os `import` do `cli.py` com o `ast` e
   afirma que nenhum sai da superfície listada acima. O `fitz` entra na lista
   como exceção conhecida, porque contar páginas não tem função pública no
   núcleo; uma segunda exceção significaria vazamento de verdade.
3. **Converte de verdade** — um PDF sintético vira DXF que o `ezdxf` abre sem
   erro, com o `$INSUNITS` da unidade pedida.
4. **`--excluir-layer` morde** — o layer excluído some do arquivo gerado. O
   `--dedup` não entra aqui: o PDF sintético não tem duplicatas o bastante para
   a asserção significar alguma coisa, e o `select()` já é coberto pelos 1024
   casos do contrato.
5. **`--escala` e `--plotagem`** dão a mesma **geometria** quando equivalentes.
   Comparar os arquivos byte a byte não serve: o `ezdxf` grava `$TDCREATE` no
   cabeçalho, e dois DXF gerados em instantes diferentes divergem sem motivo.
6. **Recusa sobrescrever** sem `--forcar`, e aceita com.
7. **Códigos de saída** — página inexistente devolve 2; escala ausente devolve 1.
8. **`inspecionar` não grava nada** e imprime os layers esperados.

## Fora de escopo

- Lote: converter uma pasta inteira. Traz decisões próprias — o que fazer quando
  um arquivo do meio falha, como nomear as saídas, se paraleliza — e cada uma é
  uma chance de errar numa etapa que deveria ser curta.
- `--servidor`: atacar a API remota por HTTP em vez do núcleo local. É outra
  ferramenta, um cliente e não um conversor, e cabe depois se fizer falta.
- Calibração por dois pontos, que precisa de tela.
