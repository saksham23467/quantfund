"""EC2 deployment diagnostics — no broker writes, no secrets leaked."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from quantfund.deploy.ec2_preflight import run_ec2_preflight
from quantfund.deploy.environment import (
    SECRET_ENV_KEYS,
    detect_execution_role,
    run_environment_check,
    zerodha_config_presence,
)
from quantfund.phase17c.safety import safety_payload


def test_detect_role_local_on_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTFUND_EXECUTION_ROLE", raising=False)
    monkeypatch.setattr("quantfund.deploy.environment.platform.system", lambda: "Darwin")
    assert detect_execution_role() == "LOCAL"


def test_detect_role_forced_ec2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTFUND_EXECUTION_ROLE", "EC2")
    assert detect_execution_role() == "EC2"


def test_environment_check_distinguishes_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTFUND_EXECUTION_ROLE", "LOCAL")
    payload = run_environment_check(fetch_egress_ip=False)
    assert payload["execution_role"] == "LOCAL"
    assert "execution_host" in payload
    assert "execution_os" in payload
    assert "execution_architecture" in payload
    assert "zerodha_ip_match" in payload
    assert payload["broker_safety"]["broker_write_capability"] == "DISABLED"
    assert payload["broker_safety"]["live_trading"] == "DISABLED"
    assert payload["broker_safety"]["paper_trading"] == "NOT_STARTED"
    assert payload["broker_safety"]["place_order_called"] == 0


def test_environment_check_never_embeds_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "SUPER_SECRET_VALUE_9f3a2c1b"
    monkeypatch.setenv("ZERODHA_API_KEY", secret)
    monkeypatch.setenv("ZERODHA_API_SECRET", secret)
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", secret)
    monkeypatch.setenv("QUANTFUND_ALLOW_ZERODHA_HISTORICAL", "1")
    monkeypatch.setenv("QUANTFUND_EXECUTION_ROLE", "LOCAL")
    payload = run_environment_check(fetch_egress_ip=False)
    blob = json.dumps(payload)
    assert secret not in blob
    assert payload["zerodha_config"]["key_set"] is True


def test_zerodha_config_presence_no_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERODHA_API_KEY", "abc")
    monkeypatch.setenv("ZERODHA_API_SECRET", "def")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "ghi")
    monkeypatch.setenv("QUANTFUND_ALLOW_ZERODHA_HISTORICAL", "1")
    cfg = zerodha_config_presence(env=dict(os.environ))
    assert cfg["ok_for_real_historical"] is True
    assert "abc" not in json.dumps(cfg)


def test_ec2_preflight_fails_on_local_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTFUND_EXECUTION_ROLE", "LOCAL")
    payload = run_ec2_preflight(require_ec2=True)
    assert payload["ok"] is False
    assert any("execution_role_not_ec2" in p for p in payload["problems"])


def test_ec2_preflight_allow_non_ec2_still_checks_broker_safety(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTFUND_EXECUTION_ROLE", "LOCAL")
    payload = run_ec2_preflight(require_ec2=False)
    assert payload["broker_safety"]["broker_write_capability"] == "DISABLED"
    assert payload["broker_safety"]["orders_submitted"] == 0
    assert payload["broker_safety"]["place_order_called"] == 0
    assert payload["broker_safety"]["kill_switch"] == "ARMED"


def test_deployment_scripts_exist() -> None:
    assert Path("scripts/deploy_to_ec2.sh").exists()
    assert Path("scripts/run_environment_check.py").exists()
    assert Path("scripts/run_ec2_preflight.py").exists()
    assert Path("requirements-lock.txt").exists()
    assert Path("docs/EC2_DEPLOYMENT.md").exists()


def test_deploy_script_has_no_place_order() -> None:
    text = Path("scripts/deploy_to_ec2.sh").read_text(encoding="utf-8")
    assert "place_order" not in text
    assert "LIVE_TRADING=true" not in text


def test_deploy_module_has_no_broker_write_defs() -> None:
    root = Path("src/quantfund/deploy")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "def place_order" not in text
        assert "from kiteconnect" not in text.lower()


def test_makefile_has_environment_targets() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")
    assert "environment-check:" in text
    assert "ec2-preflight:" in text
    assert "deploy-ec2:" in text


def test_safety_payload_still_disabled() -> None:
    s = safety_payload()
    assert s["ok"] is True
    assert s["live_trading"] == "DISABLED"
    assert s["paper_trading"] == "NOT_STARTED"


def test_secret_env_keys_include_zerodha() -> None:
    assert "ZERODHA_API_KEY" in SECRET_ENV_KEYS
    assert "ZERODHA_ACCESS_TOKEN" in SECRET_ENV_KEYS


def test_ip_match_unknown_without_expected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTFUND_EXPECTED_ZERODHA_IP", raising=False)
    monkeypatch.setenv("QUANTFUND_EXECUTION_ROLE", "LOCAL")
    payload = run_environment_check(fetch_egress_ip=False)
    assert payload["zerodha_ip_match"] == "UNKNOWN_EXPECTED_IP_NOT_CONFIGURED"


def test_ip_match_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTFUND_EXPECTED_ZERODHA_IP", "1.2.3.4")
    monkeypatch.setenv("QUANTFUND_EXECUTION_ROLE", "LOCAL")
    monkeypatch.setattr(
        "quantfund.deploy.environment.public_egress_ip", lambda timeout_s=3.0: "1.2.3.4"
    )
    payload = run_environment_check(fetch_egress_ip=True)
    assert payload["zerodha_ip_match"] == "MATCH"


def test_ip_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTFUND_EXPECTED_ZERODHA_IP", "1.2.3.4")
    monkeypatch.setenv("QUANTFUND_EXECUTION_ROLE", "EC2")
    monkeypatch.setattr(
        "quantfund.deploy.environment.public_egress_ip", lambda timeout_s=3.0: "9.9.9.9"
    )
    payload = run_environment_check(fetch_egress_ip=True)
    assert payload["execution_role"] == "EC2"
    assert payload["zerodha_ip_match"] == "MISMATCH"


def test_requirements_lock_pins_python_deps() -> None:
    text = Path("requirements-lock.txt").read_text(encoding="utf-8")
    assert "pandas==" in text
    assert "exchange_calendars==" in text
    assert "ZERODHA" not in text


def test_phase18_exists_without_broker_writes() -> None:
    assert Path("src/quantfund/phase18").exists()
    from quantfund.phase18.safety import safety_payload

    s = safety_payload()
    assert s["live_trading"] == "DISABLED"
    assert s["orders_submitted"] == 0
    assert s["ok"] is True


def test_gitignore_keeps_pem_out() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")
    assert "*.pem" in text
    assert ".env" in text
