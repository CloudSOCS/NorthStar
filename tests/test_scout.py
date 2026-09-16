from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from typer.testing import CliRunner

from poly.practice.orientation import CONTINUE
from poly.practice.walk import FOOTER, MIN_EDGE_TO_CARE, WalkQuote, WALK_RATE_LIMIT_WAIT

ET = ZoneInfo("America/New_York")
LIVE_CLOSE = "2026-09-13T16:15:00-04:00"
NOW_LIVE = datetime(2026, 9, 13, 16, 0, 0, tzinfo=ET)


def _quote(
    *,
    yes=0.38,
    no=0.63,
    edge=0.07,
    close_time=LIVE_CLOSE,
    ticker="KXBTC15M-26SEP131600-00",
):
    model = None if edge is None else yes + edge
    return WalkQuote(
        asset="BTC",
        question="BTC price up in next 15 mins?",
        yes_price=yes,
        no_price=no,
        model_prob=model,
        edge=edge,
        ticker=ticker,
        close_time=close_time,
    )


def test_leftover_yes_is_not_a_click():
    from poly.practice.scout import is_scout_click

    for yes in (0.06, 0.15, 0.90, 1.00):
        assert is_scout_click(_quote(yes=yes, edge=0.40), now=NOW_LIVE) is False


def test_closing_and_over_are_not_clicks():
    from poly.practice.scout import is_scout_click

    closing = _quote(close_time="2026-09-13T16:00:45-04:00")
    over = _quote(close_time="2026-09-13T15:45:00-04:00")
    unknown = _quote(close_time=None, ticker=None)
    assert is_scout_click(closing, now=NOW_LIVE) is False
    assert is_scout_click(over, now=NOW_LIVE) is False
    assert is_scout_click(unknown, now=NOW_LIVE) is False


def test_tiny_negative_and_missing_edge_are_not_clicks():
    from poly.practice.scout import is_scout_click

    assert is_scout_click(_quote(edge=None), now=NOW_LIVE) is False
    assert is_scout_click(_quote(edge=0.02), now=NOW_LIVE) is False
    assert is_scout_click(_quote(edge=-0.08), now=NOW_LIVE) is False
    assert 0.02 < MIN_EDGE_TO_CARE <= 0.07


def test_live_thirty_eight_cents_plus_seven_is_a_click():
    from poly.practice.scout import is_scout_click

    assert is_scout_click(_quote(yes=0.38, edge=0.07), now=NOW_LIVE) is True


def test_hedge_skip_does_not_block_a_click():
    from poly.practice.scout import is_scout_click
    from poly.practice.walk import hedge_verdict

    quote = _quote(yes=0.38, no=0.63, edge=0.07)
    assert hedge_verdict(quote.yes_price, quote.no_price) == "SKIP"
    assert is_scout_click(quote, now=NOW_LIVE) is True


def test_hours_refuse_zero_and_nine():
    from poly.practice.scout import HOURS_REFUSE, scout_hours_refuse

    assert scout_hours_refuse(0) == HOURS_REFUSE
    assert scout_hours_refuse(9) == HOURS_REFUSE
    assert scout_hours_refuse(1) is None
    assert scout_hours_refuse(8) is None
    assert scout_hours_refuse(6) is None


