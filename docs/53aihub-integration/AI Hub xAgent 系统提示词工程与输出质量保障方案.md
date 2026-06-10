# AI Hub xAgent 系统提示词工程与输出质量保障方案

版本：v1.0
日期：2026-05-14
依据：`docs/AI Hub xAgent 集成需求设计文档.md` 5.5 节、`Tencent Cloud #2668186 生产级 Multi-Agent Harness 设计方法`
目标：使系统输出达到 L2（可执行级）以上，关键交付物达到 L3（闭环方案级）

---

## 1. 问题诊断

### 1.1 当前输出特征

验证案例 "学员张三（Java 2年经验 → 大数据方向）" 的实际输出表现为：

| 问题类型 | 具体表现 | 严重度 |
| --- | --- | --- |
| **总结化** | 每个子任务产物仅 3-5 句概括，缺少操作细节 | 阻塞 |
| **无模板约束** | 输出格式随意，缺少统一的结构化框架 | 阻塞 |
| **无量化指标** | "建议补充大数据技能"而非"Hadoop 3.x HDFS 原理与运维（预计4周，每天2h）" | 阻塞 |
| **无时间标注** | 缺少 Day-1/Week-1/Month-1 的时间锚点 | 阻塞 |
| **无资源引用** | "可以参考网上教程"而非具体书籍章节、课程链接、练习编号 | 高 |
| **无风险提示** | 只有正面建议，缺少前置条件、Plan B、失败模式 | 高 |

### 1.2 根因定位

引用参考文章（Tencent Cloud #2668186）的核心论断：

> "Harness 是 Agent 的'操作系统'，而非'多 Prompt 拼盘'。它负责编排、调度、记忆、状态、工具治理、预算控制、可观测性、安全边界。"

当前系统的三层架构中：
- **53AIHub**（API 网关/权限层）：已有 Agent 注册、鉴权、审批、文件映射 → ✅ 已就绪
- **xAgent DAG Planner/Executor**（调度脑）：已有 Plan Generator、Executor、Result Analyzer → ✅ 已就绪
- **输出质量治理层**（Harness Governance）：缺失 ❌ **← 这是根因**

也就是说，系统缺少一个**输出质量门禁（Output Quality Gate）**，在综合结果之前验证产出物是否达到 L2/L3 标准。

### 1.3 参考文章方法论映射

| 文章概念 | 映射到本系统 | 当前状态 |
| --- | --- | --- |
| Harness 全局控制 | xAgent DAG Planner + Result Analyzer | 部分就绪（有 planner 和 analyzer，缺 quality gate） |
| 声明式计划 | Planner 生成 DAG → 声明步骤目标而非命令 | ✅ 已就绪 |
| 工具治理（9 元信息） | Agent Capability Registry | 进行中（元信息需补全） |
| 四层评估体系 | 组件评估 → 轨迹评估 → 任务完成度 → 业务效果 | 仅 L1（轨迹评估），缺 L2-L4 |
| Token Budget 三层降级 | 当前无成本控制层 | 待建设 |
| 输出质量门禁 | **本方案核心建设内容** | ❌ 缺失 |

---

## 2. 整体方案：三层输出质量保障体系

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Result Analyzer Quality Gate（结果分析层）          │
│ - 检查每个子任务输出是否符合 L2/L3 标准                      │
│ - 不通过 → 触发"输出细化"重新生成步骤                       │
│ - 通过 → 进入综合输出                                       │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: System Prompt Injection（指令注入层）               │
│ - Agent Builder System Prompt 中注入输出质量硬约束            │
│ - 每个 Step Agent 注入该步骤的输出模板                      │
│ - 禁止空泛话术（明确的 anti-pattern 词库）                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Output Schema Enforcement（Schema 约束层）          │
│ - 每个业务场景定义结构化输出 Schema（字段名、类型、必填）     │
│ - Mock Gateway 返回符合 Schema 的示例数据                   │
│ - Step Agent 必须按 Schema 输出结构化 JSON                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 1：结构化输出 Schema 定义

### 3.1 核心原则

> 参考文章方法论："每个工具需登记 9 项元信息。Schema 是 Harness 对 Agent 的合约，不是约束而是保障。"

每个业务场景的输出不再是自由文本，而是带 Schema 的结构化 JSON，由 DAG Planner 在规划阶段就声明目标输出格式。

### 3.2 通用输出 Schema（所有场景共有字段）

```json
{
  "$schema": "https://53aihub.com/output-schema/v1",
  "output_version": "1.0",
  "generated_by": "<Agent Name>",
  "generated_at": "<ISO 8601 timestamp>",
  "confidence": 0.0-1.0,
  "status": "complete | partial | insufficient_data",
  "missing_info": ["需要补充的信息字段列表"],
  "content": { /* 具体场景内容 */ },
  "executability_check": {
    "has_quantified_targets": true,
    "has_timeline": true,
    "has_resource_refs": true,
    "has_risk_warnings": true,
    "is_operational": true,
    "min_word_count": 0,
    "actual_word_count": 0
  }
}
```

### 3.3 求职全链路输出 Schema

当任务为"简历优化 → 岗位匹配 → 模拟面试题 → 学习补课"时，最终输出必须包含以下结构化章节：

