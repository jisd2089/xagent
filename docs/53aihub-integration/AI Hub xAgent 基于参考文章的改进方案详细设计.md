# AI Hub xAgent 生产级改进方案 —— 基于"从零设计生产级 Multi-Agent Harness"方法论

版本：v1.0
日期：2026-05-14
参考文章：Tencent Cloud #2668186《从零设计生产级 Multi-Agent Harness：架构、评估、记忆、成本与 MCP 工具接入全拆解》
作者：李伟山（2026-05-13）

---

## 0. 文档导航

本文档是对参考文章方法论的逐章分析和改进方案映射。每个章节遵循统一格式：

> **文章方法论** → **当前系统现状** → **差距分析** → **改进方案** → **验收指标**

各改进项的详细实施方案分布在以下配套文档中：

| 改进方向 | 配套实施文档 |
| --- | --- |
| System Prompt 工程与输出质量保障 | `AI Hub xAgent 系统提示词工程与输出质量保障方案.md` |
| 三层质量保障体系架构 | `AI Hub xAgent 集成需求设计文档.md` §5.5.5 |
| Quality Gate 验收验证 | `AI Hub xAgent 前端验证流程操作文档.md` §12.4.7 |
| Quality Gate 测试矩阵 | `AI Hub xAgent 端到端测试验证矩阵方案.md` §8.1.7 |
| Agent Builder 部署配置 | `AI Hub xAgent 部署文档.md` §4.8 |

---

## 1. 总体诊断：当前系统的 Harness 成熟度评估

### 1.1 参考文章核心论断

> "Harness 是 Agent 的'操作系统'，而非'多 Prompt 拼盘'。它负责编排、调度、记忆、状态、工具治理、预算控制、可观测性、安全边界。"
> "Agent 负责局部智能，Harness 负责全局控制。"
> "Planner 应输出声明式计划，而非命令式调用。"

### 1.2 当前系统 Harness 评分

以参考文章的 8 大 Harness 能力域为评分维度：

| Harness 能力域 | 当前状态 | 成熟度评分 | 关键差距 |
| --- | --- | --- | --- |
| **编排（Orchestration）** | xAgent DAG Plan Execute 已就绪，支持多步骤、依赖、并发、扩展 | 🟢 80/100 | Planner 输出偏命令式，缺少声明式计划模板 |
| **调度（Scheduling）** | 顺序执行 + 并发执行已就绪，支持条件分支 | 🟢 75/100 | 缺少优先级调度、资源隔离 |
| **记忆（Memory）** | xAgent /api/memory 已就绪，支持用户隔离 | 🟡 60/100 | 缺少遗忘机制、记忆分类层次、跨 Agent 记忆共享策略 |
| **状态管理（State）** | DAG execution state 已就绪，支持暂停/恢复 | 🟢 70/100 | Session-level state 缺少持久化策略 |
| **工具治理（Tool Governance）** | Agent Capability Registry 进行中 | 🟡 45/100 | 缺少完整的工具元信息登记（9 项中仅覆盖 4 项） |
| **预算控制（Budget Control）** | 有 max_steps 和 token budget 的雏形 | 🔴 20/100 | 无实时预算监控、三层降级、成本归因 |
| **可观测性（Observability）** | trace_events 已就绪，支持 step-level tracing | 🟡 55/100 | 缺少质量门禁事件、业务指标 dashboard |
| **输出质量治理（Output Governance）** | ❌ 完全缺失 ← 验证案例核心问题 | 🔴 0/100 | 无输出 Schema 约束、无质量门禁、无 Anti-Pattern 检测 |

**综合 Harness 成熟度评分：46/100**（生产级门槛 ≥ 70/100）

### 1.3 验证案例问题回溯

在"学员张三（Java 2年 → 大数据）"验证场景中，系统输出了过于简化的总结性内容。从 Harness 视角分析：

