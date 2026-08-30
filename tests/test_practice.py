import json
from pathlib import Path

import pytest

from poly.practice.account import (
    PracticeAccount,
    load_account,
    save_account,
)


def test_buy_and_settle_win(tmp_path: Path):
    acc = PracticeAccount(bankroll=100, starting_bankroll=100)
    pos = acc.buy("eth-updown-5m-1", "ETH", "UP", usd=20, price=0.5, strategy="manual")
    assert pos.shares == pytest.approx(40.0)
    assert acc.bankroll == pytest.approx(80.0)

    ev = acc.settle(pos, won=True)
    assert ev.realized_pnl == pytest.approx(20.0)  # paid 20, got 40
    assert acc.bankroll == pytest.approx(120.0)
    assert pos.closed is True


def test_buy_and_settle_loss():
    acc = PracticeAccount(bankroll=100, starting_bankroll=100)
    pos = acc.buy("eth-updown-5m-1", "ETH", "UP", usd=20, price=0.5)
    acc.settle(pos, won=False)
    assert acc.bankroll == pytest.approx(80.0)
    assert acc.total_realized_pnl() == pytest.approx(-20.0)


def test_hedged_locked_profit():
    acc = PracticeAccount(bankroll=100, starting_bankroll=100)
    yes = acc.buy("btc-updown-5m-1", "BTC", "UP", usd=10, price=0.40)  # 25 shares
    no = acc.buy("btc-updown-5m-1", "BTC", "DOWN", usd=10, price=0.45)  # ~22.2 shares
    # UP resolves
    ev_yes = acc.settle(yes, won=True)
    ev_no = acc.settle(no, won=False)
    total_pnl = ev_yes.realized_pnl + ev_no.realized_pnl
    assert total_pnl > 0


def test_persistence_roundtrip(tmp_path: Path):
    path = tmp_path / "practice.json"
    acc = PracticeAccount(bankroll=500, starting_bankroll=500)
    acc.buy("eth-updown-5m-2", "ETH", "DOWN", usd=15, price=0.3)
    save_account(acc, path)

    loaded = load_account(path)
    assert loaded.bankroll == pytest.approx(485.0)
    assert len(loaded.positions) == 1
    assert loaded.positions[0].asset == "ETH"


def test_insufficient_bankroll_raises():
    acc = PracticeAccount(bankroll=10, starting_bankroll=10)
    with pytest.raises(ValueError):
        acc.buy("x", "BTC", "UP", usd=50, price=0.5)


def test_close_at_price():
    acc = PracticeAccount(bankroll=100, starting_bankroll=100)
    pos = acc.buy("eth-updown-5m-1", "ETH", "UP", usd=20, price=0.5)  # 40 shares
    ev = acc.close_at_price(pos, sell_price=0.7)
    # 40 * 0.7 = 28, paid 20 → +8
    assert ev.realized_pnl == pytest.approx(8.0)
    assert acc.bankroll == pytest.approx(108.0)


ACCOUNT_BANNER = (
    "This is a fake-money wallet, not a Kalshi live account — no live order will be placed."
)
ACCOUNT_WALK_HINT = (
    "Four-step lesson (ticket, P&L, edge, hedge): northstar practice walk"
)


def _invoke_account(args, monkeypatch, path):
    from typer.testing import CliRunner

    from poly.cli import app

    monkeypatch.setenv("POLY_PRACTICE_FILE", str(path))
    return CliRunner().invoke(app, ["practice", *args])


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_practice_status_honesty_banner_and_tickets(monkeypatch, tmp_path):
    path = tmp_path / "practice.json"
    acc = PracticeAccount(bankroll=80, starting_bankroll=100)
    acc.buy("btc-updown-5m-1", "BTC", "UP", usd=20, price=0.80)
    save_account(acc, path)
    result = _invoke_account(["status"], monkeypatch, path)
    assert result.exit_code == 0
    text = _flat(result.stdout)
    assert ACCOUNT_BANNER in text
    assert ACCOUNT_WALK_HINT in text
    assert "Tickets" in text
    assert "Shares" not in text
    assert "Realized P&L" in text
    assert "Realized PnL" not in text
    assert "Kalshi" in text
    assert "practice walk" in text


def test_practice_pnl_honesty_banner_and_spelling(monkeypatch, tmp_path):
    path = tmp_path / "practice.json"
    acc = PracticeAccount(bankroll=100, starting_bankroll=100)
    save_account(acc, path)
    result = _invoke_account(["pnl"], monkeypatch, path)
    assert result.exit_code == 0
    text = _flat(result.stdout)
    assert ACCOUNT_BANNER in text
    assert ACCOUNT_WALK_HINT in text
    assert "Practice P&L" in text
    assert "Realized P&L" in text
    assert "Practice PnL" not in text
    assert "Realized PnL" not in text
