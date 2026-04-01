# TraceAgent（追踪代理）说明文档

## 概述

**TraceAgent** 收集整个分析流水线中各个 agent 的**执行摘要**，生成一个结构化的追踪日志，用于审计和调试。

## 核心职责

- 汇总 `PlannerAgent`、`RetrievalAgent`、`EvidenceFusionAgent`、`ComplianceAgent`、`ConfidenceAgent` 的核心输出
- 统计证据的**标签分布**（environment / social / governance）
- 生成**可序列化的 JSON 追踪日志**

## 输入参数

```python
def run(self, plan: dict, evidence: list[dict], compliance: dict, confidence: dict) -> list[dict]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `plan` | `dict` | PlannerAgent 的输出（子查询列表、框架、关键词） |
| `evidence` | `list[dict]` | 经过 Verification 后的证据列表 |
| `compliance` | `dict` | ComplianceAgent 的输出（框架对齐结果） |
| `confidence` | `dict` | ConfidenceAgent 的输出（置信度评分） |

## 处理逻辑

1. **统计证据标签分布**
   ```python
   tag_counter = Counter(tag for item in evidence for tag in item.get("tags", []))
   ```
   **示例输出**：`{"environment": 5, "social": 3, "governance": 2, "general": 1}`

2. **组装追踪日志**
   生成一个包含 4 个条目的列表，每个条目代表一个 agent 的核心输出：
   - **planner** — 完整的规划结果
   - **retrieval_fusion** — 检索到的证据数量和标签分布
   - **compliance** — 框架对齐结果
   - **confidence** — 置信度评估结果

## 输出格式

```python
[
    {
        "agent": "planner",
        "output": {
            "objective": "生成 GreenTech 的 ESG 分析",
            "sub_queries": ["GreenTech environment...", "GreenTech social...", ...],
            "framework_focus": ["GRI", "SASB", "TCFD", "CSRD"],
            "keywords": ["esg", "performance"]
        }
    },
    {
        "agent": "retrieval_fusion",
        "retrieved_evidence": 6,
        "tag_breakdown": {
            "environment": 3,
            "social": 2,
            "governance": 1
        }
    },
    {
        "agent": "compliance",
        "output": {
            "GRI": {"coverage": "high", "matched_evidence_count": 6, ...},
            "SASB": {"coverage": "moderate", ...},
            ...
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

## 为什么需要 Trace？

### 1. 可审计性
ESG 报告需要**透明的证据链**。TraceAgent 记录了：
- 使用了哪些子查询
- 检索到了多少证据
- 证据如何分布在 ESG 三个维度
- 最终的置信度如何计算

### 2. 调试和优化
如果报告质量不佳，可以通过 trace 快速定位问题：
- `retrieved_evidence: 0` → 检索失败，检查知识库是否已索引
- `tag_breakdown: {"general": 6}` → 所有证据都是通用的，可能需要更精确的查询
- `confidence.level: "low"` → 证据质量差，需要补充文档

### 3. 前端展示
用户在报告中点开 **"Agent trace"** 折叠块，可以看到完整的 JSON 追踪日志，了解分析过程。

## 典型应用场景

**场景 1：报告质量低**
```
trace 显示: {"retrieved_evidence": 2, "tag_breakdown": {"general": 2}}
```
**诊断**：只检索到 2 条通用证据 → 知识库内容太少或查询不精确

**场景 2：某框架覆盖度低**
```
compliance.TCFD.coverage = "low"
tag_breakdown = {"social": 4, "governance": 2}
```
**诊断**：没有环境相关证据 → 需要上传气候披露文档

**场景 3：高质量报告**
```
retrieved_evidence: 8
tag_breakdown: {"environment": 3, "social": 3, "governance": 2}
confidence.score: 0.85
```
**诊断**：证据充足、分布均衡、高置信度 → 报告可以对外使用
