from dataclasses import dataclass, field
from typing import List

from poly.config import Settings
from poly.data.sample import WindowSeries
from poly.execution.dry import evaluate_hedged_dry
from poly.execution.paper import run_hedged_paper_backtest
from poly.strategies.hedged_binary import HedgedBinaryStrategy


@dataclass
class _FakeMarket:
    asset: str = "ETH"
    question: str = "ETH 15m up?"


@dataclass
class _FakeTracker:
    """Mimics KalshiTickState/MarketTickState for hedge-detector tests."""

    up_prices: List[float] = field(default_factory=list)
    down_prices: List[float] = field(default_factory=list)
    market: _FakeMarket = field(default_factory=_FakeMarket)

    def feed(self, yes: float, no: float):
        self.up_prices.append(yes)
        self.down_prices.append(no)


def _hedge(tracker, **kw):
    return evaluate_hedged_dry(tracker, Settings(), bankroll=1000.0, **kw)


def test_hedge_leg1_fires_only_on_a_dip():
    t = _FakeTracker()
    t.feed(0.55, 0.45)  # YES was a coin-flip+ here (window high 0.55)
    assert _hedge(t).would_trade is False
    t.feed(0.40, 0.60)  # YES dipped from 0.55 -> actionable leg 1
    sig = _hedge(t)
    assert sig.would_trade is True
    assert "GRAB LEG 1" in sig.message and "YES" in sig.message


def test_hedge_ignores_structural_longshot():
    """A side that opens cheap and stays cheap is NOT a hedge leg."""
    t = _FakeTracker()
    t.feed(0.77, 0.23)  # NO is a cheap longshot, never was >= 0.50
    assert _hedge(t).would_trade is False
    t.feed(0.78, 0.22)  # still a longshot, no dip
    assert _hedge(t).would_trade is False


def test_hedge_completes_only_when_second_leg_cheap_now():
    t = _FakeTracker()
    t.feed(0.55, 0.45)
    t.feed(0.40, 0.60)  # leg1 = YES @ 0.40 (dipped from 0.55)
    _hedge(t)
    t.feed(0.62, 0.38)  # opposite (NO) now < 0.45 -> completes
    sig = _hedge(t)
    assert sig.would_trade is True
    assert "COMPLETE HEDGE" in sig.message
    # 0.40 + 0.38 = 0.78 -> locked 0.22
    assert "+0.220" in sig.message


def test_hedge_does_not_fire_after_completed():
    t = _FakeTracker()
    t.feed(0.55, 0.45)
    t.feed(0.40, 0.60)
    _hedge(t)
    t.feed(0.62, 0.38)
    _hedge(t)  # completes here
    t.feed(0.42, 0.58)  # leg cheap again, but window already hedged
    sig = _hedge(t)
    assert sig.would_trade is False


def test_hedge_grabs_both_when_simultaneously_cheap():
    t = _FakeTracker()
    t.feed(0.44, 0.44)  # sum 0.88 < breakeven -> instant grab both
    sig = _hedge(t)
    assert sig.would_trade is True
    assert "GRAB BOTH NOW" in sig.message


def test_hedge_stays_quiet_in_efficient_market():
    t = _FakeTracker()
    for _ in range(5):
        t.feed(0.52, 0.48)  # balanced, neither side below threshold
        assert _hedge(t).would_trade is False


def _make_window(prices, resolved_up=True):
    return WindowSeries(
        asset="BTC",
        prices=prices,
        resolved_up=resolved_up,
        open_price=prices[0],
        close_price=prices[-1],
    )


def test_hedged_locks_profit_when_volatile():
    window = _make_window([0.30, 0.32, 0.50, 0.70, 0.72], resolved_up=True)
    s = HedgedBinaryStrategy(buy_yes_below=0.45, buy_no_below=0.45)
    signal = s.evaluate_window(window, bankroll=1000)
    assert signal.filled is True
    assert signal.total_cost_per_share < 1.0
    assert signal.locked_profit_per_share > 0


def test_hedged_does_not_fill_when_flat():
    window = _make_window([0.50] * 8, resolved_up=False)
    s = HedgedBinaryStrategy(buy_yes_below=0.45, buy_no_below=0.45)
    signal = s.evaluate_window(window, bankroll=1000)
    assert signal.filled is False


def test_hedged_backtest_runs():
    result = run_hedged_paper_backtest(n_windows=80, seed=1)
    assert result.n_windows == 80
    assert result.ending_bankroll > 0