| 问题现象 | Harness 缺失的能力 | 根因归类 |
| --- | --- | --- |
| 简历优化仅 3 句话概括 | 输出 Schema 约束（Layer 1） | 输出质量治理 |
| 学习建议为"建议补充大数据技能" | Anti-Pattern 检测 | 输出质量治理 |
| 无时间节点、无资源引用 | Prompt Injection（Layer 2）缺失 | 工具治理（描述不精确） |
| 无风险提示、无 Plan B | Quality Gate（Layer 3）缺失 | 输出质量治理 |
| 各子任务输出混合不分章节 | 输出 Schema 约束 | 输出质量治理 |

---

## 2. 逐章改进方案

### 2.1 编排层改进（对应文章 §2）

#### 文章方法论

> "顶层 Orchestrator 负责全局意图理解与任务分解，生成声明式计划（做什么、依赖谁、期望输出是什么），而不是命令式调用（调谁、传什么参数）"
> "建议：Orchestrator → Sub-Agent → Tool，三层分工而非混合调用"

#### 当前系统现状

xAgent 的 DAG Plan Generator（`plan_generator.py`）生成的 Plan 结构：

```python
class PlanStep:
    id: str
    name: str
    description: str          # ← 仅文本描述，缺少结构化输出期望
    tool_names: List[str]     # ← 直接指定工具名，偏命令式
    dependencies: List[str]
    difficulty: str
    requires_vision: bool
```

**问题**：
1. `description` 是自由文本，Planner 不会声明期望的输出格式
2. `tool_names` 直接指定工具，缺少"声明能力需求 → 工具匹配"的抽象层
3. 缺少 `expected_output_schema` 字段——Step Agent 不知道输出应该长什么样

#### 改进方案

**新增 PlanStep 字段**：

```python
class PlanStep:
    # ...现有字段...
    expected_output_schema: Optional[Dict]    # 期望输出 JSON Schema
    output_quality_level: str = "L2"           # L1/L2/L3
    output_min_word_count: Optional[int]       # 最低字数
    scenario_prompt_injection: Optional[str]    # 场景 Prompt 注入标识（如 "job_placement_full"）
```

**Planner Prompt 增强**：

在 `plan_generator.py` 的 `_build_planning_prompt` 中增加：

```
OUTPUT EXPECTATIONS: For each step, you MUST also declare:
1. expected_output_schema: A JSON schema describing the required output fields
2. output_quality_level: "L2" (must have quantified targets, timeline, resource refs, risks) or "L3" (L2 + preconditions, deliverable list, acceptance criteria, fallback)
3. output_min_word_count: Minimum expected word count for this step

Example:
{
  "id": "step_resume_optimize",
  "name": "简历优化",
  "description": "基于学员背景和JD关键词，生成优化后简历",
  "expected_output_schema": {
    "type": "object",
    "required": ["original_summary", "optimized_resume", "diff_sections", "ats_checklist"],
    "properties": {
      "optimized_resume": {"type": "string", "minLength": 800},
      "diff_sections": {"type": "array", "minItems": 3}
    }
  },
  "output_quality_level": "L2",
  "output_min_word_count": 800
}
```

#### 验收指标

- [ ] Planner 生成的每个 Step 都包含 `expected_output_schema`、`output_quality_level`、`output_min_word_count`
- [ ] Step Agent 收到的 System Prompt 中包含期望输出的 Schema 描述

---

### 2.2 工具治理层改进（对应文章 §3）

#### 文章方法论

> "Tool Registry 作为安全边界：每个工具需要登记 name、description、input/output schema、RBAC 策略、超时、重试次数、风险等级、是否需要人工确认、成本标签等 9 项元信息。"

#### 当前系统现状

53AIHub 的 Agent Capability Registry（需求设计文档 §6.1）已定义 13 个字段，xAgent Custom API 工具已有基础字段。但存在以下问题：

1. **工具描述太简单**：如 `"Query CRM sales leads"` 不足以让 Planner 判断这个工具能产出什么质量的输出
2. **缺少输出质量标注**：工具没有声明"我产出的内容能达到 L2/L3 吗？"
3. **缺少成本信息**：Planner 选择工具时没有成本考量
4. **Mock 输出质量低**：Mock Gateway 返回的数据是 "summary" 级别，不是 "executable" 级别

