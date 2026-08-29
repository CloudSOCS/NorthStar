"""Read-only four-step walk of a real Kalshi market. Never places an order."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import json
import os
import time

from poly.config import Settings
from poly.data.kalshi_live import KalshiLiveFeed
from poly.strategies.markov_crypto import MarkovCryptoStrategy

DEFAULT_SPEND = 2.0
MAX_SPEND = 5.0
MIN_EDGE_TO_CARE = 0.03
FOOTER = "This is practice only — no live order was placed."
BANNER = "This is a teaching walk of a real market — no order will be placed"
DEMO_BANNER = (
    "This is a demo snapshot, not a live Kalshi market — no order will be placed"
)
REPLAY_BANNER = "This is a notebook replay of a saved lesson — no order will be placed"
REPLAY_FOOTER = "This is a notebook replay — no live order was placed"
JOURNAL_SCHEMA = 1
SAVE_NOTE = "Saved this lesson snapshot — a notebook, not a trade."


@dataclass(frozen=True)
class WalkQuote:
    asset: str
    question: str
    yes_price: float
    no_price: float
    model_prob: Optional[float]
    edge: Optional[float]


# LEARNING.md Steps 2–4: $2 on YES at 40¢, guess 50¢, NO 40¢ cheap pair.
DEMO_YES = 0.40
DEMO_NO = 0.40
DEMO_GUESS = 0.50
DEMO_EDGE = 0.10
DEMO_QUESTION = "Teaching snapshot — not a live market"


def demo_quote() -> WalkQuote:
    """Fixed teaching snapshot. Does not fetch a market."""
    return WalkQuote(
        asset="DEMO",
        question=DEMO_QUESTION,
        yes_price=DEMO_YES,
        no_price=DEMO_NO,
        model_prob=DEMO_GUESS,
        edge=DEMO_EDGE,
    )


def clamp_spend(usd: float) -> Tuple[float, Optional[str]]:
    if usd <= 0:
        return DEFAULT_SPEND, f"Spend must be positive; using ${DEFAULT_SPEND:.0f}."
    if usd > MAX_SPEND:
        return MAX_SPEND, f"Tiny size only; capped at ${MAX_SPEND:.0f}."
    return usd, None


def tickets_bought(usd: float, price: float) -> float:
    if price <= 0:
        return 0.0
    return usd / price


def win_pnl(usd: float, price: float) -> float:
    """Step 2: dollars back minus dollars in if the ticket wins ($1 payout)."""
    return tickets_bought(usd, price) - usd


def lose_pnl(usd: float, price: float) -> float:
    return -usd


def pair_cost(yes_price: float, no_price: float) -> float:
    return yes_price + no_price


def _signed_usd(amount: float) -> str:
    sign = "+" if amount >= 0 else "-"
    return f"{sign}${abs(amount):.2f}"


def paid_price(ask: Optional[float], mid: float) -> float:
    if ask is not None and ask > 0:
        return ask
    return mid


def format_walk(
    quote: WalkQuote,
    spend: float,
    *,
    replay: bool = False,
    saved_at: Optional[str] = None,
    demo: bool = False,
) -> str:
    spend, spend_note = clamp_spend(spend)
    yes = quote.yes_price
    no = quote.no_price
    n_tickets = tickets_bought(spend, yes)
    win = win_pnl(spend, yes)
    lose = lose_pnl(spend, yes)
    cost = pair_cost(yes, no)
    cheap = cost < 1.0

    if replay:
        banner = REPLAY_BANNER
    elif demo:
        banner = DEMO_BANNER
    else:
        banner = BANNER
    footer = REPLAY_FOOTER if replay else FOOTER
    lines = [banner, ""]
    if replay and saved_at:
        lines.append(f"Saved at: {format_journal_time(saved_at)}")
        lines.append("")
    if spend_note:
        lines.append(spend_note)
        lines.append("")

    lines.extend(
        [
            f"{quote.asset} — {quote.question}",
            "",
            "Step 1 — What you're buying",
            "A YES or NO ticket. Winner pays $1. Loser pays $0.",
            f"YES ticket price: {yes:.2f} ({yes * 100:.0f}¢)",
            f"NO ticket price:  {no:.2f} ({no * 100:.0f}¢)",
            "",
            "Step 2 — Profit & Loss (before you click)",
            f"${spend:.2f} on YES at {yes:.2f} → {n_tickets:.2f} tickets.",
            f"If YES wins: get ${n_tickets:.2f} back → profit {_signed_usd(win)}.",
            f"If YES loses: get $0 back → {_signed_usd(lose)}.",
            "Until the question is answered, you have not won or lost.",
            "",
            "Step 3 — Edge (is this a good price?)",
        ]
    )

    if quote.model_prob is None or quote.edge is None:
        lines.append(f"Crowd YES price: {yes:.2f}.")
        lines.append(
            "Guess: not ready — not enough price ticks yet. "
            "The bot will not invent a number. Wait."
        )
    else:
        guess = quote.model_prob
        edge = quote.edge
        lines.append(
            f"Crowd YES price: {yes:.2f}. Bot's guess: {guess:.2f}. "
            f"Edge = {edge:+.2f}."
        )
        if abs(edge) < MIN_EDGE_TO_CARE:
            lines.append("Tiny gap — not a green light. Wait.")
        elif edge > 0:
            lines.append("Positive edge: the YES ticket looks too cheap. You still decide.")
        else:
            lines.append("Negative edge: the YES ticket looks too expensive. Don't click.")
        lines.append("Edge is an opinion, not locked profit.")

    lines.extend(
        [
            "",
            "Step 4 — Hedge check (both sides)",
            f"YES {yes:.2f} + NO {no:.2f} = {cost:.2f} for the pair.",
        ]
    )
    if cheap:
        lines.append("Hedge: CHEAP PAIR")
        lines.append(
            "Cheap pair (under $1): same dollars either way if you bought both. "
            "This is not edge."
        )
    else:
        lines.append("Hedge: SKIP")
        lines.append(
            "Pair costs more than $1: skip it. That is overpaying for both sides, "
            "not a hedge."
        )

    lines.extend(
        [
            "",
            footer,
        ]
    )
    return "\n".join(lines)


def default_journal_path() -> Path:
    override = os.environ.get("NORTHSTAR_WALK_JOURNAL")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".poly" / "walk_journal.json"


def hedge_verdict(yes_price: float, no_price: float) -> str:
    return "CHEAP PAIR" if pair_cost(yes_price, no_price) < 1.0 else "SKIP"


def journal_entry(
    quote: WalkQuote,
    spend: float,
    saved_at: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    spend, _ = clamp_spend(spend)
    cost = round(pair_cost(quote.yes_price, quote.no_price), 4)
    if quote.model_prob is None or quote.edge is None:
        edge: Union[str, float] = "not ready"
    else:
        edge = round(quote.edge, 4)
    entry: Dict[str, Any] = {
        "saved_at": saved_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "asset": quote.asset,
        "question": quote.question,
        "yes_price": round(quote.yes_price, 4),
        "no_price": round(quote.no_price, 4),
        "spend": round(spend, 2),
        "tickets": round(tickets_bought(spend, quote.yes_price), 4),
        "win_pnl": round(win_pnl(spend, quote.yes_price), 4),
        "lose_pnl": round(lose_pnl(spend, quote.yes_price), 4),
        "edge": edge,
        "hedge": hedge_verdict(quote.yes_price, quote.no_price),
        "pair_cost": cost,
    }
    if source:
        entry["source"] = source
    return entry


def quote_from_journal_entry(entry: Dict[str, Any]) -> Tuple[WalkQuote, float]:
    """Rebuild a WalkQuote from a saved snapshot. Does not fetch a market."""
    yes = float(entry.get("yes_price") or 0.0)
    no = float(entry.get("no_price") or 0.0)
    spend = float(entry.get("spend") or DEFAULT_SPEND)
    raw_edge = entry.get("edge")
    if raw_edge == "not ready" or raw_edge is None:
        model_prob: Optional[float] = None
        edge: Optional[float] = None
    else:
        edge = float(raw_edge)
        model_prob = yes + edge
    quote = WalkQuote(
        asset=str(entry.get("asset") or ""),
        question=str(entry.get("question") or ""),
        yes_price=yes,
        no_price=no,
        model_prob=model_prob,
        edge=edge,
    )
    return quote, spend


def _read_journal(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"schema_version": JOURNAL_SCHEMA, "entries": []}
    blob = json.loads(path.read_text())
    if blob.get("schema_version") != JOURNAL_SCHEMA:
        raise ValueError(f"Unsupported walk journal schema_version: {blob.get('schema_version')}")
    entries = blob.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Walk journal is missing an entries list")
    return {"schema_version": JOURNAL_SCHEMA, "entries": entries}


def load_journal(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only load. Missing file → empty entries. Never writes."""
    return _read_journal(path or default_journal_path())


