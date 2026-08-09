# Estágio 1: compilar o frontend. Fica aqui, e só aqui, o node.
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY web/frontend/package*.json ./
RUN npm ci
COPY web/frontend/ ./
COPY tests/casos_select.json /tests/casos_select.json
COPY tests/fixtures/ /tests/fixtures/
# O build roda os testes antes: uma imagem não deve nascer de código que
# desobedece ao contrato do select().
RUN npm test && npm run build

# Estágio 2: o que de fato vai ao ar. Sem node, sem node_modules.
FROM python:3.13-slim
WORKDIR /app
RUN adduser --system --group --no-create-home servico

COPY requirements.txt ./requirements.txt
COPY web/requirements.txt ./web/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r web/requirements.txt

COPY pdftodxf/ ./pdftodxf/
COPY web/api/ ./web/api/
COPY --from=frontend /frontend/dist ./web/frontend/dist

ENV PDFTODXF_DADOS=/dados
RUN mkdir -p /dados && chown servico:servico /dados
USER servico
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "web.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
