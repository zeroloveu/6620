# ReportAgent（报告代理）说明文档

## 概述

**ReportAgent** 是流水线的最后一环，负责调用 **LLM**（DeepSeek / OpenAI）生成结构化的 ESG 分析报告，或在 LLM 不可用时使用**回退模板**生成基础报告。

## 核心职责

- 组装所有上游 agent 的输出，构造 LLM prompt
- 调用 LLM API 生成符合 JSON schema 的结构化报告
- 如果 LLM 不可用或出错，使用本地规则生成回退报告

## 输入参数

```python
def run(
    self,
    company_name: str,
    user_query: str,
    framework_focus: list[str],
    evidence: list[dict],
    compliance_alignment: dict,
    confidence_assessment: dict,
    agent_trace: list[dict],
) -> dict
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `company_name` | `str` | 公司名称 |
| `user_query` | `str` | 用户原始查询 |
| `framework_focus` | `list[str]` | 框架列表 |
| `evidence` | `list[dict]` | 已验证的证据 |
| `compliance_alignment` | `dict` | 框架对齐结果 |
| `confidence_assessment` | `dict` | 置信度评分 |
| `agent_trace` | `list[dict]` | 流水线追踪日志 |

## 处理流程

### 1. 组装 LLM Prompt

将所有证据格式化为文本块：
```
Source: GreenTech_ESG_Report.docx
Page: 3
Score: 0.8234
Tags: environment
Verification: Traceable source: GreenTech_ESG_Report.docx. Page 3 available for citation.
Excerpt:
GreenTech reduced Scope 1 and Scope 2 emissions by 18% compared to 2024...
```

构造完整 prompt：
```
Company: GreenTech
User request: 生成结构化 ESG 分析
Framework focus: GRI, SASB, TCFD, CSRD
Compliance alignment input: {GRI: {...}, SASB: {...}}
Confidence assessment input: {level: "high", score: 0.782}
Agent trace summary: [...]

You must produce a structured ESG analysis with Environment, Social, Governance,
compliance alignment, confidence assessment, and next steps.
Use only the evidence below and be explicit about gaps.

Evidence:
[所有证据...]
```

### 2. 调用 LLM Client

`LLMClient.structured_esg_report()` 会：
- 如果没有配置 `OPENAI_API_KEY` → 直接使用回退报告
- 如果配置了 API Key → 调用 `/chat/completions` API（流式传输）
- 如果 API 调用失败 → 捕获异常，使用回退报告

### 3. 合并输出

将 LLM 生成的报告与上游 agent 的结果合并：
```python
report["compliance_alignment"] = compliance_alignment
report["confidence_assessment"] = confidence_assessment
report["agent_trace"] = agent_trace
```

## 输出格式

完整的 ESG 分析报告 JSON：

```python
{
    "executive_summary": "...",
    "environment": {
        "title": "Environmental Performance",
        "summary": "...",
        "findings": ["Reduced GHG emissions by 18%", ...],
        "risks": ["Water scarcity risks in manufacturing regions", ...],
        "opportunities": ["Expand renewable energy to 50% by 2028", ...],
        "evidence": [
            {"source": "GreenTech_ESG_Report.docx", "page": 3, "score": 0.823, "excerpt": "...", "verification_notes": "..."},
            ...
        ]
    },
    "social": { ... },
    "governance": { ... },
    "compliance_alignment": {
        "GRI": {"coverage": "high", ...},
        ...
    },
    "confidence_assessment": {
        "level": "high",
        "score": 0.782,
        "reason": "..."
    },
    "next_steps": ["...", "..."],
    "agent_trace": [...]
}
```

## LLM vs 回退报告

### LLM 模式（需要 API Key）
- **优势**：生成自然流畅的叙述性文本，能理解复杂语境，提取深度洞察
- **劣势**：需要外部 API（可能有延迟、成本），依赖网络

### 回退模式（Fallback）
- **优势**：完全本地化，无需外部依赖，生成速度快（毫秒级）
- **劣势**：只是规则模板拼接，缺少深度分析

**回退报告逻辑**（`_fallback_report`）：
1. 取前 3 条证据生成 `executive_summary` 简介
2. 对每个维度（Environment/Social/Governance），使用 `_section_from_evidence()` 生成：
   - 如果有该标签的证据 → 展示证据摘要和基础风险/机会
   - 如果无证据 → 明确说明"无证据"，建议补充文档
3. 使用已计算好的 `compliance_alignment` 和 `confidence_assessment`

## 为什么需要 ReportAgent？

1. **格式统一** — 无论用 LLM 还是回退模式，输出格式都遵循相同 JSON schema
2. **降级优雅** — API 故障时不会完全失败，仍能生成基础报告
3. **分离关注点** — 其他 agent 专注逻辑（检索、验证、评分），ReportAgent 专注叙述生成

## 典型使用流程

```
User → Query → Pipeline → [6 agents run] → ReportAgent

ReportAgent:
  1. 尝试 LLM 生成（if API key exists）
     ├─ 成功 → 返回 LLM 报告
     └─ 失败 → 捕获异常，进入步骤 2
  2. 使用回退模板生成报告
  3. 附加 compliance_alignment, confidence_assessment, agent_trace
  4. 返回完整报告
```

## 前端展示

用户看到的报告包含：
- **Executive Summary** — 概览
- **Environment / Social / Governance** 三大区块 — 每块有 summary、findings、risks、opportunities、evidence
- **Compliance Grid** — 框架对齐卡片（GRI high、SASB moderate...）
- **Confidence Badge** — 置信度徽章（high 0.782）
- **Next Steps** — 后续建议
- **Agent Trace**（折叠）— 完整流水线日志
- **Raw Context**（折叠）— 原始检索结果
