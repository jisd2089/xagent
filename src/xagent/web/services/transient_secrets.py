from __future__ import annotations

import secrets

from ...config import get_redis_url


DEFAULT_SECRET_TTL_SECONDS = 3600
SECRET_PREFIX = "xagent:transient-secret:"


def stash_transient_secret(
    secret: str,
    *,
    namespace: str,
    ttl_seconds: int = DEFAULT_SECRET_TTL_SECONDS,
) -> str:
    if not secret:
        raise ValueError("secret is required")
    client = _redis_client()
    ref = f"{namespace}:{secrets.token_urlsafe(24)}"
    client.setex(_redis_key(ref), max(1, int(ttl_seconds)), secret)
    return ref


def pop_transient_secret(ref: str) -> str:
    if not ref:
        raise ValueError("secret reference is required")
    client = _redis_client()
    key = _redis_key(ref)
    pipeline = client.pipeline()
    pipeline.get(key)
    pipeline.delete(key)
    value, _deleted = pipeline.execute()
    if value is None:
        raise ValueError("transient secret is missing or expired")
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def get_transient_secret(ref: str) -> str:
    if not ref:
        raise ValueError("secret reference is required")
    value = _redis_client().get(_redis_key(ref))
    if value is None:
        raise ValueError("transient secret is missing or expired")
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def delete_transient_secret(ref: str) -> None:
    if not ref:
        return
    _redis_client().delete(_redis_key(ref))


def _redis_key(ref: str) -> str:
    return SECRET_PREFIX + ref


def _redis_client():
    redis_url = get_redis_url()
    if not redis_url:
        raise RuntimeError("XAGENT_REDIS_URL is required for transient secrets")
    import redis  # type: ignore[import-not-found]

    return redis.Redis.from_url(redis_url)
