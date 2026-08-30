import json

from poly.practice.orientation import (
    CONTINUE,
    HELPER,
    format_last_walk_kind,
    format_last_walk_line,
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
    assert blob["continue"] == CONTINUE
    assert blob["continue"] == [
        "uv run northstar status --json",
        "uv run northstar practice walk --demo --save",
        "uv run northstar practice walk --save",
        "uv run northstar practice last --json",
        "uv run northstar practice journal --json",
        "uv run northstar practice paper list",
        "uv run northstar practice paper postmortem",
        "uv run northstar practice paper postmortem --json",
    ]
    assert not any("buy" in cmd or "close" in cmd or "--live" in cmd for cmd in blob["continue"])
    assert not any("kalshi-live" in cmd for cmd in blob["continue"])
    assert not any("paper book" in cmd or "paper settle" in cmd for cmd in blob["continue"])
    assert format_last_walk_line(None) == "no saved walks yet"


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


def _invoke_status(args, monkeypatch, journal_path):
    from typer.testing import CliRunner

    from poly.cli import app

    monkeypatch.setenv("NORTHSTAR_WALK_JOURNAL", str(journal_path))
    return CliRunner().invoke(app, ["status", *args])


def test_status_json_empty_missing_file(monkeypatch, tmp_path):
    path = tmp_path / "missing.json"
    result = _invoke_status(["--json"], monkeypatch, path)
    assert result.exit_code == 0
    blob = json.loads(result.stdout)
    assert blob["last_walk"] is None
    assert blob["last_walk_kind"] is None
    assert blob["fences"]["live_orders"] == "approve-per-order"
    assert blob["helper"] == "must not run kalshi-live"
    assert blob["fences"]["source"] == "static"
    assert "Places real orders" not in result.stdout
    assert not path.exists()


def test_status_json_newest_walk_no_chrome(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    newest = {
        "saved_at": "2026-08-26T15:14:00-05:00",
        "asset": "ETH",
        "edge": 0.1,
        "hedge": "CHEAP PAIR",
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
    assert blob["last_walk_kind"] == "live"
    assert "NorthStar status" not in result.stdout
    assert "no saved walks yet" not in result.stdout


def test_status_human_empty_and_continue(monkeypatch, tmp_path):
    path = tmp_path / "missing.json"
    result = _invoke_status([], monkeypatch, path)
    assert result.exit_code == 0
    text = result.stdout
    assert "approve-per-order" in text
    assert "must not run kalshi-live" in text
    assert "kalshi-live book" not in text
    assert "stubbed" in text
    assert "stop" in text.lower()
    assert "no saved walks yet" in text
    assert "uv run northstar status --json" in text
    assert "uv run northstar practice walk --demo --save" in text
    assert "uv run northstar practice walk --save" in text
    assert "uv run northstar practice last --json" in text
    assert "uv run northstar practice journal --json" in text
    assert "uv run northstar practice paper list" in text
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
    assert blob["last_walk"]["source"] == "demo"


def test_status_json_corrupt_journal_exits_nonzero(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    path.write_text("{not json")
    result = _invoke_status(["--json"], monkeypatch, path)
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "Could not read journal" in (result.stderr or "")
