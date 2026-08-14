"""Health endpoint + heartbeat for Phase 19 EC2 paper service."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable


@dataclass
class Phase19Health:
    status: str = "STARTING"
    heartbeat_at: str | None = None
    market_data_ok: bool = True
    stale_data: bool = False
    kill_switch: str = "ARMED"
    reconciliation_ok: bool = True
    allows_new_paper_orders: bool = True
    live_trading: str = "DISABLED"
    real_broker_orders: int = 0
    paper_orders: int = 0
    paper_fills: int = 0
    session_id: str = ""
    detail: list[str] = field(default_factory=list)

    def beat(self) -> None:
        self.heartbeat_at = datetime.now(timezone.utc).isoformat()
        if self.status == "STARTING":
            self.status = "OK"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "heartbeat_at": self.heartbeat_at,
            "market_data_ok": self.market_data_ok,
            "stale_data": self.stale_data,
            "kill_switch": self.kill_switch,
            "reconciliation_ok": self.reconciliation_ok,
            "allows_new_paper_orders": self.allows_new_paper_orders,
            "live_trading": self.live_trading,
            "real_broker_orders": self.real_broker_orders,
            "paper_orders": self.paper_orders,
            "paper_fills": self.paper_fills,
            "session_id": self.session_id,
            "detail": list(self.detail),
            "secrets_exposed": False,
        }


class _HealthHandler(BaseHTTPRequestHandler):
    health_fn: Callable[[], dict[str, Any]] = staticmethod(lambda: {"status": "OK"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return  # quiet

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/health", "/healthz", "/heartbeat"):
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(self.health_fn(), sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_health_server(
    health: Phase19Health,
    *,
    host: str = "127.0.0.1",
    port: int = 8719,
) -> tuple[HTTPServer, threading.Thread]:
    """Bind loopback-only health server (no secrets)."""

    def snapshot() -> dict[str, Any]:
        health.beat()
        return health.to_dict()

    handler = type(
        "Phase19HealthHandler",
        (_HealthHandler,),
        {"health_fn": staticmethod(snapshot)},
    )
    server = HTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="p19-health")
    thread.start()
    return server, thread


def stop_health_server(server: HTTPServer | None) -> None:
    if server is not None:
        server.shutdown()
