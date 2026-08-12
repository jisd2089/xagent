from __future__ import annotations

import json
from pathlib import Path

from xagent.loop_data_factory.agent_output_judge import (
    build_expected_agent_output,
    judge_agent_output,
)
from xagent.loop_data_factory.adversarial_mutator import (
    build_mutation_plan_from_coverage,
    mutate_case,
    mutate_cases,
)
from xagent.loop_data_factory.export_agent_snapshot import (
    build_snapshot_payload,
    redact_sensitive_values,
    render_snapshot_markdown,
)
from xagent.loop_data_factory.gates import build_coverage_report, validate_loop_case
from xagent.loop_data_factory.generate_dataset import generate_dataset
from xagent.loop_data_factory.generators import (
    generate_loop1_case,
    generate_loop2_case,
    generate_loop3_case,
)
from xagent.loop_data_factory.import_loop_kb import (
    build_file_fingerprint,
    build_manifest_key,
    build_multipart_body,
    is_manifest_entry_current,
    merge_unique,
)
from xagent.loop_data_factory.local_sample_extractor import (
    anonymize_seed_text,
    extract_claims,
    extract_local_seed_dir,
)
from xagent.loop_data_factory.llm_output_judge import (
    LLMJudgeConfig,
    combine_rule_and_llm_judges,
    estimate_llm_judge_cost,
    judge_agent_output_with_llm,
)
from xagent.loop_data_factory.run_agent31_regression import run_regression
import xagent.loop_data_factory.llm_output_judge as llm_output_judge
import xagent.loop_data_factory.run_agent31_regression as regression_runner
from xagent.web.api.loop_data import (
    LoopEvalRunRequest,
    build_loop_eval_payload,
    discover_dataset_manifests,
    resolve_loop_file,
    resolve_loop_output_dir,
)


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "loop_data_factory" / "schemas"


def test_schema_files_are_valid_json() -> None:
    expected = {
        "loop_case.schema.json",
        "loop1_case.schema.json",
        "loop2_case.schema.json",
        "loop3_case.schema.json",
    }
    found = {path.name for path in SCHEMA_DIR.glob("*.json")}
    assert expected.issubset(found)
    for name in expected:
        data = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_generated_cases_pass_quality_gate() -> None:
    for case in [generate_loop1_case(0), generate_loop2_case(0), generate_loop3_case(1)]:
        result = validate_loop_case(case)
        assert result.passed, result.to_dict()


def test_loop2_weight_update_is_normalized() -> None:
    case = generate_loop2_case(0)
    weights = case["expected_output"]["expected_weight_update"]
    assert abs(sum(weights.values()) - 1.0) <= 0.02


def test_coverage_report_has_no_smoke_gaps() -> None:
    cases = [
        *[generate_loop1_case(i) for i in range(6)],
        *[generate_loop2_case(i) for i in range(3)],
        *[generate_loop3_case(i) for i in range(3)],
    ]
    for case in cases:
        case["quality"] = validate_loop_case(case).to_dict()
    report = build_coverage_report(cases, "test")
    assert report["case_count"] == {"loop1": 6, "loop2": 3, "loop3": 3}
    assert report["quality_pass_rate"] == 1.0


def test_generate_dataset_writes_manifest_and_prompts(tmp_path: Path) -> None:
    manifest = generate_dataset(level="smoke", output_dir=tmp_path)
    assert manifest["case_count"] == 12
    manifest_path = tmp_path / "dataset_manifest.json"
    assert manifest_path.exists()
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded["case_count"] == 12
    first = loaded["cases"][0]
    assert (tmp_path / first["path"]).exists()
    assert (tmp_path / first["prompt_path"]).exists()


