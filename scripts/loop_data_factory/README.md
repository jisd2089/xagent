# Loop Data Factory

Generate deterministic Loop 1/2/3 datasets for the interview psychologist
agent design under `docs/loop`.

Common usage from the repository root:

```bash
python scripts/loop_data_factory/generate_dataset.py --level smoke --output docs/loop/generated
python scripts/loop_data_factory/generate_dataset.py --level mvp --output docs/loop/generated
python scripts/loop_data_factory/generate_dataset.py \
  --level smoke \
  --seed-dir docs/loop/private_seed_samples \
  --output docs/loop/generated_seeded
python scripts/loop_data_factory/generate_dataset.py \
  --level smoke \
  --adversarial-copies 1 \
  --output docs/loop/generated_adversarial
```

The MVP implementation is intentionally stdlib-only. It produces JSON cases,
regression prompts, and a coverage report. Later phases can replace or augment
the deterministic generators with DeepResearch and LLM-backed generators while
keeping the same case schemas and quality gates.

`--seed-dir` performs a conservative stdlib-only pass over local text seed
materials (`.md`, `.txt`, `.json`). It removes phone/email/ID-card-like values,
redacts explicit name/company/school fields, extracts candidate claims, and
writes `local_seed_extracts/anonymized_seed_manifest.json`. Unsupported binary
files are recorded as skipped instead of being parsed.

`--adversarial-copies` appends deterministic mutation copies for each generated
case. The copy keeps a pointer to the source case in `adversarial.source_case_id`
and tags the mutation type so coverage gaps can be traced back to concrete
stress cases.

Key files:

- `schemas/*.schema.json`: LoopCase and Loop 1/2/3 JSON Schema contracts.
- `gates.py`: generated-data quality gate and coverage reporter.
- `local_sample_extractor.py`: local seed-material anonymizer for `--seed-dir`.
- `adversarial_mutator.py`: deterministic stress-case mutations for
  `--adversarial-copies`.
- `agent_output_judge.py`: rule-based judge for Agent 31 outputs.
- `run_agent31_regression.py`: manifest-driven regression runner.

## Agent 31 Regression

Verify the regression filesystem and Rule Judge without a live backend:

```bash
python scripts/loop_data_factory/run_agent31_regression.py \
  --dataset docs/loop/generated/dataset_manifest.json \
  --dry-run
```

Run against a live Xagent backend through the SDK task API:

```bash
python scripts/loop_data_factory/run_agent31_regression.py \
  --dataset docs/loop/generated/dataset_manifest.json \
  --agent-id 31 \
  --api-base http://localhost \
  --api-key "$XAGENT_AGENT31_API_KEY"
```

Agent 31 currently runs in DAG `think` mode, so a single smoke case can take
7-10 minutes. The runner defaults to a 900 second per-case timeout for live
HTTP mode. If a completed task needs to be rejudged without creating another
Agent execution, reuse it:

```bash
python scripts/loop_data_factory/run_agent31_regression.py \
  --dataset docs/loop/generated/dataset_manifest.json \
  --api-base http://localhost \
  --login-username admin \
  --login-password admin123456 \
  --rotate-runtime-key \
  --limit 1 \
  --reuse-task-id 188
```

The judge accepts both JSON outputs and structured Markdown reports. Markdown
reports are checked against hard anchors such as case id, claim risk, BEI probe
types, bias audit, BARS dimensions, and decision enum.

Outputs are written under `docs/loop/generated/eval_reports/` by default:

- `summary.json`
- `eval_manifest.json`
- `results/*.json`
- `raw_outputs/*.json`
- `failed_cases/*.json`