```json
{
  "job_seeker_profile": {
    "name": "张三（已脱敏）",
    "current_role": "Java 开发工程师",
    "years_of_experience": 2,
    "current_skills": ["Java SE", "Spring Boot", "MySQL", "..."],
    "target_direction": "大数据开发",
    "reason_for_transition": "...",
    "budget": "待确认"
  },
  "resume_optimization": {
    "original_summary": "原简历 200 字摘要",
    "optimized_summary": "优化后简历草稿（≥500字）",
    "diff_sections": [
      {
        "section": "个人简介",
        "before": "...",
        "after": "...",
        "reason": "强化大数据关键词，补充量化成果"
      }
    ],
    "jd_keyword_match": {
      "target_jd": "大数据开发工程师",
      "keywords_covered": ["Hadoop", "Spark", "ETL"],
      "keywords_missing": ["Flink", "Hive SQL"],
      "match_rate": "65%"
    },
    "quantified_achievements_added": [
      "原：负责XX系统开发 → 新：主导XX系统开发，日处理数据量从1GB提升至50GB，接口响应时间优化40%"
    ],
    "ats_checklist": {
      "has_standard_headings": true,
      "has_keyword_density": "12%",
      "has_no_images_or_tables": true,
      "has_consistent_formatting": true,
      "overall_ats_score": "85/100"
    },
    "optimization_tips": [
      "建议在项目经历中补充使用 Kafka 的场景，即使只是学习项目",
      "大数据岗位 JD 中 Spark 出现率 78%，建议将 Spring Boot 项目中的数据处理部分强化为 Spark 处理"
    ]
  },
  "job_matching": {
    "recommended_positions": [
      {
        "title": "大数据开发工程师",
        "match_score": 88,
        "score_breakdown": {
          "skill_match": "60/100（Java基础匹配，需补Spark/Hadoop）",
          "experience_match": "70/100（2年工程经验可迁移）",
          "education_match": "90/100",
          "location_match": "85/100"
        },
        "salary_range": "15K-25K （一线城市）",
        "competitor_companies": ["阿里云", "腾讯云", "字节跳动数据平台"],
        "gap_analysis": [
          {"gap": "Spark 实战经验", "priority": "high", "fix_time": "4周"},
          {"gap": "Hive SQL 复杂查询", "priority": "high", "fix_time": "2周"},
          {"gap": "Flink 实时计算", "priority": "medium", "fix_time": "4周"}
        ],
        "interview_focus": ["Spark Shuffle 原理", "HDFS 读写流程", "Hive 调优"]
      }
    ],
    "transition_advice": {
      "feasibility": "高（Java 基础是最大优势，大数据框架多为 Java/Scala 生态）",
      "estimated_transition_time": "8-12周全职学习 + 4周求职",
      "key_leverage_points": [
        "Java 多线程经验 → Spark 并行计算理解",
        "Spring Boot 系统设计经验 → 数据平台架构理解",
        "MySQL 经验 → Hive SQL 快速上手"
      ]
    }
  },
  "mock_interview": {
    "questions": [
      {
        "question_number": 1,
        "category": "JVM 基础",
        "difficulty": "medium",
        "question": "请解释 JVM 的类加载机制，以及双亲委派模型在大数据场景下可能遇到的问题？",
        "reference_answer_points": [
          "类加载的三个阶段：加载、链接、初始化",
          "双亲委派模型的目的和流程",
          "大数据场景下 Jar 包冲突的常见原因（如 Hadoop/Spark 依赖冲突）"
        ],
        "suggested_answer_time": "3-5分钟",
        "common_mistakes": ["只回答了JVM基础，未联系大数据场景", "遗漏双亲委派的破坏场景"],
        "score": 0,
        "scoring_rubric": {
          "completeness": "0-25分 是否涵盖全部要点",
          "depth": "0-25分 是否有深度思考",
          "relevance": "0-25分 是否联系大数据场景",
          "clarity": "0-25分 表达是否清晰"
        }
      }
    ],
    "overall_assessment": {
      "total_score": "72/100",
      "radar_chart": {
        "jvm_basics": 75,
        "system_design": 65,
        "cache_strategy": 60,
        "distributed_systems": 45,
        "data_pipeline": 50,
        "problem_solving": 80,
        "communication": 70,
        "project_experience": 68
      },
      "examiner_feedback": "JVM基础和问题解决能力扎实，但缓存设计和分布式系统为明显薄弱项。建议重点补强分布式理论（CAP、一致性协议）和至少完成一个端到端的数据管道项目。"
    }
  },
  "learning_plan": {
    "total_duration": "8-12周",
    "weekly_hours": "每天3-4小时，周末6-8小时",
    "phases": [
      {
        "phase": 1,
        "name": "大数据基础（Week 1-2）",
        "topics": [
          {"name": "Hadoop 3.x HDFS 原理与运维", "hours": 12, "resources": "《Hadoop权威指南》第4版 第3-6章", "practice": "搭建3节点Hadoop集群"},
          {"name": "MapReduce 编程模型", "hours": 8, "resources": "官网 Tutorial + 实验楼 MapReduce 实战", "practice": "完成 WordCount 进阶版（TOP N + 二次排序）"},
          {"name": "Hive 数据仓库", "hours": 10, "resources": "《Hive编程指南》第1-5章", "practice": "基于 TPCDS 数据集完成10个复杂查询"}
        ],
        "checkpoint": "能用 Hive 完成复杂数据分析需求，产出分析报告"
      },
      {
        "phase": 2,
        "name": "核心计算引擎（Week 3-5）",
        "topics": [
          {"name": "Spark 3.x Core/RDD", "hours": 15, "resources": "《Spark快速大数据分析》第3-8章", "practice": "用 RDD 实现 PageRank + 协同过滤"},
          {"name": "Spark SQL/DataFrame", "hours": 12, "resources": "官方 Structured Streaming 指南", "practice": "ETL 管道：MySQL → Spark → Hive"},
          {"name": "Kafka 消息系统", "hours": 10, "resources": "《Kafka权威指南》第1-5章", "practice": "搭建 Kafka 集群 + 实现 exactly-once 语义"}
        ],
        "checkpoint": "能独立完成 Spark 批处理任务开发，理解 Kafka 在数据管道中的作用"
      },
      {
        "phase": 3,
        "name": "流处理与进阶（Week 6-8）",
        "topics": [
          {"name": "Flink 实时计算", "hours": 15, "resources": "《Stream Processing with Apache Flink》第1-6章", "practice": "实时大屏：Kafka → Flink → Redis → Grafana"},
          {"name": "数据仓库建模（维度建模）", "hours": 8, "resources": "《数据仓库工具箱》第3版", "practice": "为电商场景设计星型模型"},
          {"name": "分布式理论", "hours": 8, "resources": "DDIA 第5-9章", "practice": "写 CAP/Paxos/Raft 的理解笔记"}
        ],
        "checkpoint": "能设计数据管道架构，理解分布式一致性"
      }
    ],
    "practice_project": {
      "name": "电商用户行为分析平台",
      "description": "模拟生产环境，构建完整的用户行为数据管道",
      "tech_stack": ["Flume/Kafka（采集）", "Spark Streaming/Flink（计算）", "Hive（存储）", "Grafana（展示）"],
      "deliverables": ["系统架构图", "全链路代码（GitHub 开源）", "性能压测报告", "README 文档"],
      "estimated_hours": 60,
      "interview_value": "高（能展示全链路理解能力）"
    },
    "interview_preparation": {
      "week_7_to_8": "刷题：LeetCode Hot 100 + 剑指 Offer（每天2题）",
      "week_9_to_10": "模拟面试：每周2次，覆盖数据结构/算法/系统设计/大数据",
      "week_11_to_12": "投递+复盘：每天投递5-8家，每周复盘面试反馈，动态调整学习重点"
    },
    "success_criteria": {
      "learning": "能独立完成电商数据分析平台的端到端开发",
      "interview": "投递10家，获得 ≥3 次面试邀请",
      "offer": "获得 ≥1 个大数据相关岗位 offer",
      "fallback": "若12周后未达标，延长学习至16周 + 考虑大数据测试/运维方向作为过渡"
    }
  },
  "combined_action_plan": {
    "priority_matrix": {
      "today_must_do": [
        "对照ATS检查清单修改简历（预计1小时）",
        "注册 LeetCode，开始每日刷题",
        "下载《Hadoop权威指南》电子版，完成第一章阅读"
      ],
      "this_week": [
        "完成简历优化并请导师 review",
        "搭建本地 Hadoop 开发环境（Docker Compose）",
        "完成 HDFS 基础实验"
      ],
      "before_interview": [
        "完成电商数据分析平台项目并上传 GitHub",
        "至少完成 6 次模拟面试",
        "准备 3 个能展示大数据能力的项目故事"
      ]
    },
    "risks_and_mitigations": [
      {
        "risk": "学习曲线陡峭，中途放弃",
        "probability": "中",
        "impact": "高",
        "mitigation": "每周设置小目标（如'搭建Hadoop集群'），完成后打卡记录；加入大数据学习社群获取同行支持"
      },
      {
        "risk": "市场招聘需求波动",
        "probability": "低-中",
        "impact": "中",
        "mitigation": "同时准备后端开发+大数据两个方向，先以大数据岗位为主，2个月无进展则拓展到后端数据方向"
      },
      {
        "risk": "模拟面试题与实际面试差距大",
        "probability": "中",
        "impact": "中",
        "mitigation": "每2周用真实 JD 重新生成模拟面试题；收集近期面经更新面试题库"
      }
    ]
  }
}
```

