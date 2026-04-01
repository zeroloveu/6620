from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict

from esg_rag.config import Settings
from esg_rag.llm import LLMClient
from esg_rag.models import SearchResult

DEFAULT_FRAMEWORKS = ["GRI", "SASB", "TCFD", "CSRD"]
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "based",
    "company",
    "for",
    "generate",
    "how",
    "in",
    "is",
    "of",
    "on",
    "provide",
    "report",
    "structured",
    "the",
    "to",
    "using",
    "what",
}
TAG_RULES = {
    "environment": {
        "climate",
        "emission",
        "emissions",
        "energy",
        "water",
        "waste",
        "renewable",
        "scope 1",
        "scope 2",
        "biodiversity",
    },
    "social": {
        "employee",
        "employees",
        "safety",
        "supplier",
        "suppliers",
        "community",
        "women",
        "diversity",
        "workforce",
        "training",
        "labor",
    },
    "governance": {
        "board",
        "governance",
        "ethics",
        "committee",
        "corruption",
        "compliance",
        "whistleblower",
        "oversight",
        "risk",
        "audit",
    },
}


def _normalize_frameworks(framework_focus: list[str]) -> list[str]:
    frameworks = [item.strip().upper() for item in framework_focus if item.strip()]
    return frameworks or DEFAULT_FRAMEWORKS.copy()


def _extract_keywords(text: str, limit: int = 6) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9-]{2,}", text.lower())
    keywords: list[str] = []
    for token in tokens:
        if token in STOPWORDS:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


