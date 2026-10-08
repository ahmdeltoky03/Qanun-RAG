# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --prefix=/install .

FROM python:3.12-slim
ARG EMBEDDING_PROVIDER=hashing
ARG EMBEDDING_MODEL=bge-m3
ARG EMBEDDING_BASE_URL=
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    QANUN_EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER} QANUN_EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    QANUN_EMBEDDING_BASE_URL=${EMBEDDING_BASE_URL} \
    QANUN_CORPUS_PATH=/app/data/processed/civil_code.json QANUN_INDEX_DIR=/app/data/index
WORKDIR /app
RUN useradd --create-home --uid 1001 app
COPY --from=builder /install /usr/local
COPY data/processed ./data/processed
COPY data/eval ./data/eval
COPY reports ./reports
# Bake the vector index into the image: the container is ready the moment it starts, no cold-start ingestion.
# For a hosted embedding model pass the key as a build secret (never as a build arg):
#   docker build --secret id=embed_key,env=COHERE_API_KEY --build-arg EMBEDDING_PROVIDER=cohere ...
RUN --mount=type=secret,id=embed_key,required=false \
    if [ -f /run/secrets/embed_key ]; then QANUN_EMBEDDING_API_KEY=$(cat /run/secrets/embed_key); export QANUN_EMBEDDING_API_KEY; fi; \
    python -m qanun.ingest && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
# One worker per container: the embedded Qdrant store is single-process. Scale with replicas (see compose).
CMD ["uvicorn", "qanun.api.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