def test_local_sample_extractor_anonymizes_pii_and_extracts_claims(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "candidate.md").write_text(
        "\n".join(
            [
                "姓名: 张三",
                "公司: 某某科技有限公司",
                "学校: 某某大学",
                "手机: 13812345678",
                "邮箱: zhangsan@example.com",
                "我主导了核心链路优化，性能提升 60%。",
                "我们一起解决了跨团队故障复盘问题。",
            ]
        ),
        encoding="utf-8",
    )
    (seed_dir / "resume.pdf").write_bytes(b"%PDF-1.4")

    manifest = extract_local_seed_dir(seed_dir)

    assert manifest["seed_count"] == 1
    assert manifest["skipped_count"] == 1
    assert manifest["pii_removed"]["phone"] == 1
    assert manifest["pii_removed"]["email"] == 1
    seed = manifest["seeds"][0]
    assert seed["candidate_seed_id"] == "candidate_001_anonymized"
    assert seed["usable_as_global_kb"] is False
    assert seed["claims"][0]["risk_type"] == "metric_inflation"
    assert "metric_inflation" in seed["risk_hypotheses"]
    assert "distancing" in seed["risk_hypotheses"]


def test_anonymize_seed_text_redacts_explicit_identity_fields() -> None:
    anonymized, counts = anonymize_seed_text(
        "姓名: Alice\ncompany: Secret Corp\nschool: Secret University\n"
        "phone 13900001111 email alice@example.com"
    )

    assert counts["phone"] == 1
    assert counts["email"] == 1
    assert "Alice" not in anonymized
    assert "Secret Corp" not in anonymized
    assert "Secret University" not in anonymized
    assert "Candidate A" in anonymized
    assert "[PHONE_REDACTED]" in anonymized
    assert "[EMAIL_REDACTED]" in anonymized


def test_generate_dataset_can_attach_local_seed_manifest(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "candidate.txt").write_text(
        "姓名: 李四\n我负责将发布失败率降低 30%，但没有说明口径。\n",
        encoding="utf-8",
    )

    manifest = generate_dataset(
        level="smoke",
        output_dir=tmp_path / "generated",
        loops=["loop1"],
        seed_dir=seed_dir,
    )

    assert manifest["case_count"] == 6
    assert manifest["local_seed_manifest"] == (
        "local_seed_extracts/anonymized_seed_manifest.json"
    )
    assert manifest["local_seed_summary"]["seed_count"] == 1
    seed_manifest = json.loads(
        (tmp_path / "generated" / manifest["local_seed_manifest"]).read_text(
            encoding="utf-8"
        )
    )
    assert seed_manifest["seeds"][0]["claims"]
    assert extract_claims("无可用行为证据。") == []


def test_adversarial_mutator_preserves_source_and_passes_quality() -> None:
    source = generate_loop1_case(1)
    mutated = mutate_case(source, mutation_type="halo_bias")

    assert source["case_id"] == "loop1_backend_architect_002"
    assert mutated["case_id"] == "loop1_backend_architect_002_adv_halo_bias"
    assert mutated["adversarial"]["source_case_id"] == source["case_id"]
    assert mutated["tags"]["adversarial_mutation"] == "halo_bias"
    assert mutated["tags"]["bias_type"] == "halo"
    assert validate_loop_case(mutated).passed


def test_adversarial_mutator_supports_loop2_and_loop3_quality() -> None:
    loop2 = mutate_case(generate_loop2_case(0), mutation_type="hard_vs_soft")
    loop3 = mutate_case(generate_loop3_case(1), mutation_type="small_sample_warning")

    assert loop2["expected_output"]["human_review_required"]
    assert loop3["expected_output"]["sample_size_warning"]
    assert validate_loop_case(loop2).passed
    assert validate_loop_case(loop3).passed


def test_generate_dataset_can_append_adversarial_cases(tmp_path: Path) -> None:
    manifest = generate_dataset(
        level="smoke",
        output_dir=tmp_path / "generated",
        loops=["loop1"],
        adversarial_copies_per_case=1,
    )

    assert manifest["case_count"] == 12
    assert manifest["adversarial"] == {"copies_per_case": 1, "case_count": 6}
    adversarial_entries = [
        item for item in manifest["cases"] if item.get("adversarial")
    ]
    assert len(adversarial_entries) == 6
    first = adversarial_entries[0]
    assert first["adversarial"]["source_case_id"] == "loop1_industrial_ai_support_001"
    assert (tmp_path / "generated" / first["path"]).exists()


def test_mutation_plan_from_coverage_gaps() -> None:
    plan = build_mutation_plan_from_coverage(
        {"gaps": ["loop1: missing coverage tag claim_risk", "loop3: no cases generated"]}
    )

    assert [item["loop_type"] for item in plan] == ["loop1", "loop3"]
    assert "metric_inflation" in plan[0]["recommended_mutations"]
    assert mutate_cases([generate_loop1_case(0)], copies_per_case=0) == []


