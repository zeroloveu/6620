# LLMClient（大语言模型客户端）说明文档

## 概述

**LLMClient** 是 ReportAgent 的底层组件，负责与 **OpenAI 兼容的 LLM API**（如 DeepSeek、OpenAI）通信，将检索到的证据和分析要求转化为结构化的 ESG 报告。

## 核心职责

- 调用 `/chat/completions` API，使用**流式传输**（streaming）避免超时
- 解析 LLM 的 JSON 输出（可能带 markdown 代码块）
- 提供**回退报告生成**，在 LLM 不可用时保证系统可用性

## 关键方法

### 1. `structured_esg_report()` — 主入口

```python
def structured_esg_report(
    self,
    prompt: str,
    company_name: str,
    evidence: list[dict],
    compliance_alignment: dict,
    confidence_assessment: dict,
) -> dict
```

**逻辑**：
1. 检查是否配置了 `openai_api_key`
   - 没有 → 直接返回回退报告
   - 有 → 尝试调用 `_chat_report()`
2. 如果 API 调用失败，捕获异常并记录日志，返回回退报告

### 2. `_chat_report()` — LLM 调用核心

```python
def _chat_report(self, prompt: str) -> dict
```

**关键实现细节**：

#### a) 使用流式传输
```python
payload = {
    "model": self.settings.openai_chat_model,  # 如 "deepseek-reasoner"
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ],
    "stream": True  # 关键！避免长时间无响应导致连接关闭
}
```

**为什么必须用流式？**
- DeepSeek 的 `deepseek-reasoner` 模型推理时间可能长达 30~120 秒
- 非流式请求会在服务器生成完整响应后才返回，期间连接可能超时
- 流式传输每生成一段就发送一次，保持连接活跃

#### b) 超大 read timeout
```python
timeout = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=30.0)
```
- `read=600.0` — 10 分钟读超时，适配推理模型的长生成时间

#### c) 解析流式响应
```python
with client.stream("POST", url, headers=headers, json=payload) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            delta = chunk["choices"][0].get("delta", {})
            if "content" in delta:
                content_parts.append(delta["content"])
content = "".join(content_parts)
```

#### d) 提取 JSON
```python
return _extract_json(content)
```
LLM 可能返回：
```
```json
{"executive_summary": "..."}
```
```
或直接返回纯 JSON。`_extract_json()` 会去掉 markdown fence，解析 JSON。

### 3. `_fallback_report()` — 回退报告生成器

当 LLM 不可用时，使用预定义规则生成报告：

```python
def _fallback_report(
    self,
    company_name: str,
    evidence: list[dict],
    compliance_alignment: dict,
    confidence_assessment: dict,
) -> dict
```

**逻辑**：
1. **Executive Summary** — 从前 3 条证据的摘要拼接而成，明确标注为"Fallback mode"
2. **三大维度** — 调用 `_section_from_evidence()` 生成：
   - 如果有对应标签的证据 → 展示证据摘要 + 基础风险/机会
   - 如果无证据 → 明确说明"无强证据"，建议补充文档
3. **Next Steps** — 根据覆盖度低的框架和置信度生成改进建议

**示例回退输出**：
```python
{
    "executive_summary": "Fallback mode produced this ESG draft for GreenTech using retrieved evidence only. Key evidence includes: Reduced GHG emissions by 18%...",
    "environment": {
        "title": "Environment",
        "summary": "Environment coverage is supported by 3 retrieved evidence snippet(s) from indexed sources.",
        "findings": ["Reduced Scope 1 and Scope 2 emissions...", ...],
        "risks": ["Evidence is traceable, but conclusions should still be reviewed..."],
        "opportunities": ["Use the cited environment evidence as the base for analyst review..."],
        "evidence": [...]
    },
    "social": {...},
    "governance": {...},
    "compliance_alignment": {...},
    "confidence_assessment": {...},
    "next_steps": [
        "Review cited evidence against full source context before external use.",
        "Add more benchmark and company disclosures to improve framework coverage.",
        "Strengthen evidence for: TCFD."
    ]
}
```

