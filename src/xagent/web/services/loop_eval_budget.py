from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ...config import get_redis_url
from ..models.loop_eval import SelectionEvalBudgetStat


LOCK_PREFIX = "xagent:loop-eval:active:"
STATS_KEY = "xagent:loop-eval:budget:totals"
DB_COUNTER_FIELDS = {
    "jobs_started",
    "jobs_rejected_budget",
    "jobs_rejected_concurrency",
    "jobs_succeeded",
    "jobs_failed",
    "new_tasks_planned",
    "new_tasks_completed",
}


class LoopEvalConcurrencyError(RuntimeError):
    pass


@dataclass
class LoopEvalBudgetLease:
    client: Any
    lock_key: str | None
    token: str | None
    scope: str
    new_task_count: int

    @property
    def acquired(self) -> bool:
        return bool(self.lock_key and self.token)

    def release(self, *, status: str, completed_new_tasks: int = 0) -> None:
        if not self.acquired:
            return

        if status == "succeeded":
            self.client.hincrby(STATS_KEY, "jobs_succeeded", 1)
            self.client.hincrby(STATS_KEY, "new_tasks_completed", max(0, completed_new_tasks))
        elif status == "failed":
            self.client.hincrby(STATS_KEY, "jobs_failed", 1)

        current = self.client.get(self.lock_key)
        if _decode(current) == self.token:
            self.client.delete(self.lock_key)


def acquire_loop_eval_budget_lease(
    *,
    job_id: str,
    new_task_count: int,
    ttl_seconds: int,
    scope: str = "agent31",
) -> LoopEvalBudgetLease:
    client = _redis_client()
    normalized_new_task_count = max(0, int(new_task_count))
    if normalized_new_task_count <= 0:
        return LoopEvalBudgetLease(
            client=client,
            lock_key=None,
            token=None,
            scope=scope,
            new_task_count=0,
        )

    token = f"{job_id}:{secrets.token_urlsafe(12)}"
    lock_key = LOCK_PREFIX + scope
    acquired = client.set(
        lock_key,
        token,
        nx=True,
        ex=max(60, int(ttl_seconds)),
    )
    if not acquired:
        client.hincrby(STATS_KEY, "jobs_rejected_concurrency", 1)
        active = _decode(client.get(lock_key)) or "unknown"
        raise LoopEvalConcurrencyError(
            f"Loop eval real-task scope {scope!r} is already running: {active}"
        )

    client.hincrby(STATS_KEY, "jobs_started", 1)
    client.hincrby(STATS_KEY, "new_tasks_planned", normalized_new_task_count)
    return LoopEvalBudgetLease(
        client=client,
        lock_key=lock_key,
        token=token,
        scope=scope,
        new_task_count=normalized_new_task_count,
    )


def get_loop_eval_budget_status() -> dict[str, Any]:
    redis_url = get_redis_url()
    if not redis_url:
        return {
            "available": False,
            "reason": "XAGENT_REDIS_URL is not configured",
            "active": [],
            "totals": {},
        }
    client = _redis_client()
    active = []
    for raw_key in client.keys(LOCK_PREFIX + "*"):
        key = _decode(raw_key) or str(raw_key)
        scope = key.removeprefix(LOCK_PREFIX)
        active.append(
            {
                "scope": scope,
                "job": _decode(client.get(key)),
                "ttl_seconds": client.ttl(key),
            }
        )
    raw_totals = client.hgetall(STATS_KEY)
    totals = {
        _decode(key) or str(key): int(_decode(value) or 0)
        for key, value in raw_totals.items()
    }
    return {
        "available": True,
        "active": sorted(active, key=lambda item: str(item["scope"])),
        "totals": totals,
    }


def record_loop_eval_budget_counters(
    db: Session,
    *,
    user_id: int,
    scope: str,
    counters: dict[str, int],
    job_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SelectionEvalBudgetStat:
    stat = (
        db.query(SelectionEvalBudgetStat)
        .filter(
            SelectionEvalBudgetStat.user_id == user_id,
            SelectionEvalBudgetStat.scope == scope,
        )
        .first()
    )
    if stat is None:
        stat = SelectionEvalBudgetStat(user_id=user_id, scope=scope)
        db.add(stat)

    for field, value in counters.items():
        if field not in DB_COUNTER_FIELDS:
            continue
        setattr(stat, field, int(getattr(stat, field) or 0) + max(0, int(value)))
    if job_id:
        stat.last_job_id = job_id
    if metadata:
        existing = stat.metadata_json if isinstance(stat.metadata_json, dict) else {}
        stat.metadata_json = {**existing, **metadata}
    db.commit()
    db.refresh(stat)
    return stat


def get_loop_eval_budget_db_status(
    db: Session,
    *,
    user_id: int,
) -> dict[str, Any]:
    rows = (
        db.query(SelectionEvalBudgetStat)
        .filter(SelectionEvalBudgetStat.user_id == user_id)
        .order_by(SelectionEvalBudgetStat.scope.asc())
        .all()
    )
    totals = {field: 0 for field in sorted(DB_COUNTER_FIELDS)}
    scopes: list[dict[str, Any]] = []
    for row in rows:
        item = serialize_loop_eval_budget_stat(row)
        scopes.append(item)
        for field in DB_COUNTER_FIELDS:
            totals[field] += int(item[field] or 0)
    return {
        "scopes": scopes,
        "totals": totals,
    }


def serialize_loop_eval_budget_stat(row: SelectionEvalBudgetStat) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "scope": row.scope,
        "jobs_started": int(row.jobs_started or 0),
        "jobs_rejected_budget": int(row.jobs_rejected_budget or 0),
        "jobs_rejected_concurrency": int(row.jobs_rejected_concurrency or 0),
        "jobs_succeeded": int(row.jobs_succeeded or 0),
        "jobs_failed": int(row.jobs_failed or 0),
        "new_tasks_planned": int(row.new_tasks_planned or 0),
        "new_tasks_completed": int(row.new_tasks_completed or 0),
        "last_job_id": row.last_job_id,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _redis_client():
    redis_url = get_redis_url()
    if not redis_url:
        raise RuntimeError("XAGENT_REDIS_URL is required for loop eval budget control")
    import redis  # type: ignore[import-not-found]

    return redis.Redis.from_url(redis_url)


def _decode(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
