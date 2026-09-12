"""Paper fills from a saved walk. Never places a live order. Never writes the graph."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from zoneinfo import ZoneInfo
import json
import os
import re
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
PAPER_LIST_EMPTY = "No paper fills yet. Run practice walk then paper book."
STUDENT_MIN_PRICE = 0.20
PAPER_BANNER = "This is a paper fill — no live order will be placed"
POSTMORTEM_FOOTER = "This is a paper post-mortem — no live order, graph not written"
POSTMORTEM_BANNER = POSTMORTEM_FOOTER
BOTH_REFUSE = (
    "Will not book both sides. Pair is not a cheap hedge (need pair cost under $1)."
)
SAME_MARKET_REFUSE = (
    "Already have a paper fill on this market (id {id}). Walk a new ticker."
)
WINDOW_OVER = "This window is over. Run practice walk on a live ticker."
WINDOW_UNKNOWN = "cannot confirm market is live."
VENUE_TZ = ZoneInfo("America/New_York")
_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_TICKER_CLOSE = re.compile(
    r"^KX[A-Z0-9]+15M-(\d{2})([A-Z]{3})(\d{2})(\d{4})(?:-.+)?$",
    re.IGNORECASE,
)
_CLOSED_STATUSES = frozenset(
    {"closed", "settled", "determined", "finalized", "inactive"}
)
_OPEN_STATUSES = frozenset({"open", "active"})


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
    pos = {
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
    ticker = str(entry.get("ticker") or "").strip()
    if ticker:
        pos["ticker"] = ticker
    return pos


def _pair_cost(entry: Dict[str, Any]) -> float:
    raw = entry.get("pair_cost")
    if raw is not None:
        return float(raw)
    return pair_cost(float(entry.get("yes_price") or 0.0), float(entry.get("no_price") or 0.0))


def find_same_market(
    positions: List[Dict[str, Any]], ticker: Optional[str]
) -> Optional[Dict[str, Any]]:
    """First fill on this ticker, open or settled. Empty ticker → no match."""
    needle = str(ticker or "").strip()
    if not needle:
        return None
    for pos in positions or []:
        if str(pos.get("ticker") or "").strip() == needle:
            return pos
    return None


def same_market_message(pos: Dict[str, Any]) -> str:
    return SAME_MARKET_REFUSE.format(id=pos.get("id"))


def paper_now() -> datetime:
    raw = os.environ.get("NORTHSTAR_NOW")
    if raw:
        return datetime.fromisoformat(raw)
    return datetime.now().astimezone()


def parse_close_time(raw: Any) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=VENUE_TZ)
    return when


def parse_ticker_close(ticker: Any) -> Optional[datetime]:
    text = str(ticker or "").strip()
    match = _TICKER_CLOSE.match(text)
    if not match:
        return None
    yy, mon, dd, hhmm = match.groups()
    month = _MONTHS.get(mon.upper())
    if month is None:
        return None
    try:
        year = 2000 + int(yy)
        day = int(dd)
        hour = int(hhmm[:2])
        minute = int(hhmm[2:])
        return datetime(year, month, day, hour, minute, tzinfo=VENUE_TZ)
    except ValueError:
        return None


def window_end(entry: Dict[str, Any]) -> Optional[datetime]:
    """Prefer stored snapshot close_time. Else ticker HHMM in venue TZ."""
    close = parse_close_time(entry.get("close_time"))
    if close is not None:
        return close
    return parse_ticker_close(entry.get("ticker"))


def refuse_expired_window(
    entry: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    status_reader: Optional[Callable[[Optional[str]], Optional[str]]] = None,
) -> Optional[str]:
    """None if the 15m window is still live. Never invents an end time."""
    if last_walk_kind(entry) == "demo":
        return None
    clock = now or paper_now()
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=VENUE_TZ)
    end = window_end(entry)
    if end is not None:
        return WINDOW_OVER if clock >= end else None
    status = None
    if status_reader is not None:
        status = status_reader(entry.get("ticker"))
    label = str(status or "").strip().lower()
    if label in _CLOSED_STATUSES:
        return WINDOW_OVER
    if label in _OPEN_STATUSES:
        return None
    return WINDOW_UNKNOWN


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


def already_settled_message(pos: Dict[str, Any]) -> str:
    outcome = str(pos.get("outcome") or "").upper()
    realized = float(pos.get("realized_pnl") or 0.0)
    return (
        f"Already settled. Paper id {pos.get('id')} outcome {outcome}  "
        f"P&L {_signed(realized)}. No change."
    )


def _settle_one(pos: Dict[str, Any], outcome: str, settled_at: str) -> Dict[str, Any]:
    if pos.get("status") == "settled":
        raise ValueError(already_settled_message(pos))
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
    already = [p for p in hits if p.get("status") == "settled"]
    if already:
        named = next((p for p in already if p.get("id") == target_id), already[0])
        raise ValueError(already_settled_message(named))
    when = _now()
    settled = [_settle_one(p, outcome_n, when) for p in hits]
    return settled[0]


def list_entry(pos: Dict[str, Any]) -> Dict[str, Any]:
    """Subset for paper list --json. Does not copy question, P&L forecast, or lesson."""
    return {
        "id": pos.get("id"),
        "kind": "paper",
        "asset": pos.get("asset"),
        "side": pos.get("side"),
        "ticket_price": pos.get("ticket_price"),
        "spend": pos.get("spend"),
        "tickets": pos.get("tickets"),
        "status": pos.get("status"),
        "outcome": pos.get("outcome"),
        "realized_pnl": pos.get("realized_pnl"),
    }


def format_paper_list_market(pos: Dict[str, Any]) -> str:
    """Ticker if stored, else the question. Does not invent a market."""
    ticker = str(pos.get("ticker") or "").strip()
    if ticker:
        return ticker
    return str(pos.get("question") or "")


def format_paper_list_pnl(pos: Dict[str, Any]) -> str:
    realized = pos.get("realized_pnl")
    if realized is None:
        return "—"
    return _signed(float(realized))


def format_paper_list_outcome(pos: Dict[str, Any]) -> str:
    if pos.get("status") != "settled":
        return "—"
    return str(pos.get("outcome") or "").upper()


def _stored_ticket_price(pos: Dict[str, Any]) -> Optional[float]:
    raw = pos.get("ticket_price")
    if raw is None or raw == "":
        return None
    return float(raw)


def format_paper_list_tag(pos: Dict[str, Any]) -> str:
    price = _stored_ticket_price(pos)
    if price is None:
        return ""
    return "cheap" if price < STUDENT_MIN_PRICE else ""


_LIST_HEADERS = (
    "ID",
    "Market",
    "Side",
    "Price",
    "Dollars in",
    "Tickets",
    "Status",
    "Outcome",
    "P&L",
    "Tag",
)
_LIST_RIGHT = {3, 4, 5, 8}


def settled_net_pnl(
    positions: List[Dict[str, Any]], *, student: bool = False
) -> float:
    """Sum stored settled realized_pnl. student=True keeps price >= 20¢ only."""
    total = 0.0
    for pos in positions or []:
        if pos.get("status") != "settled":
            continue
        raw = pos.get("realized_pnl")
        if raw is None:
            continue
        if student:
            price = _stored_ticket_price(pos)
            if price is None or price < STUDENT_MIN_PRICE:
                continue
        total += float(raw)
    return total


def open_paper_count(positions: List[Dict[str, Any]]) -> int:
    return sum(1 for pos in positions or [] if pos.get("status") == "open")


def format_paper_list_net(positions: List[Dict[str, Any]]) -> str:
    return (
        f"Settled net (all): {_signed(settled_net_pnl(positions))}\n"
        f"Student net (price 20¢ or higher): {_signed(settled_net_pnl(positions, student=True))}\n"
        f"Open: {open_paper_count(positions)}"
    )


def format_paper_list_table(positions: List[Dict[str, Any]]) -> str:
    """Human table. Newest first. Does not invent edge or settle."""
    rows = []
    for p in reversed(positions or []):
        rows.append(
            (
                str(p.get("id") or ""),
                format_paper_list_market(p),
                str(p.get("side") or "").upper(),
                f"{float(p.get('ticket_price') or 0):.2f}",
                f"${float(p.get('spend') or 0):.2f}",
                f"{float(p.get('tickets') or 0):.2f}",
                str(p.get("status") or ""),
                format_paper_list_outcome(p),
                format_paper_list_pnl(p),
                format_paper_list_tag(p),
            )
        )
    widths = [len(h) for h in _LIST_HEADERS]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]

    def _line(cols: tuple) -> str:
        parts = []
        for i, (cell, width) in enumerate(zip(cols, widths)):
            parts.append(cell.rjust(width) if i in _LIST_RIGHT else cell.ljust(width))
        return "  ".join(parts)

    lines = ["Paper fills (not live)", _line(_LIST_HEADERS)]
    lines.extend(_line(row) for row in rows)
    return "\n".join(lines) + "\n"


def dump_paper_json(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Newest first. List subset only. Does not write."""
    return {
        "schema_version": PAPER_SCHEMA,
        "entries": [list_entry(p) for p in reversed(positions or [])],
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


def paper_lesson(pos: Dict[str, Any]) -> str:
    """One lesson from stored paper fields. Does not invent edge."""
    side = str(pos.get("side") or "").upper()
    outcome = str(pos.get("outcome") or "").upper()
    if pos.get("pair_id"):
        lead = "You booked both sides (a hedge). A hedge is not edge."
    else:
        lead = f"You booked one {side} ticket, not a hedge."
    if str(pos.get("side") or "") == str(pos.get("outcome") or ""):
        step = "Outcome matched your side. Step 2: you won."
    else:
        step = f"Outcome was {outcome}. Step 2: you lost the dollars in."
    return (
        f"{lead} {step} This fill does not store a guess — do not invent edge."
    )


def select_closed_paper(
    positions: List[Dict[str, Any]],
    target_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Newest closed fill, or --id if that row is settled. Does not write."""
    if target_id:
        hits = [p for p in positions if p.get("id") == target_id]
        if not hits:
            raise ValueError(f"No paper position with id {target_id}")
        pos = hits[0]
        if pos.get("status") != "settled":
            raise ValueError(f"Position {target_id} is still open. Settle it first.")
        return pos
    closed = [p for p in positions if p.get("status") == "settled"]
    if not closed:
        raise ValueError("No closed paper fills yet.")
    return closed[-1]


def postmortem_entry(pos: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": pos.get("id"),
        "kind": "paper",
        "asset": pos.get("asset"),
        "question": pos.get("question"),
        "side": pos.get("side"),
        "ticket_price": pos.get("ticket_price"),
        "spend": pos.get("spend"),
        "tickets": pos.get("tickets"),
        "outcome": pos.get("outcome"),
        "realized_pnl": pos.get("realized_pnl"),
        "hedge_booked": bool(pos.get("pair_id")),
        "lesson": paper_lesson(pos),
    }


def dump_postmortem_json(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Zero or one closed fill. Does not write."""
    return {
        "schema_version": PAPER_SCHEMA,
        "entries": [postmortem_entry(p) for p in positions],
    }


def format_paper_postmortem(pos: Dict[str, Any]) -> str:
    side = str(pos.get("side") or "").upper()
    outcome = str(pos.get("outcome") or "").upper()
    price = float(pos.get("ticket_price") or 0.0)
    spend = float(pos.get("spend") or 0.0)
    tickets = float(pos.get("tickets") or 0.0)
    realized = float(pos.get("realized_pnl") or 0.0)
    lines = [
        POSTMORTEM_BANNER,
        "",
        f"{pos.get('asset')} — {pos.get('question')}",
        (
            f"Booked: {side} ticket at {price:.2f} ({price * 100:.0f}¢). "
            f"${spend:.2f} → {tickets:.2f} tickets. kind: paper"
        ),
        f"Outcome: {outcome}",
        f"P&L: {_signed(realized)}",
        f"Lesson: {paper_lesson(pos)}",
        "",
        POSTMORTEM_FOOTER,
    ]
    return "\n".join(lines) + "\n"


def format_postmortem_refuse(message: str) -> str:
    return f"{message}\n{POSTMORTEM_FOOTER}\n"


def _signed(amount: float) -> str:
    sign = "+" if amount >= 0 else "-"
    return f"{sign}${abs(amount):.2f}"