def clamp_last(n: int) -> int:
    return 1 if n < 1 else n


def format_journal_time(saved_at: str) -> str:
    raw = str(saved_at).replace("T", " ")
    return raw[:16] if len(raw) >= 16 else raw


def format_journal_edge(edge: Any) -> str:
    if edge == "not ready" or edge is None:
        return "not ready"
    try:
        return f"{float(edge):+.2f}"
    except (TypeError, ValueError):
        return "not ready"


def recent_journal_entries(entries: List[Dict[str, Any]], last: int) -> List[Dict[str, Any]]:
    """Newest first, at most `last` snapshots."""
    n = clamp_last(last)
    return list(reversed(entries[-n:]))


def dump_journal_json(entries: List[Dict[str, Any]], last: int) -> Dict[str, Any]:
    """Machine-readable view of saved lessons. Newest first. Does not write."""
    return {
        "schema_version": JOURNAL_SCHEMA,
        "entries": recent_journal_entries(entries or [], last),
    }


def append_journal_entry(
    entry: Dict[str, Any],
    path: Optional[Path] = None,
) -> Path:
    """Append one lesson snapshot. Never writes the Hypothesis Graph."""
    path = path or default_journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = _read_journal(path)
    blob["entries"].append(entry)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=2) + "\n")
    tmp.replace(path)
    return path


