import json
from pathlib import Path

import httpx
import pytest

from poly.config import ExecutionMode, Settings
from poly.execution.kalshi_live import (
    LIVE_ATTEMPT_KIND,
    LIVE_REFUSE_FOOTER,
    RATE_LIMIT_LINE,
    LiveRequest,
    attempt_live_book,
    default_live_attempts_path,
    load_live_attempts,
)
from poly.practice.orientation import CONTINUE, FENCES, product_status_payload


def _req(**overrides) -> LiveRequest:
    data = dict(
        ticker="KXBTC15M-TEST",
        side="yes",
        spend=2.0,
        yes_price=0.80,
        no_price=0.21,
        edge="not ready",
        approve_live=True,
        approve_not_ready=False,
        both=False,
    )
    data.update(overrides)
    return LiveRequest(**data)


def _settings(*, mode=ExecutionMode.LIVE, key="key-id", pem: Path) -> Settings:
    return Settings(
        POLY_MODE=mode,
        KALSHI_API_KEY=key,
        KALSHI_PRIVATE_KEY_PATH=str(pem),
    )


def _pem(tmp_path: Path) -> Path:
    path = tmp_path / "kalshi_private.pem"
    path.write_text("-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n")
    return path


def test_live_attempts_path_uses_env(monkeypatch, tmp_path):
    target = tmp_path / "live_attempts.json"
    monkeypatch.setenv("NORTHSTAR_LIVE_ATTEMPTS", str(target))
    assert default_live_attempts_path() == target


def test_refuse_without_approve_live(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(approve_live=False),
        settings=_settings(pem=pem),
        log_path=log,
        sender=lambda *_a, **_k: pytest.fail("must not send"),
    )
    assert result.status == "refused_local"
    assert result.sent is False
    blob = json.loads(log.read_text())
    assert blob["attempts"][0]["status"] == "refused_local"
    assert blob["attempts"][0]["kind"] == LIVE_ATTEMPT_KIND


def test_refuse_when_mode_not_live(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(approve_not_ready=True),
        settings=_settings(mode=ExecutionMode.PAPER, pem=pem),
        log_path=log,
        sender=lambda *_a, **_k: pytest.fail("must not send"),
    )
    assert result.status == "refused_local"
    assert "POLY_MODE" in result.reason


def test_refuse_missing_keys(tmp_path):
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(approve_not_ready=True),
        settings=Settings(POLY_MODE=ExecutionMode.LIVE),
        log_path=log,
        sender=lambda *_a, **_k: pytest.fail("must not send"),
    )
    assert result.status == "refused_local"
    assert "KALSHI" in result.reason


def test_refuse_spend_over_five(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(spend=5.01, approve_not_ready=True),
        settings=_settings(pem=pem),
        log_path=log,
        sender=lambda *_a, **_k: pytest.fail("must not send"),
    )
    assert result.status == "refused_local"
    assert "5" in result.reason


def test_refuse_both_when_pair_not_cheap(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(both=True, approve_not_ready=True),
        settings=_settings(pem=pem),
        log_path=log,
        sender=lambda *_a, **_k: pytest.fail("must not send"),
    )
    assert result.status == "refused_local"
    assert "both sides" in result.reason.lower() or "hedge" in result.reason.lower()


def test_refuse_edge_not_ready_without_flag(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(edge="not ready", approve_not_ready=False),
        settings=_settings(pem=pem),
        log_path=log,
        sender=lambda *_a, **_k: pytest.fail("must not send"),
    )
    assert result.status == "refused_local"
    assert "not ready" in result.reason.lower()
    assert "invent" in result.reason.lower() or "approve-not-ready" in result.reason.lower()


