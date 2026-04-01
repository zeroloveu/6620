# ESG RAG 系统完整流程说明文档

## 系统概述

**ESG RAG** 是一个基于 **检索增强生成（RAG）** 的 ESG（环境、社会、治理）分析平台，支持：
- **知识库管理** — 创建多个知识库，上传 PDF、DOCX、TXT、JSON 等文档
- **智能检索** — 基于 Sentence-Transformers 的语义搜索
- **多 Agent 分析流水线** — 6 个专业 agent 协作生成结构化 ESG 报告
- **框架对齐** — 自动评估与 GRI、SASB、TCFD、CSRD 等国际框架的符合度
- **置信度评分** — 量化分析结果的可靠性

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web Frontend (HTML/JS)                   │
│  - Knowledge Base Management (CRUD)                             │
│  - Document Upload & Auto-Indexing                              │
│  - Query & Analysis with KB filtering                           │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP API
┌────────────────────────────┴────────────────────────────────────┐
│                     FastAPI Backend (Python)                     │
│  - RESTful API: /kb, /query, /analyze                           │
│  - KnowledgeBaseManager: 知识库和文档的增删改查                │
│  - ESGPipeline: 核心分析流水线                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
┌────────┴────────┐  ┌──────┴───────┐  ┌────────┴────────┐
│ Document Loader │  │  Embedding   │  │  Vector Store   │
│ (PDF/DOCX/TXT)  │  │  (MiniLM-L6) │  │  (SimpleVector) │
└─────────────────┘  └──────────────┘  └─────────────────┘
                             │
                   ┌─────────┴─────────┐
                   │  6 Agent Pipeline  │
                   │  (详见下方)        │
                   └───────────────────┘
```

---

## 完整流程（从零开始）

### 阶段 1：环境准备

#### 1.1 安装依赖
```bash
# 在项目根目录下
pip install -e .
```
**安装的核心依赖**：
- `fastapi`, `uvicorn` — Web 框架和服务器
- `sentence-transformers` — 本地 embedding 模型（all-MiniLM-L6-v2）
- `pypdf`, `python-docx` — PDF 和 DOCX 文档解析
- `numpy`, `scikit-learn` — 向量计算和余弦相似度
- `httpx` — LLM API 调用客户端

#### 1.2 配置环境变量
复制 `.env.example` 为 `.env`，配置：
```ini
# LLM 配置（可选，不配置则使用回退报告）
OPENAI_API_KEY=sk-xxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_CHAT_MODEL=deepseek-reasoner

# 知识库存储路径
KB_STORAGE_DIR=./storage/kbs
```

#### 1.3 启动服务
```bash
# 在项目根目录下（重要！不是 src 目录）
set PYTHONPATH=src
uvicorn esg_rag.main:app --port 8001
```

**重要提示**：必须在**项目根目录**启动，否则：
- `.env` 文件无法被 `pydantic-settings` 正确加载
- `KB_STORAGE_DIR` 等相对路径会解析错误

#### 1.4 访问前端
浏览器打开：`http://localhost:8001`

---

### 阶段 2：知识库管理

#### 2.1 创建知识库

**前端操作**：
1. 在左侧 **Knowledge Bases** 区域
2. 输入知识库名称（如"GreenTech 2025 ESG"）
3. 可选输入描述（如"GreenTech 公司 2025 年度 ESG 披露文档集合"）
4. 点击 **"Create knowledge base"**

**后端处理**：
```
POST /kb
→ KnowledgeBaseManager.create_kb(name, description)
  → 生成唯一 KB ID（UUID）
  → 创建目录结构：
     storage/kbs/{kb_id}/
       ├── meta.json         # KB 元数据（name, description, created_at）
       ├── docs.json         # 文档清单（初始为空数组 []）
       ├── files/            # 上传的文档存储目录
       └── index/            # 向量索引存储目录
  → 返回 KB 详情 JSON
```

**前端响应**：
- KB 列表刷新，新 KB 出现在列表中
- 自动选中新创建的 KB

#### 2.2 上传文档

**前端操作**：
1. 选中一个 KB（点击 KB 列表中的某一项）
2. 点击 **"Choose files"** 按钮（自定义样式）
3. 在文件选择器中选择文档（支持 PDF、DOCX、TXT、MD、JSON）
4. 点击 **"Upload & Index"** 按钮