def test_next_wake_uses_grace_then_next_open():
    from poly.practice.scout import POST_OPEN_DELAY_SECONDS, next_scout_wake

    just_open = datetime(2026, 9, 13, 16, 0, 3, tzinfo=ET)
    wake = next_scout_wake(just_open)
    assert wake == datetime(2026, 9, 13, 16, 0, POST_OPEN_DELAY_SECONDS, tzinfo=ET)

    already_past_delay = datetime(2026, 9, 13, 16, 0, 8, tzinfo=ET)
    assert next_scout_wake(already_past_delay) == already_past_delay

    mid = datetime(2026, 9, 13, 16, 7, 0, tzinfo=ET)
    assert next_scout_wake(mid) == datetime(2026, 9, 13, 16, 15, 5, tzinfo=ET)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def sleep(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def _http_429() -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.elections.kalshi.com/")
    response = httpx.Response(429, request=request)
    return httpx.HTTPStatusError("Too Many Requests", request=request, response=response)


def test_start_and_end_copy():
    from poly.practice.scout import (
        ScoutCounts,
        format_scout_click_header,
        format_scout_end,
        format_scout_start,
    )

    assert format_scout_start("BTC", 6) == (
        "Scout BTC for 6 hours. Opens only. Silent except a real click. "
        "No order will be placed."
    )
    end = format_scout_end(ScoutCounts(windows=4, clicks=1, skips=3, rate_limits=0))
    assert end == (
        "Scout done. windows=4 clicks=1 skips=3 rate_limits=0. " + FOOTER
    )
    header = format_scout_click_header(_quote(yes=0.38, edge=0.07))
    assert header.startswith("SCOUT CLICK ")
    assert "YES 0.38" in header
    assert "edge +0.07" in header


def test_run_scout_one_click_then_deadline():
    from poly.practice.scout import run_scout

    clock = _Clock(datetime(2026, 9, 13, 16, 0, 8, tzinfo=ET))
    clicked = []

    def on_click(quote):
        clicked.append(quote)
        clock.now = clock.now + timedelta(hours=6)

    counts = run_scout(
        hours=6,
        now_fn=lambda: clock.now,
        sleep_fn=clock.sleep,
        load_fn=lambda _a: _quote(yes=0.38, edge=0.07),
        on_click=on_click,
    )
    assert counts.windows == 1
    assert counts.clicks == 1
    assert counts.skips == 0
    assert counts.rate_limits == 0
    assert len(clicked) == 1


def test_run_scout_does_not_rewalk_same_open():
    from poly.practice.scout import run_scout

    clock = _Clock(datetime(2026, 9, 13, 16, 0, 8, tzinfo=ET))
    sleeps: list[float] = []

    def sleep_fn(seconds: float) -> None:
        sleeps.append(seconds)
        clock.sleep(seconds)
        clock.now = clock.now + timedelta(hours=6)

    run_scout(
        hours=6,
        now_fn=lambda: clock.now,
        sleep_fn=sleep_fn,
        load_fn=lambda _a: _quote(yes=0.38, edge=0.07),
        on_click=lambda _q: None,
    )
    assert sleeps
    assert sleeps[0] >= 14 * 60


def test_run_scout_429_twice_skips_window():
    from poly.practice.scout import run_scout

    clock = _Clock(datetime(2026, 9, 13, 16, 0, 8, tzinfo=ET))
    sleeps: list[float] = []

    def sleep_fn(seconds: float) -> None:
        sleeps.append(seconds)
        clock.sleep(seconds)
        if seconds == WALK_RATE_LIMIT_WAIT:
            clock.now = clock.now + timedelta(hours=6)

    def load_fn(_asset: str):
        raise _http_429()

    counts = run_scout(
        hours=6,
        now_fn=lambda: clock.now,
        sleep_fn=sleep_fn,
        load_fn=load_fn,
        on_click=lambda _q: pytest.fail("must not click"),
    )
    assert counts.windows == 1
    assert counts.clicks == 0
    assert counts.skips == 1
    assert counts.rate_limits == 1
    assert WALK_RATE_LIMIT_WAIT in sleeps


def test_run_scout_429_then_click():
    from poly.practice.scout import run_scout

    clock = _Clock(datetime(2026, 9, 13, 16, 0, 8, tzinfo=ET))
    calls = {"n": 0}

    def load_fn(_asset: str):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_429()
        return _quote(yes=0.38, edge=0.07)

    def on_click(_quote) -> None:
        clock.now = clock.now + timedelta(hours=6)

    counts = run_scout(
        hours=6,
        now_fn=lambda: clock.now,
        sleep_fn=clock.sleep,
        load_fn=load_fn,
        on_click=on_click,
    )
    assert counts.windows == 1
    assert counts.clicks == 1
    assert counts.rate_limits == 0


def test_cli_refuse_hours_zero_and_nine():
    from poly.cli import app
    from poly.practice.scout import HOURS_REFUSE

    runner = CliRunner()
    for hours in ("0", "9"):
        result = runner.invoke(app, ["practice", "scout", "--hours", hours])
        assert result.exit_code == 1
        assert HOURS_REFUSE in result.output


def test_scout_allowlist_has_scout_not_live():
    from pathlib import Path

    from poly.practice.scout import format_scout_start

    charter = Path("docs/GROK_BOT.md").read_text()
    block = charter.split("## 4. Allowed commands only", 1)[1].split("## 5. Forbidden", 1)[0]
    assert "practice scout" in block
    assert "kalshi-live" not in block
    assert any("practice scout" in cmd for cmd in CONTINUE)
    assert not any("kalshi-live" in cmd for cmd in CONTINUE)
    src = Path("src/poly/practice/scout.py").read_text()
    assert "attempt_live_book" not in src
    assert "signed_create_order" not in src
    cli = Path("src/poly/cli.py").read_text()
    scout_src = cli.split("def practice_scout", 1)[1].split("def ", 1)[0]
    assert "attempt_live_book" not in scout_src
    assert "signed_create_order" not in scout_src
    assert "--save" not in scout_src
    assert format_scout_start("BTC", 6)
