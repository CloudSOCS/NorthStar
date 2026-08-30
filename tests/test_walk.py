import json

import pytest

from poly.practice.walk import (
    BANNER,
    DEFAULT_SPEND,
    DEMO_BANNER,
    FOOTER,
    MAX_SPEND,
    REPLAY_BANNER,
    REPLAY_FOOTER,
    WalkQuote,
    append_journal_entry,
    clamp_spend,
    default_journal_path,
    demo_quote,
    format_journal_edge,
    format_journal_time,
    format_walk,
    journal_entry,
    load_journal,
    lose_pnl,
    pair_cost,
    dump_journal_json,
    quote_from_journal_entry,
    recent_journal_entries,
    tickets_bought,
    win_pnl,
)


def test_step2_pnl_two_dollars_at_forty_cents():
    spend = 2.0
    price = 0.40
    assert tickets_bought(spend, price) == 5.0
    assert win_pnl(spend, price) == 3.0
    assert lose_pnl(spend, price) == -2.0


def test_cheap_pair_under_one_dollar():
    assert pair_cost(0.40, 0.40) == 0.80
    assert pair_cost(0.40, 0.40) < 1.0
    assert pair_cost(0.60, 0.55) == 1.15
    assert pair_cost(0.60, 0.55) > 1.0


def test_clamp_spend_default_and_cap():
    assert clamp_spend(2.0) == (2.0, None)
    usd, note = clamp_spend(10.0)
    assert usd == MAX_SPEND
    assert note is not None
    usd, note = clamp_spend(0.0)
    assert usd == DEFAULT_SPEND
    assert note is not None


def test_format_walk_has_four_steps_and_practice_only_footer():
    quote = WalkQuote(
        asset="ETH",
        question="Will ETH be above the strike?",
        yes_price=0.40,
        no_price=0.40,
        model_prob=0.50,
        edge=0.10,
    )
    text = format_walk(quote, spend=2.0)
    assert "Step 1" in text
    assert "Step 2" in text
    assert "Step 3" in text
    assert "Step 4" in text
    assert BANNER in text
    assert FOOTER in text
    assert "+$3.00" in text
    assert "too cheap" in text.lower()
    assert "cheap pair" in text.lower()
    assert "Hedge: CHEAP PAIR" in text


def test_demo_quote_uses_learning_md_numbers():
    quote = demo_quote()
    assert quote.asset == "DEMO"
    assert quote.yes_price == 0.40
    assert quote.no_price == 0.40
    assert quote.model_prob == 0.50
    assert quote.edge == 0.10
    text = format_walk(quote, spend=2.0, demo=True)
    assert DEMO_BANNER in text
    assert BANNER not in text
    assert FOOTER in text
    assert "+$3.00" in text
    assert "Hedge: CHEAP PAIR" in text
    assert "too cheap" in text.lower()


def test_demo_journal_entry_marks_source():
    entry = journal_entry(demo_quote(), spend=2.0, source="demo")
    assert entry["asset"] == "DEMO"
    assert entry["source"] == "demo"
    assert entry["yes_price"] == 0.40
    assert entry["tickets"] == 5.0
    assert entry["win_pnl"] == 3.0
    assert entry["edge"] == 0.10
    assert entry["hedge"] == "CHEAP PAIR"
    live = journal_entry(
        WalkQuote("ETH", "ETH", 0.40, 0.40, None, None),
        spend=2.0,
    )
    assert "source" not in live


def test_format_walk_expensive_pair_and_negative_edge():
    quote = WalkQuote(
        asset="BTC",
        question="BTC up/down",
        yes_price=0.80,
        no_price=0.55,
        model_prob=0.70,
        edge=-0.10,
    )
    text = format_walk(quote, spend=2.0)
    assert "too expensive" in text.lower()
    assert "skip" in text.lower()
    assert "Hedge: SKIP" in text


def test_format_walk_without_guess_does_not_invent_edge():
    quote = WalkQuote(
        asset="SOL",
        question="SOL",
        yes_price=0.50,
        no_price=0.50,
        model_prob=None,
        edge=None,
    )
    text = format_walk(quote, spend=2.0)
    assert "wait" in text.lower()
    assert "too cheap" not in text.lower()
    assert "Guess: not ready" in text
    assert "will not invent a number" in text


def test_walk_module_does_not_import_live():
    import inspect

    from poly.practice import walk

    source = inspect.getsource(walk)
    assert "execution.live" not in source
    assert "run_live_loop" not in source
    assert "hypothesis_graph" not in source


