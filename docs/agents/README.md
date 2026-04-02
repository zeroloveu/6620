# ESG 分析系统 — Agents 完整文档

## 概述
本项目采用**多 Agent 流水线架构**,将 ESG 分析任务拆解为 8 个专项代理 (Agent),每个代理负责一个明确的子任务。所有 agent 按顺序执行,前一个 agent 的输出作为后一个 agent 的输入,最终生成结构化的 ESG 分析报告。

## 流程图
```
用户查询 → PlannerAgent (规划)
            ↓
        RetrievalAgent (检索)
            ↓
        EvidenceFusionAgent (融合)
            ↓
        VerificationAgent (验证)
            ↓
        ComplianceAgent (合规) + ConfidenceAgent (置信度)
            ↓
        TraceAgent (追踪)
            ↓
        ReportAgent (报告) + LLMClient (LLM 调用)
            ↓
        最终报告 (JSON)
```

## 8 个核心 Agent

### 1. PlannerAgent — 查询规划代理
**职责**: 将用户的自然语言查询分解为 5 个结构化的子查询,覆盖 ESG 三大维度 + 框架合规 + 争议风险。

**输入**:
- `company_name`: 公司名称
- `user_query`: 用户查询 (例如"分析碳排放管理")
- `framework_focus`: ESG 框架 (例如 ["GRI", "TCFD"])

**输出**:
```python
{
    "objective": "原始用户查询",
    "sub_queries": [
        "公司名 environment climate emissions energy water targets 关键词",
        "公司名 social workforce safety diversity supply chain community 关键词",
        "公司名 governance board risk ethics compliance oversight 关键词",
        "公司名 GRI TCFD disclosure alignment material topics 关键词",
        "公司名 controversies media sentiment ESG strengths weaknesses 关键词"
    ],
    "framework_focus": ["GRI", "TCFD"],
    "keywords": ["carbon", "emissions", "management"]
}
```

**核心逻辑**:
- 提取用户查询中的关键词 (去除停用词)
- 为每个 ESG 维度生成专项子查询,注入领域术语
- 标准化框架名称为大写

**详细文档**: [01_planner_agent.md](./01_planner_agent.md)

---

### 2. RetrievalAgent — 检索执行代理
**职责**: 对 `PlannerAgent` 生成的子查询执行向量检索,并通过 **ESG 同义词扩展** 提升召回质量。

**输入**:
- `queries`: 子查询列表 (来自 `PlannerAgent`)
- `retriever`: 检索器实例 (Retriever 或 _KBRetriever)
- `top_k`: 最终返回的证据数量 (例如 20)

**输出**:
```python
[
    SearchResult(
        chunk_id="uuid-1",
        score=0.856,
        text="Tesla's Scope 1 emissions decreased by 12%...",
        metadata={"source": "tesla_esg_2024.pdf", "page": 15}
    ),
    ...
]
```

**核心逻辑**:
1. 使用 `expand_query()` 为每个子查询生成同义词变体 (例如 `"carbon"` → `["GHG", "carbon dioxide"]`)
2. 对所有查询 (原始 + 变体) 执行向量检索
3. 按 `chunk_id` 去重,保留最高分的检索结果
4. 按 `score` 降序排列,返回前 `top_k` 个

**详细文档**: [02_retrieval_agent.md](./02_retrieval_agent.md)

---

### 3. EvidenceFusionAgent — 证据融合代理
**职责**: 为检索结果标注 **ESG 标签** (environment/social/governance) 和生成摘要。

**输入**: `list[SearchResult]` (来自 `RetrievalAgent`)

**输出**:
```python
[
    {
        "chunk_id": "uuid-1",
        "score": 0.856,
        "text": "Tesla's Scope 1 emissions decreased by 12%...",
        "metadata": {...},
        "tags": ["environment"],  # 新增字段
        "excerpt": "Tesla's Scope 1 emissions decreased by 12%..."  # 新增字段
    },
    ...
]
```

