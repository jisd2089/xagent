# Coze 职业规划智能体接入 xAgent 手动操作手册

本手册提供逐步操作指引，完成 Coze 职业规划 workflow 在 xAgent 中的接入、配置与验证。

---

## 准备工作

在开始前，确认以下信息已就绪：

| 项目 | 说明 |
|------|------|
| Coze PAT（Personal Access Token） | 从 Coze 控制台获取，需具备对应 workflow/app 的调用权限 |
| Coze Workflow ID | `7648982443038703656` |
| Coze App ID | `7648929438155210767` |
| xAgent 服务地址 | 假设为 `http://<xagent-host>:<port>`，下文用 `{BASE_URL}` 代替 |

---

## 第一步：在 xAgent 中注册 Custom API Tool

### 1.1 打开 xAgent Custom API 管理页面

在浏览器中访问：

```
{BASE_URL}/tools/custom-api
```

或者在 xAgent 左侧导航栏中找到 **Tools → Custom API**。

### 1.2 点击「新建」按钮

进入 Custom API 创建表单。

### 1.3 填写表单

按以下内容逐项填写：

| 字段 | 值 |
|------|-----|
| **Name** | `Coze_Career_Planning`（必须使用英文，避免工具名清洗后不可读） |
| **Description** | `调用 Coze 职业规划 workflow，根据城市、规划方向、简历文件、目标岗位、薪资期望生成职业规划结果。` |
| **URL** | `https://api.coze.cn/v1/workflow/stream_run` |
| **Method** | `POST` |

### 1.4 添加请求头（Headers）

点击「添加 Header」，逐条添加：

| Header Name | Header Value |
|-------------|-------------|
| `Authorization` | `Bearer $COZE_TOKEN` |
| `Content-Type` | `application/json` |

> **说明**：`$COZE_TOKEN` 是变量引用，xAgent 会在调用时自动替换为环境变量中保存的 Token。

### 1.5 配置环境变量（Env）

点击「添加环境变量」：

| 变量名 | 变量值 |
|--------|--------|
| `COZE_TOKEN` | `<你的 Coze PAT>` |

> **注意**：Env 中的值会被加密存储，不会明文暴露。

### 1.6 填写请求体（Body）

将以下 JSON 粘贴到 Body 字段（**注意：这是一整行 JSON 字符串，不要换行**）：

```json
{"workflow_id":"7648982443038703656","app_id":"7648929438155210767","parameters":{"chengshi_in":"上海","guihua_fangxiang":"AI大模型","input":"https://p9-bot-workflow-sign.byteimg.com/tos-cn-i-mdko3gqilj/35a502eb00fa411da13bbcc8ab472df2.pdf~tplv-mdko3gqilj-image.image?rk3s=81d4c505&x-expires=1812022967&x-signature=bjYJK1hLorUemG2xziNsezuJK9k%3D&x-wf-file_name=21%E5%B1%8A++%E5%BC%A0%E6%81%BA%E6%98%8E+%E4%B8%AA%E4%BA%BA%E7%AE%80%E5%8E%86.pdf","mubiao_gangwei":"AI产品经理","xinzi_in":"10k"}}
```

> **说明**：
> - 当前 Body 使用的是固定测试参数。
> - 如果后续需要让用户动态传参，可在 Agent 指令中要求 LLM 通过 tool call 覆盖 `body.parameters` 中的对应字段。
> - `input` 字段是简历文件的 URL，可按需替换为实际简历地址。

### 1.7 启用工具

将 **is_active** 开关打开（设为 `true`）。

### 1.8 保存

点击页面底部的「保存」或「创建」按钮。

### 1.9 确认注册结果

保存成功后，在 Custom API 列表中应能看到 `Coze_Career_Planning`，状态为 **active**。

该工具在 xAgent 工具系统中的实际调用名为：

```
api_Coze_Career_Planning_call
```

---

## 第二步：创建 xAgent Agent Builder 智能体

### 2.1 打开 Agent Builder 页面

在浏览器中访问：

```
{BASE_URL}/agents
```

或者在左侧导航栏中找到 **Agents**。

### 2.2 点击「创建智能体」

进入智能体创建表单。

### 2.3 填写基本信息

| 字段 | 值 |
|------|-----|
| **Name** | `Coze 职业规划顾问` |
| **Description** | `通过 Coze 职业规划 workflow 生成职业规划建议。` |

### 2.4 填写指令（Instructions）

将以下内容粘贴到 Instructions 输入框：

```
你是职业规划顾问。用户请求职业规划、岗位规划、AI大模型方向规划时，必须调用工具 api_Coze_Career_Planning_call。调用该工具时必须传入 timeout=180、retry_count=0，避免 Coze stream_run 长流程被默认 30 秒超时中断。不要自己编造 Coze workflow 的执行结果。工具返回后，提取 workflow 输出，整理成中文结构化报告，包括职业定位、技能差距、学习路径、岗位建议、薪资预期和下一步行动。
```

### 2.5 配置执行模式

选择 **Execution Mode** 为 `balanced`。

### 2.6 配置工具选择（关键步骤）

在 **Tool Categories** 字段中填写：

```
mcp:Coze_Career_Planning
```

> **注意**：
> - 这是精确工具选择，xAgent 会根据此值匹配到前面注册的 `api_Coze_Career_Planning_call` 工具。
> - **不要**使用 `other` 类别，否则会放开所有 OTHER 类工具，不安全且不必要。

### 2.7 添加建议提示词（可选）

