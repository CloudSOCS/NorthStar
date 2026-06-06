"""
Kalshi-only dry-run: live 15m crypto prices + strategy signals.

Use this on Kalshi (US-legal). Place trades manually in the Kalshi app when you
see a green ▶ line — no API key required for signals.
"""

from __future__ import annotations

import time
from typing import List, Optional

from rich.console import Console

from poly.alerts import AlertConfig, alert_for_signal, open_url
from poly.config import Settings
from poly.data.kalshi_live import KalshiLiveFeed
from poly.execution.dry import DrySignal, evaluate_hedged_dry, evaluate_markov_dry

console = Console()


def _assets(settings: Settings, assets: Optional[List[str]]) -> List[str]:
    if assets:
        return [a.upper() for a in assets]
    return [a.strip().upper() for a in settings.dry_assets.split(",") if a.strip()]


def run_kalshi_dry_snapshot(
    settings: Optional[Settings] = None,
    strategies: Optional[List[str]] = None,
    assets: Optional[List[str]] = None,
) -> List[DrySignal]:
    settings = settings or Settings()
    asset_list = _assets(settings, assets)
    strat_list = strategies or ["markov", "hedged"]
    signals: List[DrySignal] = []

    with KalshiLiveFeed() as feed:
        markets = feed.refresh_and_poll(asset_list)
        if not markets:
            console.print("[yellow]No active Kalshi 15m markets found.[/yellow]")
            return []

        for _ in range(3):
            time.sleep(min(1.0, settings.dry_poll_seconds))
            markets = feed.refresh_and_poll(asset_list)

        bankroll = settings.starting_bankroll
        for m in markets:
            console.print(
                f"[cyan]{m.asset}[/cyan] YES mid={m.yes_mid:.3f} "
                f"(bid {m.yes_bid:.3f} / ask {m.yes_ask:.3f})  "
                f"[dim]{m.title[:48]}[/dim]"
            )

        for tracker in feed.trackers_for_assets(asset_list):
            if "markov" in strat_list:
                s = evaluate_markov_dry(tracker, settings, bankroll)
                if s:
                    s = DrySignal(
                        strategy=s.strategy,
                        asset=s.asset,
                        question=s.question,
                        message=s.message.replace("YES", "YES (Kalshi)"),
                        would_trade=s.would_trade,
                    )
                    signals.append(s)
            if "hedged" in strat_list:
                s = evaluate_hedged_dry(tracker, settings, bankroll)
                if s:
                    signals.append(s)

    return signals


def run_kalshi_dry_loop(
    settings: Optional[Settings] = None,
    duration_seconds: int = 120,
    strategies: Optional[List[str]] = None,
    assets: Optional[List[str]] = None,
    alert: Optional[AlertConfig] = None,
    open_site: bool = False,
) -> None:
    settings = settings or Settings()
    asset_list = _assets(settings, assets)
    strat_list = strategies or ["markov", "hedged"]
    interval = settings.dry_poll_seconds

    console.print(
        f"[bold]Kalshi dry-run[/bold] — 15m crypto | assets: {', '.join(asset_list)} | "
        f"poll every {interval}s"
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
    if open_site:
        console.print(
            "[dim]Auto-open: browser jumps to the Kalshi market when ▶ fires.[/dim]"
        )
    console.print(
        "[dim]No API key. Place trades yourself in the Kalshi app when ▶ appears.[/dim]\n"
    )

    end = time.time() + duration_seconds
    seen: set[str] = set()

    with KalshiLiveFeed() as feed:
        while time.time() < end:
            markets = feed.refresh_and_poll(asset_list)
            if not markets:
                console.print("[yellow]Waiting for Kalshi 15m markets…[/yellow]")
                time.sleep(interval)
                continue

            bankroll = settings.starting_bankroll
            ts = time.strftime("%H:%M:%S")

            for tracker in feed.trackers_for_assets(asset_list):
                m = tracker.market
                console.print(
                    f"[dim]{ts}[/dim] [cyan]{m.asset}[/cyan] "
                    f"YES={tracker.up_prices[-1]:.3f} "
                    f"NO={tracker.down_prices[-1]:.3f} "
                    f"[dim]({len(tracker.up_prices)} ticks)[/dim]"
                )
                for name, fn in [
                    ("markov", lambda t: evaluate_markov_dry(t, settings, bankroll)),
                    ("hedged", lambda t: evaluate_hedged_dry(t, settings, bankroll)),
                ]:
                    if name not in strat_list:
                        continue
                    sig = fn(tracker)
                    if not sig or not sig.would_trade:
                        continue
                    key = f"{sig.strategy}:{sig.asset}:{sig.message[:40]}"
                    if key in seen:
                        continue
                    seen.add(key)
                    console.print(
                        f"  [green]▶ Kalshi {sig.strategy}: {sig.message}[/]"
                    )
                    if sig.strategy == "markov":
                        hint = f"→ open Kalshi app → {m.asset} 15m → Yes"
                    else:
                        hint = (
                            f"→ open Kalshi app → {m.asset} 15m → "
                            f"buy the leg named above"
                        )
                    console.print(f"    [dim]{hint}[/dim]")
                    if alert:
                        alert_for_signal(
                            alert,
                            asset=sig.asset,
                            strategy=sig.strategy,
                            message=sig.message,
                            platform="Kalshi",
                        )
                    if open_site:
                        url = m.web_url
                        console.print(f"    [dim]opening {url}[/dim]")
                        open_url(url)

            console.print()
            time.sleep(interval)

    console.print("[bold]Kalshi dry-run finished.[/bold]")
