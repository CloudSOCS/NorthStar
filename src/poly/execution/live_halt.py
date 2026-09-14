"""Live-loss circuit breaker. File is the halt. Helper cannot lift it."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import json
import os

from poly.practice.walk import lose_pnl, win_pnl

HALT_SCHEMA = 1
LOSS_LIMIT = 100.0
BOOK_HALT_LINE = (
    "Live trading halted. Realized live losses reached $100. No order was sent."
)
RESUME_FLAG_REFUSE = (
    "Pass --i-clear-loss-halt to lift the live-loss halt. Halt unchanged."
)
HALT_READ_REFUSE = "Could not read live halt. No order was sent."
MANUAL_REASON = "manual"
CLEARED_REASON = "cleared"
LOSS_REASON = "loss"


def default_halt_path() -> Path:
    override = os.environ.get("NORTHSTAR_LIVE_HALT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".poly" / "live_halt.json"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def empty_halt() -> Dict[str, Any]:
    return {
        "schema_version": HALT_SCHEMA,
        "halted": False,
        "reason": None,
        "realized_live_pnl": None,
        "halted_at": None,
    }


def _read_halt(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return empty_halt()
    blob = json.loads(path.read_text())
    if blob.get("schema_version") != HALT_SCHEMA:
        raise ValueError(f"Unsupported live halt schema_version: {blob.get('schema_version')}")
    if "halted" not in blob:
        raise ValueError("Live halt file is missing halted")
    return {
        "schema_version": HALT_SCHEMA,
        "halted": bool(blob.get("halted")),
        "reason": blob.get("reason"),
        "realized_live_pnl": blob.get("realized_live_pnl"),
        "halted_at": blob.get("halted_at"),
    }


def load_halt(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only load. Missing file → not halted. Never writes."""
    return _read_halt(path or default_halt_path())


def save_halt(blob: Dict[str, Any], path: Optional[Path] = None) -> Path:
    path = path or default_halt_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=2) + "\n")
    tmp.replace(path)
    return path


def is_halted(path: Optional[Path] = None) -> bool:
    return bool(load_halt(path).get("halted"))


def write_manual_halt(path: Optional[Path] = None) -> Dict[str, Any]:
    prior = load_halt(path)
    blob = {
        "schema_version": HALT_SCHEMA,
        "halted": True,
        "reason": MANUAL_REASON,
        "realized_live_pnl": prior.get("realized_live_pnl"),
        "halted_at": _now(),
    }
    save_halt(blob, path)
    return blob


def clear_halt(path: Optional[Path] = None) -> Dict[str, Any]:
    prior = load_halt(path)
    blob = {
        "schema_version": HALT_SCHEMA,
        "halted": False,
        "reason": CLEARED_REASON,
        "realized_live_pnl": prior.get("realized_live_pnl"),
        "halted_at": None,
    }
    save_halt(blob, path)
    return blob


STATUS_HALT_UNKNOWN = "unknown"
STATUS_HALT_UNKNOWN_LINE = "Live halt: unknown (Mini only)"


def status_halt_view(path: Optional[Path] = None) -> str:
    """on/off if this machine has a readable halt file. Missing → unknown. Never writes."""
    path = path or default_halt_path()
    if not path.exists():
        return STATUS_HALT_UNKNOWN
    try:
        blob = _read_halt(path)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return STATUS_HALT_UNKNOWN
    return "on" if blob.get("halted") else "off"


def format_status_halt_line(state: str) -> str:
    if state == STATUS_HALT_UNKNOWN:
        return STATUS_HALT_UNKNOWN_LINE
    return f"Live halt: {state}"


def _fill_count(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _is_closed_live_fill(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("kind") or "") != "live":
        return False
    if str(row.get("status") or "") != "sent":
        return False
    return _fill_count(row.get("fill_count")) > 0


def realized_live_pnl(
    attempts: Optional[List[Dict[str, Any]]] = None,
    *,
    result_reader: Optional[Callable[[Optional[str]], Optional[str]]] = None,
) -> float:
    """Sum P&L for venue-filled live sends with a yes/no result. Never uses paper."""
    reader = result_reader or (lambda _ticker: None)
    total = 0.0
    for row in attempts or []:
        if not _is_closed_live_fill(row):
            continue
        result = str(reader(row.get("ticker")) or "").strip().lower()
        if result not in ("yes", "no"):
            continue
        side = str(row.get("side") or "").strip().lower()
        spend = float(row.get("spend") or 0.0)
        price = float(row.get("ticket_price") or 0.0)
        if side == result:
            total += win_pnl(spend, price)
        else:
            total += lose_pnl(spend, price)
    return round(total, 2)


def apply_realized_live_pnl(
    path: Optional[Path],
    attempts: Optional[List[Dict[str, Any]]] = None,
    *,
    result_reader: Optional[Callable[[Optional[str]], Optional[str]]] = None,
) -> Dict[str, Any]:
    """Persist computed live P&L. Trip at -$100. Never lifts an existing halt."""
    path = path or default_halt_path()
    pnl = realized_live_pnl(attempts, result_reader=result_reader)
    existed = path.exists()
    prior = load_halt(path)
    prior_halted = bool(prior.get("halted")) if existed else False
    halted = prior_halted or pnl <= -LOSS_LIMIT
    if not existed and not halted:
        blob = empty_halt()
        blob["realized_live_pnl"] = pnl
        return blob
    reason = prior.get("reason")
    halted_at = prior.get("halted_at")
    if halted and not prior_halted:
        reason = LOSS_REASON
        halted_at = _now()
    blob = {
        "schema_version": HALT_SCHEMA,
        "halted": halted,
        "reason": reason,
        "realized_live_pnl": pnl,
        "halted_at": halted_at if halted else None,
    }
    save_halt(blob, path)
    return blob


def format_halt_status(blob: Dict[str, Any]) -> str:
    on = bool(blob.get("halted"))
    lines = [f"Live halt: {'on' if on else 'off'}"]
    if on and blob.get("reason"):
        lines.append(f"Reason: {blob.get('reason')}")
    pnl = blob.get("realized_live_pnl")
    if pnl is None:
        lines.append("Realized live P&L: not computed")
    else:
        sign = "+" if float(pnl) >= 0 else "-"
        lines.append(f"Realized live P&L: {sign}${abs(float(pnl)):.2f}")
    if on and blob.get("halted_at"):
        lines.append(f"Halted at: {blob.get('halted_at')}")
    return "\n".join(lines) + "\n"


def format_manual_halt_ok() -> str:
    return (
        "Live trading halted. Manual halt. "
        "No live send until resume --i-clear-loss-halt.\n"
    )


def format_resume_ok() -> str:
    return "Live-loss halt cleared. kalshi-live book gates still apply.\n"
