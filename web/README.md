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

O estado de uma página vale `na_fila`, `extraindo`, `pronta` ou `erro`. Quem lê
deve tratar `extraindo` como "ainda em andamento", igual a `na_fila` — ele está
no contrato, mas hoje nada o escreve: o processo pai é o dono do estado e não
sabe a hora em que o worker pega o trabalho.

## Ciclo de vida dos arquivos

```
<raiz>/<job_id>/
    origem.pdf        sai quando todas as páginas do documento terminam
    ficha.json        nome original, páginas, tamanho, hora de criação
    p<N>/
        cache.pickle  extração e etiquetas, insumo da exportação
        meta.json     layers, contagens, dimensões da folha
        esqueleto.bin geometria estrutural, entregue primeiro
        detalhe.bin   o resto, entregue em segundo plano
        export/       um DXF por combinação de opções, com a contagem ao lado
```

O original só é apagado quando não sobra página para extrair: enquanto faltar
uma, o usuário ainda pode pedi-la, e sem o original não há de onde extrair.

Uma tarefa de fundo roda a cada 10 minutos e apaga trabalhos com mais de 4 horas.
Se ainda assim a cota de disco estourar, ela apaga do mais antigo para o mais
novo até caber.

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

A **exportação não tem esses limites**: ela roda no processo que atende o site.
Uma planta no teto de 3 milhões de entidades carrega o cache inteiro e escreve o
DXF ali mesmo. Está registrado como dívida no handoff.
