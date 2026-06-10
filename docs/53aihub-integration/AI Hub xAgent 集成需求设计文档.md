# AI Hub xAgent 集成需求设计文档

版本：v1.0  
日期：2026-05-06  
范围：53AIHub + Dify + Coze + xAgent 企业级智能体调度体系  
依据：`docs/AI Hub 集成与调度大脑选型.docx`、`D:\Workspace\53AIHub` 当前代码、`D:\github\xagent` 当前代码

## 1. 背景与目标

职坐标已经沉淀了覆盖教学、销售、教研、求职出口的智能体资产（`平台智能体.xlsx` 登记 31 个，其中 27 个已确认功能描述，NO.10/16/20/29 待确认），主要分布在 Dify、Coze、CRM、官网系统、CareerMagic 等平台。现状的核心问题不是缺少单点能力，而是缺少统一入口、统一任务上下文、跨平台调度、长期记忆和端到端质量评估。

本项目目标是把 53AIHub 建成统一 AI 门户与 API 聚合层，把 Dify/Coze 作为确定性垂直能力执行层，把 xAgent 作为复杂任务的动态规划与调度大脑。最终形成“用户描述目标，系统规划步骤，按权限调用各平台智能体，保留记忆与审计证据”的企业级 Agentic 工作流。

### 1.1 建设目标

1. 统一入口：所有员工、老师、销售、学员通过 53AIHub 访问智能体能力。
2. 统一调度：复杂任务由 xAgent 根据目标动态拆解，调用 53AIHub 已注册的 Dify/Coze/自研系统能力。
3. 统一协议：建立 Agent Handoff Protocol，规范任务、上下文、输入输出 Schema、错误、审计字段。
4. 统一记忆：建立跨销售、教学、求职的长期记忆总线，支持学员画像与任务历史复用。
5. 统一验证：以四条完整业务流为验收主线，建立端到端测试与 KPI 矩阵。

### 1.2 非目标

1. 不重写 Dify、Coze 内部已经稳定运行的原子工作流。
2. 不把所有业务逻辑搬进 xAgent。确定性高、风险高、可枚举的流程仍由 Dify/Coze Workflow 或 53AIHub 后端执行。
3. 不在第一阶段实现完全无人值守的高风险决策。职业建议、销售关键话术、学员评价需要 Human-in-the-Loop 审核闸口。

## 2. 当前系统能力基线

### 2.1 53AIHub 当前能力

53AIHub 当前代码已经具备作为统一门户和 API 聚合层的基础：

1. Agent 管理模型：`api/model/agent.go` 支持 `AgentTypeApp=0` 与 `AgentTypeWorkflow=1`，支持企业 `eid`、用户组权限、启用状态、渠道类型、模型名、提示词、工具、`custom_config`。
2. Agent 管理接口：`api/controller/agent.go` 和 `api/router/api.go` 提供 `/api/agents`、`/api/agents/available`、`/api/agents/{agent_id}` 等管理入口。
3. OpenAI 兼容调用入口：`/v1/chat/completions` 通过 `RelayTokenAuth` 校验 JWT，并通过 `model: agent-{id}` 解析具体 Agent。
4. Workflow 调用入口：`/v1/workflow/run` 对 `AgentTypeWorkflow` 做独立执行，返回 `custom.WorkflowResponseData`，包含 `workflow_output_data`、`execute_id`、`channel_id`、`model_name`。
5. Dify/Coze 适配：已有 `api/service/hub_adaptor/dify`、`api/service/hub_adaptor/coze`，支持聊天、工作流、文件映射、流式响应转换。
6. 前端平台配置：`web/console/src/constants/platform/config.ts` 已包含 Dify、Coze、53AI、FastGPT、MaxKB、n8n、腾讯等平台类型。
7. 会话与消息：`api/model/conversation.go`、`api/model/message.go` 已记录会话、消息、token、耗时、渠道、工作流输入输出解析。

### 2.2 xAgent 当前能力

xAgent 当前代码已经具备作为调度脑的基础：

1. 执行模式：`src/xagent/web/api/chat.py` 将 `flash` 映射到 `single_call`，`balanced` 映射到 `react`，`think` 映射到 `dag_plan_execute`。
2. 任务入口：`/api/chat/task/create` 接收 `title`、`description`、`agent_id`、`files`、`llm_ids`、`execution_mode` 等字段。
3. DAG 动态规划：`DAGPlanExecutePattern` 支持 DAG 步骤、依赖、并发、目标检查、计划扩展、暂停恢复、trace。
4. Custom API 工具：`/api/custom-apis` 可注册外部 REST API，`CustomApiTool` 支持默认 URL、method、headers、env 密文变量替换，作为工具被 xAgent 自动发现。
5. 记忆管理：`/api/memory` 支持按用户隔离的记忆列表、搜索、更新、删除、统计。
6. 可观测性：`tasks`、`dag_executions`、`trace_events` 记录任务状态、DAG 阶段、步骤事件、token 使用。
7. 工具工厂：`ToolFactory` 统一加载基础工具、知识库、文件、视觉、MCP、Custom API、Agent tool 等工具。

### 2.3 附件智能体资产基线

根据 `docs/平台智能体.xlsx`，本次集成要覆盖的既有能力不是抽象的“外部 Agent”，而是已经在业务里使用的 Dify、Coze、CRM、豆包和自研系统能力。需求设计以这些资产为第一批能力注册对象。

