# RetrievalAgent — 检索执行代理

## 概述
`RetrievalAgent` 是 ESG 分析流程的**第二个**代理，负责执行多轮向量检索，并通过**查询扩展**（ESG 同义词替换）提升召回质量。

## 核心职责
1. **查询扩展** — 对每个子查询生成 ESG 同义词变体（例如 `"carbon"` → `["GHG", "carbon dioxide", "carbon footprint"]`）
2. **多轮检索** — 对所有子查询及其同义词变体执行向量检索
3. **结果去重** — 合并多轮检索结果，同一 chunk 只保留最高分的检索记录
4. **按分数排序** — 返回前 `top_k` 个最相关的检索结果

## 输入参数
```python
def run(
    self,
    queries: list[str],         # PlannerAgent 生成的子查询列表（通常 5 个）
    retriever,                  # Retriever 或 _KBRetriever 实例
    top_k: int                  # 最终返回的证据数量（例如 20）
) -> list[SearchResult]:
```

## 输出结构
```python
[
    SearchResult(
        chunk_id="uuid-1",
        score=0.856,
        text="Tesla's Scope 1 emissions decreased by 12% in 2024...",
        metadata={
            "source": "/path/to/tesla_esg_2024.pdf",
            "source_name": "tesla_esg_2024.pdf",
            "page": 15,
            "section_heading": "Environmental Performance"
        }
    ),
    SearchResult(chunk_id="uuid-2", score=0.832, text="...", metadata={...}),
    ...
]
```

## 工作流程

### 1. 查询扩展 (Query Expansion)
对于每个输入查询，调用 `query_expansion.expand_query()` 生成同义词变体：

```python
# 原始查询
q = "Tesla environment climate emissions energy water targets"

# 扩展后（最多 2 个变体）
variants = [
    "Tesla environment climate emissions energy water targets",           # 原始
    "Tesla environment climate GHG energy water targets",                 # carbon → GHG
    "Tesla environment global warming emissions energy water targets"    # climate → global warming
]
```

**扩展规则**：
- 每个查询最多生成 `max_variants=2` 个同义词变体
- 使用 `query_expansion.ESG_SYNONYMS` 字典（包含 30+ 个 ESG 术语的同义词映射）
- 示例映射：
  - `carbon` → `["GHG", "greenhouse gas", "CO2", "carbon dioxide"]`
  - `emissions` → `["GHG emissions", "carbon footprint", "Scope 1", "Scope 2", "Scope 3"]`
  - `employee` → `["workforce", "human capital", "staff", "personnel", "labor"]`

### 2. 多轮检索执行
```python
all_queries = []
for q in queries:  # 5 个 PlannerAgent 生成的子查询
    all_queries.append(q)
    for variant in expand_query(q, max_variants=2):
        if variant != q and variant not in all_queries:
            all_queries.append(variant)

# 最终可能生成 5×3 = 15 个查询（5 个原始 + 10 个同义词变体）

collected = {}
for query in all_queries:
    results = retriever.search(query, top_k=top_k)  # 每次检索返回 top_k 个结果
    for result in results:
        if result.chunk_id not in collected or result.score > collected[result.chunk_id].score:
            collected[result.chunk_id] = result  # 同一 chunk 只保留最高分
```

### 3. 去重与排序
- **去重依据**：`chunk_id`（同一文档块的唯一标识符）
- **分数合并策略**：保留同一 chunk 在多次检索中的**最高分数**
- **最终排序**：按 `score` 降序排列，返回前 `top_k` 个

## 在流程中的位置
```
PlannerAgent (生成 5 个子查询)
    ↓
RetrievalAgent (查询扩展 → 多轮检索 → 去重排序)
    ↓ 输出：list[SearchResult]
EvidenceFusionAgent (标注 ESG 标签)
```

## 查询扩展的价值

### 为什么需要同义词扩展？
1. **术语多样性** — ESG 文档可能使用不同术语表达同一概念（`"carbon footprint"` vs `"GHG emissions"` vs `"Scope 1 emissions"`）
2. **中英文混合** — 支持中文同义词（`"碳排放"` → `["carbon emissions", "温室气体", "GHG", "碳足迹"]`）
3. **提升召回率** — 单个查询可能因术语不匹配而漏检相关文档，同义词扩展可以弥补这一缺陷

