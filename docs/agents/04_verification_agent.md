# VerificationAgent — 证据验证代理

## 概述
`VerificationAgent` 是 ESG 分析流程的**第四个**代理,负责对证据进行**质量检查**和**可追溯性评估**,为每条证据生成验证备注,帮助分析师判断证据的可信度。

## 核心职责
1. **检测证据长度** — 标识过短的证据片段 (< 120 字符),提示需要查看完整上下文
2. **评估相似度分数** — 标识低置信度证据 (score < 0.2),提示需要交叉验证
3. **验证来源可追溯性** — 检查证据是否包含 `source`、`page` 等元数据
4. **识别数据类型** — 区分结构化数据 (JSON) 和叙述性文本 (PDF/DOCX)

## 输入参数
```python
def run(self, results: list[dict]) -> list[dict]:
```

**输入示例** (来自 `EvidenceFusionAgent` 的输出):
```python
[
    {
        "chunk_id": "uuid-1",
        "score": 0.856,
        "text": "Tesla's Scope 1 emissions decreased by 12% in 2024...",
        "metadata": {"source": "tesla_esg_2024.pdf", "source_name": "tesla_esg_2024.pdf", "page": 15},
        "tags": ["environment"],
        "excerpt": "Tesla's Scope 1 emissions decreased by 12%..."
    },
    {
        "chunk_id": "uuid-2",
        "score": 0.18,
        "text": "Revenue: $96.8B",
        "metadata": {"source": "financial_data.json", "source_type": "json"},
        "tags": ["general"],
        "excerpt": "Revenue: $96.8B"
    }
]
```

## 输出结构
在每条证据中新增 `verification_notes` 字段:
```python
[
    {
        "chunk_id": "uuid-1",
        "score": 0.856,
        "text": "Tesla's Scope 1 emissions decreased by 12% in 2024...",
        "metadata": {"source": "tesla_esg_2024.pdf", "source_name": "tesla_esg_2024.pdf", "page": 15},
        "tags": ["environment"],
        "excerpt": "Tesla's Scope 1 emissions decreased by 12%...",
        "verification_notes": "Traceable source: tesla_esg_2024.pdf. Page 15 available for citation."  # 新增字段
    },
    {
        "chunk_id": "uuid-2",
        "score": 0.18,
        "text": "Revenue: $96.8B",
        "metadata": {"source": "financial_data.json", "source_type": "json"},
        "tags": ["general"],
        "excerpt": "Revenue: $96.8B",
        "verification_notes": "Short excerpt; inspect adjacent source context. Similarity score is modest, so this evidence should be cross-checked. Traceable source: financial_data.json. Structured supplementary data; corroborate against narrative disclosures."  # 新增字段
    }
]
```

## 验证规则详解

### 1. 长度检查 (< 120 字符)
```python
if len(result["text"]) < 120:
    notes.append("Short excerpt; inspect adjacent source context.")
```

**目的**: 短文本可能缺乏完整语义,需要查看文档的上下文才能准确理解。

**示例**:
- `"Revenue: $96.8B"` → 过短,可能缺少时间信息、增长率等关键上下文
- `"Board consists of 11 directors"` → 过短,缺少独立董事比例、专业背景等细节

### 2. 相似度评估 (score < 0.2)
```python
if result["score"] < 0.2:
    notes.append("Similarity score is modest, so this evidence should be cross-checked.")
```

**目的**: 低相似度分数可能意味着:
- 检索算法的语义匹配不够精确
- 该证据与用户查询的相关性较弱
- 可能是噪音数据

**阈值选择**: 
- `score >= 0.8`: 高置信度,通常是直接匹配
- `0.2 <= score < 0.8`: 中等置信度,可能相关
- `score < 0.2`: 低置信度,建议交叉验证

### 3. 来源可追溯性检查
```python
if "source" not in metadata:
    notes.append("Missing source metadata.")
else:
    notes.append(f"Traceable source: {metadata.get('source_name', metadata['source'])}.")

if metadata.get("page") is not None:
    notes.append(f"Page {metadata['page']} available for citation.")
```

**目的**: ESG 报告需要引用具体出处,缺少来源信息的证据可信度较低。

**元数据字段**:
- `source`: 文件的完整路径 (例如 `/data/uploads/tesla_esg_2024.pdf`)
- `source_name`: 文件名 (例如 `tesla_esg_2024.pdf`)
- `page`: PDF 的页码 (例如 `15`)

### 4. 数据类型识别
```python
if metadata.get("source_type") == "json":
    notes.append("Structured supplementary data; corroborate against narrative disclosures.")
```

**目的**: 结构化数据 (JSON) 通常是量化指标,需要与叙述性披露 (PDF/DOCX) 交叉验证。

