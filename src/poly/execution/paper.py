from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from poly.config import Settings
from poly.data.sample import WindowSeries, generate_paper_windows
from poly.strategies.hedged_binary import HedgedBinaryStrategy
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


@dataclass
class HedgedTrade:
    asset: str
    yes_price: float
    no_price: float
    cost_per_share: float
    capital_used: float
    payout: float
    pnl: float
    resolved_up: bool


@dataclass
class HedgedResult:
    starting_bankroll: float
    ending_bankroll: float
    n_windows: int
    n_trades: int
    n_filled_unprofitable: int
    avg_locked_profit_per_share: float
    trades: List[HedgedTrade]


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


def run_hedged_paper_backtest(
    n_windows: int = 200,
    settings: Optional[Settings] = None,
    seed: Optional[int] = 42,
    buy_yes_below: float = 0.45,
    buy_no_below: float = 0.45,
    leg_fraction: float = 0.05,
) -> HedgedResult:
    """
    Phase 1.5 paper backtest: hedged YES+NO buys.

    Each filled hedge pays exactly $1 on the winning side, so PnL per filled
    window = (1 / cost_per_share - 1) * capital_used_per_leg. If cost > 1, the
    "hedge" lost money and we record that too.
    """
    settings = settings or Settings()
    strategy = HedgedBinaryStrategy(
        settings,
        buy_yes_below=buy_yes_below,
        buy_no_below=buy_no_below,
        leg_fraction=leg_fraction,
    )
    windows = generate_paper_windows(n_windows=n_windows, seed=seed)

    bankroll = settings.starting_bankroll
    trades: List[HedgedTrade] = []
    n_filled_unprofitable = 0
    locked_profits: List[float] = []

    for window in windows:
        signal = strategy.evaluate_window(window, bankroll=bankroll)
        if not signal.filled:
            continue

        shares_per_leg = signal.bet_per_leg_usd
        yes_shares = shares_per_leg / signal.yes_entry_price
        no_shares = shares_per_leg / signal.no_entry_price
        capital_used = 2 * shares_per_leg
        if capital_used > bankroll:
            continue

        payout = yes_shares if window.resolved_up else no_shares
        pnl = payout - capital_used
        bankroll += pnl

        locked_profits.append(signal.locked_profit_per_share)
        if signal.locked_profit_per_share <= 0:
            n_filled_unprofitable += 1

        trades.append(
            HedgedTrade(
                asset=window.asset,
                yes_price=signal.yes_entry_price,
                no_price=signal.no_entry_price,
                cost_per_share=signal.total_cost_per_share,
                capital_used=capital_used,
                payout=payout,
                pnl=pnl,
                resolved_up=window.resolved_up,
            )
        )

    avg_locked = (
        sum(locked_profits) / len(locked_profits) if locked_profits else 0.0
    )
    return HedgedResult(
        starting_bankroll=settings.starting_bankroll,
        ending_bankroll=bankroll,
        n_windows=n_windows,
        n_trades=len(trades),
        n_filled_unprofitable=n_filled_unprofitable,
        avg_locked_profit_per_share=avg_locked,
        trades=trades,
    )