---

## 4. Layer 2：System Prompt 注入方案

### 4.1 Agent Builder 主 System Prompt

以下 Prompt 必须配置到 xAgent Agent Builder 的 `instructions` 字段（部署文档 4.8 节），替换当前的简短版本：

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

## 严格禁止的输出模式
以下表述在任何情况下不得出现：
- ❌ "建议补充相关技能" → ✅ "建议在 Week 1-2 学习 Hadoop HDFS 原理与搭建（参考《Hadoop权威指南》第4版 第3-6章，每天投入2小时）"
- ❌ "可以多投递简历" → ✅ "建议每天投递 5-8 家，目标累计投递 50 家后复盘回复率（基准回复率 15%）"
- ❌ "参考网上教程" → ✅ "参考：《Spring 实战》第5版 第8-12章；练习：LeetCode Hot 100 题 #1-30"
- ❌ "后续补充"、"慢慢来" → ✅ "Week 1-2: ...; Week 3-4: ..."
- ❌ "建议多练习" → ✅ "完成以下 3 个练习项目，每个项目标注验收标准：..."
- ❌ "注意提升" → ✅ "当前评分 45/100，目标评分 70/100。提升路径：Step 1... Step 2..."

## 输出格式要求
- 必须使用 Markdown 结构化格式
- 每个二级标题 `##` 对应一个独立产出章节
- 每个章节标注来源 Agent、生成时间、置信度
- 涉及文件时使用 `file_id:xxx` 格式引用
- 外部资源使用完整 URL
- 所有建议必须嵌入表格、列表或代码块，不得出现纯段落式的"建议"

## 信息不足处理
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

### 4.2 求职全链路 Scenario Prompt 注入

当检测到任务属于"简历优化 + 岗位匹配 + 模拟面试 + 学习补课"组合时，在 System Prompt 中额外注入：

```markdown
# 场景专属要求：求职全链路辅导方案

你正在为一个学员生成全套求职辅导方案。这是一个包含 4 个子任务的复合方案，必须达到 L3 闭环方案级输出。

## 输出必须包含的章节（每个都是独立章节，不可合并）

### 第一章：学员画像与背景分析
- 学员基本信息（脱敏）
- 现有技能盘点（按熟练度分 1-5 级）
- 目标方向定位分析
- 转型可行性评估（优势/劣势/机会/威胁四象限）
- 技能迁移路径图（现有技能 → 目标岗位要求 SQL 对照）

### 第二章：简历优化方案
- 原简历问题诊断（按段落标注）
- 优化后简历完整草稿（≥ 800 字）
- 逐段修改说明（每段标注：改了哪里、为什么改、预期效果）
- JD 关键词匹配分析（图标展示，标注覆盖率）
- ATS 友好度检查清单（10 项 check）
- 量化成果补充建议（每段经历至少 1 项量化指标）

### 第三章：岗位匹配报告
- 推荐岗位列表（每个岗位含匹配度评分 + 评分明细表）
- 技能差距分析（每个差距标注严重程度、补强方法、预计时间）
- 薪资范围 & 竞品公司
- 转型路径建议（分阶段，标注每个阶段的投递策略）

### 第四章：模拟面试题
- 至少 3 道面试题，覆盖不同知识领域
- 每题含：题目、参考答案要点（不是唯一答案）、建议答题时间、常见错误
- 综合评分雷达图（≥6 个维度，每个维度 0-100 评分）
- 考官评语（包含亮点 + 薄弱项 + 针对性提升建议）

### 第五章：学习补课方案
- 学习路径图（分阶段，每阶段 1-N 周）
- 每个阶段：主题、学习内容、预计时长、参考资源、实战练习、阶段检测方法
- **参考资源必须具体**：书名+版本+章节、课程名称+链接、练习编号
- 实战项目建议（项目名称、技术栈、产出物、预估耗时）
- 每周实战目标（可 check 的 checkbox 形式）
- 面试冲刺计划（刷题 → 模拟 → 投递 → 复盘的时间线）

### 第六章：综合行动计划总览
- 优先级矩阵（今日必做 / 本周完成 / 面试前完成）
- 时间甘特图（文本形式，标注关键里程碑）
- 资源清单（所有引用的 file_id、URL、书籍、工具）
- 成功标准（每个环节的可测量目标 + 达标判断方法）
- 风险矩阵（风险描述 + 概率 + 影响 + 缓解措施 + Plan B）

## 格式要求
- 全文使用中文，Markdown 结构化输出
- 每个章节 ≥ 500 字（模拟面试题除外，每道题 ≥ 200 字）
- 学习方案总字数 ≥ 1500 字
- 所有评分使用 0-100 制，附带置信度百分比
- 所有时间标注使用"Week 1-2 每天投入 X 小时"格式
- 所有资源必须可检索（书名+ISBN、URL、file_id）
```

### 4.3 销售转化流 Scenario Prompt 注入

```markdown
# 场景专属要求：销售转化全链路

## 首电逐字稿要求
- 完整结构化：开场白 → 需求探询（≥5 个追问点）→ 价值呈现（≥3 个卖点）→ 异议处理（≥5 种常见异议）→ 关单引导 → 跟进锚点
- 逐字稿 ≥ 800 字
- 每个环节标注预计时长（如"开场白 1 分钟"）
- 每个追问点有预设的用户可能回答 + 对应应对话术

## 异议处理手册
- 每种异议含：异议原文、心理原因分析、应对话术（≥2 套）、避雷提示
- 覆盖面 ≥ 5 种常见异议（价格类、效果类、竞品类、时间类、决策类）

## 客户画像
- 8 个必填字段：基础信息、来源、技术方向、决策角色、预算区间、紧急程度、历史交互、竞品情况
- 每个字段有明确值或"待确认"标注

## 跟进建议
- 时间节点（当天 → 3天 → 7天）的独立动作
- 每个动作有目标 + 话术锚点 + 预期结果 + 不成功时的 Plan B
```

### 4.4 教学管理流 Scenario Prompt 注入

