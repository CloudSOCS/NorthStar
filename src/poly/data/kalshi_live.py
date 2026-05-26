"""Live Kalshi price polling for dry-run signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from poly.clients.kalshi import KalshiClient, KalshiMarket
from poly.data.sample import WindowSeries


@dataclass
class KalshiTickState:
    """Tick history for one Kalshi 15m Up/Down market."""

    market: KalshiMarket
    up_prices: List[float] = field(default_factory=list)
    down_prices: List[float] = field(default_factory=list)

    def record(self, yes_mid: float, no_mid: float) -> None:
        self.up_prices.append(yes_mid)
        self.down_prices.append(no_mid)

    def to_window_series(self) -> WindowSeries:
        return WindowSeries(
            asset=self.market.asset,
            prices=list(self.up_prices),
            down_prices=list(self.down_prices),
            resolved_up=False,
            open_price=self.up_prices[0] if self.up_prices else 0.5,
            close_price=self.up_prices[-1] if self.up_prices else 0.5,
        )


class KalshiLiveFeed:
    """Poll Kalshi 15m crypto markets (read-only, no API key)."""

    def __init__(self, kalshi: Optional[KalshiClient] = None):
        self._kalshi = kalshi or KalshiClient()
        self._owns = kalshi is None
        self._trackers: Dict[str, KalshiTickState] = {}

    def close(self) -> None:
        if self._owns:
            self._kalshi.close()

    def __enter__(self) -> "KalshiLiveFeed":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def refresh_and_poll(self, assets: List[str]) -> List[KalshiMarket]:
        markets = self._kalshi.list_crypto_15m(assets=assets)
        for m in markets:
            yes = m.yes_mid
            no = m.no_ask if m.no_ask > 0 else (1.0 - yes)
            key = m.ticker
            if key not in self._trackers:
                self._trackers[key] = KalshiTickState(market=m)
            else:
                self._trackers[key].market = m
            self._trackers[key].record(yes, no)
        return markets

    def trackers_for_assets(self, assets: List[str]) -> List[KalshiTickState]:
        want = {a.upper() for a in assets}
        return [t for t in self._trackers.values() if t.market.asset in want]