#### 改进方案

**新增工具元信息字段**：

| 字段 | 用途 | 当前状态 |
| --- | --- | --- |
| `output_quality_native_level` | 该工具原生输出能达到的质量等级（L0-L3） | ❌ 缺失 |
| `output_min_confidence` | 工具输出的最低置信度阈值 | ❌ 缺失 |
| `suggested_follow_up_tools` | 建议配合使用的下游工具 | ❌ 缺失 |
| `known_limitations` | 已知局限性（如"仅返回模拟数据"、"不支持文件解析"） | ❌ 缺失 |
| `cost_per_call_estimate` | 单次调用预估 token 成本 | ❌ 缺失 |
| `response_time_p50/p95_ms` | 响应时间分布 | ❌ 缺失 |

**工具描述规范**：

每个工具的描述（`description` 字段）必须遵循以下格式：

```
[业务域]:[能力名称] - [核心功能描述（1句话）]
Input: [关键入参列表]
Output: [关键出参列表 + 输出质量等级]
Limitations: [已知限制]
Quality: [输出质量等级 L0-L3]
```

**示例（改造前 vs 改造后）**：

改造前（当前）：
```
"Query CRM sales leads including contact info, source, status, and budget"
```

改造后（目标）：
```
"sales:crm_lead_query - Query CRM sales leads with full customer profile
Input: lead_id (required), include_recordings (optional)
Output: customer_profile (8 fields: 基础信息/来源/技术方向/决策角色/预算区间/紧急程度/历史交互/竞品), lead_status, assigned_sales
Limitations: Mock data only in staging; real CRM data requires production deployment; recording files not returned, file_id only
Quality: L2 (returns structured profile with all 8 fields populated or marked '待确认')
ResponseTime: P50=500ms, P95=2000ms
CostEstimate: ~1200 input tokens, ~800 output tokens"
```

#### 验收指标

- [ ] 所有 Mock Agent 的 `description` 字段改造为新格式
- [ ] 每个工具标注 `output_quality_native_level`
- [ ] Mock Gateway 输出升级为 L2 级别（完整结构化数据，而非摘要）

---

### 2.3 状态与记忆层改进（对应文章 §4）

#### 文章方法论

> "State 是短生命周期的事务数据，Memory 是跨任务复用的长期知识。"
> "记忆需要遗忘机制——记忆不是仓库，而是花园，需要定期修剪和评估关联度。"

#### 当前系统现状

xAgent 记忆隔离为按 user_id 隔离，支持创建、搜索、更新、删除、统计。但缺少：

1. **记忆分类层次**：所有记忆平铺在一起，没有 domain 层次
2. **遗忘/衰减机制**：旧记忆和新记忆同等权重
3. **关联度评估**：搜索记忆时只看相似度，没有 relevance 分级
4. **跨任务记忆策略**：销售任务不会引用教学任务中的学员画像记忆

> **分阶段实施说明**：Phase 1 保留 xAgent 现有记忆能力作为基础（不阻塞 MVP 交付），以下改进方案为 Phase 4 增强项——在四条业务流 MVP 和输出质量门禁稳定后再实施。这是对现有记忆的"升级"而非"替代"。

#### 改进方案（Phase 4 增强）

**新增记忆分类层次**：

```python
class MemoryClassification:
    primary_domain: str      # sales / teaching / placement / content_rd
    secondary_domains: List[str]
    subject_type: str        # student / lead / agent_config / task_template
    access_policy: str       # same_domain_only / cross_domain_readonly / global
    retention_period_days: int
    decay_rate: float        # 0.0-1.0，1.0 表示 30 天后权重降到 0
    min_relevance_threshold: float  # 低于此值不返回
```

**记忆检索策略增强**：

| 任务类型 | 优先检索域 | 可访问域 | 衰减窗口 |
| --- | --- | --- | --- |
| 销售转化 | sales | sales + placement（只读） | 90 天 |
| 教学管理 | teaching | teaching + student_profile | 180 天 |
| 求职出口 | placement | placement + teaching + student_profile | 180 天 |
| 教研内容 | content_rd | content_rd + placement（岗位需求） | 365 天 |

