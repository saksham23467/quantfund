"""EC2 preflight checks — fail closed; never print secrets."""

from __future__ import annotations

import importlib
import platform
import sys
from pathlib import Path
from typing import Any

from quantfund.deploy.environment import (
    broker_write_safety_snapshot,
    dataset_availability,
    detect_execution_role,
    disk_and_memory,
    git_commit,
    public_egress_ip,
    run_environment_check,
    zerodha_config_presence,
)
from quantfund.phase15.models import scrub_secrets

REQUIRED_PACKAGES = (
    "pandas",
    "numpy",
    "pydantic",
    "pyarrow",
    "exchange_calendars",
    "pytest",
)


def run_ec2_preflight(*, require_ec2: bool = True) -> dict[str, Any]:
    role = detect_execution_role()
    problems: list[str] = []
    warnings: list[str] = []

    if require_ec2 and role != "EC2":
        problems.append(f"execution_role_not_ec2:{role}")
    if platform.system().lower() != "linux" and require_ec2:
        problems.append(f"os_not_linux:{platform.system()}")

    py = sys.version_info
    if py < (3, 12):
        problems.append(f"python_below_3_12:{platform.python_version()}")

    missing_pkgs: list[str] = []
    for name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(name)
        except ImportError:
            missing_pkgs.append(name)
    if missing_pkgs:
        problems.append(f"missing_packages:{','.join(missing_pkgs)}")

    resources = disk_and_memory()
    free = resources.get("disk_free_gb")
    mem = resources.get("memory_total_gb")
    if free is not None and free < 2.0:
        problems.append(f"disk_free_gb_low:{free}")
    if mem is not None and mem < 1.0:
        warnings.append(f"memory_total_gb_low:{mem}")

    egress = public_egress_ip()
    if egress is None:
        warnings.append("public_egress_ip_unavailable")

    zcfg = zerodha_config_presence()
    if not zcfg["ok_for_real_historical"]:
        # Presence check only — real API call is separate
        warnings.extend([f"zerodha_config:{p}" for p in zcfg["problems"]])

    datasets = dataset_availability()
    if datasets["package_count"] == 0:
        problems.append("no_zerodha_research_packages_found")

    safety = broker_write_safety_snapshot()
    if not safety.get("ok"):
        problems.append("broker_write_safety_failed")
    if safety.get("broker_write_capability") != "DISABLED":
        problems.append("broker_write_capability_not_disabled")
    if safety.get("live_trading") != "DISABLED":
        problems.append("live_trading_not_disabled")
    if safety.get("paper_trading") != "NOT_STARTED":
        problems.append("paper_trading_not_not_started")
    if int(safety.get("place_order_called") or 0) != 0:
        problems.append("place_order_called_nonzero")
    if int(safety.get("orders_submitted") or 0) != 0:
        problems.append("orders_submitted_nonzero")

    env = run_environment_check(fetch_egress_ip=False)
    env["public_egress_ip"] = egress

    ok = len(problems) == 0
    return scrub_secrets(
        {
            "ok": ok,
            "result": "PASS" if ok else "FAIL",
            "execution_role": role,
            "execution_os": platform.platform(),
            "python_version": platform.python_version(),
            "repository_commit": git_commit(),
            "public_egress_ip": egress,
            "zerodha_ip_match": env.get("zerodha_ip_match"),
            "expected_zerodha_ip_if_configured": env.get(
                "expected_zerodha_ip_if_configured"
            ),
            "resources": resources,
            "zerodha_config": zcfg,
            "datasets": {
                "package_count": datasets["package_count"],
                "symbols": datasets["symbols"],
                "hashes": [
                    {
                        "symbol": p["symbol"],
                        "dataset_id": p["dataset_id"],
                        "dataset_version": p["dataset_version"],
                        "content_hash": p["content_hash"],
                    }
                    for p in datasets["packages"]
                ],
            },
            "broker_safety": safety,
            "problems": problems,
            "warnings": warnings,
            "statement": (
                "EC2 preflight only. No broker order submission. "
                "NO PAPER OR LIVE TRADING WAS STARTED."
            ),
            "cwd": str(Path.cwd()),
        }
    )
