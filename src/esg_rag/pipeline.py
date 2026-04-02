from __future__ import annotations

from pathlib import Path
import re
from uuid import uuid4

from esg_rag.agents import (
    ComplianceAgent,
    ConfidenceAgent,
    EvidenceFusionAgent,
    PlannerAgent,
    ReportAgent,
    RetrievalAgent,
    TraceAgent,
    VerificationAgent,
)
from esg_rag.chunking import ESGChunker
from esg_rag.config import Settings, settings
from esg_rag.document_loader import DocumentLoader
from esg_rag.embedding import build_embedding_provider
from esg_rag.models import SearchResult
from esg_rag.vector_store import SimpleVectorStore, build_vector_store


class Retriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedding_provider = build_embedding_provider(settings)
        self.vector_store = build_vector_store(settings)

    def index_directory(self, directory: Path) -> tuple[int, int, list[str]]:
        loader = DocumentLoader()
        documents = loader.load_directory(directory)
        chunker = ESGChunker(self.settings.chunk_size, self.settings.chunk_overlap)
        chunks = chunker.chunk_documents(documents)
        embeddings = self.embedding_provider.embed_documents([chunk.text for chunk in chunks]) if chunks else []
        if chunks:
            self.vector_store.index(chunks, embeddings)
        sources = sorted({str(doc.metadata.get("source", "unknown")) for doc in documents})
        return len(documents), len(chunks), sources

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        from esg_rag.query_expansion import enrich_query

        top_k = top_k or self.settings.top_k
        enriched = enrich_query(query)
        query_vector = self.embedding_provider.embed_query(enriched)
        candidate_k = max(top_k, top_k * self.settings.retrieval_candidate_multiplier)
        results = self.vector_store.search(query_vector, top_k=candidate_k)
        return self._rerank_results(query, results, top_k=top_k)

    def _rerank_results(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        query_tokens = self._tokenize(query)
        deduped: dict[str, SearchResult] = {}
        for result in results:
            normalized_text = self._normalize_text(result.text)
            keyword_overlap = self._keyword_overlap(query_tokens, self._tokenize(result.text))
            source_penalty = 0.02 if "\\uploads\\" in str(result.metadata.get("source", "")).lower() else 0.0
            boosted_score = float(result.score) + (keyword_overlap * 0.2) - source_penalty
            boosted = SearchResult(
                chunk_id=result.chunk_id,
                score=round(boosted_score, 4),
                text=result.text,
                metadata=result.metadata,
            )
            existing = deduped.get(normalized_text)
            if existing is None or boosted.score > existing.score:
                deduped[normalized_text] = boosted
        ranked = sorted(deduped.values(), key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    def _tokenize(self, text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9\u4e00-\u9fff][a-zA-Z0-9\u4e00-\u9fff-]{1,}", text.lower()))

    def _keyword_overlap(self, query_tokens: set[str], result_tokens: set[str]) -> float:
        if not query_tokens:
            return 0.0
        return len(query_tokens & result_tokens) / len(query_tokens)

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()


class ESGAnalysisPipeline:
    def __init__(self, settings_obj: Settings | None = None) -> None:
        self.settings = settings_obj or settings
        self.retriever = Retriever(self.settings)
        self.planner_agent = PlannerAgent()
        self.retrieval_agent = RetrievalAgent()
        self.evidence_fusion_agent = EvidenceFusionAgent()
        self.verification_agent = VerificationAgent()
        self.compliance_agent = ComplianceAgent()
        self.confidence_agent = ConfidenceAgent()
        self.trace_agent = TraceAgent()
        self.report_agent = ReportAgent(self.settings)

    def ingest(self) -> tuple[int, int, list[str]]:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.index_dir.mkdir(parents=True, exist_ok=True)
        return self.retriever.index_directory(self.settings.data_dir)

    def ingest_files(self, files: list[tuple[str, bytes]]) -> tuple[list[str], int, int, list[str]]:
        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        saved_files: list[str] = []
        for original_name, content in files:
            target = self.settings.upload_dir / f"{uuid4().hex}_{Path(original_name).name}"
            target.write_bytes(content)
            saved_files.append(str(target))
        files_indexed, chunks_indexed, sources = self.ingest()
        return saved_files, files_indexed, chunks_indexed, sources

    def query(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        return self.retriever.search(query, top_k or self.settings.top_k)

    def system_snapshot(self) -> dict[str, object]:
        store = self.retriever.vector_store
        store_stats = store.stats() if hasattr(store, "stats") else {}
        return {
            "vector_backend": self.settings.vector_backend,
            "embedding_backend": getattr(self.retriever.embedding_provider, "provider_name", "unknown"),
            "openai_enabled": str(bool(self.settings.openai_api_key)).lower(),
            "data_dir": str(self.settings.data_dir),
            "upload_dir": str(self.settings.upload_dir),
            "indexed_chunks": store_stats.get("chunk_count"),
            "indexed_sources": store_stats.get("source_count"),
            "source_preview": store_stats.get("source_preview", []),
        }

    def analyze(
        self,
        company_name: str,
        query: str,
        framework_focus: list[str],
        top_k: int | None = None,
    ) -> tuple[dict, list[SearchResult]]:
        return self._run_analysis(self.retriever, company_name, query, framework_focus, top_k)

    # ── Knowledge-base operations ───────────────────────────────────

    def index_kb(self, files_dir: Path, index_dir: Path) -> tuple[int, int, list[str]]:
        index_dir.mkdir(parents=True, exist_ok=True)
        loader = DocumentLoader()
        documents = loader.load_directory(files_dir)
        chunker = ESGChunker(self.settings.chunk_size, self.settings.chunk_overlap)
        chunks = chunker.chunk_documents(documents)
        store = SimpleVectorStore(index_dir)
        if chunks:
            embeddings = self.retriever.embedding_provider.embed_documents(
                [c.text for c in chunks]
            )
            store.index(chunks, embeddings)
        else:
            store.clear()
        sources = sorted({str(doc.metadata.get("source", "unknown")) for doc in documents})
        return len(documents), len(chunks), sources

    def query_kbs(
        self, query: str, index_dirs: list[Path], top_k: int | None = None
    ) -> list[SearchResult]:
        retriever = _KBRetriever(self.retriever.embedding_provider, index_dirs, self.settings)
        return retriever.search(query, top_k)

    def analyze_kbs(
        self,
        company_name: str,
        query: str,
        framework_focus: list[str],
        index_dirs: list[Path],
        top_k: int | None = None,
    ) -> tuple[dict, list[SearchResult]]:
        retriever = _KBRetriever(self.retriever.embedding_provider, index_dirs, self.settings)
        return self._run_analysis(retriever, company_name, query, framework_focus, top_k)

    # ── Shared analysis pipeline ────────────────────────────────────

    def _run_analysis(self, retriever, company_name, query, framework_focus, top_k=None):
        plan = self.planner_agent.run(company_name, query, framework_focus)
        raw_results = self.retrieval_agent.run(
            plan["sub_queries"], retriever, top_k=top_k or self.settings.max_context_chunks
        )
        fused = self.evidence_fusion_agent.run(raw_results)
        verified = self.verification_agent.run(fused)
        compliance = self.compliance_agent.run(framework_focus, verified)
        confidence = self.confidence_agent.run(verified)
        agent_trace = self.trace_agent.run(plan, verified, compliance, confidence)
        report = self.report_agent.run(
            company_name, query, framework_focus, verified, compliance, confidence, agent_trace,
        )
        return report, raw_results


class _KBRetriever:
    """Searches across one or more knowledge-base indexes with reranking."""

    _YEAR_RE = re.compile(r"(20\d{2})")

    def __init__(self, embedding_provider, index_dirs: list[Path], settings: Settings) -> None:
        self.embedding_provider = embedding_provider
        self.stores = [SimpleVectorStore(d) for d in index_dirs if d.exists()]
        self.settings = settings

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        from esg_rag.query_expansion import enrich_query

        top_k = top_k or self.settings.top_k
        candidate_k = max(top_k, top_k * self.settings.retrieval_candidate_multiplier)

        enriched = enrich_query(query)
        query_vector = self.embedding_provider.embed_query(enriched)

        all_results: list[SearchResult] = []
        for store in self.stores:
            all_results.extend(store.search(query_vector, top_k=candidate_k))

        return self._rerank(query, all_results, top_k)

    def _rerank(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        query_tokens = self._tokenize(query)
        deduped: dict[str, SearchResult] = {}

        for r in results:
            norm_text = re.sub(r"\s+", " ", r.text).strip().lower()
            kw_overlap = self._keyword_overlap(query_tokens, self._tokenize(r.text))
            year_boost = self._temporal_boost(r.metadata)
            score = float(r.score) + (kw_overlap * 0.15) + year_boost

            boosted = SearchResult(
                chunk_id=r.chunk_id,
                score=round(score, 4),
                text=r.text,
                metadata=r.metadata,
            )
            existing = deduped.get(norm_text)
            if existing is None or boosted.score > existing.score:
                deduped[norm_text] = boosted

        ranked = sorted(deduped.values(), key=lambda x: x.score, reverse=True)
        return ranked[:top_k]

    def _temporal_boost(self, metadata: dict) -> float:
        name = metadata.get("source_name", "")
        match = self._YEAR_RE.search(name)
        if not match:
            return 0.0
        age = max(0, 2026 - int(match.group(1)))
        return round(-0.01 * age, 4)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9\u4e00-\u9fff][a-zA-Z0-9\u4e00-\u9fff-]{1,}", text.lower()))

    @staticmethod
    def _keyword_overlap(query_tokens: set[str], result_tokens: set[str]) -> float:
        if not query_tokens:
            return 0.0
        return len(query_tokens & result_tokens) / len(query_tokens)
