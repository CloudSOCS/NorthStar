from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from poly.config import Settings
from poly.data.sample import WindowSeries, generate_paper_windows
from poly.strategies.markov_crypto import MarkovCryptoStrategy, TradeSignal


@dataclass
class PaperTrade:
    asset: str
    bet_usd: float
    market_price: float
    model_prob: float
    edge: float
    won: bool
    pnl: float


@dataclass
class PaperResult:
    starting_bankroll: float
    ending_bankroll: float
    n_windows: int
    n_trades: int
    win_rate: float
    trades: List[PaperTrade]


def _settle_yes_bet(bet_usd: float, market_price: float, won: bool) -> float:
    """Buy YES shares: pay bet, receive bet/price if win else 0."""
    if bet_usd <= 0:
        return 0.0
    shares = bet_usd / market_price
    payout = shares * 1.0 if won else 0.0
    return payout - bet_usd


def run_paper_backtest(
    n_windows: int = 200,
    settings: Optional[Settings] = None,
    seed: Optional[int] = 42,
) -> PaperResult:
    settings = settings or Settings()
    strategy = MarkovCryptoStrategy(settings)
    windows = generate_paper_windows(n_windows=n_windows, seed=seed)

    bankroll = settings.starting_bankroll
    trades: List[PaperTrade] = []

    for window in windows:
        signal = strategy.evaluate_window(
            window,
            bankroll=bankroll,
            scan_all_ticks=True,
            monte_carlo_paths=80,
        )
        if not signal.decision.should_trade or signal.bet_usd <= 0:
            continue
        if signal.bet_usd > bankroll:
            continue

        pnl = _settle_yes_bet(signal.bet_usd, signal.market_price, window.resolved_up)
        bankroll += pnl
        trades.append(
            PaperTrade(
                asset=window.asset,
                bet_usd=signal.bet_usd,
                market_price=signal.market_price,
                model_prob=signal.model_prob,
                edge=signal.edge,
                won=window.resolved_up,
                pnl=pnl,
            )
        )

    wins = sum(1 for t in trades if t.won)
    win_rate = wins / len(trades) if trades else 0.0

    return PaperResult(
        starting_bankroll=settings.starting_bankroll,
        ending_bankroll=bankroll,
        n_windows=n_windows,
        n_trades=len(trades),
        win_rate=win_rate,
        trades=trades,
    )


def pick_explanation_window(seed: int = 7) -> tuple[WindowSeries, TradeSignal]:
    """One window + signal for the `poly explain` command."""
    windows = generate_paper_windows(n_windows=20, seed=seed)
    window = windows[10]
    signal = MarkovCryptoStrategy().evaluate_window(window)
    return window, signal
