"""Operator CLI for the Hypothesis Graph (ingest + fail-closed run-m1)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import List, Optional

from agents.critic import IngestError, apply_cycle_stamps, map_m1_payload, map_m5_payload
from agents.generator import propose_experiment
from agents.hypothesis_graph import (
    DEFAULT_PATH,
    GraphError,
    append_entry,
    load_graph,
    relevant,
    save_graph,
    status_summary,
)

GRAPH_PATH = DEFAULT_PATH
EXPERIMENTS_ROOT = Path(__file__).resolve().parent.parent / "experiments"
REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_WINDOWS = Path(__file__).resolve().parent.parent / "backtest" / "eval_windows.py"
# 8 incumbents × 6 datasets × 2 windows plus the candidate; uncached OHLCV fetch
# can dominate. Unit tests mock run_subprocess and do not wait this out.
RUN_M1_TIMEOUT_SEC = 1800


def run_subprocess(argv: List[str], timeout: int):
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        class _T:
            returncode = 124
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + "\ntimeout"
        return _T()


def _maybe_stamp(entries, args):
    version = getattr(args, "version", None)
    supersedes = getattr(args, "supersedes", None)
    core_idea = getattr(args, "core_idea", None)
    if supersedes and not version:
        raise IngestError("--supersedes requires --version")
    if not version:
        if not core_idea:
            return entries
        out = []
        for e in entries:
            item = dict(e)
            item["core_idea"] = core_idea
            out.append(item)
        return out
    return apply_cycle_stamps(
        entries,
        version=version,
        supersedes=supersedes,
        core_idea=core_idea,
    )


def _commit_entries(entries) -> None:
    working = load_graph(GRAPH_PATH)
    for e in entries:
        working = append_entry(working, e)
    save_graph(working, GRAPH_PATH)


def _add_cycle_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--version",
        default=None,
        help="Cycle version stamped onto ingested ids (required with --supersedes)",
    )
    parser.add_argument(
        "--supersedes",
        default=None,
        help="Existing graph id the OOS (or sole) row supersedes",
    )
    parser.add_argument(
        "--core-idea",
        default=None,
        dest="core_idea",
        help="Override core_idea on stamped entries",
    )


def _windows_tag(windows: str | None) -> str:
    if not windows:
        return "all"
    parts = [w.strip() for w in windows.split(",") if w.strip()]
    return "+".join(parts) if parts else "all"


def _run_m1_dest(args) -> Path:
    direction = args.direction or "long"
    registry = args.registry or "spot"
    version = getattr(args, "version", None) or "defaults"
    windows = _windows_tag(getattr(args, "windows", None))
    return (
        EXPERIMENTS_ROOT
        / f"{date.today().isoformat()}-{args.strategy}-{registry}-{direction}-{version}-{windows}-m1"
    )


def _artifact_source(path: Path) -> str:
    """Prefer a repo-relative path so git-tracked graph entries are portable."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def _cmd_status(_args) -> int:
    s = status_summary(load_graph(GRAPH_PATH))
    print(f"updated={s['updated']}")
    print(f"n_entries={s['n_entries']}")
    for k in sorted(s["by_status"]):
        print(f"status {k}={s['by_status'][k]}")
    for k in sorted(s["by_family"]):
        print(f"family {k}={s['by_family'][k]}")
    return 0


def _cmd_relevant(args) -> int:
    rows = relevant(load_graph(GRAPH_PATH), family=args.family, status=args.status)
    for r in rows:
        tag = ""
        if r.get("obsolete"):
            nxt = r.get("superseded_by")
            tag = f" [obsolete -> {nxt}]" if nxt else " [obsolete]"
        print(f"{r['id']} {r['status']} {r['verdict']} {r['name']}{tag} — {r['failure_reason']}")
    return 0


def _cmd_ingest_m5(args) -> int:
    path = Path(args.json)
    try:
        payload = json.loads(path.read_text())
        entries = map_m5_payload(
            payload,
            include_incomplete=bool(args.include_incomplete),
            source=str(path),
            date=date.today().isoformat(),
        )
        entries = _maybe_stamp(entries, args)
        _commit_entries(entries)
    except (OSError, json.JSONDecodeError, GraphError, IngestError) as exc:
        print(f"ingest-m5 failed: {exc}", file=sys.stderr)
        return 1
    print(f"ingested {len(entries)} M5 entries")
    return 0


