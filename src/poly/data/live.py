from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from poly.clients.clob import ClobClient
from poly.clients.gamma import GammaClient, UpDownMarket
from poly.data.sample import WindowSeries


@dataclass
class MarketTickState:
    """Accumulates live UP/DOWN mids for one active market."""

    market: UpDownMarket
    up_prices: List[float] = field(default_factory=list)
    down_prices: List[float] = field(default_factory=list)

    def record(self, up_mid: float, down_mid: float) -> None:
        self.up_prices.append(up_mid)
        self.down_prices.append(down_mid)

    def to_window_series(self) -> WindowSeries:
        return WindowSeries(
            asset=self.market.asset,
            prices=list(self.up_prices),
            down_prices=list(self.down_prices),
            resolved_up=False,
            open_price=self.up_prices[0] if self.up_prices else 0.5,
            close_price=self.up_prices[-1] if self.up_prices else 0.5,
        )


class LiveFeed:
    """Discover markets via Gamma, poll mids via CLOB."""

    def __init__(
        self,
        gamma: Optional[GammaClient] = None,
        clob: Optional[ClobClient] = None,
    ):
        self._gamma = gamma or GammaClient()
        self._clob = clob or ClobClient()
        self._owns_gamma = gamma is None
        self._owns_clob = clob is None
        self._trackers: Dict[str, MarketTickState] = {}

    def close(self) -> None:
        if self._owns_gamma:
            self._gamma.close()
        if self._owns_clob:
            self._clob.close()

    def __enter__(self) -> "LiveFeed":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def refresh_markets(self, assets: List[str]) -> List[UpDownMarket]:
        return self._gamma.list_updown_5m(assets=assets)

    def poll_prices(self, markets: List[UpDownMarket]) -> Dict[str, tuple[float, float]]:
        """Return asset -> (up_mid, down_mid). Falls back to Gamma if CLOB fails."""
        out: Dict[str, tuple[float, float]] = {}
        for m in markets:
            up = self._clob.get_midpoint(m.up_token_id)
            down = self._clob.get_midpoint(m.down_token_id)
            if up is None:
                up = m.gamma_up_price
            if down is None:
                down = m.gamma_down_price
            out[m.asset] = (up, down)

            key = m.slug
            if key not in self._trackers:
                self._trackers[key] = MarketTickState(market=m)
            self._trackers[key].record(up, down)
        return out

    def get_tracker(self, slug: str) -> Optional[MarketTickState]:
        return self._trackers.get(slug)

    def trackers_for_assets(self, assets: List[str]) -> List[MarketTickState]:
        want = {a.upper() for a in assets}
        return [t for t in self._trackers.values() if t.market.asset in want]
