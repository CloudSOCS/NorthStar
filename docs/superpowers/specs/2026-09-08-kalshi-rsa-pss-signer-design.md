# Kalshi RSA-PSS signer — Phase 3 door 3b

**Date:** 2026-09-08
**Status:** Approved design. No live-send code until the human says **implement signer**.
**Scope:** One-shot signed `CreateOrder` V2 from `northstar kalshi-live book` after existing fail-closed gates. Mac Mini only.

Official sources: [Authenticated requests](https://docs.kalshi.com/getting_started/quick_start_authenticated_requests), [Create Order V2](https://docs.kalshi.com/api-reference/orders/create-order-v2), [Create your first order](https://docs.kalshi.com/getting_started/quick_start_create_order).

## 1. Goal

Replace the current `sender=None` refuse (*This repo has no RSA-PSS signer*) with one RSA-PSS signed POST when every gate has already passed. Still one human invocation. Still no helper live. Still no auto loop.

`src/poly/clients/kalshi.py` stays a public GET client. It must not sign, POST, or retry a fill.

## 2. Locked fences

- Helper must not gain `kalshi-live`. Continue / `GROK_BOT.md` allowlist unchanged.
- No PEM or API keys in `/workspace` or git. Path is env-only: `KALSHI_PRIVATE_KEY_PATH`.
- Gates already in `attempt_live_book` stay: `--i-approve-live`, `POLY_MODE=live`, keys present on this machine, spend in `($0, $5]`, no `--last`, no 429 retry-to-fill, `--both` refused when pair ≥ $1.
- This increment also refuses `--both` even when the pair is cheap (one POST only).
- Generator stays stubbed. Graph command stays stop. `execution/live.py` `run_live_loop` stays `NotImplementedError`.
- `--spend` stays required on the CLI. Teaching default is $2. No silent clamp; over $5 or ≤ $0 refuses locally.

## 3. Where the signer lives

| Path | Role |
| --- | --- |
| `src/poly/execution/kalshi_signer.py` | Load PEM from disk. Sign one POST. Return or raise. Mac-only in practice: no PEM, no send. |
| `src/poly/execution/kalshi_live.py` | Unchanged gates. After implement: CLI passes this sender instead of `None`. |
| `src/poly/cli.py` `kalshi_live_book` | After implement: `sender=signed_create_order`. Until then: `sender=None`. |
| `src/poly/clients/kalshi.py` | Read-only. Do not add auth headers. |
| `src/poly/execution/live.py` | Do not wire the signer here. |

Add `cryptography` (what Kalshi’s docs use). Add `*.pem` and `*.key` to `.gitignore`.

## 4. Keys

| Env | Meaning |
| --- | --- |
| `KALSHI_API_KEY` | API Key ID → header `KALSHI-ACCESS-KEY` |
| `KALSHI_PRIVATE_KEY_PATH` | PEM on this Mac → RSA-PSS SHA256, MGF1 SHA256, salt length = digest length |

Sign string (no query, no body): `{timestamp_ms}POST/trade-api/v2/portfolio/events/orders`

Headers: `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-TIMESTAMP`, `KALSHI-ACCESS-SIGNATURE`, `Content-Type: application/json`.

Unreadable file or non-RSA PEM → `refused_local`, no POST. Never log PEM, key bytes, or the signature.

Production base URL (same host family as the read-only client): `https://external-api.kalshi.com/trade-api/v2`. HTTP path `/portfolio/events/orders`. Signed path is the full URL path from the API root: `/trade-api/v2/portfolio/events/orders`.

## 5. Exact request after all gates pass

Verified 2026-09-08 against Create Order V2 (`FixedPointDollars`, `FixedPointCount`) and the official create-order quick start. Wire format is **not** integer cents and **not** whole contracts only.

- `price`: string dollars, 2–4 decimal places (example `"0.5600"`, 1¢ is `"0.0100"`). Do not send `80`.
- `count`: string contracts, 0–2 decimal places. Fractional values such as `"2.50"` are supported; minimum `0.01`.

One POST. New `client_order_id` (UUID4) every invocation. Do not reuse it to retry a 429.

YES (`--side yes`): buy YES on the YES book.

```json
{
  "ticker": "<explicit --ticker>",
  "side": "bid",
  "count": "<spend / yes_price, two decimals>",
  "price": "<yes_price, four decimals>",
  "time_in_force": "immediate_or_cancel",
  "self_trade_prevention_type": "taker_at_cross",
  "client_order_id": "<uuid4>"
}
```

Example: `--spend 2 --yes-price 0.80` → `"count": "2.50"`, `"price": "0.8000"`.

NO (`--side no`): Kalshi V2 quotes the YES book only. `ask` = sell YES = buy NO at `1 − price`.

```json
{
  "ticker": "<explicit --ticker>",
  "side": "ask",
  "count": "<spend / no_price, two decimals>",
  "price": "<1 - no_price, four decimals>",
  "time_in_force": "immediate_or_cancel",
  "self_trade_prevention_type": "taker_at_cross",
  "client_order_id": "<uuid4>"
}
```

Example: `--spend 2 --no-price 0.21` → `"count": "9.52"` (`f"{tickets_bought(spend, no_price):.2f}"`), `"price": "0.7900"`.

`count` below `0.01` after that format → `refused_local`, no POST. `--both` is refused in `attempt_live_book` for this increment even when the pair is cheap.

IOC: do not rest a GTC order. HTTP 201 with `fill_count` `0.00` is still `sent` (venue accepted; nothing filled). No retry.

## 6. `live_attempts.json`

File: `~/.poly/live_attempts.json` (`NORTHSTAR_LIVE_ATTEMPTS` in tests). Append-only. No graph write. Do not log PEM or signature.

| Event | `status` | `kind` | `sent` | Meaning |
| --- | --- | --- | --- | --- |
| Gate fail, bad PEM, missing keys | `refused_local` | `live_attempt` | no | Never POSTed |
| HTTP 429 (one POST, then stop) | `rate_limited` | `live_attempt` | no | POSTed once; venue did not accept. `sent` means HTTP 201 (accepted as a live order, including IOC `fill_count` `0.00`), not “a packet left the machine.” |
| HTTP 400 / 401 / 409 / 5xx | `rejected` | `live_attempt` | no | POSTed; venue rejected |
| HTTP 201 | `sent` | `live` | yes | Venue accepted. IOC with `fill_count` `0.00` is still this row |

Success row also stores `order_id`, `client_order_id`, `fill_count`, `remaining_count`. Rejected row may store venue `code` / `message` text, not headers.

Existing 429 / reject / accept handling in `attempt_live_book` stays. Signer raises `httpx.HTTPStatusError` on non-201 (including 429). Signer returns `{accepted: True, order_id, fill_count, remaining_count, client_order_id}` on 201.

## 7. Tests (when implementing)

- Gates still refuse without calling the signer (approve, `POLY_MODE`, keys, spend, `--both`, not-ready).
- CLI still has `--ticker` required and no `--last`.
- Signer unit tests: temp RSA key in `tmp_path` (never the real PEM). Mock httpx. Assert signed path, headers present, body mapping for YES and NO, one POST on 429 (no second call).
- Production tests must not read `~/.kalshi/` or the human’s `.env` PEM.
- Continue / helper allowlist still has no `kalshi-live`.

## 8. Will not build

Helper `kalshi-live`. `run_live_loop`. `--last` auto-send. 429 retry-to-fill. Batch create. Legacy `POST /portfolio/orders`. Graph writes. Generator. pump.fun. Alpaca. Keys in the repo.

## 9. Implementation trigger

Do not write signer or change `sender=None` until the human says **implement signer**.
