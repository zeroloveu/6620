# PlannerAgent（规划代理）说明文档

## 概述

**PlannerAgent** 是 ESG 分析流水线中的第一个代理，负责将用户的单一查询请求**分解为多个子查询**，以全面覆盖 ESG 三大维度（环境、社会、治理）和框架合规性。

## 核心职责

将一个宽泛的 ESG 分析请求（如"生成 Company A 的 ESG 报告"）拆解为 **5 个专项子查询**，确保后续检索能够：
- 覆盖 **环境、社会、治理** 三个核心维度
- 针对性地检索 **框架披露**（GRI、SASB、TCFD、CSRD）
- 捕获 **争议和风险** 相关信息

## 输入参数

```python
def run(self, company_name: str, user_query: str, framework_focus: list[str]) -> dict
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `company_name` | `str` | 公司名称（用于生成公司特定的查询） |
| `user_query` | `str` | 用户原始请求（如"为 XX 公司生成 ESG 分析"） |
| `framework_focus` | `list[str]` | 关注的 ESG 披露框架列表（如 `["GRI", "SASB"]`） |

## 处理逻辑

1. **规范化框架** — 将 `framework_focus` 转为大写标准形式，默认使用 `["GRI", "SASB", "TCFD", "CSRD"]`
2. **提取关键词** — 从 `user_query` 中提取最多 6 个关键词（排除停用词）
3. **生成 5 个子查询**：
   - **环境查询** — `{公司名} environment climate emissions energy water targets {关键词}`
   - **社会查询** — `{公司名} social workforce safety diversity supply chain community {关键词}`
   - **治理查询** — `{公司名} governance board risk ethics compliance oversight {关键词}`
   - **框架查询** — `{公司名} {框架列表} disclosure alignment material topics {关键词}`
   - **争议查询** — `{公司名} controversies media sentiment ESG strengths weaknesses {关键词}`

## 输出格式

```python
{
    "objective": "生成 Company A 的 ESG 分析",
    "sub_queries": [
        "Company A environment climate emissions energy water targets esg performance",
        "Company A social workforce safety diversity supply chain community esg performance",
        "Company A governance board risk ethics compliance oversight esg performance",
        "Company A GRI SASB TCFD CSRD disclosure alignment material topics esg performance",
        "Company A controversies media sentiment ESG strengths weaknesses esg performance"
    ],
    "framework_focus": ["GRI", "SASB", "TCFD", "CSRD"],
    "keywords": ["esg", "performance", "company"]
}
```

## 设计思想

- **避免单一查询遗漏** — 用户查询可能笼统（如"生成报告"），单次检索难以覆盖 ESG 全貌
- **领域导向扩展** — 子查询预置了 ESG 领域的高频术语（emissions、diversity、board 等），提升检索召回率
- **可审计** — 所有子查询都记录在 `agent_trace` 中，便于追溯分析逻辑

## 典型使用场景

用户输入：
```
公司：GreenTech
请求：生成结构化 ESG 分析
框架：GRI, SASB
```

PlannerAgent 输出：
```python
{
  "objective": "生成结构化 ESG 分析",
  "sub_queries": [
    "GreenTech environment climate emissions energy water targets",
    "GreenTech social workforce safety diversity supply chain community",
    "GreenTech governance board risk ethics compliance oversight",
    "GreenTech GRI SASB disclosure alignment material topics",
    "GreenTech controversies media sentiment ESG strengths weaknesses"
  ],
  "framework_focus": ["GRI", "SASB"],
  "keywords": []
}
```

这 5 个子查询会被 `RetrievalAgent` 并行执行，确保检索到的证据均匀覆盖各维度。
