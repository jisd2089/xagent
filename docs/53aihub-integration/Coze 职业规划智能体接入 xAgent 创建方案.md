# Coze 职业规划智能体接入 xAgent 创建方案

本文记录如何把 Coze 的“职业规划” workflow 通过 xAgent Custom API Tool 接入，并在 xAgent Agent Builder 中创建一个可调用该接口的智能体。

## 1. Coze API 合同

Coze workflow 接口：

```http
POST https://api.coze.cn/v1/workflow/stream_run
Authorization: Bearer <COZE_PAT>
Content-Type: application/json
```

请求体：

```json
{
  "workflow_id": "7648982443038703656",
  "app_id": "7648929438155210767",
  "parameters": {
    "chengshi_in": "上海",
    "guihua_fangxiang": "AI大模型",
    "input": "https://p9-bot-workflow-sign.byteimg.com/tos-cn-i-mdko3gqilj/35a502eb00fa411da13bbcc8ab472df2.pdf~tplv-mdko3gqilj-image.image?rk3s=81d4c505&x-expires=1812022967&x-signature=bjYJK1hLorUemG2xziNsezuJK9k%3D&x-wf-file_name=21%E5%B1%8A++%E5%BC%A0%E6%81%BA%E6%98%8E+%E4%B8%AA%E4%BA%BA%E7%AE%80%E5%8E%86.pdf",
    "mubiao_gangwei": "AI产品经理",
    "xinzi_in": "10k"
  }
}
```

## 2. 注册 xAgent Custom API Tool

在 xAgent 侧创建 Custom API 记录。建议工具名使用英文，避免工具名清洗后不可读。

```json
{
  "name": "Coze_Career_Planning",
  "description": "调用 Coze 职业规划 workflow，根据城市、规划方向、简历文件、目标岗位、薪资期望生成职业规划结果。",
  "url": "https://api.coze.cn/v1/workflow/stream_run",
  "method": "POST",
  "headers": {
    "Authorization": "Bearer $COZE_TOKEN",
    "Content-Type": "application/json"
  },
  "env": {
    "COZE_TOKEN": "<COZE_PAT>"
  },
  "body": "{\"workflow_id\":\"7648982443038703656\",\"app_id\":\"7648929438155210767\",\"parameters\":{\"chengshi_in\":\"上海\",\"guihua_fangxiang\":\"AI大模型\",\"input\":\"https://p9-bot-workflow-sign.byteimg.com/tos-cn-i-mdko3gqilj/35a502eb00fa411da13bbcc8ab472df2.pdf~tplv-mdko3gqilj-image.image?rk3s=81d4c505&x-expires=1812022967&x-signature=bjYJK1hLorUemG2xziNsezuJK9k%3D&x-wf-file_name=21%E5%B1%8A++%E5%BC%A0%E6%81%BA%E6%98%8E+%E4%B8%AA%E4%BA%BA%E7%AE%80%E5%8E%86.pdf\",\"mubiao_gangwei\":\"AI产品经理\",\"xinzi_in\":\"10k\"}}",
  "is_active": true
}
```

注册后，该 Custom API 在 xAgent 工具系统中的实际工具名为：

```text
api_Coze_Career_Planning_call
```

说明：

- `COZE_TOKEN` 通过 `env` 加密保存，`headers.Authorization` 使用 `$COZE_TOKEN` 注入。
- `body` 是 JSON 字符串模板，xAgent `CustomApiTool` 会在调用时解析为 JSON body。
- 当前配置使用固定测试参数；如果后续需要让用户动态传参，可在任务运行时通过 tool call 的 `body.parameters` 覆盖默认字段。
- Coze `/v1/workflow/stream_run` 是长流程/流式接口，Agent 指令应要求工具调用携带 `timeout: 180`、`retry_count: 0`；否则默认 30 秒超时会导致工具返回 `Request failed after 4 attempts`。

