# ESG RAG 系统 — 文档处理完整流程详解

## 目录
1. [概述](#概述)
2. [整体架构图](#整体架构图)
3. [阶段一：文档上传与存储](#阶段一文档上传与存储)
4. [阶段二：文档加载与解析](#阶段二文档加载与解析)
5. [阶段三：文本分块（Chunking）](#阶段三文本分块chunking)
6. [阶段四：向量化（Embedding）](#阶段四向量化embedding)
7. [阶段五：向量存储与索引](#阶段五向量存储与索引)
8. [阶段六：检索与查询](#阶段六检索与查询)
9. [完整示例：从上传到检索](#完整示例从上传到检索)
10. [性能优化与最佳实践](#性能优化与最佳实践)
11. [故障排查指南](#故障排查指南)

---

## 概述

本系统采用 **RAG (Retrieval-Augmented Generation)** 架构，将用户上传的 ESG 文档转换为可检索的向量数据库。整个处理流程分为 **6 个核心阶段**，每个阶段都经过精心设计以确保数据质量和检索精度。

### 支持的文件格式
- **文本文件**: `.txt`, `.md` (Markdown)
- **PDF 文件**: `.pdf` (支持多页文档，自动合并碎片页)
- **Word 文档**: `.docx` (支持标题提取、表格识别)
- **JSON 数据**: `.json` (支持数组和对象)

### 核心设计原则
1. **结构化保留** — 保留文档的章节结构、标题层级
2. **元数据完整** — 记录文件来源、页码、章节索引
3. **语义连续性** — 使用滑动窗口和重叠区域避免语义断裂
4. **中英文兼容** — 针对中英文混合文档优化断句逻辑
5. **可追溯性** — 每个 chunk 都能追溯到原始文件和具体位置

---

## 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户上传文档                                   │
│          (Web UI / API / 文件系统扫描)                             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段 1: 文档上传与存储 (KnowledgeBaseManager)                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ • 生成唯一文档 ID                                              ││
│  │ • 保存原始文件到 storage/kbs/{kb_id}/files/                   ││
│  │ • 记录元数据到 docs.json (文件名、大小、类型、时间戳)            ││
│  └─────────────────────────────────────────────────────────────┘│
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段 2: 文档加载与解析 (DocumentLoader)                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ TXT/MD → 直接读取全文                                          ││
│  │ JSON   → 解析并格式化为文本                                     ││
│  │ PDF    → 逐页提取文本 + 合并碎片页                              ││
│  │ DOCX   → 提取段落、标题、表格 + 按章节分组                       ││
│  │                                                               ││
│  │ 输出: list[Document]                                           ││
│  │   ├─ text: 文档文本内容                                         ││
│  │   └─ metadata: {source, page, section_heading, ...}          ││
│  └─────────────────────────────────────────────────────────────┘│
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段 3: 文本分块 (ESGChunker)                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 1. 文本标准化 (去除多余空白、统一换行符)                         ││
│  │ 2. 章节切分 (识别标题: 大写、编号、Markdown、中文章节标记)        ││
│  │ 3. 表格独立提取 (避免表格被窗口截断)                            ││
│  │ 4. 滑动窗口切片                                                 ││
│  │    ├─ chunk_size: 900 字符                                    ││
│  │    ├─ chunk_overlap: 150 字符 (确保语义连续性)                 ││
│  │    └─ 智能断句 (优先在段落、句子边界切分)                       ││
│  │ 5. 标题注入 (为每个 chunk 添加所属章节标题)                     ││
│  │                                                               ││
│  │ 输出: list[Chunk]                                              ││
│  │   ├─ chunk_id: UUID                                           ││
│  │   ├─ text: "[章节标题] 文本内容..."                             ││
│  │   └─ metadata: {source, page, section_heading, section_index, window_index} ││
│  └─────────────────────────────────────────────────────────────┘│
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段 4: 向量化 (EmbeddingProvider)                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 方式 1: 本地模型 (sentence-transformers)                       ││
│  │   ├─ 模型: all-MiniLM-L6-v2                                   ││
│  │   ├─ 维度: 384                                                ││
│  │   ├─ 速度: ~1000 chunks/秒 (CPU)                              ││
│  │   └─ 成本: 免费                                                ││
│  │                                                               ││
│  │ 方式 2: OpenAI API                                             ││
│  │   ├─ 模型: text-embedding-3-small                             ││
│  │   ├─ 维度: 1536                                               ││
│  │   ├─ 速度: 受 API 限制                                         ││
│  │   └─ 成本: $0.0001/1K tokens                                  ││
│  │                                                               ││
│  │ 方式 3: 哈希向量 (HashingVectorizer) - 离线降级方案             ││
│  │                                                               ││
│  │ 输出: np.ndarray (shape: [num_chunks, embedding_dim])         ││
│  └─────────────────────────────────────────────────────────────┘│
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段 5: 向量存储与索引 (VectorStore)                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ SimpleVectorStore (默认):                                      ││
│  │   ├─ vectors.npy — NumPy 向量矩阵                             ││
│  │   ├─ chunks.json — Chunk 元数据 (文本、metadata)               ││
│  │   └─ state.joblib — 索引状态                                   ││
│  │                                                               ││
│  │ 可选后端:                                                      ││
│  │   ├─ ChromaDB — 持久化向量数据库                               ││
│  │   └─ Milvus — 企业级向量检索引擎                               ││
│  │                                                               ││
│  │ 存储位置: storage/kbs/{kb_id}/index/                           ││
│  └─────────────────────────────────────────────────────────────┘│
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段 6: 检索与查询 (Retriever + Multi-Agent Pipeline)             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 1. 查询扩展 (ESG 同义词替换)                                    ││
│  │    "carbon emissions" → ["GHG", "Scope 1", "carbon footprint"]││
│  │                                                               ││
│  │ 2. 向量检索 (余弦相似度)                                        ││
│  │    query_vector @ document_vectors → top_k 候选               ││
│  │                                                               ││
│  │ 3. Reranking (关键词重叠、时间加权、文本去重)                   ││
│  │                                                               ││
│  │ 4. Multi-Agent 处理                                            ││
│  │    ├─ EvidenceFusionAgent (ESG 标签分类)                      ││
│  │    ├─ VerificationAgent (质量检查)                             ││
│  │    ├─ ComplianceAgent (框架对齐)                               ││
│  │    └─ ConfidenceAgent (置信度评分)                             ││
│  │                                                               ││
│  │ 5. 报告生成 (LLM 或模板)                                        ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## 阶段一：文档上传与存储

### 1.1 触发方式

#### 方式 1: Web UI 上传
```javascript
// 用户在前端界面选择文件
const formData = new FormData();
formData.append('files', file);

// 发送到后端 API
fetch('/kb/{kb_id}/documents', {
    method: 'POST',
    body: formData
});
```

#### 方式 2: API 直接上传
```bash
curl -X POST http://localhost:8000/kb/{kb_id}/documents \
  -F "files=@report.pdf" \
  -F "files=@policy.docx"
```

#### 方式 3: 文件系统扫描
```python
# 系统自动扫描指定目录
pipeline.index_kb(
    files_dir=Path("./data/my_documents"),
    index_dir=Path("./storage/index")
)
```

---

### 1.2 文件存储流程

```python
# 位置: knowledge_base.py → KnowledgeBaseManager.add_documents()

def add_documents(self, kb_id: str, files: list[tuple[str, bytes]]) -> list[dict]:
    """
    为知识库添加文档
    
    参数:
        kb_id: 知识库 ID
        files: [(原始文件名, 文件内容字节), ...]
    
    返回:
        添加的文档元数据列表
    """
    
    # 1. 读取现有文档列表
    docs = self._read_json(self._docs_path(kb_id), [])
    
    # 2. 确保存储目录存在
    files_dir = self.files_dir(kb_id)  # storage/kbs/{kb_id}/files/
    files_dir.mkdir(parents=True, exist_ok=True)
    
    added = []
    for original_name, content in files:
        # 3. 生成唯一文档 ID (12位16进制)
        doc_id = uuid4().hex[:12]  # 例如: "a3f8c9e1b2d4"
        
        # 4. 构造存储文件名 (防止重名冲突)
        stored_name = f"{doc_id}_{original_name}"
        # 例如: "a3f8c9e1b2d4_tesla_esg_2024.pdf"
        
        # 5. 写入文件到磁盘
        (files_dir / stored_name).write_bytes(content)
        
        # 6. 记录文档元数据
        doc = {
            "id": doc_id,
            "original_name": original_name,
            "stored_name": stored_name,
            "file_size": len(content),
            "file_type": Path(original_name).suffix.lower().lstrip("."),
            "created_at": self._now()  # ISO 8601 时间戳
        }
        docs.append(doc)
        added.append(doc)
    
    # 7. 更新文档清单
    self._write_json(self._docs_path(kb_id), docs)
    
    # 8. 更新知识库的 updated_at 时间戳
    self._touch_updated(kb_id)
    
    return added
```

---

### 1.3 存储结构

```
storage/kbs/
├── a3f8c9e1b2d4/                    # 知识库 ID
│   ├── meta.json                    # 知识库元数据
│   ├── docs.json                    # 文档清单
│   ├── files/                       # 原始文件存储
│   │   ├── x1y2z3_report.pdf
│   │   ├── x4y5z6_policy.docx
│   │   └── x7y8z9_data.json
│   └── index/                       # 向量索引
│       ├── vectors.npy
│       ├── chunks.json
│       └── state.joblib
└── b5e9d7c2a1f3/                    # 另一个知识库
    └── ...
```

#### meta.json 示例
```json
{
  "id": "a3f8c9e1b2d4",
  "name": "Tesla ESG 分析库",
  "description": "包含 Tesla 公司的 ESG 报告、可持续发展报告等",
  "created_at": "2026-03-31T10:30:00+00:00",
  "updated_at": "2026-03-31T15:45:00+00:00"
}
```

#### docs.json 示例
```json
[
  {
    "id": "x1y2z3",
    "original_name": "tesla_esg_2024.pdf",
    "stored_name": "x1y2z3_tesla_esg_2024.pdf",
    "file_size": 2458624,
    "file_type": "pdf",
    "created_at": "2026-03-31T10:35:00+00:00"
  },
  {
    "id": "x4y5z6",
    "original_name": "diversity_policy.docx",
    "stored_name": "x4y5z6_diversity_policy.docx",
    "file_size": 153600,
    "file_type": "docx",
    "created_at": "2026-03-31T10:36:00+00:00"
  }
]
```

---

## 阶段二：文档加载与解析

### 2.1 DocumentLoader 核心逻辑

```python
# 位置: document_loader.py → DocumentLoader

class DocumentLoader:
    """
    支持的文件格式: .txt, .md, .pdf, .json, .docx
    """
    
    supported_extensions = {".txt", ".md", ".pdf", ".json", ".docx"}
    
    def load_directory(self, directory: Path) -> list[Document]:
        """
        扫描目录并加载所有支持的文档
        """
        documents = []
        
        # 递归扫描目录 (rglob 会递归搜索子目录)
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in self.supported_extensions:
                docs = self.load_file(path)
                if docs:
                    logger.info("加载了 %d 个文档片段: %s", len(docs), path.name)
                else:
                    logger.warning("无法提取内容: %s", path.name)
                documents.extend(docs)
        
        return documents
```

---

### 2.2 TXT / Markdown 处理

**特点**: 最简单的格式，直接读取全文。

```python
def _load_txt_md(path: Path) -> list[Document]:
    """
    TXT 和 Markdown 文件处理
    """
    return [
        Document(
            text=path.read_text(encoding="utf-8", errors="ignore"),
            metadata={
                "source": str(path),
                "source_name": path.name,
                "source_type": path.suffix.lower().lstrip(".")
            }
        )
    ]
```

**示例输入**: `report.md`
```markdown
# Tesla 2024 ESG Report

## Environmental Performance
Our Scope 1 emissions decreased by 12% in 2024...

## Social Impact
We employed 140,000 workers globally...
```

**输出**: 
```python
Document(
    text="# Tesla 2024 ESG Report\n\n## Environmental Performance\nOur Scope 1 emissions...",
    metadata={
        "source": "/path/to/report.md",
        "source_name": "report.md",
        "source_type": "md"
    }
)
```

---

### 2.3 JSON 处理

**特点**: 支持数组和对象，格式化为可读文本。

```python
def _load_json(path: Path) -> list[Document]:
    """
    JSON 文件处理
    
    支持两种格式:
    1. 对象: {key: value, ...}
    2. 数组: [{...}, {...}, ...]
    """
    payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    
    # 如果是数组，每个元素生成一个 Document
    if isinstance(payload, list):
        return [
            Document(
                text=json.dumps(item, ensure_ascii=False, indent=2),
                metadata={
                    **self._base_metadata(path),
                    "record_index": index  # 记录在数组中的位置
                }
            )
            for index, item in enumerate(payload)
        ]
    
    # 如果是对象，整体生成一个 Document
    return [
        Document(
            text=json.dumps(payload, ensure_ascii=False, indent=2),
            metadata=self._base_metadata(path)
        )
    ]
```

**示例输入**: `metrics.json`
```json
[
  {
    "year": 2024,
    "scope_1_emissions": 120000,
    "scope_2_emissions": 85000,
    "unit": "tCO2e"
  },
  {
    "year": 2023,
    "scope_1_emissions": 137000,
    "scope_2_emissions": 92000,
    "unit": "tCO2e"
  }
]
```

**输出**: 2 个 Document
```python
Document(
    text='{\n  "year": 2024,\n  "scope_1_emissions": 120000,\n  ...\n}',
    metadata={"source": "...", "source_name": "metrics.json", "record_index": 0}
)
Document(
    text='{\n  "year": 2023,\n  "scope_1_emissions": 137000,\n  ...\n}',
    metadata={"source": "...", "source_name": "metrics.json", "record_index": 1}
)
```

---

### 2.4 PDF 处理 ⭐ (核心功能)

**特点**: 
- 逐页提取文本
- **自动合并碎片页** (< 60 字符的页面)
- 保留页码信息

```python
_MIN_PAGE_CHARS = 60  # 少于 60 字符的页面视为碎片

def _load_pdf(path: Path) -> list[Document]:
    """
    PDF 文件处理
    
    核心优化: 
    1. 自动合并碎片页 (避免生成过多无意义的 Document)
    2. 保留完整的页码追溯信息
    """
    
    # 1. 安全检查: 跳过空文件
    if path.stat().st_size == 0:
        logger.warning("跳过空文件: %s", path.name)
        return []
    
    # 2. 尝试打开 PDF
    try:
        reader = PdfReader(str(path))
    except Exception:
        logger.exception("无法打开 PDF: %s", path.name)
        return []
    
    # 3. 初始化
    base = self._base_metadata(path)
    total_pages = len(reader.pages)
    documents = []
    carry = ""  # 用于累积碎片页的文本
    carry_start = None  # 碎片页的起始页码
    
    # 4. 逐页处理
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        
        if not text:
            continue  # 跳过空页
        
        # 5. 碎片页处理 (< 60 字符)
        if len(text) < _MIN_PAGE_CHARS:
            if carry_start is None:
                carry_start = page_number
            carry += ("\n" if carry else "") + text
            continue  # 继续累积
        
        # 6. 正常页面处理
        if carry:
            # 将累积的碎片合并到当前页
            text = carry + "\n" + text
            start_page = carry_start or page_number
            carry = ""
            carry_start = None
        else:
            start_page = page_number
        
        # 7. 生成 Document
        documents.append(Document(
            text=text,
            metadata={
                **base,
                "page": start_page,  # 起始页码
                "total_pages": total_pages
            }
        ))
    
    # 8. 处理末尾的碎片页
    if carry:
        if documents:
            # 合并到最后一个 Document
            documents[-1].text += "\n" + carry
        else:
            # 如果整个 PDF 都是碎片页，仍然保留
            documents.append(Document(
                text=carry,
                metadata={**base, "page": carry_start or 1, "total_pages": total_pages}
            ))
    
    return documents
```

**示例**: 假设 PDF 有 5 页

| 页码 | 字符数 | 处理方式 |
|-----|--------|---------|
| 1   | 1500   | 正常页 → Document 1 (page=1) |
| 2   | 45     | 碎片页 → 累积到 carry |
| 3   | 50     | 碎片页 → 继续累积 |
| 4   | 1200   | 正常页 → **合并** carry (页2-3) + 页4 → Document 2 (page=2) |
| 5   | 800    | 正常页 → Document 3 (page=5) |

**最终生成 3 个 Document**，而不是 5 个！

---

### 2.5 DOCX 处理 ⭐ (核心功能)

**特点**:
- **提取标题样式** (Heading 1-6, Title)
- **按章节分组**
- **表格识别** (转换为文本格式)
- **批量切片** (每 15 段文本生成一个 Document)

```python
def _load_docx(path: Path) -> list[Document]:
    """
    DOCX 文件处理
    
    核心优化:
    1. 识别 Word 标题样式 (Heading, Title)
    2. 按章节结构分组
    3. 为每个 Document 注入章节标题
    """
    from docx import Document as DocxDocument
    from docx.table import Table
    
    # 1. 安全检查
    if path.stat().st_size == 0:
        return []
    
    try:
        doc = DocxDocument(str(path))
    except Exception:
        logger.exception("无法打开 DOCX: %s", path.name)
        return []
    
    # 2. 按章节分组
    sections = []
    current_heading = None
    current_paras = []
    
    for element in doc.element.body:
        tag = element.tag.split("}")[-1]
        
        # 2.1 段落处理
        if tag == "p":
            from docx.text.paragraph import Paragraph
            para = Paragraph(element, doc)
            text = para.text.strip()
            
            if not text:
                continue
            
            # 检测标题样式
            style_name = (para.style.name or "").lower() if para.style else ""
            
            if "heading" in style_name or "title" in style_name:
                # 遇到新标题，保存之前的章节
                if current_paras:
                    sections.append((current_heading, current_paras))
                current_heading = text  # 更新当前标题
                current_paras = []
            else:
                current_paras.append(text)
        
        # 2.2 表格处理
        elif tag == "tbl":
            table = Table(element, doc)
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(" | ".join(cells))  # 转换为文本格式
            if rows:
                current_paras.append("\n".join(rows))
    
    # 保存最后一个章节
    if current_paras:
        sections.append((current_heading, current_paras))
    
    if not sections:
        return []
    
    # 3. 批量切片 (每 15 段生成一个 Document)
    documents = []
    chunk_size = 15
    
    for heading, paras in sections:
        for i in range(0, len(paras), chunk_size):
            batch = paras[i : i + chunk_size]
            
            text_parts = []
            if heading:
                text_parts.append(f"## {heading}")  # 标题前缀
            text_parts.extend(batch)
            
            text = "\n\n".join(text_parts)
            if text.strip():
                meta = {**base, "section_start": i}
                if heading:
                    meta["section_heading"] = heading
                documents.append(Document(text=text, metadata=meta))
    
    return documents
```

**示例输入**: `policy.docx`
```
[Heading 1] Environmental Policy

Our company is committed to reducing carbon emissions.
We have implemented renewable energy projects.

[Table]
Year | Emissions | Target
2023 | 150000    | 140000
2024 | 137000    | 130000

[Heading 1] Social Responsibility

We employ 10,000 workers globally.
```

**输出**: 2 个 Document
```python
Document(
    text="## Environmental Policy\n\nOur company is committed...\n\nYear | Emissions | Target\n2023 | 150000 | 140000\n...",
    metadata={"source": "...", "section_heading": "Environmental Policy", "section_start": 0}
)
Document(
    text="## Social Responsibility\n\nWe employ 10,000 workers...",
    metadata={"source": "...", "section_heading": "Social Responsibility", "section_start": 0}
)
```

---

### 2.6 Document 数据结构

```python
@dataclass
class Document:
    text: str  # 文档文本内容
    metadata: dict[str, Any]  # 元数据
```

**metadata 常见字段**:

| 字段 | 类型 | 说明 | 示例 |
|-----|------|------|------|
| `source` | str | 文件完整路径 | `/path/to/storage/kbs/abc/files/x1_report.pdf` |
| `source_name` | str | 文件名 | `report.pdf` |
| `source_type` | str | 文件类型 | `pdf`, `docx`, `txt`, `json` |
| `page` | int | PDF 页码 | `15` |
| `total_pages` | int | PDF 总页数 | `50` |
| `section_heading` | str | DOCX 章节标题 | `Environmental Performance` |
| `section_start` | int | DOCX 段落起始索引 | `0`, `15`, `30` |
| `record_index` | int | JSON 数组索引 | `0`, `1`, `2` |

---

## 阶段三：文本分块（Chunking）

### 3.1 为什么需要分块？

**问题**: 完整文档通常很长 (数千到数万字符)，直接向量化会导致:
1. **语义稀释** — 长文本的 embedding 无法精确表达局部语义
2. **检索不精确** — 用户查询"碳排放"，可能匹配到一个谈论多个主题的长文档，但相关内容只有一小段
3. **上下文超限** — LLM 的输入 token 有限制 (例如 GPT-4 的 8k/32k)

**解决方案**: 将文档切分为 **小而语义完整** 的 chunks，每个 chunk 独立向量化和检索。

---

### 3.2 ESGChunker 核心流程

```python
class ESGChunker:
    def __init__(self, chunk_size=900, chunk_overlap=150):
        """
        chunk_size: 每个 chunk 的最大字符数 (默认 900)
        chunk_overlap: 相邻 chunk 的重叠区域 (默认 150)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def _chunk_document(self, document: Document) -> list[Chunk]:
        """
        对单个 Document 进行分块
        
        流程:
        1. 文本标准化
        2. 章节切分
        3. 表格独立提取
        4. 滑动窗口切片
        5. 标题注入
        """
        
        # 步骤 1: 文本标准化
        normalized = self._normalize(document.text)
        
        # 步骤 2: 章节切分
        sections = self._split_sections(normalized)
        
        chunks = []
        for section_index, section in enumerate(sections):
            # 步骤 3: 提取章节标题
            heading = self._extract_heading(section)
            
            # 步骤 4: 分离表格和正文
            tables, prose = self._separate_tables(section)
            
            # 步骤 5: 表格独立成块
            for table in tables:
                prefix = f"[{heading}] " if heading else ""
                chunks.append(self._make_chunk(
                    f"{prefix}{table}",
                    document.metadata,
                    section_index,
                    0,
                    heading
                ))
            
            # 步骤 6: 正文滑动窗口切片
            windows = self._sliding_windows(prose)
            for window_index, window in enumerate(windows):
                # 步骤 7: 标题注入
                if heading and not window.startswith(heading):
                    window = f"[{heading}]\n{window}"
                
                chunks.append(self._make_chunk(
                    window,
                    document.metadata,
                    section_index,
                    window_index,
                    heading
                ))
        
        return chunks
```

---

### 3.3 步骤详解

#### 步骤 1: 文本标准化

**目的**: 清理不一致的空白字符和换行符。

```python
def _normalize(text: str) -> str:
    """
    文本标准化
    
    1. 将 \u00a0 (不间断空格) 替换为普通空格
    2. 统一换行符为 \n
    3. 压缩连续的空行 (3+ 空行 → 2 空行)
    """
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\r\n?", "\n", text)  # Windows/Mac → Unix
    text = re.sub(r"\n{3,}", "\n\n", text)  # 最多保留 2 个连续换行
    return text.strip()
```

**示例**:
```python
# 输入
"Line 1\r\n\r\n\r\n\r\nLine 2\u00a0\u00a0End"

# 输出
"Line 1\n\nLine 2  End"
```

---

#### 步骤 2: 章节切分 ⭐

**目的**: 识别文档的章节结构，避免跨章节切分。

```python
_SECTION_HEADING = re.compile(
    r"\n(?="
    r"(?:[A-Z][A-Z\s/&-]{3,})"                         # UPPERCASE HEADING
    r"|(?:[0-9]+(?:\.[0-9]+)*\.?\s+\S)"                # 1. or 1.2.3 Heading
    r"|(?:#{1,4}\s+\S)"                                 # Markdown # / ## / ### / ####
    r"|(?:第[一二三四五六七八九十百千\d]+[章节部分篇条])"  # Chinese chapter markers
    r"|(?:[一二三四五六七八九十]+[、.])"                 # Chinese numbered lists
    r")"
)

def _split_sections(text: str) -> list[str]:
    """
    按章节标题切分文档
    
    支持的标题格式:
    1. 全大写标题: "ENVIRONMENTAL PERFORMANCE"
    2. 编号标题: "1. Introduction", "2.3.1 Data Sources"
    3. Markdown 标题: "# Chapter 1", "## Section 1.1"
    4. 中文章节: "第一章 概述", "第二节 数据分析"
    5. 中文列表: "一、背景", "二、目标"
    """
    if not text:
        return []
    
    blocks = _SECTION_HEADING.split(text)
    return [block.strip() for block in blocks if block.strip()]
```

**示例**:
```python
# 输入
"""
# Tesla 2024 ESG Report

## Environmental Performance
Our Scope 1 emissions decreased...

## Social Impact
We employed 140,000 workers...

第一章 公司治理
董事会由 11 名成员组成...
"""

# 输出 (3 个章节)
[
    "# Tesla 2024 ESG Report",
    "## Environmental Performance\nOur Scope 1 emissions decreased...",
    "## Social Impact\nWe employed 140,000 workers...",
    "第一章 公司治理\n董事会由 11 名成员组成..."
]
```

---

#### 步骤 3: 提取章节标题

```python
def _extract_heading(section: str) -> str | None:
    """
    从章节文本中提取标题
    
    规则:
    1. 取第一行
    2. 去除 Markdown 标记 (# ## ###)
    3. 长度限制: 2-80 字符 (太短或太长都不是标题)
    """
    first_line = section.split("\n", 1)[0].strip()
    cleaned = re.sub(r"^#{1,4}\s+", "", first_line).strip()
    
    if len(cleaned) > 80 or len(cleaned) < 2:
        return None  # 不是标题
    
    return cleaned
```

**示例**:
```python
# 输入
"## Environmental Performance\nOur Scope 1 emissions..."

# 输出
"Environmental Performance"
```

---

#### 步骤 4: 分离表格 ⭐

**目的**: 表格应该作为一个整体索引，避免被滑动窗口截断。

```python
_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)

def _separate_tables(section: str) -> tuple[list[str], str]:
    """
    从章节中提取表格
    
    Markdown 表格格式:
    | Column 1 | Column 2 |
    | Value 1  | Value 2  |
    
    返回:
        (tables, prose)
        tables: 表格文本列表
        prose: 去除表格后的正文
    """
    lines = section.split("\n")
    tables = []
    prose_lines = []
    current_table = []
    
    for line in lines:
        if _TABLE_ROW.match(line):
            # 这是表格行
            current_table.append(line)
        else:
            # 这不是表格行
            if current_table:
                # 保存之前累积的表格
                table_text = "\n".join(current_table)
                if len(table_text) > 30:  # 至少 30 字符才是有效表格
                    tables.append(table_text)
                else:
                    prose_lines.extend(current_table)  # 太短，当作正文
                current_table = []
            prose_lines.append(line)
    
    # 处理末尾的表格
    if current_table:
        table_text = "\n".join(current_table)
        if len(table_text) > 30:
            tables.append(table_text)
        else:
            prose_lines.extend(current_table)
    
    return tables, "\n".join(prose_lines)
```

**示例**:
```python
# 输入
"""
Our emissions data:

| Year | Scope 1 | Scope 2 |
| 2023 | 150000  | 92000   |
| 2024 | 137000  | 85000   |

Analysis shows a 12% reduction.
"""

# 输出
tables = [
    "| Year | Scope 1 | Scope 2 |\n| 2023 | 150000  | 92000   |\n| 2024 | 137000  | 85000   |"
]
prose = "Our emissions data:\n\nAnalysis shows a 12% reduction."
```

---

#### 步骤 5: 滑动窗口切片 ⭐⭐⭐

**核心算法**: 使用重叠窗口避免语义断裂。

```python
def _sliding_windows(text: str) -> list[str]:
    """
    滑动窗口切片
    
    参数:
        chunk_size: 900 字符 (约 150-200 个英文单词)
        chunk_overlap: 150 字符 (约 20-30 个单词)
    
    智能断句优先级:
        1. 段落边界 (\n\n) — 最优
        2. 句子边界 (. 或 。) — 次优
        3. 分号边界 (; 或 ；) — 可接受
        4. 强制切分 (达到 chunk_size) — 最后手段
    """
    if not text.strip():
        return []
    
    if len(text) <= self.chunk_size:
        return [text]  # 无需切分
    
    windows = []
    start = 0
    
    while start < len(text):
        # 1. 确定候选窗口
        end = min(start + self.chunk_size, len(text))
        candidate = text[start:end]
        
        # 2. 如果未到文本末尾，尝试智能断句
        if end < len(text):
            # 在窗口后 40%-100% 区域寻找断句点
            split_at = max(
                candidate.rfind("\n\n"),  # 段落边界 (优先级最高)
                candidate.rfind(". "),    # 英文句子边界
                candidate.rfind("。"),     # 中文句子边界
                candidate.rfind("; "),    # 英文分号
                candidate.rfind("；")      # 中文分号
            )
            
            # 3. 如果找到合适的断句点
            if split_at > int(self.chunk_size * 0.4):
                end = start + split_at + 1
                candidate = text[start:end]
        
        # 4. 添加窗口
        windows.append(candidate.strip())
        
        # 5. 移动到下一个窗口 (带重叠)
        if end >= len(text):
            break  # 已到末尾
        
        start = max(0, end - self.chunk_overlap)  # 重叠 150 字符
    
    return windows
```

**图解示例**:

```
原文: "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"  (36 字符)
chunk_size = 15
chunk_overlap = 5

┌─────────────────┐
│ ABCDEFGHIJKLMNO │  Window 1 (0-15)
└─────────────────┘
          ┌─────────────────┐
          │ KLMNOPQRSTUVWXY │  Window 2 (10-25, 重叠 5 字符 KLMNO)
          └─────────────────┘
                    ┌─────────────────┐
                    │ VWXYZ1234567890 │  Window 3 (20-36, 重叠 5 字符 VWXYZ)
                    └─────────────────┘
```

**重叠的好处**:
- **避免语义断裂** — 如果一个关键信息正好被切分在两个窗口交界处，重叠区域能确保至少有一个窗口包含完整信息
- **提高召回率** — 用户查询时，更容易匹配到相关 chunk

---

#### 步骤 6: 标题注入

**目的**: 为每个 chunk 添加上下文信息 (所属章节标题)。

```python
# 在生成 chunk 时注入标题
if heading and not window.startswith(heading):
    window = f"[{heading}]\n{window}"
```

**示例**:
```python
# 原始 chunk
"Our Scope 1 emissions decreased by 12% in 2024 due to increased renewable energy usage."

# 注入标题后
"[Environmental Performance]\nOur Scope 1 emissions decreased by 12% in 2024 due to increased renewable energy usage."
```

**好处**:
- **独立理解** — 即使用户只看到这一个 chunk，也能知道它讨论的是"Environmental Performance"
- **提升检索精度** — 标题中的关键词 (例如"Environmental") 会参与 embedding 计算

---

### 3.4 Chunk 数据结构

```python
@dataclass
class Chunk:
    chunk_id: str  # UUID (全局唯一)
    text: str      # chunk 文本 (可能包含标题前缀)
    metadata: dict[str, Any]  # 元数据 (继承自 Document + 新增字段)
```

**metadata 新增字段**:

| 字段 | 类型 | 说明 | 示例 |
|-----|------|------|------|
| `section_index` | int | 所属章节索引 | `0`, `1`, `2` |
| `window_index` | int | 章节内的窗口索引 | `0`, `1`, `2` |
| `section_heading` | str | 章节标题 | `"Environmental Performance"` |

**完整示例**:
```python
Chunk(
    chunk_id="a3f8c9e1-b2d4-5678-90ab-cdef12345678",
    text="[Environmental Performance]\nOur Scope 1 emissions decreased by 12% in 2024...",
    metadata={
        "source": "/path/to/storage/kbs/abc/files/x1_report.pdf",
        "source_name": "tesla_esg_2024.pdf",
        "source_type": "pdf",
        "page": 15,
        "total_pages": 50,
        "section_index": 2,
        "window_index": 0,
        "section_heading": "Environmental Performance"
    }
)
```

---

### 3.5 分块效果对比

#### 无分块 (直接向量化整个文档)
- ❌ 检索不精确 (文档谈论多个主题，无法定位具体段落)
- ❌ 上下文超限 (无法传递给 LLM)
- ❌ 语义稀释 (embedding 无法表达局部语义)

#### 简单分块 (按固定字符数硬切)
- ⚠️ 可能在句子中间切分 (例如 "Tesla's Scope 1 emis|sions decreased...")
- ⚠️ 跨章节切分 (例如 "...Environmental章节末尾|Social章节开头...")
- ⚠️ 表格被截断

#### ESGChunker (本系统)
- ✅ 章节感知 (按章节结构切分)
- ✅ 智能断句 (优先在段落、句子边界切分)
- ✅ 表格完整 (表格独立成块)
- ✅ 标题注入 (每个 chunk 包含上下文)
- ✅ 重叠窗口 (避免语义断裂)

---

## 阶段四：向量化（Embedding）

### 4.1 什么是 Embedding？

**Embedding** 是将文本转换为**高维向量** (数值数组) 的过程。

```python
# 文本
"Tesla's Scope 1 emissions decreased by 12%"

# 向量 (384 维，简化示例)
[0.123, -0.456, 0.789, ..., 0.012]
```

**核心特性**:
- **语义相似度** — 语义相似的文本，其向量在高维空间中距离较近
- **可计算** — 可以用余弦相似度、欧氏距离等度量相似性

---

### 4.2 Embedding 方式对比

| 方式 | 模型 | 维度 | 速度 | 成本 | 质量 |
|-----|------|------|------|------|------|
| **本地 (推荐)** | `all-MiniLM-L6-v2` | 384 | ~1000 chunks/秒 (CPU) | 免费 | 中等 |
| **本地 (高质量)** | `bge-base-en-v1.5` | 768 | ~500 chunks/秒 (CPU) | 免费 | 高 |
| **OpenAI API** | `text-embedding-3-small` | 1536 | 受 API 限制 | $0.0001/1K tokens | 高 |
| **哈希降级** | `HashingVectorizer` | 1024 | 非常快 | 免费 | 低 (仅关键词匹配) |

---

### 4.3 本地 Embedding (默认方式)

```python
# 位置: embedding.py → SentenceTransformerEmbeddingProvider

class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """
    使用 sentence-transformers 本地模型
    
    默认模型: all-MiniLM-L6-v2
    - 模型大小: 80 MB
    - 首次使用时自动下载
    - 下载位置: ~/.cache/torch/sentence_transformers/
    """
    
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        
        logger.info("加载 sentence-transformers 模型: %s", model_name)
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
    
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """
        批量向量化文档
        
        参数:
            texts: 文本列表 (例如 chunk 的 text 字段)
        
        返回:
            np.ndarray, shape (len(texts), 384)
        """
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        
        return self.model.encode(
            texts,
            normalize_embeddings=True,   # 归一化到单位长度 (便于计算余弦相似度)
            show_progress_bar=False       # 不显示进度条 (后台运行)
        ).astype(np.float32)
    
    def embed_query(self, text: str) -> np.ndarray:
        """
        向量化单个查询
        
        返回:
            np.ndarray, shape (384,)
        """
        return self.model.encode(
            [text],
            normalize_embeddings=True,
            show_progress_bar=False
        ).astype(np.float32)[0]
```

**使用示例**:
```python
from esg_rag.embedding import SentenceTransformerEmbeddingProvider

# 初始化 (首次使用会下载模型)
provider = SentenceTransformerEmbeddingProvider()

# 向量化一批 chunk
chunks = [
    "Tesla's Scope 1 emissions decreased by 12%",
    "The company employs 140,000 workers globally",
    "Board consists of 11 independent directors"
]

embeddings = provider.embed_documents(chunks)
print(embeddings.shape)  # (3, 384)

# 向量化查询
query_vector = provider.embed_query("carbon emissions reduction")
print(query_vector.shape)  # (384,)
```

---

### 4.4 OpenAI API Embedding

```python
# 位置: embedding.py → OpenAIEmbeddingProvider

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    使用 OpenAI API (或兼容接口)
    
    适用场景:
    - 需要更高质量的 embedding
    - 本地资源有限 (CPU 较慢)
    
    成本: $0.0001 / 1K tokens
    """
    
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise ValueError("需要配置 OPENAI_API_KEY")
        self.settings = settings
    
    def _request_embeddings(self, inputs: list[str]) -> np.ndarray:
        """
        调用 OpenAI Embeddings API
        """
        payload = {
            "model": self.settings.openai_embedding_model,
            "input": inputs
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json"
        }
        url = f"{self.settings.openai_base_url.rstrip('/')}/embeddings"
        
        timeout = httpx.Timeout(connect=15.0, read=120.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        
        data = response.json()["data"]
        vectors = np.array([row["embedding"] for row in data], dtype=np.float32)
        
        # 归一化
        return _normalize_embeddings(vectors)
```

**配置方式**:
```bash
# .env 文件
EMBEDDING_BACKEND=openai
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

---

### 4.5 性能对比

#### 测试条件
- CPU: Intel i7-12700 (12 核)
- 文档: 100 个 PDF 文件, 共 5000 个 chunks
- 平均 chunk 长度: 600 字符

| Embedding 方式 | 总耗时 | 每秒处理 chunks | 内存占用 | 成本 |
|---------------|--------|----------------|---------|------|
| `all-MiniLM-L6-v2` (CPU) | 5 秒 | 1000 | ~500 MB | 免费 |
| `bge-base-en-v1.5` (CPU) | 10 秒 | 500 | ~800 MB | 免费 |
| `all-MiniLM-L6-v2` (GPU) | 0.5 秒 | 10000 | ~2 GB | 免费 |
| `OpenAI API` | 15 秒 | 333 | ~100 MB | $0.03 |

---

## 阶段五：向量存储与索引

### 5.1 SimpleVectorStore (默认存储)

**特点**:
- **纯本地存储** — 无需外部依赖
- **基于 NumPy** — 高效的向量计算
- **文件持久化** — 重启服务后数据不丢失

```python
# 位置: vector_store.py → SimpleVectorStore

class SimpleVectorStore:
    """
    简单向量存储
    
    存储文件:
        vectors.npy   — NumPy 向量矩阵 (shape: [num_chunks, embedding_dim])
        chunks.json   — Chunk 元数据 (文本、metadata)
        state.joblib  — 索引状态 (chunk 数量等)
    """
    
    def __init__(self, persist_dir: Path):
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        self.matrix_path = self.persist_dir / "vectors.npy"
        self.meta_path = self.persist_dir / "chunks.json"
        
        self.vectors = None  # np.ndarray (num_chunks, embedding_dim)
        self.chunks = []     # list[Chunk]
        
        self._load()  # 如果存在旧索引，自动加载
    
    def index(self, chunks: list[Chunk], embeddings: np.ndarray):
        """
        构建索引
        
        参数:
            chunks: Chunk 列表
            embeddings: 向量矩阵 (shape: [len(chunks), embedding_dim])
        """
        self.chunks = chunks
        self.vectors = embeddings.astype(np.float32)
        
        # 1. 保存向量矩阵
        np.save(self.matrix_path, self.vectors)
        
        # 2. 保存 chunk 元数据
        payload = [
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "metadata": chunk.metadata
            }
            for chunk in chunks
        ]
        self.meta_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        # 3. 保存索引状态
        joblib.dump({"count": len(chunks)}, self.persist_dir / "state.joblib")
    
    def search(self, query_vector: np.ndarray, top_k=6) -> list[SearchResult]:
        """
        向量检索
        
        参数:
            query_vector: 查询向量 (shape: [embedding_dim])
            top_k: 返回前 k 个最相关的结果
        
        返回:
            list[SearchResult], 按相似度降序排列
        """
        if self.vectors is None or len(self.chunks) == 0:
            return []  # 空索引
        
        # 1. 计算余弦相似度
        #    cosine_sim = (query · document) / (||query|| * ||document||)
        #    由于 embedding 已归一化, 直接点积即可
        query = query_vector.astype(np.float32)
        norms = np.linalg.norm(self.vectors, axis=1) * max(np.linalg.norm(query), 1e-9)
        scores = (self.vectors @ query) / np.maximum(norms, 1e-9)
        
        # 2. 排序并取 top_k
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        # 3. 构造结果
        return [
            SearchResult(
                chunk_id=self.chunks[int(index)].chunk_id,
                score=float(scores[index]),
                text=self.chunks[int(index)].text,
                metadata=self.chunks[int(index)].metadata
            )
            for index in top_indices
        ]
    
    def _load(self):
        """
        加载已有索引 (服务重启后恢复数据)
        """
        if self.matrix_path.exists() and self.meta_path.exists():
            self.vectors = np.load(self.matrix_path)
            payload = json.loads(self.meta_path.read_text(encoding="utf-8"))
            self.chunks = [
                Chunk(
                    chunk_id=item["chunk_id"],
                    text=item["text"],
                    metadata=item["metadata"]
                )
                for item in payload
            ]
```

---

### 5.2 存储文件示例

#### vectors.npy (NumPy 向量矩阵)
```python
# 形状: (5000, 384)  # 5000 个 chunks, 每个 384 维
array([[0.123, -0.456, 0.789, ..., 0.012],
       [0.234, -0.567, 0.890, ..., 0.023],
       ...,
       [0.345, -0.678, 0.901, ..., 0.034]], dtype=float32)
```

#### chunks.json (元数据)
```json
[
  {
    "chunk_id": "a3f8c9e1-b2d4-5678-90ab-cdef12345678",
    "text": "[Environmental Performance]\nOur Scope 1 emissions decreased by 12% in 2024...",
    "metadata": {
      "source": "/path/to/report.pdf",
      "source_name": "tesla_esg_2024.pdf",
      "page": 15,
      "section_heading": "Environmental Performance"
    }
  },
  {
    "chunk_id": "b4g9d0f2-c3e5-6789-01bc-defg23456789",
    "text": "[Social Impact]\nWe employed 140,000 workers globally...",
    "metadata": {
      "source": "/path/to/report.pdf",
      "source_name": "tesla_esg_2024.pdf",
      "page": 25,
      "section_heading": "Social Impact"
    }
  }
]
```

---

### 5.3 索引构建完整流程

```python
# 位置: pipeline.py → ESGAnalysisPipeline.index_kb()

def index_kb(files_dir: Path, index_dir: Path) -> tuple[int, int, list[str]]:
    """
    为知识库构建索引
    
    流程:
    1. 加载文档 (DocumentLoader)
    2. 分块 (ESGChunker)
    3. 向量化 (EmbeddingProvider)
    4. 存储索引 (VectorStore)
    
    返回:
        (文档数, chunk数, 来源列表)
    """
    
    # 步骤 1: 加载文档
    loader = DocumentLoader()
    documents = loader.load_directory(files_dir)
    print(f"加载了 {len(documents)} 个文档片段")
    
    # 步骤 2: 分块
    chunker = ESGChunker(chunk_size=900, chunk_overlap=150)
    chunks = chunker.chunk_documents(documents)
    print(f"生成了 {len(chunks)} 个 chunks")
    
    # 步骤 3: 向量化
    store = SimpleVectorStore(index_dir)
    
    if chunks:
        embeddings = self.retriever.embedding_provider.embed_documents(
            [c.text for c in chunks]
        )
        print(f"生成了 {embeddings.shape} 向量")
        
        # 步骤 4: 存储索引
        store.index(chunks, embeddings)
        print(f"索引已保存到 {index_dir}")
    else:
        # 如果没有 chunks (例如所有文档被删除), 清空索引
        store.clear()
    
    # 统计来源
    sources = sorted({
        str(doc.metadata.get("source", "unknown"))
        for doc in documents
    })
    
    return len(documents), len(chunks), sources
```

**调用示例**:
```python
pipeline = ESGAnalysisPipeline()
kb_manager = KnowledgeBaseManager(settings.kb_storage_dir)

# 为知识库 'abc123' 构建索引
files_indexed, chunks_indexed, sources = pipeline.index_kb(
    files_dir=kb_manager.files_dir('abc123'),
    index_dir=kb_manager.index_dir('abc123')
)

print(f"索引完成: {files_indexed} 文件 → {chunks_indexed} chunks")
print(f"来源: {sources}")
```

**输出示例**:
```
加载了 15 个文档片段
生成了 450 个 chunks
生成了 (450, 384) 向量
索引已保存到 storage/kbs/abc123/index
索引完成: 3 文件 → 450 chunks
来源: ['storage/kbs/abc123/files/x1_report.pdf', 'storage/kbs/abc123/files/x2_policy.docx', 'storage/kbs/abc123/files/x3_data.json']
```

---

## 阶段六:检索与查询

### 6.1 向量检索原理

```
用户查询: "Tesla 的碳排放管理策略"
    ↓
1. 查询扩展
    "Tesla carbon emissions management strategy"
    → ["Tesla GHG management", "Tesla Scope 1 reduction", "Tesla carbon footprint"]
    ↓
2. 向量化
    query_vector = embed("Tesla carbon emissions management")
    ↓
3. 相似度计算
    for each chunk_vector in index:
        similarity = cosine_sim(query_vector, chunk_vector)
    ↓
4. 排序并取 top_k
    top_6_chunks (相似度最高的 6 个)
    ↓
5. Reranking (可选)
    - 关键词重叠加分
    - 时间衰减 (优先新文档)
    - 文本去重
    ↓
6. 返回结果
    list[SearchResult]
```

---

### 6.2 查询扩展 (ESG 同义词)

```python
# 位置: query_expansion.py

ESG_SYNONYMS = {
    "carbon": ["GHG", "greenhouse gas", "CO2", "carbon dioxide"],
    "emissions": ["GHG emissions", "carbon footprint", "Scope 1", "Scope 2", "Scope 3"],
    "employee": ["workforce", "human capital", "staff", "personnel"],
    "board": ["board of directors", "independent directors", "board composition"],
    # ... 30+ 映射
}

def enrich_query(query: str) -> str:
    """
    查询增强: 在查询末尾附加相关同义词
    
    示例:
        "carbon emissions" → "carbon emissions GHG Scope 1 carbon footprint"
    """
    query_lower = query.lower()
    extra_terms = []
    
    for term, synonyms in ESG_SYNONYMS.items():
        if term.lower() in query_lower:
            for syn in synonyms[:2]:  # 每个术语取前 2 个同义词
                if syn.lower() not in query_lower:
                    extra_terms.append(syn)
    
    if not extra_terms:
        return query
    
    return f"{query} {' '.join(extra_terms[:6])}"
```

**示例**:
```python
# 输入
"Analyze Tesla's carbon emissions reduction strategy"

# 输出
"Analyze Tesla's carbon emissions reduction strategy GHG greenhouse gas Scope 1 Scope 2"
```

---

### 6.3 Reranking (二次排序)

```python
# 位置: pipeline.py → _KBRetriever._rerank()

def _rerank(query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
    """
    Reranking: 在向量检索的基础上, 进行二次排序
    
    策略:
    1. 关键词重叠加分 (+0.15)
    2. 时间衰减 (新文档优先, -0.01 * age)
    3. 文本去重 (相同文本只保留最高分)
    """
    query_tokens = self._tokenize(query)  # 提取查询关键词
    deduped = {}
    
    for r in results:
        # 1. 文本归一化 (用于去重)
        norm_text = re.sub(r"\s+", " ", r.text).strip().lower()
        
        # 2. 关键词重叠计算
        chunk_tokens = self._tokenize(r.text)
        overlap = len(query_tokens & chunk_tokens) / len(query_tokens)
        
        # 3. 时间衰减
        year_match = re.search(r"(20\d{2})", r.metadata.get("source_name", ""))
        if year_match:
            age = max(0, 2026 - int(year_match.group(1)))
            time_boost = -0.01 * age  # 每年衰减 0.01
        else:
            time_boost = 0
        
        # 4. 综合评分
        score = float(r.score) + (overlap * 0.15) + time_boost
        
        # 5. 去重 (保留最高分)
        boosted = SearchResult(
            chunk_id=r.chunk_id,
            score=round(score, 4),
            text=r.text,
            metadata=r.metadata
        )
        
        existing = deduped.get(norm_text)
        if existing is None or boosted.score > existing.score:
            deduped[norm_text] = boosted
    
    # 6. 排序并返回
    ranked = sorted(deduped.values(), key=lambda x: x.score, reverse=True)
    return ranked[:top_k]
```

**Reranking 效果**:

| 原始排序 (向量相似度) | 关键词重叠 | 时间加权 | 最终分数 | 最终排序 |
|-------------------|-----------|---------|---------|---------|
| Chunk A: 0.85 | +0.05 | -0.02 | 0.88 | 第 1 名 |
| Chunk B: 0.88 | +0.01 | -0.05 | 0.84 | 第 2 名 |
| Chunk C: 0.80 | +0.10 | 0 | 0.90 | 第 3 名 → **提升至第 1 名!** |

---

### 6.4 完整检索流程

```python
# 位置: pipeline.py → _KBRetriever.search()

def search(query: str, top_k: int = 6) -> list[SearchResult]:
    """
    知识库检索
    
    流程:
    1. 查询增强 (ESG 同义词)
    2. 向量化
    3. 向量检索 (从多个知识库)
    4. Reranking
    """
    
    # 步骤 1: 查询增强
    from esg_rag.query_expansion import enrich_query
    enriched = enrich_query(query)
    print(f"增强查询: {enriched}")
    
    # 步骤 2: 向量化
    query_vector = self.embedding_provider.embed_query(enriched)
    
    # 步骤 3: 从多个知识库检索
    candidate_k = max(top_k, top_k * 4)  # 检索 4 倍候选
    all_results = []
    
    for store in self.stores:  # 遍历所有知识库
        all_results.extend(store.search(query_vector, top_k=candidate_k))
    
    # 步骤 4: Reranking
    return self._rerank(query, all_results, top_k)
```

---

## 完整示例:从上传到检索

### 示例场景
用户上传了一份 Tesla 2024 ESG 报告 (PDF, 50 页),然后查询"Tesla 的碳排放管理"。

---

### 第 1 步:用户上传文件

```python
# API 请求
POST /kb/abc123/documents
Content-Type: multipart/form-data

files: tesla_esg_2024.pdf (2.5 MB)
```

**后端处理**:
```python
# 1. KnowledgeBaseManager 保存文件
doc_id = "x1y2z3"
stored_name = "x1y2z3_tesla_esg_2024.pdf"
file_path = "storage/kbs/abc123/files/x1y2z3_tesla_esg_2024.pdf"

# 2. 记录元数据
docs.json += {
    "id": "x1y2z3",
    "original_name": "tesla_esg_2024.pdf",
    "file_size": 2621440,
    "file_type": "pdf",
    "created_at": "2026-03-31T10:00:00Z"
}
```

---

### 第 2 步:自动触发索引

```python
# API 自动调用
pipeline.index_kb(
    files_dir="storage/kbs/abc123/files",
    index_dir="storage/kbs/abc123/index"
)
```

**详细流程**:

#### 2.1 DocumentLoader 加载 PDF
```
输入: tesla_esg_2024.pdf (50 页)

处理:
- 逐页提取文本
- 合并碎片页 (< 60 字符)

输出: 45 个 Document (5 个碎片页被合并)
```

#### 2.2 ESGChunker 分块
```
输入: 45 个 Document

处理:
1. 识别章节 (例如: "Environmental Performance", "Social Impact")
2. 提取表格 (例如: 排放数据表)
3. 滑动窗口切片 (chunk_size=900, overlap=150)
4. 标题注入

输出: 450 个 Chunk
```

**Chunk 示例**:
```python
Chunk(
    chunk_id="a3f8c9e1-...",
    text="[Environmental Performance]\nOur Scope 1 emissions decreased by 12% in 2024 due to increased use of renewable energy. We achieved this through: 1) Solar panel installations at 15 manufacturing facilities...",
    metadata={
        "source": "storage/kbs/abc123/files/x1y2z3_tesla_esg_2024.pdf",
        "source_name": "tesla_esg_2024.pdf",
        "page": 15,
        "section_heading": "Environmental Performance",
        "section_index": 2,
        "window_index": 0
    }
)
```

#### 2.3 EmbeddingProvider 向量化
```
输入: 450 个 Chunk 的文本

处理:
provider.embed_documents([
    "[Environmental Performance]\nOur Scope 1 emissions...",
    "[Environmental Performance]\nWe achieved this through...",
    ...
])

输出: np.ndarray, shape (450, 384)
```

#### 2.4 SimpleVectorStore 存储
```
写入文件:
- storage/kbs/abc123/index/vectors.npy (450×384 向量矩阵)
- storage/kbs/abc123/index/chunks.json (450 个 chunk 元数据)
- storage/kbs/abc123/index/state.joblib (索引状态)
```

---

### 第 3 步:用户查询

```python
# API 请求
POST /query
Content-Type: application/json

{
  "query": "Tesla 的碳排放管理",
  "kb_ids": ["abc123"],
  "top_k": 6
}
```

**后端处理**:

#### 3.1 查询增强
```python
原始查询: "Tesla 的碳排放管理"

增强后: "Tesla 的碳排放管理 GHG Scope 1 carbon footprint 温室气体"
```

#### 3.2 向量化查询
```python
query_vector = provider.embed_query("Tesla 的碳排放管理 GHG Scope 1...")
# shape: (384,)
```

#### 3.3 向量检索
```python
# 加载索引
vectors = np.load("storage/kbs/abc123/index/vectors.npy")  # (450, 384)
chunks = json.load("storage/kbs/abc123/index/chunks.json")

# 计算相似度
scores = vectors @ query_vector  # (450,)

# 排序
top_indices = np.argsort(scores)[::-1][:24]  # 取前 24 个候选

# 构造结果
candidates = [
    SearchResult(chunk_id=chunks[i]["chunk_id"], score=scores[i], ...)
    for i in top_indices
]
```

#### 3.4 Reranking
```python
# 关键词重叠
query_tokens = {"Tesla", "碳排放", "管理", "GHG", "Scope", "1"}

for r in candidates:
    chunk_tokens = tokenize(r.text)
    overlap = len(query_tokens & chunk_tokens) / len(query_tokens)
    r.score += overlap * 0.15

# 时间加权
# "tesla_esg_2024.pdf" → year=2024 → age=2026-2024=2 → boost=-0.02
r.score += -0.02

# 文本去重
deduped = {normalize(r.text): r for r in candidates}

# 排序并取 top_6
final = sorted(deduped.values(), key=lambda x: x.score, reverse=True)[:6]
```

#### 3.5 返回结果
```json
{
  "query": "Tesla 的碳排放管理",
  "results": [
    {
      "chunk_id": "a3f8c9e1-...",
      "score": 0.892,
      "text": "[Environmental Performance]\nOur Scope 1 emissions decreased by 12% in 2024...",
      "metadata": {
        "source_name": "tesla_esg_2024.pdf",
        "page": 15,
        "section_heading": "Environmental Performance"
      }
    },
    {
      "chunk_id": "b4g9d0f2-...",
      "score": 0.875,
      "text": "[Climate Strategy]\nTesla's carbon management strategy includes...",
      "metadata": {
        "source_name": "tesla_esg_2024.pdf",
        "page": 18,
        "section_heading": "Climate Strategy"
      }
    },
    ...
  ]
}
```

---

## 性能优化与最佳实践

### 10.1 索引性能优化

#### 优化 1: 批量向量化
```python
# ❌ 不推荐: 逐个向量化
for chunk in chunks:
    vector = provider.embed_query(chunk.text)

# ✅ 推荐: 批量向量化
embeddings = provider.embed_documents([c.text for c in chunks])
```

#### 优化 2: 使用 GPU 加速
```python
# 安装 PyTorch GPU 版本
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# sentence-transformers 会自动检测并使用 GPU
provider = SentenceTransformerEmbeddingProvider("all-MiniLM-L6-v2")
# 速度提升: 1000 chunks/秒 (CPU) → 10000 chunks/秒 (GPU)
```

#### 优化 3: 增量索引
```python
# 只索引新增文档,而不是每次重建整个索引
def incremental_index(new_files):
    # 1. 加载现有索引
    store = SimpleVectorStore(index_dir)
    old_chunks = store.chunks.copy()
    old_vectors = store.vectors.copy()
    
    # 2. 处理新文档
    new_docs = loader.load_files(new_files)
    new_chunks = chunker.chunk_documents(new_docs)
    new_embeddings = provider.embed_documents([c.text for c in new_chunks])
    
    # 3. 合并索引
    all_chunks = old_chunks + new_chunks
    all_vectors = np.vstack([old_vectors, new_embeddings])
    
    store.index(all_chunks, all_vectors)
```

---

### 10.2 检索性能优化

#### 优化 1: 使用 FAISS (高性能向量检索)
```python
# 安装 FAISS
pip install faiss-cpu  # CPU 版本
pip install faiss-gpu  # GPU 版本

# 替换 SimpleVectorStore
import faiss

class FAISSVectorStore:
    def __init__(self, embedding_dim=384):
        self.index = faiss.IndexFlatIP(embedding_dim)  # 内积索引 (适用于归一化向量)
        self.chunks = []
    
    def index(self, chunks, embeddings):
        self.chunks = chunks
        self.index.add(embeddings)
    
    def search(self, query_vector, top_k=6):
        scores, indices = self.index.search(query_vector.reshape(1, -1), top_k)
        return [
            SearchResult(
                chunk_id=self.chunks[i].chunk_id,
                score=float(scores[0][idx]),
                text=self.chunks[i].text,
                metadata=self.chunks[i].metadata
            )
            for idx, i in enumerate(indices[0])
        ]

# 速度提升: 10x+ (对于 10,000+ chunks)
```

#### 优化 2: 缓存查询向量
```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=128)
def cached_embed_query(query: str):
    return provider.embed_query(query)

# 相同查询会直接返回缓存结果,避免重复计算
```

---

### 10.3 存储空间优化

#### 优化 1: 使用 float16 (减半存储空间)
```python
# 修改 SimpleVectorStore.index()
self.vectors = embeddings.astype(np.float16)  # 384维 × 2字节 = 768 字节/chunk
# vs float32: 384维 × 4字节 = 1536 字节/chunk

# 注意: 精度略有损失 (~0.1% 检索准确率下降)
```

#### 优化 2: 压缩 chunks.json
```python
# 使用 gzip 压缩
import gzip

with gzip.open(self.meta_path.with_suffix('.json.gz'), 'wt', encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False)

# 压缩率: ~70% (100 MB → 30 MB)
```

---

## 故障排查指南

### 11.1 常见问题

#### 问题 1: 索引后检索不到结果
**症状**: `POST /query` 返回 `[]` 空结果

**排查步骤**:
```python
# 1. 检查索引是否生成
import os
print(os.path.exists("storage/kbs/abc123/index/vectors.npy"))
print(os.path.exists("storage/kbs/abc123/index/chunks.json"))

# 2. 检查 chunk 数量
store = SimpleVectorStore("storage/kbs/abc123/index")
print(f"已索引 {len(store.chunks)} 个 chunks")

# 3. 检查查询向量
query_vector = provider.embed_query("test query")
print(f"查询向量维度: {query_vector.shape}")  # 应为 (384,)

# 4. 手动检索测试
results = store.search(query_vector, top_k=10)
print(f"检索到 {len(results)} 个结果")
for r in results[:3]:
    print(f"  - [{r.score:.3f}] {r.text[:100]}...")
```

**可能原因**:
1. **向量维度不匹配** — 索引时用的 `all-MiniLM-L6-v2` (384维),查询时用的 `bge-base-en-v1.5` (768维)
2. **索引为空** — 文档加载失败 (例如 PDF 损坏、DOCX 无法打开)
3. **embedding 模型未加载** — 首次启动时模型还在下载

---

#### 问题 2: PDF 文件无法索引
**症状**: `DocumentLoader` 报错 `Failed to open PDF`

**排查步骤**:
```python
# 1. 检查文件是否损坏
from pypdf import PdfReader

try:
    reader = PdfReader("path/to/file.pdf")
    print(f"PDF 有 {len(reader.pages)} 页")
except Exception as e:
    print(f"PDF 损坏: {e}")

# 2. 检查文件大小
import os
size = os.path.getsize("path/to/file.pdf")
print(f"文件大小: {size} 字节")
if size == 0:
    print("❌ 文件为空!")

# 3. 尝试提取文本
text = reader.pages[0].extract_text()
print(f"第 1 页文本 ({len(text)} 字符):\n{text[:200]}")
```

**可能原因**:
1. **文件损坏** — 重新下载或用 PDF 修复工具修复
2. **文件是图片 PDF** — 需要 OCR (本系统暂不支持)
3. **文件加密** — 需要密码解密 (本系统暂不支持)

---

#### 问题 3: 索引速度过慢
**症状**: 1000 个 chunks 索引需要 5 分钟+

**排查步骤**:
```python
import time

# 1. 测试 embedding 速度
texts = ["test text"] * 100
start = time.time()
embeddings = provider.embed_documents(texts)
elapsed = time.time() - start
print(f"100 个文本向量化耗时: {elapsed:.2f} 秒")
print(f"速度: {100/elapsed:.1f} chunks/秒")

# 预期速度:
# - all-MiniLM-L6-v2 (CPU): 500-1000 chunks/秒
# - all-MiniLM-L6-v2 (GPU): 5000-10000 chunks/秒
# - OpenAI API: 100-500 chunks/秒 (受限于网络和 API 速率)
```

**优化方案**:
1. **使用 GPU** — 安装 PyTorch GPU 版本
2. **减少 batch size** — 如果内存不足,降低每次处理的 chunk 数量
3. **使用更轻量的模型** — 例如 `all-MiniLM-L6-v2` → `paraphrase-MiniLM-L3-v2` (维度 384 → 128)

---

#### 问题 4: 查询结果不相关
**症状**: 查询"碳排放",返回的都是"员工福利"相关内容

**排查步骤**:
```python
# 1. 检查查询向量
query = "碳排放"
query_vector = provider.embed_query(query)

# 2. 手动检查 top 10 结果
results = store.search(query_vector, top_k=10)
for i, r in enumerate(results):
    print(f"\n[{i+1}] 分数: {r.score:.3f}")
    print(f"    文本: {r.text[:150]}...")
    print(f"    标签: {r.metadata.get('section_heading')}")

# 3. 检查是否有相关内容被索引
all_chunks = store.chunks
carbon_chunks = [c for c in all_chunks if "carbon" in c.text.lower() or "排放" in c.text]
print(f"\n包含 'carbon' 或 '排放' 的 chunks: {len(carbon_chunks)}/{len(all_chunks)}")
```

**可能原因**:
1. **索引中没有相关内容** — 需要上传更多 ESG 报告
2. **查询词不精确** — 尝试 "Scope 1 emissions" 而不是 "碳排放"
3. **embedding 模型质量不高** — 升级到 `bge-base-zh-v1.5` (专为中文优化)

---

#### 问题 5: 内存不足 (OOM)
**症状**: 服务器崩溃,日志显示 `MemoryError` 或 `Killed`

**排查步骤**:
```python
# 1. 检查索引大小
import os
import numpy as np

vectors = np.load("storage/kbs/abc123/index/vectors.npy")
print(f"向量矩阵: {vectors.shape}")
print(f"内存占用: {vectors.nbytes / 1024 / 1024:.1f} MB")

# 预估:
# - 10,000 chunks × 384 维 × 4 字节 = 15 MB
# - 100,000 chunks = 150 MB
# - 1,000,000 chunks = 1.5 GB
```

**优化方案**:
1. **分批索引** — 将大型知识库拆分为多个子库
2. **使用 float16** — 减半内存占用
3. **使用外部向量数据库** — Milvus / Chroma (支持磁盘存储)

---

### 11.2 日志分析

#### 查看索引日志
```python
# 启用 DEBUG 日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 重新索引
pipeline.index_kb(files_dir, index_dir)
```

**关键日志**:
```
DEBUG:esg_rag.document_loader:Loaded 15 document(s) from tesla_esg_2024.pdf
DEBUG:esg_rag.chunking:Generated 450 chunks from 15 documents
DEBUG:esg_rag.embedding:Encoding 450 texts with model all-MiniLM-L6-v2
DEBUG:esg_rag.vector_store:Indexed 450 chunks, saved to storage/kbs/abc123/index
```

---

### 11.3 性能监控

#### 监控索引速度
```python
import time

start = time.time()
files_indexed, chunks_indexed, sources = pipeline.index_kb(files_dir, index_dir)
elapsed = time.time() - start

print(f"索引完成:")
print(f"  - 文档数: {files_indexed}")
print(f"  - Chunk 数: {chunks_indexed}")
print(f"  - 耗时: {elapsed:.1f} 秒")
print(f"  - 速度: {chunks_indexed/elapsed:.1f} chunks/秒")
```

#### 监控检索速度
```python
import time

queries = [
    "carbon emissions",
    "employee diversity",
    "board governance",
    ...
]

total_time = 0
for q in queries:
    start = time.time()
    results = pipeline.query_kbs(q, index_dirs, top_k=6)
    elapsed = time.time() - start
    total_time += elapsed
    print(f"查询 '{q[:20]}...' 耗时: {elapsed*1000:.1f} ms, 结果数: {len(results)}")

print(f"\n平均查询延迟: {total_time/len(queries)*1000:.1f} ms")
```

---

## 总结

本文档详细介绍了 ESG RAG 系统的 **6 个核心阶段**:

1. **文档上传与存储** — 知识库管理、文件持久化
2. **文档加载与解析** — 多格式支持 (TXT/PDF/DOCX/JSON)
3. **文本分块 (Chunking)** — 章节感知、智能断句、表格提取、标题注入
4. **向量化 (Embedding)** — 本地模型 / OpenAI API / 哈希降级
5. **向量存储与索引** — SimpleVectorStore / Chroma / Milvus
6. **检索与查询** — 查询扩展、向量检索、Reranking

**核心优势**:
- ✅ **结构化保留** — 保留文档的章节、标题、表格结构
- ✅ **中英文兼容** — 针对 ESG 中英文混合文档优化
- ✅ **可追溯性** — 每个检索结果都能追溯到原始文件和页码
- ✅ **高质量分块** — 避免语义断裂、表格截断
- ✅ **灵活扩展** — 支持多种 embedding 和向量存储后端

**最佳实践**:
- 推荐使用 `all-MiniLM-L6-v2` 本地模型 (免费且高效)
- 定期重新索引 (当文档更新时)
- 使用 GPU 加速 (如果可用)
- 监控索引和检索性能 (日志 + 计时)

如有任何问题，请参考 [故障排查指南](#故障排查指南)！
