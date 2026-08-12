"""Regression prompt rendering for generated loop cases."""

from __future__ import annotations

import json
from typing import Any


def render_prompt(case: dict[str, Any]) -> str:
    loop_type = case["loop_type"]
    title = {
        "loop1": "Loop 1 候选人证据审计",
        "loop2": "Loop 2 招聘判断反馈",
        "loop3": "Loop 3 选拔结果校准",
    }[loop_type]
    payload = json.dumps(case["input"], ensure_ascii=False, indent=2)
    expected = json.dumps(case["expected_output"], ensure_ascii=False, indent=2)
    return f"""# {title}

Case ID: `{case["case_id"]}`

请执行 `{loop_type}`，并按面试心理学家智能体三循环协议输出结构化结果。

## 输入

```json
{payload}
```

## 期望检查点

下面不是要求你逐字复述，而是用于回归评估的检查点。你的输出需要覆盖这些风险、追问、评分或校准动作。

```json
{expected}
```
"""

