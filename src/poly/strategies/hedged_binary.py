"""
Phase 1.5 — Hedged binary ("Gabagool"-style) strategy.

Idea (in 3 lines):
  1. Buy YES when its price dips (e.g. <= 0.45).
  2. Later in the same window, buy NO when YES has risen (so NO is now <= 0.45).
  3. Pay roughly: p_yes_low + (1 - p_yes_high). If that sum < 1, you locked in
     profit *regardless of which side resolves*. You harvest volatility.

This is the opposite philosophy from MarkovCryptoStrategy: instead of predicting
direction, you stay directionally neutral and get paid for the market's price
swings inside a window. Win rate becomes ~irrelevant — only the average per-pair
cost matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from poly.config import Settings
from poly.data.sample import WindowSeries


@dataclass
class HedgedSignal:
    asset: str
    yes_entry_price: float
    no_entry_price: float
    yes_entry_tick: int
    no_entry_tick: int
    total_cost_per_share: float
    locked_profit_per_share: float
    bet_per_leg_usd: float
    filled: bool
    reason: str


class HedgedBinaryStrategy:
    """Open YES low, then NO low. Both legs filled = locked profit per share."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        buy_yes_below: float = 0.45,
        buy_no_below: float = 0.45,
        leg_fraction: float = 0.05,
    ):
        self.settings = settings or Settings()
        self.buy_yes_below = buy_yes_below
        self.buy_no_below = buy_no_below
        self.leg_fraction = leg_fraction

    def evaluate_window(
        self, window: WindowSeries, bankroll: float = 1000.0
    ) -> HedgedSignal:
        yes_price = None
        yes_tick = -1
        no_price = None
        no_tick = -1

        for idx, price in enumerate(window.prices):
            if yes_price is None and price <= self.buy_yes_below:
                yes_price = price
                yes_tick = idx
                continue
            if (
                yes_price is not None
                and no_price is None
                and (1.0 - price) <= self.buy_no_below
            ):
                no_price = 1.0 - price
                no_tick = idx
                break

        if yes_price is None or no_price is None:
            return HedgedSignal(
                asset=window.asset,
                yes_entry_price=yes_price or 0.0,
                no_entry_price=no_price or 0.0,
                yes_entry_tick=yes_tick,
                no_entry_tick=no_tick,
                total_cost_per_share=0.0,
                locked_profit_per_share=0.0,
                bet_per_leg_usd=0.0,
                filled=False,
                reason="One or both legs never reached entry threshold",
            )

        total_cost = yes_price + no_price
        locked_profit = 1.0 - total_cost
        bet_per_leg = bankroll * self.leg_fraction

        return HedgedSignal(
            asset=window.asset,
            yes_entry_price=yes_price,
            no_entry_price=no_price,
            yes_entry_tick=yes_tick,
            no_entry_tick=no_tick,
            total_cost_per_share=total_cost,
            locked_profit_per_share=locked_profit,
            bet_per_leg_usd=bet_per_leg,
            filled=True,
            reason=(
                f"YES @ {yes_price:.3f} (t={yes_tick}), "
                f"NO @ {no_price:.3f} (t={no_tick}); "
                f"cost={total_cost:.3f}, locked={locked_profit:+.3f}/share"
            ),
        )