def test_journal_entry_edge_not_ready_and_cheap_pair():
    quote = WalkQuote(
        asset="ETH",
        question="Will ETH be above the strike?",
        yes_price=0.40,
        no_price=0.40,
        model_prob=None,
        edge=None,
    )
    entry = journal_entry(quote, spend=2.0, saved_at="2026-08-26T15:14:00-05:00")
    assert entry["saved_at"] == "2026-08-26T15:14:00-05:00"
    assert entry["asset"] == "ETH"
    assert entry["yes_price"] == 0.40
    assert entry["no_price"] == 0.40
    assert entry["spend"] == 2.0
    assert entry["tickets"] == 5.0
    assert entry["win_pnl"] == 3.0
    assert entry["lose_pnl"] == -2.0
    assert entry["edge"] == "not ready"
    assert entry["hedge"] == "CHEAP PAIR"
    assert entry["pair_cost"] == 0.80


def test_journal_entry_numeric_edge_and_skip():
    quote = WalkQuote(
        asset="BTC",
        question="BTC up/down",
        yes_price=0.80,
        no_price=0.55,
        model_prob=0.70,
        edge=-0.10,
    )
    entry = journal_entry(quote, spend=2.0)
    assert entry["edge"] == -0.10
    assert entry["hedge"] == "SKIP"


def test_append_journal_is_opt_in_append_only(tmp_path):
    path = tmp_path / "walk_journal.json"
    quote = WalkQuote(
        asset="SOL",
        question="SOL",
        yes_price=0.40,
        no_price=0.40,
        model_prob=0.50,
        edge=0.10,
    )
    first = journal_entry(quote, spend=2.0, saved_at="2026-08-26T15:00:00-05:00")
    append_journal_entry(first, path)
    second = journal_entry(quote, spend=2.0, saved_at="2026-08-26T15:01:00-05:00")
    append_journal_entry(second, path)
    blob = json.loads(path.read_text())
    assert blob["schema_version"] == 1
    assert len(blob["entries"]) == 2
    assert blob["entries"][0]["saved_at"] == "2026-08-26T15:00:00-05:00"
    assert blob["entries"][1]["saved_at"] == "2026-08-26T15:01:00-05:00"


def test_journal_path_uses_env(monkeypatch, tmp_path):
    target = tmp_path / "custom.json"
    monkeypatch.setenv("NORTHSTAR_WALK_JOURNAL", str(target))
    assert default_journal_path() == target


def test_load_journal_missing_file_does_not_create(tmp_path):
    path = tmp_path / "missing.json"
    blob = load_journal(path)
    assert blob["entries"] == []
    assert not path.exists()


def test_format_journal_cells():
    assert format_journal_time("2026-08-26T15:14:00-05:00") == "2026-08-26 15:14"
    assert format_journal_edge("not ready") == "not ready"
    assert format_journal_edge(-0.23) == "-0.23"
    assert format_journal_edge(0.10) == "+0.10"


def test_recent_journal_entries_newest_first():
    entries = [
        {"saved_at": "a", "asset": "BTC"},
        {"saved_at": "b", "asset": "ETH"},
        {"saved_at": "c", "asset": "SOL"},
    ]
    rows = recent_journal_entries(entries, last=2)
    assert [r["asset"] for r in rows] == ["SOL", "ETH"]
    assert recent_journal_entries(entries, last=0)[0]["asset"] == "SOL"


def test_dump_journal_json_empty():
    blob = dump_journal_json([], last=5)
    assert blob == {"schema_version": 1, "entries": []}


def test_dump_journal_json_newest_first_and_sliced():
    entries = [
        {"saved_at": "a", "asset": "BTC", "edge": "not ready"},
        {"saved_at": "b", "asset": "ETH", "edge": 0.10},
        {"saved_at": "c", "asset": "SOL", "edge": -0.05},
    ]
    blob = dump_journal_json(entries, last=2)
    assert blob["schema_version"] == 1
    assert [e["asset"] for e in blob["entries"]] == ["SOL", "ETH"]
    assert blob["entries"][0] is entries[2]
    assert [e["asset"] for e in entries] == ["BTC", "ETH", "SOL"]


def test_quote_from_journal_not_ready():
    entry = {
        "asset": "SOL",
        "question": "SOL",
        "yes_price": 0.50,
        "no_price": 0.50,
        "spend": 2.0,
        "edge": "not ready",
        "hedge": "SKIP",
    }
    quote, spend = quote_from_journal_entry(entry)
    assert spend == 2.0
    assert quote.model_prob is None
    assert quote.edge is None
    text = format_walk(quote, spend, replay=True, saved_at="2026-08-26T12:00:00-05:00")
    assert REPLAY_BANNER in text
    assert REPLAY_FOOTER in text
    assert "Guess: not ready" in text
    assert BANNER not in text
    assert FOOTER not in text


