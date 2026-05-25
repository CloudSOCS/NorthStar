from poly.execution.paper import run_paper_backtest


def test_paper_backtest_runs():
    result = run_paper_backtest(n_windows=50, seed=123)
    assert result.n_windows == 50
    assert result.ending_bankroll > 0
    assert result.n_trades >= 0