def test_429_logs_rate_limited_and_does_not_retry(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    calls = {"n": 0}

    def boom(_req):
        calls["n"] += 1
        raise httpx.HTTPStatusError(
            "429",
            request=httpx.Request("POST", "https://example.invalid"),
            response=httpx.Response(429),
        )

    result = attempt_live_book(
        _req(edge=0.10, approve_not_ready=False),
        settings=_settings(pem=pem),
        log_path=log,
        sender=boom,
    )
    assert calls["n"] == 1
    assert result.status == "rate_limited"
    assert result.sent is False
    assert RATE_LIMIT_LINE in result.message
    blob = json.loads(log.read_text())
    assert blob["attempts"][0]["status"] == "rate_limited"
    assert blob["attempts"][0]["kind"] != "live"


def test_sent_only_when_sender_accepts(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(edge=0.10),
        settings=_settings(pem=pem),
        log_path=log,
        sender=lambda req: {"accepted": True, "order_id": "ord1"},
    )
    assert result.status == "sent"
    blob = json.loads(log.read_text())
    row = blob["attempts"][0]
    assert row["status"] == "sent"
    assert row["kind"] == "live"


def test_production_sender_does_not_exist_no_network(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(edge=0.10),
        settings=_settings(pem=pem),
        log_path=log,
        sender=None,
    )
    assert result.status == "refused_local"
    assert "signer" in result.reason.lower()
    assert result.sent is False
    blob = json.loads(log.read_text())
    assert blob["attempts"][0]["kind"] == LIVE_ATTEMPT_KIND
    assert blob["attempts"][0]["status"] == "refused_local"


def test_prints_step2_before_send(tmp_path):
    pem = _pem(tmp_path)
    seen = {}

    def sender(req):
        seen["printed"] = True
        return {"accepted": True}

    result = attempt_live_book(
        _req(edge=0.10),
        settings=_settings(pem=pem),
        log_path=tmp_path / "live_attempts.json",
        sender=sender,
    )
    assert "2.50 tickets" in result.message or "2.5 tickets" in result.message
    assert "+$0.50" in result.message or "+$0.5" in result.message
    assert "-$2.00" in result.message
    assert seen["printed"] is True


def test_status_continue_and_fence_unchanged():
    blob = product_status_payload([])
    assert blob["fences"]["live_orders"] == "unwired"
    assert FENCES["live_orders"] == "unwired"
    assert not any("kalshi-live" in cmd for cmd in CONTINUE)
    assert not any("i-approve-live" in cmd for cmd in blob["continue"])


def test_kalshi_live_module_does_not_import_graph_or_loop():
    import inspect

    from poly.execution import kalshi_live

    source = inspect.getsource(kalshi_live)
    assert "hypothesis_graph" not in source
    assert "run_live_loop" not in source
    assert "propose_experiment" not in source
    assert "agents." not in source


def _invoke(args, monkeypatch, tmp_path, *, mode="live", key="key-id", pem=True):
    from typer.testing import CliRunner

    from poly.cli import app

    log = tmp_path / "live_attempts.json"
    monkeypatch.setenv("NORTHSTAR_LIVE_ATTEMPTS", str(log))
    monkeypatch.setenv("POLY_MODE", mode)
    monkeypatch.setenv("KALSHI_API_KEY", key or "")
    if pem:
        path = _pem(tmp_path)
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(path))
    else:
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_path / "missing.pem"))
    return CliRunner().invoke(app, ["kalshi-live", "book", *args]), log


BASE = [
    "--ticker",
    "KXBTC15M-TEST",
    "--side",
    "yes",
    "--spend",
    "2",
    "--yes-price",
    "0.80",
    "--no-price",
    "0.21",
    "--edge",
    "not ready",
]


def test_cli_refuse_missing_approve(monkeypatch, tmp_path):
    result, log = _invoke(BASE, monkeypatch, tmp_path)
    assert result.exit_code == 1
    assert LIVE_REFUSE_FOOTER in result.stdout
    assert json.loads(log.read_text())["attempts"][0]["status"] == "refused_local"


def test_cli_refuse_missing_keys(monkeypatch, tmp_path):
    result, log = _invoke(
        [*BASE, "--i-approve-live", "--i-approve-not-ready"],
        monkeypatch,
        tmp_path,
        pem=False,
        key="",
    )
    assert result.exit_code == 1
    assert "KALSHI" in result.stdout
    assert not any(
        a["status"] == "sent" for a in json.loads(log.read_text())["attempts"]
    )


def test_cli_no_signer_no_send(monkeypatch, tmp_path):
    result, log = _invoke(
        [*BASE, "--edge", "0.10", "--i-approve-live"],
        monkeypatch,
        tmp_path,
    )
    assert result.exit_code == 1
    assert "signer" in result.stdout.lower()
    assert LIVE_REFUSE_FOOTER in result.stdout
    row = json.loads(log.read_text())["attempts"][0]
    assert row["status"] == "refused_local"
    assert row["kind"] != "live"


def test_load_attempts_missing_does_not_create(tmp_path):
    path = tmp_path / "missing.json"
    blob = load_live_attempts(path)
    assert blob == {"schema_version": 1, "attempts": []}
    assert not path.exists()
