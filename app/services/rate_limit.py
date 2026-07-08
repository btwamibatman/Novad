from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, status

WINDOW_SECONDS = 60

_lock = asyncio.Lock()
_buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)


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
        timestamps = _buckets[key]
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
