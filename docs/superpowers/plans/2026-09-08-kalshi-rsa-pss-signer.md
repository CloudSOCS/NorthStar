# Kalshi RSA-PSS Signer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Do not execute this plan until the human says `implement signer`.** Until those words, `kalshi-live book` must keep `sender=None`. Task 7 is the only `sender=` swap and is blocked until then.

**Goal:** After existing fail-closed gates, sign one IOC Create Order V2 POST with a temp-tested RSA-PSS signer; log HTTP 201 as `sent` and 429 as `rate_limited` with `sent: no`.

**Architecture:** Keep `src/poly/clients/kalshi.py` unsigned GET-only. Put PEM load, RSA-PSS sign, body mapping, and one `httpx` POST in `src/poly/execution/kalshi_signer.py`. `attempt_live_book` keeps every gate and maps sender results/errors onto `live_attempts.json`. CLI stays `sender=None` until Task 7.

**Tech Stack:** Python 3.9+, `httpx`, `cryptography` (Kalshi’s documented RSA-PSS), existing `LiveRequest` / `attempt_live_book`.

**Spec:** `docs/superpowers/specs/2026-09-08-kalshi-rsa-pss-signer-design.md`

**Verified against Kalshi Create Order V2 (2026-09-08):** `price` is `FixedPointDollars` (`"0.8000"`, not integer cents). `count` is `FixedPointCount` (fractional `"2.50"` allowed, min `0.01`). Do not guess other shapes in code. Re-read https://docs.kalshi.com/api-reference/orders/create-order-v2 before writing the POST body.

## Global Constraints

- Helper must not gain `kalshi-live`. Continue / `docs/GROK_BOT.md` unchanged.
- No PEM / keys in `/workspace` or git. Tests use a generated key under `tmp_path` only. Never read `~/.kalshi/` or the human `.env` PEM.
- `--i-approve-live`, `POLY_MODE=live`, spend in `($0, $5]`, no silent clamp, no `--last`, no 429 retry-to-fill.
- `--both` refused even on a cheap pair (one POST only).
- `src/poly/clients/kalshi.py` stays read-only (no `KALSHI-ACCESS-*` headers, no POST).
- `sender=None` in `src/poly/cli.py` until Task 7.
- YES = `bid` at `--yes-price`. NO = `ask` at `1 - no_price` on the YES book.
- IOC + new `client_order_id` every try. Do not reuse the id after a 429.
- HTTP 201 with `fill_count` `"0.00"` logs `status: sent`, `kind: live`, `sent: true` (venue accepted, nothing filled).
- HTTP 429: one POST, stop. Log `status: rate_limited`, `kind: live_attempt`, `sent: false`. `sent` means venue HTTP 201, not “a packet left the machine.”
- Generator stubbed. Graph stop. `execution/live.py` `run_live_loop` stays `NotImplementedError`.
- No pump.fun, Alpaca, batch create, or legacy `POST /portfolio/orders`.

## File map

| Path | Responsibility |
| --- | --- |
| `src/poly/execution/kalshi_signer.py` | PEM load, sign, `order_body`, one POST |
| `src/poly/execution/kalshi_live.py` | Gates, `--both` always refuse, log mapping, catch PEM `ValueError` as `refused_local` |
| `src/poly/cli.py` | Task 7 only: pass signer. Until then `sender=None` |
| `tests/test_kalshi_signer.py` | Temp RSA + mock HTTP |
| `tests/test_kalshi_live.py` | Gates, 429 `sent: no`, 201 extras, CLI `--last` absent |
| `pyproject.toml` | Add `cryptography` |
| `.gitignore` | `*.pem`, `*.key` |
| `src/poly/clients/kalshi.py` | Do not modify |
| `src/poly/execution/live.py` | Do not modify |
| `docs/GROK_BOT.md` | Do not modify |

---

### Task 1: Fail-closed `--both` + ignore key files + cryptography

**Files:**
- Modify: `src/poly/execution/kalshi_live.py`
- Modify: `tests/test_kalshi_live.py`
- Modify: `.gitignore`
- Modify: `pyproject.toml`
- Test: `tests/test_kalshi_live.py`

**Interfaces:**
- Consumes: existing `attempt_live_book`, `LiveRequest.both`
- Produces: `--both` always `_refuse`s before `sender`; `cryptography` installable for later tasks

