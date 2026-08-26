"""Append-only Hypothesis Graph (git-tracked JSON)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parent / "hypothesis_graph.json"

STATUSES = ("killed", "salvage", "incomplete", "survived", "open")
VERDICTS = (
    "deprecate", "graduate_m1", "healthy", "unscreened_short", "no_trades",
    "m1_fail", "m1_pass", "liquidated", "documented",
)
HARNESSES = ("m1", "m5", "m2", "m3", "documented")
REQUIRED_ENTRY_FIELDS = (
    "id", "name", "version", "family", "core_idea", "status",
    "failure_reason", "regime_or_period", "metrics", "lesson", "date",
    "harness", "verdict", "source",
)

UNIVERSE = {
    "note": "M1/M5 audit slices — do not silently change",
    "datasets": [
        ["BTC/USDT", "1h"], ["BTC/USDT", "4h"],
        ["ETH/USDT", "1h"], ["ETH/USDT", "4h"],
        ["SOL/USDT", "1h"], ["SOL/USDT", "4h"],
    ],
    "windows": {
        "is": ["2025-06-10", "2026-01-01"],
        "oos": ["2026-01-01", None],
    },
}


class GraphError(ValueError):
    """Invalid graph or entry; callers must not write."""


def empty_graph(*, updated: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated": updated or date.today().isoformat(),
        "universe": json.loads(json.dumps(UNIVERSE)),
        "entries": [],
    }


def validate_entry(entry: Dict[str, Any]) -> None:
    missing = [k for k in REQUIRED_ENTRY_FIELDS if k not in entry]
    if missing:
        raise GraphError(f"entry missing required fields: {missing}")
    if entry["status"] not in STATUSES:
        raise GraphError(f"invalid status: {entry['status']!r}")
    if entry["verdict"] not in VERDICTS:
        raise GraphError(f"invalid verdict: {entry['verdict']!r}")
    if entry["harness"] not in HARNESSES:
        raise GraphError(f"invalid harness: {entry['harness']!r}")
    if not isinstance(entry.get("metrics"), dict):
        raise GraphError("metrics must be an object")
    if entry.get("supersedes") is not None and not isinstance(entry["supersedes"], str):
        raise GraphError("supersedes must be a string id")
    if entry.get("superseded_by") is not None and not isinstance(entry["superseded_by"], str):
        raise GraphError("superseded_by must be a string id")


def validate_graph(graph: Dict[str, Any]) -> None:
    if not isinstance(graph, dict):
        raise GraphError("graph must be an object")
    if graph.get("schema_version") != SCHEMA_VERSION:
        raise GraphError(f"unsupported schema_version: {graph.get('schema_version')!r}")
    for key in ("updated", "universe", "entries"):
        if key not in graph:
            raise GraphError(f"graph missing {key}")
    if not isinstance(graph["entries"], list):
        raise GraphError("entries must be a list")
    ids = []
    for e in graph["entries"]:
        validate_entry(e)
        ids.append(e["id"])
    if len(ids) != len(set(ids)):
        raise GraphError("duplicate entry id")


def load_graph(path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(path) if path is not None else DEFAULT_PATH
    try:
        raw = path.read_text()
    except OSError as exc:
        raise GraphError(f"cannot read {path}: {exc}") from exc
    try:
        graph = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GraphError(f"corrupt JSON in {path}: {exc}") from exc
    validate_graph(graph)
    return graph


def save_graph(graph: Dict[str, Any], path: Optional[Path] = None) -> None:
    path = Path(path) if path is not None else DEFAULT_PATH
    validate_graph(graph)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(graph, indent=2) + "\n"
    tmp.write_text(text)
    tmp.replace(path)


def entry_key(entry: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    return (
        str(entry["name"]),
        str(entry.get("registry") or ""),
        str(entry["harness"]),
        str(entry.get("window") or ""),
        str(entry.get("direction") or ""),
        str(entry["version"]),
    )


def _successor_map(entries: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """old_id -> new_id from forward `supersedes` pointers."""
    known = {e["id"] for e in entries}
    out: Dict[str, str] = {}
    for e in entries:
        sid = e.get("supersedes")
        if not sid or sid not in known:
            continue
        if sid in out and out[sid] != e["id"]:
            raise GraphError(f"multiple successors for {sid}")
        out[sid] = e["id"]
    return out


def append_entry(graph: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    validate_graph(graph)
    validate_entry(entry)
    if entry.get("superseded_by"):
        raise GraphError("new entries must not set superseded_by")
    entries = [dict(e) for e in graph["entries"]]
    if any(e["id"] == entry["id"] for e in entries):
        raise GraphError(f"duplicate entry id: {entry['id']}")
    key = entry_key(entry)
    for e in entries:
        if entry_key(e) == key:
            raise GraphError(f"duplicate key {key}")
    sid = entry.get("supersedes")
    if sid:
        matches = [i for i, e in enumerate(entries) if e["id"] == sid]
        if not matches:
            raise GraphError(f"supersedes id not found: {sid}")
        old = entries[matches[0]]
        if entry["version"] == old["version"]:
            raise GraphError("supersedes requires a new version")
        existing = old.get("superseded_by")
        if existing:
            raise GraphError(f"already superseded by {existing}")
        old["superseded_by"] = entry["id"]
    entries.append(dict(entry))
    out = dict(graph)
    out["entries"] = entries
    out["updated"] = date.today().isoformat()
    validate_graph(out)
    return out


def relevant(
    graph: Dict[str, Any],
    family: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    validate_graph(graph)
    successors = _successor_map(graph["entries"])
    rows = []
    for e in graph["entries"]:
        if family is not None and e["family"] != family:
            continue
        if status is not None and e["status"] != status:
            continue
        item = dict(e)
        successor = e.get("superseded_by") or successors.get(e["id"])
        if successor:
            item["superseded_by"] = successor
        item["obsolete"] = successor is not None
        rows.append(item)
    rows.sort(key=lambda r: (r["date"], r["id"]))
    return rows


def status_summary(graph: Dict[str, Any]) -> Dict[str, Any]:
    validate_graph(graph)
    by_status: Dict[str, int] = {}
    by_family: Dict[str, int] = {}
    for e in graph["entries"]:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
        by_family[e["family"]] = by_family.get(e["family"], 0) + 1
    return {
        "updated": graph["updated"],
        "n_entries": len(graph["entries"]),
        "by_status": by_status,
        "by_family": by_family,
    }
