"""Rule-based judge for Agent 31 loop regression outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


DECISION_VALUES = {"录取", "降级录取", "备选池挂起", "拒绝"}
HIGH_RISK_CLAIMS = {"metric_inflation", "role_exaggeration", "distancing", "omission"}
CLAIM_RISK_ALIASES = {
    "metric_inflation": [
        "metric_inflation",
        "指标注水",
        "性能提升",
        "基线",
        "统计口径",
        "验收周期",
        "60%",
    ],
    "role_exaggeration": ["role_exaggeration", "角色夸大", "个人贡献", "团队成果"],
    "distancing": ["distancing", "人称漂移", "我们", "项目组"],
    "omission": ["omission", "遗漏", "回避", "缺失"],
}
SENSITIVE_TERMS = {
    "年龄",
    "婚育",
    "宗教",
    "民族",
    "籍贯",
    "健康",
    "残疾",
    "怀孕",
    "家庭",
}
PROBE_ALIASES = {
    "5_minute_slice": ["5_minute_slice", "5-Minute Slice", "5 Minute Slice", "5分钟", "5 分钟"],
    "counterfactual_probe": ["counterfactual_probe", "反事实"],
    "failure_review_probe": ["failure_review_probe", "失败复盘", "阻力复盘", "复盘追问"],
}
BARS_DIMENSION_ALIASES = {
    "constructive_collaboration": [
        "constructive_collaboration",
        "constructive collaboration",
        "建设性协作",
        "协作",
    ],
    "ownership": ["ownership", "主人翁", "主人翁意识", "owner"],
    "learning_agility": ["learning_agility", "learning agility", "学习敏捷", "学习敏捷度"],
    "hard_skill_match": ["hard_skill_match", "hard skill", "硬实力", "岗位硬实力", "技术能力"],
    "resilience_review": ["resilience_review", "resilience", "抗逆境", "复盘", "抗压复盘"],
}
BIAS_ALIASES = {
    "halo": ["halo", "光环", "光环效应", "知名公司", "品牌光环", "大厂"],
    "reactance": ["reactance", "抵触", "抗拒", "防御", "同辈防卫"],
    "similarity": ["similarity", "相似性", "同类偏好"],
    "confirmation": ["confirmation", "确认偏误", "证实偏见"],
    "family": ["family", "婚育", "家庭", "孩子"],
}


@dataclass(frozen=True)
class JudgeIssue:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def judge_agent_output(case: dict[str, Any], raw_output: Any) -> dict[str, Any]:
    """Judge one Agent output against loop-specific structural rules."""

    issues: list[JudgeIssue] = []
    parsed = _coerce_output(raw_output, issues)
    loop_type = str(case.get("loop_type") or "")

    if not parsed:
        issues.append(JudgeIssue("empty_output", "Agent output is empty or unparseable"))
    elif loop_type == "loop1":
        if _is_markdown_output(parsed):
            _judge_loop1_markdown(str(parsed["_text"]), case, issues)
        else:
            _judge_loop1(parsed, case, issues)
    elif loop_type == "loop2":
        if _is_markdown_output(parsed):
            _judge_loop2_markdown(str(parsed["_text"]), case, issues)
        else:
            _judge_loop2(parsed, case, issues)
    elif loop_type == "loop3":
        if _is_markdown_output(parsed):
            _judge_loop3_markdown(str(parsed["_text"]), case, issues)
        else:
            _judge_loop3(parsed, case, issues)
    else:
        issues.append(JudgeIssue("loop_type", f"Unsupported loop type {loop_type!r}"))

    score = _score(issues)
    return {
        "passed": not issues,
        "score": score,
        "issues": [issue.to_dict() for issue in issues],
        "parsed_output": parsed,
    }


def build_expected_agent_output(case: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic passing output from expected data for dry runs."""

    loop_type = case["loop_type"]
    expected = case["expected_output"]
    if loop_type == "loop1":
        return {
            "claim_audit": expected.get("claim_risks", []),
            "bei_probe_plan": expected.get("required_probes", []),
            "bias_audit": expected.get("bias_audit", []),
            "compliance_rewrites": expected.get("compliance_rewrites", []),
            "bars_scorecard": expected.get("bars_dimensions", []),
            "decision": "备选池挂起",
            "quality_gate": {
                "passed": True,
                "issues": [],
                "self_check": "All high-risk claims have evidence probes.",
            },
        }
    if loop_type == "loop2":
        return {
            "updated_profile": {
                "competency_weights": expected.get("expected_weight_update", {})
            },
            "weight_changes": expected.get("expected_weight_update", {}),
            "probe_changes": expected.get("expected_probe_update", {}),
            "conflicts": [expected.get("conflict_resolution", {})],
            "human_review_required": expected.get("human_review_required", []),
            "quality_gate": {"passed": True, "issues": []},
        }
    if loop_type == "loop3":
        calibration = expected.get("calibration_expected", {})
        return {
            "prediction_hits": expected.get("prediction_hits", []),
            "prediction_misses": expected.get("prediction_misses", []),
            "calibration_actions": calibration.get("probe_changes", []),
            "next_batch_strategy": {
                "weight_changes": calibration.get("weight_changes", {}),
                "rules_not_to_change": calibration.get("rules_not_to_change", []),
            },
            "sample_size_warning": expected.get("sample_size_warning", ""),
            "quality_gate": {"passed": True, "issues": []},
        }
    return {}