- [ ] **Step 1: Write the failing test**

In `tests/test_kalshi_live.py`, add:

```python
def test_refuse_both_even_when_pair_is_cheap(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(
            both=True,
            yes_price=0.40,
            no_price=0.40,
            approve_not_ready=True,
        ),
        settings=_settings(pem=pem),
        log_path=log,
        sender=lambda *_a, **_k: pytest.fail("must not send"),
    )
    assert result.status == "refused_local"
    assert result.sent is False
    assert "one POST" in result.reason
    blob = json.loads(log.read_text())
    assert blob["attempts"][0]["status"] == "refused_local"
    assert blob["attempts"][0]["kind"] == LIVE_ATTEMPT_KIND
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_kalshi_live.py::test_refuse_both_even_when_pair_is_cheap -v`

Expected: FAIL (`must not send` or assertion on `"one POST"`), because cheap `--both` currently reaches `sender`.

- [ ] **Step 3: Write minimal implementation**

In `src/poly/execution/kalshi_live.py`, replace the pair-cost `--both` gate with:

```python
    if req.both:
        return _refuse(
            req,
            reason="Will not send both sides. One POST only. No order was sent.",
            log_path=path,
        )
```

Keep `pair_cost` import if still used elsewhere in the file; if not, leave the import (later tasks may still use it) or drop it only if unused.

`.gitignore` add:

```
*.pem
*.key
```

`pyproject.toml` dependencies add `"cryptography>=42.0"`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_kalshi_live.py -q`

Expected: PASS, including the old expensive-pair `--both` test (still refuse, reason text may now be the one-POST line — update that test to accept `"one POST"` or `"both sides"`).

If `test_refuse_both_when_pair_not_cheap` asserts `"hedge"` only, change it to:

```python
    assert "both sides" in result.reason.lower() or "one post" in result.reason.lower()
```

- [ ] **Step 5: Commit** (when executing this plan)

```bash
git add src/poly/execution/kalshi_live.py tests/test_kalshi_live.py .gitignore pyproject.toml
git commit -m "$(cat <<'EOF'
Refuse --both on live book so only one signed POST can fire.

EOF
)"
```

---

### Task 2: Order body mapping (no HTTP)

**Files:**
- Create: `src/poly/execution/kalshi_signer.py`
- Create: `tests/test_kalshi_signer.py`

**Interfaces:**
- Consumes: `LiveRequest` from `poly.execution.kalshi_live`; `tickets_bought` from `poly.practice.walk`
- Produces: `order_body(req: LiveRequest) -> Dict[str, Any]` with Kalshi V2 fields; `COUNT_TOO_SMALL = "Count below 0.01 contracts. No order was sent."`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_kalshi_signer.py`:

```python
from poly.execution.kalshi_live import LiveRequest
from poly.execution.kalshi_signer import COUNT_TOO_SMALL, order_body


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
```

`$0.001 / $0.80` formats below `0.01`. `attempt_live_book` already refuses `spend <= 0`; this check is on `order_body` only.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_kalshi_signer.py -v`

Expected: FAIL with `ModuleNotFoundError` or `cannot import order_body`.

- [ ] **Step 3: Write minimal implementation**

Create `src/poly/execution/kalshi_signer.py`:

```python
"""RSA-PSS signer for one Kalshi Create Order V2 POST. No retry. No loop."""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlparse
import uuid

from poly.execution.kalshi_live import LiveRequest
from poly.practice.walk import tickets_bought

COUNT_TOO_SMALL = "Count below 0.01 contracts. No order was sent."
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
```

Leave sign/POST functions for Task 3–4. Do not import `urlparse` yet.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_kalshi_signer.py -v`

Expected: PASS. If `test_order_body_no_is_ask_at_one_minus_no_price` fails on `"9.52"`, print `tickets_bought(2.0, 0.21)` and use that `.2f` string — do not invent a different count.

- [ ] **Step 5: Commit** (when executing)

```bash
git add src/poly/execution/kalshi_signer.py tests/test_kalshi_signer.py
git commit -m "$(cat <<'EOF'
Map live YES/NO to Kalshi V2 bid/ask dollar strings.

EOF
)"
```

