from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from poly.config import Settings
from poly.data.sample import WindowSeries
from poly.models.edge import EdgeDecision, compute_edge
from poly.models.kelly import kelly_binary_yes, size_bet_usd
from poly.models.markov import MarkovModel


@dataclass
class TradeSignal:
    asset: str
    market_price: float
    model_prob: float
    edge: float
    kelly_full: float
    bet_usd: float
    decision: EdgeDecision


class MarkovCryptoStrategy:
    """
    Thread-1 style strategy (simplified for learning):

    1. Fit Markov transitions on early-window ticks
    2. Monte Carlo estimate P(UP) from current price
    3. Trade YES only when edge and entry band pass
    4. Size with fractional Kelly
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()

    def evaluate_window(
        self,
        window: WindowSeries,
        tick_index: Optional[int] = None,
        bankroll: float = 1000.0,
        scan_all_ticks: bool = False,
        monte_carlo_paths: Optional[int] = None,
    ) -> TradeSignal:
        """
        Decision at one tick inside the window.

        Backtests scan all ticks and take the first valid signal (like watching
        the live book until edge appears). `explain` uses a fixed mid tick.
        """
        if tick_index is not None and not scan_all_ticks:
            indices = [tick_index]
        elif scan_all_ticks:
            # Need enough history to fit transitions
            indices = list(range(5, len(window.prices) - 1, 2))
            if not indices:
                indices = [max(0, len(window.prices) - 2)]
        else:
            indices = [min(15, len(window.prices) - 2)]

        best: Optional[TradeSignal] = None
        for idx in indices:
            signal = self._signal_at_tick(
                window, idx, bankroll, monte_carlo_paths=monte_carlo_paths
            )
            if signal.decision.should_trade and signal.bet_usd > 0:
                return signal
            if best is None or signal.edge > best.edge:
                best = signal

        assert best is not None
        return best

    def _signal_at_tick(
        self,
        window: WindowSeries,
        tick_index: int,
        bankroll: float,
        monte_carlo_paths: Optional[int] = None,
    ) -> TradeSignal:
        history = window.prices[: tick_index + 1]
        market_price = history[-1]

        model = MarkovModel.fit(history, n_bins=self.settings.n_markov_bins)
        steps_left = max(1, len(window.prices) - tick_index - 1)
        n_paths = monte_carlo_paths or self.settings.monte_carlo_paths
        model_prob = model.monte_carlo_up_probability(
            market_price,
            n_steps=steps_left,
            n_paths=n_paths,
            seed=hash((window.asset, tick_index)) % (2**31),
        )

        decision = compute_edge(
            model_prob=model_prob,
            market_price=market_price,
            min_edge=self.settings.min_edge,
            entry_min=self.settings.entry_min_price,
            entry_max=self.settings.entry_max_price,
        )

        kelly_full = kelly_binary_yes(model_prob, market_price)
        bet = 0.0
        if decision.should_trade:
            bet = size_bet_usd(
                bankroll=bankroll,
                prob_win=model_prob,
                market_price=market_price,
                kelly_fraction=self.settings.kelly_fraction,
                max_bet_fraction=self.settings.max_bet_fraction,
            )

        return TradeSignal(
            asset=window.asset,
            market_price=market_price,
            model_prob=model_prob,
            edge=decision.edge,
            kelly_full=kelly_full,
            bet_usd=bet,
            decision=decision,
        )
