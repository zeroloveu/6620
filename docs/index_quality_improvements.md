# ESG RAG 索引质量提升方案

## 当前系统评估

### 现有优势
✅ **基础架构扎实**
- 使用 sentence-transformers（all-MiniLM-L6-v2）提供语义理解
- 支持多种文件类型（PDF、DOCX、TXT、JSON、MD）
- 滑动窗口切分 + 章节感知
- Metadata 完整可追溯

✅ **已有优化**
- Reranking：关键词重叠加权（+0.2）
- 去重：基于文本规范化
- 候选扩展：检索 `top_k × 4` 候选后筛选

### 当前局限

| 维度 | 现状 | 影响 |
|------|------|------|
| **Embedding 模型** | all-MiniLM-L6-v2（384 维） | 通用模型，ESG 领域特化不足 |
| **切分策略** | 固定 900 字符滑动窗口 | 可能切断语义单元（表格、列表） |
| **向量检索** | 纯语义相似度 | 缺少关键词精确匹配 |
| **索引结构** | 单层 flat 索引 | 无层次结构，长文档召回困难 |
| **Reranking** | 简单关键词重叠 | 未使用 Cross-Encoder 深度排序 |
| **元数据利用** | 仅用于展示 | 未用于检索过滤和加权 |

---

## 提升方案（按优先级排序）

### 🎯 优先级 1：切换更强的 Embedding 模型

#### 问题
- `all-MiniLM-L6-v2` 是通用英文模型，对 ESG 专业术语（如"Scope 1 emissions"、"materiality assessment"）理解不足
- 如果文档中有中文，效果更差

#### 解决方案

**方案 A：多语言 ESG 增强模型**
```python
# 修改 .env
LOCAL_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5  # 英文 ESG 文档
# 或
LOCAL_EMBEDDING_MODEL=BAAI/bge-base-zh-v1.5  # 中文 ESG 文档
```

**模型对比**：

| 模型 | 维度 | 参数量 | ESG 适配度 | 速度 | 推荐场景 |
|------|------|--------|-----------|------|---------|
| all-MiniLM-L6-v2 | 384 | 23M | ⭐⭐ | 快 | 当前默认 |
| bge-base-en-v1.5 | 768 | 109M | ⭐⭐⭐⭐ | 中 | 英文 ESG 报告 |
| bge-large-en-v1.5 | 1024 | 335M | ⭐⭐⭐⭐⭐ | 慢（需 GPU） | 高质量检索 |
| bge-base-zh-v1.5 | 768 | 102M | ⭐⭐⭐⭐ | 中 | 中文 ESG 报告 |
| e5-large-v2 | 1024 | 335M | ⭐⭐⭐⭐ | 慢 | 多任务通用 |

**实施步骤**：
```bash
# 1. 更新配置
echo "LOCAL_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5" >> .env

# 2. 重建索引（会自动下载新模型）
curl -X POST http://localhost:8001/kb/{kb_id}/index

# 3. 验证效果（对比查询结果）
```

**预期提升**：
- 检索准确率 +15~25%
- 对专业术语的召回率显著提升

**成本**：
- CPU 推理速度减半（10 句/秒 → 5 句/秒）
- 内存占用 +300MB
- 磁盘占用（embeddings.npy）增加 2x

---

### 🎯 优先级 2：混合检索（Semantic + BM25）

#### 问题
当前只用向量检索，对**精确关键词匹配**不敏感。

**示例**：
- 用户查询："GreenTech Scope 1 emissions 2024"
- 期望：包含准确年份和公司名的结果
- 现状：可能返回其他公司或年份的结果（语义相似）

#### 解决方案

添加 BM25 稀疏检索，与向量检索结果融合。

**代码实现**（新增 `HybridRetriever`）：

