"""Deterministic adversarial mutations for loop regression cases."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


MUTATION_VERSION = "2026-07-07.adversarial.001"

LOOP_MUTATIONS: dict[str, tuple[str, ...]] = {
    "loop1": (
        "metric_inflation",
        "role_exaggeration",
        "distancing",
        "halo_bias",
        "sensitive_question",
    ),
    "loop2": (
        "urgent_vs_high_standard",
        "hard_vs_soft",
        "culture_fit_vs_debias",
        "compliance_regression",
    ),
    "loop3": (
        "small_sample_warning",
        "false_positive",
        "false_negative",
        "human_override_success",
    ),
}


def mutate_cases(
    cases: list[dict[str, Any]],
    *,
    copies_per_case: int = 1,
) -> list[dict[str, Any]]:
    """Return deterministic adversarial copies for the provided cases."""

    if copies_per_case <= 0:
        return []
    mutated: list[dict[str, Any]] = []
    for case in cases:
        loop_type = str(case.get("loop_type", ""))
        mutations = LOOP_MUTATIONS.get(loop_type, ())
        for copy_index in range(copies_per_case):
            if not mutations:
                continue
            mutation_type = mutations[copy_index % len(mutations)]
            mutated.append(mutate_case(case, mutation_type=mutation_type))
    return mutated


def mutate_case(case: dict[str, Any], *, mutation_type: str) -> dict[str, Any]:
    """Create one adversarial copy while preserving the original case."""

    loop_type = case.get("loop_type")
    if mutation_type not in LOOP_MUTATIONS.get(str(loop_type), ()):
        raise ValueError(f"Unsupported mutation {mutation_type!r} for loop {loop_type!r}")

    mutated = deepcopy(case)
    source_case_id = str(case["case_id"])
    mutated["case_id"] = f"{source_case_id}_adv_{mutation_type}"
    mutated["source_type"] = "synthetic_case"
    mutated["synthetic"] = True
    mutated["version"] = MUTATION_VERSION
    mutated["quality"] = {"passed": False, "issues": []}
    mutated["tags"] = {
        **dict(mutated.get("tags", {})),
        "difficulty": "hard",
        "adversarial_mutation": mutation_type,
    }
    mutated["adversarial"] = {
        "source_case_id": source_case_id,
        "mutation_type": mutation_type,
        "mutation_version": MUTATION_VERSION,
    }

    if loop_type == "loop1":
        _mutate_loop1(mutated, mutation_type)
    elif loop_type == "loop2":
        _mutate_loop2(mutated, mutation_type)
    elif loop_type == "loop3":
        _mutate_loop3(mutated, mutation_type)
    return mutated


def build_mutation_plan_from_coverage(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert simple coverage gaps into deterministic mutation suggestions."""

    plan: list[dict[str, Any]] = []
    gaps = [str(gap) for gap in coverage.get("gaps", [])]
    for loop_type, mutations in LOOP_MUTATIONS.items():
        loop_gaps = [gap for gap in gaps if gap.startswith(f"{loop_type}:")]
        if loop_gaps:
            plan.append(
                {
                    "loop_type": loop_type,
                    "recommended_mutations": list(mutations),
                    "reason": "; ".join(loop_gaps),
                }
            )
    return plan


def _mutate_loop1(case: dict[str, Any], mutation_type: str) -> None:
    claim_text = {
        "metric_inflation": "候选人称将关键链路吞吐提升 80%，但没有说明基线、分母、统计窗口和验收周期。",
        "role_exaggeration": "候选人称主导平台重构，但细节全部描述为团队推进和负责人拍板。",
        "distancing": "候选人复盘线上事故时持续使用我们，没有说明自己的决策、动作和复盘责任。",
        "halo_bias": "候选人称曾在知名公司核心团队任职，但无法给出当前岗位相关行为证据。",
        "sensitive_question": "候选人回答被婚育和加班稳定性问题打断，岗位能力证据不足。",
    }[mutation_type]
    risk_type = {
        "metric_inflation": "metric_inflation",
        "role_exaggeration": "role_exaggeration",
        "distancing": "distancing",
        "halo_bias": "omission",
        "sensitive_question": "omission",
    }[mutation_type]
    case["tags"]["claim_risk"] = risk_type
    case["input"]["candidate_claims"] = [
        {"claim_id": "claim_001", "claim_text": claim_text, "risk_type": risk_type}
    ]
    case["input"]["interview_transcript"] = [
        {"speaker": "interviewer", "text": "请介绍一个最能证明岗位能力的项目。"},
        {"speaker": "candidate", "text": claim_text},
    ]
    case["expected_output"]["claim_risks"] = [risk_type]
    if mutation_type == "halo_bias":
        _set_loop1_bias(case, "halo", "HR 评价：候选人来自知名公司，能力应该不会差。")
    if mutation_type == "sensitive_question":
        case["tags"]["compliance_risk"] = "family"
        case["input"]["interview_transcript"].append(
            {"speaker": "interviewer", "text": "你结婚了吗？如果经常加班孩子谁带？"}
        )
        case["expected_output"]["compliance_rewrites"] = ["family"]