| NO. | 智能体 | 平台/框架 | 当前集成入口 | 目标能力域 | 目标调用方式 |
| --- | --- | --- | --- | --- | --- |
| 1 | AI 编程助手 | Dify | 官网平台，VIP 学员提问 | 教学答疑 | 53AIHub Dify Chat Agent，xAgent 教学工具 |
| 2 | IT 作业评估 | Dify | 官网平台、教学系统后台 | 作业批改 | 53AIHub 后台 Workflow/Agent，审批后写回成绩 |
| 3 | 求职神器 | Coze | Coze 外部开放 | 求职服务 | Coze Workflow，简历解析/优化/职业规划 |
| 4 | 复盘分析 | CRM 系统 | CRM 内部集成 | 销售/面试复盘 | CRM Custom API，TQ 录音、ASR、复盘 |
| 5 | 小职002 | Dify | 钉钉内部群 | 内部问答 | 钉钉 Bot -> 53AIHub -> Dify |
| 6 | 职业规划 | Dify | 官网平台 | 学员职业规划 | Dify 文件型 Agent |
| 7 | 简历优化 | Dify | 官网平台 | 简历优化 | Dify 文件型 Agent |
| 8 | 学习伴侣知识点解析 | Dify | 官网平台 | 音视频知识点解析 | Dify/解析服务，文件型 Agent |
| 9 | 学习伴侣 Chatflow | Dify | 官网平台 | 课程知识库问答 | Dify Chatflow，课程权限控制 |
| 11-15 | AI 职业规划、简历优化、销售预案、岗位上传、岗位分析 | Coze | 扣子销售使用 | 销售转化 | Coze Workflow 工具组 |
| 17-19 | 小红书种草、封面创作、热点提醒 | Coze | 扣子运营使用 | 内容运营 | Coze 多模态 Workflow，外发审批 |
| 21 | Prompt 训练器 | Coze | 扣子培训使用 | 培训/提示词工程 | Coze Agent 工具 |
| 22 | 百问百答 | 豆包 | 豆包平台 | 测评/模拟面试 | Custom API，后续独立 Doubao channel |
| 23-28 | 课程大纲、教案、逐字稿、PPT、口播配音、代码演示 | Coze | 扣子培训使用 | 敏捷教研 | Coze Workflow 编排链 |
| 30 | CareerMagic | 自研系统 | 官网个性化 AI 教学系统 | 教学闭环 | Internal System Provider，事件 + API |
| 31 | CareerOS | 自研系统 | 官网个性化 AI 求职系统 | 求职闭环 | Internal System Provider，JD/面试/能力模型 API |

第一批上线验收必须至少覆盖 Dify 教学、Coze 销售、CRM 复盘、自研 CareerMagic/CareerOS 事件接入。Coze 运营和完整教研内容生产可在销售流稳定后进入第二批。

## 3. 用户与角色

| 角色 | 核心诉求 | 主要入口 | 权限边界 |
| --- | --- | --- | --- |
| 销售 | 快速生成客户画像、职业规划、首电逐字稿、跟进建议 | 53AIHub 前台、钉钉/企微 | 仅可访问自己负责线索与授权话术模板 |
| 助教/讲师 | 作业评估、薄弱知识点定位、个性化补课建议 | 53AIHub 教学智能体、CareerMagic | 可访问所带班级学员学习数据 |
| 教研 | 课程大纲、教案、PPT、逐字稿、代码演示环境 | 53AIHub 教研工作台 | 可访问课程与岗位资料库 |
| 求职顾问 | 简历优化、岗位匹配、模拟面试、录音复盘 | 53AIHub 求职服务入口 | 可访问负责学员求职数据 |
| 管理员 | Agent 注册、平台凭证、调度策略、审计、KPI | 53AIHub 管理后台、xAgent 管理台 | 全局配置与审计权限 |
| 学员 | 提问、作业反馈、简历优化、模拟面试 | 53AIHub 前台、官网/CareerOS | 仅访问本人数据与公开课程数据 |

## 4. 总体架构

### 4.1 分层架构

```text
用户/业务系统
  | 53AIHub 门户、前台、控制台、DingTalk/WeCom/官网
  v
53AIHub 聚合层
  | Agent Registry | Auth/RBAC | Relay API | Workflow API | Conversation | Audit | KPI
  v
xAgent 调度脑
  | Task Planner | DAG Executor | ToolFactory | Custom API Tools | Memory | Trace
  v
Dify / Coze / CareerMagic / CRM / CareerOS / 钉钉 / 课程系统 / 文件与知识库
```

### 4.2 双向集成关系

1. 53AIHub 调用 xAgent：把 xAgent 作为一个新的调度型 Agent 平台接入 53AIHub。用户在 53AIHub 发起复杂目标，53AIHub 将请求转成 xAgent task，展示任务计划、执行过程和最终产出。
2. xAgent 调用 53AIHub：把 53AIHub 中的 Dify、Coze、自研智能体导出为 xAgent Custom API 工具。xAgent Planner 在执行 DAG 步骤时选择具体工具调用。

这两个方向必须同时存在。只做 53AIHub 调 xAgent，会导致 xAgent 看不到 31 个既有 Agent 能力。只做 xAgent 调 53AIHub，会导致用户入口、权限、运营、审计割裂。

### 4.3 运行模式

| 任务类型 | 调度模式 | 执行层 | 示例 |
| --- | --- | --- | --- |
| 单轮问答、普通咨询 | 53AIHub 直接调用 | Dify/Coze/模型渠道 | “解释 Java 泛型” |
| 确定性工作流 | 53AIHub Workflow API | Dify/Coze Workflow | “用固定模板生成销售预案” |
| 多步骤、模糊目标、需要工具选择 | xAgent `think` | xAgent DAG + 53AIHub Tools | “根据这个学员履历找岗位并重写简历” |
| 高风险输出 | xAgent 规划 + 人工确认 | 53AIHub 审核闸口 + 执行工具 | 职业建议、销售关键话术 |

