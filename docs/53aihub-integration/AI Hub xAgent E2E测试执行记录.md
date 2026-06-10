# AI Hub xAgent 端到端测试执行记录

版本：v1.0
日期：2026-05-14
目标：验证"学员张三（Java 2年经验 → 大数据方向）"场景输出达到 L2（可执行级）以上

---

## 1. 测试环境要求

| 组件 | 要求 |
| --- | --- |
| Go 环境 | Go 1.21+ |
| 数据库 | MySQL 8.0+ (或 SQLite for test) |
| 环境变量 | 参考 `docker/.env` 模板 |
| xAgent 服务 | 运行 xAgent 后端服务（对外暴露 `/api/chat/task/create`） |

## 2. 测试前提检查

### 2.1 单元测试

```bash
cd api
go test ./service/hub_adaptor/xagent/... -v -run Test
```

**预期通过的测试用例：**

| 测试用例 | 验证目标 |
| --- | --- |
| `TestCheckQualityGate_L2PassOutput` | L2 标准输出通过质量门禁 |
| `TestCheckQualityGate_L0FailOutput` | L0 摘要式输出被质量门禁拦截 |
| `TestDetectAntiPatterns` | 空泛话术词库检测准确率 |
| `TestDetectScenario_CareerCoaching` | 求职全链路场景自动识别 |
| `TestDetectScenario_Sales` | 销售场景自动识别 |
| `TestDetectScenario_General` | 通用场景回退 |
| `TestBuildQualityDescription` | System Prompt 注入完整性 |
| `TestBuildQualityDescription_NoSystemPrompt` | 无自定义 Prompt 时质量约束仍生效 |
| `TestBuildQualityGateWarning` | 质量警告 Markdown 格式化 |
| `TestMergeQualityGateToOutput_Pass` | 通过时不追加警告 |

### 2.2 配置验证

```bash
# 确认质量门禁环境变量
export QUALITY_GATE_ENABLED=true
export QUALITY_GATE_MIN_QUANTIFIED_NUMBERS=15
export QUALITY_GATE_MIN_RESOURCE_REFS=8
export QUALITY_GATE_MIN_H2_HEADINGS=6
export QUALITY_GATE_MIN_RISK_ITEMS=3
export QUALITY_GATE_MIN_TIME_LEVELS=3
export QUALITY_GATE_DEGRADE_ON_FAIL=true
```

## 3. E2E 测试场景

### 3.1 场景 1：求职全链路（主要验证目标）

**输入请求：**
```json
{
  "model": "xagent-chat",
  "messages": [
    {
      "role": "user",
      "content": "学员张三（Java 2年经验）上传了简历（file_id:175），想找大数据方向的工作。请帮我做：1）简历优化，2）岗位匹配，3）模拟面试（3道题），4）学习补课方案。要求每个环节都给出可执行的详细方案，不要简单的建议。"
    }
  ],
  "stream": false
}
```

**验证检查清单（每项必须通过）：**

| # | 检查项 | L2 标准阈值 | 验证方法 |
| --- | --- | --- | --- |
| QG-01 | 空泛建议 | 0 个命中 | 搜索输出中无"建议补充相关"、"多练习"、"参考网上"等 12 个禁止词 |
| QG-02 | 量化指标 | ≥ 15 个数字 | 统计百分比、数量、时长、金额、评分等数字出现次数 |
| QG-03 | 时间层级 | ≥ 3 层 | 验证是否有"当日/本周/本月"或"Week 1-2/3-5/6-8"等时间锚点 |
| QG-04 | 资源引用 | ≥ 8 个 | 验证是否有具体书名+章节、URL、LeetCode 题号等可检索资源 |
| QG-05 | 结构化输出 | ≥ 6 个 H2 | 验证 Markdown 二级标题数量 |
| QG-06 | 风险提示 | ≥ 3 项 | 验证是否有风险描述+概率+影响+Plan B 的完整矩阵 |
| QG-07 | 简历章节 | ≥ 800 字 | 验证简历优化章节字数 |
| QG-08 | 面试章节 | ≥ 3 道题 | 验证面试题数量，每题是否有答题时间+参考答案 |
| QG-09 | 学习章节 | ≥ 1500 字 | 验证学习方案字数，是否分阶段、有实战项目 |
| QG-10 | 综合行动计划 | 有优先级矩阵 | 验证是否有"今日必做/本周完成/面试前完成"的分类 |

### 3.2 场景 2：低质量输出验证（负面测试）

**目的：** 验证当 xAgent 返回低质量输出时，Quality Gate 能正确检测并降级标注。

**预期行为：**
1. 质量门禁检测到输出不符合 L2 标准
2. 追加质量门禁警告 Markdown 到输出末尾
3. 在 AgentWorkflowRun 中保存 QualityGateJSON
4. 日志中记录质量检查结果

## 4. 验证通过标准

| 级别 | 标准 | 要求 |
| --- | --- | --- |
| **必须通过** | 场景 1 所有 QG-01 至 QG-10 | 全部通过 |
| **必须通过** | 质量门禁 Pass=true | 输出达到 L2 标准 |
| **必须通过** | 质量评分 ≥ 70/100 | 计算评分达标 |
| **期望通过** | 质检耗时 < 500ms | 不影响用户体验 |
| **期望通过** | AgentWorkflowRun.quality_gate_json 非空 | 审计记录完整 |

## 5. 执行记录

### 5.1 单元测试

| 日期 | 执行人 | 结果 | 备注 |
| --- | --- | --- | --- |
| | | | |

### 5.2 E2E 场景 1

| 日期 | 执行人 | 通过项 | 失败项 | 备注 |
| --- | --- | --- | --- | --- |
| | | | | |

### 5.3 E2E 场景 2

| 日期 | 执行人 | 通过项 | 失败项 | 备注 |
| --- | --- | --- | --- | --- |

---

## 6. 快速验证命令

```bash
# 1. 运行全部单元测试
cd api && go test ./service/hub_adaptor/xagent/... -v

# 2. 运行质量门禁单独测试
go test ./service/hub_adaptor/xagent/... -v -run TestCheckQualityGate

# 3. 运行场景检测测试
go test ./service/hub_adaptor/xagent/... -v -run TestDetectScenario

# 4. 运行 Prompt 构建测试
go test ./service/hub_adaptor/xagent/... -v -run TestBuildQualityDescription

# 5. 构建项目
cd api && go build ./...

# 6. 启动服务后执行 E2E curl 测试
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -d '{
    "model": "xagent-chat",
    "messages": [
      {
        "role": "user",
        "content": "学员张三（Java 2年经验）上传了简历（file_id:175），想找大数据方向的工作。请帮我做：1）简历优化，2）岗位匹配，3）模拟面试（3道题），4）学习补课方案。要求每个环节都给出可执行的详细方案，不要简单的建议。"
      }
    ],
    "stream": false
  }' | jq '.choices[0].message.content' > /tmp/xagent_e2e_output.md

# 7. 人工检查输出
cat /tmp/xagent_e2e_output.md
```

## 7. 问题追踪

当 Quality Gate 不通过时，按以下步骤排查：

1. **检查 Prompt 注入**：确认 `BuildQualityDescription` 中的 L2/L3 约束和自检清单是否被正确注入
2. **检查场景检测**：确认 `DetectScenario` 是否正确识别了业务场景
3. **检查 xAgent Agent Builder**：确认 xAgent 端的 Agent Builder 是否使用了注入后的 System Prompt
4. **检查模型**：确认使用的 LLM 模型是否具有足够的生成能力
5. **检查输出切分**：确认输出没有被截断（`max_tokens` 设置是否足够）
