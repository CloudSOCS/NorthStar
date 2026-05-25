"""
Live practice session: real Polymarket prices, virtual money.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from rich.console import Console
from rich.live import Live
from rich.table import Table

from poly.clients.clob import ClobClient
from poly.clients.gamma import GammaClient, UpDownMarket, _parse_json_list
from poly.config import Settings
from poly.data.live import LiveFeed
from poly.execution.dry import evaluate_hedged_dry, evaluate_markov_dry
from poly.practice.account import (
    PracticeAccount,
    Position,
    default_state_path,
    load_account,
    save_account,
)

console = Console()


@dataclass
class SessionConfig:
    duration_seconds: int = 300
    poll_seconds: float = 5.0
    auto_trade: bool = True
    strategies: tuple = ("markov", "hedged")
    assets: tuple = ("BTC", "ETH", "SOL", "BNB", "XRP")
    hedged_buy_below: float = 0.45


def _settle_closed_markets(
    account: PracticeAccount,
    gamma: GammaClient,
    log_lines: List[str],
) -> int:
    """For each open position, ask Gamma if the market closed; settle if yes."""
    settled = 0
    open_slugs: Set[str] = {p.market_slug for p in account.open_positions()}
    for slug in open_slugs:
        market = gamma.get_market_by_slug(slug)
        if not market or not market.get("closed"):
            continue

        outcomes = _parse_json_list(market.get("outcomes"))
        prices = _parse_json_list(market.get("outcomePrices"))
        up_idx = 0
        down_idx = 1
        for i, name in enumerate(outcomes):
            if str(name).lower() == "up":
                up_idx = i
            elif str(name).lower() == "down":
                down_idx = i
        try:
            up_final = float(prices[up_idx])
            down_final = float(prices[down_idx])
        except (IndexError, ValueError, TypeError):
            continue

        up_won = up_final >= down_final
        for pos in list(account.open_for_market(slug)):
            won = (pos.side == "UP" and up_won) or (pos.side == "DOWN" and not up_won)
            ev = account.settle(pos, won, note="resolved by Gamma")
            settled += 1
            icon = "✓" if won else "✗"
            log_lines.append(
                f"{icon} settled {pos.asset} {pos.side} {pos.shares:.2f}sh @ "
                f"{pos.entry_price:.3f} → PnL ${ev.realized_pnl:+.2f}"
            )
    return settled


def _maybe_auto_trade(
    account: PracticeAccount,
    settings: Settings,
    feed: LiveFeed,
    cfg: SessionConfig,
    log_lines: List[str],
) -> None:
    """If a strategy signal fires and we have no open position, place a practice buy."""
    if not cfg.auto_trade:
        return

    bankroll = account.bankroll
    if bankroll <= 0:
        return

    for tracker in feed.trackers_for_assets(list(cfg.assets)):
        slug = tracker.market.slug

        if "markov" in cfg.strategies:
            existing = account.open_for_market(slug)
            if not existing:
                sig = evaluate_markov_dry(tracker, settings, bankroll)
                if sig and sig.would_trade:
                    up = tracker.up_prices[-1]
                    bet = min(bankroll, max(1.0, settings.starting_bankroll * 0.02))
                    bet = min(bet, bankroll)
                    if up > 0 and bet > 0:
                        pos = account.buy(
                            market_slug=slug,
                            asset=tracker.market.asset,
                            side="UP",
                            usd=bet,
                            price=up,
                            strategy="markov",
                        )
                        log_lines.append(
                            f"▶ BOUGHT UP {pos.asset} ${bet:.2f} @ {up:.3f} (markov)"
                        )
                        continue

        if "hedged" in cfg.strategies:
            yes_open = account.open_for_market(slug, side="UP")
            no_open = account.open_for_market(slug, side="DOWN")
            up = tracker.up_prices[-1]
            down = tracker.down_prices[-1]
            asset = tracker.market.asset
            leg_usd = min(bankroll, max(1.0, settings.starting_bankroll * 0.02))

            if not yes_open and up <= cfg.hedged_buy_below and leg_usd > 0:
                pos = account.buy(slug, asset, "UP", leg_usd, up, strategy="hedged")
                log_lines.append(
                    f"▶ BOUGHT UP {asset} ${leg_usd:.2f} @ {up:.3f} (hedged leg 1)"
                )
            elif (
                yes_open
                and not no_open
                and down <= cfg.hedged_buy_below
                and leg_usd > 0
            ):
                pos = account.buy(slug, asset, "DOWN", leg_usd, down, strategy="hedged")
                log_lines.append(
                    f"▶ BOUGHT DOWN {asset} ${leg_usd:.2f} @ {down:.3f} (hedged leg 2)"
                )


def _render_dashboard(
    account: PracticeAccount,
    markets: List[UpDownMarket],
    prices: Dict[str, tuple[float, float]],
    cfg: SessionConfig,
    log_lines: List[str],
) -> Table:
    container = Table.grid(expand=True)
    container.add_column()

    mids_by_slug: Dict[str, Dict[str, float]] = {}
    for m in markets:
        up, down = prices.get(m.asset, (m.gamma_up_price, m.gamma_down_price))
        mids_by_slug[m.slug] = {"UP": up, "DOWN": down}

    mtm = account.mark_to_market(mids_by_slug)
    risk = account.total_capital_at_risk()
    unrealized = mtm - risk
    realized = account.total_realized_pnl()
    equity = account.bankroll + mtm
    pnl_color = "green" if (realized + unrealized) >= 0 else "red"
    summary = Table(title="Practice account", expand=True, show_header=False)
    summary.add_column("k", style="cyan")
    summary.add_column("v", justify="right")
    summary.add_row("Cash", f"${account.bankroll:,.2f}")
    summary.add_row("Open positions @ mid", f"${mtm:,.2f}")
    summary.add_row("Equity (cash + open)", f"${equity:,.2f}")
    summary.add_row(
        "Realized / Unrealized PnL",
        f"[{pnl_color}]${realized:+,.2f}  /  ${unrealized:+,.2f}[/]",
    )
    container.add_row(summary)

    markets_table = Table(title="Live 5m Up/Down (Polymarket CLOB)", expand=True)
    markets_table.add_column("Asset", style="cyan")
    markets_table.add_column("UP", justify="right")
    markets_table.add_column("DOWN", justify="right")
    markets_table.add_column("Question", style="dim", no_wrap=True)
    for m in markets:
        up, down = prices.get(m.asset, (m.gamma_up_price, m.gamma_down_price))
        markets_table.add_row(
            m.asset, f"{up:.3f}", f"{down:.3f}", m.question[:48]
        )
    container.add_row(markets_table)

    open_positions = account.open_positions()
    pos_table = Table(title=f"Open positions ({len(open_positions)})", expand=True)
    pos_table.add_column("ID")
    pos_table.add_column("Asset")
    pos_table.add_column("Side")
    pos_table.add_column("Shares", justify="right")
    pos_table.add_column("Entry", justify="right")
    pos_table.add_column("Mid", justify="right")
    pos_table.add_column("MtM PnL", justify="right")
    pos_table.add_column("Strategy", style="dim")

    for p in open_positions:
        mid = mids_by_slug.get(p.market_slug, {}).get(p.side, p.entry_price)
        value = p.shares * mid
        pnl = value - p.capital_used
        pnl_style = "green" if pnl >= 0 else "red"
        pos_table.add_row(
            p.id,
            p.asset,
            p.side,
            f"{p.shares:.2f}",
            f"{p.entry_price:.3f}",
            f"{mid:.3f}",
            f"[{pnl_style}]{pnl:+.2f}[/]",
            p.strategy,
        )
    container.add_row(pos_table)

    log_table = Table(title="Recent activity", expand=True)
    log_table.add_column("Event")
    for line in log_lines[-8:]:
        log_table.add_row(line)
    container.add_row(log_table)

    return container


def run_practice_session(
    duration_seconds: int = 300,
    settings: Optional[Settings] = None,
    auto_trade: bool = True,
    strategies: Optional[List[str]] = None,
    assets: Optional[List[str]] = None,
    hedged_buy_below: float = 0.45,
    poll_seconds: Optional[float] = None,
) -> PracticeAccount:
    settings = settings or Settings()
    cfg = SessionConfig(
        duration_seconds=duration_seconds,
        poll_seconds=poll_seconds or settings.dry_poll_seconds,
        auto_trade=auto_trade,
        strategies=tuple(strategies or ["markov", "hedged"]),
        assets=tuple(a.upper() for a in (assets or settings.dry_assets.split(","))),
        hedged_buy_below=hedged_buy_below,
    )

    account = load_account()
    log_lines: List[str] = [
        f"Loaded account: cash ${account.bankroll:,.2f}, "
        f"{len(account.open_positions())} open positions"
    ]

    end = time.time() + duration_seconds

    with GammaClient() as gamma, ClobClient() as clob:
        feed = LiveFeed(gamma=gamma, clob=clob)
        markets: List[UpDownMarket] = []
        prices: Dict[str, tuple[float, float]] = {}

        try:
            with Live(
                _render_dashboard(account, markets, prices, cfg, log_lines),
                console=console,
                refresh_per_second=2,
                screen=False,
            ) as live:
                last_settle_check = 0.0
                while time.time() < end:
                    markets = feed.refresh_markets(list(cfg.assets))
                    if markets:
                        prices = feed.poll_prices(markets)
                        _maybe_auto_trade(account, settings, feed, cfg, log_lines)

                    now = time.time()
                    if now - last_settle_check > max(15.0, cfg.poll_seconds * 2):
                        n = _settle_closed_markets(account, gamma, log_lines)
                        if n:
                            log_lines.append(f"Settled {n} position(s)")
                        last_settle_check = now

                    save_account(account)
                    live.update(_render_dashboard(account, markets, prices, cfg, log_lines))
                    time.sleep(cfg.poll_seconds)
        finally:
            save_account(account)

    return account