## 5. 核心业务需求

### 5.1 销售转化全自动化流

目标：线索进入后 5 分钟内形成可执行销售预案，降低新销售培养成本，提高首电转化率。

触发来源：

1. 官网表单线索。
2. 小红书/内容平台链接。
3. CRM 中新增或更新的咨询记录。
4. 销售在 53AIHub 手动提交简历或咨询内容。

核心步骤：

1. 53AIHub 接收线索并创建销售任务。
2. xAgent 读取线索类型、用户画像、来源渠道。
3. 如来源为小红书链接，调用 AI 小红书种草进行内容拆解。
4. 调用 AI 岗位上传或岗位热度工具，提取对应技术方向 JD 热度。
5. 调用 AI 职业规划生成职业规划报告。
6. 从 CRM 历史成功案例与长期记忆中检索相似用户转化话术。
7. 调用 AI 销售预案生成首电逐字稿。
8. 进入人工确认闸口，销售可采纳、修改、驳回。
9. 通过钉钉/企微推送结果，并回写 53AIHub 消息、CRM 跟进记录、KPI。

验收指标：

| 指标 | 目标 |
| --- | --- |
| 全套预案生成时间 | P95 < 5 分钟 |
| 首个 Agent 动作触发延迟 | 文本 P95 < 2 秒 |
| 销售话术采纳率 | > 75% |
| 首电转化率提升 | 目标从 12% 提升到 18% |

### 5.2 智能化教学管理流

目标：在学员学习过程中自动识别薄弱点，给出个性化辅导和作业反馈。

触发来源：

1. 学员入班测验。
2. CareerMagic 中代码练习停顿或多次失败。
3. 作业提交。
4. 学员主动提问。

核心步骤：

1. 入班后调用百问百答或测评 Agent，生成初始能力模型。
2. 53AIHub 建立学员画像记忆，记录基础、目标岗位、薄弱知识点。
3. CareerMagic 上报练习事件，如停顿超过 10 分钟。
4. xAgent 判断是否需要介入，优先给提示和引导，不直接给最终答案。
5. 调用 AI 编程助手给出分层提示。
6. 学员提交作业后调用 IT 作业评估。
7. 若得分低于 80，调用知识点解析从课程录音或资料中提取补课片段。
8. 通过学习伴侣推送补课内容，并更新学员能力模型。

验收指标：

| 指标 | 目标 |
| --- | --- |
| 作业批改自动化覆盖率 | 100% 可触发，异常可回退人工 |
| 薄弱知识点召回率 | 样本抽检 > 85% |
| 不直接泄题率 | 抽检 100% 满足教学策略 |
| 学员画像更新延迟 | 作业评估完成后 1 分钟内 |

### 5.3 敏捷教研内容生产流

目标：将课程研发周期从月级缩短到周级，保证内容与岗位能力模型一致。

触发来源：

1. 教研输入技术主题。
2. 市场岗位热度变化。
3. 课程版本迭代。

核心步骤：

1. xAgent 读取技术主题、目标岗位、课程层级。
2. 调用 AI 课程大纲生成结构化大纲。
3. 调用 AI 课程教案生成课时设计。
4. 并行调用 AI 课程逐字稿、AIPPT 自动生成、AI 口播配音。
5. 调用 AI 代码演示生成实验脚本与演示代码。
6. xAgent 做一致性检查：大纲、PPT、逐字稿、配音、代码 demo 是否覆盖同一技能点。
7. 进入教研审核闸口，审核结果回写版本库。

验收指标：

| 指标 | 目标 |
| --- | --- |
| 单门课程研发人时 | 降低 > 50% |
| 教案与岗位技能匹配度 | 抽检评分 > 85/100 |
| PPT 与逐字稿一致性 | 自动检查通过率 > 90% |
| 资产版本可追溯率 | 100% |

### 5.4 求职出口保障流

目标：形成简历优化、岗位匹配、模拟面试、录音复盘的就业服务闭环。

触发来源：

1. 学员上传简历。
2. CareerOS 推送岗位。
3. 学员申请模拟面试。
4. 学员上传真实面试录音。

核心步骤：

1. xAgent 接收简历、目标岗位、学员画像。
2. 调用 AI 简历优化做 JD 匹配度评分。
3. 若匹配度低于 70%，调用求职神器进行项目经验重构与行业表达优化。
4. CareerOS 推送岗位后，xAgent 提取 JD 关键要求。
5. 调用百问百答进入面试追问模式。
6. 学员上传真实面试录音后，调用复盘分析识别失败点。
7. 更新能力模型与下一轮补课/模拟面试任务。

验收指标：

| 指标 | 目标 |
| --- | --- |
| 简历 JD 匹配评分可解释率 | 100% 输出评分依据 |
| 模拟面试追问覆盖率 | 覆盖 JD Top 5 要求 |
| 复盘问题归因准确率 | 样本抽检 > 80% |
| HR 点击率提升 | 与优化前对照统计 |

### 5.5 输出可执行性标准（核心设计原则）

> **设计原则**：系统输出必须是 **"可直接执行的方案"**，而非 **"摘要性总结"**。每一步产出都必须包含足够的细节，以便业务人员不依赖额外 AI 问询即可直接操作。这是本系统区别于通用 Chatbot 的核心价值。

#### 5.5.1 可执行性定义