```markdown
# 场景专属要求：教学管理

## 作业评估报告
- 总体评分 + 逐题评分明细 + 每题扣分原因 + 知识点归类
- 错误模式分析（按类型分类：逻辑错误/语法错误/设计问题/边界遗漏）
- 与上次作业的变化趋势（进步点/退步点）
- 改进建议按优先级排序，标注预计练习时长

## 补课方案可操作性
- 按知识点分组补充材料
- 每个知识点标注：课程录音片段时间戳、教材章节页码、练习题目编号
- 学习顺序有先后依赖标注
- 每个知识点标注预计学习时间

## 学员能力模型
- 技能雷达图（≥8 个维度），每个维度 0-100 评分
- 标注置信度（高/中/低）
- 历史分数曲线
- 目标岗位对标差距
- 建议优先提升的 Top 3 维度
```

### 4.5 教研内容生产流 Scenario Prompt 注入

```markdown
# 场景专属要求：教研内容生产

## 课程大纲
每个模块必须包含：
- 模块标题 + 知识点清单
- 学习目标（使用 Bloom 认知层级标注：记忆/理解/应用/分析/评价/创造）
- 建议时长（分钟）
- 前置依赖（本模块需要先完成哪些模块）
- 实战练习描述（具体到题目级别）
- 评估方式（笔试/项目/代码 Review）

## 课程逐字稿
- 分节标注时间（精确到分钟）
- 讲课关键语句（标注哪些必须原话讲）
- 板书/PPT 切换提示（标注切换时机）
- 提问设计（≥2 个/节，包含预设的学员回答和引导方向）

## 课程 PPT
- 每页：标题 + 核心观点（一句话总结）+ 配图描述 + 动画建议 + 预估讲解时长 + 逐字稿页码对照

## 代码演示
- 完整可运行代码 + 运行环境说明（Docker/本地/在线）
- 注释覆盖率 ≥ 60%
- 预期输出 + 常见错误与排查
```

---

## 5. Layer 3：输出质量门禁（Quality Gate）

### 5.1 设计思路

> 参考文章方法论："四层评估体系 → 组件评估、轨迹评估、任务完成度评估、端到端业务效果评估"

在 xAgent 的 Result Analyzer（`result_analyzer.py`）中增加一个 **输出质量自检步骤**，在综合结果前自动检查产物是否达标。如果不达标，自动注入细化指令让 Step Agent 重新生成。

### 5.2 Quality Gate Prompt

此 Prompt 需添加到 xAgent `result_analyzer.py` 的 `_build_comprehensive_goal_check_prompt` 之后，作为独立的质量检查步骤：

```markdown
# 输出质量门禁检查（Harness Quality Gate）

你正在对 DAG 执行结果进行质量检查。请逐项验证以下标准：

## L2 可执行级检查清单（单项不通过 → 整体不通过）

### 检查项 1：空泛建议检测
搜索以下关键词，如果出现在最终输出中 → 不通过：
- "建议补充相关技能"（无具体技能名）
- "多练习"、"多投递"（无量化数字）
- "可以参考网上教程"（无具体引用）
- "后续补充"、"慢慢来"（无时间节点）
- "注意提升"（无目标值和提升路径）
- "建议" 后没有跟具体数字/名称/操作

### 检查项 2：量化指标覆盖率
- 全文至少出现 15 个量化数字（百分比、数量、时长、金额）
- 每个子任务产出至少关联 1 个可测量目标

### 检查项 3：时间线完整性
- 至少包含 3 个时间层级（如：当日/本周/本月 或 Week 1-2/Week 3-5/Week 6-8）
- 每个操作步骤有预计耗时

### 检查项 4：资源引用充分性
- 不得出现"网上搜索"、"找相关教程"等空泛指引
- 每个学习建议必须标注具体引用（书名+章节 或 URL 或 练习编号）
- 全文至少 8 个具体资源引用

### 检查项 5：结构化输出
- 至少 6 个二级标题（`## 章节名`）
- 使用了表格、列表或代码块（不是纯段落文字）

### 检查项 6：风险提示
- 至少 3 项风险提示，每项含：风险描述 + 概率 + 影响 + Plan B

## 判定结果
{
  "quality_pass": true/false,
  "failed_items": ["检查项1", "检查项3"],
  "score": 0-100,
  "recommendation": "通过 / 需细化（列出具体需要细化的点）"
}
```

### 5.3 触发重生成机制

当 Quality Gate 判定不通过时，xAgent DAG Engine 应：

1. **记录质量检查结果**到 trace event（`quality_gate_check`）
2. **构造细化指令**：将 `failed_items` 转为具体的改进要求
3. **触发 Step Agent 重新生成**：传入原输出 + 细化指令
4. **再次质检**：最多重试 3 次
5. **降级标识**：3 次仍不通过 → 输出不通过的内容 + 明确标注 `⚠️ 以下内容未达到可执行级标准，建议人工介入细化`

### 5.4 实现细节

#### 5.4.1 `result_analyzer.py` — 新增 Quality Gate Prompt

在 `_build_comprehensive_goal_check_prompt` 方法之后（约 line 430），新增方法：

```python
def _build_quality_gate_prompt(
    self,
    goal: str,
    final_answer: str,
    step_outputs: List[Dict[str, Any]]
) -> str:
    """构建输出质量门禁检查 Prompt。

    在 result analyzer 综合结果之前调用，检查各步骤输出是否达到 L2/L3 标准。
    返回 JSON: {"pass": bool, "score": int, "failed_items": [...], "recommendation": str}
    """
    anti_patterns = [
        "建议补充相关", "建议多练习", "建议多投递", "可以参考网上",
        "后续补充", "慢慢来", "根据情况", "网上有很多", "搜索一下",
        "注意提升", "尽量做好"
    ]

    return f"""# 输出质量门禁检查

你正在对以下 DAG 执行结果进行质量检查。请逐项验证 L2 可执行级标准。

## 原始目标
{goal}

## 综合结果
{final_answer[:3000]}  # 截断以防超 token

## 检查清单

### 1. 空泛建议检测
搜索 Anti-Pattern 词库：{anti_patterns}
全文出现任意一个 → failed_items 加入 "空泛建议"

### 2. 量化指标覆盖率
统计全文量化数字（百分比/数值/时长/金额）：目标 >= 15 个
不足 → failed_items 加入 "量化指标不足"

### 3. 时间线完整性
检查时间层级数（日/周/月/阶段）：目标 >= 3 层
不足 → failed_items 加入 "时间线不足"

### 4. 资源引用充分性
统计具体资源引用（书名+章节/URL/练习编号）：目标 >= 8 个
不足 → failed_items 加入 "资源引用不足"

### 5. 结构化输出
统计二级标题（##）：目标 >= 6 个 + 表格/列表
不足 → failed_items 加入 "结构化不足"

### 6. 风险提示
统计风险项（含概率+影响+Plan B）：目标 >= 3 项
不足 → failed_items 加入 "风险提示不足"

## 输出格式
{{
  "pass": true/false,
  "score": 0-100,
  "failed_items": ["检查项名"],
  "quantified_metrics": {{
    "quantified_numbers_count": N,
    "time_levels_count": N,
    "resource_refs_count": N,
    "h2_headings_count": N,
    "risk_items_count": N,
    "word_count": N,
    "anti_pattern_hits": ["命中短语"]
  }},
  "recommendation": "通过 / 需细化：列出具体需要细化的点"
}}
"""
```

#### 5.4.2 `schemas.py` — 新增 QualityGateResult Pydantic Model

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class QualityGateMetrics(BaseModel):
    """质量门禁量化指标"""
    quantified_numbers_count: int = 0
    time_levels_count: int = 0
    resource_refs_count: int = 0
    h2_headings_count: int = 0
    risk_items_count: int = 0
    word_count: int = 0
    anti_pattern_hits: List[str] = Field(default_factory=list)

class QualityGateResult(BaseModel):
    """输出质量门禁检查结果"""
    pass_: bool = Field(alias="pass")
    score: int = 0          # 0-100
    failed_items: List[str] = Field(default_factory=list)
    metrics: Optional[QualityGateMetrics] = None
    recommendation: str = ""
    retry_count: int = 0    # 当前已是第几次重试
    checked_at: Optional[datetime] = None
```