**后端处理**：
```
POST /kb/{kb_id}/documents + files
→ KnowledgeBaseManager.add_documents(kb_id, files)
  → 为每个文件生成唯一文档 ID
  → 保存文件到 files/ 目录
  → 更新 docs.json 清单
→ Pipeline.index_kb(files_dir, index_dir)  # 自动索引
  → DocumentLoader.load_directory(files_dir)
    → 遍历 files/ 下的所有文件
    → 根据扩展名调用对应加载器：
       - .pdf → _load_pdf() (pypdf)
       - .docx → _load_docx() (python-docx)
       - .txt/.md → _load_text()
       - .json → _load_json()
    → 每个文件切分为 Document 对象（带 metadata）
  → ESGAwareChunker.chunk(documents)
    → 将 Document 切分为 ≤512 字符的 chunk
    → ESG 关键词附近的边界优先（如"emission"、"governance"）
  → EmbeddingProvider.embed(chunk.text)
    → 使用 all-MiniLM-L6-v2 模型生成 384 维向量
  → SimpleVectorStore.add_chunks(chunks, embeddings)
    → 保存到 index/ 目录：chunks.json + embeddings.npy
→ 返回：{"documents": [...], "index": {"files_indexed": 3, "chunks_indexed": 45, "sources": [...]}}
```

**前端响应**：
- 文档列表刷新，显示新上传的文档
- 输出区域显示索引结果（如"索引了 3 个文件，生成 45 个 chunk"）

#### 2.3 重新索引

**使用场景**：
- 删除了某些文档后，需要重建索引
- 手动触发全量索引

**前端操作**：
1. 选中一个 KB
2. 点击 **"Re-index"** 按钮

**后端处理**：
```
POST /kb/{kb_id}/index
→ Pipeline.index_kb(files_dir, index_dir)
  → 删除旧索引（index/ 目录下的 chunks.json 和 embeddings.npy）
  → 重新加载、切片、嵌入、存储
→ 返回索引结果
```

#### 2.4 删除文档

**前端操作**：
1. 选中一个 KB
2. 点击某个文档后的红色 **"Delete"** 按钮
3. 在确认对话框中点 **"Confirm"**

**后端处理**：
```
DELETE /kb/{kb_id}/documents/{doc_id}
→ KnowledgeBaseManager.delete_document(kb_id, doc_id)
  → 删除 files/ 下的文件
  → 从 docs.json 中移除该条目
→ 返回 204 No Content
```

**前端响应**：
- 文档从列表中移除
- 提示"需要重新索引以更新搜索结果"

#### 2.5 删除知识库

**前端操作**：
1. 点击 KB 列表某项后的红色 **"Delete"** 按钮
2. 确认删除

**后端处理**：
```
DELETE /kb/{kb_id}
→ KnowledgeBaseManager.delete_kb(kb_id)
  → 删除整个 storage/kbs/{kb_id}/ 目录树
  → 包括所有文档、索引、元数据
→ 返回 204 No Content
```

**前端响应**：
- KB 从列表中移除
- 如果当前选中的 KB 被删除，文档区域隐藏

---

### 阶段 3：查询（Query）

#### 3.1 前端操作

1. 在 **Query** 区域的 KB 选择框中勾选要查询的知识库（可多选）
   - 不勾选任何 KB → 默认查询**所有 KB**
2. 在文本框中输入查询（如"碳排放数据"）
3. 点击 **"Search"** 按钮

#### 3.2 后端处理

```
POST /query
{
  "query": "碳排放数据",
  "kb_ids": ["kb-uuid-1", "kb-uuid-2"]  # 或 null（查询所有 KB）
}

→ _resolve_kb_index_dirs(kb_ids)
  → 如果 kb_ids 为 null → 扫描 storage/kbs/，返回所有 KB 的 index/ 路径
  → 如果 kb_ids 有值 → 只返回指定 KB 的 index/ 路径
→ Pipeline.query_kbs(query, index_dirs, top_k=8)
  → 创建 _KBRetriever(embedding_provider, index_dirs)
    → 为每个 index_dir 加载 SimpleVectorStore
  → _KBRetriever.search(query, top_k=8)
    → 将查询文本嵌入为向量
    → 遍历所有 VectorStore，执行余弦相似度搜索
    → 合并所有结果，按 score 排序
    → 去重（同一 chunk_id 只保留最高分）
    → 返回 Top-8
→ 返回检索结果列表
```

#### 3.3 前端显示

