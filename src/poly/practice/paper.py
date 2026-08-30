"""Paper fills from a saved walk. Never places a live order. Never writes the graph."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import json
import os
import uuid

from poly.practice.walk import (
    clamp_spend,
    last_walk_kind,
    lose_pnl,
    pair_cost,
    tickets_bought,
    win_pnl,
)

PAPER_SCHEMA = 1
PAPER_FOOTER = "This is paper only — no live order was placed."
PAPER_BANNER = "This is a paper fill — no live order will be placed"
BOTH_REFUSE = (
    "Will not book both sides. Pair is not a cheap hedge (need pair cost under $1)."
)


def default_paper_path() -> Path:
    override = os.environ.get("NORTHSTAR_PAPER_POSITIONS")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".poly" / "paper_positions.json"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _read_paper(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"schema_version": PAPER_SCHEMA, "positions": []}
    blob = json.loads(path.read_text())
    if blob.get("schema_version") != PAPER_SCHEMA:
        raise ValueError(f"Unsupported paper schema_version: {blob.get('schema_version')}")
    positions = blob.get("positions")
    if not isinstance(positions, list):
        raise ValueError("Paper file is missing a positions list")
    return {"schema_version": PAPER_SCHEMA, "positions": positions}


def load_paper(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only load. Missing file → empty positions. Never writes."""
    return _read_paper(path or default_paper_path())


def save_paper(blob: Dict[str, Any], path: Optional[Path] = None) -> Path:
    path = path or default_paper_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=2) + "\n")
    tmp.replace(path)
    return path


def _leg(
    entry: Dict[str, Any],
    side: str,
    *,
    pair_id: Optional[str] = None,
    booked_at: Optional[str] = None,
) -> Dict[str, Any]:
    spend, _ = clamp_spend(float(entry.get("spend") or 0.0))
    yes = float(entry.get("yes_price") or 0.0)
    no = float(entry.get("no_price") or 0.0)
    if side == "yes":
        price = yes
        tickets = float(entry.get("tickets") or tickets_bought(spend, price))
        win = float(entry.get("win_pnl") if entry.get("win_pnl") is not None else win_pnl(spend, price))
        lose = float(entry.get("lose_pnl") if entry.get("lose_pnl") is not None else lose_pnl(spend, price))
    else:
        price = no
        tickets = tickets_bought(spend, price)
        win = win_pnl(spend, price)
        lose = lose_pnl(spend, price)
    return {
        "id": _new_id(),
        "booked_at": booked_at or _now(),
        "status": "open",
        "kind": "paper",
        "side": side,
        "asset": str(entry.get("asset") or ""),
        "question": str(entry.get("question") or ""),
        "ticket_price": round(price, 4),
        "spend": round(spend, 2),
        "tickets": round(tickets, 4),
        "win_pnl": round(win, 4),
        "lose_pnl": round(lose, 4),
        "from_saved_at": str(entry.get("saved_at") or ""),
        "from_kind": last_walk_kind(entry) or "live",
        "pair_id": pair_id,
        "outcome": None,
        "settled_at": None,
        "realized_pnl": None,
    }


def _pair_cost(entry: Dict[str, Any]) -> float:
    raw = entry.get("pair_cost")
    if raw is not None:
        return float(raw)
    return pair_cost(float(entry.get("yes_price") or 0.0), float(entry.get("no_price") or 0.0))


def book_from_entry(
    entry: Dict[str, Any],
    *,
    side: str = "yes",
    both: bool = False,
) -> Union[Dict[str, Any], Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Build paper position(s) from a saved walk. Does not fetch a market."""
    if both:
        if _pair_cost(entry) >= 1.0:
            raise ValueError(BOTH_REFUSE)
        pair_id = _new_id()
        when = _now()
        return _leg(entry, "yes", pair_id=pair_id, booked_at=when), _leg(
            entry, "no", pair_id=pair_id, booked_at=when
        )
    side_n = side.strip().lower()
    if side_n not in ("yes", "no"):
        raise ValueError("side must be yes or no")
    return _leg(entry, side_n)


def _matches(pos: Dict[str, Any], target: str) -> bool:
    return pos.get("id") == target or pos.get("pair_id") == target


def _settle_one(pos: Dict[str, Any], outcome: str, settled_at: str) -> Dict[str, Any]:
    if pos.get("status") == "settled":
        raise ValueError(f"Position {pos.get('id')} is already settled")
    won = str(pos.get("side") or "") == outcome
    realized = float(pos["win_pnl"] if won else pos["lose_pnl"])
    pos["status"] = "settled"
    pos["outcome"] = outcome
    pos["settled_at"] = settled_at
    pos["realized_pnl"] = round(realized, 4)
    return pos


def settle_paper(blob: Dict[str, Any], target_id: str, outcome: str) -> Dict[str, Any]:
    """Apply Step 2 to matching open paper fills. Mutates blob. Does not fetch."""
    outcome_n = outcome.strip().lower()
    if outcome_n not in ("yes", "no"):
        raise ValueError("outcome must be yes or no")
    positions = blob.get("positions") or []
    hits = [p for p in positions if _matches(p, target_id)]
    if not hits:
        raise ValueError(f"No paper position with id {target_id}")
    pair_ids = {p.get("pair_id") for p in hits if p.get("pair_id")}
    if pair_ids:
        hits = [p for p in positions if p.get("pair_id") in pair_ids or p.get("id") == target_id]
    when = _now()
    settled = [_settle_one(p, outcome_n, when) for p in hits]
    return settled[0]


def dump_paper_json(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Newest first. Does not write."""
    return {
        "schema_version": PAPER_SCHEMA,
        "positions": list(reversed(positions or [])),
    }


def format_paper_book(positions: List[Dict[str, Any]]) -> str:
    lines = [PAPER_BANNER, ""]
    for pos in positions:
        side = str(pos.get("side") or "").upper()
        price = float(pos.get("ticket_price") or 0.0)
        spend = float(pos.get("spend") or 0.0)
        tickets = float(pos.get("tickets") or 0.0)
        win = float(pos.get("win_pnl") or 0.0)
        lose = float(pos.get("lose_pnl") or 0.0)
        lines.extend(
            [
                f"{pos.get('asset')} — {pos.get('question')}",
                f"Side: {side}  tickets  kind: paper",
                f"Ticket price: {price:.2f} ({price * 100:.0f}¢)",
                f"${spend:.2f} → {tickets:.2f} tickets.",
                f"If {side} wins: profit {_signed(win)}.",
                f"If {side} loses: {_signed(lose)}.",
                f"Booked paper position {pos.get('id')}",
                "",
            ]
        )
    lines.append(PAPER_FOOTER)
    return "\n".join(lines).rstrip() + "\n"


def format_paper_settle(positions: List[Dict[str, Any]]) -> str:
    lines = [PAPER_BANNER, ""]
    for pos in positions:
        side = str(pos.get("side") or "").upper()
        outcome = str(pos.get("outcome") or "").upper()
        realized = float(pos.get("realized_pnl") or 0.0)
        lines.extend(
            [
                f"{pos.get('asset')} — {pos.get('question')}",
                f"Settled paper {pos.get('id')}: {side} ticket, outcome {outcome}.",
                f"P&L: {_signed(realized)}",
                "",
            ]
        )
    lines.append(PAPER_FOOTER)
    return "\n".join(lines).rstrip() + "\n"


def format_paper_refuse(message: str) -> str:
    return f"{message}\n{PAPER_FOOTER}\n"


def _signed(amount: float) -> str:
    sign = "+" if amount >= 0 else "-"
    return f"{sign}${abs(amount):.2f}"