| 等级 | 名称 | 标准 | 判定 |
| --- | --- | --- | --- |
| L0 | 摘要级 | 仅概括方向，无可操作步骤。如"建议补充大数据技能" | ❌ 不通过 |
| L1 | 要点级 | 列出了要点但缺少具体操作指令、时间线、量化标准 | ❌ 不通过 |
| L2 | 可执行级 | 每个产出包含：具体步骤、时间安排、量化目标、资源引用、风险提示 | ✅ 最低通过 |
| L3 | 闭环方案级 | L2 + 前置条件检查、交付物清单、验收标准、回退路径 | 🎯 目标等级 |

系统所有核心业务流产出的**最低质量门槛为 L2（可执行级）**，关键交付物（学员辅导方案、销售预案、教研资产）应达到 L3。

#### 5.5.2 各业务流产出的细化要求

**销售转化流**：

| 产出物 | 最低细化度要求 | 示例标准 |
| --- | --- | --- |
| 销售预案/首电逐字稿 | 完整的开场白 → 需求探询（≥5 个追问点）→ 价值呈现（≥3 个核心卖点）→ 异议处理（≥3 种常见异议+应对话术）→ 关单引导 → 下次跟进锚点 | 逐字稿 ≥ 800 字，每个环节独立标注时长预期 |
| 异议处理手册 | 每种异议包含：异议原文、心理原因分析、应对话术（≥2 套）、避雷提示 | 覆盖面 ≥ 5 种常见异议 |
| 客户画像摘要 | 基础信息、来源渠道、关注技术方向、决策角色、预算区间、紧急程度、历史交互摘要 | 每个字段有明确值或"待确认"标注 |
| 跟进建议 | 时间节点（当天/3天/7天）、动作（电话/微信/面访）、目标（确认意向/试听邀请/关单）、话术锚点 | 每个动作有可量化的完成标准 |

**教学管理流**：

| 产出物 | 最低细化度要求 |
| --- | --- |
| 作业评估报告 | 总体评分 + 逐题评分明细 + 每题扣分原因 + 知识点归类 + 错误模式分析 + 对比上次作业的变化趋势 |
| 个性化补课方案 | 按知识点分组的补充材料（含课程录音片段时间戳、教材章节页码、练习题目编号），学习顺序有先后依赖标注，每个知识点标注预计学习时间 |
| 学员能力模型 | 技能雷达图（≥8 个维度）+ 各维度评分与置信度 + 历史分数曲线 + 目标岗位对标差距 + 建议优先提升的 Top 3 维度 |

**求职出口流**：

| 产出物 | 最低细化度要求 |
| --- | --- |
| 优化简历 | 修改前后对照 + 逐段修改说明 + JD 关键词匹配标注 + 量化成果补充（每段经历至少 1 项量化指标）+ ATS 友好度检查清单 |
| 岗位匹配报告 | 匹配度评分 + 评分明细（技能匹配/经验匹配/教育匹配/地域匹配）+ 具体差距列表 + 补强路径 + 薪资范围+竞品公司 |
| 模拟面试反馈 | 逐题评分 + 亮点与改进点 + 参考答案（不是唯一答案，是评分要点）+ 答题时间建议 + 语言表达/逻辑结构/技术深度三维度雷达图 |
| 面试复盘报告 | 录音时间轴标注（失败点精确定位到第几分第几秒）+ 失败分类（技术/表达/行为）+ 根因分析 + 针对性训练建议 |

**教研内容生产流**：

| 产出物 | 最低细化度要求 |
| --- | --- |
| 课程大纲 | 每个模块：标题 + 知识点清单 + 学习目标（Bloom 层级）+ 建议时长 + 前置依赖 + 实战练习描述 + 评估方式 |
| 课程逐字稿 | 分节标注时间 + 讲课关键语句 + 板书/PPT 切换提示 + 提问设计（≥2 个/节）+ 学员可能的回答与引导方向 |
| 课程 PPT | 每页的标题、核心观点、配图描述、动画建议、预估讲解时长、与逐字稿的页码对照 |
| 代码演示 | 完整可运行代码 + 运行环境说明 + 注释覆盖率 ≥ 60% + 预期输出 + 常见错误与排查 |

#### 5.5.3 综合方案产出的可执行性要求

当 xAgent 执行跨多个 Agent 的复合任务时（如"简历优化 + 岗位匹配 + 模拟面试题 + 学习补课"），最终汇总方案必须满足：

1. **结构化交付清单**：每个子任务产出独立章节，标注来源 Agent、生成时间、置信度。
2. **优先级排序**：按紧急程度和依赖关系给出执行顺序。标注"今日必做"、"本周完成"、"面试前完成"。
3. **资源清单**：列出执行所需的所有文件引用（简历 file_id、课程录音片段、PPT file_id），可直接打开或下载。
4. **量化目标**：每项产出关联一个可测量的成功标准（如"投递 10 家公司后获得 ≥3 次面试邀请"）。
5. **风险提示**：标注可能失败的点、前置条件、建议的 Plan B。

#### 5.5.4 xAgent Agent Builder 完整 System Prompt（核心保障层）

> **设计原则（引用 Tencent Cloud #2668186 方法论）**："Harness 是 Agent 的'操作系统'，负责编排、调度、记忆、状态、工具治理、预算控制、可观测性、安全边界。Agent 负责局部智能，Harness 负责全局控制。"

为保证输出满足 L2 以上标准，xAgent Agent Builder 的 `instructions` 字段**必须使用以下完整 System Prompt**（不得使用简短版"you are a helpful assistant"）：

