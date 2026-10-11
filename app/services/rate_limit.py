from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from time import monotonic

from fastapi import HTTPException, status

WINDOW_SECONDS = 60

_lock = asyncio.Lock()


@dataclass
class _Bucket:
    timestamps: deque[float] = field(default_factory=deque)
    window_seconds: int = WINDOW_SECONDS


_buckets: dict[tuple[str, str], _Bucket] = {}
_last_cleanup_at = 0.0


def _remove_stale_buckets(now: float) -> None:
    global _last_cleanup_at
    if now - _last_cleanup_at < WINDOW_SECONDS:
        return

    for key, bucket in list(_buckets.items()):
        while bucket.timestamps and now - bucket.timestamps[0] >= bucket.window_seconds:
            bucket.timestamps.popleft()
        if not bucket.timestamps:
            _buckets.pop(key, None)
    _last_cleanup_at = now


async def enforce_rate_limit(
    session_id: str,
    bucket: str,
    *,
    limit: int,
    window_seconds: int = WINDOW_SECONDS,
) -> None:
    now = monotonic()
    key = (session_id, bucket)

    async with _lock:
        _remove_stale_buckets(now)
        state = _buckets.setdefault(key, _Bucket(window_seconds=window_seconds))
        state.window_seconds = window_seconds
        timestamps = state.timestamps
        while timestamps and now - timestamps[0] >= window_seconds:
            timestamps.popleft()

        if len(timestamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - timestamps[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)


async def clear_session_limits(session_id: str) -> None:
    async with _lock:
        for key in [key for key in _buckets if key[0] == session_id]:
            _buckets.pop(key, None)
