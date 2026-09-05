"""Read-only product orientation. Fences are static locked facts, not a graph read."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from poly.practice.paper import select_closed_paper
from poly.practice.walk import (
    dump_journal_json,
    format_journal_edge,
    format_journal_time,
    last_walk_kind,
)

STATUS_SCHEMA = 1
# Locked product path. Fences are hardcoded on purpose.
FENCES = {
    "live_orders": "approve-per-order",
    "generator": "stubbed",
    "graph_command": "stop",
    "source": "static",
}
HELPER = "must not run kalshi-live"
CONTINUE = [
    "uv run northstar status --json",
    "uv run northstar practice walk --demo --save",
    "uv run northstar practice walk --save",
    "uv run northstar practice last --json",
    "uv run northstar practice journal --json",
    "uv run northstar practice paper list",
    "uv run northstar practice paper list --json",
    "uv run northstar practice paper postmortem",
    "uv run northstar practice paper postmortem --json",
]
STATUS_FOOTER = "This is a status check, not a trade."


def format_last_walk_kind(entry: Optional[Dict[str, Any]]) -> str:
    kind = last_walk_kind(entry)
    if kind is None:
        return "no saved walks yet"
    if kind == "demo":
        return "demo snapshot — not a live Kalshi market"
    return "live Kalshi"


def last_paper_entry(positions: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Newest settled paper fill. Open-only or empty → None. Does not invent edge."""
    try:
        pos = select_closed_paper(positions or [])
    except ValueError:
        return None
    return {
        "id": pos.get("id"),
        "kind": "paper",
        "asset": pos.get("asset"),
        "side": pos.get("side"),
        "outcome": pos.get("outcome"),
        "realized_pnl": pos.get("realized_pnl"),
    }


def last_paper_kind(entry: Optional[Dict[str, Any]]) -> Optional[str]:
    return "paper" if entry else None


def format_last_paper_line(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return "no closed paper fills yet"
    asset = str(entry.get("asset") or "")
    side = str(entry.get("side") or "").upper()
    outcome = str(entry.get("outcome") or "").upper()
    realized = float(entry.get("realized_pnl") or 0.0)
    sign = "+" if realized >= 0 else "-"
    return f"{asset} {side} outcome {outcome}  P&L {sign}${abs(realized):.2f}  (paper)"


def product_status_payload(
    entries: Optional[List[Dict[str, Any]]] = None,
    paper_positions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Newest saved lesson plus newest closed paper fill. Does not write or fetch."""
    dumped = dump_journal_json(entries or [], last=1)
    last = dumped["entries"][0] if dumped["entries"] else None
    last_p = last_paper_entry(paper_positions)
    return {
        "schema_version": STATUS_SCHEMA,
        "fences": dict(FENCES),
        "last_walk": last,
        "last_walk_kind": last_walk_kind(last),
        "last_paper": last_p,
        "last_paper_kind": last_paper_kind(last_p),
        "helper": HELPER,
        "continue": list(CONTINUE),
    }


def format_last_walk_line(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return "no saved walks yet"
    asset = str(entry.get("asset") or "")
    when = format_journal_time(str(entry.get("saved_at") or ""))
    edge = format_journal_edge(entry.get("edge"))
    hedge = str(entry.get("hedge") or "")
    return f"{asset}  {when}  edge {edge}  hedge {hedge}"