---

### Task 3: RSA-PSS headers with a temp key (no HTTP)

**Files:**
- Modify: `src/poly/execution/kalshi_signer.py`
- Modify: `tests/test_kalshi_signer.py`

**Interfaces:**
- Consumes: PEM path; Kalshi sign string `{timestamp}{METHOD}{path without query}`
- Produces: `load_private_key(path: Path) -> Any`; `create_signature(private_key, timestamp: str, method: str, path: str) -> str`; `auth_headers(api_key_id: str, private_key, method: str, url: str) -> Dict[str, str]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_kalshi_signer.py`:

```python
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from poly.execution.kalshi_signer import (
    SIGN_PATH,
    auth_headers,
    create_signature,
    load_private_key,
)


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
    sig = create_signature(
        key, headers["KALSHI-ACCESS-TIMESTAMP"], "POST", SIGN_PATH
    )
    assert sig == headers["KALSHI-ACCESS-SIGNATURE"]
```

Do not point `_rsa_pem` at `Path.home() / ".kalshi"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_kalshi_signer.py::test_auth_headers_sign_full_trade_api_path -v`

Expected: FAIL (`cannot import` those names).

- [ ] **Step 3: Write minimal implementation**

Append to `src/poly/execution/kalshi_signer.py` (add imports at top: `base64`, `Path`, `datetime`, `urlparse`, `hashes`, `padding`, `serialization`, `default_backend`):

```python
import base64
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PEM_REFUSE = "Could not load RSA private key. No order was sent."


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
```

Confirm `urlparse("https://external-api.kalshi.com/trade-api/v2/portfolio/events/orders").path` equals `SIGN_PATH`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_kalshi_signer.py -v`

Expected: PASS.

- [ ] **Step 5: Commit** (when executing)

```bash
git add src/poly/execution/kalshi_signer.py tests/test_kalshi_signer.py
git commit -m "$(cat <<'EOF'
Sign Kalshi headers with RSA-PSS from a local PEM path.

EOF
)"
```

---

### Task 4: One mocked POST (201, 429 once, 400)

**Files:**
- Modify: `src/poly/execution/kalshi_signer.py`
- Modify: `tests/test_kalshi_signer.py`

**Interfaces:**
- Consumes: `order_body`, `auth_headers`, `load_private_key`, `Settings`
- Produces: `signed_create_order(req: LiveRequest, *, settings: Settings, client: Any = None) -> Dict[str, Any]`  
  On HTTP 201: `{accepted: True, order_id, fill_count, remaining_count, client_order_id}`  
  On other status: `httpx.HTTPStatusError` after **exactly one** `client.post`

- [ ] **Step 1: Write the failing tests**

```python
import httpx
import pytest

from poly.config import ExecutionMode, Settings
from poly.execution.kalshi_signer import BASE_URL, CREATE_PATH, signed_create_order


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.request = httpx.Request(
            "POST", BASE_URL + CREATE_PATH
        )

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.response


def _settings(pem: Path) -> Settings:
    return Settings(
        POLY_MODE=ExecutionMode.LIVE,
        KALSHI_API_KEY="key-id-uuid",
        KALSHI_PRIVATE_KEY_PATH=str(pem),
    )


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_kalshi_signer.py::test_signed_create_order_429_posts_once -v`

Expected: FAIL (`signed_create_order` missing).

- [ ] **Step 3: Write minimal implementation**

```python
import httpx

from poly.config import Settings


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
```

Do not loop. Do not call `KalshiClient._get_json`. `_FakeResponse` has no `raise_for_status`; the function must branch on `status_code` itself.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_kalshi_signer.py -v`

Expected: PASS.

- [ ] **Step 5: Commit** (when executing)

```bash
git add src/poly/execution/kalshi_signer.py tests/test_kalshi_signer.py
git commit -m "$(cat <<'EOF'
POST one signed Kalshi order and stop on 429.

EOF
)"
```

---

### Task 5: Log 201 extras; 429 stays `sent: no`

**Files:**
- Modify: `src/poly/execution/kalshi_live.py` (`attempt_live_book` sender success row and `ValueError` from sender)
- Modify: `tests/test_kalshi_live.py`