**遗忘策略**：

- 默认 180 天无更新标记为 `archived`
- `archived` 后 90 天无访问自动删除
- 每次搜索时应用 `decay_rate` 权重衰减

#### 验收指标

- [ ] 记忆写入时带完整分类标签
- [ ] 记忆搜索时按 domain 过滤 + relevance 排序
- [ ] 过期记忆自动归档/删除

---

### 2.4 评估体系改进（对应文章 §5）—— 核心改进

> 这是与"输出质量保障"最直接相关的章节。

#### 文章方法论

> "四层评估体系：组件评估 → 轨迹评估 → 任务完成度评估 → 端到端业务效果评估"
> "Eval 必须进入 CI，每次 PR 自动运行评估套件"

#### 当前系统现状

| 评估层 | 当前状态 | 成熟度 |
| --- | --- | --- |
| 组件评估（单工具调用正确性） | API-001~015 接口级测试 | 🟡 基础覆盖 |
| 轨迹评估（步骤是否正确执行） | Trace Events 已有 step_start/step_end | 🟡 可追踪但无自动评估 |
| 任务完成度（结果是否达成目标） | Result Analyzer 的 `achieved` 判断 | 🟡 仅二元判断，无质量评分 |
| 业务效果（是否提升业务指标） | KPI 采集点已定义 | 🔴 未实施 |

**核心缺失**：任务完成度评估仅判断 achieved=true/false，不评估输出质量等级。

#### 改进方案

**新增加第四层半：输出质量评估（Output Quality Evaluation）**

这是"任务完成度评估"的细分维度，专门评估输出是否达到 L2/L3 标准。

```python
class OutputQualityEval:
    """在 task completed 后自动运行的输出质量评估"""
    task_id: str
    eval_timestamp: datetime
    overall_score: int         # 0-100
    quality_level: str         # L0/L1/L2/L3
    dimension_scores: {
        "quantified_targets": int,    # 量化指标得分
        "timeline_completeness": int, # 时间线完整度得分
        "resource_references": int,   # 资源引用得分
        "structure_score": int,       # 结构化得分
        "risk_coverage": int,         # 风险覆盖得分
        "actionability": int          # 综合可执行性得分
    }
    anti_pattern_hits: List[str]      # 检测到的 Anti-Pattern 列表
    word_count: int                   # 总字数
    quantified_count: int             # 量化数字个数
    heading_count: int                # 二级标题个数
    resource_ref_count: int           # 资源引用个数
    risk_count: int                   # 风险提示个数
    passed: bool                      # 是否通过 L2 门禁
```

**自动化评估流程**：

```
DAG Execution Complete
  → Result Analyzer: Goal Achieved Check
  → OutputQualityEval: Auto-scoring
    → Pass (≥ L2) → Write to trace_event, mark task complete ✅
    → Fail (< L2) → Trigger Re-generation (max 3 retries)
        → Pass after retry → mark complete ✅
        → Still fail → mark complete with ⚠️ flag + human_intervention_required
```

**CI 集成**：

每个 PR 必须通过以下评估：

```bash
# E2E 评估套件
python -m pytest tests/e2e/test_output_quality.py \
  --scenario job_placement_full \
  --expected-quality L2 \
  --min-word-count 1500 \
  --min-quantified-count 15

# 回归检测
python -m pytest tests/regression/test_baseline_quality.py \
  --baseline baseline_v1.json \
  --tolerance 0.05  # 质量退化不超过 5%
```

#### 验收指标

- [ ] 每个 task 完成后自动运行 OutputQualityEval
- [ ] Eval 结果写入 trace_event（`output_quality_eval`）
- [ ] 不通过的 task 自动触发重生成（最多 3 次）
- [ ] E2E 评估套件集成到 CI

---

### 2.5 成本控制改进（对应文章 §6）

#### 文章方法论