```python
# src/esg_rag/hybrid_retrieval.py (新文件)
from rank_bm25 import BM25Okapi
import numpy as np

class HybridRetriever:
    def __init__(self, vector_store, chunks, alpha=0.7):
        """
        alpha: 向量权重（1-alpha 为 BM25 权重）
        推荐 0.7（语义为主，关键词为辅）
        """
        self.vector_store = vector_store
        self.chunks = chunks
        self.alpha = alpha
        
        # 构建 BM25 索引
        tokenized_corpus = [self._tokenize(c.text) for c in chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)
    
    def search(self, query: str, query_vector: np.ndarray, top_k: int = 6):
        # 1. 向量检索
        vector_results = self.vector_store.search(query_vector, top_k=top_k * 2)
        vector_scores = {r.chunk_id: r.score for r in vector_results}
        
        # 2. BM25 检索
        tokenized_query = self._tokenize(query)
        bm25_scores = self.bm25.get_scores(tokenized_query)
        bm25_normalized = (bm25_scores - bm25_scores.min()) / (bm25_scores.max() - bm25_scores.min() + 1e-9)
        
        # 3. 融合分数（归一化后加权）
        all_chunk_ids = set(vector_scores.keys())
        hybrid_scores = {}
        
        for idx, chunk in enumerate(self.chunks):
            if chunk.chunk_id not in all_chunk_ids:
                continue
            v_score = vector_scores.get(chunk.chunk_id, 0.0)
            b_score = float(bm25_normalized[idx])
            hybrid_scores[chunk.chunk_id] = self.alpha * v_score + (1 - self.alpha) * b_score
        
        # 4. 排序返回
        sorted_ids = sorted(hybrid_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            SearchResult(
                chunk_id=cid,
                score=score,
                text=next(c.text for c in self.chunks if c.chunk_id == cid),
                metadata=next(c.metadata for c in self.chunks if c.chunk_id == cid)
            )
            for cid, score in sorted_ids
        ]
    
    def _tokenize(self, text):
        return text.lower().split()
```

**依赖安装**：
```bash
pip install rank-bm25
```

**预期提升**：
- 精确匹配查询（公司名、年份、指标名）召回率 +30%
- 平衡语义理解和关键词匹配

**成本**：
- 索引构建时间 +10%（构建 BM25 索引）
- 内存占用 +50MB（BM25 倒排索引）

---

### 🎯 优先级 3：改进切分策略（语义感知）

#### 问题
当前切分逻辑：
1. 按标题分段（正则匹配大写字母）
2. 900 字符滑动窗口
3. 在句子边界切分

**局限**：
- 表格可能被切断（跨窗口）
- 列表项可能分散在多个 chunk
- 没有利用文档结构（章节层次）

#### 解决方案

**方案 A：表格和列表专用处理**

```python
# src/esg_rag/chunking.py 增强版
def _chunk_document(self, document: Document) -> list[Chunk]:
    normalized = self._normalize(document.text)
    
    # 1. 识别特殊结构
    tables = self._extract_tables(normalized)
    lists = self._extract_lists(normalized)
    
    # 2. 移除特殊结构，切分普通文本
    text_only = self._remove_structures(normalized, tables + lists)
    sections = self._split_sections(text_only)
    chunks = []
    
    # 3. 普通文本切分
    for section in sections:
        chunks.extend(self._sliding_windows(section))
    
    # 4. 表格和列表单独成块
    for table in tables:
        if len(table) <= self.chunk_size * 1.5:  # 短表格独立
            chunks.append(table)
        else:  # 长表格按行切分
            chunks.extend(self._split_table(table))
    
    for lst in lists:
        if len(lst) <= self.chunk_size:
            chunks.append(lst)
        else:
            chunks.extend(self._split_list(lst))
    
    return chunks

def _extract_tables(self, text: str) -> list[str]:
    # 识别 markdown 表格或制表符对齐的表格
    pattern = r"(\|.+\|[\r\n]+\|[-| ]+\|[\r\n]+(?:\|.+\|[\r\n]+)+)"
    return re.findall(pattern, text)

def _extract_lists(self, text: str) -> list[str]:
    # 识别连续的列表项（-、*、数字）
    pattern = r"(?:(?:^|\n)(?:[-*]|\d+\.) .+[\r\n]*)+"
    return re.findall(pattern, text, re.MULTILINE)
```

**预期提升**：
- 表格数据召回准确率 +40%
- 列表项完整性保持率 +30%

**方案 B：使用 LlamaIndex / LangChain 的 Semantic Chunker**

```python
from langchain_experimental.text_splitter import SemanticChunker

chunker = SemanticChunker(
    embeddings=self.embedding_provider,
    breakpoint_threshold_type="percentile",  # 按语义相似度分段
    breakpoint_threshold_amount=0.8
)
```

**优点**：
- 自动识别语义边界（不依赖规则）
- 适应各种文档格式

**缺点**：
- 需要为切分过程多次调用 embedding（慢 3~5x）

---