```markdown
# 角色定义

你是 53AIHub 的智能业务助手，服务于职坐标的教学、销售、教研和求职四大业务线。
你的核心价值不是"给建议"，而是"出方案"——你产出的每一项内容都必须是业务人员可以直接执行的，不需要他们再找你追问细节。

# 核心约束

## 输出质量等级要求
- 所有单 Agent 产出 → 必须达到 L2（可执行级）
- 复合任务综合方案 → 必须达到 L3（闭环方案级）

## L2 可执行级标准（硬约束）
每一项产出必须同时满足以下六个条件，缺一不可：
1. **有具体步骤**：不要说"建议补充相关技能"，要说"学习 Hadoop HDFS 原理（预计4周，每天2小时）"
2. **有时间标注**：每个行动标注预计耗时，规划有多级时间锚点（当日/本周/本月）
3. **有量化目标**：每个建议带数字（"投递 5-8 家/天"、"完成 3 个项目"、"累计刷 LeetCode 150 题"）
4. **有资源引用**：具体书名+章节、课程链接、练习编号、工具名+版本
5. **有风险提示**：前置条件、可能的失败点、Plan B
6. **结构化输出**：Markdown 格式，≥4 个二级标题，每个产出独立章节

## L3 闭环方案级标准
L2 全部满足 +：
7. **前置条件检查**：开始执行前需要什么
8. **交付物清单**：最终产出什么、什么格式、交付给谁
9. **验收标准**：怎么判断做完了、做好了
10. **回退路径**：如果失败怎么办

## 严格禁止的输出模式（Anti-Pattern）
以下表述在任何情况下不得出现：
- ❌ "建议补充相关技能" → ✅ "建议在 Week 1-2 学习 Hadoop HDFS 原理与搭建（参考《Hadoop权威指南》第4版 第3-6章，每天投入2小时）"
- ❌ "可以多投递简历" → ✅ "建议每天投递 5-8 家，目标累计投递 50 家后复盘回复率（基准回复率 15%）"
- ❌ "参考网上教程" → ✅ "参考：《Spring 实战》第5版 第8-12章；练习：LeetCode Hot 100 题 #1-30"
- ❌ "后续补充"、"慢慢来" → ✅ "Week 1-2: ...; Week 3-4: ..."
- ❌ "建议多练习" → ✅ "完成以下 3 个练习项目，每个项目标注验收标准：..."
- ❌ "注意提升" → ✅ "当前评分 45/100，目标评分 70/100。提升路径：Step 1... Step 2..."

## 信息不足处理原则
如果你发现某项输出因信息不足无法细化，**不要输出一个模糊的概括**。
必须明确输出：
```
⚠️ 需要补充以下信息才能细化此部分：
- 缺失字段 A（影响范围：...）
- 缺失字段 B（影响范围：...）
请提供以上信息后重新生成。
```

## 语言要求
全文使用中文输出（专业术语保留英文）。
```

> **重要提示**：上述 System Prompt 在 Agent Builder 创建时填入 `instructions` 字段。部署时参见 `docs/AI Hub xAgent 系统提示词工程与输出质量保障方案.md` 第 7.1 节获取完整配置清单。

#### 5.5.5 三层输出质量保障体系（新增核心设计）

> 参考 Tencent Cloud #2668186 文章方法论：输出质量不能仅靠 Prompt 倡议，必须通过 Harness 层面的门禁机制强制执行。

```text
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Result Analyzer Quality Gate（结果分析层）          │
│ - 检查每个子任务输出是否符合 L2/L3 标准                      │
│ - 不通过 → 触发"输出细化"重新生成步骤（最多 3 次重试）       │
│ - 通过 → 进入综合输出                                       │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: System Prompt Injection（指令注入层）               │
│ - Agent Builder System Prompt 中注入输出质量硬约束            │
│ - 每个 Step Agent 注入该步骤的输出模板（Scenario Prompt）     │
│ - 禁止空泛话术（明确的 Anti-Pattern 词库）                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Output Schema Enforcement（Schema 约束层）          │
│ - 每个业务场景定义结构化输出 Schema（字段名、类型、必填）     │
│ - Mock Gateway 返回符合 Schema 的示例数据                    │
│ - Step Agent 必须按 Schema 输出结构化 JSON                   │
└─────────────────────────────────────────────────────────────┘
```

**Layer 1 关键输出 Schema**：

每个业务场景的最终输出必须包含以下通用字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `generated_by` | string | 是 | 生成 Agent 名称 |
| `generated_at` | timestamp | 是 | 生成时间 |
| `confidence` | float(0-1) | 是 | 置信度 |
| `status` | enum | 是 | `complete` / `partial` / `insufficient_data` |
| `missing_info` | array | 否 | 需要补充的信息字段 |
| `executability_check` | object | 是 | 包含 `has_quantified_targets`、`has_timeline`、`has_resource_refs`、`has_risk_warnings`、`is_operational`、`word_count` |

**Layer 2 Scenario Prompt**：

当 DAG Planner 识别任务属于特定业务场景时，在 Step Agent 的 System Prompt 中额外注入场景相关的输出模板要求。详细模板定义见 `docs/AI Hub xAgent 系统提示词工程与输出质量保障方案.md` §4。

**Layer 3 Quality Gate**：

xAgent Result Analyzer 在综合结果之前，自动执行以下质量检查：

| 检查项 | 判定标准 | 不通过动作 |
| --- | --- | --- |
| 空泛建议检测 | 全文无 Anti-Pattern 词库中的短语 | 触发重生成，注入反例 |
| 量化指标覆盖率 | 全文 ≥ 15 个量化数字 | 触发重生成，要求在每个建议后加数字 |
| 时间线完整性 | ≥ 3 个时间层级 + 每操作有预计耗时 | 触发重生成，要求增加时间标注 |
| 资源引用充分性 | ≥ 8 个具体资源引用 | 触发重生成，要求补资源引用 |
| 结构化程度 | ≥ 6 个二级标题 + 表格/列表 | 触发重生成，要求结构化 |
| 风险提示 | ≥ 3 项风险（含概率+影响+Plan B） | 触发重生成，要求补风险分析 |

