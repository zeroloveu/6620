# 检索与查询完整流程详解

> **文档版本**: v1.0  
> **最后更新**: 2026-03-31  
> **适用项目**: ESG RAG 系统

---

## 📋 目录

1. [概述](#概述)
2. [场景 1：简单查询（Query）](#场景-1简单查询query)
3. [场景 2：完整分析（Analyze）](#场景-2完整分析analyze)
4. [核心技术详解](#核心技术详解)
5. [性能数据](#性能数据)
6. [常见问题](#常见问题)

---

## 概述

### 什么是检索与查询阶段？

检索与查询阶段是 ESG RAG 系统的核心环节，负责：

1. **理解用户意图** — 将自然语言查询转换为可检索的向量
2. **多轮检索** — 从知识库中找到最相关的证据
3. **智能排序** — 综合语义、关键词、时间等多维度排序
4. **多 Agent 协同** — 通过 8 个专业 Agent 生成结构化报告

### 两种使用场景

| 场景 | API 端点 | 返回内容 | 耗时 | 适用情况 |
|-----|---------|---------|------|---------|
| **简单查询** | `POST /query` | `list[SearchResult]` | ~50ms | 快速检索相关文档片段 |
| **完整分析** | `POST /analyze` | 结构化 ESG 报告 (JSON) | 5-120 秒 | 生成专业分析报告 |

---

## 场景 1：简单查询（Query）

### 用户请求示例

```python
POST /query
{
    "query": "Tesla 的碳排放管理",
    "kb_ids": ["abc123"],  # 指定知识库
    "top_k": 6             # 返回 6 个结果
}
```

### 完整流程图

```
用户查询: "Tesla 的碳排放管理"
    ↓
【步骤 1】查询增强 (enrich_query)
    原始查询 + ESG 同义词
    ↓
【步骤 2】向量化查询
    文本 → 384 维向量
    ↓
【步骤 3】向量检索 (从多个知识库)
    候选集: top_24 (4 倍过采样)
    ↓
【步骤 4】Reranking (二次排序)
    - 关键词重叠加分
    - 时间加权 (优先新文档)
    - 文本去重
    ↓
返回 top_6 结果
```

---

### 【步骤 1】查询增强

#### 代码实现

```python
# 文件: src/esg_rag/pipeline.py (line 42-50)

def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
    from esg_rag.query_expansion import enrich_query

    top_k = top_k or self.settings.top_k
    enriched = enrich_query(query)  # ← 查询增强
    query_vector = self.embedding_provider.embed_query(enriched)
    candidate_k = max(top_k, top_k * self.settings.retrieval_candidate_multiplier)
    results = self.vector_store.search(query_vector, top_k=candidate_k)
    return self._rerank_results(query, results, top_k=top_k)
```

#### 增强逻辑

```python
# 文件: src/esg_rag/query_expansion.py (line 71-83)

def enrich_query(query: str) -> str:
    """
    在查询末尾附加 ESG 同义词，提升召回率
    
    示例:
        输入: "Tesla 的碳排放管理"
        输出: "Tesla 的碳排放管理 carbon emissions GHG 温室气体 碳足迹"
    """
    query_lower = query.lower()
    extra_terms: list[str] = []
    
    # 遍历 ESG 同义词字典 (42 组同义词)
    for term, synonyms in ESG_SYNONYMS.items():
        if term.lower() in query_lower:  # 检测到 "碳排放"
            for syn in synonyms[:2]:     # 取前 2 个同义词
                if syn.lower() not in query_lower:
                    extra_terms.append(syn)
    
    if not extra_terms:
        return query
    
    # 附加到查询末尾 (最多 6 个)
    return f"{query} {' '.join(extra_terms[:6])}"
```

#### 实际效果

| 原始查询 | 增强后查询 |
|---------|-----------|
| `Tesla 的碳排放管理` | `Tesla 的碳排放管理 carbon emissions GHG 温室气体 碳足迹` |
| `员工安全培训` | `员工安全培训 workforce health and safety occupational safety` |
| `董事会治理` | `董事会治理 board of directors corporate governance accountability` |

**为什么要增强查询？**

- ✅ 处理同义词 (`碳排放` ↔ `carbon emissions` ↔ `GHG`)
- ✅ 跨语言检索 (中文查询也能匹配英文文档)
- ✅ 提升召回率 (不会漏掉使用不同术语的相关文档)

---

### 【步骤 2】向量化查询

#### 代码实现

```python
query_vector = self.embedding_provider.embed_query(enriched)
```

#### 内部流程

```python
# 文件: src/esg_rag/embedding.py (SentenceTransformerEmbeddingProvider)

def embed_query(self, text: str) -> np.ndarray:
    """
    使用 Sentence-BERT 模型将文本编码为向量
    
    模型: all-MiniLM-L6-v2 (默认)
    维度: 384
    """
    # 1. Tokenization (分词)
    tokens = self.tokenizer.encode(text)
    # 输入: "Tesla 的碳排放管理 carbon emissions GHG"
    # 输出: [101, 8915, 1052, 12043, 3198, 2290, 3824, 6243, 102]
    
    # 2. Transformer Encoding (Transformer 编码)
    hidden_states = self.model(tokens)
    # 输出: (batch_size=1, seq_len=9, hidden_dim=384)
    
    # 3. Mean Pooling (平均池化)
    sentence_embedding = torch.mean(hidden_states, dim=1)
    # 输出: (1, 384)
    
    # 4. Normalization (归一化)
    normalized = F.normalize(sentence_embedding, p=2, dim=1)
    # 输出: (1, 384), L2 范数 = 1.0
    
    return normalized.cpu().numpy()[0]
```

#### 输出示例

```python
query_vector = np.array([
    0.15234, -0.23456, 0.67890, 0.34567, -0.45678, 0.12345, ...,
    # ... 共 384 个浮点数
    -0.56789, 0.78901, -0.11223
])

# 形状: (384,)
# 数据类型: float32
# L2 范数: 1.0
```

---

### 【步骤 3】向量检索

#### 代码实现

```python
# 文件: src/esg_rag/pipeline.py (line 202-215)

def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
    top_k = top_k or self.settings.top_k
    candidate_k = max(top_k, top_k * self.settings.retrieval_candidate_multiplier)
    # candidate_k = max(6, 6 * 4) = 24 (检索 4 倍候选)
    
    enriched = enrich_query(query)
    query_vector = self.embedding_provider.embed_query(enriched)
    
    all_results: list[SearchResult] = []
    for store in self.stores:  # 遍历所有知识库的索引
        all_results.extend(store.search(query_vector, top_k=candidate_k))
    
    return self._rerank(query, all_results, top_k)
```

#### SimpleVectorStore 内部实现

```python
# 文件: src/esg_rag/vector_store.py

def search(self, query_vector: np.ndarray, top_k: int) -> list[SearchResult]:
    """
    使用余弦相似度进行向量检索
    """
    # 1. 加载索引
    if self.vectors is None:
        self.vectors = np.load(self.matrix_path)  # shape: (450, 384)
        self.chunks = json.load(self.meta_path)   # 450 个 chunk 元数据
    
    # 2. 计算余弦相似度 (因为向量已归一化，内积 = 余弦相似度)
    query = query_vector.astype(np.float32)
    scores = self.vectors @ query  # 矩阵乘法，结果: (450,)
    
    # 3. 排序并取 top_k
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    # 4. 构造返回结果
    return [
        SearchResult(
            chunk_id=self.chunks[i].chunk_id,
            score=float(scores[i]),
            text=self.chunks[i].text,
            metadata=self.chunks[i].metadata
        )
        for i in top_indices
    ]
```

#### 候选结果示例

```python
# 从单个知识库检索到 24 个候选
[
    SearchResult(score=0.91, chunk_id="a3f8...", text="[Environmental Performance]..."),
    SearchResult(score=0.88, chunk_id="b4g9...", text="[Climate Strategy]..."),
    SearchResult(score=0.85, chunk_id="c5h0...", text="[Energy Management]..."),
    # ... 共 24 个候选
]

# 如果有 2 个知识库，合并后可能有 48 个候选
```

---

### 【步骤 4】Reranking（二次排序）⭐

#### 为什么需要 Reranking？

向量检索虽然快速，但存在局限性：

- ❌ **语义漂移** — 相似向量不一定是相关文档
- ❌ **忽略关键词** — "Tesla" 查询可能返回 "Ford" 的文档（因为都是汽车公司）
- ❌ **忽略时间** — 2018 年的报告和 2024 年的报告相似度可能相同

Reranking 通过引入额外的排序因子解决这些问题。

#### 代码实现

```python
# 文件: src/esg_rag/pipeline.py (line 217-238)

def _rerank(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
    """
    二次排序：综合语义、关键词、时间三个维度
    
    评分公式:
        final_score = vector_score + keyword_boost + time_boost
    """
    query_tokens = self._tokenize(query)
    deduped: dict[str, SearchResult] = {}
    
    for r in results:  # 遍历 24-48 个候选
        # 1. 文本归一化 (用于去重)
        norm_text = re.sub(r"\s+", " ", r.text).strip().lower()
        
        # 2. 关键词重叠计算
        chunk_tokens = self._tokenize(r.text)
        kw_overlap = self._keyword_overlap(query_tokens, chunk_tokens)
        kw_boost = kw_overlap * 0.15  # 关键词加分权重: 15%
        
        # 3. 时间加权
        year_boost = self._temporal_boost(r.metadata)
        
        # 4. 综合评分
        score = float(r.score) + kw_boost + year_boost
        
        boosted = SearchResult(
            chunk_id=r.chunk_id,
            score=round(score, 4),
            text=r.text,
            metadata=r.metadata,
        )
        
        # 5. 去重 (相同文本只保留最高分)
        existing = deduped.get(norm_text)
        if existing is None or boosted.score > existing.score:
            deduped[norm_text] = boosted
    
    # 6. 排序并返回 top_k
    ranked = sorted(deduped.values(), key=lambda x: x.score, reverse=True)
    return ranked[:top_k]
```

#### 关键词重叠计算

```python
def _tokenize(self, text: str) -> set[str]:
    """
    分词器：支持中英文
    """
    # 正则: 字母/数字/中文字符开头，后跟字母/数字/中文/连字符
    return set(re.findall(r"[a-zA-Z0-9\u4e00-\u9fff][a-zA-Z0-9\u4e00-\u9fff-]{1,}", text.lower()))

def _keyword_overlap(self, query_tokens: set[str], result_tokens: set[str]) -> float:
    """
    计算查询词在结果中的覆盖率
    
    示例:
        query_tokens = {"tesla", "碳排放", "管理", "carbon", "emissions"}
        result_tokens = {"environmental", "performance", "emissions", "decreased"}
        
        交集 = {"emissions"}
        overlap = 1 / 5 = 0.2
    """
    if not query_tokens:
        return 0.0
    return len(query_tokens & result_tokens) / len(query_tokens)
```

#### 时间加权计算

```python
# 文件: src/esg_rag/pipeline.py (line 240-246)

_YEAR_RE = re.compile(r"(20\d{2})")  # 匹配 2000-2099 年份

def _temporal_boost(self, metadata: dict) -> float:
    """
    根据文档年份计算时间加权
    
    规则: 每年衰减 -0.01 分
    
    示例:
        文件名: "tesla_esg_2024.pdf"
        当前年份: 2026
        age = 2026 - 2024 = 2
        boost = -0.01 * 2 = -0.02
    """
    name = metadata.get("source_name", "")
    match = self._YEAR_RE.search(name)
    if not match:
        return 0.0
    age = max(0, 2026 - int(match.group(1)))
    return round(-0.01 * age, 4)
```

#### Reranking 效果示例

| Chunk | 向量分数 | 关键词加分 | 时间加权 | 最终分数 | 排名变化 |
|-------|---------|-----------|---------|---------|---------|
| Chunk A | 0.85 | +0.02 (13%) | -0.02 (2 年) | **0.85** | 1 → 1 |
| Chunk B | 0.83 | +0.08 (53%) | -0.01 (1 年) | **0.90** | 3 → **1** ⬆️⬆️ |
| Chunk C | 0.88 | +0.00 (0%) | -0.05 (5 年) | **0.83** | 2 → 3 ⬇️ |
| Chunk D | 0.86 | +0.04 (27%) | -0.03 (3 年) | **0.87** | 4 → 2 ⬆️ |

**结论**：
- **Chunk B** 虽然向量分数较低 (0.83)，但因为关键词覆盖率高 (53%) 且文档较新，最终排名第 1
- **Chunk C** 虽然向量分数最高 (0.88)，但因为关键词覆盖率低且文档较旧 (5 年前)，排名下降

---

### 最终返回结果

```python
[
    SearchResult(
        chunk_id="a3f8...",
        score=0.90,
        text="[Environmental Performance]\nOur Scope 1 emissions decreased by 12% in 2024, achieving 120,000 tCO2e compared to 136,000 tCO2e in 2023. This reduction was driven by increased renewable energy adoption...",
        metadata={
            "source": "C:/Users/81011/Desktop/Myrag/storage/kbs/abc123/files/tesla_esg_2024.pdf",
            "source_name": "tesla_esg_2024.pdf",
            "source_type": "pdf",
            "page": 15,
            "total_pages": 120,
            "section_heading": "Environmental Performance",
            "section_start": 34567,
            "section_index": 3,
            "window_index": 0
        }
    ),
    SearchResult(
        chunk_id="b4g9...",
        score=0.85,
        text="[Climate Strategy]\nTesla's carbon management strategy focuses on three pillars: emissions reduction, renewable energy, and carbon offsetting. Our long-term goal is to achieve net-zero Scope 1 and 2 emissions by 2030...",
        metadata={
            "source_name": "tesla_esg_2024.pdf",
            "page": 18,
            "section_heading": "Climate Strategy"
        }
    ),
    # ... 共 6 个结果
]
```

---

## 场景 2：完整分析（Analyze）

### 用户请求示例

```python
POST /analyze
{
    "company_name": "Tesla Inc.",
    "query": "分析 Tesla 的碳排放管理策略",
    "framework_focus": ["GRI", "TCFD"],
    "kb_ids": ["abc123"],
    "top_k": 8
}
```

### Multi-Agent 流程图

```
用户查询
    ↓
┌─────────────────────────────────────────────────────┐
│ Agent 1: PlannerAgent (查询规划)                      │
│   职责: 拆分查询，生成子查询                            │
│   输入: "分析 Tesla 的碳排放管理策略"                   │
│   输出: 5 个子查询 (覆盖 ESG 三大维度)                  │
└─────────────────────┬───────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ Agent 2: RetrievalAgent (多轮检索)                    │
│   职责: 查询扩展 + 多轮检索 + 结果合并                  │
│   输入: 5 个子查询                                     │
│   输出: 8 个最相关的 SearchResult                      │
└─────────────────────┬───────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ Agent 3: EvidenceFusionAgent (证据融合)               │
│   职责: ESG 标签分类 + 生成摘要                        │
│   输入: 8 个 SearchResult                             │
│   输出: 8 个带 tags 和 excerpt 的证据                 │
└─────────────────────┬───────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ Agent 4: VerificationAgent (证据验证)                 │
│   职责: 质量检查 + 可追溯性验证                         │
│   输入: 8 个证据                                       │
│   输出: 8 个带 verification_notes 的证据              │
└─────────────────────┬───────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ Agent 5 & 6: ComplianceAgent + ConfidenceAgent      │
│   职责: 框架对齐评估 + 置信度评分                      │
│   输入: 8 个验证后的证据                               │
│   输出: compliance 对象 + confidence 对象              │
└─────────────────────┬───────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ Agent 7: TraceAgent (追踪记录)                        │
│   职责: 汇总所有中间结果                               │
│   输入: plan + evidence + compliance + confidence    │
│   输出: agent_trace (执行日志)                         │
└─────────────────────┬───────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│ Agent 8: ReportAgent (报告生成)                       │
│   职责: 调用 LLM 生成结构化报告                        │
│   输入: 所有中间结果                                   │
│   输出: 结构化 ESG 报告 (JSON)                         │
└─────────────────────────────────────────────────────┘
```

---

### Agent 1: PlannerAgent（查询规划）

#### 职责

将用户的单一查询拆分为 **5 个子查询**，确保覆盖 ESG 三大维度 + 框架对齐 + 负面新闻。

#### 代码实现

```python
# 文件: src/esg_rag/agents.py (line 101-117)

class PlannerAgent:
    def run(self, company_name: str, user_query: str, framework_focus: list[str]) -> dict:
        framework_terms = _normalize_frameworks(framework_focus)
        keyword_string = " ".join(_extract_keywords(user_query))
        
        sub_queries = [
            f"{company_name} environment climate emissions energy water targets {keyword_string}".strip(),
            f"{company_name} social workforce safety diversity supply chain community {keyword_string}".strip(),
            f"{company_name} governance board risk ethics compliance oversight {keyword_string}".strip(),
            f"{company_name} {' '.join(framework_terms)} disclosure alignment material topics {keyword_string}".strip(),
            f"{company_name} controversies media sentiment ESG strengths weaknesses {keyword_string}".strip(),
        ]
        
        return {
            "objective": user_query,
            "sub_queries": sub_queries,
            "framework_focus": framework_terms,
            "keywords": _extract_keywords(user_query),
        }
```

#### 输入输出示例

**输入**：
```python
company_name = "Tesla Inc."
user_query = "分析 Tesla 的碳排放管理策略"
framework_focus = ["GRI", "TCFD"]
```

**输出**：
```python
{
    "objective": "分析 Tesla 的碳排放管理策略",
    "sub_queries": [
        "Tesla Inc. environment climate emissions energy water targets 碳排放 管理 策略",
        "Tesla Inc. social workforce safety diversity supply chain community 碳排放 管理 策略",
        "Tesla Inc. governance board risk ethics compliance oversight 碳排放 管理 策略",
        "Tesla Inc. GRI TCFD disclosure alignment material topics 碳排放 管理 策略",
        "Tesla Inc. controversies media sentiment ESG strengths weaknesses 碳排放 管理 策略"
    ],
    "framework_focus": ["GRI", "TCFD"],
    "keywords": ["碳排放", "管理", "策略"]
}
```

#### 设计思路

| 子查询编号 | 关注维度 | 注入的关键词 |
|-----------|---------|------------|
| #1 | 环境 (E) | `environment climate emissions energy water targets` |
| #2 | 社会 (S) | `social workforce safety diversity supply chain community` |
| #3 | 治理 (G) | `governance board risk ethics compliance oversight` |
| #4 | 框架对齐 | `GRI TCFD disclosure alignment material topics` |
| #5 | 负面新闻 | `controversies media sentiment ESG strengths weaknesses` |

**为什么要拆分成 5 个子查询？**

- ✅ 确保 ESG 三大维度都被检索到（不会偏向某一维度）
- ✅ 每个维度注入领域术语，提升召回精度
- ✅ 特别检索框架对齐和负面信息

---

### Agent 2: RetrievalAgent（多轮检索）

#### 职责

1. **查询扩展** — 为每个子查询生成同义词变体
2. **多轮检索** — 对所有查询（原始 + 变体）执行检索
3. **结果合并** — 去重并返回 top_k 个最佳结果

#### 代码实现

```python
# 文件: src/esg_rag/agents.py (line 120-137)

class RetrievalAgent:
    def run(self, queries: list[str], retriever, top_k: int) -> list[SearchResult]:
        from esg_rag.query_expansion import expand_query
        
        # 步骤 1: 查询扩展
        all_queries: list[str] = []
        for q in queries:  # 5 个子查询
            all_queries.append(q)
            for variant in expand_query(q, max_variants=2):
                if variant != q and variant not in all_queries:
                    all_queries.append(variant)
        
        # 步骤 2: 多轮检索
        collected: dict[str, SearchResult] = {}
        for query in all_queries:  # 15 个查询
            for result in retriever.search(query, top_k=top_k):
                existing = collected.get(result.chunk_id)
                # 同一 chunk 只保留最高分
                if existing is None or result.score > existing.score:
                    collected[result.chunk_id] = result
        
        # 步骤 3: 排序并返回 top_k
        return sorted(collected.values(), key=lambda item: item.score, reverse=True)[:top_k]
```

#### 查询扩展示例

```python
# 原始子查询 #1:
"Tesla Inc. environment climate emissions energy water targets 碳排放 管理 策略"

# 变体 1 (替换 "climate"):
"Tesla Inc. environment global warming emissions energy water targets 碳排放 管理 策略"

# 变体 2 (替换 "emissions"):
"Tesla Inc. environment climate GHG emissions energy water targets 碳排放 管理 策略"
```

#### 多轮检索流程

```
5 个子查询 × 3 个变体 (1 原始 + 2 同义词) = 15 个查询

for each 查询 in 15 个查询:
    1. 查询增强 (enrich_query)
    2. 向量化
    3. 向量检索 (top_8)
    4. Reranking
    5. 结果加入 collected (按 chunk_id 去重)

最终 collected 可能包含 15-30 个不同的 chunk
排序并取 top_8
```

#### 输出示例

```python
[
    SearchResult(score=0.91, text="[Environmental Performance]\nScope 1 emissions..."),
    SearchResult(score=0.88, text="[Climate Strategy]\nCarbon reduction targets..."),
    SearchResult(score=0.85, text="[Energy Management]\nRenewable energy projects..."),
    SearchResult(score=0.82, text="[Governance]\nBoard oversight of climate risks..."),
    SearchResult(score=0.79, text="[Social Impact]\nSupply chain carbon footprint..."),
    SearchResult(score=0.76, text="[Environmental Data]\nScope 2 emissions table..."),
    SearchResult(score=0.73, text="[Climate Disclosure]\nTCFD alignment statement..."),
    SearchResult(score=0.70, text="[Risk Management]\nClimate risk assessment...")
]
```

---

### Agent 3: EvidenceFusionAgent（证据融合）

#### 职责

为每个 SearchResult 添加：
- **tags** — ESG 维度标签 (`environment`, `social`, `governance`)
- **excerpt** — 简短摘要（前 220 个字符）

#### 代码实现

```python
# 文件: src/esg_rag/agents.py (line 140-149)

class EvidenceFusionAgent:
    def run(self, results: list[SearchResult]) -> list[dict]:
        fused: list[dict] = []
        for result in results:
            text_lower = result.text.lower()
            
            # 根据关键词匹配 ESG 标签
            tags = [
                tag for tag, keywords in TAG_RULES.items()
                if any(token in text_lower for token in keywords)
            ]
            if not tags:
                tags.append("general")
            
            fused.append({
                **asdict(result),
                "tags": tags,
                "excerpt": _clean_excerpt(result.text)
            })
        return fused
```

#### TAG_RULES 规则

```python
# 文件: src/esg_rag/agents.py (line 35-73)

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

#### 输出示例

```python
[
    {
        "chunk_id": "a3f8...",
        "score": 0.91,
        "text": "[Environmental Performance]\nScope 1 emissions decreased by 12%...",
        "metadata": {...},
        "tags": ["environment"],  # ← 新增
        "excerpt": "Scope 1 emissions decreased by 12% in 2024, achieving 120,000 tCO2e..."  # ← 新增
    },
    {
        "chunk_id": "b4g9...",
        "score": 0.82,
        "text": "[Governance]\nBoard oversight of climate risks through quarterly reviews...",
        "metadata": {...},
        "tags": ["governance", "environment"],  # ← 可能包含多个标签！
        "excerpt": "Board oversight of climate risks through quarterly reviews..."
    },
    # ... 共 8 个证据
]
```

---

### Agent 4: VerificationAgent（证据验证）

#### 职责

为每个证据添加 **verification_notes**（质量评估备注），包括：
- 文本长度检查
- 相似度分数评估
- 来源可追溯性验证
- 数据类型识别

#### 代码实现

```python
# 文件: src/esg_rag/agents.py (line 152-171)

class VerificationAgent:
    def run(self, results: list[dict]) -> list[dict]:
        verified: list[dict] = []
        for result in results:
            notes: list[str] = []
            metadata = result["metadata"]
            
            # 检查 1: 文本长度
            if len(result["text"]) < 120:
                notes.append("Short excerpt; inspect adjacent source context.")
            
            # 检查 2: 相似度分数
            if result["score"] < 0.2:
                notes.append("Similarity score is modest, so this evidence should be cross-checked.")
            
            # 检查 3: 来源可追溯性
            if "source" not in metadata:
                notes.append("Missing source metadata.")
            else:
                notes.append(f"Traceable source: {metadata.get('source_name', metadata['source'])}.")
            
            # 检查 4: 页码
            if metadata.get("page") is not None:
                notes.append(f"Page {metadata['page']} available for citation.")
            
            # 检查 5: 数据类型
            if metadata.get("source_type") == "json":
                notes.append("Structured supplementary data; corroborate against narrative disclosures.")
            
            verified.append({**result, "verification_notes": " ".join(notes)})
        return verified
```

#### 输出示例

```python
{
    "chunk_id": "a3f8...",
    "score": 0.91,
    "text": "...",
    "tags": ["environment"],
    "excerpt": "...",
    "verification_notes": "Traceable source: tesla_esg_2024.pdf. Page 15 available for citation."  # ← 新增
}
```

---

### Agent 5 & 6: ComplianceAgent + ConfidenceAgent

#### ComplianceAgent（框架对齐评估）

##### 职责

评估证据对 ESG 报告框架的覆盖程度（GRI、SASB、TCFD、CSRD）。

##### 代码实现

```python
# 文件: src/esg_rag/agents.py (line 174-208)

class ComplianceAgent:
    def run(self, framework_focus: list[str], evidence: list[dict]) -> dict:
        frameworks = _normalize_frameworks(framework_focus)
        alignment: dict[str, dict] = {}
        
        for framework in frameworks:
            evidence_hits = []
            covered_tags: set[str] = set()
            
            for item in evidence:
                tags = item.get("tags", [])
                excerpt = item.get("excerpt") or _clean_excerpt(item["text"])
                
                # 框架匹配规则
                if framework == "TCFD" and "environment" in tags:
                    evidence_hits.append(excerpt)
                    covered_tags.update(tags)
                elif framework == "SASB" and any(tag in tags for tag in ("environment", "social", "governance")):
                    evidence_hits.append(excerpt)
                    covered_tags.update(tags)
                elif framework in {"GRI", "CSRD"}:
                    evidence_hits.append(excerpt)
                    covered_tags.update(tags)
            
            # 覆盖度评级
            count = len(evidence_hits)
            if count >= 4:
                coverage = "high"
            elif count >= 2:
                coverage = "moderate"
            elif count == 1:
                coverage = "limited"
            else:
                coverage = "low"
            
            alignment[framework] = {
                "coverage": coverage,
                "matched_evidence_count": count,
                "covered_topics": sorted(tag for tag in covered_tags if tag != "general"),
                "notes": evidence_hits[:3],
            }
        return alignment
```

##### 输出示例

```python
{
    "GRI": {
        "coverage": "high",
        "matched_evidence_count": 8,
        "covered_topics": ["environment", "governance", "social"],
        "notes": [
            "Scope 1 emissions decreased by 12% in 2024...",
            "Board oversight of climate risks through quarterly reviews...",
            "Employee safety training hours increased by 25%..."
        ]
    },
    "TCFD": {
        "coverage": "moderate",
        "matched_evidence_count": 3,
        "covered_topics": ["environment"],
        "notes": [
            "Scope 1 emissions decreased by 12% in 2024...",
            "Climate risk assessment updated in Q4 2024...",
            "Renewable energy projects expanded to 250 MW..."
        ]
    }
}
```

---

#### ConfidenceAgent（置信度评分）

##### 职责

综合评估检索结果的质量和可靠性。

##### 代码实现

```python
# 文件: src/esg_rag/agents.py (line 211-233)

class ConfidenceAgent:
    def run(self, evidence: list[dict]) -> dict:
        if not evidence:
            return {"level": "low", "score": 0.0, "reason": "No evidence retrieved."}
        
        # 因子 1: 平均相似度分数 (55% 权重)
        avg_score = sum(item["score"] for item in evidence) / len(evidence)
        
        # 因子 2: 可追溯性比例 (20% 权重)
        traceable_ratio = sum(1 for item in evidence if "source" in item["metadata"]) / len(evidence)
        
        # 因子 3: 话题覆盖率 (15% 权重)
        unique_tags = {tag for item in evidence for tag in item.get("tags", []) if tag != "general"}
        coverage_ratio = len(unique_tags) / 3  # 3 = ESG 三大维度
        
        # 因子 4: 证据数量 (10% 权重)
        evidence_volume = min(len(evidence) / 6, 1.0)
        
        # 综合评分
        numeric_score = round(
            (avg_score * 0.55) + (traceable_ratio * 0.2) + (coverage_ratio * 0.15) + (evidence_volume * 0.1),
            3,
        )
        
        # 评级
        if numeric_score >= 0.72:
            level = "high"
        elif numeric_score >= 0.48:
            level = "medium"
        else:
            level = "low"
        
        return {
            "level": level,
            "score": numeric_score,
            "reason": "Blend of retrieval quality, traceability, topic coverage, and evidence volume.",
        }
```

##### 评分示例

**假设有 8 条证据**：

```python
avg_score = 0.82          # 平均相似度
traceable_ratio = 1.0     # 100% 可追溯
coverage_ratio = 1.0      # 覆盖 3/3 个 ESG 维度
evidence_volume = 1.0     # 8/6 = 1.33，上限 1.0

numeric_score = (0.82 * 0.55) + (1.0 * 0.20) + (1.0 * 0.15) + (1.0 * 0.10)
              = 0.451 + 0.20 + 0.15 + 0.10
              = 0.901

level = "high"  # >= 0.72
```

##### 输出示例

```python
{
    "level": "high",
    "score": 0.901,
    "reason": "Blend of retrieval quality, traceability, topic coverage, and evidence volume."
}
```

---

### Agent 7: TraceAgent（追踪记录）

#### 职责

汇总所有中间结果，提供完整的执行日志。

#### 代码实现

```python
# 文件: src/esg_rag/agents.py (line 236-248)

class TraceAgent:
    def run(self, plan: dict, evidence: list[dict], compliance: dict, confidence: dict) -> list[dict]:
        tag_counter = Counter(tag for item in evidence for tag in item.get("tags", []))
        return [
            {"agent": "planner", "output": plan},
            {
                "agent": "retrieval_fusion",
                "retrieved_evidence": len(evidence),
                "tag_breakdown": dict(tag_counter),
            },
            {"agent": "compliance", "output": compliance},
            {"agent": "confidence", "output": confidence},
        ]
```

#### 输出示例

```python
[
    {
        "agent": "planner",
        "output": {
            "objective": "分析 Tesla 的碳排放管理策略",
            "sub_queries": [...],
            "keywords": ["碳排放", "管理", "策略"]
        }
    },
    {
        "agent": "retrieval_fusion",
        "retrieved_evidence": 8,
        "tag_breakdown": {
            "environment": 5,
            "governance": 2,
            "social": 1
        }
    },
    {
        "agent": "compliance",
        "output": {...}
    },
    {
        "agent": "confidence",
        "output": {...}
    }
]
```

---

### Agent 8: ReportAgent（报告生成）

#### 职责

调用 DeepSeek LLM 生成结构化 ESG 报告。

#### 代码实现

```python
# 文件: src/esg_rag/agents.py (line 251-303)

class ReportAgent:
    def __init__(self, settings: Settings) -> None:
        self.llm = LLMClient(settings)
    
    def run(
        self,
        company_name: str,
        user_query: str,
        framework_focus: list[str],
        evidence: list[dict],
        compliance_alignment: dict,
        confidence_assessment: dict,
        agent_trace: list[dict],
    ) -> dict:
        # 步骤 1: 构造 Prompt
        evidence_text = "\n\n".join([
            (
                f"Source: {item['metadata'].get('source', 'unknown')}\n"
                f"Page: {item['metadata'].get('page')}\n"
                f"Score: {item['score']:.4f}\n"
                f"Tags: {', '.join(item.get('tags', []))}\n"
                f"Verification: {item['verification_notes']}\n"
                f"Excerpt:\n{item['text']}"
            )
            for item in evidence
        ])
        
        prompt = f"""
Company: {company_name}
User request: {user_query}
Framework focus: {", ".join(_normalize_frameworks(framework_focus))}
Compliance alignment input: {compliance_alignment}
Confidence assessment input: {confidence_assessment}
Agent trace summary: {agent_trace}

You must produce a structured ESG analysis with Environment, Social, Governance,
compliance alignment, confidence assessment, and next steps.
Use only the evidence below and be explicit about gaps.

Evidence:
{evidence_text}
""".strip()
        
        # 步骤 2: 调用 LLM
        report = self.llm.structured_esg_report(
            prompt=prompt,
            company_name=company_name,
            evidence=evidence,
            compliance_alignment=compliance_alignment,
            confidence_assessment=confidence_assessment,
        )
        
        # 步骤 3: 合并结果
        report["compliance_alignment"] = compliance_alignment
        report["confidence_assessment"] = confidence_assessment
        report["agent_trace"] = agent_trace
        return report
```

#### LLM 调用流程

```python
# 文件: src/esg_rag/llm.py

def structured_esg_report(self, prompt: str, ...) -> dict:
    """
    调用 DeepSeek API，使用流式响应
    """
    response = httpx.post(
        url=f"{self.base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "deepseek-reasoner",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_schema", "json_schema": ESG_REPORT_SCHEMA},
            "stream": True,  # 流式响应
            "temperature": 0.3
        },
        timeout=httpx.Timeout(10.0, read=600.0)  # 读取超时 600 秒
    )
    
    # 流式接收响应
    content_parts = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            chunk = json.loads(line[6:])
            delta = chunk["choices"][0]["delta"]
            if "content" in delta:
                content_parts.append(delta["content"])
    
    final_content = "".join(content_parts)
    return extract_json(final_content)
```

#### LLM 返回的报告结构

```json
{
    "executive_summary": "Tesla Inc. 在碳排放管理方面表现突出，2024 年 Scope 1 排放下降 12%...",
    "environment": {
        "title": "Environment",
        "summary": "环境维度有 5 条证据支持，重点关注碳排放和可再生能源...",
        "findings": [
            "Scope 1 排放下降 12%，达到 120,000 tCO2e",
            "可再生能源装机容量 250 MW",
            "水资源消耗下降 8%"
        ],
        "risks": [
            "Scope 3 排放数据披露不完整",
            "生物多样性相关指标较少"
        ],
        "opportunities": [
            "扩大太阳能项目投资",
            "推动供应链减排"
        ],
        "evidence": [...]
    },
    "social": {
        "title": "Social",
        "summary": "社会维度证据较少，主要关注供应链管理...",
        "findings": ["供应链碳足迹追踪系统上线"],
        "risks": ["员工多样性指标披露不足"],
        "opportunities": ["加强员工 ESG 培训"],
        "evidence": [...]
    },
    "governance": {
        "title": "Governance",
        "summary": "治理维度有 2 条证据，重点是董事会对气候风险的监督...",
        "findings": [
            "董事会每季度审查气候风险",
            "ESG 委员会独立运作"
        ],
        "risks": ["气候风险量化模型待完善"],
        "opportunities": ["引入外部气候顾问"],
        "evidence": [...]
    },
    "compliance_alignment": {...},
    "confidence_assessment": {...},
    "next_steps": [
        "Review cited evidence against full source context",
        "Add more TCFD-specific climate risk disclosures",
        "Supplement Scope 3 emissions data"
    ],
    "agent_trace": [...]
}
```

---

## 核心技术详解

### 1. 查询增强技术

#### 两层增强策略

| 层级 | 函数 | 作用 | 示例 |
|-----|------|------|------|
| **第 1 层** | `enrich_query()` | 在查询末尾附加同义词 | `"碳排放管理"` → `"碳排放管理 carbon emissions GHG"` |
| **第 2 层** | `expand_query()` | 生成同义词替换变体 | `"碳排放管理"` → `["GHG管理", "温室气体管理"]` |

#### ESG 同义词词典

```python
# 文件: src/esg_rag/query_expansion.py (line 5-42)

ESG_SYNONYMS: dict[str, list[str]] = {
    # 环境 (Environment)
    "carbon": ["GHG", "greenhouse gas", "CO2", "carbon dioxide"],
    "emissions": ["GHG emissions", "carbon footprint", "Scope 1", "Scope 2", "Scope 3"],
    "climate": ["global warming", "climate change", "climate risk", "climate action"],
    "energy": ["renewable energy", "energy consumption", "energy efficiency", "power"],
    "water": ["water consumption", "water management", "water stewardship", "wastewater"],
    "waste": ["waste management", "recycling", "circular economy", "hazardous waste"],
    
    # 社会 (Social)
    "diversity": ["DEI", "inclusion", "gender equity", "equal opportunity"],
    "safety": ["health and safety", "occupational safety", "workplace safety", "OHS"],
    "employee": ["workforce", "human capital", "staff", "personnel", "labor"],
    
    # 治理 (Governance)
    "governance": ["corporate governance", "board oversight", "accountability"],
    "board": ["board of directors", "independent directors", "board composition"],
    "ethics": ["business ethics", "code of conduct", "anti-corruption", "integrity"],
    
    # 中文术语
    "碳排放": ["carbon emissions", "温室气体", "GHG", "碳足迹"],
    "环境": ["environment", "environmental", "环保", "生态"],
    "社会": ["social", "社会责任", "CSR"],
    "治理": ["governance", "公司治理", "董事会"],
    "员工": ["employee", "workforce", "人力资源", "劳动力"],
    "安全": ["safety", "安全管理", "职业健康", "生产安全"],
    # ... 共 42 组同义词
}
```

---

### 2. Reranking 算法

#### 评分公式

```
final_score = vector_score + keyword_boost + time_boost

其中:
  keyword_boost = keyword_overlap * 0.15
  time_boost = -0.01 * (current_year - document_year)
```

#### 权重分配

| 因子 | 权重 | 说明 |
|-----|------|------|
| **向量相似度** | 基准分数 | 语义匹配程度 (0.0-1.0) |
| **关键词重叠** | +15% | 查询词在结果中的覆盖率 |
| **时间加权** | -1%/年 | 优先返回新文档 |

#### 去重策略

- 文本归一化：去除多余空格、转小写
- 相同文本只保留最高分
- 基于 `chunk_id` 的最终去重

---

### 3. Multi-Agent 协同机制

#### Agent 执行顺序

```
PlannerAgent (查询拆分)
    ↓
RetrievalAgent (多轮检索) — 耗时最长 (150-300ms)
    ↓
EvidenceFusionAgent (标签分类) ← 规则处理，极快
    ↓
VerificationAgent (质量检查) ← 规则处理，极快
    ↓
ComplianceAgent + ConfidenceAgent (并行) ← 规则处理，极快
    ↓
TraceAgent (日志汇总) ← 数据汇总，极快
    ↓
ReportAgent (LLM 生成) — 耗时最长 (5-120秒)
```

#### Agent 间通信

| Agent | 输入类型 | 输出类型 |
|-------|---------|---------|
| PlannerAgent | `str` (用户查询) | `dict` (plan) |
| RetrievalAgent | `list[str]` (子查询) | `list[SearchResult]` |
| EvidenceFusionAgent | `list[SearchResult]` | `list[dict]` (带 tags) |
| VerificationAgent | `list[dict]` | `list[dict]` (带 notes) |
| ComplianceAgent | `list[dict]` | `dict` (框架对齐) |
| ConfidenceAgent | `list[dict]` | `dict` (置信度) |
| TraceAgent | `混合输入` | `list[dict]` (日志) |
| ReportAgent | `混合输入` | `dict` (报告) |

---

### 4. 向量检索优化

#### 候选集过采样

```python
top_k = 6
candidate_k = top_k * 4 = 24  # 检索 4 倍候选

# 原因:
# 1. 为 Reranking 提供足够的候选空间
# 2. 避免向量检索的边界效应
# 3. 提升最终结果的多样性
```

#### 多知识库并行检索

```python
all_results = []
for store in self.stores:  # 遍历所有知识库
    results = store.search(query_vector, top_k=24)
    all_results.extend(results)

# 如果有 3 个知识库，合并后有 72 个候选
# Reranking 后返回 top_6
```

---

## 性能数据

### 一次完整分析的耗时分布

| 阶段 | 耗时 | 占比 | 说明 |
|-----|------|------|------|
| PlannerAgent | <1 ms | 0.001% | 纯规则，极快 |
| RetrievalAgent (15 轮) | 150-300 ms | 0.5% | 15 次 embedding + 15 次向量检索 |
| EvidenceFusionAgent | <5 ms | 0.01% | 规则匹配 |
| VerificationAgent | <5 ms | 0.01% | 规则检查 |
| ComplianceAgent | <5 ms | 0.01% | 规则评估 |
| ConfidenceAgent | <1 ms | 0.001% | 数值计算 |
| TraceAgent | <1 ms | 0.001% | 数据汇总 |
| **ReportAgent (LLM)** | **5-120 秒** | **99%+** | DeepSeek Reasoner 的思考时间 |
| **总计** | **5-120 秒** | 100% | **主要瓶颈在 LLM** |

### 单次查询（Query）的耗时

| 阶段 | 耗时 |
|-----|------|
| 查询增强 | <1 ms |
| 向量化查询 | 10-20 ms |
| 向量检索 | 15-25 ms |
| Reranking | 5-10 ms |
| **总计** | **30-56 ms** |

---

## 常见问题

### Q1: 为什么要多轮检索？

**A**: 单次检索可能漏掉重要证据：

- ❌ **同义词问题** — 查询 "碳排放"，文档中使用 "GHG"
- ❌ **表述差异** — 查询 "员工安全"，文档中是 "职业健康"
- ❌ **跨语言** — 中文查询，英文文档

多轮检索通过查询扩展解决这些问题，提升召回率。

---

### Q2: Reranking 的关键词加分会不会影响语义检索？

**A**: 不会，关键词加分权重仅 **15%**，向量分数仍占主导。

**示例**：

| Chunk | 向量分数 | 关键词加分 | 最终分数 |
|-------|---------|-----------|---------|
| A | 0.90 | +0.00 | 0.90 |
| B | 0.70 | +0.15 | 0.85 |

即使 Chunk B 关键词全部匹配（+0.15），仍然低于语义更相关的 Chunk A。

---

### Q3: 为什么 LLM 这么慢？

**A**: DeepSeek Reasoner 是推理模型，会进行长时间思考（5-120 秒）：

- ✅ 分析所有证据
- ✅ 生成结构化报告
- ✅ 确保逻辑一致性

**优化建议**：

1. 使用更快的模型（例如 `deepseek-chat`）— 3-5 秒
2. 减少证据数量（`top_k=4` 而非 8）
3. 启用流式响应（前端实时显示）

---

### Q4: 如何提升检索召回率？

**方法 1: 增加候选集**

```python
# .env
RETRIEVAL_CANDIDATE_MULTIPLIER=6  # 从 4 倍提升到 6 倍
```

**方法 2: 扩展同义词词典**

```python
# src/esg_rag/query_expansion.py
ESG_SYNONYMS["新增术语"] = ["同义词1", "同义词2"]
```

**方法 3: 使用更强的 Embedding 模型**

```python
# .env
EMBEDDING_BACKEND=local
LOCAL_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5  # 768 维，更强语义理解
```

---

### Q5: 如何查看 Multi-Agent 的执行日志？

**A**: 分析返回的 `agent_trace` 字段：

```python
response = requests.post("/analyze", json={...})
print(response.json()["agent_trace"])
```

**输出示例**：

```json
[
    {
        "agent": "planner",
        "output": {"sub_queries": [...], "keywords": [...]}
    },
    {
        "agent": "retrieval_fusion",
        "retrieved_evidence": 8,
        "tag_breakdown": {"environment": 5, "governance": 2, "social": 1}
    },
    {
        "agent": "confidence",
        "output": {"level": "high", "score": 0.901}
    }
]
```

---

## 总结

### 简单查询（Query）

```
用户查询 → 查询增强 → 向量化 → 向量检索 → Reranking → 返回结果
(1 个查询，耗时 ~50ms)
```

**特点**：
- ✅ 快速（<100ms）
- ✅ 返回原始检索结果
- ✅ 适合快速查找文档片段

---

### 完整分析（Analyze）

```
用户查询 → PlannerAgent (拆分为 5 个子查询)
         → RetrievalAgent (查询扩展 → 15 轮检索 → 合并去重)
         → EvidenceFusionAgent (ESG 标签分类)
         → VerificationAgent (质量检查)
         → ComplianceAgent + ConfidenceAgent (框架对齐 + 置信度评分)
         → TraceAgent (汇总日志)
         → ReportAgent (LLM 生成报告)
         → 返回结构化报告

(8 个 Agent 串行执行，耗时 5-120 秒，主要等待 LLM)
```

**特点**：
- ✅ 全面（覆盖 ESG 三大维度）
- ✅ 专业（结构化报告 + 框架对齐评估）
- ✅ 可追溯（完整的执行日志）
- ⚠️ 较慢（主要等待 LLM）

---

### 核心优势

| 优势 | 说明 |
|-----|------|
| **多轮检索** | 提升召回率，不会漏掉重要证据 |
| **查询扩展** | 处理同义词和不同表述，支持跨语言 |
| **Reranking** | 综合语义、关键词、时间等多个因素 |
| **Multi-Agent** | 结构化处理，每个环节可独立优化 |
| **可追溯** | 完整的执行日志（agent_trace） |

---

**文档结束**
