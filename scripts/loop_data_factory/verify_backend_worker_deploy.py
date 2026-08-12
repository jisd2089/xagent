"""HTTP smoke checks for backend/worker loop-data deployment.

This script intentionally uses only the Python standard library so it can run
from WSL hosts that do not have the project's test dependencies installed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        parsed["_http_error"] = exc.code
        return exc.code, parsed


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def record(results: list[dict[str, Any]], name: str, status: str, **details: Any) -> None:
    results.append({"name": name, "status": status, **details})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("XAGENT_BASE_URL", "http://localhost"))
    parser.add_argument("--username", default=os.getenv("XAGENT_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("XAGENT_PASSWORD", "admin123"))
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d%H%M%S"))
    parser.add_argument(
        "--seed-subdir",
        help="Existing raw seed-material directory under XAGENT_LOOP_DATA_DIR.",
    )
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    results: list[dict[str, Any]] = []
    output: dict[str, Any] = {
        "base_url": base_url,
        "run_id": args.run_id,
        "checks": results,
    }

    status, auth_check = request_json("GET", f"{base_url}/api/auth/check")
    require(status == 200 and auth_check.get("success") is True, "auth check failed")
    record(results, "auth_check", "passed", http_status=status)

    status, login = request_json(
        "POST",
        f"{base_url}/api/auth/login",
        payload={"username": args.username, "password": args.password},
    )
    require(status == 200 and login.get("access_token"), "login failed")
    token = str(login["access_token"])
    record(
        results,
        "login",
        "passed",
        http_status=status,
        username=login.get("user", {}).get("username"),
        is_admin=login.get("user", {}).get("is_admin"),
    )

    sync_output = f"deploy_verify_sync_{args.run_id}"
    status, sync_result = request_json(
        "POST",
        f"{base_url}/api/loop-data/generate",
        token=token,
        payload={
            "level": "smoke",
            "loops": ["loop1"],
            "output_subdir": sync_output,
            "clean": True,
        },
        timeout=180,
    )
    require(status == 200, f"sync generation failed: {sync_result}")
    require(sync_result.get("case_count") == 6, "sync smoke case_count should be 6")
    require(sync_result.get("trace_task_id"), "sync generation missing trace_task_id")
    record(
        results,
        "sync_loop_data_generate",
        "passed",
        output_subdir=sync_output,
        case_count=sync_result.get("case_count"),
        trace_task_id=sync_result.get("trace_task_id"),
    )

    seed_subdir = args.seed_subdir or f"deploy_verify_raw_seed_{args.run_id}"
    seed_output = f"deploy_verify_seed_{args.run_id}"
    status, seed_result = request_json(
        "POST",
        f"{base_url}/api/loop-data/generate",
        token=token,
        payload={
            "level": "smoke",
            "loops": ["loop1"],
            "output_subdir": seed_output,
            "seed_subdir": seed_subdir,
            "adversarial_copies": 1,
            "clean": True,
        },
        timeout=180,
    )
    require(status == 200, f"seed/adversarial generation failed: {seed_result}")
    require(seed_result.get("case_count") == 12, "seed/adversarial case_count should be 12")
    local_seed_summary = seed_result.get("local_seed_summary") or {}
    adversarial = seed_result.get("adversarial") or {}
    adversarial_count = adversarial.get("mutated_count", adversarial.get("case_count"))
    require(local_seed_summary.get("seed_count", 0) >= 1, "local seed extractor should find raw seeds")
    require(adversarial_count == 6, "adversarial mutator should add 6 cases")
    record(
        results,
        "seed_and_adversarial_generate",
        "passed",
        output_subdir=seed_output,
        seed_subdir=seed_subdir,
        case_count=seed_result.get("case_count"),
        seed_count=local_seed_summary.get("seed_count"),
        mutated_count=adversarial_count,
        trace_task_id=seed_result.get("trace_task_id"),
    )

    trace_task_id = seed_result.get("trace_task_id")
    require(trace_task_id, "seed/adversarial generation missing trace_task_id")
    record(
        results,
        "trace_task_created_for_generation",
        "passed",
        trace_task_id=trace_task_id,
    )

    background_output = f"deploy_verify_background_{args.run_id}"
    status, background = request_json(
        "POST",
        f"{base_url}/api/loop-data/generate",
        token=token,
        payload={
            "level": "smoke",
            "loops": ["loop2"],
            "output_subdir": background_output,
            "seed_subdir": seed_subdir,
            "adversarial_copies": 1,
            "background": True,
            "clean": True,
        },
        timeout=60,
    )
    require(status in {200, 202}, f"background generation should enqueue: {background}")
    job_id = background.get("job_id")
    require(job_id, "background response missing job_id")
    record(
        results,
        "background_loop_data_generate_enqueue",
        "passed",
        job_id=job_id,
        trace_task_id=background.get("trace_task_id"),
    )

    job_result: dict[str, Any] = {}
    for _ in range(90):
        status, job_result = request_json("GET", f"{base_url}/api/jobs/{job_id}", token=token)
        require(status == 200, f"job query failed: {job_result}")
        if job_result.get("status") in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(2)
    require(job_result.get("status") == "succeeded", f"background job did not succeed: {job_result}")
    result_payload = job_result.get("result") or {}
    require(result_payload.get("case_count") == 6, "background result case_count should be 6")
    background_adversarial = result_payload.get("adversarial") or {}
    background_adversarial_count = background_adversarial.get(
        "mutated_count",
        background_adversarial.get("case_count"),
    )
    require(background_adversarial_count == 3, "background mutated count should be 3")
    record(
        results,
        "background_loop_data_generate_complete",
        "passed",
        job_id=job_id,
        case_count=result_payload.get("case_count"),
        seed_count=(result_payload.get("local_seed_summary") or {}).get("seed_count"),
        mutated_count=background_adversarial_count,
        output_subdir=background_output,
    )

    output["sync_result"] = {
        "output_subdir": sync_output,
        "trace_task_id": sync_result.get("trace_task_id"),
    }
    output["seed_result"] = {
        "output_subdir": seed_output,
        "seed_subdir": seed_subdir,
        "trace_task_id": seed_result.get("trace_task_id"),
    }
    output["background_result"] = {
        "output_subdir": background_output,
        "job_id": job_id,
    }

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
