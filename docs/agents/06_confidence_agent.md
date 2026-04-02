# ConfidenceAgent — 置信度评分代理

## 概述
`ConfidenceAgent` 是 ESG 分析流程的**第六个**代理,负责综合评估检索证据的**质量和可信度**,生成一个 0-1 之间的数值评分和对应的置信度等级。

## 核心职责
1. **多维度评分** — 综合考虑检索分数、来源可追溯性、主题覆盖度、证据数量
2. **置信度分级** — 将数值评分映射为 `high`/`medium`/`low` 三个等级
3. **生成评分理由** — 说明评分逻辑,帮助用户理解置信度来源

## 输入参数
```python
def run(self, evidence: list[dict]) -> dict:
```

**输入示例** (来自 `VerificationAgent` 的输出):
```python
evidence = [
    {
        "chunk_id": "uuid-1",
        "score": 0.856,
        "metadata": {"source": "tesla_esg_2024.pdf", "page": 15},
        "tags": ["environment"]
    },
    {
        "chunk_id": "uuid-2",
        "score": 0.792,
        "metadata": {"source": "tesla_diversity_report.pdf"},
        "tags": ["social"]
    },
    {
        "chunk_id": "uuid-3",
        "score": 0.745,
        "metadata": {},  # 缺少 source
        "tags": ["governance"]
    },
    {
        "chunk_id": "uuid-4",
        "score": 0.621,
        "metadata": {"source": "financial_data.json"},
        "tags": ["general"]
    }
]
```

## 输出结构
```python
{
    "level": "high",           # 置信度等级: high/medium/low
    "score": 0.748,            # 数值评分 (0-1)
    "reason": "Blend of retrieval quality, traceability, topic coverage, and evidence volume."
}
```

## 评分模型

### 核心公式
```python
numeric_score = (
    avg_score * 0.55 +           # 检索质量权重: 55%
    traceable_ratio * 0.20 +     # 来源可追溯性权重: 20%
    coverage_ratio * 0.15 +      # 主题覆盖度权重: 15%
    evidence_volume * 0.10       # 证据数量权重: 10%
)
```

### 1. 检索质量 (avg_score, 权重 55%)
```python
avg_score = sum(item["score"] for item in evidence) / len(evidence)
```

**含义**: 所有证据的平均相似度分数,反映检索算法的精准度。

**示例**:
- 4 条证据,分数分别为 `0.856, 0.792, 0.745, 0.621`
- `avg_score = (0.856 + 0.792 + 0.745 + 0.621) / 4 = 0.7535`

### 2. 来源可追溯性 (traceable_ratio, 权重 20%)
```python
traceable_ratio = sum(1 for item in evidence if "source" in item["metadata"]) / len(evidence)
```

**含义**: 包含 `source` 元数据的证据比例,反映证据的可引用性。

**示例**:
- 4 条证据中有 3 条包含 `source` 字段
- `traceable_ratio = 3 / 4 = 0.75`

### 3. 主题覆盖度 (coverage_ratio, 权重 15%)
```python
unique_tags = {tag for item in evidence for tag in item.get("tags", []) if tag != "general"}
coverage_ratio = len(unique_tags) / 3  # 3 = ESG 三大维度
```

**含义**: 证据覆盖的 ESG 主题数量,理想情况下应覆盖 environment、social、governance 三个维度。

**示例**:
- 4 条证据的标签: `["environment"]`, `["social"]`, `["governance"]`, `["general"]`
- `unique_tags = {"environment", "social", "governance"}` (排除 `general`)
- `coverage_ratio = 3 / 3 = 1.0`

### 4. 证据数量 (evidence_volume, 权重 10%)
```python
evidence_volume = min(len(evidence) / 6, 1.0)
```

**含义**: 证据数量相对于理想值 (6 条) 的比例,上限为 1.0。