**示例**:
- JSON 数据: `{"scope_1_emissions": 120000, "unit": "tCO2e", "year": 2024}`
- 叙述性文本: "Tesla's Scope 1 emissions decreased by 12% in 2024, totaling 120,000 tCO2e due to increased renewable energy usage."

## 验证备注示例

### 高质量证据
```python
{
    "chunk_id": "uuid-1",
    "score": 0.892,
    "text": "Tesla's Board of Directors consists of 11 members, including 4 independent directors with expertise in sustainability...",
    "metadata": {"source_name": "tesla_governance_2024.pdf", "page": 8},
    "verification_notes": "Traceable source: tesla_governance_2024.pdf. Page 8 available for citation."
}
```

### 低质量证据
```python
{
    "chunk_id": "uuid-2",
    "score": 0.15,
    "text": "Revenue increased",
    "metadata": {"source_type": "json"},
    "verification_notes": "Short excerpt; inspect adjacent source context. Similarity score is modest, so this evidence should be cross-checked. Missing source metadata. Structured supplementary data; corroborate against narrative disclosures."
}
```

### 中等质量证据
```python
{
    "chunk_id": "uuid-3",
    "score": 0.45,
    "text": "The company employs 140,000 workers globally...",
    "metadata": {"source_name": "hr_report_2023.xlsx"},
    "verification_notes": "Traceable source: hr_report_2023.xlsx."
}
```

## 在流程中的位置
```
EvidenceFusionAgent (标注 ESG 标签)
        ↓
VerificationAgent (质量检查 + 生成验证备注)
        ↓
ComplianceAgent (框架合规评估) + ConfidenceAgent (置信度评分)
        ↓
ReportAgent (生成最终报告)
```

## 设计原理

### 为什么需要质量验证?
1. **提高报告可信度** — ESG 报告可能被外部审计,需要明确标识证据的局限性
2. **辅助人工审核** — 分析师可以优先检查带有警告标记的证据 (例如 "modest score")
3. **降低误报风险** — 低质量证据可能导致错误结论,验证备注可以提前预警

### 为什么不直接过滤低质量证据?
- **保留完整信息** — 即使低质量证据也可能包含有价值的信息 (例如某个关键数字)
- **由后续 agent 决策** — `ComplianceAgent` 和 `ConfidenceAgent` 会根据验证备注调整权重
- **透明度原则** — 让最终用户看到所有证据及其质量评估,而不是由系统单方面过滤

### 为什么阈值设置为 120 字符和 0.2 分?
- **120 字符**: 经验值,约等于 1-2 句英文 (大约 15-20 个单词)
- **0.2 分**: 基于 `all-MiniLM-L6-v2` 模型的实际测试,相似度 < 0.2 时通常表示语义差异较大

## 扩展建议

### 1. 增加时效性检查
```python
year_match = re.search(r"20\d{2}", metadata.get("source_name", ""))
if year_match:
    year = int(year_match.group())
    if 2026 - year > 3:  # 数据超过 3 年
        notes.append(f"Evidence from {year} may be outdated.")
```

### 2. 检测矛盾证据
```python
def detect_contradictions(results: list[dict]) -> None:
    for i, r1 in enumerate(results):
        for r2 in results[i+1:]:
            if has_numeric_contradiction(r1["text"], r2["text"]):
                r1["verification_notes"] += " Potential contradiction detected."
```

### 3. 集成外部验证服务
```python
def verify_source(url: str) -> bool:
    # 调用第三方 API 验证 URL 是否有效
    response = requests.head(url, timeout=5)
    return response.status_code == 200
```

## 常见问题

**Q: 为什么不使用机器学习模型来判断证据质量?**  
A: 当前的规则足够简单且可解释,机器学习模型会增加系统复杂度和推理延迟。如果有大量标注数据,可以训练一个二分类模型 (高质量/低质量)。

**Q: `verification_notes` 字段会被传递给 LLM 吗?**  
A: 会。在 `ReportAgent._chat_report()` 中,所有证据 (包括 `verification_notes`) 都会作为 prompt 的一部分传递给 LLM,帮助 LLM 评估证据可信度。

**Q: 如果所有证据的 score 都 < 0.2,会发生什么?**  
A: 所有证据都会被标记为 "modest score",`ConfidenceAgent` 会给出 "low" 置信度评级,`ReportAgent` 会在报告中明确提示证据不足。

---

**相关文档**:
- [EvidenceFusionAgent — 证据融合代理](./03_evidence_fusion_agent.md)
- [ComplianceAgent — 合规评估代理](./05_compliance_agent.md)
- [ConfidenceAgent — 置信度评分代理](./06_confidence_agent.md)
