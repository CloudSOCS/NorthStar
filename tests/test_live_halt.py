import json
from pathlib import Path

from poly.config import ExecutionMode, Settings
from poly.execution.kalshi_live import (
    LIVE_ATTEMPT_KIND,
    LIVE_REFUSE_FOOTER,
    LiveRequest,
    attempt_live_book,
)
from poly.execution.live_halt import (
    BOOK_HALT_LINE,
    RESUME_FLAG_REFUSE,
    default_halt_path,
    load_halt,
    write_manual_halt,
)
from poly.practice.orientation import CONTINUE


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


def test_halt_path_uses_env(monkeypatch, tmp_path):
    target = tmp_path / "live_halt.json"
    monkeypatch.setenv("NORTHSTAR_LIVE_HALT", str(target))
    assert default_halt_path() == target


def test_load_halt_missing_is_off_and_does_not_create(tmp_path):
    path = tmp_path / "missing.json"
    blob = load_halt(path)
    assert blob["halted"] is False
    assert blob["realized_live_pnl"] is None
    assert not path.exists()


def test_halted_book_does_not_post(tmp_path):
    halt = tmp_path / "live_halt.json"
    log = tmp_path / "live_attempts.json"
    pem = _pem(tmp_path)
    write_manual_halt(halt)
    result = attempt_live_book(
        _req(edge=0.10, approve_not_ready=True),
        settings=_settings(pem=pem),
        log_path=log,
        halt_path=halt,
        sender=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not POST")),
    )
    assert result.status == "refused_local"
    assert result.sent is False
    assert BOOK_HALT_LINE in result.reason
    assert LIVE_REFUSE_FOOTER in result.message
    row = json.loads(log.read_text())["attempts"][0]
    assert row["status"] == "refused_local"
    assert row["kind"] == LIVE_ATTEMPT_KIND
    assert json.loads(halt.read_text())["halted"] is True


def test_helper_continue_has_no_halt_or_live():
    assert not any("kalshi-live" in cmd for cmd in CONTINUE)
    assert not any("halt" in cmd or "resume" in cmd for cmd in CONTINUE)


def test_cli_halt_resume_and_book(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from poly.cli import app

    halt = tmp_path / "live_halt.json"
    log = tmp_path / "live_attempts.json"
    pem = _pem(tmp_path)
    monkeypatch.setenv("NORTHSTAR_LIVE_HALT", str(halt))
    monkeypatch.setenv("NORTHSTAR_LIVE_ATTEMPTS", str(log))
    monkeypatch.setenv("POLY_MODE", "live")
    monkeypatch.setenv("KALSHI_API_KEY", "key-id")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(pem))
    runner = CliRunner()

    status = runner.invoke(app, ["kalshi-live", "halt-status"])
    assert status.exit_code == 0
    assert "Live halt: off" in status.stdout
    assert not halt.exists()

    halted = runner.invoke(app, ["kalshi-live", "halt"])
    assert halted.exit_code == 0
    blob = json.loads(halt.read_text())
    assert blob == {
        "schema_version": 1,
        "halted": True,
        "reason": "manual",
        "realized_live_pnl": None,
        "halted_at": blob["halted_at"],
    }
    assert blob["halted_at"]

    book_args = [
        "kalshi-live",
        "book",
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
        "0.10",
        "--i-approve-live",
    ]
    booked = runner.invoke(app, book_args)
    assert booked.exit_code == 1
    assert BOOK_HALT_LINE in booked.stdout
    assert json.loads(log.read_text())["attempts"][0]["status"] == "refused_local"

    before = halt.read_text()
    no_flag = runner.invoke(app, ["kalshi-live", "resume"])
    assert no_flag.exit_code == 1
    assert RESUME_FLAG_REFUSE in no_flag.stdout
    assert halt.read_text() == before

    cleared = runner.invoke(app, ["kalshi-live", "resume", "--i-clear-loss-halt"])
    assert cleared.exit_code == 0
    assert "cleared" in cleared.stdout.lower()
    after = json.loads(halt.read_text())
    assert after["halted"] is False
    assert after["reason"] == "cleared"
    assert after["halted_at"] is None

    again = runner.invoke(app, book_args)
    assert BOOK_HALT_LINE not in again.stdout
    assert again.exit_code == 1
    assert "private key" in again.stdout.lower() or "rsa" in again.stdout.lower()


def test_cli_resume_requires_flag():
    import inspect

    from poly.cli import kalshi_live_resume

    source = inspect.getsource(kalshi_live_resume)
    assert "--i-clear-loss-halt" in source
    assert "kalshi-live" not in "".join(CONTINUE)