在 **Suggested Prompts** 中添加以下预设提示词：

- `帮我基于这份简历生成 AI 产品经理方向的职业规划`
- `我想在上海找 AI 大模型方向岗位，帮我规划路线`

### 2.8 保存智能体

点击「保存」或「创建」按钮。

### 2.9 记录 Agent ID

创建成功后，系统会生成一个 `agent_id`，记录下这个 ID，后续调用时需要使用。

---

## 第三步：调用智能体执行任务

### 3.1 构造任务创建请求

使用以下 API 创建任务：

**请求方式**：`POST`

**请求地址**：`{BASE_URL}/api/chat/task/create`

**请求体**：

```json
{
  "title": "Coze 职业规划测试",
  "description": "请调用 Coze 职业规划工具，为上海、AI大模型方向、AI产品经理岗位、10k薪资目标生成职业规划。",
  "agent_id": "<第二步记录的 agent_id>",
  "execution_mode": "balanced",
  "sync": true
}
```

> **注意**：将 `agent_id` 替换为第二步创建智能体后记录的实际 ID。

### 3.2 发送请求

可以通过以下方式发送：

**方式 A：使用 curl（命令行）**

```bash
curl -X POST "{BASE_URL}/api/chat/task/create" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Coze 职业规划测试",
    "description": "请调用 Coze 职业规划工具，为上海、AI大模型方向、AI产品经理岗位、10k薪资目标生成职业规划。",
    "agent_id": "<YOUR_AGENT_ID>",
    "execution_mode": "balanced",
    "sync": true
  }'
```

**方式 B：使用 Postman 或同类工具**

1. 新建 POST 请求，URL 填入 `{BASE_URL}/api/chat/task/create`
2. Headers 添加 `Content-Type: application/json`
3. Body 选择 raw → JSON，粘贴上述请求体
4. 点击 Send

### 3.3 查看执行流程

任务执行的完整链路如下：

```
xAgent Agent
  → tool_categories 精确命中 mcp:Coze_Career_Planning
  → 加载 Custom API Tool: api_Coze_Career_Planning_call
  → 携带 timeout=180、retry_count=0 调用 Coze /v1/workflow/stream_run
  → 解析工具返回
  → 整理为最终中文职业规划报告
```

---

## 第四步：验证结果

### 4.1 必检项

逐项检查以下内容，确保接入成功：

| # | 检查项 | 如何验证 |
|---|--------|---------|
| 1 | Custom API 已注册且激活 | 在 Custom API 列表中确认 `Coze_Career_Planning` 存在，状态为 active |
| 2 | Agent 工具配置正确 | 打开 Agent 详情，确认 `tool_categories` 包含 `mcp:Coze_Career_Planning` |
| 3 | 工具被正确调用 | 查看任务执行日志，确认日志中出现 `api_Coze_Career_Planning_call` |
| 4 | 超时参数正确 | 确认工具调用参数中包含 `timeout: 180`、`retry_count: 0` |
| 5 | Coze 鉴权通过 | Coze 返回码不是 401/403；如果返回 `authentication is invalid`，检查 PAT 是否过期、是否属于正确空间、是否有 workflow/app 权限 |
| 6 | 输出为真实结果 | 最终返回内容是中文职业规划报告（含职业定位、技能差距、学习路径等），而不是模型自编的答案 |

### 4.2 常见问题排查

| 问题 | 可能原因 | 解决办法 |
|------|---------|---------|
| 工具返回 `Request failed after 4 attempts` | 默认 30 秒超时对 Coze 长流程不够 | 确认 Agent instructions 中写了 `timeout=180`，且任务日志中参数确实传了 180 |
| 返回 `authentication is invalid` | PAT 过期或权限不足 | 到 Coze 控制台重新生成 PAT，确认 PAT 所属空间有该 workflow/app 的访问权限 |
| Agent 没有调用工具，直接编造答案 | Agent instructions 中要求不够明确 | 检查 instructions 中是否包含"必须调用工具"、"不要自己编造结果"等约束 |
| 找不到工具 `api_Coze_Career_Planning_call` | tool_categories 配置不匹配 | 确认 tool_categories 填写的是 `mcp:Coze_Career_Planning`（注意拼写和大小写） |

---

## 快速操作清单（Cheatsheet）

```
□ Step 1: 注册 Custom API Tool
  □ 填写 Name: Coze_Career_Planning
  □ 填写 URL: https://api.coze.cn/v1/workflow/stream_run
  □ 添加 Header: Authorization = Bearer $COZE_TOKEN
  □ 添加 Env: COZE_TOKEN = <你的PAT>
  □ 粘贴 Body JSON
  □ 开启 is_active
  □ 保存

□ Step 2: 创建 Agent
  □ 填写 Name: Coze 职业规划顾问
  □ 粘贴 Instructions（含 timeout=180, retry_count=0）
  □ 设置 Tool Categories: mcp:Coze_Career_Planning
  □ 保存, 记录 agent_id

□ Step 3: 测试调用
  □ POST /api/chat/task/create
  □ body 中传入 agent_id
  □ 查看任务执行结果

□ Step 4: 验证
  □ Custom API 列表中有 Coze_Career_Planning (active)
  □ Agent tool_categories 含 mcp:Coze_Career_Planning
  □ 执行日志中有 api_Coze_Career_Planning_call
  □ 参数含 timeout=180
  □ Coze 返回非 401/403
  □ 最终输出为真实职业规划报告
```