def test_quote_from_journal_rebuilds_guess_from_edge():
    entry = {
        "asset": "ETH",
        "question": "Will ETH be above the strike?",
        "yes_price": 0.40,
        "no_price": 0.40,
        "spend": 2.0,
        "edge": 0.10,
        "hedge": "CHEAP PAIR",
    }
    quote, spend = quote_from_journal_entry(entry)
    assert quote.model_prob == pytest.approx(0.50)
    assert quote.edge == pytest.approx(0.10)
    text = format_walk(
        quote, spend, replay=True, saved_at="2026-08-26T15:14:00-05:00"
    )
    assert REPLAY_BANNER in text
    assert REPLAY_FOOTER in text
    assert BANNER not in text
    assert FOOTER not in text
    assert "Saved at: 2026-08-26 15:14" in text
    assert "Step 1" in text
    assert "too cheap" in text.lower()
    assert "Hedge: CHEAP PAIR" in text


def _invoke_practice(args, monkeypatch, journal_path):
    from typer.testing import CliRunner

    from poly.cli import app

    monkeypatch.setenv("NORTHSTAR_WALK_JOURNAL", str(journal_path))
    return CliRunner().invoke(app, ["practice", *args])


def test_practice_journal_json_empty_missing_file(monkeypatch, tmp_path):
    path = tmp_path / "missing.json"
    result = _invoke_practice(["journal", "--json"], monkeypatch, path)
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"schema_version": 1, "entries": []}
    assert "No saved walks" not in result.stdout
    assert not path.exists()


def test_practice_last_json_defaults_to_newest_one(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {"saved_at": "a", "asset": "BTC", "edge": "not ready"},
                    {"saved_at": "b", "asset": "ETH", "edge": 0.10},
                ],
            }
        )
    )
    result = _invoke_practice(["last", "--json"], monkeypatch, path)
    assert result.exit_code == 0
    blob = json.loads(result.stdout)
    assert [e["asset"] for e in blob["entries"]] == ["ETH"]
    assert "NorthStar practice replay" not in result.stdout
    assert "Step 1" not in result.stdout


def test_practice_journal_json_respects_last(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {"saved_at": "a", "asset": "BTC"},
                    {"saved_at": "b", "asset": "ETH"},
                    {"saved_at": "c", "asset": "SOL"},
                ],
            }
        )
    )
    result = _invoke_practice(["journal", "--last", "2", "--json"], monkeypatch, path)
    assert result.exit_code == 0
    blob = json.loads(result.stdout)
    assert [e["asset"] for e in blob["entries"]] == ["SOL", "ETH"]
    assert "Practice journal" not in result.stdout


def test_practice_last_json_respects_n(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {"saved_at": "a", "asset": "BTC"},
                    {"saved_at": "b", "asset": "ETH"},
                    {"saved_at": "c", "asset": "SOL"},
                ],
            }
        )
    )
    result = _invoke_practice(["last", "--n", "3", "--json"], monkeypatch, path)
    assert result.exit_code == 0
    blob = json.loads(result.stdout)
    assert [e["asset"] for e in blob["entries"]] == ["SOL", "ETH", "BTC"]


def test_practice_journal_without_json_stays_human(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    result = _invoke_practice(["journal"], monkeypatch, path)
    assert result.exit_code == 0
    assert "No saved walks yet" in result.stdout


def test_practice_json_corrupt_journal_exits_nonzero(monkeypatch, tmp_path):
    path = tmp_path / "walk_journal.json"
    path.write_text("{not json")
    result = _invoke_practice(["journal", "--json"], monkeypatch, path)
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "Could not read journal" in (result.stderr or "")


def test_practice_walk_rate_limit_is_quiet_and_does_not_save(monkeypatch, tmp_path):
    import httpx

    path = tmp_path / "walk_journal.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [{"saved_at": "a", "asset": "BTC"}],
            }
        )
    )
    before = path.read_text()

    def boom(_asset, settings=None):
        raise httpx.HTTPStatusError(
            "Kalshi rate-limited after fetching 0/1 assets (missing: BTC). "
            "Wait ~10s and retry once.",
            request=None,
            response=None,
        )

    monkeypatch.setattr("poly.cli.load_walk_quote", boom)
    result = _invoke_practice(["walk", "--save"], monkeypatch, path)
    combined = (result.stdout or "") + (result.stderr or "")
    assert result.exit_code == 1
    assert (
        "Kalshi rate-limited. Wait and retry once. "
        "No lesson was saved. No order was placed."
    ) in combined
    assert "Traceback" not in combined
    assert "Step 1" not in combined
    assert "too cheap" not in combined.lower()
    assert path.read_text() == before


def test_practice_walk_demo_does_not_call_kalshi(monkeypatch, tmp_path):
    def boom(_asset, settings=None):
        raise AssertionError("load_walk_quote must not run on --demo")

    monkeypatch.setattr("poly.cli.load_walk_quote", boom)
    path = tmp_path / "walk_journal.json"
    result = _invoke_practice(["walk", "--demo"], monkeypatch, path)
    assert result.exit_code == 0
    assert DEMO_BANNER in result.stdout
    assert BANNER not in result.stdout
    assert "Step 1" in result.stdout
    assert "+$3.00" in result.stdout
    assert not path.exists()


