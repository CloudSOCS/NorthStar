import json
from pathlib import Path

from poly.practice.orientation import (
    CONTINUE,
    HELPER,
    format_last_paper_line,
    format_last_walk_kind,
    format_last_walk_line,
    last_paper_entry,
    last_walk_kind,
    product_status_payload,
)


def test_product_status_empty_last_walk():
    blob = product_status_payload([])
    assert blob["schema_version"] == 1
    assert blob["fences"] == {
        "live_orders": "approve-per-order",
        "generator": "stubbed",
        "graph_command": "stop",
        "source": "static",
    }
    assert blob["helper"] == HELPER
    assert blob["helper"] == "must not run kalshi-live"
    assert blob["last_walk"] is None
    assert blob["last_walk_kind"] is None
    assert blob["last_walk_window"] == "unknown"
    assert blob["continue"] == CONTINUE
    assert blob["continue"] == [
        "uv run northstar status --json",
        "uv run northstar practice walk --demo --save",
        "uv run northstar practice walk --save",
        "uv run northstar practice scout --hours 6",
        "uv run northstar practice last --json",
        "uv run northstar practice journal --json",
        "uv run northstar practice paper list",
        "uv run northstar practice paper list --json",
        "uv run northstar practice paper postmortem",
        "uv run northstar practice paper postmortem --json",
    ]
    assert not any("buy" in cmd or "close" in cmd or "--live" in cmd for cmd in blob["continue"])
    assert not any("kalshi-live" in cmd for cmd in blob["continue"])
    assert not any("halt" in cmd or "resume" in cmd for cmd in blob["continue"])
    assert not any("paper book" in cmd or "paper settle" in cmd for cmd in blob["continue"])
    assert blob["last_paper"] is None
    assert blob["last_paper_kind"] is None
    assert format_last_walk_line(None) == "no saved walks yet"
    assert format_last_paper_line(None) == "no closed paper fills yet"


def test_product_status_uses_newest_stored_entry():
    entries = [
        {
            "saved_at": "2026-08-26T15:00:00-05:00",
            "asset": "BTC",
            "question": "BTC",
            "yes_price": 0.5,
            "no_price": 0.5,
            "spend": 2.0,
            "tickets": 4.0,
            "win_pnl": 2.0,
            "lose_pnl": -2.0,
            "edge": "not ready",
            "hedge": "SKIP",
            "pair_cost": 1.0,
        },
        {
            "saved_at": "2026-08-26T15:14:00-05:00",
            "asset": "ETH",
            "question": "Will ETH be above the strike?",
            "yes_price": 0.4,
            "no_price": 0.4,
            "spend": 2.0,
            "tickets": 5.0,
            "win_pnl": 3.0,
            "lose_pnl": -2.0,
            "edge": 0.1,
            "hedge": "CHEAP PAIR",
            "pair_cost": 0.8,
        },
    ]
    blob = product_status_payload(entries)
    assert blob["last_walk"]["asset"] == "ETH"
    assert blob["last_walk"]["kind"] == "live"
    assert blob["last_walk"] is not entries[1]
    assert "kind" not in entries[1]
    assert blob["last_walk_kind"] == "live"
    line = format_last_walk_line(blob["last_walk"])
    assert line == "ETH  2026-08-26 15:14  edge +0.10  hedge CHEAP PAIR"
    assert format_last_walk_kind(blob["last_walk"]) == "live Kalshi"


def test_last_paper_closed_only_subset():
    open_pos = {
        "id": "open1",
        "status": "open",
        "kind": "paper",
        "asset": "ETH",
        "side": "yes",
        "outcome": None,
        "realized_pnl": None,
    }
    older = {
        "id": "old1",
        "status": "settled",
        "kind": "paper",
        "asset": "ETH",
        "side": "no",
        "outcome": "no",
        "realized_pnl": 1.25,
        "question": "ignore me",
        "lesson": "do not copy",
    }
    newest = {
        "id": "8195d3ae",
        "status": "settled",
        "kind": "paper",
        "asset": "BTC",
        "side": "yes",
        "outcome": "no",
        "realized_pnl": -2.0,
        "question": "BTC price up in next 15 mins?",
        "lesson": "do not invent edge",
    }
    assert last_paper_entry([]) is None
    assert last_paper_entry([open_pos]) is None
    row = last_paper_entry([open_pos, older, newest])
    assert row == {
        "id": "8195d3ae",
        "kind": "paper",
        "asset": "BTC",
        "side": "yes",
        "outcome": "no",
        "realized_pnl": -2.0,
    }
    assert "lesson" not in row
    blob = product_status_payload([], paper_positions=[open_pos, older, newest])
    assert blob["last_paper"] == row
    assert blob["last_paper_kind"] == "paper"
    assert format_last_paper_line(row) == "BTC YES outcome NO  P&L -$2.00  (paper)"


