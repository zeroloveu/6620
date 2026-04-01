# ComplianceAgent（合规代理）说明文档

## 概述

**ComplianceAgent** 评估检索到的证据与 ESG 披露框架（GRI、SASB、TCFD、CSRD）的**对齐程度**，生成每个框架的覆盖度评分和主题分布。

## 核心职责

- 为每个指定的 ESG 框架计算**覆盖度等级**（high / moderate / limited / low）
- 统计**匹配证据数量**和**覆盖的主题标签**
- 提取**框架相关证据摘要**（最多 3 条）

## 输入参数

```python
def run(self, framework_focus: list[str], evidence: list[dict]) -> dict
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `framework_focus` | `list[str]` | 用户关注的框架列表（如 `["GRI", "SASB", "TCFD"]`） |
| `evidence` | `list[dict]` | 来自 VerificationAgent 的已验证证据（包含 `tags` 和 `verification_notes`） |

## 处理逻辑

### 1. 规范化框架
将输入转为大写标准形式，默认为 `["GRI", "SASB", "TCFD", "CSRD"]`。

### 2. 框架匹配规则

对每个框架，根据证据的 `tags` 字段判断是否匹配：

| 框架 | 匹配规则 |
|------|----------|
| **TCFD** | 只匹配 `environment` 标签（TCFD 专注气候披露） |
| **SASB** | 匹配 `environment`、`social`、`governance` 任一标签（SASB 全维度） |
| **GRI / CSRD** | 匹配所有证据（GRI 和 CSRD 是通用框架） |

### 3. 覆盖度评级

根据匹配证据数量计算覆盖度：

| 匹配证据数 | 覆盖度等级 |
|-----------|-----------|
| ≥ 4 | `high` |
| 2~3 | `moderate` |
| 1 | `limited` |
| 0 | `low` |

### 4. 统计覆盖主题

从匹配证据的 `tags` 中收集去重后的标签列表（排除 `general`），表示该框架覆盖了哪些 ESG 维度。

## 输出格式

```python
{
    "GRI": {
        "coverage": "high",
        "matched_evidence_count": 6,
        "covered_topics": ["environment", "social", "governance"],
        "notes": [
            "GreenTech reduced Scope 1 and Scope 2 emissions by 18%...",
            "Conducted diversity training for all employees...",
            "Added two independent directors to the board..."
        ]
    },
    "SASB": {
        "coverage": "moderate",
        "matched_evidence_count": 3,
        "covered_topics": ["environment", "social"],
        "notes": [...]
    },
    "TCFD": {
        "coverage": "limited",
        "matched_evidence_count": 1,
        "covered_topics": ["environment"],
        "notes": [...]
    },
    "CSRD": {
        "coverage": "high",
        "matched_evidence_count": 5,
        "covered_topics": ["environment", "governance", "social"],
        "notes": [...]
    }
}
```

## 为什么需要合规评估？

不同的 ESG 框架有不同的侧重点：
- **TCFD** 只关注气候相关财务信息披露
- **SASB** 按行业分类，侧重财务重要性
- **GRI** 和 **CSRD** 是通用框架，覆盖广泛

ComplianceAgent 帮助用户了解：
- **当前知识库对哪些框架支持良好**（high coverage）
- **哪些框架缺乏证据**（low coverage）→ 需要补充相关文档
- **报告符合哪些标准**（用于对外披露）

## 典型使用场景

**场景 1：投资机构要求 TCFD 披露**
- 查看 `TCFD.coverage`：如果是 `low`，说明需要补充气候风险相关文档

**场景 2：供应商审核要求 GRI 对齐**
- 查看 `GRI.covered_topics`：如果只有 `["environment"]`，说明社会和治理维度数据不足

**场景 3：欧盟 CSRD 合规**
- 查看 `CSRD.matched_evidence_count`：如果 < 3，说明披露不完整

## 前端展示

在 Analysis 报告的 **Compliance** 区块中，用户会看到：

> **GRI**  
> high coverage  
> 6 hits  
> Topics: environment, social, governance

这让用户一目了然地知道当前知识库对该框架的支持程度。
