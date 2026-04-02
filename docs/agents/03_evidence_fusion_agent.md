# EvidenceFusionAgent — 证据融合代理

## 概述
`EvidenceFusionAgent` 是 ESG 分析流程的**第三个**代理,负责对检索结果进行**ESG 主题分类**和**摘要生成**,为后续的验证和合规评估提供结构化证据。

## 核心职责
1. **ESG 标签分类** — 根据文本内容自动标注 `environment`、`social`、`governance` 标签
2. **生成摘要** — 为每条证据生成简洁的摘要(最多 220 字符)
3. **保留完整上下文** — 不修改原始检索结果,仅增加新字段

## 输入参数
```python
def run(self, results: list[SearchResult]) -> list[dict]:
```

**输入示例**:
```python
[
    SearchResult(
        chunk_id="uuid-1",
        score=0.856,
        text="Tesla's Scope 1 emissions decreased by 12% in 2024 due to increased renewable energy usage...",
        metadata={"source": "tesla_esg_2024.pdf", "page": 15}
    ),
    SearchResult(
        chunk_id="uuid-2",
        score=0.792,
        text="The company employs 140,000 workers globally, with 35% women in management positions...",
        metadata={"source": "tesla_diversity_report.pdf", "page": 8}
    )
]
```

## 输出结构
```python
[
    {
        "chunk_id": "uuid-1",
        "score": 0.856,
        "text": "Tesla's Scope 1 emissions decreased by 12% in 2024...",
        "metadata": {"source": "tesla_esg_2024.pdf", "page": 15},
        "tags": ["environment"],  # 新增字段
        "excerpt": "Tesla's Scope 1 emissions decreased by 12% in 2024 due to increased renewable energy usage..."  # 新增字段
    },
    {
        "chunk_id": "uuid-2",
        "score": 0.792,
        "text": "The company employs 140,000 workers globally, with 35% women...",
        "metadata": {"source": "tesla_diversity_report.pdf", "page": 8},
        "tags": ["social"],  # 新增字段
        "excerpt": "The company employs 140,000 workers globally, with 35% women in management positions..."  # 新增字段
    }
]
```

## ESG 标签分类规则

### 标签规则表 (`TAG_RULES`)
```python
TAG_RULES = {
    "environment": {
        "climate", "emission", "emissions", "energy", "water", "waste",
        "renewable", "scope 1", "scope 2", "biodiversity"
    },
    "social": {
        "employee", "employees", "safety", "supplier", "suppliers",
        "community", "women", "diversity", "workforce", "training", "labor"
    },
    "governance": {
        "board", "governance", "ethics", "committee", "corruption",
        "compliance", "whistleblower", "oversight", "risk", "audit"
    }
}
```

### 分类逻辑
```python
text_lower = result.text.lower()
tags = [
    tag for tag, keywords in TAG_RULES.items()
    if any(keyword in text_lower for keyword in keywords)
]
if not tags:
    tags.append("general")  # 未匹配任何规则的证据标记为 "general"
```

### 示例分类结果
| 证据文本                                          | 匹配关键词           | 标签                           |
|--------------------------------------------------|---------------------|--------------------------------|
| "Scope 1 emissions decreased by 12%"             | `emissions`, `scope 1` | `["environment"]`              |
| "Board approved new ethics policy"               | `board`, `ethics`    | `["governance"]`               |
| "Employee safety training for 10,000 workers"    | `employee`, `safety`, `training` | `["social"]` |
| "Revenue increased by 20% in Q4"                 | (无匹配)             | `["general"]`                  |
| "Climate risk governance oversight by audit committee" | `climate`, `governance`, `oversight`, `audit` | `["environment", "governance"]` |

**注意**: 一条证据可能同时匹配多个标签 (例如"气候治理"同时属于 environment 和 governance)。

## 摘要生成规则

### 函数: `_clean_excerpt(text: str, limit: int = 220)`
1. **空白字符压缩** — 将连续的空格、换行、制表符压缩为单个空格
   ```python
   compact = re.sub(r"\s+", " ", text).strip()
   ```
2. **长度截断** — 如果文本超过 220 字符,截断并添加 `"..."`
   ```python
   if len(compact) > 220:
       return compact[:217] + "..."
   ```
3. **原样返回** — 如果文本 ≤ 220 字符,直接返回压缩后的文本

