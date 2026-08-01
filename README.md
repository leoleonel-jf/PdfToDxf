# PdfToDxf

Converte plantas em **PDF vetorial** (plotadas/exportadas do AutoCAD) de volta para
**DXF em escala real**, pronto para medir e conferir no CAD com `DIST` e `AREA`.

> Funciona apenas com PDFs **vetoriais** (gerados por Plot/Export do CAD).
> PDFs escaneados (imagem de papel) não são suportados.

## Como usar

```powershell
python main.py
```

1. **Abrir PDF…** — escolha a planta (multi-página suportado; selecione a folha).
2. Navegue: **arrastar** = pan, **roda do mouse** = zoom, **Ajustar à janela** reenquadra.
3. **Calibrar (2 pontos)** — dê zoom numa medida conhecida (ex.: uma cota de parede),
   clique nas duas extremidades e digite o valor real (ex.: `3,50` m).
   `Esc` cancela. A barra de status mostra a escala deduzida (ex.: ≈ 1:50).
   - Alternativa: **Escala 1:N…** se você souber a escala de plotagem —
     mas evite se o PDF foi gerado com *fit to page*.
4. **Exportar DXF…** — abre o painel de opções de compactação e salva o arquivo
   já em escala 1:1 na unidade escolhida (m, cm ou mm), com `$INSUNITS` correto.

Também dá para abrir direto: `python main.py planta.pdf`

## Painel de exportação (compactação)

PDFs de plantas explodem hachuras em milhões de mini-segmentos — sem otimização,
um PDF de 13 MB pode virar um DXF de 500 MB. O painel oferece:

| Opção | Perda? | Efeito típico |
|---|---|---|
| Unir segmentos em polilinhas | nenhuma | ~5× menor |
| Arredondar coordenadas (4 casas) | nenhuma na prática | −20 % |
| Remover duplicados/sobrepostos | nenhuma visual | até −60 % das entidades |
| Remover preenchimentos (hachuras sólidas) | remove os "triângulos" | depende da planta |
| Descartar segmentos < N mm (ajustável) | hachuras mais ralas | grande em plantas densas |
| Painel de layers | você escolhe | remove layers inteiros |

- A **estimativa de tamanho** (≈ MB e % de redução) recalcula a cada opção marcada.
- A **prévia na tela** redesenha o desenho mostrando só o que vai sobrar,
  atualizada ao marcar/desmarcar qualquer opção ou layer (zoom/pan continuam
  funcionando durante a prévia).

## O que é convertido

| No PDF | No DXF |
|---|---|
| Linhas | `LINE` |
| Retângulos / quadriláteros | `LWPOLYLINE` fechada |
| Curvas Bézier que são arcos (círculos plotados do CAD) | `ARC` / `CIRCLE` |
| Demais curvas Bézier | `SPLINE` |
| Texto | `TEXT` (posição, altura e rotação preservadas) |
| Layers do AutoCAD (se o PDF tiver *optional content*) | Layers com o mesmo nome |
| Sem layers no PDF | Layers por cor (`COR_RRGGBB`) + layer `TEXTO` |

## O que se perde na conversão

O PDF não guarda a estrutura do desenho original, só o resultado gráfico:

- **Blocos** viram geometria solta;
- **Cotas** viram linhas + texto (não são entidades `DIMENSION`);
- **Hachuras** viram muitas linhas individuais.

Para *medir e conferir*, nada disso atrapalha — a geometria e a escala ficam corretas.

## Requisitos

Python 3.10+ com:

```powershell
pip install -r requirements.txt
```

(PyMuPDF, ezdxf e Pillow. Tkinter já vem com o Python.)

## Testes

```powershell
python tests/test_roundtrip.py
```

Gera um PDF sintético com medidas conhecidas, converte e confere que as
distâncias, arcos e textos batem no DXF resultante.

Os demais testes rodam do mesmo jeito:

```powershell
python tests/test_optimize.py
python tests/test_casos_select.py
```

`tests/casos_select.json` é o contrato entre o `select()` do Python e a versão
que roda no navegador. Se você mudar `classify()` ou `select()`, regenere com
`python tests/gerar_casos_select.py` e confira o diff: mudança nesse arquivo
significa mudança de comportamento visível na prévia.

## Limitações / futuro

- Saída **DWG**: não suportada (formato fechado). O DXF abre nativamente no
  AutoCAD; se precisar de DWG, use o *ODA File Converter* (gratuito) no DXF gerado.
- PDFs escaneados exigiriam vetorização por visão computacional (fora do escopo).
- Detecção automática da escala pelas cotas do desenho: ideia futura.
