"""Optional LLM judge for Agent 31 loop regression outputs.

The module is stdlib-only so the regression runner can still execute in thin
WSL/container environments. It targets OpenAI-compatible chat-completions APIs
but keeps provider details configurable through explicit arguments or
environment variables.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


ENV_ENABLED = "XAGENT_LOOP_LLM_JUDGE_ENABLED"
ENV_API_BASE = "XAGENT_LOOP_LLM_JUDGE_API_BASE"
ENV_API_KEY = "XAGENT_LOOP_LLM_JUDGE_API_KEY"
ENV_MODEL = "XAGENT_LOOP_LLM_JUDGE_MODEL"
ENV_TIMEOUT_SECONDS = "XAGENT_LOOP_LLM_JUDGE_TIMEOUT_SECONDS"
ENV_MAX_OUTPUT_TOKENS = "XAGENT_LOOP_LLM_JUDGE_MAX_OUTPUT_TOKENS"
ENV_INPUT_COST_PER_1K = "XAGENT_LOOP_LLM_JUDGE_INPUT_COST_PER_1K"
ENV_OUTPUT_COST_PER_1K = "XAGENT_LOOP_LLM_JUDGE_OUTPUT_COST_PER_1K"


@dataclass(frozen=True)
class LLMJudgeConfig:
    enabled: bool = False
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout_seconds: float = 60.0
    max_output_tokens: int = 700
    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None

    @classmethod
    def from_env(cls, *, enabled: bool | None = None) -> "LLMJudgeConfig":
        return cls(
            enabled=_coerce_bool(os.getenv(ENV_ENABLED))
            if enabled is None
            else bool(enabled),
            api_base=os.getenv(ENV_API_BASE) or os.getenv("OPENAI_BASE_URL"),
            api_key=os.getenv(ENV_API_KEY) or os.getenv("OPENAI_API_KEY"),
            model=os.getenv(ENV_MODEL) or os.getenv("OPENAI_MODEL"),
            timeout_seconds=_coerce_float(os.getenv(ENV_TIMEOUT_SECONDS), 60.0),
            max_output_tokens=_coerce_int(os.getenv(ENV_MAX_OUTPUT_TOKENS), 700),
            input_cost_per_1k=_coerce_optional_float(os.getenv(ENV_INPUT_COST_PER_1K)),
            output_cost_per_1k=_coerce_optional_float(os.getenv(ENV_OUTPUT_COST_PER_1K)),
        )

    def with_overrides(
        self,
        *,
        enabled: bool | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> "LLMJudgeConfig":
        return LLMJudgeConfig(
            enabled=self.enabled if enabled is None else enabled,
            api_base=api_base or self.api_base,
            api_key=api_key or self.api_key,
            model=model or self.model,
            timeout_seconds=self.timeout_seconds,
            max_output_tokens=self.max_output_tokens,
            input_cost_per_1k=self.input_cost_per_1k,
            output_cost_per_1k=self.output_cost_per_1k,
        )


def disabled_llm_judge_result(reason: str = "disabled") -> dict[str, Any]:
    return {
        "enabled": False,
        "status": reason,
        "passed": None,
        "score": None,
        "issues": [],
        "usage": {},
        "estimated_cost_usd": None,
    }


def judge_agent_output_with_llm(
    case: dict[str, Any],
    raw_output: Any,
    rule_judge: dict[str, Any],
    *,
    config: LLMJudgeConfig | None = None,
) -> dict[str, Any]:
    """Run semantic LLM judging for one regression result.

    Returns a stable result object. Provider/API failures are captured as
    ``status=error`` so regression reports can be archived and inspected rather
    than losing the whole run.
    """

    resolved = config or LLMJudgeConfig.from_env()
    if not resolved.enabled:
        return disabled_llm_judge_result()
    missing = [
        name
        for name, value in {
            "api_base": resolved.api_base,
            "api_key": resolved.api_key,
            "model": resolved.model,
        }.items()
        if not value
    ]
    if missing:
        return {
            **disabled_llm_judge_result("misconfigured"),
            "enabled": True,
            "error": f"missing {', '.join(missing)}",
        }

    started = time.monotonic()
    try:
        response = _request_chat_completion(
            config=resolved,
            messages=_build_llm_judge_messages(case, raw_output, rule_judge),
        )
        content = _extract_message_content(response)
        payload = _parse_llm_judge_content(content)
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        return {
            "enabled": True,
            "status": "evaluated",
            "model": resolved.model,
            "passed": bool(payload.get("passed")),
            "score": _coerce_score(payload.get("score")),
            "issues": _coerce_issues(payload.get("issues")),
            "rationale": str(payload.get("rationale") or ""),
            "confidence": _coerce_score(payload.get("confidence")),
            "usage": usage,
            "estimated_cost_usd": estimate_llm_judge_cost(
                usage,
                input_cost_per_1k=resolved.input_cost_per_1k,
                output_cost_per_1k=resolved.output_cost_per_1k,
            ),
            "latency_seconds": round(time.monotonic() - started, 4),
        }
    except Exception as exc:  # noqa: BLE001 - report, do not abort regression.
        return {
            **disabled_llm_judge_result("error"),
            "enabled": True,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "latency_seconds": round(time.monotonic() - started, 4),
        }


def combine_rule_and_llm_judges(
    rule_judge: dict[str, Any],
    llm_judge: dict[str, Any],
) -> dict[str, Any]:
    llm_status = str(llm_judge.get("status") or "")
    llm_passed = llm_judge.get("passed")
    passed = bool(rule_judge.get("passed")) and (
        llm_status != "evaluated" or llm_passed is True
    )
    issues = list(rule_judge.get("issues") or [])
    if llm_status == "evaluated" and llm_passed is False:
        issues.extend(
            {
                "code": str(item.get("code") or "llm_judge"),
                "message": str(item.get("message") or item),
            }
            for item in llm_judge.get("issues") or []
            if isinstance(item, dict)
        )
    return {
        **rule_judge,
        "passed": passed,
        "rule_passed": bool(rule_judge.get("passed")),
        "llm_passed": llm_passed if llm_status == "evaluated" else None,
        "llm_status": llm_status,
        "issues": issues,
    }


def estimate_llm_judge_cost(
    usage: dict[str, Any],
    *,
    input_cost_per_1k: float | None,
    output_cost_per_1k: float | None,
) -> float | None:
    if input_cost_per_1k is None and output_cost_per_1k is None:
        return None
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(
        usage.get("completion_tokens") or usage.get("output_tokens") or 0
    )
    total = 0.0
    if input_cost_per_1k is not None:
        total += prompt_tokens * input_cost_per_1k / 1000
    if output_cost_per_1k is not None:
        total += completion_tokens * output_cost_per_1k / 1000
    return round(total, 8)


def _build_llm_judge_messages(
    case: dict[str, Any],
    raw_output: Any,
    rule_judge: dict[str, Any],
) -> list[dict[str, str]]:
    payload = {
        "case_id": case.get("case_id"),
        "loop_type": case.get("loop_type"),
        "tags": case.get("tags", {}),
        "input": _trim_for_prompt(case.get("input")),
        "expected_output": _trim_for_prompt(case.get("expected_output")),
        "agent_output": _trim_for_prompt(raw_output),
        "rule_judge": _trim_for_prompt(rule_judge),
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a strict semantic judge for interview psychology loop "
                "regression tests. Evaluate whether the agent output actually "
                "addresses the case, matches expected risks or calibration "
                "actions, avoids unsupported sensitive-attribute reasoning, and "
                "is semantically consistent with the rule judge. Return only one "
                "JSON object with keys: passed(boolean), score(number 0..1), "
                "issues(array of {code,message}), rationale(string), "
                "confidence(number 0..1)."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _request_chat_completion(
    *,
    config: LLMJudgeConfig,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    assert config.api_base is not None
    assert config.api_key is not None
    assert config.model is not None
    url = f"{config.api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": config.max_output_tokens,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            data = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM judge request failed: HTTP {exc.code}: {detail}") from exc
    loaded = json.loads(data)
    if not isinstance(loaded, dict):
        raise RuntimeError("LLM judge returned non-object JSON")
    return loaded


def _extract_message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM judge response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("LLM judge choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeError("LLM judge response missing message.content")
    return message["content"]


def _parse_llm_judge_content(content: str) -> dict[str, Any]:
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM judge content must be a JSON object")
    return parsed


def _coerce_issues(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    issues: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            issues.append(
                {
                    "code": str(item.get("code") or "llm_judge"),
                    "message": str(item.get("message") or ""),
                }
            )
        else:
            issues.append({"code": "llm_judge", "message": str(item)})
    return issues


def _coerce_score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, score))


def _trim_for_prompt(value: Any, max_chars: int = 7000) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return value
    return {"_truncated": True, "text": text[:max_chars]}


def _coerce_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _coerce_float(value: str | None, default: float) -> float:
    parsed = _coerce_optional_float(value)
    return default if parsed is None else parsed


def _coerce_optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _coerce_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default