def test_last_walk_kind_demo_vs_live():
    demo = {"asset": "DEMO", "source": "demo", "edge": 0.1}
    live = {"asset": "BTC", "edge": -0.07}
    demo_asset_only = {"asset": "DEMO", "edge": 0.1}
    assert last_walk_kind(None) is None
    assert last_walk_kind(demo) == "demo"
    assert last_walk_kind(demo_asset_only) == "demo"
    assert last_walk_kind(live) == "live"
    assert format_last_walk_kind(None) == "no saved walks yet"
    assert format_last_walk_kind(demo) == "demo snapshot — not a live Kalshi market"
    assert format_last_walk_kind(live) == "live Kalshi"


def test_orientation_does_not_import_live_or_graph():
    import ast
    import inspect

    from poly.practice import orientation

    tree = ast.parse(inspect.getsource(orientation))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert all(not name.startswith("agents") for name in imported)
    assert all("execution.live" not in name for name in imported)
    assert "propose_experiment" not in inspect.getsource(orientation)
    assert "load_graph" not in inspect.getsource(orientation)


def _invoke_status(args, monkeypatch, journal_path, paper_path=None):
    from typer.testing import CliRunner

    from poly.cli import app

    monkeypatch.setenv("NORTHSTAR_WALK_JOURNAL", str(journal_path))
    if paper_path is None:
        paper_path = journal_path.parent / "paper_positions.json"
    monkeypatch.setenv("NORTHSTAR_PAPER_POSITIONS", str(paper_path))
    return CliRunner().invoke(app, ["status", *args])


def test_status_json_empty_missing_file(monkeypatch, tmp_path):
    path = tmp_path / "missing.json"
    monkeypatch.setenv("NORTHSTAR_CODE", "")
    result = _invoke_status(["--json"], monkeypatch, path)
    assert result.exit_code == 0
    blob = json.loads(result.stdout)
    assert blob["last_walk"] is None
    assert blob["last_walk_kind"] is None
    assert blob["last_walk_window"] == "unknown"
    assert blob["last_paper"] is None
    assert blob["last_paper_kind"] is None
    assert blob["fences"]["live_orders"] == "approve-per-order"
    assert blob["helper"] == "must not run kalshi-live"
    assert blob["fences"]["source"] == "static"
    assert blob["live_halt"] == "unknown"
    assert blob["code"] == "unknown"
    assert "Places real orders" not in result.stdout
    assert not path.exists()


def test_status_json_newest_walk_no_chrome(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    newest = {
        "saved_at": "2026-08-26T15:14:00-05:00",
        "asset": "ETH",
        "edge": 0.1,
        "hedge": "CHEAP PAIR",
        "ticker": "KXETH15M-TEST",
    }
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {"saved_at": "a", "asset": "BTC", "edge": "not ready", "hedge": "SKIP"},
                    newest,
                ],
            }
        )
    )
    result = _invoke_status(["--json"], monkeypatch, path)
    assert result.exit_code == 0
    blob = json.loads(result.stdout)
    assert blob["last_walk"]["asset"] == "ETH"
    assert blob["last_walk"]["hedge"] == "CHEAP PAIR"
    assert blob["last_walk"]["ticker"] == "KXETH15M-TEST"
    assert blob["last_walk_kind"] == "live"
    assert "NorthStar status" not in result.stdout
    assert "no saved walks yet" not in result.stdout


def test_status_human_empty_and_continue(monkeypatch, tmp_path):
    path = tmp_path / "missing.json"
    monkeypatch.setenv("NORTHSTAR_CODE", "")
    result = _invoke_status([], monkeypatch, path)
    assert result.exit_code == 0
    text = result.stdout
    assert "approve-per-order" in text
    assert "must not run kalshi-live" in text
    assert "Live halt: unknown (Mini only)" in text
    assert "Code: unknown" in text
    assert "Live halt: on" not in text
    assert "Live halt: off" not in text
    assert "kalshi-live book" not in text
    assert "stubbed" in text
    assert "stop" in text.lower()
    assert "no saved walks yet" in text
    assert "no closed paper fills yet" in text
    assert "uv run northstar status --json" in text
    assert "uv run northstar practice walk --demo --save" in text
    assert "uv run northstar practice walk --save" in text
    assert "uv run northstar practice scout --hours 6" in text
    assert "uv run northstar practice last --json" in text
    assert "uv run northstar practice journal --json" in text
    assert "uv run northstar practice paper list" in text
    assert "uv run northstar practice paper list --json" in text
    assert "uv run northstar practice paper postmortem" in text
    assert "uv run northstar practice paper postmortem --json" in text
    assert "paper book" not in text
    assert "paper settle" not in text
    assert "This is a status check, not a trade." in text
    assert "Places real orders" not in text