#### 5.4.3 `dag_plan_execute.py` — 增加质量检查步骤

在 `_run_execution_loop` 方法中，`result = await self.result_analyzer.analyze(...)` 之后、返回 result 之前插入：

```python
# [新增] 输出质量门禁检查
MAX_QUALITY_RETRIES = 3
quality_retry_count = 0

while quality_retry_count < MAX_QUALITY_RETRIES:
    quality_result = await self.result_analyzer.check_quality_gate(
        goal=task_description,
        final_answer=result.final_answer,
        step_outputs=step_results
    )

    # 记录 trace event
    await self._emit_trace_event("quality_gate_check", {
        "attempt": quality_retry_count + 1,
        "pass": quality_result.pass_,
        "score": quality_result.score,
        "failed_items": quality_result.failed_items,
        "metrics": quality_result.metrics.dict() if quality_result.metrics else {}
    })

    if quality_result.pass_ or quality_retry_count >= MAX_QUALITY_RETRIES - 1:
        if not quality_result.pass_:
            # 最后一次仍不通过 → 降级输出 + 人工介入标注
            result.final_answer = (
                "⚠️ 以下内容未达到可执行级标准，建议人工介入细化。\n\n"
                f"质量检查未通过项：{quality_result.failed_items}\n"
                f"质量评分：{quality_result.score}/100\n\n"
                f"{result.final_answer}"
            )
            result.quality_degraded = True
        break

    # 不通过 → 构造细化指令 → 重生成
    refinement_instruction = (
        f"你之前的输出未通过质量检查。以下方面需要细化：\n"
        + "\n".join(f"- {item}" for item in quality_result.failed_items)
        + "\n\n请基于原有内容，补充以下信息后重新输出完整的方案：\n"
        + self._build_refinement_hints(quality_result.failed_items)
    )

    result = await self.result_analyzer.regenerate_with_refinement(
        goal=task_description,
        previous_output=result.final_answer,
        refinement_instruction=refinement_instruction
    )
    quality_retry_count += 1
```

#### 5.4.4 细化指令构造逻辑

```python
def _build_refinement_hints(self, failed_items: List[str]) -> str:
    """根据失败项构造具体的细化指令"""
    hints = []
    for item in failed_items:
        if "空泛建议" in item:
            hints.append("- 将每个"建议"改为具体的操作步骤（含技术栈名称、版本、时间预估）")
        if "量化指标" in item:
            hints.append("- 在每个建议后增加量化数字：预计时长、目标次数、金额、百分比")
        if "时间线" in item:
            hints.append("- 为每个行动标注具体时间节点（今日/本周/Week N），避免"后续"、"慢慢来"")
        if "资源引用" in item:
            hints.append("- 补充具体资源：书名+版本+章节、LeetCode 题号、课程 URL")
        if "结构化" in item:
            hints.append("- 使用 Markdown ## 二级标题分章节，每个建议用列表或表格呈现")
        if "风险提示" in item:
            hints.append("- 在方案末尾增加风险矩阵（至少 3 项，每项含概率+影响+Plan B）")
    return "\n".join(hints) if hints else "- 请提供更多具体内容和量化数据以满足可执行级标准。"
```

#### 5.4.5 文件修改清单

| 文件 | 新增方法/类 | 新增行数（估算） |
| --- | --- | --- |
| `src/xagent/core/agent/pattern/dag_plan_execute/schemas.py` | `QualityGateMetrics`、`QualityGateResult` | ~30 行 |
| `src/xagent/core/agent/pattern/dag_plan_execute/result_analyzer.py` | `_build_quality_gate_prompt()`、`check_quality_gate()`、`regenerate_with_refinement()` | ~120 行 |
| `src/xagent/core/agent/pattern/dag_plan_execute/dag_plan_execute.py` | `_run_execution_loop` 中插入 quality gate 逻辑、`_build_refinement_hints()` | ~60 行 |
| `src/xagent/core/agent/pattern/dag_plan_execute/models.py` | `DAGExecutionTrace` 增加 `quality_gate_event` 字段 | ~10 行 |

---

## 6. Mock Gateway 输出升级：从摘要到完整 Schema

### 6.1 当前问题

当前 Mock Gateway 返回的模拟数据过于简单，例如 Mock Agent 2（IT 作业评估）仅返回几行评分文字，导致 DAG 综合时缺少结构化数据。

### 6.2 升级要求

所有 Mock Agent 的输出必须改为符合 L2 标准的完整结构。以下是关键 Agent 的升级前后对比和具体输出 Schema。

| Agent | 当前输出（示例） | 升级后输出（示例） |
| --- | --- | --- |
| Agent 2（作业评估） | `"score: 85, comments: good"` | 完整的 5 维度评分明细 + 每题扣分原因 + 错误模式分析 + 改进建议 |
| Agent 41（CRM 线索查询） | `"L001, 官网, 初次沟通"` | 包含 8 字段的完整客户画像 + 历史交互摘要 + 上次跟进结果 |
| Agent 13（销售预案） | `"电话话术 + 异议处理"` | 完整的 6 段式逐字稿（≥800字）+ 5 种异议处理手册 + 跟进时间线 |
| Agent 61（岗位推荐） | `"大数据工程师，匹配度88%"` | 4 维匹配评分明细 + 差距列表 + 补强路径 + 薪资+竞品 |
| Agent 22（百问百答） | `"3道题，得分72"` | 逐题评分 + 亮点/改进 + 参考答案要点 + 三维度雷达图 |

### 6.3 Mock 数据膨胀策略

在 `api/service/mock_gateway/fixtures/` 中引入三种场景模式的数据文件：