def test_rule_judge_accepts_expected_loop_outputs() -> None:
    for case in [generate_loop1_case(0), generate_loop2_case(0), generate_loop3_case(0)]:
        output = build_expected_agent_output(case)
        result = judge_agent_output(case, output)
        assert result["passed"], result


def test_llm_judge_disabled_is_stable() -> None:
    case = generate_loop1_case(0)
    rule_judge = judge_agent_output(case, build_expected_agent_output(case))
    llm_judge = judge_agent_output_with_llm(
        case,
        build_expected_agent_output(case),
        rule_judge,
        config=LLMJudgeConfig(enabled=False),
    )
    combined = combine_rule_and_llm_judges(rule_judge, llm_judge)
    assert llm_judge["status"] == "disabled"
    assert combined["passed"] is True
    assert combined["llm_passed"] is None


def test_llm_judge_evaluated_result_and_cost(monkeypatch) -> None:
    case = generate_loop1_case(0)
    output = build_expected_agent_output(case)
    rule_judge = judge_agent_output(case, output)

    def fake_request_chat_completion(**kwargs):
        assert kwargs["config"].model == "judge-model"
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "passed": True,
                                "score": 0.92,
                                "issues": [],
                                "rationale": "Semantic match.",
                                "confidence": 0.88,
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }

    monkeypatch.setattr(
        llm_output_judge,
        "_request_chat_completion",
        fake_request_chat_completion,
    )
    llm_judge = judge_agent_output_with_llm(
        case,
        output,
        rule_judge,
        config=LLMJudgeConfig(
            enabled=True,
            api_base="http://judge.local/v1",
            api_key="secret",
            model="judge-model",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
        ),
    )
    assert llm_judge["status"] == "evaluated"
    assert llm_judge["passed"] is True
    assert llm_judge["estimated_cost_usd"] == 0.025
    assert combine_rule_and_llm_judges(rule_judge, llm_judge)["passed"] is True


def test_llm_judge_error_is_reported(monkeypatch) -> None:
    case = generate_loop1_case(0)
    output = build_expected_agent_output(case)
    rule_judge = judge_agent_output(case, output)

    def fake_request_chat_completion(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        llm_output_judge,
        "_request_chat_completion",
        fake_request_chat_completion,
    )
    llm_judge = judge_agent_output_with_llm(
        case,
        output,
        rule_judge,
        config=LLMJudgeConfig(
            enabled=True,
            api_base="http://judge.local/v1",
            api_key="secret",
            model="judge-model",
        ),
    )
    assert llm_judge["status"] == "error"
    assert llm_judge["error_type"] == "RuntimeError"
    assert combine_rule_and_llm_judges(rule_judge, llm_judge)["passed"] is True


def test_llm_judge_cost_estimation() -> None:
    assert estimate_llm_judge_cost(
        {"prompt_tokens": 1200, "completion_tokens": 300},
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.02,
    ) == 0.018


def test_rule_judge_accepts_loop2_productized_agent_shape() -> None:
    case = generate_loop2_case(0)
    output = {
        "case_id": case["case_id"],
        "updated_profile": {
            "competency_weights": {
                "hard_skill_match": 0.2,
                "constructive_collaboration": 0.25,
                "ownership": 0.25,
                "learning_agility": 0.15,
                "resilience_review": 0.15,
            },
            "probe_strategy": {
                "add": ["incident_reconstruction"],
                "remove": ["sensitive_attribute_questions"],
            },
            "conflicts": [{"conflict_type": "urgent_vs_high_standard"}],
        },
        "weight_changes": {
            "hard_skill_match": {"before": 0.3, "after": 0.2},
            "constructive_collaboration": {"before": 0.2, "after": 0.25},
        },
        "human_review_required": ["owner_priority_review"],
    }
    result = judge_agent_output(case, output)
    assert result["passed"], result


