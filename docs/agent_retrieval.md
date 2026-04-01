# RetrievalAgent（检索代理）说明文档

## 概述

**RetrievalAgent** 接收 `PlannerAgent` 生成的多个子查询，对每个子查询执行向量相似度搜索，并**去重合并**所有结果，返回得分最高的 Top-K 证据片段。

## 核心职责

- 对多个子查询**并行检索**（通过循环遍历子查询列表）
- **去重** — 相同的 chunk 可能被多个子查询检索到，保留最高分的那次
- **排序并截断** — 按相似度分数从高到低排序，返回 Top-K

## 输入参数

```python
def run(self, queries: list[str], retriever, top_k: int) -> list[SearchResult]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `queries` | `list[str]` | 子查询列表（来自 PlannerAgent） |
| `retriever` | `Retriever` 或 `_KBRetriever` | 向量检索器实例 |
| `top_k` | `int` | 最终返回的最大结果数（通常为 6~8） |

## 处理逻辑

1. **初始化去重字典** — `collected: dict[str, SearchResult] = {}`，key 为 `chunk_id`
2. **遍历所有子查询** — 对每个子查询调用 `retriever.search(query, top_k)`
3. **去重合并** — 对于每个检索结果：
   - 如果 `chunk_id` 第一次出现，加入字典
   - 如果已存在，比较分数，保留更高分的版本
4. **排序截断** — 按 `score` 降序排序，取前 `top_k` 个

## 输出格式

```python
[
    SearchResult(
        chunk_id="uuid-xxx",
        score=0.8234,
        text="GreenTech reduced Scope 1 and Scope 2 emissions by 18%...",
        metadata={
            "source": "storage/kbs/xxx/files/GreenTech_ESG_Report.docx",
            "source_name": "GreenTech_ESG_Report.docx",
            "source_type": "docx",
            "section_start": 20
        }
    ),
    # ... 更多结果
]
```

## 为什么需要去重？

**示例问题**：同一段关于"碳排放"的文本，可能同时匹配：
- 环境查询："Company A environment climate emissions"
- 框架查询："Company A GRI SASB disclosure"

如果不去重，该文本会在结果列表中出现两次，浪费 Top-K 配额。去重后，保留相似度更高的那次检索结果。

## 典型执行流程

1. PlannerAgent 生成 5 个子查询
2. RetrievalAgent 对每个子查询调用 `retriever.search()`
3. 假设每个子查询返回 8 个结果，总共 40 个候选
4. 去重后可能剩余 25 个唯一 chunk
5. 排序后取 Top-8，返回给下游 agent

## 优势

- **多角度覆盖** — 单一查询可能遗漏某些维度，多查询确保全面性
- **去重避免冗余** — 高质量证据只保留一次
- **简单高效** — 逻辑清晰，无复杂依赖