## SYSTEM_PROMPT（系统提示词）

嵌入在 `llm.py` 中的系统提示词：

```
You are an ESG analyst. Use only supplied evidence. 
If evidence is weak, say so explicitly.

You MUST respond with a valid JSON object (no markdown fences, no extra text) 
matching this structure:
{
  "executive_summary": "string",
  "environment": { "title": "string", "summary": "string", "findings": [...], "risks": [...], "opportunities": [...], "evidence": [...] },
  "social": { same structure },
  "governance": { same structure },
  "compliance_alignment": { ... },
  "confidence_assessment": { ... },
  "next_steps": ["string"]
}
```

**关键约束**：
- **只使用提供的证据** — 不允许 LLM 编造内容
- **明确说明弱证据** — 如果证据不足，必须在报告中标注
- **严格遵循 JSON schema** — 输出必须可解析

## 错误处理机制

LLMClient 有三层防护：

### 第 1 层：API Key 检查
```python
if not self.settings.openai_api_key:
    return self._fallback_report(...)
```

### 第 2 层：API 调用异常捕获
```python
try:
    return self._chat_report(prompt)
except Exception:
    logger.exception("LLM API call failed, falling back to template report")
    return self._fallback_report(...)
```

### 第 3 层：空响应检查
```python
content = "".join(content_parts)
if not content:
    raise ValueError("LLM returned empty content")
```

**结果**：无论任何情况（无 API key、网络故障、超时、返回格式错误），系统都能返回一个有效的报告。

## 流式传输的重要性

### 问题背景
DeepSeek 的 `deepseek-reasoner` 模型在生成复杂 JSON 时：
- 推理时间：30~120 秒
- 非流式请求会一直等待完整响应，期间没有任何数据传输
- HTTP 连接可能因"无活动"而被中间代理（nginx、防火墙）关闭

### 流式解决方案
```python
"stream": True
```
- 服务器每生成一段（如 50 字符）就立即发送一个 SSE chunk
- 客户端持续接收数据 → 连接保持活跃
- 所有 chunk 拼接后得到完整响应

**对比**：
| | 非流式 | 流式 |
|---|---|---|
| 延迟感知 | 长时间无响应（用户以为死机） | 持续收到数据（有进度感） |
| 超时风险 | 高（可能 60 秒后被断开） | 低（只要在生成就有数据） |
| 适用场景 | 快速模型（< 10s） | 推理模型（30s ~ 分钟级） |

## 典型执行流程

### 场景 1：LLM 正常生成
```
ReportAgent → LLMClient.structured_esg_report()
  → _chat_report()
    → POST /chat/completions (stream=True)
    → 收到 120 个 SSE chunks
    → 拼接为完整 JSON
    → _extract_json() 解析
    → 返回报告
```
**耗时**：30~90 秒（取决于模型）

### 场景 2：LLM 失败，回退生成
```
ReportAgent → LLMClient.structured_esg_report()
  → _chat_report()
    → POST /chat/completions
    → httpx.ReadTimeout (网络故障)
    → 捕获异常
  → _fallback_report()
    → 使用规则模板生成
    → 返回回退报告
```
**耗时**：< 1 秒

## 配置要求

在 `.env` 中配置：
```ini
OPENAI_API_KEY=sk-xxxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_CHAT_MODEL=deepseek-reasoner
```

**DeepSeek 配置示例**（当前项目使用）：
- Base URL: `https://api.deepseek.com`
- Model: `deepseek-reasoner`（推理增强模型，适合结构化输出）

**OpenAI 配置示例**：
- Base URL: `https://api.openai.com/v1`
- Model: `gpt-4o` 或 `gpt-4-turbo`

## 前端用户体验

- **LLM 模式**：用户点"Generate report"后等待 30~60 秒，看到高质量分析
- **回退模式**：用户点击后 < 1 秒返回，但报告开头会标注"Fallback mode produced..."

无论哪种模式，用户都能看到结构化的 ESG 报告，只是深度和叙述质量不同。