### 🎯 优先级 4：Cross-Encoder Reranking

#### 问题
当前 reranking 只用简单的关键词重叠，无法理解：
- 同义词（"reduce" vs "decrease"）
- 否定（"did not achieve" 应该排低）
- 上下文相关性

#### 解决方案

在向量检索后，使用 Cross-Encoder 模型重排序 Top-K 候选。

**代码实现**：

```python
# src/esg_rag/reranker.py (新文件)
from sentence_transformers import CrossEncoder

class CrossEncoderReranker:
    def __init__(self, model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = CrossEncoder(model_name)
    
    def rerank(self, query: str, results: list[SearchResult], top_k: int = 6):
        if not results:
            return []
        
        # 1. 准备 (query, passage) pairs
        pairs = [(query, r.text) for r in results]
        
        # 2. 计算相关性分数
        scores = self.model.predict(pairs)
        
        # 3. 排序
        ranked = sorted(
            zip(results, scores),
            key=lambda x: x[1],
            reverse=True
        )
        
        # 4. 返回 Top-K
        return [
            SearchResult(
                chunk_id=r.chunk_id,
                score=float(score),
                text=r.text,
                metadata=r.metadata
            )
            for r, score in ranked[:top_k]
        ]
```

**集成到 Pipeline**：

```python
# src/esg_rag/pipeline.py 修改
def search(self, query: str, top_k: int = 6):
    # 1. 向量检索（扩大候选池）
    candidates = self.vector_store.search(query_vector, top_k=top_k * 3)
    
    # 2. Cross-Encoder 重排序
    reranker = CrossEncoderReranker()
    return reranker.rerank(query, candidates, top_k=top_k)
```

**预期提升**：
- 复杂查询（长句、多条件）准确率 +20~30%
- Top-3 命中率显著提升

**成本**：
- 查询延迟 +200~500ms（取决于候选数量）
- 内存 +150MB（加载 Cross-Encoder 模型）

**推荐模型**：

| 模型 | 速度 | 质量 | 适用场景 |
|------|------|------|---------|
| ms-marco-MiniLM-L-6-v2 | 快 | ⭐⭐⭐ | 通用检索 |
| bge-reranker-base | 中 | ⭐⭐⭐⭐ | 多语言 |
| bge-reranker-large | 慢 | ⭐⭐⭐⭐⭐ | 高质量场景 |

---

### 🎯 优先级 5：Metadata 过滤和加权

#### 问题
当前 metadata 只用于显示，未用于检索优化。

**示例 metadata**：
```json
{
  "source_name": "GreenTech_2024_Report.pdf",
  "page": 12,
  "section_index": 2,
  "source_type": "pdf"
}
```

#### 解决方案

**方案 A：时间衰减加权**

对于 ESG 报告，**最新数据更重要**。

```python
def _apply_temporal_boost(self, results: list[SearchResult]) -> list[SearchResult]:
    """根据文档年份提升新数据的权重"""
    for r in results:
        filename = r.metadata.get("source_name", "")
        # 提取年份（如 "GreenTech_2024_Report.pdf"）
        year_match = re.search(r"(20\d{2})", filename)
        if year_match:
            year = int(year_match.group(1))
            current_year = 2025
            age = current_year - year
            # 每年衰减 5%
            decay_factor = 0.95 ** age
            r.score *= decay_factor
    
    return sorted(results, key=lambda x: x.score, reverse=True)
```

**方案 B：文档类型加权**

优先返回正式报告，降低用户上传的临时文件权重。

```python
def _apply_source_boost(self, results: list[SearchResult]) -> list[SearchResult]:
    for r in results:
        source = r.metadata.get("source", "")
        # 正式报告（data/reports/）加权 +10%
        if "/reports/" in source:
            r.score *= 1.1
        # 用户上传（data/uploads/）降权 -5%
        elif "/uploads/" in source:
            r.score *= 0.95
    
    return sorted(results, key=lambda x: x.score, reverse=True)
```

**方案 C：章节过滤**

允许用户指定只搜索特定章节（如"只搜索环境章节"）。

```python
def search_with_filter(self, query: str, section_filter: str | None = None):
    results = self.vector_store.search(query_vector, top_k=100)
    
    if section_filter:
        # 根据 metadata.section_index 或文本内容过滤
        results = [
            r for r in results
            if section_filter.lower() in r.text[:200].lower()
        ]
    
    return results[:top_k]
```

