"""Phase 11 certification orchestration — research package + paper gates."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantfund.phase11.connectivity_status import BrokerConnectivityStatus
from quantfund.phase11.paper_gates import Phase11PaperCertificationGate, Phase11PaperGateDecision
from quantfund.paper.kill_switch import KillSwitch
from quantfund.paper.models import SessionMode
from quantfund.production.connectivity import run_zerodha_connectivity_test
from quantfund.production.preflight import PreflightContext, PreflightReport, run_preflight
from quantfund.research.certify_package import certify_research_package


@dataclass
class Phase11CertificationSnapshot:
    research_eligibility: str
    paper_eligible: bool
    connectivity: BrokerConnectivityStatus
    preflight_ok: bool
    live_orders: int = 0
    live_trading: str = "DISABLED"
    claims: str = "NONE"
    blockers: list[str] = field(default_factory=list)
    package_configured: bool = False
    gate: Phase11PaperGateDecision | None = None
    preflight: PreflightReport | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_eligibility": self.research_eligibility,
            "paper_eligible": self.paper_eligible,
            "connectivity": self.connectivity.value,
            "preflight_ok": self.preflight_ok,
            "live_orders": self.live_orders,
            "live_trading": self.live_trading,
            "claims": self.claims,
            "blockers": list(self.blockers),
            "package_configured": self.package_configured,
        }


def resolve_research_package(env: dict[str, str] | None = None) -> Path | None:
    e = env if env is not None else os.environ
    raw = (e.get("QUANTFUND_RESEARCH_PACKAGE") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.exists() else p  # existence checked by certify


def certify_phase11(
    *,
    env: dict[str, str] | None = None,
    strategy_enabled: bool = False,
    reconciliation_clean: bool = True,
    kill_switch: KillSwitch | None = None,
    session_mode: SessionMode = SessionMode.INFRASTRUCTURE_SANDBOX,
    simulate_connectivity: bool = True,
) -> Phase11CertificationSnapshot:
    """Certify research package (if configured) and evaluate paper gates.

    Never enables live trading. Never places orders.
    """
    env = env if env is not None else dict(os.environ)
    ks = kill_switch or KillSwitch()
    pkg = resolve_research_package(env)
    package_configured = bool((env.get("QUANTFUND_RESEARCH_PACKAGE") or "").strip())

    if package_configured and pkg is not None and pkg.exists():
        elig, facts, blockers, meta = certify_research_package(package_root=pkg)
    else:
        elig, facts, blockers, meta = certify_research_package(package_root=None)
        if not package_configured:
            blockers = list(blockers) or ["research_package_not_configured"]

    # Phase 11 certification default: never place orders; prefer simulated
    # connectivity unless explicitly requesting a real read-only probe.
    if simulate_connectivity:
        conn = run_zerodha_connectivity_test(env={}, simulate_if_unconfigured=True)
        connectivity = BrokerConnectivityStatus.SIMULATED
    else:
        conn = run_zerodha_connectivity_test(
            env=env, simulate_if_unconfigured=False
        )
        connectivity = (
            BrokerConnectivityStatus.CONNECTED_READ_ONLY
            if conn.configured and conn.ok
            else BrokerConnectivityStatus.SIMULATED
        )

    preflight = run_preflight(
        PreflightContext(
            env=env,
            kill_switch=ks,
            risk_limits_configured=True,
            reconciliation_clean=reconciliation_clean,
            research_eligibility=elig,
            paper_eligible=False,
            strategy_eligible=strategy_enabled,
            config_hashes={"phase11": "v1"},
            broker_health_connected=conn.authenticated,
        )
    )

    gate = Phase11PaperCertificationGate().evaluate(
        certified_eligibility=elig,
        connectivity=connectivity,
        kill_switch=ks,
        reconciliation_clean=reconciliation_clean,
        strategy_explicitly_enabled=strategy_enabled,
        session_mode=session_mode,
        facts=facts,
    )

    all_blockers = list(dict.fromkeys(list(blockers) + list(gate.blockers)))
    return Phase11CertificationSnapshot(
        research_eligibility=elig,
        paper_eligible=gate.paper_eligible,
        connectivity=connectivity,
        preflight_ok=preflight.ok,
        live_orders=0,
        live_trading="DISABLED",
        claims="NONE",
        blockers=all_blockers,
        package_configured=package_configured,
        gate=gate,
        preflight=preflight,
        meta={"certify_meta": meta, "connectivity": conn.to_dict()},
    )
