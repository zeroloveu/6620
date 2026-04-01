# ============================================================
# Stage 1: Builder — install dependencies & pre-download model
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .

ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
RUN PYTHONPATH=/install/lib/python3.11/site-packages \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# ============================================================
# Stage 2: Runtime — slim image with only what we need
# ============================================================
FROM python:3.11-slim

LABEL maintainer="ESG RAG Team"
LABEL description="ESG analysis system based on RAG and agentic workflows"

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends tini && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash appuser

COPY --from=builder /install /usr/local
COPY --from=builder /root/.cache/huggingface /home/appuser/.cache/huggingface

COPY src/ src/
COPY .env.example .env.example
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

RUN mkdir -p /app/storage/kbs /app/storage/index /app/data/uploads && \
    chown -R appuser:appuser /app /home/appuser

ENV PYTHONPATH=src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/home/appuser/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/appuser/.cache/huggingface \
    PORT=8001

EXPOSE 8001

VOLUME ["/app/storage", "/app/data"]

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:${PORT:-8001}/health'); r.raise_for_status()" || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["/docker-entrypoint.sh"]
