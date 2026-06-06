from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from rich.console import Console

from poly.alerts import AlertConfig, alert_for_signal
from poly.config import Settings
from poly.data.live import LiveFeed
from poly.strategies.markov_crypto import MarkovCryptoStrategy

console = Console()


@dataclass
class DrySignal:
    strategy: str
    asset: str
    question: str
    message: str
    would_trade: bool


@dataclass
class _HedgeState:
    """Per-window memory so hedge alerts are real-time, not backward-looking."""

    leg1_side: Optional[str] = None  # "YES" or "NO" — the leg you'd buy first
    leg1_price: float = 0.0
    leg1_tick: int = -1
    completed: bool = False


def _parse_assets(settings: Settings) -> List[str]:
    return [a.strip().upper() for a in settings.dry_assets.split(",") if a.strip()]


def _realized_vol(prices: List[float]) -> float:
    """Choppiness gauge: std-dev of tick-to-tick changes.

    A smooth one-way drift (like a market gliding to its target) has tiny
    tick-to-tick moves -> low value. A jagged, whipsawing market -> high value.
    This is what tells a hedge-able window apart from a calm one.
    """
    if len(prices) < 3:
        return 0.0
    diffs = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    mean = sum(diffs) / len(diffs)
    var = sum((d - mean) ** 2 for d in diffs) / len(diffs)
    return var**0.5


def evaluate_markov_dry(
    tracker,
    settings: Settings,
    bankroll: float,
) -> Optional[DrySignal]:
    if len(tracker.up_prices) < 4:
        return None
    window = tracker.to_window_series()
    strategy = MarkovCryptoStrategy(settings)
    signal = strategy.evaluate_window(
        window,
        bankroll=bankroll,
        scan_all_ticks=True,
        monte_carlo_paths=80,
    )
    msg = (
        f"UP @ {signal.market_price:.3f} | model P(UP)={signal.model_prob:.3f} | "
        f"edge={signal.edge:+.3f} | Kelly bet=${signal.bet_usd:.2f}"
    )
    if signal.decision.should_trade and signal.bet_usd > 0:
        msg = f"WOULD BUY YES — {msg}"
    else:
        msg = f"no trade — {signal.decision.reason}"
    return DrySignal(
        strategy="markov",
        asset=tracker.market.asset,
        question=tracker.market.question,
        message=msg,
        would_trade=signal.decision.should_trade and signal.bet_usd > 0,
    )