def test_rule_judge_prefers_loop2_markdown_over_embedded_json_fragment() -> None:
    case = generate_loop2_case(3)
    output = """
# Loop 2 完整结构化输出

**Case ID:** `loop2_industrial_ai_product_004`

| 维度 | 结论 |
|---|---|
| 权重调整 | 无需调整，5 项胜任力权重维持不变 |
| 追问策略 | 新增 3 项 / 下调 1 项 / 删除 1 项 |
| 冲突类型 | `culture_fit_vs_debias` |
| 人工复核 | 已标记，需 Hiring Manager / HRBP 裁定 |

## 二、能力权重

| 能力维度 | 权重 | 状态 |
|---|---|---|
| `hard_skill_match` | 0.30 | 不变 |
| `constructive_collaboration` | 0.20 | 不变 |
| `ownership` | 0.20 | 不变 |
| `learning_agility` | 0.15 | 不变 |
| `resilience_review` | 0.15 | 不变 |

## 三、追问策略更新

| 操作 | 提及项 | 驱动原因 |
|---|---|---|
| 新增 | `incident_reconstruction` | 用可观察事件替代主观文化匹配判断 |
| 新增 | `feedback_absorption_probe` | 用行为证据替代主观标签 |
| 新增 | `cross_team_conflict_probe` | 验证协作韧性 |
| 下调 | `background_prestige` | 降低背景光环 |
| 删除 | `sensitive_attribute_questions` | 婚育/年龄/健康/地域问题彻底移除 |

## 四、冲突解决方案

```json
{
  "conflict_type": "culture_fit_vs_debias",
  "rule": "list_conflict_and_request_owner_priority"
}
```

## 五、人工复核标记

```json
[
  "decision_owner_priority"
]
```
"""
    result = judge_agent_output(case, output)
    assert result["passed"], result


def test_rule_judge_accepts_loop3_productized_agent_shape() -> None:
    case = generate_loop3_case(0)
    output = {
        "case_id": case["case_id"],
        "sample_size_warning": "sample_too_small_for_global_rule",
        "prediction_hits": ["hard_skill_match"],
        "prediction_misses": [],
        "weight_changes_applied": {"constructive_collaboration": {"old": 0.2, "new": 0.3}},
        "probe_changes_applied": {"added": ["cross_team_conflict_probe"], "removed": []},
        "rules_preserved": ["do_not_remove_hard_skill_probes"],
        "global_rules_frozen": True,
    }
    result = judge_agent_output(case, output)
    assert result["passed"], result


def test_rule_judge_accepts_loop3_single_prediction_miss_shape() -> None:
    case = generate_loop3_case(2)
    output = {
        "case_id": case["case_id"],
        "prediction_miss": {
            "type": "False Negative",
            "root_cause": "learning_agility_underestimated",
        },
        "competency_weights_after": {
            "hard_skill_match": 0.30,
            "learning_agility": 0.30,
            "ownership": 0.15,
            "constructive_collaboration": 0.15,
            "resilience_review": 0.10,
            "terminology_fluency": 0.00,
        },
        "new_probes": ["P09_48_hour_work_sample", "P10_learning_path_probe"],
        "hard_skill_probes_preserved": ["P01", "P02", "P03"],
        "rules_compliance": {"do_not_remove_hard_skill_probes": "passed"},
        "sample_size_warning": "24人批次/1条失误记录 — 建议半幅执行权重调整",
        "human_review_required": None,
    }
    result = judge_agent_output(case, output)
    assert result["passed"], result


def test_rule_judge_rejects_unstructured_output() -> None:
    case = generate_loop1_case(0)
    result = judge_agent_output(case, "looks good")
    assert not result["passed"]
    assert result["issues"][0]["code"] == "json_parse"


def test_rule_judge_accepts_structured_markdown_loop1_output() -> None:
    case = generate_loop1_case(0)
    output = """
# 招聘选拔期：人才心理与核心胜任力客观诊断报告

| 字段 | 内容 |
|:---|:---|
| Case ID | loop1_industrial_ai_support_001 |
| 当前决策 | 备选池挂起 |

## 一、主张风险全量审计

claim_001 触发 metric_inflation，当前缺少基线、统计口径和验收周期。

## 二、BEI 追问设计

- 5-Minute Slice 深钻 hard_skill_match 与 ownership。
- 反事实探针 learning_agility。
- 失败复盘追问 resilience_review 与 constructive_collaboration。

## 三、面试官偏见审计

同级面试官评价触发 reactance，需要排除偏见。

## 四、BARS 五维评分卡

constructive_collaboration、ownership、learning_agility、hard_skill_match、
resilience_review 均需补充证据。
"""
    result = judge_agent_output(case, output)
    assert result["passed"], result