输出区域显示：
```
Found 6 results

[Result 1]
Source: GreenTech_ESG_Report.docx
Section: 20
Score: 0.823
Text: GreenTech reduced Scope 1 and Scope 2 emissions by 18% compared to 2024...

[Result 2]
...
```

---

### 阶段 4：分析（Analysis）

#### 4.1 前端操作

1. 在 **Analysis** 区域选择知识库（同 Query）
2. 输入公司名称（如"GreenTech"）
3. 输入分析请求（如"生成结构化 ESG 分析"）
4. 可选输入框架（如"GRI, SASB"）
5. 点击 **"Generate report"** 按钮

#### 4.2 后端处理（核心流水线）

```
POST /analyze
{
  "company_name": "GreenTech",
  "user_query": "生成结构化 ESG 分析",
  "framework_focus": ["GRI", "SASB"],
  "kb_ids": ["kb-uuid-1"]
}

→ _resolve_kb_index_dirs(kb_ids)
  → 返回指定 KB 的 index/ 路径列表
→ Pipeline.analyze_kbs(company_name, user_query, framework_focus, index_dirs)
  → 创建 _KBRetriever(embedding_provider, index_dirs)
  → 执行 6 个 Agent 流水线（详见下方）
  → 返回 (report: dict, evidence: list[SearchResult])
→ 返回完整报告 JSON
```

#### 4.3 六个 Agent 的执行顺序

```
┌──────────────────────────────────────────────────────────┐
│ Agent 1: PlannerAgent                                    │
│ 输入: company_name, user_query, framework_focus         │
│ 输出: {sub_queries: [...], keywords: [...]}             │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────┴─────────────────────────────────┐
│ Agent 2: RetrievalAgent                                  │
│ 输入: sub_queries, retriever (KBRetriever)              │
│ 输出: list[SearchResult] (去重后的 Top-K 证据)         │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────┴─────────────────────────────────┐
│ Agent 3: EvidenceFusionAgent                             │
│ 输入: SearchResult 列表                                  │
│ 输出: 添加 tags (environment/social/governance)         │
│       和 excerpt (简洁摘要)                              │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────┴─────────────────────────────────┐
│ Agent 4: VerificationAgent                               │
│ 输入: 融合后的证据                                       │
│ 输出: 添加 verification_notes (质量检查注释)            │
└────────────────────────┬─────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
┌────────┴────────┐            ┌────────┴────────┐
│ Agent 5:        │            │ Agent 6:        │
│ ComplianceAgent │            │ ConfidenceAgent │
│ 框架对齐评估    │            │ 置信度评分      │
└────────┬────────┘            └────────┬────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
┌────────────────────────┴─────────────────────────────────┐
│ TraceAgent (汇总 trace 日志)                             │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────┴─────────────────────────────────┐
│ ReportAgent (调用 LLM 生成最终报告)                      │
│ 输出: 结构化 ESG 报告 JSON                               │
└──────────────────────────────────────────────────────────┘
```

**详细流程**：

1. **PlannerAgent**
   - 将"生成 GreenTech 的 ESG 分析"拆解为 5 个子查询
   - 输出：`{sub_queries: ["GreenTech environment...", "GreenTech social...", ...], keywords: [...]}`

2. **RetrievalAgent**
   - 对 5 个子查询分别检索（调用 `_KBRetriever.search()`）
   - 每个子查询返回 Top-8，共 40 个候选结果
   - 去重合并后取 Top-8

3. **EvidenceFusionAgent**
   - 给每条证据打标签（environment / social / governance / general）
   - 生成 220 字符以内的摘要

4. **VerificationAgent**
   - 检查证据长度、相似度分数、元数据完整性
   - 生成 `verification_notes`（如"Traceable source: xxx"）

5. **ComplianceAgent**
   - 对每个框架（GRI、SASB、TCFD、CSRD）计算覆盖度
   - 输出：`{GRI: {coverage: "high", matched_evidence_count: 6, ...}, ...}`

6. **ConfidenceAgent**
   - 基于平均相似度、可追溯性、主题覆盖、证据数量计算综合置信度
   - 输出：`{level: "high", score: 0.782, reason: "..."}`

7. **TraceAgent**
   - 汇总所有 agent 的输出
   - 统计标签分布（如 `{"environment": 3, "social": 2}`）

