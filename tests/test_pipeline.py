from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from esg_rag.config import Settings
from esg_rag.main import app
from esg_rag.pipeline import ESGAnalysisPipeline


def build_test_settings(tmp_path: Path) -> Settings:
    return Settings(
        DATA_DIR=Path("C:/Users/81011/Desktop/Myrag/data/sample"),
        INDEX_DIR=tmp_path / "index",
        UPLOAD_DIR=tmp_path / "uploads",
        OPENAI_API_KEY=None,
        EMBEDDING_BACKEND="hash",
    )


def test_ingest_query_and_analyze(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    pipeline = ESGAnalysisPipeline(settings)

    files_indexed, chunks_indexed, sources = pipeline.ingest()
    assert files_indexed >= 3
    assert chunks_indexed >= 3
    assert any("company_a_esg_report.md" in source for source in sources)

    query_results = pipeline.query("emissions and climate governance", top_k=3)
    assert query_results
    assert any(
        "Scope 1" in item.text or "Climate risk management" in item.text for item in query_results
    )

    report, raw_results = pipeline.analyze(
        company_name="Company A",
        query="Generate a structured ESG analysis for Company A.",
        framework_focus=["GRI", "TCFD"],
        top_k=4,
    )
    assert raw_results
    assert report["executive_summary"]
    assert report["environment"]["title"] == "Environment"
    assert report["confidence_assessment"]["score"] >= 0
    assert report["agent_trace"]


def test_api_endpoints() -> None:
    client = TestClient(app)

    home = client.get("/")
    assert home.status_code == 200
    assert "ESG RAG Analyst" in home.text

    system = client.get("/system")
    assert system.status_code == 200
    assert "vector_backend" in system.json()
    assert "embedding_backend" in system.json()

    query = client.post("/query", json={"query": "climate governance Company A", "top_k": 3})
    assert query.status_code == 200
    assert "results" in query.json()