def test_rule_judge_accepts_markdown_claim_risk_aliases() -> None:
    case = generate_loop1_case(0)
    output = """
# 招聘选拔期：人才心理与核心胜任力客观诊断报告

Case ID: `loop1_industrial_ai_support_001`

## 一、关键风险总结

60% 性能提升声明不可采信，缺少基线、统计口径和验收周期，属于指标注水风险。

## 二、BEI 追问

- 5 分钟切片深钻
- 反事实探针
- 失败复盘追问

## 三、面试官偏误审计

Reactance 偏误已识别并校正。

## 四、BARS 评分卡

constructive_collaboration、ownership、learning_agility、hard_skill_match、resilience_review 均已覆盖。

最终建议：备选池挂起
"""
    result = judge_agent_output(case, output)
    assert result["passed"], result


def test_rule_judge_accepts_markdown_bias_aliases() -> None:
    case = generate_loop1_case(1)
    output = """
# Loop 1 候选人证据审计报告

Case ID: `loop1_backend_architect_002`

## 风险审计

候选人 claim 触发 role_exaggeration，存在角色夸大和团队成果包装风险。

## BEI 追问

- 5-Minute Slice
- counterfactual_probe
- failure_review_probe

## 面试官偏见审计

HR 认为候选人来自知名公司所以应该没问题，这是典型光环效应，需要校正。

## BARS 评分卡

constructive_collaboration、ownership、learning_agility、hard_skill_match、resilience_review 均已覆盖。

## 合规改写

涉及家庭照料的问题需要改写为岗位排班要求确认。

最终建议：澶囬€夋睜鎸傝捣
"""
    result = judge_agent_output(case, output)
    assert result["passed"], result


def test_rule_judge_accepts_prefaced_markdown_report() -> None:
    case = generate_loop1_case(0)
    output = """
基于三循环协议，以下是结构化输出。

---

# Loop 1 候选人证据审计报告

Case ID: `loop1_industrial_ai_support_001`

## 一、包装、夸大与逻辑断裂审计

| Claim | 风险 |
|---|---|
| 性能提升 60% | metric_inflation，缺少基线、统计口径和验收周期 |

## 二、BEI 追问计划

- 5分钟切片深钻
- 反事实探针
- 失败复盘追问

## 三、偏误审计

reactance 已校正。

## 四、BARS 去偏评分卡

| 维度 | 评分 |
|---|---|
| 建设性协作 | 3 |
| 主人翁意识 | 3 |
| 学习敏捷度 | 3 |
| 岗位硬实力 | 2 |
| 抗逆境与复盘 | 2 |

最终建议：备选池挂起
"""
    result = judge_agent_output(case, output)
    assert result["passed"], result


def test_rule_judge_rejects_high_risk_claim_without_enough_probes() -> None:
    case = generate_loop1_case(0)
    output = build_expected_agent_output(case)
    output["bei_probe_plan"] = ["5_minute_slice"]
    result = judge_agent_output(case, output)
    assert not result["passed"]
    assert any(issue["code"] == "high_risk_probe_count" for issue in result["issues"])


def test_rule_judge_rejects_loop2_without_sensitive_probe_removal() -> None:
    case = generate_loop2_case(0)
    output = build_expected_agent_output(case)
    output["probe_changes"]["remove"] = []
    result = judge_agent_output(case, output)
    assert not result["passed"]
    assert any(issue["code"] == "sensitive_probe_remove" for issue in result["issues"])


def test_rule_judge_rejects_loop3_without_rules_not_to_change() -> None:
    case = generate_loop3_case(0)
    output = build_expected_agent_output(case)
    output["next_batch_strategy"].pop("rules_not_to_change")
    result = judge_agent_output(case, output)
    assert not result["passed"]
    assert any(issue["code"] == "rules_not_to_change" for issue in result["issues"])


def test_human_override_success_is_treated_as_prediction_miss() -> None:
    case = generate_loop3_case(3)
    assert case["tags"]["outcome_type"] == "human_override_success"
    assert case["expected_output"]["prediction_misses"]


