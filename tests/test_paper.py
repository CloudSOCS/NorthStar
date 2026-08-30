import json

import pytest

from poly.practice.paper import (
    PAPER_FOOTER,
    PAPER_SCHEMA,
    book_from_entry,
    default_paper_path,
    dump_paper_json,
    load_paper,
    settle_paper,
)
from poly.practice.walk import last_walk_kind


BTC_SKIP = {
    "saved_at": "2026-08-30T16:55:24+00:00",
    "asset": "BTC",
    "question": "BTC price up in next 15 mins?",
    "yes_price": 0.8,
    "no_price": 0.21,
    "spend": 2.0,
    "tickets": 2.5,
    "win_pnl": 0.5,
    "lose_pnl": -2.0,
    "edge": "not ready",
    "hedge": "SKIP",
    "pair_cost": 1.01,
}

DEMO_CHEAP = {
    "saved_at": "2026-08-29T18:44:15+00:00",
    "asset": "DEMO",
    "question": "Teaching snapshot — not a live market",
    "yes_price": 0.4,
    "no_price": 0.4,
    "spend": 2.0,
    "tickets": 5.0,
    "win_pnl": 3.0,
    "lose_pnl": -2.0,
    "edge": 0.1,
    "hedge": "CHEAP PAIR",
    "pair_cost": 0.8,
    "source": "demo",
}


def test_paper_path_uses_env(monkeypatch, tmp_path):
    target = tmp_path / "paper_positions.json"
    monkeypatch.setenv("NORTHSTAR_PAPER_POSITIONS", str(target))
    assert default_paper_path() == target


def test_load_paper_missing_file_does_not_create(tmp_path):
    path = tmp_path / "missing.json"
    blob = load_paper(path)
    assert blob == {"schema_version": PAPER_SCHEMA, "positions": []}
    assert not path.exists()


def test_book_from_last_yes_is_paper_kind():
    pos = book_from_entry(BTC_SKIP, side="yes")
    assert pos["kind"] == "paper"
    assert pos["side"] == "yes"
    assert pos["status"] == "open"
    assert pos["asset"] == "BTC"
    assert pos["ticket_price"] == 0.8
    assert pos["spend"] == 2.0
    assert pos["tickets"] == 2.5
    assert pos["win_pnl"] == 0.5
    assert pos["lose_pnl"] == -2.0
    assert pos["from_saved_at"] == BTC_SKIP["saved_at"]
    assert pos["from_kind"] == "live"
    assert pos["pair_id"] is None
    assert pos["outcome"] is None
    assert pos["realized_pnl"] is None
    assert last_walk_kind(BTC_SKIP) == "live"


def test_book_side_no_uses_step2_math():
    pos = book_from_entry(BTC_SKIP, side="no")
    assert pos["side"] == "no"
    assert pos["ticket_price"] == 0.21
    assert pos["tickets"] == pytest.approx(2.0 / 0.21, abs=1e-4)
    assert pos["win_pnl"] == pytest.approx((2.0 / 0.21) - 2.0, abs=1e-4)
    assert pos["lose_pnl"] == -2.0
    assert pos["kind"] == "paper"


def test_book_both_refused_when_pair_not_cheap():
    try:
        book_from_entry(BTC_SKIP, both=True)
    except ValueError as exc:
        assert "both sides" in str(exc).lower() or "hedge" in str(exc).lower()
    else:
        raise AssertionError("expected refuse")


def test_book_both_cheap_pair_two_paper_legs():
    yes, no = book_from_entry(DEMO_CHEAP, both=True)
    assert yes["kind"] == "paper"
    assert no["kind"] == "paper"
    assert yes["side"] == "yes"
    assert no["side"] == "no"
    assert yes["pair_id"] == no["pair_id"]
    assert yes["pair_id"]
    assert yes["tickets"] == 5.0
    assert no["tickets"] == 5.0
    assert yes["from_kind"] == "demo"


def test_settle_yes_win_and_no_lose_step2():
    pos = book_from_entry(BTC_SKIP, side="yes")
    blob = {"schema_version": 1, "positions": [pos]}
    won = settle_paper(blob, pos["id"], outcome="yes")
    assert won["status"] == "settled"
    assert won["outcome"] == "yes"
    assert won["realized_pnl"] == 0.5
    lost = book_from_entry(BTC_SKIP, side="yes")
    blob2 = {"schema_version": 1, "positions": [lost]}
    settled = settle_paper(blob2, lost["id"], outcome="no")
    assert settled["realized_pnl"] == -2.0


def test_dump_paper_json_empty():
    assert dump_paper_json([]) == {"schema_version": 1, "positions": []}


