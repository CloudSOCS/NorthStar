import json

import pytest

from poly.practice.walk import (
    BANNER,
    DEFAULT_SPEND,
    FOOTER,
    MAX_SPEND,
    REPLAY_BANNER,
    REPLAY_FOOTER,
    WalkQuote,
    append_journal_entry,
    clamp_spend,
    default_journal_path,
    format_journal_edge,
    format_journal_time,
    format_walk,
    journal_entry,
    load_journal,
    lose_pnl,
    pair_cost,
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