### 示例
| 原始文本 (带换行)                                  | 压缩后的摘要                                      |
|--------------------------------------------------|------------------------------------------------|
| `"Tesla's Scope 1\nemissions decreased\nby 12%"` | `"Tesla's Scope 1 emissions decreased by 12%"` |
| `"The board consists of 11 directors, including 4 independent members with expertise in sustainability, finance, and technology. The audit committee..."` | `"The board consists of 11 directors, including 4 independent members with expertise in sustainability, finance, and technology. The audit committee..."` (截断到 217 字符) |

## 在流程中的位置
```
PlannerAgent → RetrievalAgent (检索证据)
                    ↓
            EvidenceFusionAgent (标注标签 + 生成摘要)
                    ↓
            VerificationAgent (质量检查)
                    ↓
            ComplianceAgent + ConfidenceAgent
```

## 设计原理

### 为什么需要 ESG 标签?
1. **后续分组** — `ComplianceAgent` 需要按标签筛选证据 (例如 TCFD 框架只关注 `environment` 标签)
2. **报告结构** — `ReportAgent` 需要按 environment/social/governance 三个章节组织内容
3. **可视化分析** — `TraceAgent` 统计标签分布 (例如 `{"environment": 8, "social": 5, "governance": 3}`)

### 为什么需要摘要 (`excerpt`)?
- **UI 显示** — 前端展示检索结果时,完整的 `text` 可能有数千字符,`excerpt` 提供快速预览
- **降低 token 消耗** — `ReportAgent` 在构造 LLM prompt 时,使用 `excerpt` 代替完整 `text` 可以节省 token
- **提高可读性** — 压缩空白字符后的文本更易阅读

### 为什么未匹配的证据标记为 `"general"`?
- **避免空标签** — 确保每条证据至少有一个标签,方便后续逻辑处理
- **标识低质量证据** — `"general"` 标签通常意味着该证据与 ESG 主题关联较弱,`ComplianceAgent` 会过滤这些证据

## 扩展建议

### 1. 动态关键词库
当前的 `TAG_RULES` 是静态字典,可以改为从配置文件加载:
```python
import json

with open("esg_keywords.json") as f:
    TAG_RULES = json.load(f)
```

### 2. 支持多语言标签
为中文 ESG 文档添加中文关键词:
```python
TAG_RULES = {
    "environment": {
        "climate", "emission", "能源", "碳排放", "气候变化", "水资源"
    },
    "social": {
        "employee", "员工", "安全", "多样性", "供应链"
    },
    "governance": {
        "board", "董事会", "治理", "合规", "风险管理"
    }
}
```

### 3. 使用 NLP 分类模型
可以用预训练的文本分类模型替代关键词匹配:
```python
from transformers import pipeline

classifier = pipeline("text-classification", model="climatebert/environmental-claims")

def classify_esg(text: str) -> list[str]:
    result = classifier(text[:512])  # 截断到模型最大长度
    if result[0]["score"] > 0.7:
        return [result[0]["label"]]
    return ["general"]
```

### 4. 动态摘要长度
可以根据证据的重要性动态调整摘要长度:
```python
def _clean_excerpt(text: str, score: float) -> str:
    limit = 300 if score > 0.8 else 180  # 高分证据保留更多上下文
    # ...
```

## 常见问题

**Q: 如果一条证据同时匹配 `environment` 和 `social`,最终标签是什么?**  
A: 返回 `["environment", "social"]`,即该证据会同时被两个标签标注。`ComplianceAgent` 在筛选时会使用 `any(tag in tags for tag in ...)` 判断。

**Q: 为什么不直接在 `RetrievalAgent` 中生成标签?**  
A: 分离职责。`RetrievalAgent` 专注于向量检索,`EvidenceFusionAgent` 专注于语义理解。这样的架构便于单独测试和优化。

**Q: `excerpt` 字段在后续流程中是必需的吗?**  
A: 不是必需的。如果后续 agent 需要完整文本,可以使用 `text` 字段。但在实践中,`excerpt` 通常足够且更高效。

---

**相关文档**:
- [RetrievalAgent — 检索执行代理](./02_retrieval_agent.md)
- [VerificationAgent — 证据验证代理](./04_verification_agent.md)
- [ComplianceAgent — 合规评估代理](./05_compliance_agent.md)
