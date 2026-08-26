"""Read-only four-step walk of a real Kalshi market. Never places an order."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import time

from poly.config import Settings
from poly.data.kalshi_live import KalshiLiveFeed
from poly.strategies.markov_crypto import MarkovCryptoStrategy

DEFAULT_SPEND = 2.0
MAX_SPEND = 5.0
MIN_EDGE_TO_CARE = 0.03
FOOTER = "This is practice only — no live order was placed."


@dataclass(frozen=True)
class WalkQuote:
    asset: str
    question: str
    yes_price: float
    no_price: float
    model_prob: Optional[float]
    edge: Optional[float]


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


def format_walk(quote: WalkQuote, spend: float) -> str:
    spend, spend_note = clamp_spend(spend)
    yes = quote.yes_price
    no = quote.no_price
    n_tickets = tickets_bought(spend, yes)
    win = win_pnl(spend, yes)
    lose = lose_pnl(spend, yes)
    cost = pair_cost(yes, no)
    cheap = cost < 1.0

    lines = []
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
        lines.append(
            "The bot needs a few more price ticks before it will guess. Wait."
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
        lines.append(
            "Cheap pair (under $1): same dollars either way if you bought both. "
            "This is not edge."
        )
    else:
        lines.append(
            "Pair costs more than $1: skip it. That is overpaying for both sides, "
            "not a hedge."
        )

    lines.extend(
        [
            "",
            FOOTER,
        ]
    )
    return "\n".join(lines)


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
