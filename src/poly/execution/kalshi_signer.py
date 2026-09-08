"""RSA-PSS signer for one Kalshi Create Order V2 POST. No retry. No loop."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse
import base64
import uuid

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from poly.config import Settings
from poly.execution.kalshi_live import LiveRequest
from poly.practice.walk import tickets_bought

COUNT_TOO_SMALL = "Count below 0.01 contracts. No order was sent."
PEM_REFUSE = "Could not load RSA private key. No order was sent."
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
CREATE_PATH = "/portfolio/events/orders"
SIGN_PATH = "/trade-api/v2/portfolio/events/orders"


def order_body(req: LiveRequest) -> Dict[str, Any]:
    side = req.side.strip().lower()
    if side == "yes":
        book = "bid"
        price = float(req.yes_price)
        ticket = float(req.yes_price)
    elif side == "no":
        book = "ask"
        price = 1.0 - float(req.no_price)
        ticket = float(req.no_price)
    else:
        raise ValueError("side must be yes or no")
    count = f"{tickets_bought(req.spend, ticket):.2f}"
    if float(count) < 0.01:
        raise ValueError(COUNT_TOO_SMALL)
    return {
        "ticker": req.ticker,
        "side": book,
        "count": count,
        "price": f"{price:.4f}",
        "time_in_force": "immediate_or_cancel",
        "self_trade_prevention_type": "taker_at_cross",
        "client_order_id": str(uuid.uuid4()),
    }


def load_private_key(path: Path):
    try:
        data = Path(path).expanduser().read_bytes()
        return serialization.load_pem_private_key(
            data, password=None, backend=default_backend()
        )
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(PEM_REFUSE) from exc


def create_signature(private_key, timestamp: str, method: str, path: str) -> str:
    path_without_query = path.split("?")[0]
    message = f"{timestamp}{method}{path_without_query}".encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def auth_headers(api_key_id: str, private_key, method: str, url: str) -> Dict[str, str]:
    timestamp = str(int(datetime.now(tz=timezone.utc).timestamp() * 1000))
    sign_path = urlparse(url).path
    signature = create_signature(private_key, timestamp, method, sign_path)
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json",
    }


def signed_create_order(
    req: LiveRequest,
    *,
    settings: Settings,
    client: Any = None,
) -> Dict[str, Any]:
    body = order_body(req)
    key = load_private_key(Path(settings.kalshi_private_key_path or ""))
    url = BASE_URL.rstrip("/") + CREATE_PATH
    headers = auth_headers(str(settings.kalshi_api_key or ""), key, "POST", url)
    own = client is None
    http = client or httpx.Client(timeout=15.0)
    try:
        response = http.post(url, headers=headers, json=body)
    finally:
        if own:
            http.close()
    if response.status_code == 429:
        raise httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=response.request,
            response=response,
        )
    if response.status_code != 201:
        raise httpx.HTTPStatusError(
            f"Kalshi HTTP {response.status_code}",
            request=response.request,
            response=response,
        )
    payload = response.json() if hasattr(response, "json") else {}
    return {
        "accepted": True,
        "order_id": payload.get("order_id"),
        "fill_count": payload.get("fill_count"),
        "remaining_count": payload.get("remaining_count"),
        "client_order_id": body["client_order_id"],
    }
