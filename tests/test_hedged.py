from poly.data.sample import WindowSeries
from poly.execution.paper import run_hedged_paper_backtest
from poly.strategies.hedged_binary import HedgedBinaryStrategy


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