**预期提升**：
- 时间相关查询（"2024 年排放数据"）准确率 +25%
- 减少过时或低质量文档的干扰

---

### 🎯 优先级 6：分层索引（Hierarchical Indexing）

#### 问题
当前所有 chunk 扁平存储，长文档（如 200 页 PDF）可能生成 500+ chunk，检索时：
- 噪音大（无关 chunk 也被检索）
- 缺少上下文（单个 chunk 可能语义不完整）

#### 解决方案

**两层索引结构**：

```
第 1 层：文档级摘要（Document Summary）
   ↓ 先检索最相关的文档
第 2 层：Chunk 级详细内容
   ↓ 只在相关文档内检索 chunk
```

**实现步骤**：

**步骤 1：生成文档摘要**

```python
def _generate_document_summary(self, document: Document) -> str:
    """为每个文档生成 200 字摘要（可用 LLM 或提取前 N 段）"""
    # 方案 A：简单截取前 1000 字符
    return document.text[:1000]
    
    # 方案 B：使用 LLM 总结
    # prompt = f"Summarize this ESG document in 200 words:\n{document.text[:5000]}"
    # return llm.generate(prompt)
```

**步骤 2：构建两层索引**

```python
# 第 1 层：文档摘要向量
doc_summaries = [self._generate_document_summary(doc) for doc in documents]
doc_embeddings = self.embedding_provider.embed_documents(doc_summaries)
self.doc_store.index(documents, doc_embeddings)

# 第 2 层：Chunk 向量（按文档分组存储）
for doc in documents:
    chunks = self.chunker.chunk_document(doc)
    chunk_embeddings = self.embedding_provider.embed_documents([c.text for c in chunks])
    self.chunk_stores[doc.id].index(chunks, chunk_embeddings)
```

**步骤 3：两阶段检索**

```python
def hierarchical_search(self, query: str, top_k_docs: int = 3, top_k_chunks: int = 6):
    # 1. 检索最相关的文档
    top_docs = self.doc_store.search(query_vector, top_k=top_k_docs)
    
    # 2. 只在这些文档内检索 chunk
    all_chunks = []
    for doc in top_docs:
        chunks = self.chunk_stores[doc.id].search(query_vector, top_k=top_k_chunks // top_k_docs)
        all_chunks.extend(chunks)
    
    # 3. 跨文档排序
    return sorted(all_chunks, key=lambda x: x.score, reverse=True)[:top_k_chunks]
```

**预期提升**：
- 长文档检索准确率 +20~30%
- 检索速度提升 2~3x（候选池缩小）
- 减少无关文档的干扰

**成本**：
- 索引存储增加 ~10%（文档摘要向量）
- 实现复杂度提升

---

### 🎯 优先级 7：查询扩展（Query Expansion）

#### 问题
用户查询可能：
- 过于简短（如"碳排放"）
- 使用非标准术语（如"温室气体" vs "GHG"）
- 缺少上下文

#### 解决方案

**方案 A：同义词扩展**

```python
ESG_SYNONYMS = {
    "carbon emissions": ["GHG emissions", "greenhouse gas", "CO2 emissions", "Scope 1", "Scope 2"],
    "diversity": ["inclusion", "gender equity", "equal opportunity", "DEI"],
    "governance": ["board oversight", "corporate governance", "risk management", "compliance"],
    # ... 更多
}

def expand_query(self, query: str) -> list[str]:
    """将原始查询扩展为多个变体"""
    expanded = [query]
    for term, synonyms in ESG_SYNONYMS.items():
        if term in query.lower():
            for syn in synonyms:
                expanded.append(query.replace(term, syn))
    return expanded
```

**方案 B：使用 LLM 生成查询变体**

```python
def llm_expand_query(self, query: str) -> list[str]:
    prompt = f"""
    Generate 3 alternative phrasings of this ESG query:
    "{query}"
    
    Output format (JSON):
    ["query1", "query2", "query3"]
    """
    return llm.generate(prompt)
```

**方案 C：伪相关反馈（PRF）**

```python
def pseudo_relevance_feedback(self, query: str, initial_top_k: int = 5):
    # 1. 初次检索
    initial_results = self.search(query, top_k=initial_top_k)
    
    # 2. 提取高频词作为查询扩展
    top_texts = " ".join([r.text for r in initial_results[:3]])
    keywords = self._extract_keywords(top_texts, limit=5)
    
    # 3. 扩展查询
    expanded_query = f"{query} {' '.join(keywords)}"
    
    # 4. 二次检索
    return self.search(expanded_query, top_k=6)
```

