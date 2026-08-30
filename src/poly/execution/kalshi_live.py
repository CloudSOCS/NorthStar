"""One-shot Kalshi live book. Fail-closed. This repo has no RSA-PSS signer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
import json
import os
import uuid

import httpx

from poly.config import ExecutionMode, Settings
from poly.practice.walk import lose_pnl, pair_cost, tickets_bought, win_pnl

LIVE_SCHEMA = 1
LIVE_ATTEMPT_KIND = "live_attempt"
LIVE_REFUSE_FOOTER = "No live order was placed."
RATE_LIMIT_LINE = "Kalshi rate-limited. No order was sent. No retry."
NO_SIGNER = (
    "Kalshi client is read-only. This repo has no RSA-PSS signer. "
    "No order was sent."
)
MAX_LIVE_SPEND = 5.0
DEFAULT_LIVE_SPEND = 2.0


@dataclass(frozen=True)
class LiveRequest:
    ticker: str
    side: str
    spend: float
    yes_price: float
    no_price: float
    edge: Union[str, float]
    approve_live: bool
    approve_not_ready: bool = False
    both: bool = False


@dataclass
class LiveResult:
    status: str
    reason: str
    message: str
    sent: bool = False


Sender = Callable[[LiveRequest], Dict[str, Any]]


def default_live_attempts_path() -> Path:
    override = os.environ.get("NORTHSTAR_LIVE_ATTEMPTS")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".poly" / "live_attempts.json"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_attempts(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"schema_version": LIVE_SCHEMA, "attempts": []}
    blob = json.loads(path.read_text())
    if blob.get("schema_version") != LIVE_SCHEMA:
        raise ValueError(f"Unsupported live attempts schema_version: {blob.get('schema_version')}")
    attempts = blob.get("attempts")
    if not isinstance(attempts, list):
        raise ValueError("Live attempts file is missing an attempts list")
    return {"schema_version": LIVE_SCHEMA, "attempts": attempts}


def load_live_attempts(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only load. Missing file → empty. Never writes the graph."""
    return _read_attempts(path or default_live_attempts_path())


def _append_attempt(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = _read_attempts(path)
    blob["attempts"].append(row)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=2) + "\n")
    tmp.replace(path)


def _edge_not_ready(edge: Union[str, float]) -> bool:
    if edge is None:
        return True
    if isinstance(edge, str) and edge.strip().lower() in ("not ready", "not-ready"):
        return True
    return False


def _ticket_price(req: LiveRequest) -> float:
    return req.yes_price if req.side == "yes" else req.no_price


def _step2_text(req: LiveRequest) -> str:
    price = _ticket_price(req)
    tickets = tickets_bought(req.spend, price)
    win = win_pnl(req.spend, price)
    lose = lose_pnl(req.spend, price)
    side = req.side.upper()
    return (
        f"{req.ticker}  Side: {side}  kind: live_attempt\n"
        f"Ticket price: {price:.2f} ({price * 100:.0f}¢)\n"
        f"${req.spend:.2f} → {tickets:.2f} tickets.\n"
        f"If {side} wins: profit {_signed(win)}.\n"
        f"If {side} loses: {_signed(lose)}."
    )


def _signed(amount: float) -> str:
    sign = "+" if amount >= 0 else "-"
    return f"{sign}${abs(amount):.2f}"


def _keys_ready(settings: Settings) -> bool:
    key = (settings.kalshi_api_key or "").strip()
    pem = (settings.kalshi_private_key_path or "").strip()
    return bool(key) and bool(pem) and Path(pem).expanduser().is_file()


def _refuse(
    req: LiveRequest,
    *,
    reason: str,
    log_path: Path,
    extra_lines: Optional[List[str]] = None,
) -> LiveResult:
    price = _ticket_price(req)
    row = {
        "id": uuid.uuid4().hex[:8],
        "attempted_at": _now(),
        "kind": LIVE_ATTEMPT_KIND,
        "status": "refused_local",
        "ticker": req.ticker,
        "side": req.side,
        "spend": req.spend,
        "ticket_price": round(price, 4),
        "reason": reason,
    }
    _append_attempt(log_path, row)
    lines = [reason]
    if extra_lines:
        lines.extend(extra_lines)
    lines.append(LIVE_REFUSE_FOOTER)
    return LiveResult(
        status="refused_local",
        reason=reason,
        message="\n".join(lines) + "\n",
        sent=False,
    )