> "Token Budget 实时调度模型，三层降级策略——绿区（正常执行）、黄区（降级模型、压缩上下文）、红区（仅返回结构化摘要、暂停低优先级步骤）、熔断区（硬停止）"
> "成本归因到任务级和工具级"

#### 当前系统现状

- 有 `max_steps=12`、`token_budget=80000` 配置
- 无实时预算消耗监控
- 无降级策略
- 无成本归因

#### 改进方案

**四区预算模型**：

| 区域 | 额度比例 | 行为 | 触发条件 |
| --- | --- | --- | --- |
| 🟢 绿区 | 0-60% | 正常执行，使用最强模型 | 预算消耗 < 60% |
| 🟡 黄区 | 60-80% | Step Agent 切换为 compact model，压缩上下文（只保留最近 3 条消息 + 关键中间结果） | 60% ≤ 消耗 < 80% |
| 🔴 红区 | 80-95% | 仅输出结构化摘要，暂停非关键步骤（如"记忆写入"、"可选分析"） | 80% ≤ 消耗 < 95% |
| ⚫ 熔断 | 95%+ | 硬停止，返回已完成步骤的结果 + "token budget exhausted" 说明 | 消耗 ≥ 95% |

**输出质量与成本的关系**：

高输出质量需要消耗更多 token，需要在预算中预留"质量冗余"：

| 输出目标等级 | Token 预算占比 | 说明 |
| --- | --- | --- |
| L2 可执行级 | 总预算的 40-50% | 需要消耗大量 token 生成详细内容 |
| L3 闭环方案级 | 总预算的 50-60% | L2 + 额外开销（前置检查、验收标准、回退路径） |
| 规划调度开销 | 总预算的 15-20% | Planner + Classifier + Result Analyzer |
| 记忆读写开销 | 总预算的 5-10% | Memory search + write |

**成本归因**：

```json
{
  "task_id": "xxx",
  "token_usage": {
    "total": 45000,
    "breakdown": {
      "planning": 3200,
      "classification": 800,
      "step_execution": [
        {"step_id": "step1", "tokens": 12000, "tool": "resume_optimize"},
        {"step_id": "step2", "tokens": 15000, "tool": "job_matching"}
      ],
      "result_analysis": 5000,
      "quality_gate": 2000,
      "memory_operations": 1500
    }
  },
  "cost_estimate_usd": 0.12,
  "budget_utilization": "56% (green zone)"
}
```

#### 验收指标

- [ ] 每个 task 有实时 token 消耗追踪
- [ ] 绿/黄/红/熔断四级策略在生产环境可切换
- [ ] 成本归因到 Step + Tool 级别

---

### 2.6 MCP 工具接入（对应文章 §7）

#### 文章方法论

> "MCP 标准化工具接入必须经过 Harness 安全网关，工具授权采用白名单而非黑名单原则。高风险工具走 Human-in-the-Loop。"

#### 当前系统现状

- 53AIHub 已有 Agent Capability Registry 作为工具注册中心
- xAgent 通过 Custom API 接入 53AIHub Agent
- Mock Gateway 模拟外部工具

**当前 53AIHub 已具备 Harness 安全网关的基本形态**（鉴权、审批、审计、eid 隔离），但工具白名单和风险分类需要强化。

#### 改进方案

**工具风险分级与审批映射**：

| 风险等级 | 典型工具 | 审批策略 | 白名单要求 |
| --- | --- | --- | --- |
| `low` | 知识库搜索、课程大纲生成 | 无需审批，自动执行 | 默认可用 |
| `medium` | 简历优化、作业评估 | 执行后审批（影子模式），可配置 | eid 管理员确认 |
| `high` | 销售话术外发、职业建议展示、成绩写入 | **执行前审批**，Human-in-the-Loop 必选 | eid 管理员 + 业务主管双确认 |
| `critical` | 合同内容、费用报价、就业承诺 | 拒绝自动生成，仅提供模板，完全人工 | 仅超级管理员 |

**工具安全网关检查清单**（每个 Custom API 注册时检查）：