重生成流程：最多重试 3 次，3 次后仍不通过则输出降级内容 + 标注 `⚠️ 以下内容未达到可执行级标准，建议人工介入细化`。

#### 5.5.6 场景专属输出模板（求职全链路示例）

> 完整模板定义见 `docs/AI Hub xAgent 系统提示词工程与输出质量保障方案.md` 第 3 节。

> 完整模板定义见 `docs/AI Hub xAgent 系统提示词工程与输出质量保障方案.md` §3。

当任务为"简历优化 + 岗位匹配 + 模拟面试 + 学习补课"组合时，最终综合方案必须包含以下独立章节（每个 ≥ 500 字）：

1. **学员画像与背景分析**：基本信息（脱敏）、技能盘点（5 级评分）、转型可行性 SWOT 分析
2. **简历优化方案**：诊断 → 优化草稿（≥800字）→ 逐段修改说明 → JD 关键词匹配 → ATS 检查清单
3. **岗位匹配报告**：推荐岗位 × N（每个含 4 维匹配评分明细 + 差距 + 补强路径 + 薪资 + 竞品）
4. **模拟面试题**：≥ 3 道（每道含参考答案要点 + 建议答题时间 + 常见错误 + 评分细则）
5. **学习补课方案**：分阶段路径（每阶段含主题/时长/资源/练习/检测） + 实战项目 + 面试冲刺时间线
6. **综合行动计划总览**：优先级矩阵 + 时间甘特图 + 资源清单 + 成功标准 + 风险矩阵

## 6. 功能需求

### 6.1 Agent 能力注册中心

53AIHub 需要提供统一 Agent 能力导出协议，供 xAgent 同步工具元数据。

能力描述字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `agent_id` | integer | 是 | 53AIHub Agent ID |
| `eid` | integer | 是 | 企业 ID |
| `name` | string | 是 | 智能体名称 |
| `agent_type` | integer | 是 | `0=App`，`1=Workflow` |
| `platform_type` | string | 是 | `dify_agent`、`coze_workflow_cn` 等 |
| `channel_type` | integer | 是 | 53AIHub 渠道类型 |
| `description` | string | 是 | 给 Planner 使用的能力说明 |
| `input_schema` | object | 是 | 参数 Schema |
| `output_schema` | object | 是 | 输出 Schema |
| `risk_level` | string | 是 | `low`、`medium`、`high` |
| `requires_approval` | boolean | 是 | 是否需要人工确认 |
| `tags` | array | 否 | `sales`、`teaching`、`placement` 等 |
| `rate_limit` | object | 否 | 并发与调用频控 |
| `enabled` | boolean | 是 | 是否可被调度 |

导出接口建议：

```http
GET /api/agent-capabilities?enabled=true&scope=xagent
Authorization: Bearer <53AIHub admin/service token>
```

### 6.2 xAgent 工具同步

xAgent 侧需要将 53AIHub Agent 能力同步为 Custom API 工具或专用 53AIHub Tool。

第一阶段采用 Custom API，原因是 xAgent 已经支持 `/api/custom-apis`、密钥加密、ToolFactory 自动发现，改动较小。

同步策略：

1. 每个 53AIHub Agent 映射为一个 xAgent Custom API。
2. App Agent 默认调用 53AIHub `/v1/chat/completions`。
3. Workflow Agent 默认调用 53AIHub `/v1/workflow/run`。
4. tool name 使用稳定命名：`api_aihub_{agent_id}_{slug}_call`。
5. tool description 必须包含业务用途、输入限制、输出含义、风险等级、是否需要审批。
6. 53AIHub JWT 以 xAgent Custom API `env` 加密保存，headers 使用 `$AIHUB_TOKEN` 注入。

### 6.2.1 既有平台能力的标准接入要求

| 平台 | 输入规范 | 输出规范 | 状态与错误 | 记忆与回写 |
| --- | --- | --- | --- | --- |
| Dify | `messages` 或文件对象字符串；文件统一使用 `file_id:{id}` | 文本回答、评分、报告、知识点列表 | 透出 Dify conversation、渠道文件映射、429/5xx | 教学画像、作业评价、课程问答摘要 |
| Coze | `/v1/workflow/run` 的 `parameters`；禁止只依赖单个 `input` 字段 | `workflow_output_data` 标准化为报告、表格、脚本、文件产物 | 记录 `execute_id`、workflow id、参数校验错误 | 销售预案、教研资产、运营内容审批记录 |
| CRM | `lead_id`、`recording_id`、`sales_user_id`、`trace_id` | 录音摘要、复盘结论、成功案例、跟进回写状态 | CRM API 失败不吞错，回写必须幂等 | 销售画像、话术采纳、转化结果 |
| CareerMagic | `event_id`、`student_id`、`course_id`、练习上下文 | 学习事件、代码卡点、AI 提示回写、能力模型更新 | 事件去重，普通提示自动回写，高风险评分审批 | 学员画像、薄弱知识点、学习干预记录 |
| CareerOS | `student_id`、`job_id`、简历/JD 引用 | JD 推荐、JD 分析、模拟面试记录、复盘结果 | 求职建议审批后展示 | 能力模型、简历优化历史、面试复盘 |
| 豆包 | 测评模式、岗位方向、画像摘要、语音会话引用 | 题目记录、分数、薄弱点、追问建议 | 语音链路先保留豆包侧，53AIHub 记录摘要 | 入班测评、模拟面试画像 |