8. **ReportAgent**
   - 调用 `LLMClient.structured_esg_report()`
     - 如果配置了 API Key → 调用 DeepSeek / OpenAI
     - 如果未配置或失败 → 使用回退模板
   - 附加 `compliance_alignment`、`confidence_assessment`、`agent_trace`
   - 返回完整报告

#### 4.4 前端显示

报告包含以下区块：

1. **Executive Summary** — 概览
2. **Environment** — 环境维度的 summary、findings、risks、opportunities、evidence
3. **Social** — 社会维度（同上）
4. **Governance** — 治理维度（同上）
5. **Compliance Grid** — 框架对齐卡片（GRI high、SASB moderate...）
6. **Confidence Badge** — 置信度徽章（如"high | 0.782"）
7. **Next Steps** — 改进建议（如"补充 TCFD 气候披露文档"）
8. **Agent Trace**（可折叠）— 完整流水线 JSON 日志
9. **Raw Context**（可折叠）— 原始检索结果列表

用户可以点击 **"Clear report"** 按钮清空报告区域，继续操作。

---

## 数据流图（完整链路）

```
用户上传文档
    ↓
KnowledgeBaseManager.add_documents()
    ↓
DocumentLoader.load_directory()
    ↓
[TXT/MD/JSON/PDF/DOCX] → Document 对象列表
    ↓
ESGAwareChunker.chunk()
    ↓
Chunk 对象列表（每个 ≤512 字符）
    ↓
SentenceTransformerEmbeddingProvider.embed()
    ↓
384 维向量数组
    ↓
SimpleVectorStore.add_chunks()
    ↓
存储到 KB 的 index/ 目录
    ↓
────────────────────────────────────────
用户发起查询/分析
    ↓
_resolve_kb_index_dirs() → 获取要查询的 KB index 路径
    ↓
Pipeline.query_kbs() / analyze_kbs()
    ↓
创建 _KBRetriever(加载多个 SimpleVectorStore)
    ↓
PlannerAgent → 生成 5 个子查询
    ↓
RetrievalAgent → 对每个子查询检索，去重合并
    ↓
EvidenceFusionAgent → 打标签 + 提取摘要
    ↓
VerificationAgent → 生成验证注释
    ↓
ComplianceAgent + ConfidenceAgent（并行执行）
    ↓
TraceAgent → 汇总追踪日志
    ↓
ReportAgent → 调用 LLM 生成报告（或回退模板）
    ↓
返回完整 JSON 报告给前端
    ↓
前端渲染为可读的 HTML 报告
```

---

## 关键技术点

### 1. 多知识库检索
- 每个 KB 有独立的向量索引
- 查询时可以指定一个或多个 KB
- `_KBRetriever` 会加载所有指定 KB 的 `SimpleVectorStore`，并行搜索后合并结果

### 2. 自动索引
- 上传文档后**自动触发索引**，无需用户手动点击"Index"
- 避免了用户忘记索引导致"无结果"的问题

### 3. 流式 LLM 调用
- 使用 `stream: True` 和 600 秒 read timeout
- 适配 DeepSeek 的长推理时间（30~120 秒）
- 避免 HTTP 连接超时

### 4. 回退机制
- LLM 不可用时，使用本地规则生成基础报告
- 确保系统在任何情况下都能返回有效结果

### 5. 鲁棒的文档加载
- 检查 0 字节文件
- `try-except` 捕获文档解析错误（损坏文件、加密 PDF 等）
- 记录日志但不中断索引流程

### 6. 前端交互优化
- **确认对话框** — 删除操作前二次确认
- **输出滚动** — 报告区域有 `max-height: 600px` 和垂直滚动条，避免挤占其他 UI
- **清除按钮** — 允许用户手动清空结果，重新开始

---

## 目录结构