**预期提升**：
- 简短查询召回率 +15~20%
- 非标准术语查询成功率提升

---

### 🎯 优先级 8：多模态索引（图表识别）

#### 问题
ESG 报告中包含大量图表（饼图、柱状图、趋势图），当前系统只能识别文字，图表中的关键数据会丢失。

**示例**：
- 图表：2020-2024 年碳排放趋势柱状图
- 当前处理：跳过（无法提取）
- 理想处理：识别为文本"2020: 150吨, 2021: 140吨, 2022: 130吨..."

#### 解决方案

**方案 A：OCR 提取图表文本**

```python
# 依赖：pytesseract + opencv
from PIL import Image
import pytesseract

def _extract_chart_text(self, image: Image) -> str:
    """对图表区域进行 OCR"""
    text = pytesseract.image_to_string(image, lang='eng+chi_sim')
    return text.strip()
```

**方案 B：使用 LLM Vision 理解图表**

```python
# 使用 GPT-4 Vision / Claude 3.5 Sonnet
def _understand_chart(self, image_base64: str) -> str:
    prompt = """
    Describe this ESG chart in detail:
    1. What type of chart is it?
    2. What metrics are shown?
    3. What are the key values and trends?
    
    Output structured data.
    """
    return llm_vision.generate(prompt, image=image_base64)
```

**集成到 DocumentLoader**：

```python
def _load_pdf(self, path: Path) -> list[Document]:
    reader = PdfReader(str(path))
    documents = []
    
    for page_num, page in enumerate(reader.pages):
        # 提取文本
        text = page.extract_text()
        
        # 提取图片（chart detection）
        for image in page.images:
            chart_text = self._extract_chart_text(image)
            text += f"\n[Chart: {chart_text}]"
        
        documents.append(Document(text=text, metadata={...}))
    
    return documents
```

**预期提升**：
- 图表数据检索成功率从 0% → 60~80%
- 完整覆盖 ESG 报告的数值披露

**成本**：
- OCR：轻量，CPU 可运行
- LLM Vision：每张图 ~$0.01（GPT-4 Vision）

---

## 实施优先级总结

### 快速见效（1~2 天实现）

| 提升点 | 难度 | 效果 | 成本 |
|-------|------|------|------|
| **1. 切换 bge-base 模型** | ⭐ | +20% | 内存 +300MB |
| **2. Metadata 时间加权** | ⭐ | +10% | 无 |
| **3. 查询扩展（同义词）** | ⭐ | +15% | 无 |

### 中期优化（1 周实现）

| 提升点 | 难度 | 效果 | 成本 |
|-------|------|------|------|
| **4. 混合检索（Semantic + BM25）** | ⭐⭐ | +25% | 内存 +50MB |
| **5. Cross-Encoder Reranking** | ⭐⭐ | +25% | 查询延迟 +300ms |
| **6. 改进切分（表格/列表）** | ⭐⭐ | +20% | 无 |

### 长期增强（2~4 周实现）

| 提升点 | 难度 | 效果 | 成本 |
|-------|------|------|------|
| **7. 分层索引** | ⭐⭐⭐ | +30% | 索引存储 +10% |
| **8. 多模态索引（图表 OCR）** | ⭐⭐⭐ | +50%（图表数据） | LLM Vision API 费用 |

---

## 立即可实施的"快速胜利"方案

### 方案 1：切换到 bge-base-en-v1.5（5 分钟）

```bash
# 1. 修改 .env
echo "LOCAL_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5" >> .env

# 2. 重启服务（会自动下载新模型）
docker compose restart

# 3. 重新索引现有知识库
curl -X POST http://localhost:8001/kb/{kb_id}/index
```

### 方案 2：添加时间衰减加权（30 分钟）

修改 `src/esg_rag/pipeline.py` 的 `_rerank_results` 方法：

```python
def _rerank_results(self, query: str, results: list[SearchResult], top_k: int):
    # ... 现有逻辑 ...
    
    # 新增：时间衰减
    for result in results:
        filename = result.metadata.get("source_name", "")
        year_match = re.search(r"(20\d{2})", filename)
        if year_match:
            year = int(year_match.group(1))
            age = 2025 - year
            result.score *= (0.95 ** age)  # 每年衰减 5%
    
    return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]
```

