from __future__ import annotations

from typing import Optional

import httpx

from poly.config import Settings


class ClobClient:
    """Read-only CLOB price fetches."""

    def __init__(self, settings: Optional[Settings] = None, timeout: float = 10.0):
        self.settings = settings or Settings()
        self._client = httpx.Client(
            base_url=self.settings.clob_api_url.rstrip("/"),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ClobClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_midpoint(self, token_id: str) -> Optional[float]:
        r = self._client.get("/midpoint", params={"token_id": token_id})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        mid = data.get("mid")
        if mid is None:
            return None
        return float(mid)

    def get_buy_price(self, token_id: str) -> Optional[float]:
        r = self._client.get("/price", params={"token_id": token_id, "side": "buy"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        price = data.get("price")
        if price is None:
            return None
        return float(price)
