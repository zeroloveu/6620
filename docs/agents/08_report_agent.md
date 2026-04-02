# ReportAgent — 报告生成代理

## 概述
`ReportAgent` 是 ESG 分析流程的**最后一个**代理,负责生成结构化的 ESG 分析报告。它有两种工作模式:
1. **LLM 模式** — 调用外部大语言模型 (例如 DeepSeek、OpenAI) 生成定制化报告
2. **模板模式** (Fallback) — 当 LLM 不可用或调用失败时,使用规则生成标准化报告

## 核心职责
1. **汇总所有证据** — 整合前面 7 个 agent 的输出
2. **生成结构化报告** — 包含执行摘要、ESG 三大维度分析、合规评估、置信度评估、后续建议
3. **处理 LLM 响应** — 解析 LLM 的 JSON 输出,处理流式响应
4. **提供降级策略** — LLM 失败时自动切换到模板模式

## 输入参数
```python
def run(
    self,
    company_name: str,            # 公司名称
    user_query: str,              # 用户查询
    framework_focus: list[str],   # ESG 框架
    evidence: list[dict],         # 经过验证的证据列表
    compliance_alignment: dict,   # ComplianceAgent 的输出
    confidence_assessment: dict,  # ConfidenceAgent 的输出
    agent_trace: list[dict]       # TraceAgent 的输出
) -> dict:
```

## 输出结构
```python
{
    "executive_summary": "Tesla Inc. 的 ESG 表现在环境维度表现突出...",
    "environment": {
        "title": "Environment",
        "summary": "环境维度覆盖 5 条证据,重点关注碳排放管理...",
        "findings": ["Scope 1 排放下降 12%", "可再生能源占比 50%", ...],
        "risks": ["供应链碳排放数据不完整", "生物多样性披露较弱", ...],
        "opportunities": ["扩大碳信用项目", "投资碳捕获技术", ...],
        "evidence": [
            {
                "source": "tesla_esg_2024.pdf",
                "page": 15,
                "score": 0.856,
                "excerpt": "Tesla's Scope 1 emissions decreased by 12%...",
                "verification_notes": "Traceable source: tesla_esg_2024.pdf. Page 15 available for citation."
            },
            ...
        ]
    },
    "social": { /* 同 environment 结构 */ },
    "governance": { /* 同 environment 结构 */ },
    "compliance_alignment": { /* ComplianceAgent 的输出 */ },
    "confidence_assessment": { /* ConfidenceAgent 的输出 */ },
    "next_steps": [
        "Review cited evidence against full source context before external use.",
        "Add more benchmark and company disclosures to improve framework coverage.",
        ...
    ],
    "agent_trace": [ /* TraceAgent 的输出 */ ]
}
```

## 工作流程

### 1. 判断是否启用 LLM
```python
if not self.settings.openai_api_key:
    return self._fallback_report(...)  # 无 API Key,使用模板模式
```

### 2. LLM 模式 — 构造 Prompt
```python
evidence_text = "\n\n".join([
    f"Source: {item['metadata'].get('source', 'unknown')}\n"
    f"Page: {item['metadata'].get('page')}\n"
    f"Score: {item['score']:.4f}\n"
    f"Tags: {', '.join(item.get('tags', []))}\n"
    f"Verification: {item['verification_notes']}\n"
    f"Excerpt:\n{item['text']}"
    for item in evidence
])

prompt = f"""
Company: {company_name}
User request: {user_query}
Framework focus: {", ".join(framework_focus)}
Compliance alignment input: {compliance_alignment}
Confidence assessment input: {confidence_assessment}
Agent trace summary: {agent_trace}

You must produce a structured ESG analysis with Environment, Social, Governance,
compliance alignment, confidence assessment, and next steps.
Use only the evidence below and be explicit about gaps.

Evidence:
{evidence_text}
""".strip()
```

**Prompt 设计原则**:
- **明确输出格式** — 要求 LLM 返回 JSON,并在 `SYSTEM_PROMPT` 中给出完整的 schema
- **证据驱动** — 所有证据的元数据 (来源、页码、分数、验证备注) 都包含在 prompt 中
- **透明度要求** — 明确要求 LLM"如果证据不足,必须在报告中说明"