def attempt_live_book(
    req: LiveRequest,
    *,
    settings: Settings,
    log_path: Optional[Path] = None,
    sender: Optional[Sender] = None,
) -> LiveResult:
    """Fail-closed one-shot. Does not write the graph. Default sender does not sign."""
    path = log_path or default_live_attempts_path()
    side = req.side.strip().lower()
    if side not in ("yes", "no"):
        return _refuse(req, reason="side must be yes or no", log_path=path)
    req = LiveRequest(
        ticker=req.ticker,
        side=side,
        spend=req.spend,
        yes_price=req.yes_price,
        no_price=req.no_price,
        edge=req.edge,
        approve_live=req.approve_live,
        approve_not_ready=req.approve_not_ready,
        both=req.both,
    )

    if not req.approve_live:
        return _refuse(
            req,
            reason="Pass --i-approve-live on this invocation. No order was sent.",
            log_path=path,
        )
    if settings.poly_mode != ExecutionMode.LIVE:
        return _refuse(
            req,
            reason="POLY_MODE must be live. No order was sent.",
            log_path=path,
        )
    if not _keys_ready(settings):
        return _refuse(
            req,
            reason="KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH are required on this machine. No order was sent.",
            log_path=path,
        )
    if req.spend <= 0 or req.spend > MAX_LIVE_SPEND:
        return _refuse(
            req,
            reason=f"Spend must be from $0.01 to ${MAX_LIVE_SPEND:.0f}. No silent clamp. No order was sent.",
            log_path=path,
        )
    if req.both and pair_cost(req.yes_price, req.no_price) >= 1.0:
        return _refuse(
            req,
            reason="Will not book both sides. Pair is not a cheap hedge (need pair cost under $1).",
            log_path=path,
        )
    if _edge_not_ready(req.edge) and not req.approve_not_ready:
        return _refuse(
            req,
            reason=(
                "Guess: not ready. Will not invent a number. "
                "Pass --i-approve-not-ready to send anyway. No order was sent."
            ),
            log_path=path,
        )

    step2 = _step2_text(req)
    if sender is None:
        return _refuse(req, reason=NO_SIGNER, log_path=path, extra_lines=["", step2])

    try:
        reply = sender(req)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        if response is not None and response.status_code == 429:
            row = {
                "id": uuid.uuid4().hex[:8],
                "attempted_at": _now(),
                "kind": LIVE_ATTEMPT_KIND,
                "status": "rate_limited",
                "ticker": req.ticker,
                "side": req.side,
                "spend": req.spend,
                "ticket_price": round(_ticket_price(req), 4),
                "reason": RATE_LIMIT_LINE,
            }
            _append_attempt(path, row)
            return LiveResult(
                status="rate_limited",
                reason=RATE_LIMIT_LINE,
                message=f"{step2}\n\n{RATE_LIMIT_LINE}\n{LIVE_REFUSE_FOOTER}\n",
                sent=False,
            )
        reason = f"Venue rejected the order. {exc}"
        row = {
            "id": uuid.uuid4().hex[:8],
            "attempted_at": _now(),
            "kind": LIVE_ATTEMPT_KIND,
            "status": "rejected",
            "ticker": req.ticker,
            "side": req.side,
            "spend": req.spend,
            "ticket_price": round(_ticket_price(req), 4),
            "reason": reason,
        }
        _append_attempt(path, row)
        return LiveResult(
            status="rejected",
            reason=reason,
            message=f"{step2}\n\n{reason}\n{LIVE_REFUSE_FOOTER}\n",
            sent=False,
        )

    accepted = bool(reply.get("accepted"))
    if not accepted:
        reason = str(reply.get("reason") or "Venue did not accept the order.")
        row = {
            "id": uuid.uuid4().hex[:8],
            "attempted_at": _now(),
            "kind": LIVE_ATTEMPT_KIND,
            "status": "rejected",
            "ticker": req.ticker,
            "side": req.side,
            "spend": req.spend,
            "ticket_price": round(_ticket_price(req), 4),
            "reason": reason,
        }
        _append_attempt(path, row)
        return LiveResult(
            status="rejected",
            reason=reason,
            message=f"{step2}\n\n{reason}\n{LIVE_REFUSE_FOOTER}\n",
            sent=False,
        )

    row = {
        "id": uuid.uuid4().hex[:8],
        "attempted_at": _now(),
        "kind": "live",
        "status": "sent",
        "ticker": req.ticker,
        "side": req.side,
        "spend": req.spend,
        "ticket_price": round(_ticket_price(req), 4),
        "reason": "venue accepted",
        "order_id": reply.get("order_id"),
    }
    _append_attempt(path, row)
    return LiveResult(
        status="sent",
        reason="venue accepted",
        message=(
            f"{step2}\n\nLive order submitted under the ${MAX_LIVE_SPEND:.0f} cap. "
            "Helper must not live-trade.\n"
        ),
        sent=True,
    )