def test_dry_run_regression_writes_eval_report(tmp_path: Path) -> None:
    generate_dataset(level="smoke", output_dir=tmp_path / "dataset")
    summary = run_regression(
        dataset_manifest=tmp_path / "dataset" / "dataset_manifest.json",
        output_dir=tmp_path / "eval",
        dry_run=True,
    )
    assert summary["case_count"] == 12
    assert summary["pass_rate"] == 1.0
    assert (tmp_path / "eval" / "summary.json").exists()
    assert (tmp_path / "eval" / "results").exists()


def test_dry_run_regression_writes_disabled_llm_judge(tmp_path: Path) -> None:
    generate_dataset(level="smoke", output_dir=tmp_path / "dataset")
    summary = run_regression(
        dataset_manifest=tmp_path / "dataset" / "dataset_manifest.json",
        output_dir=tmp_path / "eval",
        dry_run=True,
        limit=1,
        llm_judge_config=LLMJudgeConfig(enabled=False),
    )
    assert summary["llm_judge"] == {
        "enabled": False,
        "evaluated": 0,
        "errors": 0,
        "estimated_cost_usd": None,
    }
    result_file = next((tmp_path / "eval" / "results").glob("*.json"))
    result = json.loads(result_file.read_text(encoding="utf-8"))
    assert result["llm_judge"]["status"] == "disabled"
    assert result["judge"]["rule_passed"] is True


def test_dry_run_regression_aggregates_llm_judge_cost(
    tmp_path: Path,
    monkeypatch,
) -> None:
    generate_dataset(level="smoke", output_dir=tmp_path / "dataset")

    def fake_request_chat_completion(**kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "passed": True,
                                "score": 1,
                                "issues": [],
                                "rationale": "ok",
                                "confidence": 1,
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
        }

    monkeypatch.setattr(
        llm_output_judge,
        "_request_chat_completion",
        fake_request_chat_completion,
    )
    summary = run_regression(
        dataset_manifest=tmp_path / "dataset" / "dataset_manifest.json",
        output_dir=tmp_path / "eval",
        dry_run=True,
        limit=2,
        llm_judge_config=LLMJudgeConfig(
            enabled=True,
            api_base="http://judge.local/v1",
            api_key="secret",
            model="judge-model",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.01,
        ),
    )
    assert summary["llm_judge"] == {
        "enabled": True,
        "evaluated": 2,
        "errors": 0,
        "estimated_cost_usd": 0.04,
    }


def test_loop_data_api_helpers_resolve_under_root(tmp_path: Path) -> None:
    root = tmp_path / "loop_data"
    output = resolve_loop_output_dir(root, "smoke/current", "smoke")
    assert output == (root / "smoke/current").resolve()
    default_output = resolve_loop_output_dir(root, None, "mvp")
    assert default_output == (root / "generated_mvp").resolve()
    assert resolve_loop_file(root, "generated/dataset_manifest.json") == (
        root / "generated/dataset_manifest.json"
    ).resolve()


def test_loop_data_api_helpers_discover_manifests(tmp_path: Path) -> None:
    manifest = generate_dataset(level="smoke", output_dir=tmp_path / "generated")
    found = discover_dataset_manifests(tmp_path)
    assert found
    assert found[0]["dataset_version"] == manifest["dataset_version"]
    assert found[0]["case_count"] == 12


def test_loop_eval_payload_uses_resolved_paths(tmp_path: Path) -> None:
    request = LoopEvalRunRequest(
        dry_run=True,
        dataset_manifest="dataset/dataset_manifest.json",
        output_subdir="eval",
        case_ids=["loop1_industrial_ai_support_001"],
    )
    payload = build_loop_eval_payload(
        request=request,
        dataset_manifest=tmp_path / "dataset" / "dataset_manifest.json",
        output_dir=tmp_path / "eval",
        reuse_task_map=None,
    )
    assert payload["dry_run"] is True
    assert payload["dataset_manifest"] == str(tmp_path / "dataset" / "dataset_manifest.json")
    assert payload["output_dir"] == str(tmp_path / "eval")
    assert payload["case_ids"] == ["loop1_industrial_ai_support_001"]


