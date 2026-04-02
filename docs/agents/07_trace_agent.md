# TraceAgent — 追踪记录代理

## 概述
`TraceAgent` 是 ESG 分析流程的**第七个**代理,负责汇总前面所有 agent 的中间输出,生成**可追溯的执行日志**,用于调试、审计和透明度展示。

## 核心职责
1. **记录规划阶段** — 保存 `PlannerAgent` 的输出 (子查询、关键词、框架)
2. **统计检索结果** — 记录检索到的证据数量和 ESG 标签分布
3. **汇总合规与置信度** — 记录 `ComplianceAgent` 和 `ConfidenceAgent` 的评估结果
4. **生成结构化日志** — 输出可序列化的 JSON 格式,便于存储和分析

## 输入参数
```python
def run(
    self,
    plan: dict,              # PlannerAgent 的输出
    evidence: list[dict],    # 经过融合和验证的证据列表
    compliance: dict,        # ComplianceAgent 的输出
    confidence: dict         # ConfidenceAgent 的输出
) -> list[dict]:
```

**输入示例**:
```python
plan = {
    "objective": "分析 Tesla 的碳排放管理",
    "sub_queries": ["Tesla environment climate emissions...", ...],
    "framework_focus": ["GRI", "TCFD"],
    "keywords": ["carbon", "emissions", "management"]
}

evidence = [
    {"chunk_id": "uuid-1", "tags": ["environment"], ...},
    {"chunk_id": "uuid-2", "tags": ["environment"], ...},
    {"chunk_id": "uuid-3", "tags": ["social"], ...},
    {"chunk_id": "uuid-4", "tags": ["governance"], ...},
]

compliance = {
    "GRI": {"coverage": "high", "matched_evidence_count": 4, ...},
    "TCFD": {"coverage": "moderate", "matched_evidence_count": 2, ...}
}

confidence = {
    "level": "high",
    "score": 0.782,
    "reason": "Blend of retrieval quality, traceability, topic coverage, and evidence volume."
}
```

## 输出结构
```python
[
    {
        "agent": "planner",
        "output": {
            "objective": "分析 Tesla 的碳排放管理",
            "sub_queries": ["Tesla environment climate emissions...", ...],
            "framework_focus": ["GRI", "TCFD"],
            "keywords": ["carbon", "emissions", "management"]
        }
    },
    {
        "agent": "retrieval_fusion",
        "retrieved_evidence": 4,
        "tag_breakdown": {
            "environment": 2,
            "social": 1,
            "governance": 1
        }
    },
    {
        "agent": "compliance",
        "output": {
            "GRI": {"coverage": "high", "matched_evidence_count": 4, ...},
            "TCFD": {"coverage": "moderate", "matched_evidence_count": 2, ...}
        }
    },
    {
        "agent": "confidence",
        "output": {
            "level": "high",
            "score": 0.782,
            "reason": "Blend of retrieval quality, traceability, topic coverage, and evidence volume."
        }
    }
]
```

## 核心逻辑

### 1. 记录规划阶段
```python
{"agent": "planner", "output": plan}
```

**目的**: 保存用户的原始查询和 `PlannerAgent` 生成的子查询,便于后续回溯分析为何检索到某些证据。

**用途**:
- 调试检索质量 — 如果检索结果不理想,检查子查询是否合理
- 审计报告 — 向外部审计师展示分析的起点和逻辑

### 2. 统计检索结果和标签分布
```python
from collections import Counter

tag_counter = Counter(tag for item in evidence for tag in item.get("tags", []))

{
    "agent": "retrieval_fusion",
    "retrieved_evidence": len(evidence),
    "tag_breakdown": dict(tag_counter)
}
```

**标签分布示例**:
```python
{
    "agent": "retrieval_fusion",
    "retrieved_evidence": 8,
    "tag_breakdown": {
        "environment": 4,
        "social": 2,
        "governance": 1,
        "general": 1
    }
}
```

**目的**: 快速了解检索到的证据在 ESG 三大维度上的分布,识别可能的偏差 (例如只检索到环境证据,缺少社会和治理)。

### 3. 汇总合规与置信度
```python
{"agent": "compliance", "output": compliance}
{"agent": "confidence", "output": confidence}
```

**目的**: 将 `ComplianceAgent` 和 `ConfidenceAgent` 的评估结果集中记录,便于 `ReportAgent` 直接引用。

## 在流程中的位置
```
PlannerAgent → RetrievalAgent → EvidenceFusionAgent → VerificationAgent
        ↓                                                      ↓
    plan                                                   evidence
        ↓                                                      ↓
ComplianceAgent + ConfidenceAgent
        ↓                    ↓
    compliance          confidence
        ↓                    ↓
TraceAgent (汇总所有中间结果)
        ↓
agent_trace (传递给 ReportAgent)
        ↓
ReportAgent (生成最终报告,附带 agent_trace 作为附录)
```

## 使用场景

### 1. 调试检索质量
**问题**: 用户报告"检索不到相关证据"

**调试步骤**:
1. 查看 `agent_trace[0]["output"]["sub_queries"]` — 检查子查询是否合理
2. 查看 `agent_trace[1]["retrieved_evidence"]` — 检查是否真的没有检索到证据
3. 查看 `agent_trace[1]["tag_breakdown"]` — 检查标签分布是否严重倾斜

### 2. 优化框架合规评估
**问题**: TCFD 框架的覆盖率总是 `low`

