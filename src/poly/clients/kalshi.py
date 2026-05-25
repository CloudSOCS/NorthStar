"""
Kalshi public market data client (read-only, unauthenticated).

Surfaces the 15-minute crypto Up/Down markets (KXBTC15M, KXETH15M, …) so we can
cross-check them against Polymarket's 5-minute Up/Down windows. Real trading would
require RSA-PSS signed headers — that lives in execution/live.py later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx

from poly.config import Settings


KALSHI_CRYPTO_SERIES: Dict[str, str] = {
    "BTC": "KXBTC15M",
    "ETH": "KXETH15M",
    "SOL": "KXSOL15M",
    "BNB": "KXBNB15M",
    "XRP": "KXXRP15M",
    "DOGE": "KXDOGE15M",
    "HYPE": "KXHYPE15M",
    "ADA": "KXADA15M",
    "BCH": "KXBCH15M",
}


@dataclass(frozen=True)
class KalshiMarket:
    """One Kalshi binary up/down market."""

    asset: str
    ticker: str
    event_ticker: str
    title: str
    yes_sub_title: str
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    last_price: float
    close_time: str
    floor_strike: Optional[float] = None
    volume_24h: float = 0.0

    @property
    def yes_mid(self) -> float:
        if self.yes_bid > 0 and self.yes_ask > 0:
            return (self.yes_bid + self.yes_ask) / 2
        return self.last_price or 0.5

    @property
    def no_mid(self) -> float:
        return 1.0 - self.yes_mid


def _f(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class KalshiClient:
    """Read-only client for Kalshi's public market data endpoints."""

    def __init__(
        self,
        base_url: str = "https://external-api.kalshi.com/trade-api/v2",
        timeout: float = 15.0,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or Settings()
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "KalshiClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_markets(self, series_ticker: str, status: str = "open", limit: int = 5) -> List[Dict[str, Any]]:
        r = self._client.get(
            "/markets",
            params={"series_ticker": series_ticker, "status": status, "limit": limit},
        )
        r.raise_for_status()
        data = r.json()
        return data.get("markets", []) or []

    def get_current_15m(self, asset: str) -> Optional[KalshiMarket]:
        """The active 15-minute Up/Down market for one asset, if any."""
        series = KALSHI_CRYPTO_SERIES.get(asset.upper())
        if not series:
            return None
        markets = self.get_markets(series, status="open", limit=3)
        if not markets:
            return None
        # Newest market = highest close_time
        m = max(markets, key=lambda x: x.get("close_time", ""))
        return KalshiMarket(
            asset=asset.upper(),
            ticker=m.get("ticker", ""),
            event_ticker=m.get("event_ticker", ""),
            title=m.get("title", ""),
            yes_sub_title=m.get("yes_sub_title", ""),
            yes_bid=_f(m.get("yes_bid_dollars")),
            yes_ask=_f(m.get("yes_ask_dollars")),
            no_bid=_f(m.get("no_bid_dollars")),
            no_ask=_f(m.get("no_ask_dollars")),
            last_price=_f(m.get("last_price_dollars")),
            close_time=m.get("close_time", ""),
            floor_strike=m.get("floor_strike"),
            volume_24h=_f(m.get("volume_24h_fp")),
        )

    def list_crypto_15m(
        self, assets: Optional[Sequence[str]] = None
    ) -> List[KalshiMarket]:
        want = [a.upper() for a in (assets or KALSHI_CRYPTO_SERIES.keys())]
        out: List[KalshiMarket] = []
        for asset in want:
            m = self.get_current_15m(asset)
            if m is not None:
                out.append(m)
        return out
