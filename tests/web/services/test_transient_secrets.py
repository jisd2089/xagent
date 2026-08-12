from __future__ import annotations

import pytest

from xagent.web.services import transient_secrets


class FakePipeline:
    def __init__(self, client: "FakeRedisClient") -> None:
        self.client = client
        self.commands: list[tuple[str, str]] = []

    def get(self, key: str) -> None:
        self.commands.append(("get", key))

    def delete(self, key: str) -> None:
        self.commands.append(("delete", key))

    def execute(self) -> list[object]:
        results: list[object] = []
        for command, key in self.commands:
            if command == "get":
                results.append(self.client.values.get(key))
            elif command == "delete":
                results.append(1 if self.client.values.pop(key, None) is not None else 0)
        return results


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def setex(self, key: str, _ttl_seconds: int, value: str) -> None:
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


def test_get_transient_secret_does_not_consume(monkeypatch) -> None:
    fake_client = FakeRedisClient()
    monkeypatch.setattr(transient_secrets, "_redis_client", lambda: fake_client)
    monkeypatch.setattr(transient_secrets.secrets, "token_urlsafe", lambda _n: "token")

    ref = transient_secrets.stash_transient_secret(
        "runtime-key",
        namespace="loop-eval-api-key",
        ttl_seconds=60,
    )

    assert ref == "loop-eval-api-key:token"
    assert transient_secrets.get_transient_secret(ref) == "runtime-key"
    assert transient_secrets.get_transient_secret(ref) == "runtime-key"

    transient_secrets.delete_transient_secret(ref)
    with pytest.raises(ValueError, match="missing or expired"):
        transient_secrets.get_transient_secret(ref)


def test_pop_transient_secret_consumes(monkeypatch) -> None:
    fake_client = FakeRedisClient()
    monkeypatch.setattr(transient_secrets, "_redis_client", lambda: fake_client)
    monkeypatch.setattr(transient_secrets.secrets, "token_urlsafe", lambda _n: "token")

    ref = transient_secrets.stash_transient_secret(
        "runtime-key",
        namespace="loop-eval-api-key",
    )

    assert transient_secrets.pop_transient_secret(ref) == "runtime-key"
    with pytest.raises(ValueError, match="missing or expired"):
        transient_secrets.pop_transient_secret(ref)
