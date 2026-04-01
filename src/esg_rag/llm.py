from __future__ import annotations

import json
import logging
import re
from textwrap import shorten

import httpx

from esg_rag.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an ESG analyst. Use only supplied evidence. \
If evidence is weak, say so explicitly.

You MUST respond with a valid JSON object (no markdown fences, no extra text) \
matching this structure:
{
  "executive_summary": "string",
  "environment": { "title": "string", "summary": "string", "findings": ["..."], "risks": ["..."], "opportunities": ["..."], "evidence": [{"source": "string", "page": null, "score": 0.0, "excerpt": "string", "verification_notes": "string"}] },
  "social":      { same structure as environment },
  "governance":  { same structure as environment },
  "compliance_alignment": { ... },
  "confidence_assessment": { ... },
  "next_steps": ["string"]
}"""


def _extract_json(text: str) -> dict:
    """Extract a JSON object from LLM output that may be wrapped in markdown fences."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _compact_text(text: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _evidence_item(item: dict) -> dict:
    metadata = item.get("metadata", {})
    return {
        "source": metadata.get("source_name", metadata.get("source", "unknown")),
        "page": metadata.get("page"),
        "score": round(float(item.get("score", 0.0)), 3),
        "excerpt": _compact_text(item.get("excerpt") or item.get("text", "")),
        "verification_notes": item.get("verification_notes", "Evidence retrieved from indexed sources."),
    }


def _section_from_evidence(title: str, tag: str, evidence: list[dict]) -> dict:
    tagged = [item for item in evidence if tag in item.get("tags", [])]
    selected = tagged[:3]
    if not selected:
        return {
            "title": title,
            "summary": f"No strong {title.lower()} evidence was retrieved from the current corpus.",
            "findings": ["Current retrieval did not surface enough direct evidence for this section."],
            "risks": ["Expand indexed disclosures or refine the query before relying on this section externally."],
            "opportunities": [f"Add more {title.lower()}-specific reports, policies, or metrics for stronger coverage."],
            "evidence": [],
        }
    findings = [_compact_text(item.get("excerpt") or item.get("text", "")) for item in selected]
    low_confidence = any("modest" in item.get("verification_notes", "").lower() for item in selected)
    summary = f"{title} coverage is supported by {len(tagged)} retrieved evidence snippet(s) from indexed sources."
    risks = []
    if len(tagged) < 2:
        risks.append(f"{title} coverage is thin and may not represent the full disclosure set.")
    if low_confidence:
        risks.append("Some supporting evidence has only moderate retrieval confidence.")
    if not risks:
        risks.append("Evidence is traceable, but conclusions should still be reviewed against full source context.")
    opportunities = [
        f"Use the cited {title.lower()} evidence as the base for analyst review or framework mapping.",
    ]
    if len(tagged) < 3:
        opportunities.append(f"Index additional {title.lower()} documents to improve coverage depth.")
    return {
        "title": title,
        "summary": summary,
        "findings": findings,
        "risks": risks,
        "opportunities": opportunities,
        "evidence": [_evidence_item(item) for item in selected],
    }


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def structured_esg_report(
        self,
        prompt: str,
        company_name: str,
        evidence: list[dict],
        compliance_alignment: dict,
        confidence_assessment: dict,
    ) -> dict:
        if not self.settings.openai_api_key:
            return self._fallback_report(
                company_name,
                evidence,
                compliance_alignment,
                confidence_assessment,
            )
        try:
            return self._chat_report(prompt)
        except Exception:
            logger.exception("LLM API call failed, falling back to template report")
            return self._fallback_report(
                company_name,
                evidence,
                compliance_alignment,
                confidence_assessment,
            )

    def _chat_report(self, prompt: str) -> dict:
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.settings.openai_chat_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
        }
        url = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        logger.info("Calling LLM at %s with model %s", url, self.settings.openai_chat_model)
        timeout = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=30.0)
        content_parts: list[str] = []
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        content_parts.append(delta["content"])
        content = "".join(content_parts)
        if not content:
            raise ValueError("LLM returned empty content")
        logger.info("LLM response received (%d chars)", len(content))
        return _extract_json(content)

    def _fallback_report(
        self,
        company_name: str,
        evidence: list[dict],
        compliance_alignment: dict,
        confidence_assessment: dict,
    ) -> dict:
        top_evidence = evidence[:3]
        executive_anchor = shorten(
            " ".join(_compact_text(item.get("excerpt") or item.get("text", ""), limit=140) for item in top_evidence),
            width=320,
            placeholder="...",
        )
        weak_frameworks = [
            framework
            for framework, payload in compliance_alignment.items()
            if payload.get("coverage") in {"low", "limited"}
        ]
        next_steps = [
            "Review cited evidence against full source context before external use.",
            "Add more benchmark and company disclosures to improve framework coverage.",
        ]
        if weak_frameworks:
            next_steps.append(f"Strengthen evidence for: {', '.join(weak_frameworks)}.")
        if confidence_assessment.get("level") != "high":
            next_steps.append("Re-run analysis after indexing more source material or enabling an external LLM.")
        return {
            "executive_summary": (
                f"Fallback mode produced this ESG draft for {company_name} using retrieved evidence only. "
                f"Key evidence includes: {executive_anchor or 'no strong evidence was retrieved.'}"
            ),
            "environment": _section_from_evidence("Environment", "environment", evidence),
            "social": _section_from_evidence("Social", "social", evidence),
            "governance": _section_from_evidence("Governance", "governance", evidence),
            "compliance_alignment": compliance_alignment,
            "confidence_assessment": confidence_assessment,
            "next_steps": next_steps,
        }
