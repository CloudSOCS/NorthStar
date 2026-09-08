from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from poly.config import ExecutionMode, Settings
from poly.execution.kalshi_live import LiveRequest
from poly.execution.kalshi_signer import (
    BASE_URL,
    COUNT_TOO_SMALL,
    CREATE_PATH,
    SIGN_PATH,
    auth_headers,
    create_signature,
    load_private_key,
    order_body,
    signed_create_order,
)


def _req(**overrides) -> LiveRequest:
    data = dict(
        ticker="KXBTC15M-TEST",
        side="yes",
        spend=2.0,
        yes_price=0.80,
        no_price=0.21,
        edge=0.10,
        approve_live=True,
        approve_not_ready=False,
        both=False,
    )
    data.update(overrides)
    return LiveRequest(**data)


def _rsa_pem(tmp_path: Path) -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "unit.pem"
    path.write_bytes(pem)
    return path


def _settings(pem: Path) -> Settings:
    return Settings(
        POLY_MODE=ExecutionMode.LIVE,
        KALSHI_API_KEY="key-id-uuid",
        KALSHI_PRIVATE_KEY_PATH=str(pem),
    )


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.request = httpx.Request("POST", BASE_URL + CREATE_PATH)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.response


def test_order_body_yes_is_bid_at_yes_price():
    body = order_body(_req(side="yes", spend=2.0, yes_price=0.80))
    assert body["ticker"] == "KXBTC15M-TEST"
    assert body["side"] == "bid"
    assert body["count"] == "2.50"
    assert body["price"] == "0.8000"
    assert body["time_in_force"] == "immediate_or_cancel"
    assert body["self_trade_prevention_type"] == "taker_at_cross"
    assert body["client_order_id"]
    assert body["price"] != 80
    assert body["count"] != 2


def test_order_body_no_is_ask_at_one_minus_no_price():
    body = order_body(_req(side="no", spend=2.0, no_price=0.21))
    assert body["side"] == "ask"
    assert body["count"] == "9.52"
    assert body["price"] == "0.7900"


def test_order_body_new_client_order_id_each_call():
    a = order_body(_req())
    b = order_body(_req())
    assert a["client_order_id"] != b["client_order_id"]


def test_order_body_refuses_count_below_min():
    try:
        order_body(_req(spend=0.001, yes_price=0.80))
    except ValueError as exc:
        assert str(exc) == COUNT_TOO_SMALL
    else:
        raise AssertionError("expected refuse")


def test_load_private_key_rejects_garbage(tmp_path):
    path = tmp_path / "bad.pem"
    path.write_text("-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n")
    try:
        load_private_key(path)
    except ValueError as exc:
        assert "RSA" in str(exc) or "private key" in str(exc).lower()
        assert "No order was sent" in str(exc)
    else:
        raise AssertionError("expected refuse")


def test_auth_headers_sign_full_trade_api_path(tmp_path):
    pem = _rsa_pem(tmp_path)
    key = load_private_key(pem)
    headers = auth_headers(
        "key-id-uuid",
        key,
        "POST",
        "https://external-api.kalshi.com/trade-api/v2/portfolio/events/orders",
    )
    assert headers["KALSHI-ACCESS-KEY"] == "key-id-uuid"
    assert headers["KALSHI-ACCESS-TIMESTAMP"].isdigit()
    assert headers["KALSHI-ACCESS-SIGNATURE"]
    assert "BEGIN" not in headers["KALSHI-ACCESS-SIGNATURE"]
    from urllib.parse import urlparse

    assert (
        urlparse(
            "https://external-api.kalshi.com/trade-api/v2/portfolio/events/orders"
        ).path
        == SIGN_PATH
    )
    sig = create_signature(key, headers["KALSHI-ACCESS-TIMESTAMP"], "POST", SIGN_PATH)
    assert sig
    assert "BEGIN" not in sig


def test_signed_create_order_201_yes(tmp_path):
    pem = _rsa_pem(tmp_path)
    client = _FakeClient(
        _FakeResponse(
            201,
            {
                "order_id": "ord-1",
                "fill_count": "0.00",
                "remaining_count": "2.50",
            },
        )
    )
    reply = signed_create_order(
        _req(side="yes"),
        settings=_settings(pem),
        client=client,
    )
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"].endswith("/portfolio/events/orders")
    assert call["json"]["side"] == "bid"
    assert call["json"]["price"] == "0.8000"
    assert call["json"]["count"] == "2.50"
    assert "KALSHI-ACCESS-SIGNATURE" in call["headers"]
    assert reply == {
        "accepted": True,
        "order_id": "ord-1",
        "fill_count": "0.00",
        "remaining_count": "2.50",
        "client_order_id": call["json"]["client_order_id"],
    }


def test_signed_create_order_429_posts_once(tmp_path):
    pem = _rsa_pem(tmp_path)
    client = _FakeClient(_FakeResponse(429, text="rate limited"))
    try:
        signed_create_order(_req(), settings=_settings(pem), client=client)
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 429
    else:
        raise AssertionError("expected 429")
    assert len(client.calls) == 1


def test_signed_create_order_400_is_http_error(tmp_path):
    pem = _rsa_pem(tmp_path)
    client = _FakeClient(_FakeResponse(400, {"code": "bad", "message": "nope"}))
    with pytest.raises(httpx.HTTPStatusError):
        signed_create_order(_req(), settings=_settings(pem), client=client)
    assert len(client.calls) == 1
