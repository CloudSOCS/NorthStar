from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from rich.console import Console

from poly.config import Settings
from poly.data.live import LiveFeed
from poly.strategies.hedged_binary import HedgedBinaryStrategy
from poly.strategies.markov_crypto import MarkovCryptoStrategy

console = Console()


@dataclass
class DrySignal:
    strategy: str
    asset: str
    question: str
    message: str
    would_trade: bool


def _parse_assets(settings: Settings) -> List[str]:
    return [a.strip().upper() for a in settings.dry_assets.split(",") if a.strip()]


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
) -> Optional[DrySignal]:
    if len(tracker.up_prices) < 2:
        return None
    window = tracker.to_window_series()
    strategy = HedgedBinaryStrategy(settings, buy_yes_below=buy_below, buy_no_below=buy_below)
    signal = strategy.evaluate_window(window, bankroll=bankroll)
    if not signal.filled:
        up = tracker.up_prices[-1]
        down = tracker.down_prices[-1] if tracker.down_prices else 1.0 - up
        msg = (
            f"watching — UP={up:.3f} DOWN={down:.3f} "
            f"(need UP<={buy_below:.2f} then DOWN<={buy_below:.2f})"
        )
        return DrySignal(
            strategy="hedged",
            asset=tracker.market.asset,
            question=tracker.market.question,
            message=msg,
            would_trade=False,
        )
    msg = (
        f"WOULD HEDGE — {signal.reason} | "
        f"${signal.bet_per_leg_usd:.2f}/leg | locked {signal.locked_profit_per_share:+.3f}/share"
    )
    return DrySignal(
        strategy="hedged",
        asset=tracker.market.asset,
        question=tracker.market.question,
        message=msg,
        would_trade=True,
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

            console.print()
            time.sleep(interval)

    console.print("[bold]Dry-run finished.[/bold]")
