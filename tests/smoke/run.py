"""Isolated Docker smoke test; uses only Python's standard library on the host."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = [
    "docker", "compose", "--project-name", "novad-docker-smoke",
    "--env-file", "tests/smoke/compose.env",
    "-f", "docker-compose.yml", "-f", "tests/smoke/compose.yml",
]


def compose(*args, capture=False, timeout=120):
    return subprocess.run(
        [*COMPOSE, *args], cwd=ROOT, check=True, text=True,
        stdout=subprocess.PIPE if capture else None, timeout=timeout,
    )


def wait_healthy(timeout: int) -> None:
    deadline = time.monotonic() + timeout
    states = {}
    while time.monotonic() < deadline:
        states = {}
        for service in ("db", "api", "analysis-worker"):
            container_id = compose("ps", "--all", "--quiet", service, capture=True).stdout.strip()
            if not container_id:
                states[service] = "missing"
                continue
            state = json.loads(subprocess.check_output(
                ["docker", "inspect", "--format", "{{json .State}}", container_id],
                text=True, timeout=10,
            ))
            states[service] = state.get("Health", {}).get("Status", state["Status"])
            if state["Status"] != "running":
                raise RuntimeError(f"{service} is {state['Status']}")
        if all(state == "healthy" for state in states.values()):
            print(f"PASS: all services healthy: {states}", flush=True)
            return
        time.sleep(2)
    raise TimeoutError(f"Readiness timed out after {timeout}s: {states}")


def expect_processing_failure() -> None:
    try:
        compose("exec", "-T", "api", "python", "-m", "smoke.check", "--timeout", "10")
    except subprocess.CalledProcessError as error:
        if error.returncode != 2:
            raise
        compose("logs", "--no-color", "--tail", "20")
        print("PASS: smoke fails without a working worker", flush=True)
        return
    raise RuntimeError("Smoke unexpectedly passed without a working worker")


def verify_failures() -> None:
    # SIGSTOP freezes PID 1 but leaves Docker's separate probe processes running.
    compose("kill", "--signal", "SIGSTOP", "analysis-worker")
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = json.loads(compose("ps", "--format", "json", "analysis-worker", capture=True).stdout)
            if state["Health"] == "unhealthy":
                print("PASS: frozen worker becomes unhealthy", flush=True)
                break
            time.sleep(2)
        else:
            raise TimeoutError("Frozen worker did not become unhealthy")
        expect_processing_failure()
    finally:
        compose("kill", "--signal", "SIGCONT", "analysis-worker")
    wait_healthy(90)

    compose("stop", "analysis-worker")
    try:
        try:
            wait_healthy(10)
        except RuntimeError:
            print("PASS: stopped worker fails readiness (container is exited)", flush=True)
        else:
            raise RuntimeError("Stopped worker unexpectedly passed readiness")
        expect_processing_failure()
    finally:
        compose("start", "analysis-worker")
    wait_healthy(90)

    compose("stop", "db")
    try:
        compose("exec", "-T", "api", "python", "-m", "smoke.check", "--database-outage")
    finally:
        compose("start", "db")
    wait_healthy(90)
    compose("exec", "-T", "api", "python", "-m", "smoke.check")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--ready-timeout", type=int, default=180)
    parser.add_argument("--verify-failures", action="store_true")
    args = parser.parse_args()
    result = 0
    try:
        if not args.skip_build:
            compose("build", "api", timeout=1800)
        compose("up", "-d", "--wait", "--wait-timeout", "90", "db")
        compose("run", "--rm", "--no-deps", "-T", "--user", "0", "api", "python", "-c",
                "import os,pwd; from app.core.database import init_db; init_db(); "
                "u=pwd.getpwnam('appuser'); os.chown('/app/storage',u.pw_uid,u.pw_gid)")
        compose("run", "--rm", "--no-deps", "-T", "api", "alembic", "upgrade", "head")
        compose("up", "-d", "api", "analysis-worker")
        wait_healthy(args.ready_timeout)
        compose("exec", "-T", "api", "python", "-m", "smoke.check")
        if args.verify_failures:
            verify_failures()
    except (subprocess.SubprocessError, RuntimeError, TimeoutError) as error:
        print(f"FAIL: {error}", file=sys.stderr, flush=True)
        result = 1
        try:
            compose("logs", "--no-color", timeout=30)
        except subprocess.SubprocessError as log_error:
            print(f"Could not read container logs: {log_error}", file=sys.stderr)
    finally:
        try:
            compose("down", "-v", "--remove-orphans", timeout=90)
        except subprocess.SubprocessError as cleanup_error:
            print(f"Cleanup failed: {cleanup_error}", file=sys.stderr)
            result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
