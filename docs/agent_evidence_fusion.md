# EvidenceFusionAgent（证据融合代理）说明文档

## 概述

**EvidenceFusionAgent** 对 `RetrievalAgent` 返回的原始检索结果进行**语义标注**和**摘要提取**，为下游分析打标签（environment、social、governance、general）。

## 核心职责

- **自动标签分类** — 根据文本内容中的关键词，给每个证据片段打上 ESG 领域标签
- **提取摘要** — 生成 220 字符以内的简洁摘要，方便快速阅读和展示

## 输入参数

```python
def run(self, results: list[SearchResult]) -> list[dict]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `results` | `list[SearchResult]` | 来自 RetrievalAgent 的检索结果 |

## 处理逻辑

1. **遍历每个检索结果**
2. **标签匹配** — 检查文本中是否包含预定义的标签规则关键词：
   - **environment** — `climate`, `emission`, `energy`, `water`, `waste`, `renewable`, `scope 1`, `scope 2`, `biodiversity`
   - **social** — `employee`, `safety`, `supplier`, `community`, `women`, `diversity`, `workforce`, `training`, `labor`
   - **governance** — `board`, `governance`, `ethics`, `committee`, `corruption`, `compliance`, `whistleblower`, `oversight`, `risk`, `audit`
3. **默认标签** — 如果不匹配任何规则，打 `general` 标签
4. **生成摘要** — 使用 `_clean_excerpt()` 将文本压缩为 ≤220 字符的单行摘要

## 输出格式

```python
[
    {
        "chunk_id": "uuid-xxx",
        "score": 0.8234,
        "text": "完整原文...",
        "metadata": {...},
        "tags": ["environment"],           # 新增：标签列表
        "excerpt": "GreenTech reduced Scope 1 and Scope 2 emissions by 18%..."  # 新增：简洁摘要
    },
    {
        "chunk_id": "uuid-yyy",
        "score": 0.7821,
        "text": "完整原文...",
        "metadata": {...},
        "tags": ["social", "governance"],  # 可能同时匹配多个标签
        "excerpt": "..."
    }
]
```

## 标签规则（TAG_RULES）

定义在 `agents.py` 顶部：

```python
TAG_RULES = {
    "environment": {"climate", "emission", "emissions", "energy", "water", ...},
    "social": {"employee", "employees", "safety", "supplier", ...},
    "governance": {"board", "governance", "ethics", "committee", ...},
}
```

## 为什么需要标签？

下游的 `ComplianceAgent` 需要按维度（环境/社会/治理）分配证据，但原始检索结果是"扁平"的列表。通过标签，可以快速筛选出：
- 只跟环境相关的证据
- 同时涉及社会和治理的证据
- 通用证据（不明确归类）

## 摘要的作用

- **报告生成** — LLM 看到的 prompt 中包含摘要，避免超长文本
- **前端展示** — 用户界面中展示的"excerpt"就是这个摘要
- **可读性** — 将多行文本压缩为单行，去除多余空格

## 示例

**输入**（检索结果）：
```
text: "GreenTech is committed to minimizing our environmental impact and 
contributing to global climate action. We focus on reducing GHG emissions, 
conserving energy and water, managing waste responsibly..."
```

**输出**（融合后）：
```python
{
    ...原始字段...
    "tags": ["environment"],
    "excerpt": "GreenTech is committed to minimizing our environmental impact and contributing to global climate action. We focus on reducing GHG emissions, conserving energy and water, managing waste..."
}
```
