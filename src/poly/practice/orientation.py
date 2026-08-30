"""Read-only product orientation. Fences are static locked facts, not a graph read."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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


def product_status_payload(entries: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Newest saved lesson plus static fences. Does not write or fetch a market."""
    dumped = dump_journal_json(entries or [], last=1)
    last = dumped["entries"][0] if dumped["entries"] else None
    return {
        "schema_version": STATUS_SCHEMA,
        "fences": dict(FENCES),
        "last_walk": last,
        "last_walk_kind": last_walk_kind(last),
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