### 6.2.2 能力域与审批策略

| 能力域 | 代表智能体 | 默认审批策略 | 说明 |
| --- | --- | --- | --- |
| 教学答疑 | 1、5、9 | `none` | 普通问答可自动返回，涉及成绩写回时升级审批 |
| 作业评分 | 2 | `before_score_writeback` | AI 可先出评分草稿，助教批准后写回教学系统 |
| 销售预案 | 11、13、15 | `before_external_send` | 首电话术、承诺性内容必须销售确认 |
| 简历/职业规划 | 3、6、7、12 | `before_student_visible` | 对学员展示重大职业建议前需要顾问确认 |
| 内容运营 | 17、18、19 | `before_external_publish` | 小红书、封面、热点内容外发前合规审查 |
| 教研生产 | 23-28 | `before_asset_publish` | 课程资产进入正式版本库前教研审核 |
| 学习/求职系统回写 | 30、31 | `policy_by_field` | 普通提示自动回写，能力模型和结果评价可审批 |

### 6.3 53AIHub 调 xAgent

53AIHub 需要新增 xAgent 平台适配。建议作为新的智能体平台类型接入，而不是混在普通 Prompt Agent 中。

新增能力：

1. 管理后台新增 xAgent Provider 配置：Base URL、服务 Token、默认 execution mode、默认模型组、超时、最大步骤数。
2. Agent 创建页新增 xAgent Agent 类型。
3. 前台聊天发起复杂任务时调用 xAgent `/api/chat/task/create`。
4. 前台展示 xAgent 任务状态、DAG 计划、步骤日志、最终产物。
5. 任务完成后，将结果写入 53AIHub Conversation/Message。

建议请求映射：

```json
{
  "title": "销售预案生成",
  "description": "根据线索、简历和历史案例生成首电逐字稿",
  "execution_mode": "think",
  "agent_config": {
    "aihub_user_id": 123,
    "aihub_eid": 1,
    "source": "53AIHub",
    "workflow_key": "sales_to_success",
    "approval_required": true
  },
  "files": [],
  "llm_ids": ["general-model-id", "fast-model-id", "vision-model-id", "compact-model-id"]
}
```

### 6.4 Agent Handoff Protocol

跨 Agent 传递上下文时必须使用统一任务信封，避免平台之间丢字段、丢审计、丢权限。

```json
{
  "task_id": "aihub-task-20260506-0001",
  "workflow_key": "sales_to_success",
  "tenant": {
    "eid": 1,
    "user_id": 123,
    "user_group_ids": [2, 5]
  },
  "subject": {
    "type": "student",
    "id": "stu_001",
    "name": "脱敏姓名",
    "profile_ref": "memory://student/stu_001"
  },
  "input": {
    "text": "用户原始目标",
    "files": [],
    "structured": {}
  },
  "context": {
    "conversation_id": 619,
    "source_system": "53AIHub",
    "business_stage": "sales"
  },
  "constraints": {
    "max_steps": 12,
    "token_budget": 80000,
    "approval_required": true,
    "pii_policy": "mask_external_output"
  },
  "trace": {
    "request_id": "uuid",
    "parent_step_id": null
  }
}
```

### 6.5 长期记忆总线

第一阶段采用 xAgent 已有用户隔离记忆能力作为调度脑记忆层，同时在 53AIHub 保留业务主数据。后续可扩展为 LanceDB 或 Milvus 独立服务。

记忆类型：

| 类型 | 示例 | 写入来源 | 读取范围 |
| --- | --- | --- | --- |
| 学员画像 | 基础水平、目标岗位、学习偏好 | 入班测评、作业、面试复盘 | 教学、求职 |
| 销售画像 | 关注点、预算、转化阶段 | 官网线索、CRM、销售反馈 | 销售 |
| 能力模型 | Java 并发薄弱、项目表达弱 | 作业评估、模拟面试 | 教学、求职 |
| 成功案例 | 类似学员转化话术、就业路径 | CRM、求职结果 | 销售、求职 |
| 审核反馈 | 采纳、修改、驳回原因 | 人工闸口 | 调度优化 |

记忆写入要求：

1. PII 默认脱敏后写入向量记忆。
2. 原始敏感文件只保留在 53AIHub 文件存储或业务系统，记忆中保存引用。
3. 记忆必须带 `eid`、`subject_id`、`category`、`source_task_id`、`created_by`。
4. 高风险输出被人工修改后，修改差异需要作为反馈记忆保存。

### 6.6 审批闸口

高风险任务必须执行影子模式或人工确认。

需要审批的任务：

1. 对学员给出职业路径重大建议。
2. 对客户发送销售话术或承诺性内容。
3. 对作业给出最终评分且影响学员记录。
4. 对外发布小红书、官网、招聘相关内容。
5. 涉及合同、费用、就业承诺、法律合规内容。

审批动作：

| 动作 | 结果 |
| --- | --- |
| 批准 | 继续执行下游推送或回写 |
| 修改后批准 | 保存修改差异，继续执行 |
| 驳回 | 任务终止，记录原因 |
| 退回重规划 | xAgent 带约束重新生成计划 |

### 6.7 合规与审计

1. 所有外发文本必须通过 Moderation Agent 或合规规则层。
2. 所有文件上传到 Dify/Coze 前必须记录渠道文件映射、过期时间、原始文件 ID。
3. 53AIHub Relay 与 Workflow 调用必须记录 `request_id`、`agent_id`、`conversation_id`、`elapsed_time`、token、渠道 ID。
4. xAgent 必须记录 DAG 计划、步骤状态、工具调用结果、错误堆栈、token 用量。
5. 管理后台需要按任务、用户、学员、Agent、工作流维度查询审计记录。