def test_status_human_shows_last_lesson(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "saved_at": "2026-08-26T15:14:00-05:00",
                        "asset": "ETH",
                        "edge": 0.1,
                        "hedge": "CHEAP PAIR",
                    }
                ],
            }
        )
    )
    result = _invoke_status([], monkeypatch, path)
    assert result.exit_code == 0
    assert "ETH" in result.stdout
    assert "2026-08-26 15:14" in result.stdout
    assert "+0.10" in result.stdout
    assert "CHEAP PAIR" in result.stdout
    assert "live Kalshi" in result.stdout


def test_status_human_and_json_label_demo(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "saved_at": "2026-08-29T18:44:15+00:00",
                        "asset": "DEMO",
                        "source": "demo",
                        "edge": 0.1,
                        "hedge": "CHEAP PAIR",
                    }
                ],
            }
        )
    )
    human = _invoke_status([], monkeypatch, path)
    assert human.exit_code == 0
    assert "demo snapshot — not a live Kalshi market" in human.stdout
    assert "DEMO" in human.stdout
    dumped = _invoke_status(["--json"], monkeypatch, path)
    blob = json.loads(dumped.stdout)
    assert blob["last_walk_kind"] == "demo"
    assert blob["last_walk_window"] == "unknown"
    assert blob["last_walk"]["source"] == "demo"
    assert "Window:" not in human.stdout


def test_status_json_newest_closed_paper(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    paper = tmp_path / "paper_positions.json"
    journal.write_text(json.dumps({"schema_version": 1, "entries": []}))
    paper.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "positions": [
                    {
                        "id": "open1",
                        "status": "open",
                        "asset": "ETH",
                        "side": "yes",
                    },
                    {
                        "id": "8195d3ae",
                        "status": "settled",
                        "asset": "BTC",
                        "side": "yes",
                        "outcome": "no",
                        "realized_pnl": -2.0,
                        "lesson": "should not appear",
                    },
                ],
            }
        )
    )
    dumped = _invoke_status(["--json"], monkeypatch, journal, paper)
    assert dumped.exit_code == 0
    blob = json.loads(dumped.stdout)
    assert blob["last_paper"] == {
        "id": "8195d3ae",
        "kind": "paper",
        "asset": "BTC",
        "side": "yes",
        "outcome": "no",
        "realized_pnl": -2.0,
    }
    assert blob["last_paper_kind"] == "paper"
    assert "lesson" not in blob["last_paper"]
    human = _invoke_status([], monkeypatch, journal, paper)
    assert human.exit_code == 0
    assert "BTC YES outcome NO  P&L -$2.00  (paper)" in human.stdout


def test_status_json_open_only_paper_is_null(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    paper = tmp_path / "paper_positions.json"
    journal.write_text(json.dumps({"schema_version": 1, "entries": []}))
    paper.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "positions": [{"id": "open1", "status": "open", "asset": "BTC"}],
            }
        )
    )
    result = _invoke_status(["--json"], monkeypatch, journal, paper)
    assert result.exit_code == 0
    blob = json.loads(result.stdout)
    assert blob["last_paper"] is None
    assert blob["last_paper_kind"] is None


def test_status_json_corrupt_paper_exits_nonzero(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    paper = tmp_path / "paper_positions.json"
    journal.write_text(json.dumps({"schema_version": 1, "entries": []}))
    paper.write_text("{not json")
    result = _invoke_status(["--json"], monkeypatch, journal, paper)
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "Could not read paper" in (result.stderr or "")


def test_status_json_corrupt_journal_exits_nonzero(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    path.write_text("{not json")
    result = _invoke_status(["--json"], monkeypatch, path)
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "Could not read journal" in (result.stderr or "")


def test_status_readable_halt_file_shows_on_or_off(monkeypatch, tmp_path):
    journal = tmp_path / "missing.json"
    halt = tmp_path / "live_halt.json"
    monkeypatch.setenv("NORTHSTAR_LIVE_HALT", str(halt))
    halt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "halted": True,
                "reason": "manual",
                "realized_live_pnl": None,
                "halted_at": "2026-09-10T13:00:00-05:00",
            }
        )
        + "\n"
    )
    dumped = _invoke_status(["--json"], monkeypatch, journal)
    assert dumped.exit_code == 0
    blob = json.loads(dumped.stdout)
    assert blob["live_halt"] == "on"
    human = _invoke_status([], monkeypatch, journal)
    assert human.exit_code == 0
    assert "Live halt: on" in human.stdout
    assert "unknown (Mini only)" not in human.stdout

    halt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "halted": False,
                "reason": "cleared",
                "realized_live_pnl": None,
                "halted_at": None,
            }
        )
        + "\n"
    )
    dumped = _invoke_status(["--json"], monkeypatch, journal)
    assert dumped.exit_code == 0
    assert json.loads(dumped.stdout)["live_halt"] == "off"
    human = _invoke_status([], monkeypatch, journal)
    assert human.exit_code == 0
    assert "Live halt: off" in human.stdout
    assert "unknown (Mini only)" not in human.stdout