1. 工具是否在白名单中？
2. 调用方是否有该工具的 RBAC 权限？
3. 工具的 `risk_level` 是否匹配当前的审批策略？
4. 工具的输出是否包含 PII？是否需要脱敏后返回？
5. 工具的调用频次是否超过 rate_limit？

#### 验收指标

- [ ] 所有 Custom API 工具注册时标注风险等级
- [ ] high/critical 风险工具执行前触发审批

---

### 2.7 可观测性与落地路线（对应文章 §8-9）

#### 文章方法论

> "三阶段演进：MVP（跑通核心流程）→ Hardening（质量、安全、成本、监控加固）→ Scale（高可用、多租户弹性、持续优化）"

#### 当前系统阶段评估

| 阶段 | 完成度 | 关键里程碑 |
| --- | --- | --- |
| MVP | 🟢 80% | 四条业务流 E2E 已跑通（P3-01~05） |
| Hardening | 🟡 30% | 输出质量门禁（本方案核心）、成本控制、审批加固进行中 |
| Scale | 🔴 0% | 高可用架构、多租户弹性、性能优化未开始 |

#### 改进方案

**从 MVP 到 Hardening 的关键动作（当前阶段）**：

| # | 动作 | 优先级 | 预估工作量 | 完成标准 |
| --- | --- | --- | --- | --- |
| H-01 | Agent Builder System Prompt 升级（替换简短版 → 完整 L2/L3 Prompt） | **P0 阻塞** | 配置变更 | 新对话的输出质量达到 L2 |
| H-02 | Mock Gateway 输出升级为 L2 Schema | **P0 阻塞** | 2-3天 | Mock 数据符合 L2 结构 |
| H-03 | Result Analyzer 增加 Quality Gate | P1 高优 | 3-5天 | trace 中可见 quality_gate_check |
| H-04 | Anti-Pattern 自动检测 | P1 高优 | 1-2天 | 触发重生成 |
| H-05 | 工具注册元信息补全（9 项） | P2 中优 | 2-3天 | 所有工具注册完整 |
| H-06 | Token Budget 四区模型 | P2 中优 | 3-5天 | 绿/黄区可切换 |
| H-07 | 记忆分类与衰减 | P3 低优 | 3-5天 | 跨任务记忆检索 |

**Hardening 阶段的 Dashboard 指标**：

| 指标 | 采集方式 | 告警阈值 |
| --- | --- | --- |
| 输出质量通过率（L2+） | trace event `output_quality_eval.passed` | < 80% → 告警 |
| Quality Gate 重生成率 | trace event `quality_gate.retry_count > 0` | > 30% → 告警 |
| Anti-Pattern 命中率 | trace event `anti_pattern_hits.length > 0` | > 20% → 告警 |
| Token 预算超支率 | task budget_utilization > 100% | > 5% → 告警 |
| 人工介入率 | task status = degraded_to_human | > 10% → 告警 |

---

## 3. 优先级排序与实施路线图

### 3.1 优先级矩阵

```
高影响 │  H-01              │  H-03
       │  System Prompt     │  Quality Gate
       │  升级（P0）         │  实现（P1）
       │                    │
       │  H-02              │  H-04
       │  Mock 升级          │  Anti-Pattern
       │  （P0）             │  检测（P1）
       │                    │
───────┼────────────────────┼──────────────────
       │                    │
低影响  │  H-05              │  H-06
       │  工具元信息          │  Token Budget
       │  补全（P2）          │  四区模型（P2）
       │                    │
       │                    │  H-07
       │                    │  记忆衰减（P3）
       │                    │
       └────────────────────┴──────────────────
          低复杂度              高复杂度
```

### 3.2 实施路线图

```
Week 1 ──────────────────────────────────────────────
  Day 1-2: H-01 System Prompt 升级 + H-02 Mock Gateway 升级
  Day 3-4: 验证新 Prompt 下的输出质量，调优
  Day 5:   首次 Quality Gate 概念验证（手动）

Week 2 ──────────────────────────────────────────────
  Day 1-3: H-03 Quality Gate 开发（result_analyzer.py）
  Day 4-5: H-04 Anti-Pattern 检测实现

Week 3 ──────────────────────────────────────────────
  Day 1-3: E2E 验证（求职全链路 + 销售全链路）
  Day 4-5: 修复 QA 发现的问题，Prompt 调优

Week 4+ ─────────────────────────────────────────────
  H-05 工具元信息补全
  H-06 Token Budget 四区模型
  H-07 记忆衰减（可选，视资源而定）
```

