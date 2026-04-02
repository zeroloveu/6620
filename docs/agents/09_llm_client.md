# LLMClient — 大语言模型客户端

## 概述
`LLMClient` 封装了与外部大语言模型 (LLM) API 的交互逻辑,为 `ReportAgent` 提供报告生成能力。支持 OpenAI 兼容 API (例如 DeepSeek、OpenAI、Azure OpenAI)。

## 核心职责
1. **API 调用封装** — 处理 HTTP 请求、超时、重试、错误处理
2. **流式响应解析** — 处理 Server-Sent Events (SSE) 格式的流式数据
3. **JSON 提取** — 从 LLM 响应中提取 JSON 对象 (支持 markdown 代码块)
4. **降级策略** — LLM 调用失败时自动切换到模板模式

## 配置参数 (来自 Settings)
```python
class Settings:
    openai_api_key: str = ""                      # API Key (例如 DeepSeek 的 sk-xxx)
    openai_base_url: str = "https://api.deepseek.com"  # API 基础 URL
    openai_chat_model: str = "deepseek-reasoner"  # 模型名称
```

## 核心方法

### 1. structured_esg_report (主入口)
```python
def structured_esg_report(
    self,
    prompt: str,                     # 完整的分析 prompt
    company_name: str,               # 公司名称
    evidence: list[dict],            # 证据列表
    compliance_alignment: dict,      # 合规评估结果
    confidence_assessment: dict      # 置信度评估结果
) -> dict:
```

**工作流程**:
```python
if not self.settings.openai_api_key:
    return self._fallback_report(...)  # 无 API Key,使用模板模式

try:
    return self._chat_report(prompt)  # 调用 LLM API
except Exception:
    logger.exception("LLM API call failed")
    return self._fallback_report(...)  # LLM 失败,降级到模板模式
```

### 2. _chat_report (LLM API 调用)
```python
def _chat_report(self, prompt: str) -> dict:
    headers = {
        "Authorization": f"Bearer {self.settings.openai_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": self.settings.openai_chat_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "stream": True
    }
    
    url = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
    timeout = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=30.0)
    
    content_parts = []
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", url, headers=headers, json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {})
                if "content" in delta and delta["content"]:
                    content_parts.append(delta["content"])
    
    content = "".join(content_parts)
    if not content:
        raise ValueError("LLM returned empty content")
    
    return _extract_json(content)
```

**关键配置**:
- **流式响应** — `"stream": True` 避免长时间阻塞
- **超时设置** — `read=600.0` (10 分钟) 适配 DeepSeek Reasoner 的长思考时间
- **错误处理** — `response.raise_for_status()` 抛出 HTTP 错误,触发降级逻辑

### 3. _extract_json (JSON 提取)
```python
def _extract_json(text: str) -> dict:
    text = text.strip()
    # 尝试匹配 markdown 代码块: ```json\n{...}\n```
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)
```

**处理三种格式**:
1. **纯 JSON**: `{"executive_summary": "..."}`
2. **Markdown 代码块**: ` ```json\n{"executive_summary": "..."}\n``` `
3. **带语言标记**: ` ```json\n{"executive_summary": "..."}\n``` `

### 4. _fallback_report (模板模式)
```python
def _fallback_report(
    self,
    company_name: str,
    evidence: list[dict],
    compliance_alignment: dict,
    confidence_assessment: dict
) -> dict:
    # 1. 生成执行摘要
    top_evidence = evidence[:3]
    executive_anchor = shorten(" ".join(摘要...), width=320)
    
    # 2. 识别薄弱框架
    weak_frameworks = [
        framework for framework, payload in compliance_alignment.items()
        if payload.get("coverage") in {"low", "limited"}
    ]
    
    # 3. 生成后续建议
    next_steps = [
        "Review cited evidence against full source context...",
        "Add more benchmark and company disclosures...",
    ]
    if weak_frameworks:
        next_steps.append(f"Strengthen evidence for: {', '.join(weak_frameworks)}.")
    if confidence_assessment.get("level") != "high":
        next_steps.append("Re-run analysis after indexing more source material...")
    
    # 4. 按标签生成三大维度分析
    return {
        "executive_summary": f"Fallback mode produced this ESG draft for {company_name}...",
        "environment": _section_from_evidence("Environment", "environment", evidence),
        "social": _section_from_evidence("Social", "social", evidence),
        "governance": _section_from_evidence("Governance", "governance", evidence),
        "compliance_alignment": compliance_alignment,
        "confidence_assessment": confidence_assessment,
        "next_steps": next_steps
    }
```

