from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx

from poly.config import Settings

SLUG_ASSET = {
    "btc": "BTC",
    "eth": "ETH",
    "sol": "SOL",
    "bnb": "BNB",
    "xrp": "XRP",
    "doge": "DOGE",
    "hype": "HYPE",
}


@dataclass(frozen=True)
class UpDownMarket:
    market_id: str
    asset: str
    question: str
    slug: str
    up_token_id: str
    down_token_id: str
    gamma_up_price: float
    gamma_down_price: float
    end_date: Optional[str] = None


def _parse_json_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return []


def _asset_from_slug(slug: str) -> str:
    prefix = slug.split("-")[0].lower()
    return SLUG_ASSET.get(prefix, prefix.upper())


def _is_5m_updown_market(market: Dict[str, Any]) -> bool:
    slug = (market.get("slug") or "").lower()
    return "updown-5m" in slug and "up or down" in (market.get("question") or "").lower()


class GammaClient:
    def __init__(self, settings: Optional[Settings] = None, timeout: float = 15.0):
        self.settings = settings or Settings()
        self._client = httpx.Client(
            base_url=self.settings.gamma_api_url.rstrip("/"),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GammaClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_market_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Look up a single market (including closed ones) by slug."""
        r = self._client.get("/markets", params={"slug": slug, "limit": 1})
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return data[0]
        return None

    def fetch_recent_markets(self, limit: int = 100) -> List[Dict[str, Any]]:
        r = self._client.get(
            "/markets",
            params={
                "limit": limit,
                "active": "true",
                "closed": "false",
                "order": "createdAt",
                "ascending": "false",
            },
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []

    def list_updown_5m(
        self, assets: Optional[Sequence[str]] = None
    ) -> List[UpDownMarket]:
        """Active 5-minute crypto Up/Down markets from Gamma."""
        want = {a.upper() for a in assets} if assets else None
        seen_slugs: set[str] = set()
        out: List[UpDownMarket] = []

        for raw in self.fetch_recent_markets(limit=120):
            if not raw.get("active") or raw.get("closed"):
                continue
            if not _is_5m_updown_market(raw):
                continue

            slug = raw.get("slug") or ""
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            asset = _asset_from_slug(slug)
            if want and asset not in want:
                continue

            outcomes = _parse_json_list(raw.get("outcomes"))
            prices = _parse_json_list(raw.get("outcomePrices"))
            token_ids = _parse_json_list(raw.get("clobTokenIds"))
            if len(outcomes) < 2 or len(token_ids) < 2:
                continue

            up_idx = 0
            down_idx = 1
            for i, name in enumerate(outcomes):
                if str(name).lower() == "up":
                    up_idx = i
                elif str(name).lower() == "down":
                    down_idx = i

            def _f(idx: int, default: float = 0.5) -> float:
                try:
                    return float(prices[idx])
                except (IndexError, TypeError, ValueError):
                    return default

            out.append(
                UpDownMarket(
                    market_id=str(raw.get("id", "")),
                    asset=asset,
                    question=raw.get("question") or "",
                    slug=slug,
                    up_token_id=str(token_ids[up_idx]),
                    down_token_id=str(token_ids[down_idx]),
                    gamma_up_price=_f(up_idx),
                    gamma_down_price=_f(down_idx),
                    end_date=raw.get("endDate"),
                )
            )

        # One market per asset: keep the newest slug (highest epoch in slug)
        by_asset: Dict[str, UpDownMarket] = {}
        for m in out:
            prev = by_asset.get(m.asset)
            if prev is None or m.slug > prev.slug:
                by_asset[m.asset] = m
        return [by_asset[a] for a in sorted(by_asset.keys())]