def _cmd_ingest_m1(args) -> int:
    path = Path(args.json)
    try:
        payload = json.loads(path.read_text())
        entries = map_m1_payload(
            payload, source=str(path), date=date.today().isoformat(),
        )
        entries = _maybe_stamp(entries, args)
        _commit_entries(entries)
    except (OSError, json.JSONDecodeError, GraphError, IngestError) as exc:
        print(f"ingest-m1 failed: {exc}", file=sys.stderr)
        return 1
    print(f"ingested {len(entries)} M1 entries")
    return 0


def _cmd_run_m1(args) -> int:
    if getattr(args, "supersedes", None) and not getattr(args, "version", None):
        print("run-m1 ingest failed: --supersedes requires --version", file=sys.stderr)
        return 1
    dest_dir = _run_m1_dest(args)
    if dest_dir.exists():
        print(
            f"run-m1 refused: dest already exists: {dest_dir}",
            file=sys.stderr,
        )
        return 1
    with tempfile.TemporaryDirectory(prefix="northstar-m1-") as td:
        tmp_json = Path(td) / "m1.json"
        argv = [
            sys.executable, str(EVAL_WINDOWS),
            "--strategy", args.strategy,
            "--json", str(tmp_json),
        ]
        if args.registry:
            argv.extend(["--registry", args.registry])
        if args.direction:
            argv.extend(["--direction", args.direction])
        if args.windows:
            argv.extend(["--windows", args.windows])
        if args.params:
            argv.extend(["--params", args.params])
        proc = run_subprocess(argv, timeout=RUN_M1_TIMEOUT_SEC)
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout or "run-m1 failed", file=sys.stderr)
            return 1
        try:
            payload = json.loads(tmp_json.read_text())
            entries = map_m1_payload(
                payload,
                source="",
                date=date.today().isoformat(),
            )
            entries = _maybe_stamp(entries, args)
        except (OSError, json.JSONDecodeError, IngestError) as exc:
            print(f"run-m1 ingest failed: {exc}", file=sys.stderr)
            return 1
        dest_dir.mkdir(parents=True, exist_ok=False)
        dest_json = dest_dir / "m1.json"
        try:
            shutil.copy2(tmp_json, dest_json)
            source_path = _artifact_source(dest_json)
            for entry in entries:
                entry["source"] = source_path
            _commit_entries(entries)
        except GraphError as exc:
            print(f"run-m1 ingest failed: {exc}", file=sys.stderr)
            shutil.rmtree(dest_dir, ignore_errors=True)
            return 1
        print(f"ingested {len(entries)} M1 entries -> {dest_json}")
        return 0


def _cmd_next(_args) -> int:
    print(json.dumps(propose_experiment(), indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="agents.loop_controller")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    sub.add_parser("next")

    pr = sub.add_parser("relevant")
    pr.add_argument("--family", default=None)
    pr.add_argument("--status", default=None)

    p5 = sub.add_parser("ingest-m5")
    p5.add_argument("--json", required=True)
    p5.add_argument("--include-incomplete", action="store_true")
    _add_cycle_flags(p5)

    p1 = sub.add_parser("ingest-m1")
    p1.add_argument("--json", required=True)
    _add_cycle_flags(p1)

    pm = sub.add_parser("run-m1")
    pm.add_argument("--strategy", required=True)
    pm.add_argument("--registry", default="spot")
    pm.add_argument("--direction", default=None)
    pm.add_argument("--windows", default=None)
    pm.add_argument("--params", default=None)
    _add_cycle_flags(pm)

    args = p.parse_args(argv)
    if args.cmd == "status":
        return _cmd_status(args)
    if args.cmd == "next":
        return _cmd_next(args)
    if args.cmd == "relevant":
        return _cmd_relevant(args)
    if args.cmd == "ingest-m5":
        return _cmd_ingest_m5(args)
    if args.cmd == "ingest-m1":
        return _cmd_ingest_m1(args)
    if args.cmd == "run-m1":
        return _cmd_run_m1(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
