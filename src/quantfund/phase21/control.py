"""Process control files for autonomous Phase 21 daemon."""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_runtime_dir(root: Path | None = None) -> Path:
    root = root or Path.cwd()
    return root / "experiments" / "phase21" / "runtime"


def write_status(runtime_dir: Path, payload: dict[str, Any]) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        **payload,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "LIVE_TRADING": "DISABLED",
        "BROKER_WRITE": "DISABLED",
        "PAPER_TRADING": "ENABLED",
        "KILL_SWITCH": payload.get("KILL_SWITCH", "ARMED"),
    }
    (runtime_dir / "status.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )


def read_status(runtime_dir: Path | None = None) -> dict[str, Any]:
    runtime_dir = runtime_dir or default_runtime_dir()
    path = runtime_dir / "status.json"
    if not path.exists():
        return {"running": False, "detail": "no_status_file"}
    return json.loads(path.read_text(encoding="utf-8"))


def write_heartbeat(runtime_dir: Path, *, seq: int = 0) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "heartbeat.json").write_text(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "seq": seq,
                "alive": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def request_stop(runtime_dir: Path | None = None) -> None:
    runtime_dir = runtime_dir or default_runtime_dir()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "STOP").write_text("1\n", encoding="utf-8")
    pid_path = runtime_dir / "pid"
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            os.kill(pid, signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError):
            pass


def clear_stop(runtime_dir: Path) -> None:
    stop = runtime_dir / "STOP"
    if stop.exists():
        stop.unlink()


def stop_requested(runtime_dir: Path) -> bool:
    return (runtime_dir / "STOP").exists()


def write_pid(runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")


def wait_idle(runtime_dir: Path, *, timeout_s: float = 5.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = read_status(runtime_dir)
        if not st.get("running"):
            return True
        time.sleep(0.1)
    return False