1. **成功模式**（`scenario=success`）：返回完整 L2 结构数据
2. **精简模式**（`scenario=summary_only`）：返回低质量数据（L0/L1），用于测试 Quality Gate 能否检测到并触发重生成
3. **边界模式**（`scenario=partial`）：返回部分字段，用于测试降级流程

### 6.4 关键 Agent L2 输出 Fixture 示例

#### Agent 41 — CRM 线索查询（`fixtures/leads.json`）

> 改造前：`"L001, 官网, 初次沟通, 预算 15000-20000"`
> 改造后：

```json
{
  "agent_no": 41,
  "scenario": "success",
  "output": {
    "lead_id": "L001",
    "generated_at": "2026-05-14T10:30:00Z",
    "confidence": 0.95,
    "customer_profile": {
      "basic_info": {
        "name": "张三",
        "age_range": "25-30",
        "education": "本科",
        "current_location": "上海",
        "target_location": "上海/杭州"
      },
      "source": "官网表单",
      "tech_direction": {"primary": "Java后端", "years": 2, "target": "大数据开发"},
      "decision_role": "自费学员（个人决策）",
      "budget_range": {"min": 15000, "max": 20000, "currency": "CNY", "flexibility": "中等（可协商分期）"},
      "urgency": "中（计划3个月内转行）",
      "history_interactions": [
        {"date": "2026-05-10", "channel": "官网", "summary": "提交联系表单，咨询大数据课程"},
        {"date": "2026-05-12", "channel": "电话", "summary": "首电沟通，确认Java基础和学习意向，约二轮详细咨询"}
      ],
      "competitors": ["达内教育（已咨询）","尚硅谷（正在对比）"]
    },
    "lead_status": "初次沟通",
    "assigned_sales": {"id": "S005", "name": "销售顾问A"},
    "missing_fields": ["身份证号（PII不采集）","具体公司名（待确认）"]
  }
}
```

#### Agent 13 — 销售预案（`fixtures/agents_coze.json`）

> 改造前：`"call_script: 您好... (3行), objection_handling: [{...}] (1条)"`
> 改造后：

```json
{
  "agent_no": 13,
  "scenario": "success",
  "output": {
    "generated_at": "2026-05-14T10:32:00Z",
    "confidence": 0.88,
    "call_script": {
      "total_duration_minutes": 15,
      "sections": [
        {
          "section": "开场白",
          "duration_seconds": 60,
          "script": "张三你好，我是职坐标的销售顾问A。上次电话我们简单聊了你从Java转大数据的想法，今天我想详细跟你分析一下你的技术背景怎么跟大数据岗位衔接，以及我们这边能提供的具体学习方案。这个电话大概15分钟，方便吗？",
          "notes": "确认身份+说明来意+征求意见，建立平等沟通氛围"
        },
        {
          "section": "需求探询",
          "duration_seconds": 300,
          "probe_points": [
            {"question": "我看了你的简历，这两年的Spring Boot项目经验挺扎实的。当时为什么决定从Java转大数据呢？", "expected_answer": "Java岗位太卷/薪资天花板/对未来趋势的判断", "if_answer": "转到下一问"},
            {"question": "你现在每天大概能抽出多少时间学习？周末有没有整块时间？", "expected_answer": "工作日2-3小时/周末全天", "if_dayjob": "确认是否在职"},
            {"question": "你目标的大数据岗位是偏开发（Spark/Flink工程师），还是偏平台（Hadoop运维/数据仓库）？", "expected_answer": "不太清楚区别", "if_unsure": "需要解释两个方向的差异，帮助用户明确"},
            {"question": "你预期从学习到拿到offer，大概多长时间可以接受？", "expected_answer": "3-6个月", "if_shorter": "需管理预期，3个月是比较紧张的时间线"},
            {"question": "之前有没有了解过其他培训机构？比较关注哪些方面？", "expected_answer": "价格/就业保障/课程内容", "if_competitor": "不贬低竞品，突出差异化"}
          ]
        },
        {
          "section": "价值呈现",
          "duration_seconds": 240,
          "selling_points": [
            {"point": "Java转大数据天然优势", "detail": "Hadoop/Spark都是Java/Scala生态，你的2年Java经验不是从零开始，而是直接站在起跑线上。我们大数据课程中50%的新学员都是Java转过来的，平均学习周期比零基础学员缩短30%。", "evidence": "往期学员李四（Java 1.5年→大数据，入职字节，18K）"},
            {"point": "项目驱动+就业导向", "detail": "我们不是纯理论教学。课程包含3个完整企业级项目：电商数据分析平台、实时日志处理系统、数据仓库建模实战。这3个项目直接放在简历上，面试官问项目经验时你有东西可以讲。", "evidence": "项目代码开源在GitHub，往期学员面试反馈汇总"},
            {"point": "就业服务闭环", "detail": "学完不是结束。我们有专门的就业顾问帮你做简历优化、模拟面试、岗位推荐。从开始学习到拿到offer，全程有人跟。", "evidence": "就业率数据：近3个月大数据方向学员68%在结课后4周内拿到offer"}
          ]
        },
        {
          "section": "异议处理",
          "duration_seconds": 180,
          "objections": [
            {
              "objection": "费用有点高，能不能便宜点？",
              "psychology": "价值认可不够，或预算确实有限",
              "responses": [
                "我理解，15000+的投入确实需要慎重考虑。但如果放在职业发展角度看，从Java 12K转大数据18K-22K，一个月多赚的钱就能覆盖学费（基于真实学员数据：平均薪资涨幅35-50%）。",
                "我们现在有分期方案，可以先付30%，剩余分3期。如果你能2个月内结清，可以免息。"
              ],
              "avoid": "不要直接降价，不要承诺不可兑现的就业薪资"
            },
            {
              "objection": "我不确定自己能不能学会",
              "psychology": "对大数据有认知门槛恐惧",
              "responses": [
                "这个担心我完全理解。但其实大数据开发用的就是Java和SQL，你两个都会。第一批项目就是Java写MapReduce和Spark，你会发现跟你平时写Spring Boot很像。而且我们有专门的答疑群，你卡住了随时问。",
                "要不要先试听一下？我们有免费试听课，周六有Hadoop入门的直播，2小时，你来听一下感受下氛围和难度。"
              ],
              "avoid": "不要承诺'几天就能学会'，保持诚实"
            },
            {
              "objection": "我朋友说大数据不好找工作",
              "psychology": "来自外部负面信息的影响",
              "responses": [
                "确实，单纯'大数据'这个词被炒得太热之后，有些公司只是挂个名字招运维。但细分看，大数据开发工程师（写Spark/Flink）的需求量反而在涨——因为所有公司都在做数据驱动。我建议你关注'大数据开发工程师'而不是'大数据工程师'，这是两个不同的市场。",
                "我们可以约一次免费职业规划，我会针对你的背景具体分析哪些岗位匹配度高，哪些需要补强。去不去我们不急，先把路径搞清楚。"
              ],
              "avoid": "不要全盘否定对方朋友的信息，尊重信息来源"
            }
          ]
        },
        {
          "section": "关单引导",
          "duration_seconds": 90,
          "script": "张三，我把今天聊的几个点总结一下：1）你的Java背景转大数据有天然优势，Hadoop/Spark都是Java生态；2）我们推荐大数据开发方向，学习路径是Hadoop→Spark→Flink，大概8-12周；3）有个电商数据分析平台项目课程很适合你。我建议下一步这样做——这周六下午2点有个免费的Hadoop直播试听课，你听完之后我们下周一约一次职业规划，把具体的岗位和简历优化方案做出来。你看周六的时间可以吗？",
          "close_type": "试听邀约（软关单）"
        },
        {
          "section": "跟进锚点",
          "duration_seconds": 30,
          "script": "好的，周六下午2点我微信上提前发直播间链接给你。听完之后你直接微信告诉我感受，如果有问题我们随时沟通。下周一同一时间我再跟你确认职业规划的时间。",
          "anchor": "周六试听课 + 下周一职业规划"
        }
      ]
    },
    "objection_handling_manual": [
      {
        "objection": "费用类",
        "sub_types": ["价格高", "能不能分期", "有没有优惠"],
        "psychology_core": "价值认可不足 / 预算有限",
        "responses": [
          "ROI计算法：总投入 ÷ 月薪涨幅 = 回本周期（通常2-3个月）",
          "分期方案：先付30%+余款分3期，免息"
        ],
        "must_avoid": ["直接降价（损害课程价值感）", "夸大薪资数据（合规风险）"]
      },
      {
        "objection": "效果类",
        "sub_types": ["学不会怎么办", "学了找不到工作", "基础太差"],
        "psychology_core": "自我效能感低 / 信息不对称",
        "responses": [
          "往期学员案例佐证（同背景转行成功案例）",
          "试听课降低决策门槛",
          "分析学习路径，把'遥不可及'拆成'每周可达'的小目标"
        ],
        "must_avoid": ["承诺100%就业（合规风险）", "说'很简单'（后期期望落差）"]
      }
    ],
    "followup_timeline": [
      {
        "time": "当天（完成后立即）",
        "action": "微信发试听课链接+课程资料包",
        "goal": "激发试听兴趣",
        "fallback_if_no_response": "第二天早上追问一条+一个行业热点资讯"
      },
      {
        "time": "第3天（试听课后）",
        "action": "电话回访试听感受+约职业规划沟通",
        "goal": "推进到职业规划阶段",
        "talk_track": "上周六的试听课听了觉得怎么样？XX老师说有个关于MapReduce的实操环节挺有意思的..."
      },
      {
        "time": "第7天（职业规划后）",
        "action": "发送个性化学习方案+试学一周邀请",
        "goal": "进入试学阶段/关单",
        "talk_track": "根据职业规划，我整理了一个8周学习方案。我建议先试学一周（免费），感受一下课程节奏和辅导质量..."
      }
    ],
    "approval_required": true,
    "approval_policy": "before_external_send"
  }
}
```