**示例**:
- 4 条证据: `evidence_volume = min(4/6, 1.0) = 0.667`
- 8 条证据: `evidence_volume = min(8/6, 1.0) = 1.0`

## 综合评分示例

### 高质量场景
```python
evidence = [
    {"score": 0.9, "metadata": {"source": "esg_2024.pdf"}, "tags": ["environment"]},
    {"score": 0.85, "metadata": {"source": "diversity_2024.pdf"}, "tags": ["social"]},
    {"score": 0.82, "metadata": {"source": "governance_2024.pdf"}, "tags": ["governance"]},
    {"score": 0.78, "metadata": {"source": "climate_report.pdf"}, "tags": ["environment"]},
    {"score": 0.75, "metadata": {"source": "supply_chain.pdf"}, "tags": ["social"]},
    {"score": 0.72, "metadata": {"source": "audit_report.pdf"}, "tags": ["governance"]},
]

avg_score = 0.803
traceable_ratio = 1.0        # 全部可追溯
coverage_ratio = 1.0         # 覆盖三大维度
evidence_volume = 1.0        # 6 条证据

numeric_score = 0.803*0.55 + 1.0*0.20 + 1.0*0.15 + 1.0*0.10
              = 0.442 + 0.20 + 0.15 + 0.10
              = 0.892

level = "high"  # >= 0.72
```

### 中等质量场景
```python
evidence = [
    {"score": 0.65, "metadata": {"source": "report.pdf"}, "tags": ["environment"]},
    {"score": 0.58, "metadata": {}, "tags": ["social"]},           # 无 source
    {"score": 0.52, "metadata": {"source": "data.json"}, "tags": ["general"]},
]

avg_score = 0.583
traceable_ratio = 0.667      # 2/3 可追溯
coverage_ratio = 0.667       # 覆盖 2/3 维度 (environment, social)
evidence_volume = 0.5        # 3/6 证据

numeric_score = 0.583*0.55 + 0.667*0.20 + 0.667*0.15 + 0.5*0.10
              = 0.321 + 0.133 + 0.100 + 0.050
              = 0.604

level = "medium"  # 0.48 <= score < 0.72
```

### 低质量场景
```python
evidence = [
    {"score": 0.18, "metadata": {}, "tags": ["general"]},
]

avg_score = 0.18
traceable_ratio = 0.0        # 无可追溯来源
coverage_ratio = 0.0         # 无 ESG 标签 (只有 general)
evidence_volume = 0.167      # 1/6 证据

numeric_score = 0.18*0.55 + 0.0*0.20 + 0.0*0.15 + 0.167*0.10
              = 0.099 + 0.0 + 0.0 + 0.017
              = 0.116

level = "low"  # < 0.48
```

## 置信度分级阈值
```python
if numeric_score >= 0.72:
    level = "high"       # 高置信度
elif numeric_score >= 0.48:
    level = "medium"     # 中等置信度
else:
    level = "low"        # 低置信度
```

### 阈值设计原理
- **0.72 (high)**: 对应检索分数 > 0.8、全部可追溯、覆盖三大维度、证据数量充足
- **0.48 (medium)**: 对应检索分数 0.5-0.7、部分可追溯、覆盖 1-2 个维度
- **< 0.48 (low)**: 检索分数 < 0.5 或证据数量极少或无可追溯来源

## 边界情况处理

### 1. 无证据场景
```python
if not evidence:
    return {"level": "low", "score": 0.0, "reason": "No evidence retrieved."}
```

### 2. 单条证据场景
```python
evidence = [{"score": 0.9, "metadata": {"source": "..."}, "tags": ["environment"]}]

avg_score = 0.9
traceable_ratio = 1.0
coverage_ratio = 0.333       # 只覆盖 1/3 维度
evidence_volume = 0.167      # 只有 1/6 理想数量

numeric_score = 0.9*0.55 + 1.0*0.20 + 0.333*0.15 + 0.167*0.10
              = 0.495 + 0.20 + 0.050 + 0.017
              = 0.762

level = "high"  # 单条高质量证据也可能达到 high
```