def _coerce_output(raw_output: Any, issues: list[JudgeIssue]) -> dict[str, Any]:
    if isinstance(raw_output, dict):
        return raw_output
    if raw_output is None:
        return {}
    if not isinstance(raw_output, str):
        issues.append(JudgeIssue("output_type", "Agent output must be a dict or string"))
        return {}

    text = raw_output.strip()
    if not text:
        return {}

    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        loaded = None
    if isinstance(loaded, dict):
        return loaded

    if _looks_like_markdown_report(text):
        return {"_format": "markdown", "_text": text}

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        try:
            loaded = json.loads(fenced.group(1))
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            return loaded

    inline = _extract_first_json_object(text)
    if inline:
        try:
            loaded = json.loads(inline)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            return loaded

    issues.append(JudgeIssue("json_parse", "Agent output does not contain JSON object"))
    return {}


def _is_markdown_output(output: dict[str, Any]) -> bool:
    return output.get("_format") == "markdown" and isinstance(output.get("_text"), str)


def _looks_like_markdown_report(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith("---"):
        stripped = stripped[3:].lstrip()
    headings = text.count("\n## ")
    any_headings = len(re.findall(r"(?m)^#{1,6}\s+", text))
    tables = text.count("|")
    normalized = text.lower()
    has_case_marker = "case id" in normalized or "case:" in normalized
    has_loop_marker = "loop 1" in normalized or "loop1" in normalized
    return (
        (stripped.startswith("#") and headings >= 2 and tables >= 6)
        or (has_case_marker and any_headings >= 2 and tables >= 6)
        or (has_loop_marker and any_headings >= 2)
    )


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _judge_loop1(
    output: dict[str, Any], case: dict[str, Any], issues: list[JudgeIssue]
) -> None:
    _require_keys(
        output,
        [
            "claim_audit",
            "bei_probe_plan",
            "bias_audit",
            "bars_scorecard",
            "decision",
            "quality_gate",
        ],
        issues,
    )
    if output.get("decision") not in DECISION_VALUES:
        issues.append(JudgeIssue("decision_enum", "Loop 1 decision is not in allowed enum"))
    if not _non_empty_list(output.get("claim_audit")):
        issues.append(JudgeIssue("claim_audit", "Loop 1 requires non-empty claim audit"))
    if not _non_empty_list(output.get("bei_probe_plan")):
        issues.append(JudgeIssue("probe_plan", "Loop 1 requires non-empty BEI probe plan"))
    if len(output.get("bars_scorecard") or []) < 3:
        issues.append(JudgeIssue("bars_scorecard", "Loop 1 requires at least 3 BARS dimensions"))

    quality_gate = output.get("quality_gate")
    if not isinstance(quality_gate, dict) or quality_gate.get("passed") is not True:
        issues.append(JudgeIssue("quality_gate", "Loop 1 quality_gate.passed must be true"))

    serialized = json.dumps(output, ensure_ascii=False)
    if any(term in serialized for term in SENSITIVE_TERMS) and "bias_audit" not in output:
        issues.append(JudgeIssue("compliance", "Sensitive terms require bias audit"))

    expected = case.get("expected_output", {})
    expected_claims = expected.get("claim_risks", [])
    if expected_claims and len(output.get("claim_audit") or []) < min(1, len(expected_claims)):
        issues.append(JudgeIssue("claim_recall", "Expected claim risks were not surfaced"))

    missing_claims = [
        claim for claim in expected_claims if claim not in serialized
    ]
    if missing_claims:
        issues.append(
            JudgeIssue(
                "claim_risk_match",
                f"Loop 1 did not mention expected claim risks: {missing_claims}",
            )
        )

    if HIGH_RISK_CLAIMS.intersection(expected_claims) and len(output.get("bei_probe_plan") or []) < 2:
        issues.append(
            JudgeIssue(
                "high_risk_probe_count",
                "High-risk claims require at least two BEI probes",
            )
        )

    expected_bias = expected.get("bias_audit", [])
    if expected_bias and not _non_empty_list(output.get("bias_audit")):
        issues.append(JudgeIssue("bias_audit", "Expected interviewer bias was not audited"))

    expected_compliance = expected.get("compliance_rewrites", [])
    if expected_compliance:
        rewrites = output.get("compliance_rewrites")
        if not _non_empty_list(rewrites):
            issues.append(
                JudgeIssue(
                    "compliance_rewrites",
                    "Sensitive interview questions require compliance rewrites",
                )
            )


def _judge_loop1_markdown(text: str, case: dict[str, Any], issues: list[JudgeIssue]) -> None:
    normalized = text.lower()
    expected = case.get("expected_output", {})

    is_coverage_summary = "覆盖检查" in text and "已覆盖" in text
    if str(case.get("case_id")) not in text and not is_coverage_summary:
        issues.append(JudgeIssue("case_id", "Markdown output does not mention case_id"))

    expected_claims = expected.get("claim_risks", [])
    missing_claims = [
        claim
        for claim in expected_claims
        if not _mentions_alias(normalized, claim, CLAIM_RISK_ALIASES)
    ]
    if missing_claims:
        issues.append(
            JudgeIssue(
                "claim_risk_match",
                f"Loop 1 markdown did not mention expected claim risks: {missing_claims}",
            )
        )

    required_probes = expected.get("required_probes", [])
    missing_probes = [
        probe
        for probe in required_probes
        if not any(alias.lower() in normalized for alias in PROBE_ALIASES.get(probe, [probe]))
    ]
    if missing_probes:
        issues.append(
            JudgeIssue(
                "probe_plan",
                f"Loop 1 markdown did not mention expected probes: {missing_probes}",
            )
        )
    if HIGH_RISK_CLAIMS.intersection(expected_claims) and len(required_probes) - len(missing_probes) < 2:
        issues.append(
            JudgeIssue(
                "high_risk_probe_count",
                "High-risk claims require at least two BEI probes",
            )
        )

    expected_bias = expected.get("bias_audit", [])
    missing_bias = [
        bias
        for bias in expected_bias
        if not _mentions_alias(normalized, bias, BIAS_ALIASES)
    ]
    if missing_bias:
        issues.append(
            JudgeIssue(
                "bias_audit",
                f"Loop 1 markdown did not mention expected bias audits: {missing_bias}",
            )
        )

    bars_dimensions = expected.get("bars_dimensions", [])
    if (
        "bars_dimensions" in normalized
        and ("5个维度" in text or "五个维度" in text or "五维度" in text)
    ):
        missing_dimensions = []
    else:
        missing_dimensions = [
            dimension
            for dimension in bars_dimensions
            if not _mentions_alias(normalized, dimension, BARS_DIMENSION_ALIASES)
        ]
    if len(bars_dimensions) - len(missing_dimensions) < 3:
        issues.append(
            JudgeIssue(
                "bars_scorecard",
                f"Loop 1 markdown has fewer than 3 expected BARS dimensions: {missing_dimensions}",
            )
        )

    if not any(value in text for value in DECISION_VALUES):
        issues.append(JudgeIssue("decision_enum", "Loop 1 markdown decision is not in allowed enum"))

    expected_compliance = expected.get("compliance_rewrites", [])
    if expected_compliance and "合规" not in text and "敏感" not in text:
        issues.append(
            JudgeIssue(
                "compliance_rewrites",
                "Sensitive interview questions require compliance rewrite discussion",
            )
        )


def _judge_loop2(
    output: dict[str, Any], case: dict[str, Any], issues: list[JudgeIssue]
) -> None:
    _require_keys(
        output,
        ["updated_profile", "weight_changes", "human_review_required"],
        issues,
    )
    conflicts = output.get("conflicts")
    if not _non_empty_list(conflicts):
        conflicts = _nested_dict(output, "updated_profile").get("conflicts")
    if not _non_empty_list(conflicts):
        issues.append(JudgeIssue("missing_field", "Missing field conflicts"))

    weights = _loop2_weights(output)
    if not isinstance(weights, dict) or not weights:
        issues.append(JudgeIssue("weights", "Loop 2 requires weight changes"))
    elif abs(sum(_numeric_values(weights)) - 1.0) > 0.03:
        issues.append(JudgeIssue("weight_sum", "Loop 2 weights must sum to 1.0"))

    probe_changes = output.get("probe_changes")
    if not isinstance(probe_changes, dict):
        probe_changes = _nested_dict(output, "updated_profile").get("probe_strategy")
    if not isinstance(probe_changes, dict):
        issues.append(JudgeIssue("probe_changes", "Loop 2 probe_changes must be object"))
    elif "remove" not in probe_changes:
        issues.append(JudgeIssue("probe_remove", "Loop 2 should include removed probes"))
    else:
        removed = probe_changes.get("remove")
        if not isinstance(removed, list) or "sensitive_attribute_questions" not in removed:
            issues.append(
                JudgeIssue(
                    "sensitive_probe_remove",
                    "Loop 2 must remove sensitive attribute questions",
                )
            )

    conflict_type = case.get("tags", {}).get("conflict_type")
    if conflict_type and conflict_type != "none" and not _non_empty_list(
        output.get("human_review_required")
    ):
        issues.append(
            JudgeIssue(
                "human_review_required",
                "Non-trivial Loop 2 conflicts require human review",
            )
        )


def _judge_loop2_markdown(text: str, case: dict[str, Any], issues: list[JudgeIssue]) -> None:
    expected = case.get("expected_output", {})
    weights = expected.get("expected_weight_update", {})
    missing_dimensions = [dimension for dimension in weights if dimension not in text]
    if len(weights) - len(missing_dimensions) < max(1, min(3, len(weights))):
        issues.append(
            JudgeIssue(
                "weights",
                f"Loop 2 markdown did not mention enough updated dimensions: {missing_dimensions}",
            )
        )
    for required in ["权重", "追问", "冲突"]:
        if required not in text:
            issues.append(JudgeIssue("markdown_structure", f"Loop 2 markdown missing {required}"))
    if expected.get("human_review_required") and "人工" not in text:
        issues.append(
            JudgeIssue(
                "human_review_required",
                "Loop 2 markdown should mark human review for non-trivial conflicts",
            )
        )
    if "sensitive_attribute_questions" not in text and "敏感" not in text:
        issues.append(
            JudgeIssue(
                "sensitive_probe_remove",
                "Loop 2 markdown should remove sensitive attribute questions",
            )
        )


def _judge_loop3(
    output: dict[str, Any], case: dict[str, Any], issues: list[JudgeIssue]
) -> None:
    _require_keys(output, ["sample_size_warning"], issues)
    prediction_hits = output.get("prediction_hits")
    prediction_misses = output.get("prediction_misses")
    prediction_miss = output.get("prediction_miss")
    has_outcome_compare = (
        _non_empty_list(prediction_hits)
        or _non_empty_list(prediction_misses)
        or isinstance(prediction_miss, dict)
    )
    if "prediction_hits" not in output and "prediction_misses" not in output and not isinstance(prediction_miss, dict):
        issues.append(JudgeIssue("missing_field", "Missing field prediction_hits/prediction_misses"))
    calibration_actions = output.get("calibration_actions")
    if not _non_empty_list(calibration_actions) and not (
        isinstance(output.get("weight_changes_applied"), dict)
        or isinstance(output.get("probe_changes_applied"), dict)
        or isinstance(output.get("competency_weights_after"), dict)
        or _non_empty_list(output.get("new_probes"))
    ):
        issues.append(JudgeIssue("missing_field", "Missing field calibration_actions"))
    batch = case.get("input", {}).get("batch_summary", {})
    candidate_count = int(batch.get("candidate_count", 0) or 0)
    if candidate_count < 10 and not output.get("sample_size_warning"):
        issues.append(
            JudgeIssue("sample_warning", "Loop 3 small samples require warning")
        )
    if not has_outcome_compare:
        issues.append(JudgeIssue("outcome_compare", "Loop 3 requires hit or miss analysis"))

    strategy = output.get("next_batch_strategy")
    if not isinstance(strategy, dict) and (
        isinstance(output.get("weight_changes_applied"), dict)
        or isinstance(output.get("probe_changes_applied"), dict)
        or isinstance(output.get("competency_weights_after"), dict)
        or _non_empty_list(output.get("new_probes"))
        or output.get("rules_compliance")
        or output.get("hard_skill_probes_preserved")
        or output.get("rules_preserved")
        or output.get("global_rules_frozen") is True
    ):
        strategy = {
            "weight_changes": output.get("weight_changes_applied")
            or output.get("competency_weights_after", {}),
            "probe_changes": output.get("probe_changes_applied")
            or {"added": output.get("new_probes", [])},
            "rules_not_to_change": output.get("rules_preserved")
            or list(_nested_dict(output, "rules_compliance").keys())
            or output.get("hard_skill_probes_preserved", []),
            "global_rules_frozen": output.get("global_rules_frozen"),
        }
    if not isinstance(strategy, dict):
        issues.append(JudgeIssue("next_batch_strategy", "Loop 3 strategy must be object"))
    elif "rules_not_to_change" not in strategy:
        issues.append(
            JudgeIssue(
                "rules_not_to_change",
                "Loop 3 must list rules that should not be changed",
            )
        )


def _judge_loop3_markdown(text: str, case: dict[str, Any], issues: list[JudgeIssue]) -> None:
    expected = case.get("expected_output", {})
    hit_or_miss_terms = ["命中", "漏检", "误判", "miss", "hit"]
    if not any(term in text for term in hit_or_miss_terms):
        issues.append(JudgeIssue("outcome_compare", "Loop 3 markdown requires hit or miss analysis"))
    if "校准" not in text:
        issues.append(JudgeIssue("calibration_actions", "Loop 3 markdown requires calibration actions"))
    if "不改" not in text and "不得" not in text and "rules_not_to_change" not in text:
        issues.append(
            JudgeIssue(
                "rules_not_to_change",
                "Loop 3 markdown must list rules that should not be changed",
            )
        )
    if expected.get("sample_size_warning") and "样本" not in text:
        issues.append(JudgeIssue("sample_warning", "Loop 3 markdown should mention sample-size warning"))


def _require_keys(
    output: dict[str, Any], keys: list[str], issues: list[JudgeIssue]
) -> None:
    for key in keys:
        if key not in output:
            issues.append(JudgeIssue("missing_field", f"Missing field {key}"))


def _non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _nested_dict(output: dict[str, Any], key: str) -> dict[str, Any]:
    value = output.get(key)
    return value if isinstance(value, dict) else {}


def _loop2_weights(output: dict[str, Any]) -> dict[str, Any]:
    profile_weights = _nested_dict(output, "updated_profile").get("competency_weights")
    if isinstance(profile_weights, dict) and profile_weights:
        return profile_weights

    weight_changes = output.get("weight_changes")
    if not isinstance(weight_changes, dict):
        return {}
    after_values = {
        key: value["after"]
        for key, value in weight_changes.items()
        if isinstance(value, dict) and isinstance(value.get("after"), int | float)
    }
    if after_values:
        return after_values
    return weight_changes


def _mentions_alias(
    normalized_text: str,
    key: str,
    aliases: dict[str, list[str]],
) -> bool:
    return any(alias.lower() in normalized_text for alias in aliases.get(key, [key]))


def _numeric_values(values: dict[str, Any]) -> list[float]:
    numbers: list[float] = []
    for value in values.values():
        if isinstance(value, int | float):
            numbers.append(float(value))
    return numbers


def _score(issues: list[JudgeIssue]) -> float:
    if not issues:
        return 1.0
    return max(0.0, round(1.0 - min(len(issues), 10) * 0.1, 4))
