"""Experiment proposals. Must read the Hypothesis Graph first.

``propose_strategy`` still refuses to emit ``@register`` code (no held-out
survivors). ``propose_experiment`` is the coded next-cycle picker: it never
invents a new mechanism and never writes the graph.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agents.hypothesis_graph import DEFAULT_PATH, load_graph, relevant

HELD_OUT_WINDOWS = ("2023", "2024", "2025H1")


def require_graph(path=None):
    return load_graph(path or DEFAULT_PATH)


def propose_strategy(family: str):
    g = require_graph()
    rows = relevant(g, family=family)
    raise NotImplementedError(
        f"generator does not emit strategy code; hypothesis graph must be read first. "
        f"{len(rows)} relevant entries for family={family!r}."
    )


def _reg(entry: Dict[str, Any]) -> str:
    return str(entry.get("registry") or "spot")


def _direction(entry: Dict[str, Any]) -> str:
    return str(entry.get("direction") or "long")


def _key(entry: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(entry["name"]),
        _reg(entry),
        str(entry.get("version") or "defaults"),
        _direction(entry),
    )


def _has_m1_direction(rows: List[Dict[str, Any]], name: str, registry: str, direction: str) -> bool:
    return any(
        e["harness"] == "m1"
        and e["name"] == name
        and _reg(e) == registry
        and _direction(e) == direction
        for e in rows
    )


def _pending_held_out(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = {}
    for e in rows:
        if e.get("harness") != "m1":
            continue
        groups.setdefault(_key(e), []).append(e)
    pending = []
    for key, items in groups.items():
        by_w = {e.get("window"): e for e in items}
        is_row, oos = by_w.get("is"), by_w.get("oos")
        if is_row is None or oos is None:
            continue
        if is_row.get("verdict") != "m1_pass" or oos.get("verdict") != "m1_pass":
            continue
        if any(w in by_w for w in HELD_OUT_WINDOWS):
            continue
        pending.append(oos)
    if not pending:
        return None
    pending.sort(key=lambda e: e["id"])
    e = pending[0]
    return {
        "action": "run-m1",
        "strategy": e["name"],
        "registry": _reg(e),
        "direction": _direction(e),
        "windows": "2023,2024,2025H1",
        "version": e["version"],
        "params": None,
        "supersedes": None,
        "reason": (
            f"protocol IS+OOS passed for {e['id']}; held-out windows not recorded. "
            "No second supersedes."
        ),
    }


def _incomplete_measurement(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = [
        e for e in rows
        if e.get("status") == "incomplete"
        and not e.get("obsolete")
        and e.get("verdict") == "unscreened_short"
    ]
    candidates.sort(key=lambda e: e["id"])
    for e in candidates:
        if _has_m1_direction(rows, e["name"], _reg(e), "short"):
            continue
        return {
            "action": "run-m1",
            "strategy": e["name"],
            "registry": _reg(e),
            "direction": "short",
            "windows": "is,oos",
            "version": "short_v1",
            "params": None,
            "supersedes": None,
            "reason": (
                f"{e['id']} is unscreened_short; short-leg M1 not in the graph. "
                "Do not supersede the long incomplete row."
            ),
        }
    return None


def _open_salvage(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = [
        e for e in rows
        if e.get("status") == "salvage"
        and e.get("verdict") == "graduate_m1"
        and not e.get("obsolete")
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda e: e["id"])
    e = candidates[0]
    return {
        "action": "selectivity_m1",
        "strategy": e["name"],
        "registry": _reg(e),
        "direction": _direction(e),
        "windows": "is,oos",
        "version": "selectivity_v1",
        "params": None,
        "supersedes": e["id"],
        "reason": (
            f"{e['id']} is graduate_m1 and not superseded. "
            "Pick one selectivity knob; do not emit @register code."
        ),
    }


def propose_experiment(graph: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Highest-leverage next harness cycle. Does not write the graph."""
    g = graph if graph is not None else require_graph()
    rows = relevant(g)
    for picker in (_pending_held_out, _incomplete_measurement, _open_salvage):
        hit = picker(rows)
        if hit is not None:
            return hit
    return {
        "action": "stop",
        "strategy": None,
        "registry": None,
        "direction": None,
        "windows": None,
        "version": None,
        "params": None,
        "supersedes": None,
        "reason": (
            "No incomplete short-leg gap, no protocol pass pending held-out, "
            "and no un-superseded graduate_m1. Do not un-stub strategy codegen."
        ),
    }
