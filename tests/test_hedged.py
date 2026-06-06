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


def test_hedge_leg1_fires_on_choppy_dip():
    t = _FakeTracker()
    # Jagged YES path that ends below 0.45 having been above 0.55.
    for yes in (0.50, 0.62, 0.48, 0.40):
        t.feed(yes, round(1.0 - yes, 3))
    sig = _hedge(t)
    assert sig.would_trade is True
    assert "GRAB LEG 1" in sig.message and "YES" in sig.message


def test_hedge_skips_gentle_drift_even_when_it_dips():
    """The new volatility gate: a smooth glide that dips must NOT fire."""
    t = _FakeTracker()
    for yes in (0.55, 0.53, 0.51, 0.49, 0.47, 0.44):  # smooth one-way drift
        t.feed(yes, round(1.0 - yes, 3))
    sig = _hedge(t)
    assert sig.would_trade is False
    assert "too calm" in sig.message


def test_hedge_ignores_structural_longshot():
    """A choppy market whose cheap side never crossed 0.50 is not a hedge leg."""
    t = _FakeTracker()
    for yes in (0.75, 0.85, 0.74, 0.82):  # choppy but NO stays a longshot
        t.feed(yes, round(1.0 - yes, 3))
    assert _hedge(t).would_trade is False


def test_hedge_completes_only_when_second_leg_cheap_now():
    t = _FakeTracker()
    for yes in (0.48, 0.40, 0.56, 0.60):  # choppy; ends with NO @ 0.40 dip
        t.feed(yes, round(1.0 - yes, 3))
    sig1 = _hedge(t)
    assert sig1.would_trade is True and "NO" in sig1.message  # leg1 = NO @ 0.40
    t.feed(0.42, 0.58)  # opposite (YES) now < 0.45 -> completes
    sig = _hedge(t)
    assert sig.would_trade is True
    assert "COMPLETE HEDGE" in sig.message
    # 0.40 + 0.42 = 0.82 -> locked 0.18
    assert "+0.180" in sig.message


def test_hedge_does_not_fire_after_completed():
    t = _FakeTracker()
    for yes in (0.48, 0.40, 0.56, 0.60):
        t.feed(yes, round(1.0 - yes, 3))
    _hedge(t)  # leg1
    t.feed(0.42, 0.58)
    _hedge(t)  # completes here
    t.feed(0.41, 0.59)  # leg cheap again, but window already hedged
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
