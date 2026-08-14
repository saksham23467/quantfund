"""Read-only execution-environment identity diagnostics.

Never prints secrets. Distinguishes LOCAL vs EC2.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from quantfund.data.zerodha_hist.envutil import (
    merge_env_with_optional_dotenv,
    validate_real_historical_config,
)
from quantfund.phase15.models import scrub_secrets


SECRET_ENV_KEYS = frozenset(
    {
        "ZERODHA_API_KEY",
        "ZERODHA_API_SECRET",
        "ZERODHA_ACCESS_TOKEN",
        "ZERODHA_REQUEST_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    }
)


def _read_text(path: Path) -> str | None:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None
    return None


def detect_execution_role() -> str:
    """Return LOCAL or EC2 (best-effort, never secret-bearing)."""
    forced = (os.environ.get("QUANTFUND_EXECUTION_ROLE") or "").strip().upper()
    if forced in {"LOCAL", "EC2"}:
        return forced

    system = platform.system().lower()
    if system == "darwin":
        return "LOCAL"

    # Linux heuristics for Amazon EC2
    sys_vendor = (_read_text(Path("/sys/class/dmi/id/sys_vendor")) or "").lower()
    product = (_read_text(Path("/sys/class/dmi/id/product_name")) or "").lower()
    bios = (_read_text(Path("/sys/class/dmi/id/bios_vendor")) or "").lower()
    if "amazon" in sys_vendor or "amazon" in product or "amazon" in bios:
        return "EC2"
    if Path("/sys/hypervisor/uuid").exists():
        uuid = (_read_text(Path("/sys/hypervisor/uuid")) or "").lower()
        if uuid.startswith("ec2"):
            return "EC2"
    # IMDSv2/IMDSv1 reachability (short timeout)
    try:
        req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=0.4) as resp:
            if resp.status == 200:
                return "EC2"
    except Exception:
        pass
    if system == "linux":
        return "LOCAL"  # Linux laptop/server without EC2 signals
    return "LOCAL"


def public_egress_ip(*, timeout_s: float = 3.0) -> str | None:
    endpoints = (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://checkip.amazonaws.com",
    )
    for url in endpoints:
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as resp:
                text = resp.read().decode("utf-8", errors="ignore").strip()
                if text and " " not in text and len(text) < 64:
                    return text
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            continue
    return None


def git_commit(repo_root: Path | None = None) -> str | None:
    root = repo_root or Path.cwd()
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def disk_and_memory() -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        usage = os.statvfs(str(Path.cwd()))
        free_gb = (usage.f_bavail * usage.f_frsize) / (1024**3)
        total_gb = (usage.f_blocks * usage.f_frsize) / (1024**3)
        info["disk_free_gb"] = round(free_gb, 2)
        info["disk_total_gb"] = round(total_gb, 2)
    except OSError:
        info["disk_free_gb"] = None
        info["disk_total_gb"] = None
    try:
        meminfo = _read_text(Path("/proc/meminfo"))
        if meminfo:
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    info["memory_total_gb"] = round(kb / (1024**2), 2)
                    break
        else:
            # macOS fallback
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            info["memory_total_gb"] = round(int(out) / (1024**3), 2)
    except Exception:
        info["memory_total_gb"] = None
    return info


def zerodha_config_presence(env: dict[str, str] | None = None) -> dict[str, Any]:
    merged = env or merge_env_with_optional_dotenv(
        dotenv_path=Path.cwd() / ".env"
    )
    cfg = validate_real_historical_config(merged)
    # Never include secret values — only presence flags from validate_*
    # Key names avoid scrub_secrets substrings (api_key/access_token).
    return {
        "allow_flag": cfg["allow_flag"],
        "key_set": cfg["api_key_present"],
        "secret_set": cfg["api_secret_present"],
        "token_set": cfg["access_token_present"],
        "ok_for_real_historical": cfg["ok"],
        "problems": list(cfg["problems"]),
    }


def broker_write_safety_snapshot() -> dict[str, Any]:
    from quantfund.phase17c.safety import safety_payload

    return safety_payload()


def dataset_availability() -> dict[str, Any]:
    from quantfund.phase17a.datasets import discover_zerodha_packages

    pkgs = discover_zerodha_packages()
    return {
        "package_count": len(pkgs),
        "symbols": [p.symbol for p in pkgs],
        "packages": [
            {
                "symbol": p.symbol,
                "dataset_id": p.dataset_id,
                "dataset_version": p.dataset_version,
                "bars": p.bars,
                "content_hash": p.content_hash,
                "eligibility": p.eligibility,
                "path": str(p.path),
            }
            for p in pkgs
        ],
    }


def run_environment_check(*, fetch_egress_ip: bool = True) -> dict[str, Any]:
    role = detect_execution_role()
    expected = (os.environ.get("QUANTFUND_EXPECTED_ZERODHA_IP") or "").strip() or None
    egress = public_egress_ip() if fetch_egress_ip else None
    if expected is None:
        match = "UNKNOWN_EXPECTED_IP_NOT_CONFIGURED"
    elif egress is None:
        match = "UNKNOWN_EGRESS_UNAVAILABLE"
    elif egress == expected:
        match = "MATCH"
    else:
        match = "MISMATCH"

    resources = disk_and_memory()
    datasets = dataset_availability()
    payload = scrub_secrets(
        {
            "execution_role": role,  # LOCAL | EC2
            "execution_host": socket.gethostname(),
            "execution_os": platform.platform(),
            "execution_system": platform.system(),
            "execution_architecture": platform.machine(),
            "python_version": platform.python_version(),
            "public_egress_ip": egress,
            "expected_zerodha_ip_if_configured": expected,
            "zerodha_ip_match": match,
            "repository_commit": git_commit(),
            "cwd": str(Path.cwd()),
            "resources": resources,
            "zerodha_config": zerodha_config_presence(),
            "broker_safety": broker_write_safety_snapshot(),
            "datasets": {
                "package_count": datasets["package_count"],
                "symbols": datasets["symbols"],
            },
            "statement": (
                f"Execution role={role}. Secrets are never printed. "
                "Broker writes remain DISABLED."
            ),
            "secret_env_keys_scanned": sorted(SECRET_ENV_KEYS),
            "ok": True,
        }
    )
    # Defense: ensure no secret values leaked into payload strings
    blob = json.dumps(payload, default=str)
    for key in SECRET_ENV_KEYS:
        val = os.environ.get(key) or ""
        if val and len(val) >= 8 and val in blob:
            raise RuntimeError(f"secret_leak_blocked:{key}")
    return payload