def _clean_excerpt(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


class PlannerAgent:
    def run(self, company_name: str, user_query: str, framework_focus: list[str]) -> dict:
        framework_terms = _normalize_frameworks(framework_focus)
        keyword_string = " ".join(_extract_keywords(user_query))
        sub_queries = [
            f"{company_name} environment climate emissions energy water targets {keyword_string}".strip(),
            f"{company_name} social workforce safety diversity supply chain community {keyword_string}".strip(),
            f"{company_name} governance board risk ethics compliance oversight {keyword_string}".strip(),
            f"{company_name} {' '.join(framework_terms)} disclosure alignment material topics {keyword_string}".strip(),
            f"{company_name} controversies media sentiment ESG strengths weaknesses {keyword_string}".strip(),
        ]
        return {
            "objective": user_query,
            "sub_queries": sub_queries,
            "framework_focus": framework_terms,
            "keywords": _extract_keywords(user_query),
        }


class RetrievalAgent:
    def run(self, queries: list[str], retriever, top_k: int) -> list[SearchResult]:
        collected: dict[str, SearchResult] = {}
        for query in queries:
            for result in retriever.search(query, top_k=top_k):
                existing = collected.get(result.chunk_id)
                if existing is None or result.score > existing.score:
                    collected[result.chunk_id] = result
        return sorted(collected.values(), key=lambda item: item.score, reverse=True)[:top_k]


class EvidenceFusionAgent:
    def run(self, results: list[SearchResult]) -> list[dict]:
        fused: list[dict] = []
        for result in results:
            text_lower = result.text.lower()
            tags = [tag for tag, keywords in TAG_RULES.items() if any(token in text_lower for token in keywords)]
            if not tags:
                tags.append("general")
            fused.append({**asdict(result), "tags": tags, "excerpt": _clean_excerpt(result.text)})
        return fused


class VerificationAgent:
    def run(self, results: list[dict]) -> list[dict]:
        verified: list[dict] = []
        for result in results:
            notes: list[str] = []
            metadata = result["metadata"]
            if len(result["text"]) < 120:
                notes.append("Short excerpt; inspect adjacent source context.")
            if result["score"] < 0.2:
                notes.append("Similarity score is modest, so this evidence should be cross-checked.")
            if "source" not in metadata:
                notes.append("Missing source metadata.")
            else:
                notes.append(f"Traceable source: {metadata.get('source_name', metadata['source'])}.")
            if metadata.get("page") is not None:
                notes.append(f"Page {metadata['page']} available for citation.")
            if metadata.get("source_type") == "json":
                notes.append("Structured supplementary data; corroborate against narrative disclosures.")
            verified.append({**result, "verification_notes": " ".join(notes)})
        return verified


class ComplianceAgent:
    def run(self, framework_focus: list[str], evidence: list[dict]) -> dict:
        frameworks = _normalize_frameworks(framework_focus)
        alignment: dict[str, dict] = {}
        for framework in frameworks:
            evidence_hits = []
            covered_tags: set[str] = set()
            for item in evidence:
                tags = item.get("tags", [])
                excerpt = item.get("excerpt") or _clean_excerpt(item["text"])
                if framework == "TCFD" and "environment" in tags:
                    evidence_hits.append(excerpt)
                    covered_tags.update(tags)
                elif framework == "SASB" and any(tag in tags for tag in ("environment", "social", "governance")):
                    evidence_hits.append(excerpt)
                    covered_tags.update(tags)
                elif framework in {"GRI", "CSRD"}:
                    evidence_hits.append(excerpt)
                    covered_tags.update(tags)
            count = len(evidence_hits)
            if count >= 4:
                coverage = "high"
            elif count >= 2:
                coverage = "moderate"
            elif count == 1:
                coverage = "limited"
            else:
                coverage = "low"
            alignment[framework] = {
                "coverage": coverage,
                "matched_evidence_count": count,
                "covered_topics": sorted(tag for tag in covered_tags if tag != "general"),
                "notes": evidence_hits[:3],
            }
        return alignment


class ConfidenceAgent:
    def run(self, evidence: list[dict]) -> dict:
        if not evidence:
            return {"level": "low", "score": 0.0, "reason": "No evidence retrieved."}
        avg_score = sum(item["score"] for item in evidence) / len(evidence)
        traceable_ratio = sum(1 for item in evidence if "source" in item["metadata"]) / len(evidence)
        coverage_ratio = len({tag for item in evidence for tag in item.get("tags", []) if tag != "general"}) / 3
        evidence_volume = min(len(evidence) / 6, 1.0)
        numeric_score = round(
            (avg_score * 0.55) + (traceable_ratio * 0.2) + (coverage_ratio * 0.15) + (evidence_volume * 0.1),
            3,
        )
        if numeric_score >= 0.72:
            level = "high"
        elif numeric_score >= 0.48:
            level = "medium"
        else:
            level = "low"
        return {
            "level": level,
            "score": numeric_score,
            "reason": "Blend of retrieval quality, traceability, topic coverage, and evidence volume.",
        }


class TraceAgent:
    def run(self, plan: dict, evidence: list[dict], compliance: dict, confidence: dict) -> list[dict]:
        tag_counter = Counter(tag for item in evidence for tag in item.get("tags", []))
        return [
            {"agent": "planner", "output": plan},
            {
                "agent": "retrieval_fusion",
                "retrieved_evidence": len(evidence),
                "tag_breakdown": dict(tag_counter),
            },
            {"agent": "compliance", "output": compliance},
            {"agent": "confidence", "output": confidence},
        ]


class ReportAgent:
    def __init__(self, settings: Settings) -> None:
        self.llm = LLMClient(settings)

    def run(
        self,
        company_name: str,
        user_query: str,
        framework_focus: list[str],
        evidence: list[dict],
        compliance_alignment: dict,
        confidence_assessment: dict,
        agent_trace: list[dict],
    ) -> dict:
        evidence_text = "\n\n".join(
            [
                (
                    f"Source: {item['metadata'].get('source', 'unknown')}\n"
                    f"Page: {item['metadata'].get('page')}\n"
                    f"Score: {item['score']:.4f}\n"
                    f"Tags: {', '.join(item.get('tags', []))}\n"
                    f"Verification: {item['verification_notes']}\n"
                    f"Excerpt:\n{item['text']}"
                )
                for item in evidence
            ]
        )
        prompt = f"""
Company: {company_name}
User request: {user_query}
Framework focus: {", ".join(_normalize_frameworks(framework_focus))}
Compliance alignment input: {compliance_alignment}
Confidence assessment input: {confidence_assessment}
Agent trace summary: {agent_trace}

You must produce a structured ESG analysis with Environment, Social, Governance,
compliance alignment, confidence assessment, and next steps.
Use only the evidence below and be explicit about gaps.

Evidence:
{evidence_text}
""".strip()
        report = self.llm.structured_esg_report(
            prompt=prompt,
            company_name=company_name,
            evidence=evidence,
            compliance_alignment=compliance_alignment,
            confidence_assessment=confidence_assessment,
        )
        report["compliance_alignment"] = compliance_alignment
        report["confidence_assessment"] = confidence_assessment
        report["agent_trace"] = agent_trace
        return report