```
Myrag/
├── .env                          # 环境变量配置（API key、存储路径）
├── pyproject.toml                # 项目元数据和依赖
├── README.md                     # 项目使用说明
├── docs/                         # 文档目录（本文档所在目录）
│   ├── agent_planner.md
│   ├── agent_retrieval.md
│   ├── agent_evidence_fusion.md
│   ├── agent_verification.md
│   ├── agent_compliance.md
│   ├── agent_confidence.md
│   ├── agent_trace.md
│   ├── agent_report.md
│   ├── agent_report_llm.md
│   └── workflow_overview.md      # 本文档
├── storage/
│   └── kbs/                      # 知识库存储根目录
│       ├── {kb_id_1}/
│       │   ├── meta.json         # KB 元数据
│       │   ├── docs.json         # 文档清单
│       │   ├── files/            # 上传的文档
│       │   └── index/            # 向量索引
│       │       ├── chunks.json
│       │       └── embeddings.npy
│       └── {kb_id_2}/
│           └── ...
├── src/
│   └── esg_rag/
│       ├── main.py               # FastAPI 应用和 API 端点
│       ├── config.py             # 配置管理（pydantic-settings）
│       ├── knowledge_base.py     # 知识库管理器（CRUD）
│       ├── pipeline.py           # ESG 分析流水线核心
│       ├── agents.py             # 6 个 Agent 实现
│       ├── llm.py                # LLM 客户端
│       ├── document_loader.py    # 文档加载器（PDF/DOCX/TXT/JSON）
│       ├── chunker.py            # ESG 感知切片器
│       ├── embedding.py          # Embedding 提供者
│       ├── vector_store.py       # 向量存储（SimpleVectorStore）
│       ├── models.py             # 数据模型（SearchResult 等）
│       ├── schemas.py            # API 请求/响应 schema
│       └── web/
│           ├── index.html        # 前端主页面
│           └── static/
│               ├── app.js        # 前端交互逻辑
│               └── styles.css    # 前端样式
└── ...
```

---

## 核心 API 端点

### 知识库管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/kb` | `GET` | 列出所有知识库 |
| `/kb` | `POST` | 创建新知识库 |
| `/kb/{kb_id}` | `GET` | 获取知识库详情（含文档列表） |
| `/kb/{kb_id}` | `PUT` | 更新知识库元数据 |
| `/kb/{kb_id}` | `DELETE` | 删除知识库 |
| `/kb/{kb_id}/documents` | `POST` | 上传文档 + 自动索引 |
| `/kb/{kb_id}/documents/{doc_id}` | `PUT` | 更新文档元数据 |
| `/kb/{kb_id}/documents/{doc_id}` | `DELETE` | 删除文档 |
| `/kb/{kb_id}/index` | `POST` | 手动触发重新索引 |

### 查询和分析

| 端点 | 方法 | 说明 |
|------|------|------|
| `/query` | `POST` | 语义搜索（返回检索结果） |
| `/analyze` | `POST` | 生成结构化 ESG 报告 |

### 系统信息

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | `GET` | 健康检查 |

---

## 典型使用流程（完整示例）

### 步骤 1：启动服务
```bash
cd C:\Users\81011\Desktop\Myrag
set PYTHONPATH=src
uvicorn esg_rag.main:app --port 8001
```

### 步骤 2：创建知识库
- 前端操作：输入"GreenTech 2025"，点击"Create knowledge base"
- 后端自动创建 `storage/kbs/{uuid}/` 目录

### 步骤 3：上传文档
- 前端操作：选择文件（如 `GreenTech_ESG_Report.docx`），点击"Upload & Index"
- 后端自动：
  1. 保存文件到 `files/`
  2. 解析 DOCX（提取段落和表格文本）
  3. 切分为 chunk（45 个）
  4. 生成 embedding
  5. 保存到 `index/`

### 步骤 4：查询
- 前端操作：勾选"GreenTech 2025"，输入"碳排放"，点击"Search"
- 返回 6 条相关证据

### 步骤 5：分析
- 前端操作：
  - 公司名称：GreenTech
  - 请求：生成结构化 ESG 分析
  - 框架：GRI, SASB, TCFD
  - 勾选 KB："GreenTech 2025"
  - 点击"Generate report"
- 后端执行 6 个 Agent，耗时 30~60 秒
- 返回完整报告（3000+ 字符）

### 步骤 6：查看报告
- 前端显示：
  - Executive Summary（概览）
  - Environment / Social / Governance 三大维度
  - Compliance Grid（框架对齐状态）
  - Confidence Badge（置信度 0.782）
  - Next Steps（改进建议）

### 步骤 7：清空并重新分析
- 点击"Clear report"按钮
- 修改查询条件（如增加框架"CSRD"）
- 重新点击"Generate report"

---

## 性能和扩展性

### 性能指标
- **索引速度**：~10 个文档/秒（取决于文档大小）
- **查询延迟**：< 100ms（本地向量搜索）
- **分析延迟**：
  - 有 LLM：30~90 秒（主要是 LLM 推理时间）
  - 无 LLM（回退）：< 1 秒

