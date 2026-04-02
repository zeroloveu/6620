from __future__ import annotations

import re

ESG_SYNONYMS: dict[str, list[str]] = {
    "carbon": ["GHG", "greenhouse gas", "CO2", "carbon dioxide"],
    "emissions": ["GHG emissions", "carbon footprint", "Scope 1", "Scope 2", "Scope 3"],
    "climate": ["global warming", "climate change", "climate risk", "climate action"],
    "energy": ["renewable energy", "energy consumption", "energy efficiency", "power"],
    "water": ["water consumption", "water management", "water stewardship", "wastewater"],
    "waste": ["waste management", "recycling", "circular economy", "hazardous waste"],
    "biodiversity": ["ecosystem", "deforestation", "land use", "habitat"],
    "diversity": ["DEI", "inclusion", "gender equity", "equal opportunity"],
    "safety": ["health and safety", "occupational safety", "workplace safety", "OHS"],
    "employee": ["workforce", "human capital", "staff", "personnel", "labor"],
    "training": ["capacity building", "professional development", "skill development"],
    "supplier": ["supply chain", "vendor", "procurement", "sourcing"],
    "community": ["social impact", "stakeholder engagement", "philanthropy", "CSR"],
    "governance": ["corporate governance", "board oversight", "accountability"],
    "board": ["board of directors", "independent directors", "board composition"],
    "ethics": ["business ethics", "code of conduct", "anti-corruption", "integrity"],
    "compliance": ["regulatory compliance", "legal compliance", "policy compliance"],
    "risk": ["risk management", "enterprise risk", "material risk", "ESG risk"],
    "audit": ["internal audit", "external audit", "assurance", "verification"],
    "disclosure": ["reporting", "transparency", "material disclosure"],
    "scope 1": ["direct emissions", "Scope 1 emissions"],
    "scope 2": ["indirect emissions", "Scope 2 emissions", "purchased electricity"],
    "scope 3": ["value chain emissions", "Scope 3 emissions", "upstream downstream"],
    "materiality": ["material topics", "materiality assessment", "double materiality"],
    "碳排放": ["carbon emissions", "温室气体", "GHG", "碳足迹"],
    "环境": ["environment", "environmental", "环保", "生态"],
    "社会": ["social", "社会责任", "CSR"],
    "治理": ["governance", "公司治理", "董事会"],
    "可持续": ["sustainability", "sustainable development", "可持续发展"],
    "排放": ["emissions", "排放量", "碳排放", "温室气体排放"],
    "能源": ["energy", "能源消耗", "可再生能源", "清洁能源"],
    "员工": ["employee", "workforce", "人力资源", "劳动力"],
    "安全": ["safety", "安全管理", "职业健康", "生产安全"],
    "多样性": ["diversity", "多元化", "包容性", "性别平等"],
    "合规": ["compliance", "合规管理", "法律合规"],
    "风险": ["risk", "风险管理", "风险评估"],
}

_TERM_PATTERN = re.compile(
    "|".join(re.escape(k) for k in sorted(ESG_SYNONYMS, key=len, reverse=True)),
    re.IGNORECASE,
)


def expand_query(query: str, max_variants: int = 3) -> list[str]:
    """Return the original query plus up to *max_variants* synonym-expanded variants."""
    variants: list[str] = [query]
    query_lower = query.lower()

    matched_terms: list[tuple[str, list[str]]] = []
    for term, synonyms in ESG_SYNONYMS.items():
        if term.lower() in query_lower:
            matched_terms.append((term, synonyms))

    for term, synonyms in matched_terms:
        for syn in synonyms[:max_variants]:
            variant = re.sub(re.escape(term), syn, query, count=1, flags=re.IGNORECASE)
            if variant != query and variant not in variants:
                variants.append(variant)
            if len(variants) >= max_variants + 1:
                return variants

    return variants


def enrich_query(query: str) -> str:
    """Append related ESG terms to the query for broader recall."""
    query_lower = query.lower()
    extra_terms: list[str] = []
    for term, synonyms in ESG_SYNONYMS.items():
        if term.lower() in query_lower:
            for syn in synonyms[:2]:
                if syn.lower() not in query_lower:
                    extra_terms.append(syn)
    if not extra_terms:
        return query
    return f"{query} {' '.join(extra_terms[:6])}"