**分析**:
1. 查看 `agent_trace[1]["tag_breakdown"]["environment"]` — 检查环境标签的证据数量
2. 查看 `agent_trace[2]["output"]["TCFD"]["matched_evidence_count"]` — 检查 TCFD 匹配到的证据数量
3. **结论**: 如果 `environment` 标签的证据数量充足 (例如 10 条),但 TCFD 匹配数量很少 (例如 1 条),说明 `ComplianceAgent` 的匹配规则过于严格

### 3. 向用户展示分析过程
**场景**: 用户希望了解"为什么置信度评分是 0.65?"

**展示**:
```json
{
  "agent": "confidence",
  "output": {
    "level": "medium",
    "score": 0.65,
    "reason": "Blend of retrieval quality, traceability, topic coverage, and evidence volume."
  }
}
```

进一步解释:
- 查看 `agent_trace[1]["retrieved_evidence"]` — 证据数量 (例如 4 条)
- 查看 `agent_trace[1]["tag_breakdown"]` — 覆盖的 ESG 维度 (例如只有 environment 和 social,缺少 governance)
- **结论**: 置信度评分较低是因为证据数量不足 (4 < 6) 且缺少治理维度证据

### 4. 生成审计报告
**场景**: 外部审计师要求提供"ESG 分析的完整执行日志"

**输出**: 将 `agent_trace` 序列化为 JSON 文件,包含:
- 原始查询和子查询
- 检索到的证据数量和来源
- 每个框架的覆盖率评估
- 置信度评分的计算依据

## 设计原理

### 为什么不直接在 `ReportAgent` 中引用其他 agent 的输出?
- **解耦架构** — `TraceAgent` 作为中间层,将多个 agent 的输出标准化为统一格式
- **简化接口** — `ReportAgent` 只需要接收 `agent_trace` 一个参数,而不是 `plan`, `evidence`, `compliance`, `confidence` 四个参数
- **便于扩展** — 如果未来增加新的 agent (例如 `RiskAgent`),只需在 `TraceAgent` 中添加一个条目,不影响 `ReportAgent`

### 为什么使用 `Counter` 统计标签分布?
- **高效** — `Counter` 是 Python 标准库中专门用于计数的数据结构,性能优于手动循环
- **可读** — `Counter` 的输出 `{"environment": 4, "social": 2}` 比列表 `["environment", "environment", "environment", "environment", "social", "social"]` 更易理解

### 为什么 `tag_breakdown` 不排除 `"general"` 标签?
- **完整性** — 保留所有标签,方便后续分析 (例如计算 `general` 标签的比例,判断检索质量)
- **一致性** — 与 `EvidenceFusionAgent` 的输出保持一致 (不过滤标签)

## 扩展建议

### 1. 记录执行时间
```python
import time

start = time.time()
# ... 执行 agent ...
elapsed = time.time() - start

{
    "agent": "retrieval_fusion",
    "retrieved_evidence": len(evidence),
    "tag_breakdown": dict(tag_counter),
    "elapsed_seconds": round(elapsed, 2)
}
```

### 2. 记录证据来源分布
```python
from collections import Counter

source_counter = Counter(
    item["metadata"].get("source_name", "unknown")
    for item in evidence
)

{
    "agent": "retrieval_fusion",
    "retrieved_evidence": len(evidence),
    "tag_breakdown": dict(tag_counter),
    "source_distribution": dict(source_counter)
}
```

**输出示例**:
```json
{
  "agent": "retrieval_fusion",
  "source_distribution": {
    "tesla_esg_2024.pdf": 5,
    "tesla_diversity_report.pdf": 2,
    "financial_data.json": 1
  }
}
```

### 3. 记录查询扩展结果
```python
from esg_rag.query_expansion import expand_query

expanded_queries = []
for q in plan["sub_queries"]:
    expanded_queries.append({
        "original": q,
        "variants": expand_query(q, max_variants=2)
    })

{
    "agent": "planner",
    "output": plan,
    "query_expansion": expanded_queries
}
```

### 4. 记录错误和警告
```python
warnings = []
if len(evidence) < 3:
    warnings.append("Evidence count is below recommended threshold (6)")
if confidence["level"] == "low":
    warnings.append("Confidence level is low; consider indexing more documents")

{
    "agent": "retrieval_fusion",
    "retrieved_evidence": len(evidence),
    "tag_breakdown": dict(tag_counter),
    "warnings": warnings
}
```

## 常见问题

**Q: `agent_trace` 会被传递给 LLM 吗?**  
A: 会。在 `ReportAgent._chat_report()` 中,`agent_trace` 会被序列化为文本,作为 prompt 的一部分传递给 LLM。LLM 可以参考这些信息生成更详细的分析报告。

**Q: 如果我不想在最终报告中显示 `agent_trace`,如何隐藏?**  
A: 在前端或 API 返回时过滤掉 `agent_trace` 字段:
```python
report = pipeline.analyze(...)
del report["agent_trace"]  # 移除追踪日志
return report
```

**Q: `tag_breakdown` 中的数字加起来可能超过 `retrieved_evidence`,为什么?**  
A: 因为一条证据可能同时有多个标签 (例如 `["environment", "governance"]`),所以 `tag_breakdown` 统计的是标签的总出现次数,而不是证据数量。

**示例**:
```python
evidence = [
    {"tags": ["environment", "governance"]},
    {"tags": ["social"]},
]

retrieved_evidence = 2
tag_breakdown = {"environment": 1, "governance": 1, "social": 1}  # 总和为 3
```

---

**相关文档**:
- [PlannerAgent — 查询规划代理](./01_planner_agent.md)
- [ComplianceAgent — 合规评估代理](./05_compliance_agent.md)
- [ConfidenceAgent — 置信度评分代理](./06_confidence_agent.md)
- [ReportAgent — 报告生成代理](./08_report_agent.md)