### 为什么限制为 `max_variants=2`？
- **平衡召回与精度** — 过多的同义词变体会引入噪音（不相关的结果）
- **控制检索成本** — 每个查询都会调用 embedding 模型，5 个子查询 × 3 个变体 = 15 次 embedding 调用
- **实验结果** — 在测试中，2 个变体已能显著提升召回率，而 3+ 个变体对精度的提升边际递减

## 去重策略对比

### 方案 1：按 chunk_id 去重（当前实现）
```python
collected = {}
for result in all_results:
    if result.chunk_id not in collected or result.score > collected[result.chunk_id].score:
        collected[result.chunk_id] = result
```
- **优点**：保证返回的 chunk 数量严格等于 `top_k`
- **缺点**：可能保留语义相似但 chunk_id 不同的重复内容

### 方案 2：按文本相似度去重（在 `Retriever._rerank_results` 中实现）
```python
deduped = {}
for result in results:
    norm_text = re.sub(r"\s+", " ", result.text).strip().lower()
    if norm_text not in deduped or result.score > deduped[norm_text].score:
        deduped[norm_text] = result
```
- **优点**：能去除语义完全相同的重复 chunk（例如同一段话出现在不同文档）
- **缺点**：对于相似但不完全相同的内容（例如不同年份的报告），可能误去重

**当前流程**：`RetrievalAgent` 使用方案 1，`Retriever` 和 `_KBRetriever` 使用方案 2，两层去重确保结果质量。

## 代码示例

```python
from esg_rag.agents import PlannerAgent, RetrievalAgent
from esg_rag.pipeline import ESGAnalysisPipeline

pipeline = ESGAnalysisPipeline()

# 第一步：PlannerAgent 生成子查询
planner = PlannerAgent()
plan = planner.run(
    company_name="Tesla Inc.",
    user_query="分析碳排放和供应链风险",
    framework_focus=["GRI", "TCFD"]
)

# 第二步：RetrievalAgent 执行检索
retrieval = RetrievalAgent()
results = retrieval.run(
    queries=plan["sub_queries"],  # 5 个子查询
    retriever=pipeline.retriever,
    top_k=20
)

print(f"检索到 {len(results)} 条证据")
for r in results[:3]:
    print(f"[{r.score:.3f}] {r.text[:100]}... (来源: {r.metadata['source_name']})")
```

## 性能优化建议

### 1. 并行检索
当前实现是串行检索（一个查询执行完再执行下一个），可以改为并行：
```python
import concurrent.futures

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(retriever.search, q, top_k) for q in all_queries]
    for future in concurrent.futures.as_completed(futures):
        results = future.result()
        # 合并到 collected
```

### 2. 动态 top_k 调整
可以根据查询数量动态调整每次检索的 `top_k`：
```python
per_query_k = max(10, top_k // len(all_queries))  # 每个查询返回更少结果，减少总计算量
```

### 3. 缓存检索结果
对于相同的查询（例如用户多次分析同一公司），可以缓存 `retriever.search()` 的结果：
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def cached_search(query: str, top_k: int):
    return retriever.search(query, top_k)
```

## 常见问题

**Q: 为什么检索结果数量少于 `top_k`？**  
A: 可能原因：
1. 索引库中的 chunk 总数少于 `top_k`
2. 去重后实际返回的 chunk 数量减少
3. 向量库返回的结果本身不足 `top_k` 个

**Q: 查询扩展会影响检索速度吗？**  
A: 会。查询数量从 5 个增加到 15 个，检索时间理论上增加 3 倍。但由于每个查询的 `top_k` 较小（通常 10-20），实际开销可接受。在生产环境中，可以通过并行检索优化。

**Q: 如果不想使用查询扩展，如何关闭？**  
A: 移除 `expand_query` 调用即可：
```python
collected = {}
for query in queries:  # 直接使用原始查询，不扩展
    for result in retriever.search(query, top_k=top_k):
        # ...
```

---

**相关文档**：
- [PlannerAgent — 查询规划代理](./01_planner_agent.md)
- [EvidenceFusionAgent — 证据融合代理](./03_evidence_fusion_agent.md)
- [query_expansion.py — 查询扩展模块](../modules/query_expansion.md)
