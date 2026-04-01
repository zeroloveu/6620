from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Knowledge-base schemas ──────────────────────────────────────────


class KBCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""


class KBUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class KBDocumentInfo(BaseModel):
    id: str
    original_name: str
    stored_name: str
    file_size: int
    file_type: str
    created_at: str


class KBSummary(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    created_at: str
    updated_at: str


class KBDetail(KBSummary):
    documents: list[KBDocumentInfo] = Field(default_factory=list)


class KBIndexResponse(BaseModel):
    kb_id: str
    files_indexed: int
    chunks_indexed: int
    sources: list[str]


class DocUpdateRequest(BaseModel):
    original_name: str | None = None


# ── Original schemas ────────────────────────────────────────────────


class IngestResponse(BaseModel):
    files_indexed: int
    chunks_indexed: int
    sources: list[str]
    vector_backend: str | None = None


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3)
    top_k: int | None = None
    kb_ids: list[str] | None = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    score: float
    text: str
    metadata: dict[str, Any]


class QueryResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]


class UploadResponse(BaseModel):
    saved_files: list[str]
    files_indexed: int
    chunks_indexed: int
    sources: list[str]
    vector_backend: str | None = None


class AnalysisRequest(BaseModel):
    company_name: str
    query: str = Field(
        default="Provide a structured ESG analysis for the company using available evidence."
    )
    top_k: int | None = None
    framework_focus: list[str] = Field(default_factory=lambda: ["GRI", "SASB", "TCFD", "CSRD"])
    kb_ids: list[str] | None = None


class EvidenceItem(BaseModel):
    source: str
    page: int | None = None
    score: float
    excerpt: str
    verification_notes: str


class ESGSection(BaseModel):
    title: str
    summary: str
    findings: list[str]
    risks: list[str]
    opportunities: list[str]
    evidence: list[EvidenceItem]


class AnalysisResponse(BaseModel):
    company_name: str
    executive_summary: str
    environment: ESGSection
    social: ESGSection
    governance: ESGSection
    compliance_alignment: dict[str, Any]
    confidence_assessment: dict[str, Any]
    next_steps: list[str]
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
    raw_context: list[RetrievedChunk]