def test_failed_regression_archives_replay_bundle(tmp_path: Path, monkeypatch) -> None:
    generate_dataset(level="smoke", output_dir=tmp_path / "dataset")
    monkeypatch.setattr(regression_runner, "build_expected_agent_output", lambda case: {})
    summary = run_regression(
        dataset_manifest=tmp_path / "dataset" / "dataset_manifest.json",
        output_dir=tmp_path / "eval",
        dry_run=True,
        limit=1,
    )
    assert summary["failed"] == 1
    failed_files = list((tmp_path / "eval" / "failed_cases").glob("*.json"))
    assert len(failed_files) == 1
    bundle = json.loads(failed_files[0].read_text(encoding="utf-8"))
    assert {"case", "prompt", "raw_output", "result"}.issubset(bundle)


def test_agent_snapshot_redacts_sensitive_model_fields() -> None:
    redacted = redact_sensitive_values(
        {
            "models": {
                "primary": {
                    "model": "deepseek-chat",
                    "api_key": "sk-secret",
                    "nested": {"refresh_token": "token"},
                }
            }
        }
    )
    assert redacted["models"]["primary"]["api_key"] == "***REDACTED***"
    assert redacted["models"]["primary"]["nested"]["refresh_token"] == "***REDACTED***"


def test_agent_snapshot_markdown_includes_checks_and_instruction_hash() -> None:
    payload = build_snapshot_payload(
        {
            "id": 31,
            "name": "Interview Psychologist",
            "description": "test",
            "instructions": "Use structured interview evidence.",
            "execution_mode": "think",
            "models": {"primary": {"model": "test", "api_key": "hidden"}},
            "knowledge_bases": ["interview_psychologist_loop_kb"],
            "skills": [],
            "tool_categories": ["knowledge", "web_search"],
            "suggested_prompts": ["run loop1"],
            "status": "published",
            "published_at": None,
            "created_at": "2026-07-02T00:00:00Z",
            "updated_at": "2026-07-02T00:00:00Z",
        },
        metadata={
            "generated_at": "2026-07-02T00:00:00+00:00",
            "api_base": "http://localhost",
            "agent_id": 31,
            "source": "GET /api/agents/{agent_id}",
        },
    )
    markdown = render_snapshot_markdown(payload)
    assert payload["agent"]["models"]["primary"]["api_key"] == "***REDACTED***"
    assert payload["derived"]["instructions_char_count"] == 34
    assert payload["configuration_checks"][2]["passed"]
    assert "# Agent 31 配置快照" in markdown
    assert "interview_psychologist_loop_kb" in markdown
    assert "***REDACTED***" in markdown


def test_loop_kb_import_helpers_merge_and_build_multipart(tmp_path: Path) -> None:
    source = tmp_path / "kb.md"
    source.write_text("# KB\n\ncontent", encoding="utf-8")
    assert merge_unique(["file", "knowledge"], ["knowledge", "web_search"]) == [
        "file",
        "knowledge",
        "web_search",
    ]
    body = build_multipart_body(
        fields={"collection": "interview_psychologist_loop_kb"},
        file_field="file",
        file_path=source,
        boundary="test-boundary",
    )
    assert b'name="collection"' in body
    assert b'filename="kb.md"' in body
    assert b"# KB" in body


def test_loop_kb_import_manifest_helpers_detect_current_file(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    source = docs_dir / "kb.md"
    source.write_text("# KB\n\ncontent", encoding="utf-8")
    fingerprint = build_file_fingerprint(source)
    key = build_manifest_key(
        collection="interview_psychologist_loop_kb",
        docs_dir=docs_dir,
        path=source,
    )
    assert key == "interview_psychologist_loop_kb:kb.md"
    entry = {
        **fingerprint,
        "embedding_model_id": "text-embedding-v4",
        "chunk_strategy": "markdown",
    }
    assert is_manifest_entry_current(
        entry,
        fingerprint=fingerprint,
        embedding_model_id="text-embedding-v4",
        chunk_strategy="markdown",
    )
    source.write_text("# KB\n\nchanged", encoding="utf-8")
    assert not is_manifest_entry_current(
        entry,
        fingerprint=build_file_fingerprint(source),
        embedding_model_id="text-embedding-v4",
        chunk_strategy="markdown",
    )