**核心逻辑**:
- 根据 `TAG_RULES` 字典 (包含 ESG 关键词映射) 自动标注标签
- 压缩文本空白字符,生成简洁摘要 (最多 220 字符)
- 未匹配任何规则的证据标记为 `"general"`

**详细文档**: [03_evidence_fusion_agent.md](./03_evidence_fusion_agent.md)

---

### 4. VerificationAgent — 证据验证代理
**职责**: 对证据进行**质量检查**和**可追溯性评估**,生成验证备注。

**输入**: `list[dict]` (来自 `EvidenceFusionAgent`)

**输出**: 在每条证据中新增 `verification_notes` 字段:
```python
{
    ...,
    "verification_notes": "Traceable source: tesla_esg_2024.pdf. Page 15 available for citation."
}
```

**核心逻辑**:
- 检测过短证据 (< 120 字符),标记需要查看上下文
- 评估低置信度证据 (score < 0.2),标记需要交叉验证
- 验证来源可追溯性 (是否包含 `source`, `page` 元数据)
- 识别数据类型 (JSON 结构化数据 vs PDF/DOCX 叙述性文本)

**详细文档**: [04_verification_agent.md](./04_verification_agent.md)

---

### 5. ComplianceAgent — 合规评估代理
**职责**: 评估检索到的证据与主流 ESG 披露框架 (GRI、SASB、TCFD、CSRD) 的对齐程度。

**输入**:
- `framework_focus`: 用户关注的框架
- `evidence`: 经过验证的证据列表

**输出**:
```python
{
    "GRI": {
        "coverage": "high",  # high/moderate/limited/low
        "matched_evidence_count": 8,
        "covered_topics": ["environment", "social", "governance"],
        "notes": ["证据摘要 1", "证据摘要 2", "证据摘要 3"]
    },
    "TCFD": {
        "coverage": "moderate",
        "matched_evidence_count": 3,
        "covered_topics": ["environment"],
        "notes": [...]
    }
}
```

**核心逻辑**:
- **TCFD**: 只匹配带有 `environment` 标签的证据 (气候专项框架)
- **SASB**: 匹配所有 ESG 标签 (行业特定框架)
- **GRI/CSRD**: 匹配所有证据 (通用全面框架)
- 根据证据数量评级: 4+ 条为 `high`,2-3 条为 `moderate`,1 条为 `limited`,0 条为 `low`

**详细文档**: [05_compliance_agent.md](./05_compliance_agent.md)

---

### 6. ConfidenceAgent — 置信度评分代理
**职责**: 综合评估检索证据的质量和可信度,生成 0-1 之间的数值评分。

**输入**: `evidence` (经过验证的证据列表)

**输出**:
```python
{
    "level": "high",  # high/medium/low
    "score": 0.782,   # 数值评分 (0-1)
    "reason": "Blend of retrieval quality, traceability, topic coverage, and evidence volume."
}
```

**核心逻辑**: 多维度加权评分
- **检索质量** (55%): 平均相似度分数
- **来源可追溯性** (20%): 包含 `source` 元数据的证据比例
- **主题覆盖度** (15%): 覆盖的 ESG 维度数量 (理想值 3)
- **证据数量** (10%): 证据数量相对于理想值 (6 条) 的比例

**评级阈值**:
- `score >= 0.72` → `high`
- `0.48 <= score < 0.72` → `medium`
- `score < 0.48` → `low`

**详细文档**: [06_confidence_agent.md](./06_confidence_agent.md)

---

### 7. TraceAgent — 追踪记录代理
**职责**: 汇总前面所有 agent 的中间输出,生成可追溯的执行日志。

**输入**:
- `plan`: PlannerAgent 的输出
- `evidence`: 经过融合和验证的证据列表
- `compliance`: ComplianceAgent 的输出
- `confidence`: ConfidenceAgent 的输出

**输出**:
```python
[
    {"agent": "planner", "output": {...}},
    {
        "agent": "retrieval_fusion",
        "retrieved_evidence": 8,
        "tag_breakdown": {"environment": 4, "social": 2, "governance": 1, "general": 1}
    },
    {"agent": "compliance", "output": {...}},
    {"agent": "confidence", "output": {...}}
]
```