## 在流程中的位置
```
VerificationAgent (质量检查)
        ↓
ComplianceAgent (框架合规) + ConfidenceAgent (置信度评分)
        ↓
TraceAgent (汇总中间结果)
        ↓
ReportAgent (根据置信度调整报告语气)
```

## 设计原理

### 为什么检索质量权重最高 (55%)?
- **核心指标**: 检索分数直接反映证据与查询的相关性,是最重要的质量指标
- **embedding 模型依赖**: 当前使用 `all-MiniLM-L6-v2`,该模型的相似度分数具有较强的区分度

### 为什么来源可追溯性权重 20%?
- **ESG 报告特性**: ESG 披露需要明确引用来源 (例如 GRI 标准要求引用具体页码)
- **审计需求**: 外部审计师需要验证数据来源

### 为什么主题覆盖度权重 15%?
- **全面性要求**: 完整的 ESG 分析需要覆盖环境、社会、治理三个维度
- **避免偏见**: 如果只检索到环境证据,报告会缺少社会和治理内容

### 为什么证据数量权重最低 (10%)?
- **质量优于数量**: 1 条高质量证据优于 10 条低质量证据
- **避免冗余**: 过多相似证据不会显著提升分析质量

## 扩展建议

### 1. 动态权重调整
根据用户的查询类型调整权重:
```python
if "climate" in user_query:
    weights = {"avg_score": 0.60, "traceable": 0.25, "coverage": 0.10, "volume": 0.05}
else:
    weights = {"avg_score": 0.55, "traceable": 0.20, "coverage": 0.15, "volume": 0.10}
```

### 2. 考虑证据分布
不仅统计主题覆盖度,还评估每个主题的证据分布:
```python
tag_counts = Counter(tag for item in evidence for tag in item.get("tags", []))
balance_score = 1 - (max(tag_counts.values()) - min(tag_counts.values())) / sum(tag_counts.values())
# 如果三个维度的证据数量接近,balance_score 接近 1
```

### 3. 集成外部信誉评分
如果证据来源于知名机构 (例如 Bloomberg、CDP),提高权重:
```python
trusted_sources = {"bloomberg.com", "cdp.net", "sec.gov"}
trusted_ratio = sum(
    1 for item in evidence
    if any(src in item["metadata"].get("source", "") for src in trusted_sources)
) / len(evidence)
```

## 常见问题

**Q: 为什么我的证据检索分数都很高 (0.8+),但置信度还是 medium?**  
A: 可能原因:
1. 证据数量不足 (< 6 条)
2. 部分证据缺少 `source` 元数据
3. 只覆盖了 1-2 个 ESG 维度

**Q: 如果我想提高置信度评分,应该怎么做?**  
A: 优先顺序:
1. 增加高质量文档的索引 (提升 `avg_score`)
2. 确保所有文档都有完整的元数据 (提升 `traceable_ratio`)
3. 索引覆盖 ESG 三大维度的文档 (提升 `coverage_ratio`)
4. 增加索引库的文档数量 (提升 `evidence_volume`)

**Q: `reason` 字段为什么总是固定文本?**  
A: 当前实现为简化版本。可以改为动态生成:
```python
reason_parts = []
if avg_score >= 0.7:
    reason_parts.append("High retrieval quality")
if traceable_ratio >= 0.8:
    reason_parts.append("Strong source traceability")
if coverage_ratio >= 0.8:
    reason_parts.append("Comprehensive ESG coverage")
reason = "; ".join(reason_parts) or "Insufficient evidence quality"
```

---

**相关文档**:
- [VerificationAgent — 证据验证代理](./04_verification_agent.md)
- [ComplianceAgent — 合规评估代理](./05_compliance_agent.md)
- [ReportAgent — 报告生成代理](./08_report_agent.md)
