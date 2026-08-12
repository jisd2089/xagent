from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from xagent.web import models as _models  # noqa: F401
from xagent.web.models.database import Base
from xagent.web.services import loop_eval_budget


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, int]] = {}
        self.ttls: dict[str, int] = {}

    def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        self.ttls.pop(key, None)
        return 1 if existed else 0

    def hincrby(self, key: str, field: str, amount: int) -> int:
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = bucket.get(field, 0) + int(amount)
        return bucket[field]

    def hgetall(self, key: str) -> dict[str, str]:
        return {field: str(value) for field, value in self.hashes.get(key, {}).items()}

    def keys(self, pattern: str) -> list[str]:
        prefix = pattern.removesuffix("*")
        return [key for key in self.values if key.startswith(prefix)]

    def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)


@pytest.fixture()
def fake_redis(monkeypatch) -> FakeRedisClient:
    client = FakeRedisClient()
    monkeypatch.setattr(loop_eval_budget, "_redis_client", lambda: client)
    monkeypatch.setattr(loop_eval_budget, "get_redis_url", lambda: "redis://redis:6379/0")
    monkeypatch.setattr(loop_eval_budget.secrets, "token_urlsafe", lambda _n: "token")
    return client


def test_loop_eval_budget_lease_tracks_active_job_and_release(fake_redis) -> None:
    lease = loop_eval_budget.acquire_loop_eval_budget_lease(
        job_id="job-a",
        new_task_count=2,
        ttl_seconds=30,
        scope="agent-31",
    )

    assert lease.acquired is True
    assert loop_eval_budget.get_loop_eval_budget_status() == {
        "available": True,
        "active": [
            {
                "scope": "agent-31",
                "job": "job-a:token",
                "ttl_seconds": 60,
            }
        ],
        "totals": {
            "jobs_started": 1,
            "new_tasks_planned": 2,
        },
    }

    lease.release(status="succeeded", completed_new_tasks=2)

    assert loop_eval_budget.get_loop_eval_budget_status() == {
        "available": True,
        "active": [],
        "totals": {
            "jobs_started": 1,
            "new_tasks_planned": 2,
            "jobs_succeeded": 1,
            "new_tasks_completed": 2,
        },
    }


def test_loop_eval_budget_lease_rejects_concurrent_real_task_job(fake_redis) -> None:
    loop_eval_budget.acquire_loop_eval_budget_lease(
        job_id="job-a",
        new_task_count=1,
        ttl_seconds=120,
        scope="agent-31",
    )

    with pytest.raises(loop_eval_budget.LoopEvalConcurrencyError, match="already running"):
        loop_eval_budget.acquire_loop_eval_budget_lease(
            job_id="job-b",
            new_task_count=1,
            ttl_seconds=120,
            scope="agent-31",
        )

    assert loop_eval_budget.get_loop_eval_budget_status()["totals"] == {
        "jobs_started": 1,
        "new_tasks_planned": 1,
        "jobs_rejected_concurrency": 1,
    }


def test_loop_eval_budget_noop_for_reuse_only_jobs(fake_redis) -> None:
    lease = loop_eval_budget.acquire_loop_eval_budget_lease(
        job_id="job-a",
        new_task_count=0,
        ttl_seconds=120,
        scope="agent-31",
    )

    lease.release(status="succeeded", completed_new_tasks=0)

    assert lease.acquired is False
    assert loop_eval_budget.get_loop_eval_budget_status() == {
        "available": True,
        "active": [],
        "totals": {},
    }


def test_loop_eval_budget_db_counters_are_durable_by_scope() -> None:
    db = _session()

    loop_eval_budget.record_loop_eval_budget_counters(
        db,
        user_id=1,
        scope="agent-31",
        counters={"jobs_started": 1, "new_tasks_planned": 2},
        job_id="job-a",
    )
    loop_eval_budget.record_loop_eval_budget_counters(
        db,
        user_id=1,
        scope="agent-31",
        counters={"jobs_succeeded": 1, "new_tasks_completed": 2},
        job_id="job-a",
        metadata={"mode": "background"},
    )

    status = loop_eval_budget.get_loop_eval_budget_db_status(db, user_id=1)

    assert status["totals"]["jobs_started"] == 1
    assert status["totals"]["jobs_succeeded"] == 1
    assert status["totals"]["new_tasks_planned"] == 2
    assert status["totals"]["new_tasks_completed"] == 2
    assert status["scopes"][0]["scope"] == "agent-31"
    assert status["scopes"][0]["last_job_id"] == "job-a"
    assert status["scopes"][0]["metadata"] == {"mode": "background"}


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
