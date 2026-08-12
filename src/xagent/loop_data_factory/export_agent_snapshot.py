"""Export a web Agent configuration snapshot for loop regression review.

The exporter intentionally uses the product HTTP API instead of reading the
database directly. This keeps the snapshot aligned with what Agent Builder and
runtime users can actually see.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "full_key",
    "key_hash",
)


def export_agent_snapshot(
    *,
    api_base: str,
    agent_id: int,
    username: str,
    password: str,
    output_dir: Path,
    basename: str | None = None,
) -> dict[str, str]:
    """Fetch an agent over HTTP and write JSON + Markdown snapshots."""

    token = login(api_base=api_base, username=username, password=password)
    agent = fetch_agent(api_base=api_base, agent_id=agent_id, token=token)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = build_snapshot_payload(
        agent,
        metadata={
            "generated_at": generated_at,
            "api_base": api_base.rstrip("/"),
            "agent_id": agent_id,
            "source": "GET /api/agents/{agent_id}",
        },
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = basename or f"agent{agent_id}_configuration_snapshot"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_snapshot_markdown(payload), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def login(*, api_base: str, username: str, password: str) -> str:
    response = request_json(
        "POST",
        f"{api_base.rstrip('/')}/api/auth/login",
        None,
        {"username": username, "password": password},
    )
    token = response.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Login succeeded without access_token")
    return token


def fetch_agent(*, api_base: str, agent_id: int, token: str) -> dict[str, Any]:
    return request_json(
        "GET",
        f"{api_base.rstrip('/')}/api/agents/{agent_id}",
        token,
        None,
    )


def build_snapshot_payload(
    agent: dict[str, Any],
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    instructions = str(agent.get("instructions") or "")
    sanitized_agent = redact_sensitive_values(agent)
    checks = build_configuration_checks(sanitized_agent)
    return {
        "metadata": metadata,
        "agent": sanitized_agent,
        "derived": {
            "instructions_char_count": len(instructions),
            "instructions_sha256": hashlib.sha256(
                instructions.encode("utf-8")
            ).hexdigest(),
            "tool_category_count": len(agent.get("tool_categories") or []),
            "knowledge_base_count": len(agent.get("knowledge_bases") or []),
            "skill_count": len(agent.get("skills") or []),
            "suggested_prompt_count": len(agent.get("suggested_prompts") or []),
        },
        "configuration_checks": checks,
    }


def build_configuration_checks(agent: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        {
            "code": "has_instructions",
            "passed": bool(str(agent.get("instructions") or "").strip()),
            "message": "Agent instructions are present.",
        },
        {
            "code": "has_tool_categories",
            "passed": bool(agent.get("tool_categories")),
            "message": "At least one tool category is enabled.",
        },
        {
            "code": "has_knowledge_binding",
            "passed": bool(agent.get("knowledge_bases")),
            "message": "At least one knowledge base is bound.",
        },
        {
            "code": "uses_dag_capable_mode",
            "passed": agent.get("execution_mode") in {"think", "auto"},
            "message": "Execution mode can use DAG planning for complex cases.",
        },
    ]
    return checks


def redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact_sensitive_values(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_values(item) for item in value]
    return value


def render_snapshot_markdown(payload: dict[str, Any]) -> str:
    agent = payload["agent"]
    metadata = payload["metadata"]
    derived = payload["derived"]
    checks = payload["configuration_checks"]

    lines = [
        f"# Agent {metadata['agent_id']} 配置快照",
        "",
        f"- 生成时间：`{metadata['generated_at']}`",
        f"- API Base：`{metadata['api_base']}`",
        f"- 来源：`{metadata['source']}`",
        "",
        "## 基本信息",
        "",
        "| 字段 | 值 |",
        "| --- | --- |",
        f"| ID | `{agent.get('id')}` |",
        f"| 名称 | {markdown_cell(agent.get('name'))} |",
        f"| 状态 | `{agent.get('status')}` |",
        f"| 执行模式 | `{agent.get('execution_mode')}` |",
        f"| 创建时间 | `{agent.get('created_at')}` |",
        f"| 更新时间 | `{agent.get('updated_at')}` |",
        f"| 发布时间 | `{agent.get('published_at')}` |",
        "",
        "## 绑定状态",
        "",
        "| 配置项 | 数量 | 当前值 |",
        "| --- | ---: | --- |",
        list_row("Tool Categories", agent.get("tool_categories")),
        list_row("Knowledge Bases", agent.get("knowledge_bases")),
        list_row("Skills", agent.get("skills")),
        list_row("Suggested Prompts", agent.get("suggested_prompts")),
        "",
        "## 配置检查",
        "",
        "| 检查 | 状态 | 说明 |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        status = "通过" if check["passed"] else "待补齐"
        lines.append(
            f"| `{check['code']}` | {status} | {markdown_cell(check['message'])} |"
        )

    lines.extend(
        [
            "",
            "## Instructions 指纹",
            "",
            f"- 字符数：`{derived['instructions_char_count']}`",
            f"- SHA-256：`{derived['instructions_sha256']}`",
            "",
            "## Instructions 全文",
            "",
            "```text",
            str(agent.get("instructions") or "").rstrip(),
            "```",
            "",
            "## Models JSON",
            "",
            "```json",
            json.dumps(agent.get("models") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def list_row(label: str, values: Any) -> str:
    items = values if isinstance(values, list) else []
    rendered = ", ".join(f"`{item}`" for item in items) if items else "未配置"
    return f"| {label} | {len(items)} | {rendered} |"


def markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def request_json(
    method: str,
    url: str,
    bearer_token: str | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc
    loaded = json.loads(data)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"{method} {url} returned non-object JSON")
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost")
    parser.add_argument("--agent-id", type=int, default=31)
    parser.add_argument("--login-username", required=True)
    parser.add_argument("--login-password", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/loop"))
    parser.add_argument(
        "--basename",
        default=None,
        help="Output filename stem. Defaults to agent{agent_id}_configuration_snapshot.",
    )
    args = parser.parse_args()
    result = export_agent_snapshot(
        api_base=args.api_base,
        agent_id=args.agent_id,
        username=args.login_username,
        password=args.login_password,
        output_dir=args.output_dir,
        basename=args.basename,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
