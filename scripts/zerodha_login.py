#!/usr/bin/env python3
"""Local Zerodha Kite login helper — obtains access_token, never prints secrets.

Usage:
  1. Put ZERODHA_API_KEY and ZERODHA_API_SECRET in gitignored .env
  2. Set Kite app Redirect URL to: http://127.0.0.1:8000/zerodha/callback
  3. Run:  make zerodha-login
  4. Open the printed login URL, complete Zerodha login
  5. This server catches the callback, exchanges request_token, writes
     ZERODHA_ACCESS_TOKEN into .env

Does NOT place orders. Does NOT print api_secret / access_token / request_token.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.brokers.zerodha.auth import (  # noqa: E402
    ZerodhaCredentials,
    ZerodhaEnv,
    load_credentials_from_env,
    parse_zerodha_env,
)
from quantfund.brokers.zerodha.client import KiteClient, UrllibKiteTransport  # noqa: E402
from quantfund.data.zerodha_hist.envutil import merge_env_with_optional_dotenv  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
CALLBACK_PATH = "/zerodha/callback"


def _upsert_env_key(env_path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    found = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _exchange(request_token: str, env: dict[str, str]) -> str:
    creds = load_credentials_from_env(env)
    if creds is None:
        raise SystemExit(
            "Missing ZERODHA_API_KEY / ZERODHA_API_SECRET in environment or .env"
        )
    # Session exchange uses production host for real Kite Connect apps unless sandbox.
    zenv = parse_zerodha_env(env.get("ZERODHA_ENV"))
    if (env.get("ZERODHA_ENV") or "").strip().lower() in {"", "paper"}:
        zenv = ZerodhaEnv.PRODUCTION
    creds = ZerodhaCredentials(
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        access_token=None,
        env=zenv,
    )
    client = KiteClient(credentials=creds, transport=UrllibKiteTransport())
    return client.connect_with_request_token(request_token)


def main() -> int:
    parser = argparse.ArgumentParser(description="Zerodha login → access_token (.env)")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--request-token",
        default="",
        help="Optional: exchange an already-captured request_token (must be fresh)",
    )
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    env_path = ROOT / ".env"
    merged = merge_env_with_optional_dotenv(dotenv_path=env_path)
    for k, v in merged.items():
        if k.startswith("ZERODHA_") or k.startswith("QUANTFUND_"):
            os.environ.setdefault(k, v)

    creds = load_credentials_from_env(dict(os.environ))
    if creds is None:
        print("FAIL: set ZERODHA_API_KEY and ZERODHA_API_SECRET in .env first.")
        print(f"Expected file: {env_path}")
        return 1

    if args.request_token.strip():
        try:
            access = _exchange(args.request_token.strip(), dict(os.environ))
        except Exception as exc:  # noqa: BLE001
            print(
                "FAIL: token exchange failed "
                f"({type(exc).__name__}). "
                "Request tokens expire quickly and are single-use. "
                "Re-run make zerodha-login and complete a FRESH login."
            )
            return 1
        _upsert_env_key(env_path, "ZERODHA_ACCESS_TOKEN", access)
        _upsert_env_key(env_path, "QUANTFUND_ALLOW_ZERODHA_HISTORICAL", "1")
        if not (os.environ.get("ZERODHA_ENV") or "").strip():
            _upsert_env_key(env_path, "ZERODHA_ENV", "production")
        print("OK: access_token written to .env (value not printed).")
        print("Next: make zerodha-auth-check && make zerodha-real-validation")
        return 0

    state: dict[str, object] = {"done": False, "error": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            # Avoid logging query strings (contain request_token).
            sys.stderr.write("callback_hit path_only=%s\n" % self.path.split("?", 1)[0])

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.rstrip("/") != CALLBACK_PATH.rstrip("/"):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"not found")
                return
            qs = parse_qs(parsed.query)
            status = (qs.get("status") or ["error"])[0]
            token = (qs.get("request_token") or [""])[0]
            if status != "success" or not token:
                state["error"] = "callback_missing_request_token_or_failed_status"
                body = b"Login callback failed. You can close this tab."
                self.send_response(400)
                self.end_headers()
                self.wfile.write(body)
                state["done"] = True
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            try:
                access = _exchange(token, dict(os.environ))
                _upsert_env_key(env_path, "ZERODHA_ACCESS_TOKEN", access)
                _upsert_env_key(env_path, "QUANTFUND_ALLOW_ZERODHA_HISTORICAL", "1")
                if not (os.environ.get("ZERODHA_ENV") or "").strip():
                    _upsert_env_key(env_path, "ZERODHA_ENV", "production")
                body = (
                    b"QuantFund: Zerodha login OK. access_token saved to .env. "
                    b"You can close this tab. (token not shown)"
                )
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # noqa: BLE001
                state["error"] = type(exc).__name__
                body = (
                    b"Token exchange failed. Request token may be expired/used. "
                    b"Close tab and re-run make zerodha-login."
                )
                self.send_response(500)
                self.end_headers()
                self.wfile.write(body)
            finally:
                state["done"] = True
                threading.Thread(target=self.server.shutdown, daemon=True).start()

    login_url = (
        f"https://kite.zerodha.com/connect/login?v=3&api_key={creds.api_key}"
    )
    print("=============================================")
    print("ZERODHA LOGIN (READ-ONLY ACCESS TOKEN)")
    print("=============================================")
    print(f"Callback: http://{args.host}:{args.port}{CALLBACK_PATH}")
    print("Kite app Redirect URL must match that exactly.")
    print()
    print("Open this login URL:")
    print(login_url)
    print()
    print("Waiting for callback (do not reuse an old browser redirect)...")

    server = HTTPServer((args.host, args.port), Handler)
    if not args.no_browser:
        try:
            webbrowser.open(login_url)
        except Exception:  # noqa: BLE001
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Cancelled.")
        return 1
    finally:
        server.server_close()

    if state.get("error"):
        print(f"FAIL: {state['error']}")
        print("Re-initiate a fresh login; request_tokens expire and are single-use.")
        return 1
    print("OK: access_token written to .env (value not printed).")
    print("Next: make zerodha-auth-check && make zerodha-real-validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