### 3. LLM 模式 — 调用 API (流式响应)
```python
def _chat_report(self, prompt: str) -> dict:
    payload = {
        "model": self.settings.openai_chat_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "stream": True  # 启用流式响应
    }
    
    timeout = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=30.0)
    content_parts = []
    
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", url, headers=headers, json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
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
    return _extract_json(content)  # 从 LLM 响应中提取 JSON
```

**关键配置**:
- **超时设置** — `read=600.0` (10 分钟),因为 DeepSeek 的 reasoning 模型响应较慢
- **流式处理** — 使用 `stream=True` 避免长时间阻塞,实时获取响应片段
- **JSON 提取** — 使用 `_extract_json()` 处理 LLM 可能返回的 markdown 代码块 (例如 ` ```json\n{...}\n``` `)

### 4. 模板模式 (Fallback)
当 LLM 不可用时,使用规则生成报告:

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
    executive_anchor = " ".join(evidence摘要...)
    
    # 2. 按标签筛选证据,生成三大维度分析
    environment = _section_from_evidence("Environment", "environment", evidence)
    social = _section_from_evidence("Social", "social", evidence)
    governance = _section_from_evidence("Governance", "governance", evidence)
    
    # 3. 生成后续建议
    weak_frameworks = [f for f in compliance_alignment if f["coverage"] in {"low", "limited"}]
    next_steps = [
        "Review cited evidence against full source context...",
        "Add more benchmark and company disclosures...",
        f"Strengthen evidence for: {', '.join(weak_frameworks)}." if weak_frameworks else None
    ]
    
    return {
        "executive_summary": f"Fallback mode produced this ESG draft for {company_name}...",
        "environment": environment,
        "social": social,
        "governance": governance,
        "compliance_alignment": compliance_alignment,
        "confidence_assessment": confidence_assessment,
        "next_steps": [s for s in next_steps if s]
    }
```

**模板模式的特点**:
- **快速生成** — 无需等待 LLM 响应,延迟 < 100ms
- **可预测** — 输出格式固定,便于测试和调试
- **证据驱动** — 依然基于检索到的证据生成分析,只是缺少 LLM 的深度解读

## _section_from_evidence 函数详解

该函数根据 ESG 标签筛选证据,生成单个维度的分析章节:

```python
def _section_from_evidence(title: str, tag: str, evidence: list[dict]) -> dict:
    # 1. 筛选带有指定标签的证据
    tagged = [item for item in evidence if tag in item.get("tags", [])]
    selected = tagged[:3]  # 选择前 3 条最相关的证据
    
    # 2. 如果无证据,返回空章节
    if not selected:
        return {
            "title": title,
            "summary": f"No strong {title.lower()} evidence was retrieved...",
            "findings": ["Current retrieval did not surface enough direct evidence..."],
            "risks": ["Expand indexed disclosures or refine the query..."],
            "opportunities": [f"Add more {title.lower()}-specific reports..."],
            "evidence": []
        }
    
    # 3. 生成章节内容
    findings = [compact(item.get("excerpt") or item["text"]) for item in selected]
    low_confidence = any("modest" in item.get("verification_notes", "").lower() for item in selected)
    
    summary = f"{title} coverage is supported by {len(tagged)} retrieved evidence snippet(s)..."
    
    risks = []
    if len(tagged) < 2:
        risks.append(f"{title} coverage is thin...")
    if low_confidence:
        risks.append("Some supporting evidence has only moderate retrieval confidence.")
    
    opportunities = [
        f"Use the cited {title.lower()} evidence as the base for analyst review...",
    ]
    
    return {
        "title": title,
        "summary": summary,
        "findings": findings,
        "risks": risks,
        "opportunities": opportunities,
        "evidence": [_evidence_item(item) for item in selected]
    }
```

## LLM 响应处理

### 1. JSON 提取 (_extract_json)
LLM 可能返回三种格式:
1. **纯 JSON**: `{"executive_summary": "...", ...}`
2. **Markdown 代码块**: ` ```json\n{"executive_summary": "...", ...}\n``` `
3. **混合格式**: `Here is the report:\n\`\`\`json\n{...}\n\`\`\``