def evaluate_hedged_dry(
    tracker,
    settings: Settings,
    bankroll: float,
    buy_below: float = 0.45,
    fee: float = 0.02,
    leg_fraction: float = 0.05,
    dip_from: float = 0.50,
    min_volatility: Optional[float] = None,
) -> Optional[DrySignal]:
    """
    Real-time hedge detector.

    Unlike a backward-looking scan, this only flags a leg you can buy *right now*.
    It walks one window through three actionable states:

      1. GRAB BOTH NOW   — both legs are cheap on the same tick (instant lock).
      2. GRAB LEG 1 NOW  — one leg *dipped* into cheap territory; buy it, then
                           watch the other side.
      3. COMPLETE HEDGE  — you hold leg 1 and the opposite leg is now cheap enough
                           that buying it locks profit regardless of resolution.

    A leg-1 candidate must have *fallen* into cheap territory (its window high was
    >= ``dip_from``), so a structurally cheap longshot — e.g. a side that opened at
    0.20 and stayed there — never trips the alert. State is remembered per window
    (stored on the tracker), so the alert fires on the tick the opportunity is
    live, not after it's gone.

    Leg 1 also requires the window to have been *choppy* enough (realized vol >=
    ``min_volatility``). A gentle one-way drift that glides toward its target can
    never produce a second cheap leg, so we don't bother flagging it.
    """
    if min_volatility is None:
        min_volatility = settings.hedge_min_volatility
    ups = tracker.up_prices
    if not ups:
        return None
    downs = tracker.down_prices
    yes_now = ups[-1]
    no_now = downs[-1] if downs else 1.0 - yes_now
    tick = len(ups) - 1
    asset = tracker.market.asset
    question = tracker.market.question
    bet_per_leg = bankroll * leg_fraction
    breakeven = 1.0 - fee  # total leg cost must stay under this to lock profit

    state = getattr(tracker, "_hedge_state", None)
    if state is None:
        state = _HedgeState()
        setattr(tracker, "_hedge_state", state)

    def watching(msg: str) -> DrySignal:
        return DrySignal("hedged", asset, question, msg, would_trade=False)

    if state.completed:
        return watching(
            f"hedge done this window — sit tight (YES={yes_now:.3f} NO={no_now:.3f})"
        )

    # State 1: both legs cheap on the SAME tick → grab both immediately.
    if state.leg1_side is None and (yes_now + no_now) < breakeven:
        locked = 1.0 - (yes_now + no_now)
        state.completed = True
        msg = (
            f"GRAB BOTH NOW — YES @ {yes_now:.3f} + NO @ {no_now:.3f} "
            f"= {yes_now + no_now:.3f} | locked +{locked:.3f}/share | "
            f"${bet_per_leg:.2f}/leg"
        )
        return DrySignal("hedged", asset, question, msg, would_trade=True)

    # State 2: no leg yet — fire when a side has *dipped* into cheap territory,
    # but only if the market has actually been choppy (gentle drifts can't hedge).
    if state.leg1_side is None:
        vol = _realized_vol(ups)
        enough_history = len(ups) >= max(2, settings.hedge_min_ticks)
        if min_volatility > 0 and vol < min_volatility:
            return watching(
                f"watching — YES={yes_now:.3f} NO={no_now:.3f} "
                f"(too calm: vol {vol:.3f} < {min_volatility:.3f}, no hedge likely)"
            )
        yes_high = max(ups)
        no_high = max(downs) if downs else (1.0 - min(ups))
        yes_dip = enough_history and yes_now < buy_below and yes_high >= dip_from
        no_dip = enough_history and no_now < buy_below and no_high >= dip_from
        if yes_dip or no_dip:
            if yes_dip and (not no_dip or yes_now <= no_now):
                state.leg1_side, state.leg1_price = "YES", yes_now
                leg1_high, wait_side = yes_high, "NO"
            else:
                state.leg1_side, state.leg1_price = "NO", no_now
                leg1_high, wait_side = no_high, "YES"
            state.leg1_tick = tick
            msg = (
                f"GRAB LEG 1 NOW — buy {state.leg1_side} @ {state.leg1_price:.3f} "
                f"(dipped from {leg1_high:.2f}), "
                f"then watch {wait_side} to dip < {buy_below:.2f} | ${bet_per_leg:.2f}/leg"
            )
            return DrySignal("hedged", asset, question, msg, would_trade=True)
        return watching(
            f"watching — YES={yes_now:.3f} NO={no_now:.3f} "
            f"(need a side to dip < {buy_below:.2f} from >= {dip_from:.2f})"
        )

    # State 3: holding leg 1 — can we lock it in right now?
    opp_now = no_now if state.leg1_side == "YES" else yes_now
    opp_side = "NO" if state.leg1_side == "YES" else "YES"
    total = state.leg1_price + opp_now
    if opp_now < buy_below and total < breakeven:
        locked = 1.0 - total
        state.completed = True
        msg = (
            f"COMPLETE HEDGE NOW — buy {opp_side} @ {opp_now:.3f} "
            f"(leg1 {state.leg1_side} @ {state.leg1_price:.3f}); total {total:.3f} | "
            f"locked +{locked:.3f}/share | ${bet_per_leg:.2f}/leg"
        )
        return DrySignal("hedged", asset, question, msg, would_trade=True)

    return watching(
        f"holding leg1 {state.leg1_side} @ {state.leg1_price:.3f} — "
        f"need {opp_side} <= {buy_below:.2f} (now {opp_now:.3f})"
    )


