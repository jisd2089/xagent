"""Deterministic case generators for Loop 1/2/3 smoke and regression data."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


JOB_FAMILIES = [
    "industrial_ai_support",
    "backend_architect",
    "software_developer",
    "industrial_ai_product",
    "quality_engineer",
]

EXPERIENCE_BANDS = ["0-3", "4-10", "10+"]
SUPER_STAGES = ["Exploration", "Establishment", "Maintenance"]
CLAIM_RISKS = [
    "metric_inflation",
    "role_exaggeration",
    "distancing",
    "omission",
    "low_risk_control",
]
INTERVIEWER_ROLES = ["HR", "PeerInterviewer", "HiringManager", "Executive"]
BIAS_TYPES = ["reactance", "halo", "affinity", "ageism", "none"]
COMPLIANCE_RISKS = ["none", "family", "religion", "health", "age", "origin"]
URGENCIES = ["High", "Med", "Low"]
FOCUSES = ["Hard", "Soft", "Balanced"]

FEEDBACK_SOURCES = ["HR", "Recruiter", "HiringManager", "PeerInterviewer", "Executive"]
FEEDBACK_TYPES = [
    "competency_weight",
    "risk_preference",
    "team_context",
    "compliance_rule",
    "scoring_calibration",
]
CONFLICT_TYPES = [
    "urgent_vs_high_standard",
    "hard_vs_soft",
    "education_vs_potential",
    "culture_fit_vs_debias",
    "none",
]

OUTCOME_TYPES = [
    "hit",
    "false_positive",
    "false_negative",
    "human_override_success",
    "human_override_failure",
]
MISS_TYPES = [
    "collaboration_risk",
    "hard_skill_water",
    "learning_agility_underestimated",
    "compliance_issue",
    "motivation_misread",
]
SAMPLE_SIZE_BANDS = ["individual", "small_5_10", "batch_20_plus", "cross_job"]
WINDOWS = ["second_round", "offer", "day_30", "day_60", "day_90", "probation"]


def _pick(values: list[str], index: int) -> str:
    return values[index % len(values)]


def generate_loop1_case(index: int) -> dict[str, Any]:
    job_family = _pick(JOB_FAMILIES, index)
    experience_band = _pick(EXPERIENCE_BANDS, index)
    super_stage = _pick(SUPER_STAGES, index)
    claim_risk = _pick(CLAIM_RISKS, index)
    interviewer_role = _pick(INTERVIEWER_ROLES, index)
    bias_type = _pick(BIAS_TYPES, index)
    compliance_risk = _pick(COMPLIANCE_RISKS, index)
    urgency = _pick(URGENCIES, index)
    focus = _pick(FOCUSES, index)

    risk_claim = {
        "metric_inflation": "候选人称将核心系统性能提升 60%，但未说明基线、统计口径和验收周期。",
        "role_exaggeration": "候选人称主导整体架构优化，但回答中多次使用项目组完成、大家一起推进。",
        "distancing": "候选人描述事故复盘时从我切换到我们，无法说清个人负责动作。",
        "omission": "候选人只讲上线成功，回避早期方案被否决和故障复盘。",
        "low_risk_control": "候选人能清楚说明个人负责模块、指标口径、约束和复盘。",
    }[claim_risk]

    feedback = {
        "reactance": "同级面试官评价：候选人太强势，不好管，可能压过组里老人。",
        "halo": "HR 评价：候选人来自知名公司，应该不会有太大问题。",
        "affinity": "高管评价：候选人背景和我很像，气质很适合团队。",
        "ageism": "年轻面试官评价：候选人毕业太久，可能跟不上年轻团队节奏。",
        "none": "面试官评价：候选人回答需要进一步验证，暂未发现明显主观标签。",
    }[bias_type]

    compliance_question = {
        "family": "你结婚了吗？如果经常加班孩子谁带？",
        "religion": "你周末做礼拜吗？我们项目有时周末上线。",
        "health": "你身体有没有问题？能不能扛住高强度？",
        "age": "你年龄不小了，能跟 00 后团队合作吗？",
        "origin": "你是外地人，会不会不稳定？",
        "none": "",
    }[compliance_risk]

    case_id = f"loop1_{job_family}_{index + 1:03d}"
    input_data = {
        "job_description": {
            "job_id": f"{job_family}_job_{index + 1:03d}",
            "title": job_family.replace("_", " ").title(),
            "responsibilities": [
                "分析岗位关键任务并形成可验证交付",
                "跨团队协作解决复杂问题",
                "用事实和指标验证结果",
            ],
            "required_competencies": [
                "hard_skill_match",
                "constructive_collaboration",
                "ownership",
                "learning_agility",
                "resilience_review",
            ],
        },
        "candidate_profile": {
            "candidate_id": f"synthetic_candidate_{index + 1:03d}",
            "experience_band": experience_band,
            "super_stage": super_stage,
            "education_summary": "synthetic anonymized profile",
            "work_experiences": [
                "负责复杂系统排查、质量验证和跨团队问题闭环",
            ],
            "skills": ["problem_analysis", "documentation", "cross_team_coordination"],
        },
        "candidate_claims": [
            {
                "claim_id": "claim_001",
                "claim_text": risk_claim,
                "risk_type": claim_risk,
            }
        ],
        "interview_transcript": [
            {
                "speaker": "interviewer",
                "text": "请介绍你最能体现岗位能力的项目。",
            },
            {
                "speaker": "candidate",
                "text": risk_claim,
            },
        ],
        "interviewer_feedback": [
            {
                "role": interviewer_role,
                "text": feedback,
                "bias_type": bias_type,
            }
        ],
    }
    if compliance_question:
        input_data["interview_transcript"].append(
            {"speaker": "interviewer", "text": compliance_question}
        )

    expected = {
        "claim_risks": [claim_risk],
        "required_probes": [
            "5_minute_slice",
            "counterfactual_probe",
            "failure_review_probe",
        ],
        "bias_audit": [] if bias_type == "none" else [bias_type],
        "compliance_rewrites": [] if compliance_risk == "none" else [compliance_risk],
        "bars_dimensions": [
            "constructive_collaboration",
            "ownership",
            "learning_agility",
            "hard_skill_match",
            "resilience_review",
        ],
        "decision_allowed_values": ["录取", "降级录取", "备选池挂起", "拒绝"],
    }

    return _case(
        case_id=case_id,
        loop_type="loop1",
        source_type="synthetic_case",
        tags={
            "job_family": job_family,
            "experience_band": experience_band,
            "super_stage": super_stage,
            "claim_risk": claim_risk,
            "interviewer_role": interviewer_role,
            "bias_type": bias_type,
            "compliance_risk": compliance_risk,
            "hiring_urgency": urgency,
            "competency_focus": focus,
            "difficulty": _pick(["easy", "medium", "hard"], index),
        },
        input_data=input_data,
        expected_output=expected,
    )


def generate_loop2_case(index: int) -> dict[str, Any]:
    job_family = _pick(JOB_FAMILIES, index)
    feedback_source = _pick(FEEDBACK_SOURCES, index)
    feedback_type = _pick(FEEDBACK_TYPES, index)
    conflict_type = _pick(CONFLICT_TYPES, index)
    urgency = _pick(URGENCIES, index)

    before = {
        "hard_skill_match": 0.30,
        "constructive_collaboration": 0.20,
        "ownership": 0.20,
        "learning_agility": 0.15,
        "resilience_review": 0.15,
    }
    after = deepcopy(before)
    if feedback_type == "competency_weight":
        after = {
            "hard_skill_match": 0.20,
            "constructive_collaboration": 0.25,
            "ownership": 0.25,
            "learning_agility": 0.15,
            "resilience_review": 0.15,
        }
    elif feedback_type == "risk_preference":
        after["resilience_review"] = 0.25
        after["hard_skill_match"] = 0.20
    elif feedback_type == "team_context":
        after["constructive_collaboration"] = 0.30
        after["hard_skill_match"] = 0.20
    elif feedback_type == "compliance_rule":
        after = before
    elif feedback_type == "scoring_calibration":
        after["learning_agility"] = 0.25
        after["hard_skill_match"] = 0.20

    # Normalize to avoid float drift after targeted edits.
    total = sum(after.values())
    after = {key: round(value / total, 4) for key, value in after.items()}

    case_id = f"loop2_{job_family}_{index + 1:03d}"
    return _case(
        case_id=case_id,
        loop_type="loop2",
        source_type="synthetic_case",
        tags={
            "job_family": job_family,
            "feedback_source": feedback_source,
            "feedback_type": feedback_type,
            "conflict_type": conflict_type,
            "hiring_urgency": urgency,
            "difficulty": _pick(["easy", "medium", "hard"], index),
        },
        input_data={
            "selection_loop_profile": {
                "job_id": f"{job_family}_job_{index + 1:03d}",
                "job_title": job_family.replace("_", " ").title(),
                "hiring_urgency": urgency,
                "target_precision": _pick(["Specific", "Broad"], index),
                "competency_focus": _pick(FOCUSES, index),
            },
            "stakeholder_feedback": [
                {
                    "source": feedback_source,
                    "feedback_type": feedback_type,
                    "content": _loop2_feedback_text(feedback_type, conflict_type),
                }
            ],
            "competency_weights_before": before,
        },
        expected_output={
            "expected_weight_update": after,
            "expected_probe_update": {
                "add": [
                    "incident_reconstruction",
                    "feedback_absorption_probe",
                    "cross_team_conflict_probe",
                ],
                "downrank": ["background_prestige"],
                "remove": ["sensitive_attribute_questions"],
            },
            "conflict_resolution": {
                "conflict_type": conflict_type,
                "rule": "list_conflict_and_request_owner_priority"
                if conflict_type != "none"
                else "no_conflict",
            },
            "human_review_required": []
            if conflict_type == "none"
            else ["decision_owner_priority"],
        },
    )


def generate_loop3_case(index: int) -> dict[str, Any]:
    job_family = _pick(JOB_FAMILIES, index)
    outcome_type = _pick(OUTCOME_TYPES, index)
    miss_type = _pick(MISS_TYPES, index)
    sample_size_band = _pick(SAMPLE_SIZE_BANDS, index)
    window = _pick(WINDOWS, index)
    sample_size = {
        "individual": 1,
        "small_5_10": 8,
        "batch_20_plus": 24,
        "cross_job": 60,
    }[sample_size_band]

    case_id = f"loop3_{job_family}_{index + 1:03d}"
    return _case(
        case_id=case_id,
        loop_type="loop3",
        source_type="synthetic_case",
        tags={
            "job_family": job_family,
            "outcome_type": outcome_type,
            "miss_type": miss_type,
            "sample_size_band": sample_size_band,
            "outcome_window": window,
            "difficulty": _pick(["easy", "medium", "hard"], index),
        },
        input_data={
            "batch_summary": {
                "job_id": f"{job_family}_job_{index + 1:03d}",
                "candidate_count": sample_size,
                "agent_recommended_hire": max(1, sample_size // 3),
                "actual_success_count": _success_count(outcome_type, sample_size),
                "outcome_window": window,
            },
            "candidate_outcomes": [
                {
                    "candidate_id": f"synthetic_candidate_{index + 1:03d}_001",
                    "agent_recommendation": _agent_recommendation(outcome_type),
                    "human_decision": _human_decision(outcome_type),
                    "actual_outcome": _actual_outcome(outcome_type),
                    "evidence": _miss_evidence(miss_type),
                }
            ],
        },
        expected_output={
            "prediction_hits": _prediction_hits(outcome_type),
            "prediction_misses": [miss_type]
            if outcome_type in {"false_positive", "false_negative", "human_override_success"}
            else [],
            "calibration_expected": {
                "weight_changes": _loop3_weight_changes(miss_type),
                "probe_changes": _loop3_probe_changes(miss_type),
                "rules_not_to_change": ["do_not_remove_hard_skill_probes"],
                "human_review_required": ["sample_size_review"]
                if sample_size < 10
                else [],
            },
            "sample_size_warning": "sample_too_small_for_global_rule"
            if sample_size < 10
            else "",
        },
    )


def generate_cases(loop_type: str, count: int) -> list[dict[str, Any]]:
    if loop_type == "loop1":
        return [generate_loop1_case(i) for i in range(count)]
    if loop_type == "loop2":
        return [generate_loop2_case(i) for i in range(count)]
    if loop_type == "loop3":
        return [generate_loop3_case(i) for i in range(count)]
    raise ValueError(f"Unsupported loop type: {loop_type}")


def _case(
    *,
    case_id: str,
    loop_type: str,
    source_type: str,
    tags: dict[str, str],
    input_data: dict[str, Any],
    expected_output: dict[str, Any],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "loop_type": loop_type,
        "source_type": source_type,
        "synthetic": source_type == "synthetic_case",
        "privacy_level": "public",
        "tags": tags,
        "input": input_data,
        "expected_output": expected_output,
        "quality": {"passed": False, "issues": []},
        "created_at": "2026-07-02T00:00:00Z",
        "version": "v1",
    }


def _loop2_feedback_text(feedback_type: str, conflict_type: str) -> str:
    base = {
        "competency_weight": "用人经理要求降低单一技术栈权重，提高复盘和带教能力权重。",
        "risk_preference": "招聘负责人表示不可接受线上事故复盘逃避责任。",
        "team_context": "团队初级成员较多，需要候选人能带教并处理跨团队冲突。",
        "compliance_rule": "HR 要求去除婚育、年龄、健康、地域相关问题。",
        "scoring_calibration": "历史复盘显示我们低估了转型候选人的学习敏捷度。",
    }[feedback_type]
    if conflict_type != "none":
        return f"{base} 当前冲突类型：{conflict_type}。"
    return base


def _success_count(outcome_type: str, sample_size: int) -> int:
    if outcome_type in {"hit", "human_override_success"}:
        return max(1, int(sample_size * 0.75))
    if outcome_type in {"false_positive", "human_override_failure"}:
        return max(0, int(sample_size * 0.35))
    return max(1, int(sample_size * 0.60))


def _agent_recommendation(outcome_type: str) -> str:
    if outcome_type in {"hit", "false_positive"}:
        return "录取"
    return "拒绝"


def _human_decision(outcome_type: str) -> str:
    if outcome_type in {"human_override_success", "human_override_failure"}:
        return "人工推翻"
    return "采纳"


def _actual_outcome(outcome_type: str) -> str:
    return {
        "hit": "high_performer",
        "false_positive": "probation_failed",
        "false_negative": "high_performer_after_manual_hire",
        "human_override_success": "high_performer",
        "human_override_failure": "probation_failed",
    }[outcome_type]


def _miss_evidence(miss_type: str) -> str:
    return {
        "collaboration_risk": "入职后跨团队冲突明显，不愿接受反馈。",
        "hard_skill_water": "项目细节无法落地，关键指标口径不成立。",
        "learning_agility_underestimated": "首轮表达生涩，但工作样本完成质量很高。",
        "compliance_issue": "面试记录中存在敏感问题，影响评分可靠性。",
        "motivation_misread": "候选人接受 offer 后快速流失，动机判断不足。",
    }[miss_type]


def _prediction_hits(outcome_type: str) -> list[str]:
    if outcome_type in {"hit", "human_override_failure"}:
        return ["hard_skill_match", "ownership"]
    return []


def _loop3_weight_changes(miss_type: str) -> dict[str, float]:
    if miss_type == "collaboration_risk":
        return {"constructive_collaboration": 0.10, "hard_skill_match": -0.05}
    if miss_type == "hard_skill_water":
        return {"hard_skill_match": 0.10, "resume_prestige": -0.10}
    if miss_type == "learning_agility_underestimated":
        return {"learning_agility": 0.10, "terminology_fluency": -0.05}
    if miss_type == "compliance_issue":
        return {"compliance_audit": 0.10}
    return {"motivation_probe": 0.10}


def _loop3_probe_changes(miss_type: str) -> list[str]:
    return {
        "collaboration_risk": ["cross_team_conflict_probe", "feedback_absorption_probe"],
        "hard_skill_water": ["5_minute_slice", "metric_baseline_probe"],
        "learning_agility_underestimated": ["48_hour_work_sample", "learning_path_probe"],
        "compliance_issue": ["compliance_rewrite_check"],
        "motivation_misread": ["offer_motivation_probe", "constraint_probe"],
    }[miss_type]
