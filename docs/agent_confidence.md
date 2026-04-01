# ConfidenceAgent（置信度代理）说明文档

## 概述

**ConfidenceAgent** 对整个分析流程的**证据质量**进行综合评分，生成一个 0~1 的置信度分数和对应等级（low / medium / high），帮助用户判断报告的可靠性。

## 核心职责

- 基于**相似度分数**、**可追溯性**、**主题覆盖度**、**证据数量**四个维度，计算综合置信度
- 输出**置信度等级**和**数值评分**
- 提供**置信度原因**说明

## 输入参数

```python
def run(self, evidence: list[dict]) -> dict
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `evidence` | `list[dict]` | 来自 VerificationAgent 的已验证证据（包含 `tags`、`verification_notes`、`metadata`） |

## 处理逻辑

### 1. 边界情况处理
如果没有检索到任何证据：
```python
return {"level": "low", "score": 0.0, "reason": "No evidence retrieved."}
```

### 2. 计算四个子指标

#### a) 平均相似度分数（权重 55%）
```python
avg_score = sum(item["score"] for item in evidence) / len(evidence)
```
**含义**：所有证据的向量相似度均值。高分说明检索到的内容与查询高度相关。

#### b) 可追溯比例（权重 20%）
```python
traceable_ratio = sum(1 for item in evidence if "source" in item["metadata"]) / len(evidence)
```
**含义**：有 `source` 元数据的证据占比。1.0 表示所有证据都可以追溯到原始文档。

#### c) 主题覆盖比例（权重 15%）
```python
coverage_ratio = len({tag for item in evidence for tag in item.get("tags", []) if tag != "general"}) / 3
```
**含义**：去重后的标签数（environment、social、governance）/ 3。如果三个维度都有证据，`coverage_ratio = 1.0`。

#### d) 证据数量比例（权重 10%）
```python
evidence_volume = min(len(evidence) / 6, 1.0)
```
**含义**：证据数量 / 6，上限为 1.0。如果检索到 ≥6 条证据，该指标满分。

### 3. 综合评分公式

```python
numeric_score = (avg_score * 0.55) + (traceable_ratio * 0.2) + (coverage_ratio * 0.15) + (evidence_volume * 0.1)
```

**权重分配逻辑**：
- **相似度最重要**（55%）— 证据必须与查询强相关
- **可追溯性第二**（20%）— ESG 分析必须引用来源
- **覆盖度和数量**（15% + 10%）— 确保全面性

### 4. 等级映射

| 数值分数 | 置信度等级 |
|---------|-----------|
| ≥ 0.72 | `high` |
| 0.48 ~ 0.71 | `medium` |
| < 0.48 | `low` |

## 输出格式

```python
{
    "level": "high",           # 置信度等级
    "score": 0.782,            # 数值评分（0~1）
    "reason": "Blend of retrieval quality, traceability, topic coverage, and evidence volume."
}
```

## 典型评分示例

### 示例 1：高置信度场景
- 检索到 8 条证据
- 平均 score = 0.85（高相关性）
- 100% 可追溯（所有证据有 source）
- 覆盖 environment、social、governance 三个标签

**计算**：
```
(0.85 * 0.55) + (1.0 * 0.2) + (1.0 * 0.15) + (1.0 * 0.1)
= 0.4675 + 0.2 + 0.15 + 0.1
= 0.9175
```
**输出**：`{"level": "high", "score": 0.918, "reason": "..."}`

### 示例 2：低置信度场景
- 检索到 2 条证据
- 平均 score = 0.35（弱相关）
- 50% 可追溯（1 条有 source，1 条缺失）
- 只覆盖 1 个标签（environment）

**计算**：
```
(0.35 * 0.55) + (0.5 * 0.2) + (0.33 * 0.15) + (0.33 * 0.1)
= 0.1925 + 0.1 + 0.05 + 0.033
= 0.375
```
**输出**：`{"level": "low", "score": 0.375, "reason": "..."}`

## 在报告中的作用

1. **前端展示** — 用户看到的报告顶部会显示置信度徽章：
   ```
   confidence high | score 0.782
   ```

2. **决策依据** — 如果置信度为 `low`，用户应：
   - 补充更多文档到知识库
   - 检查查询是否太宽泛/模糊
   - 不应将报告直接用于对外披露

3. **质量门槛** — 可以在 API 层设置规则：置信度 < 0.5 时拒绝生成报告，要求用户先改进数据。
