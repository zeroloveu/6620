# PlannerAgent — 查询规划代理

## 概述
`PlannerAgent` 是 ESG 分析流程的**第一个**代理，负责将用户的自然语言查询分解为多个结构化的子查询，为后续的检索和分析提供方向。

## 核心职责
1. **提取关键词** — 从用户查询中提取 ESG 核心术语（去除停用词）
2. **生成子查询** — 根据 ESG 三大维度（环境、社会、治理）+ 框架合规 + 争议风险，生成 5 个专项子查询
3. **框架标准化** — 将用户指定的框架名称标准化为大写（GRI、SASB、TCFD、CSRD）

## 输入参数
```python
def run(
    self,
    company_name: str,           # 目标公司名称
    user_query: str,              # 用户的原始查询（例如："分析该公司的碳排放管理"）
    framework_focus: list[str]    # 用户关注的 ESG 框架（例如：["GRI", "TCFD"]）
) -> dict:
```

## 输出结构
```python
{
    "objective": "原始用户查询",
    "sub_queries": [
        "公司名 environment climate emissions energy water targets 关键词...",
        "公司名 social workforce safety diversity supply chain community 关键词...",
        "公司名 governance board risk ethics compliance oversight 关键词...",
        "公司名 GRI TCFD disclosure alignment material topics 关键词...",
        "公司名 controversies media sentiment ESG strengths weaknesses 关键词..."
    ],
    "framework_focus": ["GRI", "SASB", "TCFD", "CSRD"],  # 标准化后的框架列表
    "keywords": ["carbon", "emissions", "target", ...]    # 提取的关键词（最多 6 个）
}
```

## 子查询设计逻辑

### 1. 环境维度查询 (Environment)
- 固定术语：`environment climate emissions energy water targets`
- 覆盖主题：气候变化、碳排放、能源管理、水资源、生物多样性

### 2. 社会维度查询 (Social)
- 固定术语：`social workforce safety diversity supply chain community`
- 覆盖主题：员工福利、职业健康安全、多样性与包容、供应链管理、社区影响

### 3. 治理维度查询 (Governance)
- 固定术语：`governance board risk ethics compliance oversight`
- 覆盖主题：董事会结构、风险管理、商业道德、合规监督、内部审计

### 4. 框架合规查询 (Framework Alignment)
- 固定术语：`disclosure alignment material topics` + 用户指定的框架（例如 `GRI TCFD`）
- 目的：检索与特定 ESG 披露框架相关的内容

### 5. 争议与风险查询 (Controversies)
- 固定术语：`controversies media sentiment ESG strengths weaknesses`
- 目的：发现负面新闻、争议事件、ESG 风险点

## 关键词提取规则
- **最小长度**：至少 3 个字符（`[a-zA-Z0-9-]{2,}` 正则匹配）
- **去除停用词**：33 个常见英文停用词（`a`, `and`, `for`, `the`, `to` 等）
- **数量限制**：最多保留 6 个关键词（按出现顺序）
- **去重**：相同关键词只保留一次

## 框架标准化规则
- 默认框架：如果用户未指定，自动使用 `["GRI", "SASB", "TCFD", "CSRD"]`
- 大写转换：所有框架名称统一转为大写（`framework.strip().upper()`）
- 空值处理：空字符串会被过滤掉

## 设计原理

### 为什么要拆分 5 个子查询？
1. **提高召回率** — 单个自然语言查询可能无法覆盖 ESG 的所有维度，拆分为多个专项查询可以确保检索到环境、社会、治理各个方面的证据
2. **语义增强** — 每个子查询注入了 ESG 领域的标准术语（例如 `climate emissions energy`），这些术语在 embedding 空间中能更精准地匹配相关文档
3. **减少漏检** — 即使用户只关注"碳排放"，子查询也会主动检索社会和治理维度的内容，避免分析报告存在明显空白

### 为什么要提取关键词？
- **查询聚焦** — 关键词附加到每个子查询末尾，使检索既有结构化维度（environment/social/governance），又保留用户原始意图（例如用户问"供应链风险"，关键词 `supply`, `chain`, `risk` 会注入到所有子查询）
- **后续复用** — 提取的关键词会记录在 `plan["keywords"]`，供 `TraceAgent` 和 `ReportAgent` 使用

## 在流程中的位置
```
用户请求 → PlannerAgent (生成子查询)
           ↓
           RetrievalAgent (执行多轮检索)
           ↓
           EvidenceFusionAgent → VerificationAgent → ...
```

## 代码示例

```python
from esg_rag.agents import PlannerAgent

agent = PlannerAgent()
plan = agent.run(
    company_name="Tesla Inc.",
    user_query="评估该公司的供应链碳排放管理和生物多样性保护措施",
    framework_focus=["GRI", "TCFD"]
)

print(plan["sub_queries"])
# 输出类似：
# [
#   "Tesla Inc. environment climate emissions energy water targets 供应链 碳排放 生物多样性 保护",
#   "Tesla Inc. social workforce safety diversity supply chain community 供应链 碳排放 生物多样性 保护",
#   "Tesla Inc. governance board risk ethics compliance oversight 供应链 碳排放 生物多样性 保护",
#   "Tesla Inc. GRI TCFD disclosure alignment material topics 供应链 碳排放 生物多样性 保护",
#   "Tesla Inc. controversies media sentiment ESG strengths weaknesses 供应链 碳排放 生物多样性 保护"
# ]
```

## 优化建议
1. **中文关键词提取** — 当前 `_extract_keywords` 只支持英文 `[a-zA-Z0-9]`，可以扩展正则表达式以支持中文：`[a-zA-Z0-9\u4e00-\u9fff]`
2. **动态子查询数量** — 可以根据用户查询的复杂度自适应调整子查询数量（例如简单查询 3 个，复杂查询 7 个）
3. **行业术语库** — 可以为不同行业（金融、制造、能源）定制子查询模板，提升检索精度

## 常见问题

**Q: 为什么不直接用用户的原始查询去检索，而要生成 5 个子查询？**  
A: 用户的自然语言查询往往集中在某个方面（例如只提到"碳排放"），如果只用原始查询检索，可能完全漏掉社会、治理维度的内容，导致分析报告不完整。通过 PlannerAgent 生成的子查询，可以确保 ESG 的三大维度都被检索到。

**Q: 如果用户查询中没有关键词（例如只输入"生成 ESG 报告"），会发生什么？**  
A: `_extract_keywords` 会返回空列表，子查询末尾的 `keyword_string` 为空字符串，不影响子查询的基础结构（依然包含 environment、social、governance 等固定术语）。

**Q: `framework_focus` 参数如果传入小写（例如 `["gri", "tcfd"]`），会影响后续流程吗？**  
A: 不会。`_normalize_frameworks` 会统一转为大写，后续所有 agent（ComplianceAgent、ReportAgent）都使用标准化后的框架名称。

---

**相关文档**：
- [RetrievalAgent — 检索执行代理](./02_retrieval_agent.md)
- [EvidenceFusionAgent — 证据融合代理](./03_evidence_fusion_agent.md)