**Interfaces:**
- Consumes: sender dict keys `accepted`, `order_id`, `fill_count`, `remaining_count`, `client_order_id`
- Produces: success log row with those fields; `ValueError` from sender → `refused_local` (bad PEM), no HTTP

Clarify in the test comments: `sent` / `kind: live` means HTTP 201 (venue accepted, including IOC `fill_count` `0.00`). A 429 row is `sent: false` even though one POST occurred.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_kalshi_live.py`:

```python
def test_sent_row_keeps_fill_count_zero_as_live(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(edge=0.10),
        settings=_settings(pem=pem),
        log_path=log,
        sender=lambda req: {
            "accepted": True,
            "order_id": "ord-1",
            "fill_count": "0.00",
            "remaining_count": "2.50",
            "client_order_id": "client-1",
        },
    )
    assert result.status == "sent"
    assert result.sent is True
    row = json.loads(log.read_text())["attempts"][0]
    assert row["status"] == "sent"
    assert row["kind"] == "live"
    assert row["fill_count"] == "0.00"
    assert row["remaining_count"] == "2.50"
    assert row["client_order_id"] == "client-1"
    assert row["order_id"] == "ord-1"


def test_429_sent_means_not_accepted(tmp_path):
    """One POST happened. Venue did not accept. sent means HTTP 201, so this is no."""
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    calls = {"n": 0}

    def boom(_req):
        calls["n"] += 1
        raise httpx.HTTPStatusError(
            "429",
            request=httpx.Request("POST", "https://example.invalid"),
            response=httpx.Response(429),
        )

    result = attempt_live_book(
        _req(edge=0.10),
        settings=_settings(pem=pem),
        log_path=log,
        sender=boom,
    )
    assert calls["n"] == 1
    assert result.sent is False
    row = json.loads(log.read_text())["attempts"][0]
    assert row["status"] == "rate_limited"
    assert row["kind"] == LIVE_ATTEMPT_KIND
    assert row["kind"] != "live"


def test_bad_pem_valueerror_is_refused_local(tmp_path):
    pem = _pem(tmp_path)
    log = tmp_path / "live_attempts.json"
    result = attempt_live_book(
        _req(edge=0.10),
        settings=_settings(pem=pem),
        log_path=log,
        sender=lambda _req: (_ for _ in ()).throw(
            ValueError("Could not load RSA private key. No order was sent.")
        ),
    )
    assert result.status == "refused_local"
    assert result.sent is False
    assert json.loads(log.read_text())["attempts"][0]["kind"] == LIVE_ATTEMPT_KIND
```

`test_429_sent_means_not_accepted` overlaps `test_429_logs_rate_limited_and_does_not_retry`. Keep both or extend the existing 429 test with `assert result.sent is False` and `kind != "live"` instead of duplicating. Prefer extending the existing test; add only the 201 extras + ValueError tests if the 429 test already covers one POST.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_kalshi_live.py::test_sent_row_keeps_fill_count_zero_as_live tests/test_kalshi_live.py::test_bad_pem_valueerror_is_refused_local -v`

Expected: FAIL (missing log keys / uncaught `ValueError`).

- [ ] **Step 3: Write minimal implementation**

In `attempt_live_book`, wrap sender:

```python
    try:
        reply = sender(req)
    except ValueError as exc:
        return _refuse(req, reason=str(exc), log_path=path, extra_lines=["", step2])
    except httpx.HTTPStatusError as exc:
        ...
```

On accepted success row, add:

```python
        "fill_count": reply.get("fill_count"),
        "remaining_count": reply.get("remaining_count"),
        "client_order_id": reply.get("client_order_id"),
```

Do not change 429 logging: `status: rate_limited`, `kind: live_attempt`, `sent=False`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_kalshi_live.py tests/test_kalshi_signer.py -q`

Expected: PASS.

- [ ] **Step 5: Commit** (when executing)

```bash
git add src/poly/execution/kalshi_live.py tests/test_kalshi_live.py
git commit -m "$(cat <<'EOF'
Log IOC zero fills as sent and 429 as not accepted.