def run_dry_snapshot(
    settings: Optional[Settings] = None,
    strategies: Optional[List[str]] = None,
) -> List[DrySignal]:
    """One poll cycle: discover markets, fetch prices, evaluate strategies."""
    settings = settings or Settings()
    assets = _parse_assets(settings)
    strat_list = strategies or ["markov", "hedged"]
    signals: List[DrySignal] = []

    with LiveFeed() as feed:
        markets = feed.refresh_markets(assets)
        if not markets:
            console.print("[yellow]No active 5m Up/Down markets found.[/yellow]")
            return []

        prices = feed.poll_prices(markets)
        for _ in range(3):
            time.sleep(min(1.0, settings.dry_poll_seconds))
            prices = feed.poll_prices(markets)
        bankroll = settings.starting_bankroll

        for m in markets:
            up, down = prices.get(m.asset, (m.gamma_up_price, m.gamma_down_price))
            console.print(
                f"[cyan]{m.asset}[/cyan] UP={up:.3f} DOWN={down:.3f}  "
                f"[dim]{m.question[:50]}…[/dim]"
            )

        for tracker in feed.trackers_for_assets(assets):
            if "markov" in strat_list:
                s = evaluate_markov_dry(tracker, settings, bankroll)
                if s:
                    signals.append(s)
            if "hedged" in strat_list:
                s = evaluate_hedged_dry(tracker, settings, bankroll)
                if s:
                    signals.append(s)

    return signals


def run_dry_loop(
    settings: Optional[Settings] = None,
    duration_seconds: int = 60,
    strategies: Optional[List[str]] = None,
    alert: Optional[AlertConfig] = None,
) -> None:
    """
    Poll live Polymarket prices and log dry-run signals. Never places orders.
    """
    settings = settings or Settings()
    assets = _parse_assets(settings)
    strat_list = strategies or ["markov", "hedged"]
    interval = settings.dry_poll_seconds

    console.print(
        f"[bold]Dry-run[/bold] — read-only Polymarket feed | assets: {', '.join(assets)} | "
        f"poll every {interval}s | strategies: {', '.join(strat_list)}"
    )
    if alert and alert.any_enabled:
        channels = [
            name
            for name, on in (
                ("sound", alert.sound),
                ("notification", alert.notification),
                ("speech", alert.speech),
            )
            if on
        ]
        console.print(f"[dim]Alerts on: {', '.join(channels)} when ▶ fires.[/dim]")
    console.print("[dim]No wallet. No orders. Signals only.[/dim]\n")

    end = time.time() + duration_seconds
    seen_trade_keys: set[str] = set()

    with LiveFeed() as feed:
        while time.time() < end:
            markets = feed.refresh_markets(assets)
            if not markets:
                console.print("[yellow]Waiting for active 5m markets…[/yellow]")
                time.sleep(interval)
                continue

            feed.poll_prices(markets)
            bankroll = settings.starting_bankroll
            ts = time.strftime("%H:%M:%S")

            for tracker in feed.trackers_for_assets(assets):
                m = tracker.market
                up = tracker.up_prices[-1]
                down = tracker.down_prices[-1]
                console.print(
                    f"[dim]{ts}[/dim] [cyan]{m.asset}[/cyan] "
                    f"UP={up:.3f} DOWN={down:.3f} [dim]({len(tracker.up_prices)} ticks)[/dim]"
                )

                for name, eval_fn in [
                    ("markov", lambda t: evaluate_markov_dry(t, settings, bankroll)),
                    ("hedged", lambda t: evaluate_hedged_dry(t, settings, bankroll)),
                ]:
                    if name not in strat_list:
                        continue
                    sig = eval_fn(tracker)
                    if not sig or not sig.would_trade:
                        continue
                    key = f"{sig.strategy}:{sig.asset}:{sig.message[:48]}"
                    if key in seen_trade_keys:
                        continue
                    seen_trade_keys.add(key)
                    console.print(f"  [green]▶ {sig.strategy}: {sig.message}[/]")
                    if alert:
                        alert_for_signal(
                            alert,
                            asset=sig.asset,
                            strategy=sig.strategy,
                            message=sig.message,
                            platform="Polymarket",
                        )

            console.print()
            time.sleep(interval)

    console.print("[bold]Dry-run finished.[/bold]")
