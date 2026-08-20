"""Distributed locks: SET NX PX acquire, Lua compare-and-delete release -
concurrency guards only, never the source of truth for business state (see
docs/architecture.md Redis section). A status column alone (e.g.
imports.status = 'VALIDATING') cannot distinguish "a live worker is
actively processing this right now" from "a worker died mid-process and
left it here" - that's exactly what these locks are for.

Caught live during Phase 2 real-scale testing: two concurrent
commit_import() calls for the same import both passed a naive status check
(TOCTOU under READ COMMITTED) and ran concurrently until one blocked on a
row lock. This module plus the with-blocks in app.workers.ingestion_worker
are the fix - see docs/decisions.md.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import redis

from app.core.config import get_settings

settings = get_settings()

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=settings.redis_host, port=settings.redis_port, db=settings.redis_db
        )
    return _client


class LockNotAcquired(Exception):
    pass


@contextmanager
def distributed_lock(key: str, ttl_seconds: int = 1800) -> Iterator[None]:
    """Raises LockNotAcquired immediately if the lock is already held
    (never blocks waiting) - callers treat "someone else has this" as
    "nothing to do right now", not an error to retry against. TTL is a
    safety net for a crashed holder, not the primary release mechanism
    (the `finally` block below releases explicitly on the success path)."""
    client = _get_client()
    token = uuid.uuid4().hex
    acquired = client.set(key, token, nx=True, ex=ttl_seconds)
    if not acquired:
        raise LockNotAcquired(key)
    try:
        yield
    finally:
        client.eval(_RELEASE_SCRIPT, 1, key, token)
