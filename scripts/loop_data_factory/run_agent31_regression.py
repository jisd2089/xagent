"""Run Agent 31 regression cases from a generated loop dataset.

The runner is stdlib-only. It supports two execution modes:

* ``--dry-run`` builds deterministic passing outputs from each case's
  expected data, then runs the Rule Judge and writes reports. This verifies
  the regression filesystem contract without requiring a live Xagent server.
* default mode calls the SDK task API with ``--api-key`` and polls task status.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.loop_data_factory.agent_output_judge import (
    build_expected_agent_output,
    judge_agent_output,
)


TERMINAL_STATUSES = {"completed", "failed"}


def run_regression(
    *,
    dataset_manifest: Path,
    agent_id: int = 31,
    output_dir: Path | None = None,
    api_base: str = "http://localhost",
    api_key: str | None = None,
    login_username: str | None = None,
    login_password: str | None = None,
    rotate_runtime_key: bool = False,
    reuse_task_id: int | None = None,
    reuse_task_map: dict[str, int] | None = None,
    dry_run: bool = False,
    case_ids: list[str] | None = None,
    limit: int | None = None,
    max_new_tasks: int | None = 3,
    stop_on_failure: bool = False,
    poll_interval: float = 2.0,
    timeout_seconds: float = 900.0,
    clean: bool = True,
) -> dict[str, Any]:
    manifest = _read_json(dataset_manifest)
    dataset_root = dataset_manifest.parent
    eval_dir = output_dir or dataset_root / "eval_reports" / _run_id(manifest, dry_run)

    resolved_api_key = api_key
    if not dry_run and resolved_api_key is None and login_username and login_password:
        resolved_api_key = _resolve_runtime_key(
            api_base=api_base,
            agent_id=agent_id,
            username=login_username,
            password=login_password,
            rotate=rotate_runtime_key,
        )

    cases = manifest.get("cases", [])
    if case_ids:
        wanted = set(case_ids)
        cases = [case_ref for case_ref in cases if case_ref.get("case_id") in wanted]
        found = {case_ref.get("case_id") for case_ref in cases}
        missing = sorted(wanted - found)
        if missing:
            raise ValueError(f"Unknown --case-id value(s): {', '.join(missing)}")
    if limit is not None:
        cases = cases[:limit]
    if reuse_task_id is not None and reuse_task_map:
        raise ValueError("--reuse-task-id and --reuse-task-map are mutually exclusive")
    if reuse_task_id is not None and len(cases) != 1:
        raise ValueError("--reuse-task-id requires exactly one selected case; use --limit 1")
    new_task_count = _count_new_tasks(
        cases,
        dry_run=dry_run,
        reuse_task_id=reuse_task_id,
        reuse_task_map=reuse_task_map,
    )
    if max_new_tasks is not None and new_task_count > max_new_tasks:
        raise ValueError(
            f"Refusing to create {new_task_count} new SDK task(s); "
            f"max_new_tasks={max_new_tasks}. Use --limit/--case-id, "
            "--reuse-task-map, or raise --max-new-tasks intentionally."
        )
    if clean and eval_dir.exists():
        shutil.rmtree(eval_dir)
    for dirname in ["results", "raw_outputs", "failed_cases"]:
        (eval_dir / dirname).mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    stopped_early = False
    for case_ref in cases:
        case = _read_json(dataset_root / case_ref["path"])
        prompt = (dataset_root / case_ref["prompt_path"]).read_text(encoding="utf-8")
        if dry_run:
            raw_output: Any = build_expected_agent_output(case)
            transport = {
                "mode": "dry_run",
                "task_id": None,
                "status": "completed",
                "error": None,
            }
        elif reuse_task_map and case["case_id"] in reuse_task_map:
            raw_output, transport = _fetch_agent_task(
                api_base=api_base,
                api_key=resolved_api_key,
                task_id=int(reuse_task_map[case["case_id"]]),
            )
        elif reuse_task_id is not None:
            raw_output, transport = _fetch_agent_task(
                api_base=api_base,
                api_key=resolved_api_key,
                task_id=reuse_task_id,
            )
        else:
            raw_output, transport = _call_agent(
                api_base=api_base,
                api_key=resolved_api_key,
                agent_id=agent_id,
                prompt=prompt,
                metadata={
                    "dataset_version": manifest.get("dataset_version"),
                    "case_id": case["case_id"],
                    "loop_type": case["loop_type"],
                },
                poll_interval=poll_interval,
                timeout_seconds=timeout_seconds,
            )

        judge = judge_agent_output(case, raw_output)
        result = {
            "case_id": case["case_id"],
            "loop_type": case["loop_type"],
            "dataset_version": manifest.get("dataset_version"),
            "transport": transport,
            "judge": judge,
            "passed": bool(transport.get("status") == "completed" and judge["passed"]),
            "tags": case.get("tags", {}),
        }
        _write_json(eval_dir / "raw_outputs" / f"{case['case_id']}.json", raw_output)
        _write_json(eval_dir / "results" / f"{case['case_id']}.json", result)
        if not result["passed"]:
            _write_json(
                eval_dir / "failed_cases" / f"{case['case_id']}.json",
                {
                    "case": case,
                    "prompt": prompt,
                    "raw_output": raw_output,
                    "result": result,
                },
            )
        results.append(result)
        if stop_on_failure and not result["passed"]:
            stopped_early = True
            break

    summary = _build_summary(
        manifest=manifest,
        results=results,
        dry_run=dry_run,
        agent_id=agent_id,
        api_base=api_base,
        new_task_count=new_task_count,
        stopped_early=stopped_early,
    )
    _write_json(eval_dir / "summary.json", summary)
    _write_json(
        eval_dir / "eval_manifest.json",
        {
            **summary,
            "result_files": [
                f"results/{item['case_id']}.json"
                for item in results
            ],
        },
    )
    return {"eval_dir": str(eval_dir), **summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("docs/loop/generated/dataset_manifest.json"),
        help="Path to dataset_manifest.json.",
    )
    parser.add_argument("--agent-id", type=int, default=31, help="Agent id.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Eval report directory. Defaults under dataset/eval_reports/.",
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost",
        help="Xagent backend base URL for non-dry-run mode.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Agent runtime API key for /v1/chat/tasks.",
    )
    parser.add_argument(
        "--login-username",
        default=None,
        help="Web login username used to obtain an Agent runtime API key.",
    )
    parser.add_argument(
        "--login-password",
        default=None,
        help="Web login password used to obtain an Agent runtime API key.",
    )
    parser.add_argument(
        "--rotate-runtime-key",
        action="store_true",
        help="Rotate Agent runtime API key after login. Required when no key exists.",
    )
    parser.add_argument(
        "--reuse-task-id",
        type=int,
        default=None,
        help="Rejudge an existing completed SDK task instead of creating a new task. Use with --limit 1.",
    )
    parser.add_argument(
        "--reuse-task-map",
        type=Path,
        default=None,
        help="JSON object mapping case_id to completed SDK task_id for batch rejudging.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Only run or rejudge the named case_id. Repeat for multiple cases.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call Agent 31; use expected outputs to verify report flow.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit cases.")
    parser.add_argument(
        "--max-new-tasks",
        type=int,
        default=3,
        help="Refuse non-dry-run execution if it would create more SDK tasks.",
    )
    parser.add_argument(
        "--no-max-new-tasks",
        action="store_true",
        help="Disable the new SDK task budget guard.",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop after the first failed case and still write partial reports.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval for task status.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=900.0,
        help="Per-case task timeout. Agent 31 DAG think-mode cases can take 7+ minutes.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not delete the eval output directory before running.",
    )
    args = parser.parse_args()
    summary = run_regression(
        dataset_manifest=args.dataset,
        agent_id=args.agent_id,
        output_dir=args.output,
        api_base=args.api_base,
        api_key=args.api_key,
        login_username=args.login_username,
        login_password=args.login_password,
        rotate_runtime_key=args.rotate_runtime_key,
        reuse_task_id=args.reuse_task_id,
        reuse_task_map=_read_reuse_task_map(args.reuse_task_map)
        if args.reuse_task_map
        else None,
        dry_run=args.dry_run,
        case_ids=args.case_ids,
        limit=args.limit,
        max_new_tasks=None if args.no_max_new_tasks else args.max_new_tasks,
        stop_on_failure=args.stop_on_failure,
        poll_interval=args.poll_interval,
        timeout_seconds=args.timeout_seconds,
        clean=not args.no_clean,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _call_agent(
    *,
    api_base: str,
    api_key: str | None,
    agent_id: int,
    prompt: str,
    metadata: dict[str, Any],
    poll_interval: float,
    timeout_seconds: float,
) -> tuple[str | None, dict[str, Any]]:
    if not api_key:
        raise ValueError("--api-key is required unless --dry-run is set")

    create_payload = {
        "agent_id": agent_id,
        "message": {"role": "user", "content": prompt},
        "metadata": metadata,
    }
    created = _request_json(
        "POST",
        f"{api_base.rstrip('/')}/v1/chat/tasks",
        api_key,
        create_payload,
    )
    task_id = created["task_id"]
    started = time.monotonic()
    last_status = created.get("status", "running")
    task_info: dict[str, Any] = {}
    while time.monotonic() - started <= timeout_seconds:
        task_info = _request_json(
            "GET",
            f"{api_base.rstrip('/')}/v1/chat/tasks/{task_id}",
            api_key,
            None,
        )
        last_status = str(task_info.get("status") or "")
        if last_status in TERMINAL_STATUSES:
            break
        time.sleep(poll_interval)

    if last_status not in TERMINAL_STATUSES:
        return None, {
            "mode": "http",
            "task_id": task_id,
            "status": "timeout",
            "error": f"Task did not finish within {timeout_seconds} seconds",
        }

    return task_info.get("output"), {
        "mode": "http",
        "task_id": task_id,
        "status": last_status,
        "error": task_info.get("error"),
    }


def _fetch_agent_task(
    *,
    api_base: str,
    api_key: str | None,
    task_id: int,
) -> tuple[str | None, dict[str, Any]]:
    if not api_key:
        raise ValueError("--api-key is required unless --dry-run is set")
    task_info = _request_json(
        "GET",
        f"{api_base.rstrip('/')}/v1/chat/tasks/{task_id}",
        api_key,
        None,
    )
    status = str(task_info.get("status") or "")
    return task_info.get("output"), {
        "mode": "http_reuse",
        "task_id": task_id,
        "status": status,
        "error": task_info.get("error"),
    }


def _resolve_runtime_key(
    *,
    api_base: str,
    agent_id: int,
    username: str,
    password: str,
    rotate: bool,
) -> str:
    login = _request_json(
        "POST",
        f"{api_base.rstrip('/')}/api/auth/login",
        None,
        {"username": username, "password": password},
    )
    token = login.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Login succeeded without access_token")

    if rotate:
        key_response = _request_json(
            "POST",
            f"{api_base.rstrip('/')}/api/agents/{agent_id}/api-key",
            token,
            None,
        )
    else:
        key_response = _request_json(
            "GET",
            f"{api_base.rstrip('/')}/api/agents/{agent_id}/api-key",
            token,
            None,
        )

    full_key = key_response.get("full_key")
    if isinstance(full_key, str) and full_key:
        return full_key

    raise RuntimeError(
        "Runtime API key was not returned. Re-run with --rotate-runtime-key."
    )


def _request_json(
    method: str,
    url: str,
    api_key: str | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
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


def _build_summary(
    *,
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
    dry_run: bool,
    agent_id: int,
    api_base: str,
    new_task_count: int = 0,
    stopped_early: bool = False,
) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    by_loop: dict[str, dict[str, int | float]] = {}
    for loop in ("loop1", "loop2", "loop3"):
        loop_results = [item for item in results if item["loop_type"] == loop]
        loop_total = len(loop_results)
        loop_passed = sum(1 for item in loop_results if item["passed"])
        by_loop[loop] = {
            "total": loop_total,
            "passed": loop_passed,
            "pass_rate": round(loop_passed / loop_total, 4) if loop_total else 0.0,
        }
    return {
        "run_id": _run_id(manifest, dry_run),
        "dataset_version": manifest.get("dataset_version"),
        "agent_id": agent_id,
        "api_base": api_base,
        "dry_run": dry_run,
        "case_count": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "by_loop": by_loop,
        "new_task_count": new_task_count,
        "stopped_early": stopped_early,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _count_new_tasks(
    cases: list[dict[str, Any]],
    *,
    dry_run: bool,
    reuse_task_id: int | None,
    reuse_task_map: dict[str, int] | None,
) -> int:
    if dry_run or reuse_task_id is not None:
        return 0
    if not reuse_task_map:
        return len(cases)
    return sum(1 for case_ref in cases if str(case_ref.get("case_id")) not in reuse_task_map)


def _run_id(manifest: dict[str, Any], dry_run: bool) -> str:
    suffix = "dry_run" if dry_run else "agent31"
    return f"{manifest.get('dataset_version', 'dataset')}.{suffix}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_reuse_task_map(path: Path) -> dict[str, int]:
    data = _read_json(path)
    mapping: dict[str, int] = {}
    for case_id, task_id in data.items():
        if not isinstance(case_id, str):
            raise ValueError("--reuse-task-map keys must be case_id strings")
        try:
            mapping[case_id] = int(task_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"--reuse-task-map value for {case_id!r} must be an integer task id"
            ) from exc
    return mapping


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