### 扩展性
- **知识库数量**：无硬性限制（取决于磁盘空间）
- **单 KB 文档数**：建议 < 1000 个（SimpleVectorStore 基于 NumPy，全量加载）
- **向量索引规模**：可升级到 ChromaDB / Milvus 支持百万级 chunk

### 水平扩展建议
如果需要支持多用户/高并发：
1. 使用 **Gunicorn + Uvicorn workers** 部署多进程
2. 替换 `SimpleVectorStore` 为 **ChromaDB**（支持 gRPC 远程调用）
3. 使用 **Redis** 缓存常见查询结果
4. LLM 调用改为异步队列（Celery + RabbitMQ）

---

## 常见问题排查

### 问题 1：上传文档后查询无结果
**排查步骤**：
1. 检查文档是否成功上传（前端文档列表是否显示）
2. 检查是否触发了索引（查看"Upload & Index"的输出）
3. 检查 `storage/kbs/{kb_id}/index/` 下是否有 `chunks.json` 和 `embeddings.npy`
4. 如果有文档但无索引 → 点击"Re-index"
5. 如果索引存在但无结果 → 检查查询是否勾选了正确的 KB

### 问题 2：分析返回默认回退报告
**可能原因**：
- 未配置 `OPENAI_API_KEY`
- API Key 无效或欠费
- `OPENAI_BASE_URL` 错误
- 网络连接问题

**排查步骤**：
1. 检查 `.env` 文件中的 `OPENAI_API_KEY`
2. 查看服务器日志（终端输出）中是否有"LLM API call failed"
3. 手动测试 API：
   ```python
   import httpx
   headers = {"Authorization": "Bearer sk-xxx"}
   response = httpx.post("https://api.deepseek.com/chat/completions", 
                         headers=headers, 
                         json={"model": "deepseek-reasoner", "messages": [{"role": "user", "content": "hi"}]})
   print(response.json())
   ```

### 问题 3：DOCX 文件索引失败
**可能原因**：
- 文件损坏或加密
- 文件为 0 字节

**排查步骤**：
1. 检查服务器日志，看是否有"Failed to load docx"
2. 检查 `storage/kbs/{kb_id}/files/` 下的文件大小
3. 尝试用 Word 手动打开该文件，确认是否可读

### 问题 4：服务启动后路径错误
**症状**：
- 上传文档后找不到
- `.env` 配置不生效

**原因**：在 `src/` 目录下启动服务，相对路径全部错误

**解决**：
```bash
# 必须在项目根目录启动
cd C:\Users\81011\Desktop\Myrag
set PYTHONPATH=src
uvicorn esg_rag.main:app --port 8001
```

---

## 技术栈总结

| 层 | 技术 | 说明 |
|-------|------|------|
| **前端** | HTML + Vanilla JS + CSS | 无框架，轻量级 |
| **后端** | FastAPI + Uvicorn | 异步 Web 框架 |
| **文档解析** | pypdf, python-docx | PDF 和 DOCX 解析 |
| **Embedding** | sentence-transformers (all-MiniLM-L6-v2) | 本地 384 维向量 |
| **向量存储** | SimpleVectorStore (NumPy + JSON) | 可扩展为 ChromaDB / Milvus |
| **LLM** | DeepSeek API (deepseek-reasoner) | 流式 JSON 输出 |
| **配置管理** | pydantic-settings | 自动加载 `.env` |

---

## 部署建议

### 本地开发
```bash
pip install -e .
set PYTHONPATH=src
uvicorn esg_rag.main:app --reload --port 8001
```

### 生产部署（Linux/Docker）
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install .
COPY src/ src/
COPY .env .env
ENV PYTHONPATH=src
CMD ["uvicorn", "esg_rag.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

启动：
```bash
docker build -t esg-rag .
docker run -p 8001:8001 -v ./storage:/app/storage esg-rag
```

---

## 总结

ESG RAG 系统通过**知识库管理 + 多 Agent 协作 + LLM 生成**，实现了从文档上传到结构化报告的全自动化流程。核心优势：

1. **模块化** — 6 个 Agent 各司其职，易于维护和扩展
2. **透明性** — 所有证据可追溯，所有流程可审计（agent_trace）
3. **鲁棒性** — 多重错误处理，LLM 失败时自动降级
4. **可扩展** — 可替换 embedding 模型、向量存储、LLM 提供商
5. **用户友好** — Web UI 直观，无需命令行操作
