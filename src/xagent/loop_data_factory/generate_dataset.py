"""Generate three-loop interview-agent datasets.

This script is intentionally stdlib-only. It writes deterministic JSON cases,
regression prompts, a manifest, and a coverage report under the requested
output directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from xagent.loop_data_factory.adversarial_mutator import mutate_cases
from xagent.loop_data_factory.gates import apply_quality, build_coverage_report
from xagent.loop_data_factory.generators import generate_cases
from xagent.loop_data_factory.local_sample_extractor import (
    LOCAL_SEED_MANIFEST,
    LOCAL_SEED_OUTPUT_DIR,
    write_local_seed_manifest,
)
from xagent.loop_data_factory.models import (
    COVERAGE_DIR,
    LEVEL_COUNTS,
    LOOP_DIRS,
    PROMPT_DIR,
    utc_version_stamp,
)
from xagent.loop_data_factory.prompts import render_prompt


def generate_dataset(
    *,
    level: str,
    output_dir: Path,
    loops: list[str] | None = None,
    clean: bool = True,
    seed_dir: Path | None = None,
    adversarial_copies_per_case: int = 0,
) -> dict[str, Any]:
    if level not in LEVEL_COUNTS:
        raise ValueError(f"Unsupported level {level!r}; choose one of {sorted(LEVEL_COUNTS)}")
    selected_loops = loops or ["loop1", "loop2", "loop3"]
    for loop in selected_loops:
        if loop not in LOOP_DIRS:
            raise ValueError(f"Unsupported loop {loop!r}; choose loop1, loop2, loop3")

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    _ensure_dirs(output_dir)

    dataset_version = utc_version_stamp()
    seed_manifest: dict[str, Any] | None = None
    if seed_dir is not None:
        seed_manifest = write_local_seed_manifest(seed_dir, output_dir)

    all_cases: list[dict[str, Any]] = []
    manifest_cases: list[dict[str, Any]] = []
    for loop in selected_loops:
        count = LEVEL_COUNTS[level][loop]
        base_cases = generate_cases(loop, count)
        cases = [
            apply_quality(case)
            for case in [
                *base_cases,
                *mutate_cases(
                    base_cases,
                    copies_per_case=adversarial_copies_per_case,
                ),
            ]
        ]
        all_cases.extend(cases)
        loop_dir = output_dir / LOOP_DIRS[loop]
        for case in cases:
            case_path = loop_dir / f"{case['case_id']}.json"
            _write_json(case_path, case)
            prompt_path = output_dir / PROMPT_DIR / f"{case['case_id']}.md"
            prompt_path.write_text(render_prompt(case), encoding="utf-8")
            manifest_case = {
                "case_id": case["case_id"],
                "loop_type": case["loop_type"],
                "path": str(case_path.relative_to(output_dir)).replace("\\", "/"),
                "prompt_path": str(prompt_path.relative_to(output_dir)).replace(
                    "\\", "/"
                ),
                "quality_passed": case["quality"]["passed"],
                "tags": case["tags"],
            }
            if case.get("adversarial"):
                manifest_case["adversarial"] = case["adversarial"]
            manifest_cases.append(manifest_case)

    coverage = build_coverage_report(all_cases, dataset_version)
    coverage_path = output_dir / COVERAGE_DIR / f"{dataset_version}.json"
    _write_json(coverage_path, coverage)

    manifest = {
        "dataset_version": dataset_version,
        "level": level,
        "loops": selected_loops,
        "case_count": len(manifest_cases),
        "coverage_report": str(coverage_path.relative_to(output_dir)).replace("\\", "/"),
        "cases": manifest_cases,
    }
    if seed_manifest is not None:
        manifest["local_seed_manifest"] = (
            f"{LOCAL_SEED_OUTPUT_DIR}/{LOCAL_SEED_MANIFEST}"
        )
        manifest["local_seed_summary"] = {
            "seed_count": seed_manifest["seed_count"],
            "skipped_count": seed_manifest["skipped_count"],
            "pii_removed": seed_manifest["pii_removed"],
            "usable_as_global_kb": False,
        }
    if adversarial_copies_per_case > 0:
        manifest["adversarial"] = {
            "copies_per_case": adversarial_copies_per_case,
            "case_count": sum(1 for case in all_cases if case.get("adversarial")),
        }
    _write_json(output_dir / "dataset_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--level",
        choices=sorted(LEVEL_COUNTS),
        default="smoke",
        help="Dataset size profile.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/loop/generated"),
        help="Output directory.",
    )
    parser.add_argument(
        "--loops",
        default="loop1,loop2,loop3",
        help="Comma-separated loops to generate.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not delete the output directory before generation.",
    )
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=None,
        help="Optional local seed-material directory to anonymize into the dataset.",
    )
    parser.add_argument(
        "--adversarial-copies",
        type=int,
        default=0,
        help="Number of deterministic adversarial copies to add per generated case.",
    )
    args = parser.parse_args()
    loops = [item.strip() for item in args.loops.split(",") if item.strip()]
    manifest = generate_dataset(
        level=args.level,
        output_dir=args.output,
        loops=loops,
        clean=not args.no_clean,
        seed_dir=args.seed_dir,
        adversarial_copies_per_case=args.adversarial_copies,
    )
    print(
        json.dumps(
            {
                "dataset_version": manifest["dataset_version"],
                "level": manifest["level"],
                "case_count": manifest["case_count"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _ensure_dirs(output_dir: Path) -> None:
    for dirname in [*LOOP_DIRS.values(), PROMPT_DIR, COVERAGE_DIR]:
        (output_dir / dirname).mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