### 3.3 上线决策点

| 里程碑 | 判定标准 | 决策 |
| --- | --- | --- |
| M1（Week 1 末） | 新 Prompt 下的输出质量 ≥ L2 | Go/No-Go 继续 Week 2 开发 |
| M2（Week 3 末） | Quality Gate 通过率 ≥ 80%，E2E 回归通过 | Go/No-Go 生产发布 |
| M3（Week 4+） | Token Budget 模型上线，成本归因可用 | Hardening 阶段完成 |

---

## 4. 关键风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
| --- | --- | --- | --- |
| L2/L3 Prompt 导致 token 消耗倍增 | 高 | 中 | H-06 Token Budget 四区模型跟进；先用绿区 + 高预算验证，再压预算 |
| Quality Gate 频繁触发重生成，用户体验差 | 中 | 高 | 先在后台异步运行 Quality Gate（影子模式），验证通过率稳定后再阻塞式运行 |
| DeepSeek 模型对长 Prompt 遵循度不足 | 中 | 高 | 备选方案：仅对关键步骤（求职全链路、销售预案）注入完整 Prompt，其他步骤用精简版 |
| Mock 数据升级后与真实 Dify/Coze 行为不一致 | 中 | 中 | Mock 数据字段与真实 Dify/Coze 合同严格一致；真实平台接入后在 staging 重跑 E2E |
| 模型切换后输出质量退化 | 低 | 高 | H-01 实施时建立输出质量 baseline；CI 中加入回归检测（OutputQualityEval score 不降 > 5%） |

---

## 5. 总结

本改进方案基于参考文章的 Harness 方法论，将当前系统的核心问题定位为 **输出质量治理缺失**，并提出了系统性的三层保障体系：

1. **Layer 1（Schema 约束）**：每个 Agent/Step 声明期望的输出 Schema，从结构层面防止自由文本生成
2. **Layer 2（Prompt 注入）**：Agent Builder System Prompt 明确 L2/L3 标准 + Anti-Pattern 禁止 + 场景专属模板
3. **Layer 3（Quality Gate）**：Result Analyzer 自动检测输出质量，不通过则触发重生成（最多 3 次）

参考文章最关键的一句话适用于本系统：

> "未来的竞争不是谁的 Agent 更多，而是谁的 Harness 更稳。"

对于 53AIHub + xAgent 来说，稳定性的核心不只是系统不崩溃，更是**每一次输出都可执行、可验证、可回溯**。

---

## 附录 A：与参考文章的术语映射

| 参考文章术语 | 本系统对应术语 | 说明 |
| --- | --- | --- |
| Harness | xAgent DAG Engine（Planner + Executor + Result Analyzer + Quality Gate） | 调度与执行框架 |
| Agent | Dify/Coze/自研 Step Agent | 执行具体能力的工具或子 Agent |
| Tool Registry | 53AIHub Agent Capability Registry + xAgent Custom API | 工具注册与治理中心 |
| Orchestrator | xAgent DAG Planner（PlanGenerator） | 任务分解与规划 |
| State | DAGExecutionState + Conversation context | 短生命周期事务数据 |
| Memory | xAgent /api/memory | 跨任务长期知识 |
| Budget Control | Token Budget 四区模型 | 成本实时控制 |
| Quality Gate | OutputQualityEval（本方案新增） | 输出质量门禁 |
| Human-in-the-Loop | 53AIHub 审批闸口 | 高风险决策人工确认 |

## 附录 B：参考文章原文链接

- [从零设计生产级 Multi-Agent Harness：架构、评估、记忆、成本与 MCP 工具接入全拆解](https://cloud.tencent.com/developer/article/2668186)
- 作者：李伟山
- 发布日期：2026-05-13