## SYSTEM_PROMPT 设计

```python
SYSTEM_PROMPT = """\
You are an ESG analyst. Use only supplied evidence. \
If evidence is weak, say so explicitly.

You MUST respond with a valid JSON object (no markdown fences, no extra text) \
matching this structure:
{
  "executive_summary": "string",
  "environment": {
    "title": "string",
    "summary": "string",
    "findings": ["..."],
    "risks": ["..."],
    "opportunities": ["..."],
    "evidence": [{"source": "string", "page": null, "score": 0.0, "excerpt": "string", "verification_notes": "string"}]
  },
  "social": { same structure as environment },
  "governance": { same structure as environment },
  "compliance_alignment": { ... },
  "confidence_assessment": { ... },
  "next_steps": ["string"]
}"""
```

**设计原则**:
1. **明确角色** — "You are an ESG analyst" 限定输出风格
2. **证据驱动** — "Use only supplied evidence" 避免 LLM 自由发挥
3. **透明度要求** — "If evidence is weak, say so explicitly" 确保报告诚实
4. **严格格式** — "valid JSON object (no markdown fences)" 降低解析失败率
5. **Schema 约束** — 提供完整的 JSON 结构示例

## 流式响应处理

### SSE (Server-Sent Events) 格式
```
data: {"choices": [{"delta": {"role": "assistant", "content": "{"}}]}

data: {"choices": [{"delta": {"content": "\"executive_summary\": \""}}]}

data: {"choices": [{"delta": {"content": "Tesla Inc. demonstrates"}}]}

data: [DONE]
```

### 解析逻辑
```python
for line in response.iter_lines():
    line = line.strip()
    if not line or not line.startswith("data: "):
        continue  # 跳过空行和非数据行
    
    data = line[6:]  # 去除 "data: " 前缀
    if data == "[DONE]":
        break  # 结束标记
    
    chunk = json.loads(data)
    delta = chunk["choices"][0].get("delta", {})
    if "content" in delta and delta["content"]:
        content_parts.append(delta["content"])  # 拼接内容片段
```

## 超时配置详解

```python
timeout = httpx.Timeout(
    connect=15.0,   # 建立连接的最大时间
    read=600.0,     # 读取响应的最大时间 (10 分钟)
    write=30.0,     # 发送请求的最大时间
    pool=30.0       # 获取连接池连接的最大时间
)
```

### 为什么 read 超时设置为 600 秒?
- **DeepSeek Reasoner** — 该模型会进行长时间的"推理"(reasoning),响应时间可能达到 5-10 分钟
- **复杂 prompt** — 当证据数量较多 (例如 20 条,每条 1000 字符),prompt 的 token 数量可能达到 50k+,生成时间较长
- **流式响应** — 流式模式下,`read` 超时是指"每次读取数据块的间隔",而不是总响应时间

## 错误处理策略

### 1. HTTP 错误
```python
try:
    response.raise_for_status()
except httpx.HTTPStatusError as e:
    logger.error(f"LLM API returned {e.response.status_code}: {e.response.text}")
    raise
```

**常见错误码**:
- `401 Unauthorized` — API Key 无效或过期
- `429 Too Many Requests` — 超过速率限制
- `500 Internal Server Error` — LLM 服务异常
- `504 Gateway Timeout` — LLM 响应超时

### 2. 网络超时
```python
except httpx.TimeoutException:
    logger.error(f"LLM API timeout after {timeout.read}s")
    raise
```

### 3. JSON 解析失败
```python
try:
    return _extract_json(content)
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse LLM response as JSON: {e}")
    logger.debug(f"Raw response: {content[:500]}")  # 记录前 500 字符
    raise
```

### 4. 空响应
```python
if not content:
    raise ValueError("LLM returned empty content")
```

## 辅助函数

### 1. _compact_text (文本压缩)
```python
def _compact_text(text: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit - 3].rstrip() + "..."
```

**用途**: 将多行文本压缩为单行,用于生成 `excerpt` 字段。