def test_dump_paper_json_newest_first():
    a = book_from_entry(DEMO_CHEAP, side="yes")
    b = book_from_entry(BTC_SKIP, side="yes")
    blob = dump_paper_json([a, b])
    assert [p["asset"] for p in blob["positions"]] == ["BTC", "DEMO"]


def test_paper_module_does_not_import_live():
    import inspect

    from poly.practice import paper

    source = inspect.getsource(paper)
    assert "execution.live" not in source
    assert "hypothesis_graph" not in source
    assert "load_walk_quote" not in source


def _write_journal(path, entries):
    path.write_text(json.dumps({"schema_version": 1, "entries": entries}))


def _invoke_paper(args, monkeypatch, journal_path, paper_path):
    from typer.testing import CliRunner

    from poly.cli import app

    monkeypatch.setenv("NORTHSTAR_WALK_JOURNAL", str(journal_path))
    monkeypatch.setenv("NORTHSTAR_PAPER_POSITIONS", str(paper_path))
    return CliRunner().invoke(app, ["practice", "paper", *args])


def test_practice_paper_book_last_no_kalshi(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    paper = tmp_path / "paper_positions.json"
    _write_journal(journal, [DEMO_CHEAP, BTC_SKIP])

    def boom(*_a, **_k):
        raise AssertionError("must not fetch Kalshi to book --last")

    monkeypatch.setattr("poly.cli.load_walk_quote", boom)
    result = _invoke_paper(["book", "--last"], monkeypatch, journal, paper)
    assert result.exit_code == 0
    assert PAPER_FOOTER in result.stdout
    assert "paper" in result.stdout.lower()
    blob = json.loads(paper.read_text())
    assert len(blob["positions"]) == 1
    pos = blob["positions"][0]
    assert pos["kind"] == "paper"
    assert pos["asset"] == "BTC"
    assert pos["side"] == "yes"
    assert pos["tickets"] == 2.5


def test_practice_paper_book_empty_journal(monkeypatch, tmp_path):
    journal = tmp_path / "missing.json"
    paper = tmp_path / "paper_positions.json"
    result = _invoke_paper(["book"], monkeypatch, journal, paper)
    assert result.exit_code == 1
    assert PAPER_FOOTER in (result.stdout or "") + (result.stderr or "")
    assert not paper.exists()


def test_practice_paper_book_both_refused_on_skip(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    paper = tmp_path / "paper_positions.json"
    _write_journal(journal, [BTC_SKIP])
    result = _invoke_paper(["book", "--both"], monkeypatch, journal, paper)
    assert result.exit_code == 1
    assert not paper.exists() or json.loads(paper.read_text())["positions"] == []


def test_practice_paper_book_both_cheap_pair(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    paper = tmp_path / "paper_positions.json"
    _write_journal(journal, [DEMO_CHEAP])
    result = _invoke_paper(["book", "--both"], monkeypatch, journal, paper)
    assert result.exit_code == 0
    blob = json.loads(paper.read_text())
    assert len(blob["positions"]) == 2
    assert {p["side"] for p in blob["positions"]} == {"yes", "no"}
    assert blob["positions"][0]["pair_id"] == blob["positions"][1]["pair_id"]
    assert all(p["kind"] == "paper" for p in blob["positions"])


def test_practice_paper_list_json_and_settle(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    paper = tmp_path / "paper_positions.json"
    _write_journal(journal, [BTC_SKIP])
    booked = _invoke_paper(["book"], monkeypatch, journal, paper)
    assert booked.exit_code == 0
    listed = _invoke_paper(["list", "--json"], monkeypatch, journal, paper)
    assert listed.exit_code == 0
    blob = json.loads(listed.stdout)
    assert blob["schema_version"] == 1
    assert blob["positions"][0]["kind"] == "paper"
    pid = blob["positions"][0]["id"]
    settled = _invoke_paper(
        ["settle", "--id", pid, "--outcome", "no"], monkeypatch, journal, paper
    )
    assert settled.exit_code == 0
    assert PAPER_FOOTER in settled.stdout
    again = json.loads(
        _invoke_paper(["list", "--json"], monkeypatch, journal, paper).stdout
    )
    assert again["positions"][0]["status"] == "settled"
    assert again["positions"][0]["realized_pnl"] == -2.0


def test_practice_paper_list_json_empty(monkeypatch, tmp_path):
    journal = tmp_path / "walk_journal.json"
    paper = tmp_path / "missing_paper.json"
    result = _invoke_paper(["list", "--json"], monkeypatch, journal, paper)
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"schema_version": 1, "positions": []}
    assert not paper.exists()


def test_paper_backtest_runs():
    from poly.execution.paper import run_paper_backtest

    result = run_paper_backtest(n_windows=50, seed=123)
    assert result.n_windows == 50
    assert result.ending_bankroll > 0
    assert result.n_trades >= 0
