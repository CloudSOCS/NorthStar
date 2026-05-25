from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class WindowSeries:
    """One synthetic 5-minute market window: price ticks + outcome."""

    asset: str
    prices: List[float]
    resolved_up: bool
    open_price: float
    close_price: float


def generate_paper_windows(
    n_windows: int = 200,
    ticks_per_window: int = 30,
    seed: Optional[int] = 42,
) -> List[WindowSeries]:
    """
    Create fake intra-window price paths resembling Polymarket 5m crypto markets.

    Each window: random walk in probability space with slight momentum,
    then resolve UP if close >= open.
    """
    rng = np.random.default_rng(seed)
    assets = ["BTC", "ETH", "SOL", "BNB", "XRP"]
    windows: List[WindowSeries] = []

    for _ in range(n_windows):
        asset = assets[int(rng.integers(0, len(assets)))]
        # Mix: ~40% of windows mimic "high-band" setups from the quant threads (83–97¢)
        if rng.random() < 0.4:
            open_p = float(rng.uniform(0.78, 0.92))
            drift = float(rng.normal(0.002, 0.006))
        else:
            open_p = float(rng.uniform(0.35, 0.65))
            drift = float(rng.normal(0, 0.008))

        price = open_p
        prices = [price]

        for _t in range(ticks_per_window - 1):
            shock = float(rng.normal(drift, 0.018))
            price = float(np.clip(price + shock, 0.02, 0.98))
            prices.append(price)

        close_p = prices[-1]
        resolved_up = close_p >= open_p
        windows.append(
            WindowSeries(
                asset=asset,
                prices=prices,
                resolved_up=resolved_up,
                open_price=open_p,
                close_price=close_p,
            )
        )
    return windows