#### Agent 22 — 百问百答/模拟面试（`fixtures/doubao.json`）

```json
{
  "agent_no": 22,
  "scenario": "success",
  "output": {
    "generated_at": "2026-05-14T10:35:00Z",
    "confidence": 0.82,
    "mode": "面试模拟",
    "questions": [
      {
        "question_number": 1,
        "category": "JVM基础",
        "difficulty": "medium",
        "question": "请解释 JVM 的类加载机制，以及双亲委派模型在大数据场景下可能遇到的问题？",
        "reference_answer_points": [
          "类加载的三个阶段：加载（Loading）、链接（Linking）、初始化（Initialization）",
          "双亲委派模型（Parent Delegation Model）：类加载器层次 + 委派机制",
          "大数据场景 Jar 包冲突：Hadoop 和 Spark 共用不同版本的 Jackson/Guava 导致 ClassNotFoundException",
          "破坏双亲委派的场景：SPI机制（ServiceLoader）、OSGi、Tomcat 类加载"
        ],
        "suggested_answer_time": "3-5分钟",
        "common_mistakes": [
          "只回答JVM基础类加载，未联系大数据实际问题",
          "遗漏双亲委派的破坏场景（SPI/Tomcat）",
          "回答过于学术化，缺少实际案例"
        ],
        "scoring_rubric": {
          "completeness": "0-25分：是否涵盖类加载三阶段+双亲委派+大数据场景应用",
          "depth": "0-25分：是否有深度理解（如破坏双亲委派的场景）",
          "relevance": "0-25分：是否联系大数据场景（Jar冲突、ClassNotFoundException 排查）",
          "clarity": "0-25分：表达是否清晰结构化"
        }
      }
    ],
    "overall_assessment": {
      "total_score": 72,
      "radar_chart": {
        "JVM基础": 75,
        "系统设计": 65,
        "缓存设计": 60,
        "分布式系统": 45,
        "数据管道": 50,
        "问题解决能力": 80,
        "沟通表达": 70,
        "项目经验表述": 68
      },
      "examiner_feedback": {
        "highlights": ["JVM基础扎实", "问题解决逻辑清晰"],
        "weaknesses": [
          {"area": "分布式系统", "current": 45, "target": 70, "gap": "对CAP理论、一致性协议理解较浅"},
          {"area": "缓存设计", "current": 60, "target": 75, "gap": "缺少缓存雪崩/穿透/击穿的实战经验"}
        ],
        "overall_comment": "技术基础扎实，但分布式系统和缓存设计是明显短板。建议重点补强分布式理论并完成端到端数据管道项目后再次模拟面试。"
      }
    }
  }
}
```

### 6.5 实施清单

| 步骤 | 文件 | 操作 | 预计工作量 |
| --- | --- | --- | --- |
| 1 | `fixtures/leads.json` | 升级 Agent 41 CRM 线索数据为 L2 级别 | 30分钟 |
| 2 | `fixtures/agents_coze.json` | 升级 Agent 13/11/12/15 销售组数据为 L2 级别 | 2小时 |
| 3 | `fixtures/doubao.json` | 升级 Agent 22 百问百答数据为 L2 级别 | 1小时 |
| 4 | `fixtures/agents_dify.json` | 升级 Agent 2/6/7/8/9 教学组数据为 L2 级别 | 2小时 |
| 5 | `fixtures/jobs.json` | 升级 Agent 61 CareerOS 岗位推荐数据为 L2 级别 | 1小时 |
| 6 | `fixtures/careermagic.json` | 升级 CareerMagic 事件数据为 L2 级别 | 30分钟 |
| 7 | `scenarios.go` | 新增 `summary_only` 场景模式（返回 L0/L1 低质量数据） | 1小时 |
| 8 | QA 验证 | 用 `scenario=success` 运行求职全链路，验证输出质量 | 2小时 |

---

## 7. Agent Builder 配置最佳实践