def _set_loop1_bias(case: dict[str, Any], bias_type: str, text: str) -> None:
    case["tags"]["bias_type"] = bias_type
    case["input"]["interviewer_feedback"] = [
        {"role": "HR", "text": text, "bias_type": bias_type}
    ]
    case["expected_output"]["bias_audit"] = [bias_type]


def _mutate_loop2(case: dict[str, Any], mutation_type: str) -> None:
    feedback = {
        "urgent_vs_high_standard": "业务方要求本周必须发 offer，但面试证据显示关键岗位能力仍缺少可验证行为。",
        "hard_vs_soft": "架构负责人要求提高硬技能权重，团队负责人同时要求提高协作和反馈吸收权重。",
        "culture_fit_vs_debias": "用人经理认为候选人气质不像团队，需要改成可观察行为证据再判断。",
        "compliance_regression": "有人建议恢复婚育和年龄问题来判断稳定性，HR 要求立即移除。",
    }[mutation_type]
    case["tags"]["conflict_type"] = (
        "culture_fit_vs_debias"
        if mutation_type == "compliance_regression"
        else mutation_type
    )
    case["tags"]["feedback_type"] = (
        "compliance_rule"
        if mutation_type in {"culture_fit_vs_debias", "compliance_regression"}
        else "competency_weight"
    )
    case["input"]["stakeholder_feedback"] = [
        {"source": "HiringManager", "feedback_type": case["tags"]["feedback_type"], "content": feedback}
    ]
    case["expected_output"]["conflict_resolution"] = {
        "conflict_type": case["tags"]["conflict_type"],
        "rule": "list_conflict_and_request_owner_priority",
    }
    case["expected_output"]["human_review_required"] = ["decision_owner_priority"]
    remove = case["expected_output"].setdefault("expected_probe_update", {}).setdefault(
        "remove", []
    )
    if "sensitive_attribute_questions" not in remove:
        remove.append("sensitive_attribute_questions")


def _mutate_loop3(case: dict[str, Any], mutation_type: str) -> None:
    batch = case["input"]["batch_summary"]
    outcome = case["input"]["candidate_outcomes"][0]
    case["tags"]["outcome_type"] = mutation_type
    if mutation_type == "small_sample_warning":
        case["tags"]["sample_size_band"] = "individual"
        batch["candidate_count"] = 3
        batch["actual_success_count"] = 1
        case["expected_output"]["sample_size_warning"] = "sample_too_small_for_global_rule"
        case["expected_output"]["calibration_expected"]["human_review_required"] = [
            "sample_size_review"
        ]
        return

    miss_type = {
        "false_positive": "collaboration_risk",
        "false_negative": "learning_agility_underestimated",
        "human_override_success": "learning_agility_underestimated",
    }[mutation_type]
    case["tags"]["miss_type"] = miss_type
    outcome["agent_recommendation"] = "录取" if mutation_type == "false_positive" else "拒绝"
    outcome["human_decision"] = (
        "人工推翻" if mutation_type == "human_override_success" else "采纳"
    )
    outcome["actual_outcome"] = (
        "probation_failed"
        if mutation_type == "false_positive"
        else "high_performer_after_manual_hire"
    )
    outcome["evidence"] = {
        "collaboration_risk": "入职后跨团队冲突明显，不愿接受反馈。",
        "learning_agility_underestimated": "首轮表达生涩，但工作样本完成质量很高。",
    }[miss_type]
    case["expected_output"]["prediction_hits"] = []
    case["expected_output"]["prediction_misses"] = [miss_type]