### 2. _evidence_item (证据格式化)
```python
def _evidence_item(item: dict) -> dict:
    metadata = item.get("metadata", {})
    return {
        "source": metadata.get("source_name", metadata.get("source", "unknown")),
        "page": metadata.get("page"),
        "score": round(float(item.get("score", 0.0)), 3),
        "excerpt": _compact_text(item.get("excerpt") or item.get("text", "")),
        "verification_notes": item.get("verification_notes", "Evidence retrieved from indexed sources.")
    }
```

**用途**: 将内部证据格式转换为报告输出格式 (去除冗余字段,压缩文本)。

### 3. _section_from_evidence (章节生成)
```python
def _section_from_evidence(title: str, tag: str, evidence: list[dict]) -> dict:
    tagged = [item for item in evidence if tag in item.get("tags", [])]
    selected = tagged[:3]
    
    if not selected:
        return {
            "title": title,
            "summary": f"No strong {title.lower()} evidence was retrieved...",
            "findings": ["Current retrieval did not surface enough direct evidence..."],
            "risks": ["Expand indexed disclosures or refine the query..."],
            "opportunities": [f"Add more {title.lower()}-specific reports..."],
            "evidence": []
        }
    
    findings = [_compact_text(item.get("excerpt") or item.get("text", "")) for item in selected]
    low_confidence = any("modest" in item.get("verification_notes", "").lower() for item in selected)
    
    summary = f"{title} coverage is supported by {len(tagged)} retrieved evidence snippet(s)..."
    
    risks = []
    if len(tagged) < 2:
        risks.append(f"{title} coverage is thin...")
    if low_confidence:
        risks.append("Some supporting evidence has only moderate retrieval confidence.")
    if not risks:
        risks.append("Evidence is traceable, but conclusions should still be reviewed...")
    
    opportunities = [
        f"Use the cited {title.lower()} evidence as the base for analyst review...",
    ]
    if len(tagged) < 3:
        opportunities.append(f"Index additional {title.lower()} documents to improve coverage depth.")
    
    return {
        "title": title,
        "summary": summary,
        "findings": findings,
        "risks": risks,
        "opportunities": opportunities,
        "evidence": [_evidence_item(item) for item in selected]
    }
```

## 扩展建议

### 1. 支持多模型回退
```python
models = ["deepseek-reasoner", "gpt-4o", "gpt-3.5-turbo"]
for model in models:
    try:
        return self._chat_report_with_model(prompt, model)
    except Exception as e:
        logger.warning(f"Model {model} failed: {e}, trying next...")
return self._fallback_report(...)
```

### 2. 增加重试逻辑
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _chat_report(self, prompt: str) -> dict:
    # ... API 调用 ...
```

### 3. Token 计数与成本估算
```python
import tiktoken

encoder = tiktoken.encoding_for_model("gpt-4")
prompt_tokens = len(encoder.encode(prompt))
logger.info(f"Prompt tokens: {prompt_tokens}, estimated cost: ${prompt_tokens * 0.00003:.4f}")
```

### 4. 缓存 LLM 响应
```python
from functools import lru_cache
import hashlib

def _cache_key(prompt: str) -> str:
    return hashlib.md5(prompt.encode()).hexdigest()

@lru_cache(maxsize=128)
def _cached_chat_report(self, cache_key: str, prompt: str) -> dict:
    return self._chat_report(prompt)
```

## 常见问题

**Q: 为什么使用流式响应而不是普通响应?**  
A: 流式响应有三个优势:
1. 降低延迟感知 (用户可以实时看到生成进度)
2. 避免超时 (某些代理服务器 60 秒无数据就断开连接)
3. 容错性更好 (即使中途断开,已生成的部分也能保留)

**Q: 如何判断 LLM 是否支持流式响应?**  
A: 查看 API 文档,或尝试发送 `"stream": True` 请求。如果 API 不支持,通常会返回错误或忽略该参数。

**Q: 为什么有时 LLM 返回的 JSON 不完整?**  
A: 可能原因:
1. LLM 上下文窗口不足,截断了响应
2. 流式响应中断 (网络问题)
3. LLM 生成能力不足 (例如某些小模型无法严格遵循 JSON 格式)

**解决方案**: 增加 JSON 修复逻辑,或降级到模板模式。

---

**相关文档**:
- [ReportAgent — 报告生成代理](./08_report_agent.md)
- [配置管理 — Settings](../modules/config.md)