def load_walk_quote(
    asset: str,
    settings: Optional[Settings] = None,
) -> Optional[WalkQuote]:
    """Read-only Kalshi snapshot. Never submits an order."""
    settings = settings or Settings()
    asset_u = asset.strip().upper()
    with KalshiLiveFeed() as feed:
        markets = feed.refresh_and_poll([asset_u])
        if not markets:
            return None
        for _ in range(3):
            time.sleep(min(1.0, settings.dry_poll_seconds))
            markets = feed.refresh_and_poll([asset_u])
        if not markets:
            return None
        market = markets[0]
        yes_price = paid_price(market.yes_ask, market.yes_mid)
        no_price = paid_price(market.no_ask, market.no_mid)
        model_prob: Optional[float] = None
        edge: Optional[float] = None
        trackers = feed.trackers_for_assets([asset_u])
        if trackers and len(trackers[0].up_prices) >= 4:
            signal = MarkovCryptoStrategy(settings).evaluate_window(
                trackers[0].to_window_series(),
                bankroll=settings.starting_bankroll,
                scan_all_ticks=True,
                monte_carlo_paths=80,
            )
            model_prob = signal.model_prob
            edge = model_prob - yes_price
        return WalkQuote(
            asset=market.asset,
            question=market.question,
            yes_price=yes_price,
            no_price=no_price,
            model_prob=model_prob,
            edge=edge,
        )
