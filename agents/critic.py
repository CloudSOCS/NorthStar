"""Kill/salvage rules in code. Maps M1/M5 JSON payloads to graph entries."""

from __future__ import annotations

from typing import Any, Dict, List

from agents.families import family_for
from agents.hypothesis_graph import GraphError

M5_PERIOD = (
    "IS 2025-06-10→2026-01-01 + OOS 2026-01-01→latest; "
    "BTC/ETH/SOL 1h+4h; direction=long"
)

M5_STATUS = {
    "deprecate": ("killed", "deprecate"),
    "graduate_m1": ("salvage", "graduate_m1"),
    "unscreened_short": ("incomplete", "unscreened_short"),
    "no_trades": ("incomplete", "no_trades"),
    "healthy": ("survived", "healthy"),
}

M1_STATUS = {
    "pass": ("survived", "m1_pass"),
    "fail": ("killed", "m1_fail"),
    "degenerate": ("killed", "m1_fail"),
}


class IngestError(GraphError):
    """Harness JSON cannot be ingested; write nothing."""


def map_m5_payload(
    payload: Dict[str, Any],
    *,
    include_incomplete: bool,
    source: str,
    date: str,
) -> List[Dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise IngestError("M5 payload missing rows")
    out: List[Dict[str, Any]] = []
    for row in rows:
        entry = _map_m5_row(row, include_incomplete=include_incomplete,
                            source=source, date=date,
                            fallback_direction=str(payload.get("direction") or "long"))
        if entry is not None:
            out.append(entry)
    return out


def _map_m5_row(row: Dict[str, Any], *, include_incomplete: bool,
                source: str, date: str, fallback_direction: str):
    name = row.get("strategy")
    verdict = row.get("verdict")
    if not name or not verdict:
        raise IngestError(f"M5 row missing strategy/verdict: {row!r}")
    n_liq = int(row.get("n_liquidated") or 0)
    if n_liq > 0:
        status, graph_verdict = "killed", "liquidated"
        reason = f"M5 liquidated_legs={n_liq} (equity floored at 0)."
        lesson = "Liquidation is an immediate kill, independent of Sharpe."
    else:
        if verdict in ("unscreened_short", "no_trades") and not include_incomplete:
            return None
        if verdict not in M5_STATUS:
            raise IngestError(f"unknown M5 verdict: {verdict!r}")
        status, graph_verdict = M5_STATUS[verdict]
        if verdict == "deprecate":
            reason = (
                f"M5 deprecate: gross {row.get('mean_gross_ret')}%/leg, "
                f"net {row.get('mean_net_ret')}%/leg, {row.get('trades')} trades."
            )
            lesson = "No positive zero-fee edge; do not re-propose the same mechanism."
        elif verdict == "graduate_m1":
            reason = (
                f"M5 graduate_m1: gross {row.get('mean_gross_ret')}%/leg but "
                f"net {row.get('mean_net_ret')}%/leg after fees."
            )
            lesson = "Gross edge exists; raise selectivity before any live consideration."
        elif verdict == "healthy":
            reason = "survived"
            lesson = "Net edge survived the M5 fee screen."
        elif verdict == "unscreened_short":
            reason = (
                f"M5 unscreened_short: long-leg net {row.get('mean_net_ret')}%/leg "
                f"over {row.get('trades')} trades; short leg unmeasured."
            )
            lesson = "Incomplete measurement, not a kill. Re-screen --direction short."
        else:
            reason = "M5 no_trades: never fired on the audit slice."
            lesson = "Incomplete measurement, not a kill."
    registry = str(row.get("registry") or "")
    direction = str(row.get("direction") or fallback_direction)
    metrics = {
        k: row.get(k)
        for k in (
            "mean_net_ret", "mean_gross_ret", "mean_net_sharpe", "trades",
            "trades_per_year", "fee_drag_pp", "n_liquidated",
        )
        if k in row
    }
    return {
        "id": f"{name}.{registry or 'na'}.m5.{date}",
        "name": name,
        "version": "defaults",
        "family": family_for(name),
        "core_idea": f"Registry strategy {name} ({registry}) at default params.",
        "status": status,
        "failure_reason": reason,
        "regime_or_period": M5_PERIOD,
        "metrics": metrics,
        "lesson": lesson,
        "date": date,
        "harness": "m5",
        "verdict": graph_verdict,
        "source": source,
        "registry": registry,
        "window": "is+oos",
        "direction": direction,
    }


def map_m1_payload(
    payload: Dict[str, Any],
    *,
    source: str,
    date: str,
) -> List[Dict[str, Any]]:
    scores = payload.get("window_scores")
    if not isinstance(scores, list) or not scores:
        raise IngestError("M1 payload missing window_scores")
    cand = payload.get("candidate") or {}
    name = cand.get("name")
    if not name:
        raise IngestError("M1 payload missing candidate.name")
    registry = str(payload.get("registry") or "")
    direction = str(payload.get("direction") or cand.get("direction") or "long")
    out = []
    for score in scores:
        window = score.get("window")
        verdict = score.get("verdict")
        if not window:
            raise IngestError(f"M1 score missing window: {score!r}")
        if verdict == "no data":
            raise IngestError(f"M1 window {window} verdict is no data")
        n_liq = int(score.get("liquidated_legs") or 0)
        if n_liq > 0:
            status, graph_verdict = "killed", "liquidated"
            reason = f"M1 {window}: liquidated_legs={n_liq}."
            lesson = "Liquidation is an immediate kill, independent of Sharpe."
        else:
            if verdict not in M1_STATUS:
                raise IngestError(f"unknown M1 verdict: {verdict!r}")
            status, graph_verdict = M1_STATUS[verdict]
            if verdict == "pass":
                reason = "survived"
                lesson = f"M1 {window} beat the incumbent median bar."
            elif verdict == "degenerate":
                reason = f"M1 {window}: degenerate (meaningless vs bar)."
                lesson = "Degenerate window is a kill for this candidate/window."
            else:
                reason = (
                    f"M1 {window} fail vs incumbent "
                    f"(sharpe {score.get('mean_sharpe')} vs bar {score.get('mean_bar_sharpe')})."
                )
                lesson = f"Failed M1 {window} vs incumbent median; do not deploy."
        metrics = {
            k: score.get(k)
            for k in (
                "mean_sharpe", "mean_bar_sharpe", "mean_ddadj",
                "mean_bar_ddadj", "verdict", "scored_datasets", "liquidated_legs",
            )
            if k in score
        }
        out.append({
            "id": f"{name}.{registry or 'na'}.m1.{window}.{date}",
            "name": name,
            "version": "defaults",
            "family": family_for(name),
            "core_idea": f"Registry strategy {name} M1 candidate.",
            "status": status,
            "failure_reason": reason,
            "regime_or_period": f"M1 window={window}; direction={direction}",
            "metrics": metrics,
            "lesson": lesson,
            "date": date,
            "harness": "m1",
            "verdict": graph_verdict,
            "source": source,
            "registry": registry,
            "window": window,
            "direction": direction,
        })
    return out


def apply_cycle_stamps(
    entries: List[Dict[str, Any]],
    *,
    version: str,
    supersedes: str | None = None,
    supersedes_window: str = "oos",
    core_idea: str | None = None,
) -> List[Dict[str, Any]]:
    """Rewrite version/id and optionally attach ``supersedes`` to one window.

    The OOS row (default) carries the pointer so a multi-window M1 ingest
    cannot stamp ``superseded_by`` twice on the same salvage entry.
    """
    if not version or version.strip() == "":
        raise IngestError("cycle version must be non-empty")
    out: List[Dict[str, Any]] = []
    for e in entries:
        item = dict(e)
        item["version"] = version
        reg = item.get("registry") or "na"
        harness = item["harness"]
        window = item.get("window") or "na"
        item["id"] = f"{item['name']}.{reg}.{harness}.{window}.{version}.{item['date']}"
        if core_idea:
            item["core_idea"] = core_idea
        out.append(item)
    if supersedes:
        stamped = []
        for item in out:
            if item.get("window") == supersedes_window:
                item["supersedes"] = supersedes
                stamped.append(item)
        if not stamped:
            if len(out) == 1:
                out[0]["supersedes"] = supersedes
            else:
                raise IngestError(
                    f"supersedes_window {supersedes_window!r} not in mapped entries"
                )
    return out
