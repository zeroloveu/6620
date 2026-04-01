#!/bin/bash
set -e

echo "=== ESG RAG Agent Starting ==="

mkdir -p /app/storage/kbs /app/storage/index /app/data/uploads

echo "Pre-warming embedding model..."
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${LOCAL_EMBEDDING_MODEL:-all-MiniLM-L6-v2}')" 2>/dev/null && \
    echo "Embedding model ready." || echo "Model will be loaded on first request."

echo "Starting server on port ${PORT:-8001}..."
exec uvicorn esg_rag.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8001}" \
    --workers "${WORKERS:-1}" \
    --log-level "${LOG_LEVEL:-info}"