**核心逻辑**:
- 记录规划阶段 (子查询、关键词、框架)
- 统计检索结果 (证据数量、标签分布)
- 汇总合规与置信度评估结果

**详细文档**: [07_trace_agent.md](./07_trace_agent.md)

---

### 8. ReportAgent — 报告生成代理
**职责**: 生成结构化的 ESG 分析报告,支持 **LLM 模式** 和 **模板模式** 两种工作方式。

**输入**:
- `company_name`: 公司名称
- `user_query`: 用户查询
- `framework_focus`: ESG 框架
- `evidence`: 经过验证的证据列表
- `compliance_alignment`: ComplianceAgent 的输出
- `confidence_assessment`: ConfidenceAgent 的输出
- `agent_trace`: TraceAgent 的输出

**输出**:
```python
{
    "executive_summary": "...",
    "environment": {
        "title": "Environment",
        "summary": "...",
        "findings": ["...", "...", ...],
        "risks": ["...", "...", ...],
        "opportunities": ["...", "...", ...],
        "evidence": [{"source": "...", "page": 15, "score": 0.856, "excerpt": "...", "verification_notes": "..."}]
    },
    "social": {...},
    "governance": {...},
    "compliance_alignment": {...},
    "confidence_assessment": {...},
    "next_steps": ["...", "...", ...],
    "agent_trace": [...]
}
```

**核心逻辑**:
1. **LLM 模式**: 构造 prompt,调用外部 LLM (例如 DeepSeek、OpenAI),解析 JSON 响应
2. **模板模式**: LLM 失败时,使用规则生成标准化报告
3. **流式响应**: 使用 SSE (Server-Sent Events) 处理长时间的 LLM 响应

**详细文档**: [08_report_agent.md](./08_report_agent.md)

---

### 9. LLMClient — 大语言模型客户端
**职责**: 封装与外部 LLM API 的交互逻辑,支持 OpenAI 兼容 API。

**核心方法**:
- `structured_esg_report()`: 主入口,调用 LLM 或降级到模板
- `_chat_report()`: 发送 HTTP 请求,处理流式响应
- `_extract_json()`: 从 LLM 响应中提取 JSON (支持 markdown 代码块)
- `_fallback_report()`: 模板模式报告生成

**核心配置**:
- `openai_api_key`: API Key (例如 DeepSeek 的 `sk-xxx`)
- `openai_base_url`: API 基础 URL (例如 `https://api.deepseek.com`)
- `openai_chat_model`: 模型名称 (例如 `deepseek-reasoner`)
- 超时设置: `read=600s` (适配 reasoning 模型的长思考时间)

**详细文档**: [09_llm_client.md](./09_llm_client.md)

---

## Agent 之间的数据流

### 1. 查询规划阶段
```
用户查询 → PlannerAgent
    输出: {
        "sub_queries": [5 个子查询],
        "keywords": [关键词列表],
        "framework_focus": [框架列表]
    }
```

### 2. 证据检索阶段
```
sub_queries → RetrievalAgent
    1. 查询扩展 (同义词变体)
    2. 向量检索 (多轮)
    3. 去重排序
    输出: list[SearchResult]
```

### 3. 证据增强阶段
```
SearchResult → EvidenceFusionAgent → VerificationAgent
    1. 标注 ESG 标签 (environment/social/governance)
    2. 生成摘要 (excerpt)
    3. 质量检查 (长度、相似度、来源)
    4. 生成验证备注 (verification_notes)
    输出: list[dict] (包含 tags, excerpt, verification_notes)
```

### 4. 评估阶段
```
evidence → ComplianceAgent + ConfidenceAgent
    ComplianceAgent: 评估框架对齐程度
    ConfidenceAgent: 计算置信度评分
    输出: compliance_alignment + confidence_assessment
```

### 5. 追踪与报告阶段
```
所有中间结果 → TraceAgent → ReportAgent
    TraceAgent: 汇总执行日志
    ReportAgent: 生成最终报告 (LLM 或模板)
    输出: 结构化 JSON 报告
```