def test_grok_bot_charter_isolation_and_weekly_receipt():
    charter = Path("docs/GROK_BOT.md").read_text()
    assert "Shared Grok computer is not isolation" in charter
    assert "~/.poly/live_halt.json" in charter
    assert "KALSHI_PRIVATE_KEY_PATH" in charter
    assert "Helper must not run `kalshi-live`, halt, or resume" in charter
    assert "Weekly receipt = `status --json` + paper postmortem" in charter
    assert "human spot-checks one artifact" in charter
    block = charter.split("## 4. Allowed commands only", 1)[1].split("## 5. Forbidden", 1)[0]
    assert "kalshi-live" not in block
    assert "halt" not in block
    assert "resume" not in block


def test_status_does_not_call_live_book_or_signer():
    status_src = Path("src/poly/cli.py").read_text().split("def status(", 1)[1]
    status_src = status_src.split('if __name__ == "__main__":', 1)[0]
    assert "signed_create_order" not in status_src
    assert "attempt_live_book" not in status_src
    assert "write_manual_halt" not in status_src
    assert "clear_halt" not in status_src
    assert "run_live_loop" not in status_src


def test_status_code_from_env_or_unknown(monkeypatch, tmp_path):
    journal = tmp_path / "missing.json"
    monkeypatch.setenv("NORTHSTAR_CODE", "deadbeef")
    dumped = _invoke_status(["--json"], monkeypatch, journal)
    assert dumped.exit_code == 0
    assert json.loads(dumped.stdout)["code"] == "deadbeef"
    human = _invoke_status([], monkeypatch, journal)
    assert human.exit_code == 0
    assert "Code: deadbeef" in human.stdout
    monkeypatch.setenv("NORTHSTAR_CODE", "")
    dumped = _invoke_status(["--json"], monkeypatch, journal)
    assert json.loads(dumped.stdout)["code"] == "unknown"
    assert "Code: unknown" in _invoke_status([], monkeypatch, journal).stdout


WINDOW_NOW = "2026-09-13T16:00:00-04:00"
WINDOW_OVER_LINE = "Window: OVER — this 15m is done. Don't click."
WINDOW_CLOSING_LINE = "Window: CLOSING — under a minute left. Don't click."


def _window_journal(path: Path, **entry):
    row = {
        "saved_at": "2026-09-13T15:50:00-04:00",
        "asset": "BTC",
        "edge": -0.06,
        "hedge": "SKIP",
        "ticker": "KXBTC15M-TEST",
    }
    row.update(entry)
    path.write_text(json.dumps({"schema_version": 1, "entries": [row]}))


def test_status_last_walk_window_over_closing_live_unknown(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    monkeypatch.setenv("NORTHSTAR_NOW", WINDOW_NOW)

    _window_journal(journal, close_time="2026-09-13T15:45:00-04:00")
    over = json.loads(_invoke_status(["--json"], monkeypatch, journal).stdout)
    assert over["last_walk_window"] == "over"
    human = _invoke_status([], monkeypatch, journal)
    assert WINDOW_OVER_LINE in human.stdout
    assert WINDOW_CLOSING_LINE not in human.stdout

    _window_journal(journal, close_time="2026-09-13T16:00:45-04:00")
    closing = json.loads(_invoke_status(["--json"], monkeypatch, journal).stdout)
    assert closing["last_walk_window"] == "closing"
    assert WINDOW_CLOSING_LINE in _invoke_status([], monkeypatch, journal).stdout

    _window_journal(journal, close_time="2026-09-13T16:15:00-04:00")
    live = json.loads(_invoke_status(["--json"], monkeypatch, journal).stdout)
    assert live["last_walk_window"] == "live"
    assert "Window:" not in _invoke_status([], monkeypatch, journal).stdout

    _window_journal(journal)
    unknown = json.loads(_invoke_status(["--json"], monkeypatch, journal).stdout)
    assert unknown["last_walk_window"] == "unknown"
    assert "Window:" not in _invoke_status([], monkeypatch, journal).stdout


def test_status_last_walk_window_demo_stays_unknown(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    monkeypatch.setenv("NORTHSTAR_NOW", WINDOW_NOW)
    _window_journal(
        journal,
        asset="DEMO",
        source="demo",
        close_time="2026-09-13T15:45:00-04:00",
        ticker="KXBTC15M-26SEP131545-45",
    )
    blob = json.loads(_invoke_status(["--json"], monkeypatch, journal).stdout)
    assert blob["last_walk_window"] == "unknown"
    assert blob["last_walk_kind"] == "demo"
    assert "Window:" not in _invoke_status([], monkeypatch, journal).stdout

