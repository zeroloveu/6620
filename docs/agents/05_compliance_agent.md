# ComplianceAgent — 合规评估代理

## 概述
`ComplianceAgent` 是 ESG 分析流程的**第五个**代理,负责评估检索到的证据与主流 ESG 披露框架 (GRI、SASB、TCFD、CSRD) 的**对齐程度**,生成框架覆盖率报告。

## 核心职责
1. **框架匹配** — 根据用户指定的框架,筛选相关证据
2. **覆盖率评估** — 统计每个框架的证据数量,评级为 `high`/`moderate`/`limited`/`low`
3. **主题覆盖分析** — 汇总证据涵盖的 ESG 主题 (environment/social/governance)
4. **生成示例备注** — 为每个框架提供前 3 条关键证据摘要

## 输入参数
```python
def run(
    self,
    framework_focus: list[str],  # 用户关注的框架 (例如 ["GRI", "TCFD"])
    evidence: list[dict]          # 经过 VerificationAgent 处理的证据列表
) -> dict:
```

**输入示例**:
```python
framework_focus = ["GRI", "TCFD"]
evidence = [
    {
        "chunk_id": "uuid-1",
        "score": 0.856,
        "text": "Tesla's Scope 1 emissions decreased by 12%...",
        "tags": ["environment"],
        "excerpt": "Tesla's Scope 1 emissions decreased by 12%..."
    },
    {
        "chunk_id": "uuid-2",
        "score": 0.792,
        "text": "The company employs 140,000 workers...",
        "tags": ["social"],
        "excerpt": "The company employs 140,000 workers..."
    },
    {
        "chunk_id": "uuid-3",
        "score": 0.745,
        "text": "Board consists of 11 directors...",
        "tags": ["governance"],
        "excerpt": "Board consists of 11 directors..."
    }
]
```

## 输出结构
```python
{
    "GRI": {
        "coverage": "high",
        "matched_evidence_count": 3,
        "covered_topics": ["environment", "governance", "social"],
        "notes": [
            "Tesla's Scope 1 emissions decreased by 12%...",
            "The company employs 140,000 workers...",
            "Board consists of 11 directors..."
        ]
    },
    "TCFD": {
        "coverage": "limited",
        "matched_evidence_count": 1,
        "covered_topics": ["environment"],
        "notes": [
            "Tesla's Scope 1 emissions decreased by 12%..."
        ]
    }
}
```

## 框架匹配规则

### 1. TCFD (Task Force on Climate-related Financial Disclosures)
```python
if framework == "TCFD" and "environment" in tags:
    evidence_hits.append(excerpt)
    covered_tags.update(tags)
```

**特点**: TCFD 专注于**气候相关披露**,只匹配带有 `environment` 标签的证据。

**适用场景**: 气候风险评估、碳排放披露、能源转型策略。

### 2. SASB (Sustainability Accounting Standards Board)
```python
elif framework == "SASB" and any(tag in tags for tag in ("environment", "social", "governance")):
    evidence_hits.append(excerpt)
    covered_tags.update(tags)
```

**特点**: SASB 覆盖 ESG 三大维度,但更侧重**财务重要性** (financially material),匹配所有 ESG 标签。

**适用场景**: 投资者关注的行业特定 ESG 指标 (例如科技行业的数据隐私、能源行业的碳排放)。

### 3. GRI (Global Reporting Initiative)
```python
elif framework in {"GRI", "CSRD"}:
    evidence_hits.append(excerpt)
    covered_tags.update(tags)
```

**特点**: GRI 是**最全面**的 ESG 披露框架,匹配所有证据 (包括 `general` 标签)。

**适用场景**: 多利益相关方报告、全面 ESG 披露、可持续发展报告。

### 4. CSRD (Corporate Sustainability Reporting Directive)
```python
elif framework in {"GRI", "CSRD"}:
    evidence_hits.append(excerpt)
    covered_tags.update(tags)
```

**特点**: 欧盟强制性披露要求,与 GRI 标准高度一致,匹配所有证据。

**适用场景**: 欧盟企业合规、双重重要性评估 (double materiality)。

## 覆盖率评级规则

### 评级阈值
```python
count = len(evidence_hits)
if count >= 4:
    coverage = "high"       # 4+ 条证据
elif count >= 2:
    coverage = "moderate"   # 2-3 条证据
elif count == 1:
    coverage = "limited"    # 1 条证据
else:
    coverage = "low"        # 0 条证据
```

### 示例评级结果
| 框架   | 证据数量 | 覆盖率评级  | 说明                          |
|--------|----------|------------|-------------------------------|
| GRI    | 12       | `high`     | 全面覆盖 ESG 三大维度         |
| TCFD   | 5        | `high`     | 环境维度证据充足              |
| SASB   | 2        | `moderate` | 部分 ESG 主题有证据支持       |
| CSRD   | 1        | `limited`  | 仅有一条相关证据              |
| CDP    | 0        | `low`      | 未检索到相关证据 (未配置规则) |