## 关键设计原则

### 1. 单一职责原则 (Single Responsibility)
每个 agent 只负责一个明确的子任务,便于测试、调试和优化。

### 2. 流水线架构 (Pipeline)
Agent 按顺序执行,前一个 agent 的输出作为后一个 agent 的输入,形成清晰的数据流。

### 3. 解耦与可扩展性
- 增加新 agent (例如 `RiskAgent`) 只需在流水线中插入新节点
- 修改某个 agent 的逻辑不影响其他 agent

### 4. 证据驱动 (Evidence-Driven)
所有分析都基于检索到的证据,不依赖 LLM 的"知识库",确保报告的可追溯性和可信度。

### 5. 降级策略 (Graceful Degradation)
LLM 调用失败时,自动切换到模板模式,确保系统稳定性。

### 6. 透明度 (Transparency)
通过 `TraceAgent` 和 `verification_notes` 提供完整的执行日志,便于审计和调试。

## 性能优化建议

### 1. 并行化
- `RetrievalAgent` 的多轮检索可以并行执行
- `ComplianceAgent` 和 `ConfidenceAgent` 可以并行执行

### 2. 缓存
- 缓存 embedding 向量 (避免重复调用 embedding 模型)
- 缓存 LLM 响应 (对于相同的查询和证据)

### 3. 批量处理
- 将多个查询的 embedding 请求合并为一个 batch

### 4. 索引优化
- 使用更强的 embedding 模型 (例如 `BAAI/bge-base-en-v1.5`)
- 增加 reranking 层 (例如 Cross-Encoder)

## 常见问题

**Q: 为什么要拆分成 8 个 agent,而不是一个大模型端到端生成?**  
A: 
1. **可控性** — 每个 agent 的逻辑是确定性的,便于调试和优化
2. **透明度** — 可以查看每个阶段的中间结果,理解分析过程
3. **成本** — 减少对 LLM 的依赖,降低 API 调用成本
4. **准确性** — 证据驱动的分析比纯 LLM 生成更准确和可靠

**Q: 如果 LLM 总是失败,是否可以完全禁用 LLM?**  
A: 可以。将 `.env` 中的 `OPENAI_API_KEY` 留空,系统会自动使用模板模式。

**Q: 如何评估 agent 流水线的质量?**  
A: 
1. **单元测试** — 为每个 agent 编写单元测试,验证输入输出
2. **集成测试** — 使用真实的 ESG 报告作为测试数据,对比生成的报告与专家标注
3. **A/B 测试** — 对比不同配置 (例如不同的 embedding 模型、reranking 策略) 的召回率和精度

**Q: 如何添加新的 ESG 框架 (例如 CDP)?**  
A: 修改 `ComplianceAgent.run()`,增加新的匹配规则:
```python
elif framework == "CDP":
    if any(kw in text_lower for kw in ["climate", "water", "forest"]):
        evidence_hits.append(excerpt)
```

---

## 相关文档索引

### Agent 详细文档
- [01_planner_agent.md](./01_planner_agent.md) — 查询规划代理
- [02_retrieval_agent.md](./02_retrieval_agent.md) — 检索执行代理
- [03_evidence_fusion_agent.md](./03_evidence_fusion_agent.md) — 证据融合代理
- [04_verification_agent.md](./04_verification_agent.md) — 证据验证代理
- [05_compliance_agent.md](./05_compliance_agent.md) — 合规评估代理
- [06_confidence_agent.md](./06_confidence_agent.md) — 置信度评分代理
- [07_trace_agent.md](./07_trace_agent.md) — 追踪记录代理
- [08_report_agent.md](./08_report_agent.md) — 报告生成代理
- [09_llm_client.md](./09_llm_client.md) — 大语言模型客户端

### 其他文档
- [workflow_overview.md](../workflow_overview.md) — 系统整体流程
- [file_processing_flow.md](../file_processing_flow.md) — 文件处理流程
- [index_quality_improvements.md](../index_quality_improvements.md) — 索引质量优化建议
