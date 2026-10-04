import os

from app import worker_health


def test_missing_stale_and_future_heartbeats_fail(tmp_path, monkeypatch):
    path = tmp_path / "heartbeat"
    monkeypatch.setattr(worker_health.time, "time", lambda: 100)
    assert not worker_health.heartbeat_is_fresh(path)
    path.touch()
    for value in (39, 101):
        os.utime(path, (value, value))
        assert not worker_health.heartbeat_is_fresh(path)
    os.utime(path, (40, 40))
    assert worker_health.heartbeat_is_fresh(path)


def test_heartbeat_refreshes_while_worker_is_busy_and_cleans_up(tmp_path, monkeypatch):
    path = tmp_path / "heartbeat"
    monkeypatch.setattr(worker_health, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    with worker_health.worker_heartbeat(path):
        initial = path.stat().st_mtime_ns
        deadline = worker_health.time.monotonic() + 2
        while path.stat().st_mtime_ns == initial:
            assert worker_health.time.monotonic() < deadline
            worker_health.time.sleep(0.01)
        assert worker_health.heartbeat_is_fresh(path)
    assert not path.exists()