`_extract_json` 使用正则表达式处理所有格式:
```python
def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)
```

### 2. 错误处理
```python
try:
    return self._chat_report(prompt)
except Exception:
    logger.exception("LLM API call failed, falling back to template report")
    return self._fallback_report(...)
```

**可能的错误**:
- **网络超时** — LLM API 响应时间超过 600 秒
- **API Key 失效** — 返回 401 Unauthorized
- **速率限制** — 返回 429 Too Many Requests
- **JSON 解析失败** — LLM 返回的不是有效 JSON

## 在流程中的位置
```
PlannerAgent → RetrievalAgent → EvidenceFusionAgent → VerificationAgent
                                        ↓
                            ComplianceAgent + ConfidenceAgent
                                        ↓
                                  TraceAgent
                                        ↓
                                  ReportAgent (生成最终报告)
                                        ↓
                                    用户界面
```

## 设计原理

### 为什么使用流式响应 (stream=True)?
- **降低延迟感知** — 用户可以实时看到 LLM 生成的内容,而不是等待 10 分钟后一次性返回
- **避免超时** — 某些代理服务器 (例如 Nginx) 默认 60 秒超时,流式响应可以保持连接活跃
- **容错性** — 如果 LLM 生成过程中断,已生成的部分内容不会丢失

### 为什么要设置 600 秒的 read 超时?
- **DeepSeek Reasoner 模型** — 该模型会进行长时间的"思考"(reasoning),响应时间可能达到 5-10 分钟
- **复杂查询** — 当证据数量较多 (例如 20 条证据,每条 1000 字符),prompt 的 token 数量可能达到 50k+,LLM 生成时间较长

### 为什么模板模式要保留 "Fallback mode" 标识?
- **透明度** — 让用户知道该报告是由规则生成,而非 LLM 生成,降低对报告深度的期望
- **调试** — 方便开发者排查 LLM 调用失败的原因

## 扩展建议

### 1. 支持多模型回退
```python
models = ["deepseek-reasoner", "gpt-4", "gpt-3.5-turbo"]
for model in models:
    try:
        return self._chat_report(prompt, model)
    except Exception:
        logger.warning(f"Model {model} failed, trying next...")
return self._fallback_report(...)
```

### 2. 缓存 LLM 响应
对于相同的查询和证据,缓存 LLM 响应:
```python
cache_key = hashlib.md5((company_name + user_query + str(evidence)).encode()).hexdigest()
if cache_key in report_cache:
    return report_cache[cache_key]
report = self._chat_report(prompt)
report_cache[cache_key] = report
return report
```

### 3. 增量更新流式输出
前端可以实时显示 LLM 生成的内容:
```python
def stream_report(self, ...):
    for chunk in self._stream_chat(prompt):
        yield {"type": "delta", "content": chunk}
    yield {"type": "done", "report": final_report}
```

### 4. 多语言报告生成
在 `SYSTEM_PROMPT` 中指定输出语言:
```python
SYSTEM_PROMPT = f"""
You are an ESG analyst. Respond in {language} language.
...
"""
```

## 常见问题

**Q: 为什么 LLM 生成的报告与模板模式的报告结构不同?**  
A: LLM 可能会根据证据内容自由发挥,生成更详细的分析。如果需要确保输出结构一致,可以在 `SYSTEM_PROMPT` 中添加更严格的 JSON schema 约束。

**Q: 如何判断当前报告是 LLM 生成的还是模板生成的?**  
A: 检查 `executive_summary` 字段是否包含 "Fallback mode" 字样。

**Q: 为什么 LLM 有时返回不完整的 JSON?**  
A: 可能原因:
1. LLM 上下文窗口不足,截断了响应
2. 流式响应中断 (网络问题)
3. LLM 生成的 JSON 本身就不完整 (模型能力问题)

**解决方案**: 增加错误处理,尝试修复不完整的 JSON,或降级到模板模式。

---

**相关文档**:
- [TraceAgent — 追踪记录代理](./07_trace_agent.md)
- [LLMClient — 大语言模型客户端](./09_llm_client.md)
- [ComplianceAgent — 合规评估代理](./05_compliance_agent.md)
- [ConfidenceAgent — 置信度评分代理](./06_confidence_agent.md)