### 7.1 xAgent Agent Builder 配置清单

在 xAgent 管理后台创建 Agent 时，以下字段必须正确配置：

| 配置项 | 推荐值 | 说明 |
| --- | --- | --- |
| `name` | `53AIHub 全链路业务助手` | 清晰的业务描述 |
| `instructions` | 本文档第 4.1 节 System Prompt | **核心：必须使用完整版本，不能是简短版** |
| `execution_mode` | `dag_plan_execute`（think 模式） | 复杂任务需要 DAG 规划 |
| `models.general` | DeepSeek-V4（或其他能力强的大模型） | 输出质量对大模型能力要求高 |
| `tool_categories` | `["other"]` 或自定义分类 | 确保可访问所有 Custom API 工具 |
| `status` | `published` | 创建后立即可用 |

### 7.2 53AIHub Agent `prompt` 字段

在 53AIHub Console 创建 Agent 时，`prompt` 字段应填写**简化的引导 Prompt**（不是完整的 System Prompt）：

```markdown
你已接入 xAgent 动态规划引擎。对于复杂任务，系统会自动拆解为多步骤并调用相应的专业工具。
你的职责是理解用户意图，将任务交给调度引擎处理。
```

> **原理**：完整的 L2/L3 输出质量约束已在 xAgent Agent Builder 的 `instructions` 中定义（4.1 节）。53AIHub 侧的 `prompt` 只需做一个简单的意图转发即可。

---

## 8. 验收验证（用于 P3-14 输出可执行性 E2E 验证）

### 8.1 验证场景：求职全链路

**输入**：
```
学员张三（Java 2年经验）上传了简历，想找大数据方向的工作。
请帮他：简历优化 → 岗位匹配 → 模拟面试题生成 → 学习补课建议
```

**验证方法**：将输出内容对照 L2/L3 Checklist，逐项勾选。

### 8.2 L2 可执行级 Checklist

| # | 检查项 | 判定标准 | 权重 |
| --- | --- | --- | --- |
| Q01 | 空泛建议 | 全文不得出现"建议补充相关技能"、"多练习"等无量化短语 | 阻塞 |
| Q02 | 量化指标 | 全文 ≥ 15 个量化数字（百分比/数值/时长/金额） | 阻塞 |
| Q03 | 分级时间 | 至少 3 个时间层级，每个操作有预计耗时 | 阻塞 |
| Q04 | 具体资源 | ≥ 8 个具体资源引用（书名+章节/URL/练习编号） | 阻塞 |
| Q05 | 结构化 | ≥ 6 个二级标题，使用表格/列表 | 阻塞 |
| Q06 | 风险提示 | ≥ 3 项风险，每项有概率+影响+Plan B | 阻塞 |
| Q07 | 学习方案字数 | 学习补课方案 ≥ 1500 字 | 高 |
| Q08 | 简历字数 | 优化后简历 ≥ 800 字 | 高 |
| Q09 | 逐题面试 | 每道面试题 ≥ 200 字（含题意+参考要点+建议时间） | 高 |
| Q10 | 岗位明细 | 每个岗位有 4 维评分明细（非单一总分） | 高 |

### 8.3 L3 闭环方案级 Checklist

| # | 检查项 | 判定标准 | 权重 |
| --- | --- | --- | --- |
| Q11 | 前置条件 | 方案开头列出执行前需要准备的事项 | 阻塞 |
| Q12 | 交付物清单 | 明确列出最终产出物及格式 | 阻塞 |
| Q13 | 验收标准 | 每项产出有可测量成功标准 | 阻塞 |
| Q14 | 回退路径 | 至少 2 项 Plan B / 降级方案 | 阻塞 |
| Q15 | 优先级排序 | "今日必做/本周/面试前"三级标注 | 阻塞 |
| Q16 | 来源标注 | 每个章节标注生成 Agent、时间、置信度 | 高 |
| Q17 | 资源可访问 | 所有 file_id 可点击，URL 可访问 | 高 |

### 8.4 判定规则

- **全部通过** → 验收通过，可发布
- **Q01-Q06 中任一项不通过** → 发布阻塞，需优化 System Prompt
- **Q07-Q10 中任一项不通过** → 高优先级 bug，需检查 Scenario Prompt 注入
- **Q11-Q15 中任一项不通过** → 综合方案降级为 L2，需检查 Quality Gate 是否触发
- **3 次 Quality Gate 均触发重生成但仍不通过** → 需人工介入分析是 Prompt 问题还是模型能力问题

---

## 9. 实施路线图

### 阶段一：Prompt 升级（立即执行，0 依赖）

| 步骤 | 操作 | 负责方 |
| --- | --- | --- |
| 1 | 将 4.1 节 System Prompt 更新到 xAgent Agent Builder | xAgent 管理后台 |
| 2 | 将 4.2 节求职场景 Prompt 注入到 Agent Builder `instructions` | xAgent 管理后台 |
| 3 | 将 4.3-4.5 节其他场景 Prompt 注入 | xAgent 管理后台 |
| 4 | 更新 Mock Gateway 输出数据为完整 Schema | 53AIHub 后端 |
| 5 | 执行 8.1 节验证场景，检查输出质量 | QA |

### 阶段二：Quality Gate 实现（需开发）

| 步骤 | 操作 | 负责方 |
| --- | --- | --- |
| 1 | 在 `result_analyzer.py` 中实现 Quality Gate Prompt | xAgent 后端 |
| 2 | 在 `dag_plan_execute.py` 中增加质量检查步骤 | xAgent 后端 |
| 3 | 在 `schemas.py` 中增加 `QualityGateResult` | xAgent 后端 |
| 4 | 实现重生成流程（最多 3 次） | xAgent 后端 |

### 阶段三：自动化验证（CI 集成）

| 步骤 | 操作 | 负责方 |
| --- | --- | --- |
| 1 | 将 8.2-8.3 节 Checklist 转为自动化测试脚本 | QA |
| 2 | 集成到 CI pipeline，每次部署自动执行 | DevOps |
| 3 | 建立输出质量基线和回归检测 | QA |

---

## 10. 附录：Anti-Pattern 词库

系统 Quality Gate 检测到的任何以下短语，直接判定未通过：

```
# 空泛建议类
"建议补充相关"   → 未指定具体技能
"建议多练习"     → 未量化
"建议多投递"     → 未量化
"可以参考网上"   → 未指定具体资源
"建议"（无后续具体操作） → 不完整

# 无时间类
"后续补充"       → 无时间节点
"慢慢来"         → 无时间节点
"以后再说"       → 无时间节点
"根据情况"       → 过于模糊

# 无来源类
"网上有很多"     → 未引用来源
"搜索一下"       → 未具体指引
"找一些"         → 未指定资源
"其他类似"       → 无具体名字

# 无目标类
"注意提升"       → 未指定当前值和目标值
"尽量做好"       → 无可测量标准
"加强"           → 未指定具体手段
"改善"           → 未指定从什么改善到什么
```
