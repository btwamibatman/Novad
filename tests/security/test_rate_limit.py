import asyncio

from app.services import rate_limit


def test_rate_limiter_removes_inactive_client_buckets(monkeypatch):
    now = [1.0]
    monkeypatch.setattr(rate_limit, "monotonic", lambda: now[0])
    monkeypatch.setattr(rate_limit, "_last_cleanup_at", 0.0)

    asyncio.run(rate_limit.enforce_rate_limit("login:old-client", "auth", limit=5))
    assert ("login:old-client", "auth") in rate_limit._buckets

    now[0] = 62.0
    asyncio.run(rate_limit.enforce_rate_limit("login:new-client", "auth", limit=5))

    assert ("login:old-client", "auth") not in rate_limit._buckets
    assert ("login:new-client", "auth") in rate_limit._buckets


def test_rate_limiter_keeps_buckets_with_a_longer_active_window(monkeypatch):
    now = [1.0]
    monkeypatch.setattr(rate_limit, "monotonic", lambda: now[0])
    monkeypatch.setattr(rate_limit, "_last_cleanup_at", 0.0)

    asyncio.run(
        rate_limit.enforce_rate_limit(
            "long-window-client", "custom", limit=5, window_seconds=120
        )
    )

    now[0] = 62.0
    asyncio.run(rate_limit.enforce_rate_limit("login:new-client", "auth", limit=5))

    assert ("long-window-client", "custom") in rate_limit._buckets