def test_practice_walk_demo_save_writes_demo_source(monkeypatch, tmp_path):
    def boom(_asset, settings=None):
        raise AssertionError("load_walk_quote must not run on --demo")

    monkeypatch.setattr("poly.cli.load_walk_quote", boom)
    path = tmp_path / "walk_journal.json"
    result = _invoke_practice(["walk", "--demo", "--save"], monkeypatch, path)
    assert result.exit_code == 0
    blob = json.loads(path.read_text())
    assert len(blob["entries"]) == 1
    entry = blob["entries"][0]
    assert entry["asset"] == "DEMO"
    assert entry["source"] == "demo"
    assert entry["yes_price"] == 0.40
    assert entry["edge"] == 0.10
    assert entry["hedge"] == "CHEAP PAIR"


def _rate_err():
    import httpx

    return httpx.HTTPStatusError(
        "Kalshi rate-limited after fetching 0/1 assets (missing: BTC). "
        "Wait ~10s and retry once.",
        request=None,
        response=None,
    )


def _btc_market():
    from poly.clients.kalshi import KalshiMarket

    return KalshiMarket(
        asset="BTC",
        ticker="KXBTC15M-TEST",
        event_ticker="e",
        title="BTC price up in next 15 mins?",
        yes_sub_title="",
        yes_bid=0.39,
        yes_ask=0.40,
        no_bid=0.39,
        no_ask=0.40,
        last_price=0.40,
        close_time="",
    )


class _ScriptedFeed:
    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = 0

    def refresh_and_poll(self, assets):
        i = self.calls
        self.calls += 1
        if i < len(self.steps):
            step = self.steps[i]
        else:
            lists = [s for s in self.steps if not isinstance(s, BaseException)]
            if not lists:
                raise self.steps[-1]
            step = lists[-1]
        if isinstance(step, BaseException):
            raise step
        return step

    def trackers_for_assets(self, assets):
        return []


def test_load_walk_quote_success(monkeypatch):
    from poly.practice.walk import load_walk_quote

    monkeypatch.setattr("poly.practice.walk.time.sleep", lambda _s: None)
    quote = load_walk_quote("BTC", feed=_ScriptedFeed([[_btc_market()]]))
    assert quote is not None
    assert quote.asset == "BTC"
    assert quote.yes_price == 0.40
    assert quote.no_price == 0.40
    assert quote.edge is None


def test_load_walk_quote_retries_once_then_succeeds(monkeypatch):
    from poly.practice.walk import WALK_RATE_LIMIT_WAIT, load_walk_quote

    sleeps = []
    monkeypatch.setattr("poly.practice.walk.time.sleep", lambda s: sleeps.append(s))
    feed = _ScriptedFeed([_rate_err(), [_btc_market()]])
    quote = load_walk_quote("BTC", feed=feed)
    assert quote is not None
    assert quote.yes_price == 0.40
    assert WALK_RATE_LIMIT_WAIT in sleeps
    assert feed.calls >= 2


def test_load_walk_quote_keeps_snapshot_if_later_poll_429s(monkeypatch):
    from poly.practice.walk import load_walk_quote

    monkeypatch.setattr("poly.practice.walk.time.sleep", lambda _s: None)
    quote = load_walk_quote(
        "BTC",
        feed=_ScriptedFeed([[_btc_market()], _rate_err()]),
    )
    assert quote is not None
    assert quote.yes_price == 0.40
    assert quote.edge is None


def test_practice_walk_two_429s_teaching_line_journal_untouched(monkeypatch, tmp_path):
    from poly.practice.walk import load_walk_quote

    monkeypatch.setattr("poly.practice.walk.time.sleep", lambda _s: None)
    feed = _ScriptedFeed([_rate_err(), _rate_err()])
    monkeypatch.setattr(
        "poly.cli.load_walk_quote",
        lambda asset, settings=None: load_walk_quote(asset, feed=feed),
    )
    path = tmp_path / "walk_journal.json"
    path.write_text(
        json.dumps({"schema_version": 1, "entries": [{"saved_at": "a", "asset": "BTC"}]})
    )
    before = path.read_text()
    result = _invoke_practice(["walk", "--save"], monkeypatch, path)
    combined = (result.stdout or "") + (result.stderr or "")
    assert result.exit_code == 1
    assert (
        "Kalshi rate-limited. Wait and retry once. "
        "No lesson was saved. No order was placed."
    ) in combined
    assert "Traceback" not in combined
    assert path.read_text() == before