EOF
)"
```

---

### Task 6: Prove CLI still does not send (pre-wire)

**Files:**
- Modify: `tests/test_kalshi_live.py` only

**Interfaces:**
- Consumes: `poly.cli.kalshi_live_book` source; `CONTINUE`; `kalshi.py` source
- Produces: tests that fail if someone wires `sender=` or adds `--last` or signs in `kalshi.py` early

- [ ] **Step 1: Write / extend tests**

Keep `test_kalshi_live_book_requires_explicit_ticker` (`--ticker` present, `--last` absent).

Add:

```python
def test_cli_book_still_passes_sender_none():
    import inspect
    from poly.cli import kalshi_live_book

    source = inspect.getsource(kalshi_live_book)
    assert "sender=None" in source
    assert "signed_create_order" not in source
    assert "make_sender" not in source


def test_kalshi_client_has_no_rsa_headers():
    import inspect
    from poly.clients import kalshi

    source = inspect.getsource(kalshi)
    assert "KALSHI-ACCESS-SIGNATURE" not in source
    assert "RSA" not in source
    assert "PSS" not in source
```

Existing `test_status_continue_and_fence_unchanged` must still assert no `kalshi-live` on `CONTINUE`.

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_kalshi_live.py tests/test_kalshi_signer.py tests/test_status.py -q`

Expected: PASS while CLI still has `sender=None`.

- [ ] **Step 3: Full suite**

Run: `uv run pytest -q`

Expected: all pass.

- [ ] **Step 4: Commit** (when executing)

```bash
git add tests/test_kalshi_live.py
git commit -m "$(cat <<'EOF'
Keep kalshi-live unwired until the signer is explicitly turned on.

EOF
)"
```

---

### Task 7: Wire CLI sender — **blocked**

**Do not start this task until the human says `implement signer` and Tasks 1–6 are done.**

**Files:**
- Modify: `src/poly/cli.py` (`kalshi_live_book`)
- Modify: `tests/test_kalshi_live.py` (`test_cli_book_still_passes_sender_none` becomes a wired assertion)

**Interfaces:**
- Consumes: `signed_create_order`
- Produces: production `kalshi-live book` passes a sender that closes over `Settings()`

- [ ] **Step 1: Replace the CLI-unwired test**

```python
def test_cli_book_wires_signed_create_order():
    import inspect
    from poly.cli import kalshi_live_book

    source = inspect.getsource(kalshi_live_book)
    assert "signed_create_order" in source
    assert "sender=None" not in source
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_kalshi_live.py::test_cli_book_wires_signed_create_order -v`

Expected: FAIL while `sender=None` remains.

- [ ] **Step 3: Wire**

In `src/poly/cli.py`:

- Import `signed_create_order` from `poly.execution.kalshi_signer`.
- Change `attempt_live_book(..., settings=Settings(), sender=None)` to:

```python
    settings = Settings()
    result = attempt_live_book(
        LiveRequest(...),
        settings=settings,
        sender=lambda req: signed_create_order(req, settings=settings),
    )
```

Do not add `--last`. Do not pass a real PEM into tests. Helper allowlist unchanged.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_kalshi_live.py tests/test_kalshi_signer.py tests/test_status.py -q && uv run pytest -q`

Expected: PASS. `test_production_sender_does_not_exist_no_network` still calls `attempt_live_book(..., sender=None)` directly and must keep passing (unit path, not CLI).

- [ ] **Step 5: Commit** (when executing)

```bash
git add src/poly/cli.py tests/test_kalshi_live.py
git commit -m "$(cat <<'EOF'
Send one approved Kalshi order through the RSA-PSS signer.

EOF
)"
```

---

## Self-review (plan vs spec)

| Spec item | Task |
| --- | --- |
| Signer in `kalshi_signer.py` | 2–4 |
| Keys env-only, temp RSA in tests | 3–4 |
| YES bid / NO ask at `1 - no_price` | 2 |
| IOC + new `client_order_id` | 2 |
| V2 dollar `price` / fractional `count` | 2 (verified, not cents/integers) |
| One POST, 429 no retry | 4 |
| 201 `fill_count` 0.00 → `sent` / `kind: live` | 5 |
| 429 → `sent: no`, `kind: live_attempt` | 5 |
| `--both` even if cheap | 1 |
| `kalshi.py` read-only | 6 |
| `sender=None` until words | 6–7 |
| Helper / graph / generator / no `--last` | Global + 6 |
| `cryptography` + gitignore pem | 1 |