## 7. 非功能需求

| 类别 | 要求 |
| --- | --- |
| 性能 | 文本任务首步触发 P95 < 2 秒；销售预案 P95 < 5 分钟；DAG 单任务默认最大 12 步 |
| 稳定性 | Coze/Dify 429、5xx 时重试或降级；xAgent 无限循环需要硬熔断 |
| 安全 | JWT 服务账号最小权限；密钥加密存储；PII 脱敏；按 `eid` 与用户组隔离 |
| 可观测 | 53AIHub 与 xAgent trace_id 贯通；每个步骤有开始、结束、耗时、输入摘要、输出摘要 |
| 可回放 | E2E 测试样本可重复执行；关键工作流保留输入、计划、输出、人工修改 |
| 可扩展 | 新增 Agent 不需要改 Planner 代码，只需补能力描述和 Schema |
| 兼容 | 现有 53AIHub Dify/Coze Agent 调用方式保持兼容 |

## 8. 数据模型增量建议

### 8.1 53AIHub 新增表

`agent_capabilities`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `eid` | 企业 ID |
| `agent_id` | 关联 `agents.agent_id` |
| `tool_name` | 导出给 xAgent 的稳定工具名 |
| `input_schema` | JSON Schema |
| `output_schema` | JSON Schema |
| `risk_level` | 风险等级 |
| `requires_approval` | 是否审批 |
| `tags` | 业务标签 |
| `enabled` | 是否可导出 |
| `version` | 能力描述版本 |

`agent_task_approvals`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `eid` | 企业 ID |
| `task_id` | 53AIHub 任务 ID 或 xAgent task ID |
| `step_id` | xAgent DAG step ID |
| `status` | pending/approved/rejected/replanned |
| `draft_output` | AI 草稿 |
| `final_output` | 审批后输出 |
| `reviewer_id` | 审批人 |
| `review_reason` | 修改或驳回原因 |

`agent_workflow_runs`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `eid` | 企业 ID |
| `workflow_key` | 四条业务流或自定义业务流 |
| `aihub_conversation_id` | 53AIHub 会话 |
| `xagent_task_id` | xAgent 任务 |
| `status` | running/completed/failed |
| `trace_id` | 贯通 trace |
| `metrics` | 延迟、步骤数、token、采纳状态 |

### 8.2 xAgent 侧增量建议

第一阶段尽量复用已有 `custom_apis`、`tasks`、`trace_events`。如需增强，建议增加：

1. 53AIHub capability sync job：将 53AIHub 能力同步到 Custom API。
2. Custom API metadata 扩展：保存 `source_system=53AIHub`、`source_agent_id`、`risk_level`、`input_schema`、`output_schema`。
3. Approval callback：xAgent 步骤进入 `PAUSED` 后向 53AIHub 创建审批记录。

## 9. API 合同

### 9.1 53AIHub App Agent 调用

```http
POST /v1/chat/completions
Authorization: Bearer <53AIHub JWT>
Content-Type: application/json
```

```json
{
  "model": "agent-1",
  "conversation_id": 619,
  "stream": false,
  "messages": [
    {
      "role": "user",
      "content": "请基于这份简历生成职业规划"
    }
  ]
}
```

### 9.2 53AIHub Workflow Agent 调用

```http
POST /v1/workflow/run
Authorization: Bearer <53AIHub JWT>
Content-Type: application/json
```

```json
{
  "model": "agent-13",
  "conversation_id": 619,
  "stream": false,
  "parameters": {
    "resume": "file_id:175",
    "career_plan": "职业规划摘要",
    "sales_context": "客户关注 Java 后端转行"
  }
}
```

### 9.3 xAgent 任务创建

```http
POST /api/chat/task/create
Authorization: Bearer <xAgent token>
Content-Type: application/json
```

```json
{
  "title": "销售转化预案",
  "description": "为线索 L001 生成职业规划、销售预案和钉钉推送内容",
  "execution_mode": "think",
  "agent_config": {
    "workflow_key": "sales_to_success",
    "aihub_trace_id": "uuid",
    "approval_required": true
  }
}
```

## 10. 验收标准

1. 管理员可在 53AIHub 配置 xAgent Provider，并创建 xAgent 调度型 Agent。
2. xAgent 可同步 53AIHub 已启用的 Dify/Coze/自研 Agent 能力，并在 Planner 中作为工具选择。
3. 四条主业务流至少各有一个端到端样例通过，包括成功路径、人工审批路径、失败回退路径。
4. 53AIHub 与 xAgent 的任务、会话、消息、trace_id 可以互相定位。
5. 关键 KPI 可统计：任务成功率、调度延迟、总耗时、token、采纳率、人工修改率、失败原因。
6. PII、权限、审计满足企业内测要求：跨用户、跨企业、跨用户组不可越权访问。

## 11. 风险与约束

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| Planner 无限循环 | 成本失控、任务超时 | 53AIHub 与 xAgent 双侧设置 max steps、timeout、token budget |
| 工具描述不准确 | xAgent 选错 Agent | 能力注册中心必须维护清晰 description、schema、示例 |
| Coze/Dify 频控 | 工作流失败 | 53AIHub 渠道健康、队列、重试、降级 |
| 文件跨平台映射失效 | 多模态工作流失败 | 复用现有 ChannelFileMapping，增加过期刷新测试 |
| 高风险输出误发 | 合规与业务风险 | 审批闸口默认开启，外发必须通过合规层 |
| 记忆污染 | 后续任务错误 | 记忆写入带来源、类别、置信度，支持人工修正和删除 |
