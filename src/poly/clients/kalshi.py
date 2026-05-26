"""
Kalshi public market data client (read-only, unauthenticated).

Surfaces the 15-minute crypto Up/Down markets (KXBTC15M, KXETH15M, …) so we can
cross-check them against Polymarket's 5-minute Up/Down windows. Real trading would
require RSA-PSS signed headers — that lives in execution/live.py later.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

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

# Seconds between per-asset API calls (Kalshi rate-limits burst traffic)
DEFAULT_REQUEST_GAP = 0.4
CACHE_TTL_SECONDS = 8.0


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

    @property
    def question(self) -> str:
        """Alias for strategies that expect Polymarket-style `.question`."""
        return self.title


def _f(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _raw_to_market(asset: str, m: Dict[str, Any]) -> KalshiMarket:
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


class KalshiClient:
    """Read-only client for Kalshi's public market data endpoints."""

    def __init__(
        self,
        base_url: str = "https://external-api.kalshi.com/trade-api/v2",
        timeout: float = 15.0,
        settings: Optional[Settings] = None,
        request_gap: float = DEFAULT_REQUEST_GAP,
    ):
        self.settings = settings or Settings()
        self.request_gap = request_gap
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        self._cache_key: Optional[Tuple[str, ...]] = None
        self._cache_at: float = 0.0
        self._cache_data: List[KalshiMarket] = []
        self._last_request_at: float = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "KalshiClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.request_gap:
            time.sleep(self.request_gap - elapsed)

    def _get_json(
        self, path: str, params: Optional[Dict[str, Any]] = None, max_retries: int = 4
    ) -> Dict[str, Any]:
        last_err: Optional[Exception] = None
        for attempt in range(max_retries):
            self._throttle()
            r = self._client.get(path, params=params or {})
            self._last_request_at = time.time()
            if r.status_code == 429:
                wait = min(8.0, 1.5 * (2**attempt))
                time.sleep(wait)
                last_err = httpx.HTTPStatusError(
                    "429 Too Many Requests", request=r.request, response=r
                )
                continue
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {}
        if last_err:
            raise last_err
        return {}

    def get_markets(
        self, series_ticker: str, status: str = "open", limit: int = 5
    ) -> List[Dict[str, Any]]:
        data = self._get_json(
            "/markets",
            params={"series_ticker": series_ticker, "status": status, "limit": limit},
        )
        return data.get("markets", []) or []

    def get_current_15m(self, asset: str) -> Optional[KalshiMarket]:
        """The active 15-minute Up/Down market for one asset, if any."""
        series = KALSHI_CRYPTO_SERIES.get(asset.upper())
        if not series:
            return None
        markets = self.get_markets(series, status="open", limit=3)
        if not markets:
            return None
        m = max(markets, key=lambda x: x.get("close_time", ""))
        return _raw_to_market(asset, m)

    def list_crypto_15m(
        self,
        assets: Optional[Sequence[str]] = None,
        use_cache: bool = True,
    ) -> List[KalshiMarket]:
        """
        Active 15m markets for requested assets.

        Uses a short in-memory cache and spaces requests to avoid Kalshi 429s.
        """
        want = tuple(a.upper() for a in (assets or KALSHI_CRYPTO_SERIES.keys()))
        now = time.time()
        if (
            use_cache
            and self._cache_key == want
            and (now - self._cache_at) < CACHE_TTL_SECONDS
            and self._cache_data
        ):
            return list(self._cache_data)

        out: List[KalshiMarket] = []
        errors: List[str] = []

        for asset in want:
            series = KALSHI_CRYPTO_SERIES.get(asset)
            if not series:
                continue
            try:
                markets = self.get_markets(series, status="open", limit=3)
                if not markets:
                    continue
                m = max(markets, key=lambda x: x.get("close_time", ""))
                out.append(_raw_to_market(asset, m))
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    errors.append(asset)
                else:
                    raise

        if errors:
            raise httpx.HTTPStatusError(
                f"Kalshi rate-limited after fetching {len(out)}/{len(want)} assets "
                f"(missing: {', '.join(errors)}). Wait ~10s and retry once.",
                request=None,
                response=None,
            )

        self._cache_key = want
        self._cache_at = now
        self._cache_data = list(out)
        return out