## 3. 创建 xAgent Agent Builder 智能体

通过 xAgent `/api/agents` 创建智能体：

```json
{
  "name": "Coze 职业规划顾问",
  "description": "通过 Coze 职业规划 workflow 生成职业规划建议。",
  "instructions": "你是职业规划顾问。用户请求职业规划、岗位规划、AI大模型方向规划时，必须调用工具 api_Coze_Career_Planning_call。调用该工具时必须传入 timeout=180、retry_count=0，避免 Coze stream_run 长流程被默认 30 秒超时中断。不要自己编造 Coze workflow 的执行结果。工具返回后，提取 workflow 输出，整理成中文结构化报告，包括职业定位、技能差距、学习路径、岗位建议、薪资预期和下一步行动。",
  "execution_mode": "balanced",
  "knowledge_bases": [],
  "skills": [],
  "tool_categories": ["mcp:Coze_Career_Planning"],
  "suggested_prompts": [
    "帮我基于这份简历生成 AI 产品经理方向的职业规划",
    "我想在上海找 AI 大模型方向岗位，帮我规划路线"
  ]
}
```

关键配置：

```json
"tool_categories": ["mcp:Coze_Career_Planning"]
```

该精确工具选择会匹配到：

```text
api_Coze_Career_Planning_call
```

如果使用 `"tool_categories": ["other"]`，也能加载 Custom API 工具，但会放开所有 `OTHER` 类工具；本接入建议使用 `mcp:Coze_Career_Planning`，只暴露这个 Coze 工具。

## 4. 调用智能体执行任务

创建任务时带上该 Agent Builder 智能体的 `agent_id`：

```json
{
  "title": "Coze 职业规划测试",
  "description": "请调用 Coze 职业规划工具，为上海、AI大模型方向、AI产品经理岗位、10k薪资目标生成职业规划。",
  "agent_id": "<XAGENT_AGENT_ID>",
  "execution_mode": "balanced",
  "sync": true
}
```

接口：

```http
POST /api/chat/task/create
```

执行链路：

```text
xAgent Agent
  -> tool_categories 精确命中 mcp:Coze_Career_Planning
  -> 加载 Custom API Tool: api_Coze_Career_Planning_call
  -> 携带 timeout=180、retry_count=0 调用 Coze /v1/workflow/stream_run
  -> 解析工具返回
  -> 整理为最终中文职业规划报告
```

## 5. 验证点

创建完成后，至少验证以下内容：

1. Custom API 列表中存在 `Coze_Career_Planning`，且状态为 active。
2. Agent 的 `tool_categories` 包含 `mcp:Coze_Career_Planning`。
3. 任务执行日志中能看到工具名 `api_Coze_Career_Planning_call`。
4. 工具调用参数中包含 `timeout: 180`、`retry_count: 0`。
5. Coze 返回非 401/403；如果返回 `authentication is invalid`，优先检查 PAT 是否过期、是否属于正确空间、是否有 workflow/app 权限。
6. 最终输出不是模型自编答案，而是基于工具返回结果整理出的职业规划报告。

## 6. 已完成代码层验证

相关回归测试位于：

```text
tests/core/tools/adapters/vibe/test_api_tool_adapter.py
```

测试覆盖内容：

- 默认 URL、method、headers 会被正确使用。
- `$COZE_TOKEN` 会被替换为解密后的 env 值。
- Coze `workflow_id`、`app_id`、`parameters` 会作为 JSON body 传给底层 `call_api`。
- 长流程调用的 `timeout`、`retry_count` 会透传到底层 `call_api`。

WSL 中已执行目标测试：

```bash
cd /mnt/d/github/xagent
PYTHONPATH=src /tmp/xagent-coze-test-venv/bin/python -m pytest --confcutdir=tests/core/tools/adapters/vibe tests/core/tools/adapters/vibe/test_api_tool_adapter.py
```

结果：

```text
11 passed in 1.95s
```