## 输出字段详解

### 1. `coverage` (覆盖率评级)
- `"high"`: 证据充足,可以支撑该框架的披露要求
- `"moderate"`: 证据一般,部分主题有覆盖
- `"limited"`: 证据稀少,仅有零星覆盖
- `"low"`: 无相关证据

### 2. `matched_evidence_count` (匹配证据数量)
- 用于量化评估,便于后续分析师判断是否需要补充更多文档

### 3. `covered_topics` (覆盖主题)
- 列出该框架下匹配到的所有 ESG 主题标签
- 排除 `"general"` 标签 (因为 general 通常与 ESG 无关)
- 按字母顺序排序

### 4. `notes` (示例证据)
- 提供前 3 条证据的摘要 (`excerpt` 字段)
- 用于快速预览关键证据,辅助报告生成

## 在流程中的位置
```
VerificationAgent (质量检查)
        ↓
ComplianceAgent (框架合规评估) + ConfidenceAgent (置信度评分)
        ↓
TraceAgent (汇总中间结果)
        ↓
ReportAgent (生成最终报告)
```

## 设计原理

### 为什么不同框架有不同的匹配规则?
- **TCFD**: 气候专项框架,只关注环境维度,避免社会/治理维度的噪音数据
- **SASB**: 行业特定框架,覆盖 ESG 三大维度,但实际应用中应根据行业调整权重 (当前简化为全匹配)
- **GRI/CSRD**: 通用框架,接受所有证据,确保报告全面性

### 为什么 `notes` 只保留前 3 条证据?
- **控制 token 消耗** — 在 `ReportAgent` 的 prompt 中,`compliance_alignment` 会被序列化为文本,过多证据会超出 LLM 上下文窗口
- **代表性采样** — 前 3 条证据通常是相似度最高的,足以代表该框架的覆盖情况
- **提高可读性** — 分析师浏览报告时,3 条示例比 10+ 条更易理解

### 为什么 `covered_topics` 排除 `"general"` 标签?
- `"general"` 标签通常是未匹配任何 ESG 关键词的证据 (例如财务数据、公司历史),这些内容与 ESG 框架关联较弱

## 扩展建议

### 1. 细化 SASB 行业规则
SASB 有 77 个行业分类,每个行业关注的 ESG 主题不同:
```python
SASB_INDUSTRY_RULES = {
    "Technology & Communications": {
        "key_topics": ["data privacy", "cybersecurity", "energy management"],
        "required_tags": ["social", "governance"]
    },
    "Energy": {
        "key_topics": ["GHG emissions", "water management", "waste"],
        "required_tags": ["environment"]
    }
}

def match_sasb(industry: str, evidence: dict) -> bool:
    rules = SASB_INDUSTRY_RULES.get(industry, {})
    required_tags = rules.get("required_tags", [])
    return any(tag in evidence["tags"] for tag in required_tags)
```

### 2. 增加框架特定关键词
除了依赖 `tags`,还可以检查特定术语:
```python
TCFD_KEYWORDS = {"climate risk", "scenario analysis", "transition plan", "physical risk"}

def match_tcfd(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in TCFD_KEYWORDS)
```

### 3. 动态调整覆盖率阈值
不同框架对证据数量的要求不同:
```python
COVERAGE_THRESHOLDS = {
    "TCFD": {"high": 3, "moderate": 2, "limited": 1},  # TCFD 要求较少证据
    "GRI": {"high": 6, "moderate": 3, "limited": 1}    # GRI 要求更多证据
}
```

### 4. 支持自定义框架
允许用户定义新框架:
```python
custom_frameworks = {
    "CDP": {
        "match_rule": lambda tags: "environment" in tags,
        "thresholds": {"high": 4, "moderate": 2}
    }
}
```

## 常见问题

**Q: 如果用户未指定 `framework_focus`,会使用哪些框架?**  
A: 默认使用 `["GRI", "SASB", "TCFD", "CSRD"]` (在 `_normalize_frameworks` 函数中定义)。

**Q: 为什么检索到 10 条环境证据,但 TCFD 的 `coverage` 还是 `high` 而不是 `very high`?**  
A: 当前只有 4 个评级档位 (`high`/`moderate`/`limited`/`low`),`high` 是最高级别。可以增加 `very high` 档位 (例如 `count >= 8`)。

**Q: 如何判断某个框架的覆盖率是否"足够好"?**  
A: 通用建议:
- `high`: 可以直接用于对外披露
- `moderate`: 需要补充部分内容
- `limited`: 需要大幅补充证据
- `low`: 该框架尚未被文档覆盖,需要索引更多资料

---

**相关文档**:
- [VerificationAgent — 证据验证代理](./04_verification_agent.md)
- [ConfidenceAgent — 置信度评分代理](./06_confidence_agent.md)
- [ReportAgent — 报告生成代理](./08_report_agent.md)
