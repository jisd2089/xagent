# Loop 设计文档目录

本目录用于沉淀 `docs/interview_psychologist_agent.md` 对应的 Loop Engineering 设计。

| 文档 | 说明 |
| --- | --- |
| `interview_psychologist_agent_three_loops_design.md` | 面试心理学家智能体的三个循环设计主文档 |
| `interview_psychologist_agent_three_loops_requirements.md` | 基于三循环设计的详细需求分析 |
| `three_loops_implementation_design.md` | 三循环自动化运行与数据工厂详细实现设计 |
| `three_loops_implementation_progress.md` | 覆盖实现全生命周期的进度表、验证结果和下一步优先级 |
| `deep_research_data_inventory.md` | Deep Research 数据包索引、来源和使用方式 |
| `three_loops_auto_data_generation_spec.md` | 三循环自动数据生成、覆盖矩阵和质量门禁方案 |
| `local_seed_case_anonymized.md` | 基于 `D:\zhizuobiao\agent` 三份 PDF 的匿名化本地种子案例 |
| `recruitment_compliance_guardrails.md` | 招聘合规红线、敏感问题改写和选择程序治理规则 |
| `structured_interview_bei_bars_library.md` | 结构化面试、BEI 追问和 BARS 行为锚定题库 |
| `software_industrial_ai_competency_library.md` | 软件开发、系统架构、工业 AI 技术支撑岗位胜任力库 |
| `loop_calibration_seed_dataset.md` | Loop 2/Loop 3 岗位反馈、结果回流和校准样本数据 |
| `agent31_deep_research_test_prompts.md` | Agent 31 三循环验收测试 Prompt 集 |

生成数据与回归报告：

- `generated/dataset_manifest.json`：当前 smoke 数据集 manifest。
- `generated/coverage_reports/`：数据覆盖报告。
- `generated/eval_reports/`：Agent 31 回归或 dry-run 回归报告。
- `generated_mvp/`：MVP 规模数据集，当前 60 条样本与 dry-run eval 报告。

参考文章：

- 微信文章：`吴恩达谈火起来的「Loop Engineering」：AI 编程真正的变化，不是写代码更快`
- 链接：<https://mp.weixin.qq.com/s/5RMVZ6TXn-vz6fFNCfEbLw>
