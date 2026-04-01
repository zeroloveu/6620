from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from esg_rag.config import settings
from esg_rag.knowledge_base import KnowledgeBaseManager
from esg_rag.pipeline import ESGAnalysisPipeline
from esg_rag.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    DocUpdateRequest,
    IngestResponse,
    KBCreateRequest,
    KBDetail,
    KBIndexResponse,
    KBSummary,
    KBUpdateRequest,
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
    UploadResponse,
)

app = FastAPI(
    title="ESG RAG Agent API",
    description="ESG analysis system based on RAG and agentic workflows.",
    version="0.1.0",
)
static_dir = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=static_dir / "static"), name="static")


@lru_cache(maxsize=1)
def get_pipeline() -> ESGAnalysisPipeline:
    return ESGAnalysisPipeline()


@lru_cache(maxsize=1)
def get_kb_manager() -> KnowledgeBaseManager:
    return KnowledgeBaseManager(settings.kb_storage_dir)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "vector_backend": settings.vector_backend}


@app.get("/system")
def system_info() -> dict[str, object]:
    return get_pipeline().system_snapshot()


@app.post("/ingest", response_model=IngestResponse)
def ingest() -> IngestResponse:
    files_indexed, chunks_indexed, sources = get_pipeline().ingest()
    return IngestResponse(
        files_indexed=files_indexed,
        chunks_indexed=chunks_indexed,
        sources=sources,
        vector_backend=settings.vector_backend,
    )


@app.post("/upload", response_model=UploadResponse)
async def upload(files: list[UploadFile] = File(...)) -> UploadResponse:
    payload: list[tuple[str, bytes]] = []
    for file in files:
        payload.append((file.filename or "uploaded_file", await file.read()))
    saved_files, files_indexed, chunks_indexed, sources = get_pipeline().ingest_files(payload)
    return UploadResponse(
        saved_files=saved_files,
        files_indexed=files_indexed,
        chunks_indexed=chunks_indexed,
        sources=sources,
        vector_backend=settings.vector_backend,
    )


def _resolve_kb_index_dirs(kb_ids: list[str] | None) -> list[Path]:
    """Return index dirs for the given KB IDs, or ALL KBs if none specified."""
    mgr = get_kb_manager()
    if kb_ids:
        return [mgr.index_dir(kid) for kid in kb_ids]
    all_kbs = mgr.list_kbs()
    return [mgr.index_dir(kb["id"]) for kb in all_kbs]


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    pipeline = get_pipeline()
    index_dirs = _resolve_kb_index_dirs(request.kb_ids)
    if index_dirs:
        results = pipeline.query_kbs(request.query, index_dirs, request.top_k)
    else:
        results = pipeline.query(request.query, request.top_k)
    return QueryResponse(
        query=request.query,
        results=[
            RetrievedChunk(
                chunk_id=item.chunk_id,
                score=item.score,
                text=item.text,
                metadata=item.metadata,
            )
            for item in results
        ],
    )


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnalysisRequest) -> AnalysisResponse:
    pipeline = get_pipeline()
    index_dirs = _resolve_kb_index_dirs(request.kb_ids)
    if index_dirs:
        report, raw_results = pipeline.analyze_kbs(
            company_name=request.company_name,
            query=request.query,
            framework_focus=request.framework_focus,
            index_dirs=index_dirs,
            top_k=request.top_k,
        )
    else:
        report, raw_results = pipeline.analyze(
            company_name=request.company_name,
            query=request.query,
            framework_focus=request.framework_focus,
            top_k=request.top_k,
        )
    report["company_name"] = request.company_name
    report["raw_context"] = [
        RetrievedChunk(
            chunk_id=item.chunk_id,
            score=item.score,
            text=item.text,
            metadata=item.metadata,
        ).model_dump()
        for item in raw_results
    ]
    return AnalysisResponse(**report)


# ── Knowledge-base routes ───────────────────────────────────────────


@app.get("/kb", response_model=list[KBSummary])
def list_knowledge_bases() -> list[KBSummary]:
    return [KBSummary(**kb) for kb in get_kb_manager().list_kbs()]


@app.post("/kb", response_model=KBSummary, status_code=201)
def create_knowledge_base(request: KBCreateRequest) -> KBSummary:
    return KBSummary(**get_kb_manager().create_kb(request.name, request.description))


@app.get("/kb/{kb_id}", response_model=KBDetail)
def get_knowledge_base(kb_id: str) -> KBDetail:
    kb = get_kb_manager().get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return KBDetail(**kb)


@app.put("/kb/{kb_id}", response_model=KBSummary)
def update_knowledge_base(kb_id: str, request: KBUpdateRequest) -> KBSummary:
    kb = get_kb_manager().update_kb(kb_id, request.name, request.description)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return KBSummary(**kb)


@app.delete("/kb/{kb_id}", status_code=204)
def delete_knowledge_base(kb_id: str) -> None:
    if not get_kb_manager().delete_kb(kb_id):
        raise HTTPException(status_code=404, detail="Knowledge base not found")


@app.post("/kb/{kb_id}/documents")
async def upload_kb_documents(
    kb_id: str, files: list[UploadFile] = File(...)
) -> dict:
    mgr = get_kb_manager()
    if not mgr.get_kb(kb_id):
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    payload: list[tuple[str, bytes]] = []
    for f in files:
        payload.append((f.filename or "uploaded_file", await f.read()))
    added = mgr.add_documents(kb_id, payload)
    files_indexed, chunks_indexed, sources = get_pipeline().index_kb(
        mgr.files_dir(kb_id), mgr.index_dir(kb_id)
    )
    return {
        "documents": added,
        "index": {
            "files_indexed": files_indexed,
            "chunks_indexed": chunks_indexed,
            "sources": sources,
        },
    }


@app.put("/kb/{kb_id}/documents/{doc_id}")
def update_kb_document(kb_id: str, doc_id: str, request: DocUpdateRequest) -> dict:
    mgr = get_kb_manager()
    doc = mgr.update_document(kb_id, doc_id, request.original_name)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.delete("/kb/{kb_id}/documents/{doc_id}", status_code=204)
def delete_kb_document(kb_id: str, doc_id: str) -> None:
    if not get_kb_manager().delete_document(kb_id, doc_id):
        raise HTTPException(status_code=404, detail="Document not found")


@app.post("/kb/{kb_id}/index", response_model=KBIndexResponse)
def index_knowledge_base(kb_id: str) -> KBIndexResponse:
    mgr = get_kb_manager()
    if not mgr.get_kb(kb_id):
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    files_dir = mgr.files_dir(kb_id)
    index_dir = mgr.index_dir(kb_id)
    files_indexed, chunks_indexed, sources = get_pipeline().index_kb(files_dir, index_dir)
    return KBIndexResponse(
        kb_id=kb_id,
        files_indexed=files_indexed,
        chunks_indexed=chunks_indexed,
        sources=sources,
    )
