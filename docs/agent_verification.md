# VerificationAgent（验证代理）说明文档

## 概述

**VerificationAgent** 对每条证据进行**可信度和可追溯性检查**，生成验证注释（verification notes），标记证据的质量和局限性。

## 核心职责

- 检查证据的**长度**、**相似度分数**、**来源可追溯性**
- 识别**数据质量问题**（如过短片段、低分数、缺失元数据）
- 生成**验证注释**，告知下游 agent 和最终用户该证据的可信度

## 输入参数

```python
def run(self, results: list[dict]) -> list[dict]
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `results` | `list[dict]` | 来自 EvidenceFusionAgent 的融合结果（已打标签） |

## 处理逻辑

遍历每条证据，执行以下检查：

### 1. 长度检查
```python
if len(result["text"]) < 120:
    notes.append("Short excerpt; inspect adjacent source context.")
```
**原因**：过短的片段可能被切片算法截断，缺少完整语境，需要回溯上下文。

### 2. 相似度检查
```python
if result["score"] < 0.2:
    notes.append("Similarity score is modest, so this evidence should be cross-checked.")
```
**原因**：低分数（< 0.2）意味着语义匹配不强，可能是弱相关或噪声数据。

### 3. 来源可追溯性检查
```python
if "source" not in metadata:
    notes.append("Missing source metadata.")
else:
    notes.append(f"Traceable source: {metadata.get('source_name', metadata['source'])}.")
```
**原因**：缺少 `source` 字段的证据无法追溯到原始文档，不适合作为正式引用。

### 4. 页码检查
```python
if metadata.get("page") is not None:
    notes.append(f"Page {metadata['page']} available for citation.")
```
**原因**：有页码的证据（PDF 文档）可以精确引用。

### 5. 数据类型检查
```python
if metadata.get("source_type") == "json":
    notes.append("Structured supplementary data; corroborate against narrative disclosures.")
```
**原因**：JSON 数据是结构化的，但可能缺少叙述性语境，需要与文本披露交叉验证。

## 输出格式

```python
[
    {
        ...原始字段（chunk_id, score, text, metadata, tags, excerpt）...
        "verification_notes": "Traceable source: GreenTech_ESG_Report.docx. Page 3 available for citation."
    },
    {
        ...
        "verification_notes": "Short excerpt; inspect adjacent source context. Similarity score is modest, so this evidence should be cross-checked. Missing source metadata."
    }
]
```

## 为什么需要验证？

ESG 分析的核心价值在于**可审计性和透明度**。VerificationAgent 确保：
- 用户知道哪些证据是**强证据**（高分、可追溯、有页码）
- 哪些证据是**弱证据**（低分、缺元数据、片段过短）
- 最终报告的**置信度评分**能反映证据质量

## 典型输出示例

**高质量证据**：
```
"Traceable source: GreenTech_ESG_Report.docx. Page 5 available for citation."
```

**低质量证据**：
```
"Short excerpt; inspect adjacent source context. Similarity score is modest, so this evidence should be cross-checked."
```

**缺元数据证据**：
```
"Missing source metadata."
```

## 在报告中的体现

用户在前端查看分析报告时，每条证据下方都会显示 `verification_notes`，例如：

> **Source**: GreenTech_ESG_Report.docx  
> **Score**: 0.823  
> **Excerpt**: GreenTech reduced Scope 1 and Scope 2 emissions by 18%...  
> **Verification**: Traceable source: GreenTech_ESG_Report.docx. Page 3 available for citation.

这让用户能够判断该证据是否适合引用到正式报告中。
