# ESG RAG Agent Project

This project is a runnable ESG analysis system built around Retrieval-Augmented Generation (RAG),
multi-agent orchestration, and an interactive web UI. It is designed for ESG reports, CSR documents,
annual reports, benchmark framework documents, PDFs, and external sentiment data.

## What it includes

- Document ingestion for `.txt`, `.md`, `.json`, and `.pdf`
- Batch upload ingestion through the browser or API
- ESG-aware chunking for long, structured documents
- Pluggable embedding layer
  - Local `sentence-transformers` embeddings by default
  - OpenAI embeddings when `EMBEDDING_BACKEND=openai`
  - Local hashing-based embeddings as a deterministic fallback
- Switchable vector store backends
  - `simple` local NumPy store
  - `chroma` persistent Chroma collection
  - `milvus` Milvus / Milvus Lite collection
- Multi-agent pipeline
  - `PlannerAgent`
  - `RetrievalAgent`
  - `EvidenceFusionAgent`
  - `VerificationAgent`
  - `ComplianceAgent`
  - `ConfidenceAgent`
  - `ReportAgent`
- FastAPI service for ingest, upload, query, analysis, and system status
- Interactive browser UI for upload, query, and report generation

## Suggested architecture

1. Put ESG reports, CSR reports, annual reports, framework documents, and sentiment data into `data/`.
2. Start the API and open the browser UI.
3. Upload PDFs or trigger re-indexing.
4. Query evidence or generate a structured ESG analysis.
5. Review the report together with compliance alignment, confidence scores, and agent trace.

## Quick start
### 0.By docker
```bash
# 1. 确保 .env 已配置好（尤其是 OPENAI_API_KEY）
# 2. 一键构建并启动
docker compose up -d --build
# 3. 查看日志
docker compose logs -f
# 4. 访问
# http://localhost:8001
```

### 1. Install dependencies

```bash
pip install -e .
```

If you want Chroma or Milvus support:

```bash
pip install -e .[vectordb]
```

### 2. Configure environment

```bash
copy .env.example .env
```

Configuration:

```env
OPENAI_API_KEY=sk-3328607470414d8f8c092d5ae13dc202
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_CHAT_MODEL=deepseek-reasoner
LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
DATA_DIR=./data
INDEX_DIR=./storage/index
UPLOAD_DIR=./data/uploads
VECTOR_BACKEND=simple
CHROMA_COLLECTION=esg_documents
MILVUS_URI=./storage/milvus_esg.db
MILVUS_COLLECTION=esg_documents
CHUNK_SIZE=900
CHUNK_OVERLAP=150
TOP_K=6
MAX_CONTEXT_CHUNKS=8
```

Without an API key, the system still works in local fallback mode:

- Retrieval uses local embeddings with hashing fallback if needed
- Report generation falls back to a deterministic evidence-backed draft

### 3. Start the API and UI

```bash
uvicorn esg_rag.main:app --reload
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## API examples

### Ingest the whole `data/` folder

```bash
curl -X POST http://127.0.0.1:8000/ingest
```

### Upload files and ingest

```bash
curl -X POST http://127.0.0.1:8000/upload ^
  -F "files=@data\\sample\\company_a_esg_report.md" ^
  -F "files=@data\\sample\\gri_reference.md"
```

### Query the knowledge base

```bash
curl -X POST http://127.0.0.1:8000/query ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"What climate and governance disclosures are available for Company A?\"}"
```

### Generate an ESG analysis

```bash
curl -X POST http://127.0.0.1:8000/analyze ^
  -H "Content-Type: application/json" ^
  -d "{\"company_name\":\"Company A\",\"query\":\"Generate a structured ESG analysis for Company A based on indexed evidence.\",\"framework_focus\":[\"GRI\",\"TCFD\"]}"
```

## Key files

- [main.py](C:/Users/81011/Desktop/Myrag/src/esg_rag/main.py)
- [pipeline.py](C:/Users/81011/Desktop/Myrag/src/esg_rag/pipeline.py)
- [agents.py](C:/Users/81011/Desktop/Myrag/src/esg_rag/agents.py)
- [vector_store.py](C:/Users/81011/Desktop/Myrag/src/esg_rag/vector_store.py)
- [llm.py](C:/Users/81011/Desktop/Myrag/src/esg_rag/llm.py)
- [index.html](C:/Users/81011/Desktop/Myrag/src/esg_rag/web/index.html)

## How this project addresses your requirements

### Long and complex ESG documents

- The chunker uses section-aware splitting and overlap windows.
- Metadata such as source path and page number are preserved for traceability.
- PDF pages are loaded individually so evidence remains linkable to source pages.

### Noisy and inconsistent data

- The verification agent annotates weak, short, and supplementary evidence.
- The pipeline supports mixing reports, benchmark documents, and sentiment inputs.
- Compliance mapping is separated from reporting so alignment can be inspected independently.

### Hallucination risk

- The reporting agent is instructed to use only retrieved evidence.
- Output includes evidence references, confidence assessment, and agent trace.
- The architecture is ready for stronger contradiction checks or reranking later.

## Docker Deployment

### Quick Start (recommended)

```bash
# 1. Copy and edit environment config
copy .env.example .env
# Edit .env — set OPENAI_API_KEY etc.

# 2. Build and start
docker compose up -d --build

# 3. Access the UI
# Open http://localhost:8001
```

### Build Image Only

```bash
docker build -t esg-rag-agent .
```

### Run Container Manually

```bash
docker run -d \
  --name esg-rag \
  -p 8001:8001 \
  --env-file .env \
  -v esg-storage:/app/storage \
  -v esg-data:/app/data \
  esg-rag-agent
```

### Key Docker Features

- **Multi-stage build** — build dependencies in a builder stage, keep runtime image slim (~1.5 GB with embedding model)
- **Pre-downloaded embedding model** — `all-MiniLM-L6-v2` is baked into the image, no download at startup
- **Persistent volumes** — `storage/` (knowledge bases, indexes) and `data/` (uploads) survive container restarts
- **Non-root user** — runs as `appuser` for security
- **Health check** — built-in `/health` endpoint monitoring
- **Graceful shutdown** — uses `tini` as init process for proper signal handling

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8001` | Server port |
| `WORKERS` | `1` | Uvicorn worker count |
| `LOG_LEVEL` | `info` | Log level (debug/info/warning/error) |
| `OPENAI_API_KEY` | (empty) | LLM API key (leave empty for fallback mode) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | LLM API base URL |
| `OPENAI_CHAT_MODEL` | `gpt-4.1-mini` | LLM model name |
| `LOCAL_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Local embedding model |

### Deploy to Cloud Platforms

**Deploy to any Docker-compatible platform:**

```bash
# Tag and push to registry
docker tag esg-rag-agent your-registry.com/esg-rag-agent:latest
docker push your-registry.com/esg-rag-agent:latest
```

Supported platforms: AWS ECS/Fargate, Google Cloud Run, Azure Container Instances, Railway, Render, Fly.io, etc.

## Notes

- Sample data is included under `data/sample/`.
- Chroma and Milvus are optional; the default `simple` backend works immediately.
- PDF and DOCX ingestion relies on `pypdf` and `python-docx` text extraction.
- For production use, add authentication, async background jobs, and audit logging.