### 方案 3：同义词扩展（1 小时）

创建 `src/esg_rag/query_expansion.py`：

```python
ESG_SYNONYMS = {
    "carbon": ["GHG", "CO2", "emissions", "greenhouse gas"],
    "diversity": ["DEI", "inclusion", "gender equity"],
    "governance": ["board", "oversight", "compliance", "risk management"],
    # 可继续扩展...
}

def expand_query(query: str) -> list[str]:
    queries = [query]
    for term, synonyms in ESG_SYNONYMS.items():
        if term.lower() in query.lower():
            for syn in synonyms:
                queries.append(query.lower().replace(term, syn))
    return queries
```

集成到 PlannerAgent 的 `sub_queries` 生成逻辑中。

---

## 性能 vs 质量权衡

| 优化方向 | 检索质量提升 | 查询延迟增加 | 内存占用增加 | 推荐场景 |
|---------|------------|------------|------------|---------|
| 更强 Embedding 模型 | +++++ | + | ++ | 高质量检索优先 |
| 混合检索 | ++++ | ++ | + | 关键词查询多 |
| Cross-Encoder | ++++ | +++ | ++ | 高精度需求 |
| 分层索引 | +++ | - | + | 长文档多 |
| 查询扩展 | +++ | + | 无 | 简短查询多 |
| 时间加权 | ++ | 无 | 无 | 报告更新频繁 |

**推荐组合**（平衡方案）：
```
bge-base-en-v1.5 + 混合检索 + 时间加权
→ 质量提升 ~40%，延迟增加 ~200ms
```

**极致质量方案**：
```
bge-large-en-v1.5 + 混合检索 + Cross-Encoder + 分层索引
→ 质量提升 ~70%，延迟增加 ~800ms，需要 GPU
```

---

## 评估和监控

### 关键指标

1. **召回率（Recall@K）**：Top-K 结果中有多少是真正相关的
2. **准确率（Precision@K）**：相关结果占 Top-K 的比例
3. **MRR（Mean Reciprocal Rank）**：第一个相关结果的平均排名
4. **查询延迟**：从查询到返回结果的时间

### 测试集构建

```python
# 构建 ESG 专用测试集
test_queries = [
    ("What are GreenTech's Scope 1 emissions in 2024?", "expected_chunk_ids"),
    ("Does the company have a diversity policy?", "expected_chunk_ids"),
    # ... 20~50 个典型查询
]

def evaluate_retrieval(queries, top_k=6):
    recall_sum = 0
    for query, expected_ids in queries:
        results = pipeline.query(query, top_k=top_k)
        retrieved_ids = {r.chunk_id for r in results}
        recall = len(retrieved_ids & set(expected_ids)) / len(expected_ids)
        recall_sum += recall
    
    return recall_sum / len(queries)
```

### A/B 测试

```python
# 对比两种配置
config_a = {"model": "all-MiniLM-L6-v2", "reranking": False}
config_b = {"model": "bge-base-en-v1.5", "reranking": True}

results_a = evaluate_retrieval(test_queries, config=config_a)
results_b = evaluate_retrieval(test_queries, config=config_b)

print(f"Config A Recall@6: {results_a:.3f}")
print(f"Config B Recall@6: {results_b:.3f}")
print(f"Improvement: {(results_b - results_a) / results_a * 100:.1f}%")
```

---

## 总结

当前系统已有**良好的基础架构**，通过以下提升点可以显著改进索引质量：

### 立即实施（效果/成本最优）
1. ✅ 切换到 bge-base-en-v1.5
2. ✅ 添加时间衰减加权
3. ✅ 同义词查询扩展

**预期总提升**：~40%，实施时间 < 2 小时

### 中期优化（质量显著提升）
4. 混合检索（Semantic + BM25）
5. Cross-Encoder Reranking
6. 改进切分策略（表格/列表）

**预期总提升**：~70%，实施时间 1~2 周

### 长期增强（系统级升级）
7. 分层索引
8. 多模态索引（图表 OCR）

**预期总提升**：~100%（翻倍），实施时间 1 个月

**建议路线图**：
```
Week 1: 快速胜利方案（bge + 时间加权 + 同义词）
Week 2-3: 混合检索 + Cross-Encoder
Week 4-6: 分层索引
Week 8+: 多模态索引（根据需求）
```
