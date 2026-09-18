"""Read-only 15m open scout. Prints a walk panel only on a real YES click. Never sends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import httpx

from poly.alerts import AlertConfig, confirm_live_book, copy_to_clipboard, fire
from poly.practice.paper import VENUE_TZ
from poly.practice.walk import (
    DEFAULT_SPEND,
    FOOTER,
    MIN_EDGE_TO_CARE,
    WALK_RATE_LIMIT_WAIT,
    WalkQuote,
    is_kalshi_rate_limit,
    last_walk_window,
)

HOURS_REFUSE = "Scout hours must be 1–8. No loop started. No order was placed."
SCOUT_BOOK_WARNING = "Run this on Mini. Helper must not run kalshi-live."
SCOUT_HOURS_MIN = 1
SCOUT_HOURS_MAX = 8
DEFAULT_SCOUT_HOURS = 6
OPEN_GRACE_SECONDS = 90
POST_OPEN_DELAY_SECONDS = 5
LEFTOVER_YES_LOW = 0.15
LEFTOVER_YES_HIGH = 0.90


def scout_hours_refuse(hours: int) -> Optional[str]:
    if hours < SCOUT_HOURS_MIN or hours > SCOUT_HOURS_MAX:
        return HOURS_REFUSE
    return None


def current_window_open(now: datetime) -> datetime:
    clock = now if now.tzinfo else now.replace(tzinfo=VENUE_TZ)
    minute = (clock.minute // 15) * 15
    return clock.replace(minute=minute, second=0, microsecond=0)


def next_scout_wake(now: datetime) -> datetime:
    """Walk this open if within grace; otherwise the next open plus delay."""
    clock = now if now.tzinfo else now.replace(tzinfo=VENUE_TZ)
    open_ = current_window_open(clock)
    elapsed = (clock - open_).total_seconds()
    if elapsed <= OPEN_GRACE_SECONDS:
        target = open_ + timedelta(seconds=POST_OPEN_DELAY_SECONDS)
        return clock if clock >= target else target
    return open_ + timedelta(minutes=15, seconds=POST_OPEN_DELAY_SECONDS)


def next_open_after(now: datetime) -> datetime:
    open_ = current_window_open(now)
    return open_ + timedelta(minutes=15, seconds=POST_OPEN_DELAY_SECONDS)


def is_scout_click(quote: WalkQuote, now: Optional[datetime] = None) -> bool:
    state = last_walk_window(
        {"close_time": quote.close_time, "ticker": quote.ticker},
        now=now,
    )
    if state != "live":
        return False
    if quote.edge is None or quote.edge < MIN_EDGE_TO_CARE:
        return False
    if quote.yes_price <= LEFTOVER_YES_LOW or quote.yes_price >= LEFTOVER_YES_HIGH:
        return False
    return True


def format_scout_start(asset: str, hours: int) -> str:
    return (
        f"Scout {asset} for {hours} hours. Opens only. "
        "Silent except a real click. No order will be placed."
    )


def format_scout_end(counts: "ScoutCounts") -> str:
    return (
        f"Scout done. windows={counts.windows} clicks={counts.clicks} "
        f"skips={counts.skips} rate_limits={counts.rate_limits}. {FOOTER}"
    )


def format_scout_click_header(quote: WalkQuote) -> str:
    ticker = (quote.ticker or "").strip()
    edge = quote.edge if quote.edge is not None else 0.0
    return f"SCOUT CLICK {ticker} YES {quote.yes_price:.2f} edge {edge:+.2f}"


def _format_scout_spend(spend: float) -> str:
    if spend == int(spend):
        return str(int(spend))
    return f"{spend:.2f}"


def format_scout_book_command(quote: WalkQuote, spend: float) -> str:
    ticker = (quote.ticker or "").strip()
    edge = quote.edge if quote.edge is not None else 0.0
    return (
        "uv run northstar kalshi-live book"
        f" --ticker {ticker}"
        " --side yes"
        f" --spend {_format_scout_spend(spend)}"
        f" --yes-price {quote.yes_price:.2f}"
        f" --no-price {quote.no_price:.2f}"
        f" --edge {edge:+.2f}"
        " --i-approve-live"
    )


def copy_scout_book_command(
    quote: WalkQuote,
    spend: float,
    copy_fn: Callable[[str], bool] | None = None,
) -> bool:
    """Copy the Mini book line to clipboard. Does not send. Helper must not run it."""
    cmd = format_scout_book_command(quote, spend)
    fn = copy_fn if copy_fn is not None else copy_to_clipboard
    return bool(fn(cmd))


SCOUT_BOOK_COPIED = "Book line copied to clipboard. Paste on Mini (Cmd+V). Helper must not run it."
SCOUT_BOOK_COPY_FAILED = "Clipboard copy failed — select the book line above and copy manually."
SCOUT_OFFER_SKIPPED = "Skipped — no live order."
SCOUT_OFFER_TITLE = "NorthStar live book"
MINI_PEM_CANDIDATES = (
    "/Volumes/App/Kalshi-k/kalshi_private.pem",
    str(Path.home() / ".kalshi" / "kalshi_private.pem"),
)


def ensure_mini_pem_env() -> Optional[str]:
    """If KALSHI_PRIVATE_KEY_PATH is unset, point at a known Mini PEM when present."""
    import os

    current = (os.environ.get("KALSHI_PRIVATE_KEY_PATH") or "").strip()
    if current:
        return current if Path(current).expanduser().is_file() else current
    for candidate in MINI_PEM_CANDIDATES:
        if Path(candidate).expanduser().is_file():
            os.environ["KALSHI_PRIVATE_KEY_PATH"] = candidate
            return candidate
    return None


def format_offer_live_message(quote: WalkQuote, spend: float) -> str:
    ticker = (quote.ticker or "").strip()
    edge = quote.edge if quote.edge is not None else 0.0
    return (
        f"{ticker}\n"
        f"BUY YES @ {quote.yes_price:.2f}  NO={quote.no_price:.2f}  "
        f"edge {edge:+.2f}\n"
        f"Spend ${_format_scout_spend(spend)}. Window must still be live.\n"
        "Approve sends one IOC order. Skip continues scouting."
    )


def offer_live_book(
    quote: WalkQuote,
    spend: float,
    *,
    confirm_fn: Callable[..., bool] = confirm_live_book,
    send_fn: Callable[[WalkQuote, float], str] | None = None,
) -> str:
    """Human Approve dialog → optional send. Never silent. Helper must not call this."""
    approved = confirm_fn(
        title=SCOUT_OFFER_TITLE,
        message=format_offer_live_message(quote, spend),
    )
    if not approved:
        return SCOUT_OFFER_SKIPPED
    if send_fn is None:
        return SCOUT_OFFER_SKIPPED
    return send_fn(quote, spend)


def format_scout_alert_message(quote: WalkQuote) -> str:
    ticker = (quote.ticker or "").strip()
    edge = quote.edge if quote.edge is not None else 0.0
    return f"{ticker} YES {quote.yes_price:.2f} edge {edge:+.2f}"


def format_scout_spoken(quote: WalkQuote) -> str:
    cents = int(round(quote.yes_price * 100))
    edge = quote.edge if quote.edge is not None else 0.0
    return (
        f"Scout click {quote.asset} YES {cents} cents, edge plus {edge:.2f}."
    )


def scout_alert_config(
    alert: bool, speak: bool, no_sound: bool
) -> Optional[AlertConfig]:
    if not alert and not speak:
        return None
    return AlertConfig(
        sound=not no_sound,
        notification=True,
        speech=speak,
    )


def alert_scout_click(
    config: Optional[AlertConfig],
    quote: WalkQuote,
    fire_fn: Callable[..., None] = fire,
) -> None:
    if config is None or not config.any_enabled:
        return
    spoken = format_scout_spoken(quote) if config.speech else ""
    fire_fn(
        config,
        "SCOUT CLICK",
        format_scout_alert_message(quote),
        spoken,
    )


@dataclass
class ScoutCounts:
    windows: int = 0
    clicks: int = 0
    skips: int = 0
    rate_limits: int = 0


def _load_with_retry(
    load_fn: Callable[[str], Optional[WalkQuote]],
    asset: str,
    sleep_fn: Callable[[float], None],
) -> tuple[Optional[WalkQuote], str]:
    for attempt in (1, 2):
        try:
            return load_fn(asset), "ok"
        except httpx.HTTPStatusError as exc:
            if not is_kalshi_rate_limit(exc):
                return None, "error"
            if attempt == 1:
                sleep_fn(WALK_RATE_LIMIT_WAIT)
                continue
            return None, "429"
        except Exception:
            return None, "error"
    return None, "error"


def run_scout(
    *,
    hours: int,
    asset: str = "BTC",
    spend: float = DEFAULT_SPEND,
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
    load_fn: Callable[[str], Optional[WalkQuote]],
    on_click: Callable[[WalkQuote], None],
) -> ScoutCounts:
    del spend  # printed by CLI on click only
    counts = ScoutCounts()
    deadline = now_fn() + timedelta(hours=hours)
    last_open: Optional[datetime] = None
    while True:
        now = now_fn()
        if now >= deadline:
            break
        open_ = current_window_open(now)
        if last_open == open_:
            wake = next_open_after(now)
        else:
            wake = next_scout_wake(now)
        if wake > deadline:
            break
        delay = (wake - now).total_seconds()
        if delay > 0:
            sleep_fn(delay)
            now = now_fn()
            if now >= deadline:
                break
            open_ = current_window_open(now)
        quote, kind = _load_with_retry(load_fn, asset, sleep_fn)
        counts.windows += 1
        last_open = open_
        if kind == "429":
            counts.rate_limits += 1
            counts.skips += 1
            continue
        if kind == "error" or quote is None or not is_scout_click(quote, now=now):
            counts.skips += 1
            continue
        counts.clicks += 1
        on_click(quote)
    return counts
