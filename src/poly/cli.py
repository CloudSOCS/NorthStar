from __future__ import annotations

import json

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from poly.config import Settings
from poly.alerts import AlertConfig
from poly.clients.clob import ClobClient
from poly.clients.gamma import GammaClient
from poly.clients.kalshi import KalshiClient
from poly.config import ExecutionMode
from poly.execution.dry import run_dry_loop, run_dry_snapshot
from poly.execution.kalshi_dry import run_kalshi_dry_loop, run_kalshi_dry_snapshot
from poly.strategies.cross_arb import find_all_arbs, find_arb_for_asset
from poly.execution.paper import (
    pick_explanation_window,
    run_hedged_paper_backtest,
    run_paper_backtest,
)
from poly.practice.account import (
    ACCOUNT_BANNER,
    ACCOUNT_WALK_HINT,
    default_state_path,
    load_account,
    save_account,
)
from poly.practice.runner import run_practice_session
from poly.practice.orientation import (
    CONTINUE,
    STATUS_FOOTER,
    format_last_walk_kind,
    format_last_walk_line,
    product_status_payload,
)
from poly.practice.walk import (
    SAVE_NOTE,
    append_journal_entry,
    default_journal_path,
    format_journal_edge,
    format_journal_time,
    format_walk,
    journal_entry,
    dump_journal_json,
    demo_quote,
    is_kalshi_rate_limit,
    last_walk_kind,
    load_journal,
    load_walk_quote,
    quote_from_journal_entry,
    recent_journal_entries,
)

app = typer.Typer(
    name="northstar",
    help="NorthStar — Polymarket/Kalshi quant toolkit — paper → dry → live",
    no_args_is_help=True,
)
console = Console()


@app.command()
def paper(
    windows: int = typer.Option(200, help="Number of synthetic 5m windows to simulate"),
    seed: int = typer.Option(42, help="Random seed for reproducible runs"),
    relaxed: bool = typer.Option(
        False,
        "--relaxed",
        help="Widen entry band so more sample trades fire while learning",
    ),
) -> None:
    """Phase 1: backtest Markov + Kelly on sample data (no API, no money)."""
    settings = Settings()
    if relaxed:
        settings = settings.model_copy(
            update={"entry_min_price": 0.70, "entry_max_price": 0.98, "min_edge": 0.02}
        )
    result = run_paper_backtest(n_windows=windows, settings=settings, seed=seed)

    table = Table(title="Paper backtest summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Windows simulated", str(result.n_windows))
    table.add_row("Trades taken", str(result.n_trades))
    table.add_row("Win rate", f"{result.win_rate:.1%}")
    table.add_row("Starting bankroll", f"${result.starting_bankroll:,.2f}")
    table.add_row("Ending bankroll", f"${result.ending_bankroll:,.2f}")
    pnl = result.ending_bankroll - result.starting_bankroll
    table.add_row("Net PnL", f"${pnl:+,.2f}")
    console.print(table)

    if result.trades:
        console.print("\n[dim]Last 5 trades:[/dim]")
        for t in result.trades[-5:]:
            icon = "✓" if t.won else "✗"
            console.print(
                f"  {icon} {t.asset} bet ${t.bet_usd:.2f} @ {t.market_price:.2f} "
                f"edge {t.edge:+.3f} → PnL ${t.pnl:+.2f}"
            )


@app.command()
def explain() -> None:
    """Walk through one trade decision in plain English."""
    settings = Settings()
    window, signal = pick_explanation_window()

    lines = [
        f"[bold]Asset[/bold]: {window.asset} (synthetic 5m UP/DOWN window)",
        f"[bold]Open / close[/bold]: {window.open_price:.3f} → {window.close_price:.3f} "
        f"({'UP' if window.resolved_up else 'DOWN'} at resolution)",
        "",
        "[bold]Step 1 — Markov model[/bold]",
        "We bucket prices into 10 bins and estimate transition probabilities "
        "from ticks seen so far in the window.",
        "",
        "[bold]Step 2 — Monte Carlo[/bold]",
        f"From current price {signal.market_price:.3f}, we simulate "
        f"{settings.monte_carlo_paths} paths for remaining ticks.",
        f"Model P(UP) ≈ [cyan]{signal.model_prob:.3f}[/cyan]",
        "",
        "[bold]Step 3 — Edge[/bold]",
        f"Market implies ~{signal.market_price:.3f}. Edge = model − market = "
        f"[cyan]{signal.edge:+.3f}[/cyan]",
        f"Entry band: {settings.entry_min_price}–{settings.entry_max_price}, "
        f"min edge: {settings.min_edge}",
        "",
        "[bold]Step 4 — Kelly sizing[/bold]",
        f"Full Kelly fraction: {signal.kelly_full:.3f} → "
        f"use {settings.kelly_fraction:.0%} → bet "
        f"[cyan]${signal.bet_usd:.2f}[/cyan] (if signal fires)",
        "",
        f"[bold]Decision[/bold]: {signal.decision.reason}",
    ]
    console.print(Panel("\n".join(lines), title="How NorthStar decides one trade", border_style="blue"))


@app.command()
def hedged(
    windows: int = typer.Option(200, help="Number of synthetic 5m windows"),
    seed: int = typer.Option(42, help="Random seed"),
    buy_below: float = typer.Option(
        0.45, help="Buy each leg only when its price is at or below this"
    ),
    leg_fraction: float = typer.Option(
        0.05, help="Fraction of bankroll to risk per leg"
    ),
) -> None:
    """Phase 1.5: Gabagool-style hedged YES+NO paper backtest."""
    settings = Settings()
    result = run_hedged_paper_backtest(
        n_windows=windows,
        settings=settings,
        seed=seed,
        buy_yes_below=buy_below,
        buy_no_below=buy_below,
        leg_fraction=leg_fraction,
    )

    table = Table(title="Hedged (YES+NO) backtest summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Windows simulated", str(result.n_windows))
    table.add_row("Hedges opened", str(result.n_trades))
    table.add_row(
        "Hedges with cost > $1 (lossy)", str(result.n_filled_unprofitable)
    )
    table.add_row(
        "Avg locked profit / share", f"{result.avg_locked_profit_per_share:+.4f}"
    )
    table.add_row("Starting bankroll", f"${result.starting_bankroll:,.2f}")
    table.add_row("Ending bankroll", f"${result.ending_bankroll:,.2f}")
    pnl = result.ending_bankroll - result.starting_bankroll
    table.add_row("Net PnL", f"${pnl:+,.2f}")
    console.print(table)

    if result.trades:
        console.print("\n[dim]Last 5 hedges:[/dim]")
        for t in result.trades[-5:]:
            direction = "UP" if t.resolved_up else "DOWN"
            console.print(
                f"  {direction:<4} {t.asset} YES@{t.yes_price:.2f} + NO@{t.no_price:.2f} "
                f"cost={t.cost_per_share:.3f}/share PnL ${t.pnl:+.2f}"
            )
    console.print(
        "\n[dim]Note: direction (UP/DOWN) is shown only for transparency — "
        "a hedge pays $1 on the winning side regardless.[/dim]"
    )


@app.command()
def markets(
    assets: str = typer.Option(
        "BTC,ETH,SOL,BNB,XRP",
        help="Comma-separated assets to show",
    ),
) -> None:
    """List active 5m Up/Down markets from Polymarket (Gamma API)."""
    asset_list = [a.strip().upper() for a in assets.split(",") if a.strip()]
    with GammaClient() as gamma:
        found = gamma.list_updown_5m(assets=asset_list)

    if not found:
        console.print("[yellow]No active 5m Up/Down markets for those assets.[/yellow]")
        raise typer.Exit(1)

    table = Table(title="Active 5m Up/Down markets (Gamma)")
    table.add_column("Asset", style="cyan")
    table.add_column("UP", justify="right")
    table.add_column("DOWN", justify="right")
    table.add_column("Question", style="dim")
    for m in found:
        table.add_row(
            m.asset,
            f"{m.gamma_up_price:.3f}",
            f"{m.gamma_down_price:.3f}",
            m.question[:55] + ("…" if len(m.question) > 55 else ""),
        )
    console.print(table)


@app.command()
def dry(
    duration: int = typer.Option(
        60, help="How long to poll (seconds). Use 0 for one snapshot."
    ),
    strategy: str = typer.Option(
        "both",
        help="markov | hedged | both",
    ),
    assets: str = typer.Option(
        "", help="Override DRY_ASSETS from .env (e.g. BTC,ETH)"
    ),
    alert: bool = typer.Option(
        False, "--alert", help="Sound + desktop notification when a ▶ signal fires"
    ),
    speak: bool = typer.Option(
        False, "--speak", help="Also speak the signal out loud (implies --alert)"
    ),
    no_sound: bool = typer.Option(
        False, "--no-sound", help="With --alert, show notification only (mute chime)"
    ),
) -> None:
    """Phase 2: real Polymarket prices, dry-run signals only (no orders)."""
    settings = Settings(poly_mode=ExecutionMode.DRY)
    if assets:
        settings = settings.model_copy(update={"dry_assets": assets})

    strat_map = {
        "markov": ["markov"],
        "hedged": ["hedged"],
        "both": ["markov", "hedged"],
    }
    strat_list = strat_map.get(strategy.lower())
    if not strat_list:
        console.print(f"[red]Unknown strategy: {strategy}[/red]")
        raise typer.Exit(1)

    alert_cfg = None
    if alert or speak:
        alert_cfg = AlertConfig(
            sound=not no_sound,
            notification=True,
            speech=speak,
        )

    if duration <= 0:
        signals = run_dry_snapshot(settings=settings, strategies=strat_list)
        if not signals:
            console.print(
                "[yellow]No signals yet — need a few price ticks for Markov, "
                "or prices outside entry bands. Try: northstar dry --duration 30[/yellow]"
            )
        for sig in signals:
            style = "green" if sig.would_trade else "dim"
            console.print(f"[{style}]{sig.asset} [{sig.strategy}] {sig.message}[/]")
        return

    run_dry_loop(
        settings=settings,
        duration_seconds=duration,
        strategies=strat_list,
        alert=alert_cfg,
    )


@app.command()
def kalshi(
    assets: str = typer.Option(
        "BTC,ETH,SOL,BNB,XRP",
        help="Comma-separated assets to show",
    ),
) -> None:
    """List active 15m Kalshi crypto Up/Down markets (KX<ASSET>15M series)."""
    asset_list = [a.strip().upper() for a in assets.split(",") if a.strip()]
    with KalshiClient() as kc:
        found = kc.list_crypto_15m(assets=asset_list)

    if not found:
        console.print("[yellow]No active 15m Kalshi crypto markets found.[/yellow]")
        raise typer.Exit(1)

    table = Table(title="Active Kalshi 15m crypto markets")
    table.add_column("Asset", style="cyan")
    table.add_column("YES bid", justify="right")
    table.add_column("YES ask", justify="right")
    table.add_column("Last", justify="right")
    table.add_column("Close", style="dim")
    table.add_column("Title", style="dim")
    for m in found:
        table.add_row(
            m.asset,
            f"{m.yes_bid:.3f}" if m.yes_bid else "-",
            f"{m.yes_ask:.3f}" if m.yes_ask else "-",
            f"{m.last_price:.3f}" if m.last_price else "-",
            m.close_time[11:16] if m.close_time else "-",
            m.yes_sub_title[:40],
        )
    console.print(table)


@app.command(name="cross-arb")
def cross_arb(
    assets: str = typer.Option(
        "BTC,ETH,SOL,BNB,XRP", help="Comma-separated assets to scan"
    ),
    min_edge_bps: float = typer.Option(
        0.0,
        help="Only show opportunities with at least this much edge (basis points)",
    ),
    fee_bps: float = typer.Option(
        0.0, help="Worst-case fee cushion in basis points"
    ),
) -> None:
    """Compare Polymarket 5m vs Kalshi 15m prices side-by-side and flag arb candidates."""
    asset_list = [a.strip().upper() for a in assets.split(",") if a.strip()]

    with GammaClient() as gamma, KalshiClient() as kc:
        poly_markets = gamma.list_updown_5m(assets=asset_list)
        try:
            kalshi_markets = kc.list_crypto_15m(assets=asset_list)
        except Exception as e:
            console.print(f"[red]Kalshi fetch failed: {e}[/red]")
            console.print(
                "[dim]Tip: run only `northstar cross-arb` (not `northstar kalshi` right before). "
                "If you hit 429, wait 10 seconds and retry.[/dim]"
            )
            raise typer.Exit(1)

    if not poly_markets:
        console.print("[yellow]No Polymarket 5m markets found.[/yellow]")
        raise typer.Exit(1)
    if not kalshi_markets:
        console.print("[yellow]No Kalshi 15m markets found.[/yellow]")
        raise typer.Exit(1)

    arbs = []
    by_kalshi = {m.asset: m for m in kalshi_markets}
    for pm in poly_markets:
        km = by_kalshi.get(pm.asset)
        if km is None:
            continue
        arbs.append(find_arb_for_asset(pm, km, fee_bps=fee_bps))

    table = Table(title="Polymarket 5m  vs  Kalshi 15m  (price-vs-price)")
    table.add_column("Asset", style="cyan")
    table.add_column("Poly UP", justify="right")
    table.add_column("Poly DOWN", justify="right")
    table.add_column("Kal YES ask", justify="right")
    table.add_column("Kal NO ask", justify="right")
    table.add_column("Best cost", justify="right")
    table.add_column("Edge (bps)", justify="right")
    table.add_column("Direction", style="dim")

    for a in arbs:
        edge_style = "green" if a.edge_bps >= max(1.0, min_edge_bps) else "red"
        table.add_row(
            a.asset,
            f"{a.polymarket_up_price:.3f}",
            f"{a.polymarket_down_price:.3f}",
            f"{a.kalshi_yes_ask:.3f}",
            f"{a.kalshi_no_ask:.3f}",
            f"{a.best_cost:.3f}",
            f"[{edge_style}]{a.edge_bps:+.0f}[/]",
            a.best_direction,
        )
    console.print(table)

    flagged = [a for a in arbs if a.edge_bps >= max(1.0, min_edge_bps)]
    if flagged:
        console.print(
            f"\n[bold green]{len(flagged)} candidate(s) above {min_edge_bps:.0f} bps edge.[/bold green]"
        )
        for a in flagged:
            console.print(f"  ▶ {a.asset} {a.best_direction} — {a.edge_bps:+.0f} bps")
    else:
        console.print(
            f"\n[dim]No edges above {min_edge_bps:.0f} bps right now.[/dim]"
        )

    console.print(
        "\n[yellow]Note:[/yellow] Polymarket 5m and Kalshi 15m resolve on different "
        "windows, so this is a sentiment-divergence signal — not risk-free arb. "
        "Pair-tracking same-window markets comes later."
    )


@app.command(name="kalshi-dry")
def kalshi_dry_cmd(
    duration: int = typer.Option(
        0, help="Seconds to poll (0 = one snapshot)"
    ),
    strategy: str = typer.Option("both", help="markov | hedged | both"),
    assets: str = typer.Option("BTC,ETH,SOL,BNB,XRP", help="Comma-separated assets"),
    alert: bool = typer.Option(
        False, "--alert", help="Sound + desktop notification when a ▶ signal fires"
    ),
    speak: bool = typer.Option(
        False, "--speak", help="Also speak the signal out loud (implies --alert)"
    ),
    no_sound: bool = typer.Option(
        False, "--no-sound", help="With --alert, show notification only (mute chime)"
    ),
    open_site: bool = typer.Option(
        False, "--open", help="Open the Kalshi market page in your browser when a ▶ fires"
    ),
) -> None:
    """Kalshi-only dry-run signals — trade manually in the Kalshi app (US-legal)."""
    strat_map = {
        "markov": ["markov"],
        "hedged": ["hedged"],
        "both": ["markov", "hedged"],
    }
    strat_list = strat_map.get(strategy.lower())
    if not strat_list:
        console.print(f"[red]Unknown strategy: {strategy}[/red]")
        raise typer.Exit(1)
    asset_list = [a.strip().upper() for a in assets.split(",") if a.strip()]

    alert_cfg = None
    if alert or speak:
        alert_cfg = AlertConfig(
            sound=not no_sound,
            notification=True,
            speech=speak,
        )

    if duration <= 0:
        signals = run_kalshi_dry_snapshot(strategies=strat_list, assets=asset_list)
        if not signals:
            console.print(
                "[dim]No trade signals yet. Run: northstar kalshi-dry --duration 120[/dim]"
            )
        for sig in signals:
            style = "green" if sig.would_trade else "dim"
            console.print(f"[{style}]{sig.asset} [{sig.strategy}] {sig.message}[/]")
        return

    run_kalshi_dry_loop(
        duration_seconds=duration,
        strategies=strat_list,
        assets=asset_list,
        alert=alert_cfg,
        open_site=open_site,
    )


practice_app = typer.Typer(help="Virtual trading and teaching walk (no live orders)")
app.add_typer(practice_app, name="practice")


@practice_app.command("walk")
def practice_walk(
    asset: str = typer.Option("BTC", help="Kalshi 15m asset, e.g. BTC, ETH, SOL"),
    spend: float = typer.Option(
        2.0, help="Dollars in for Step 2 (default $2, max $5)"
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="Append this lesson snapshot to the local walk journal (not a trade)",
    ),
    demo: bool = typer.Option(
        False,
        "--demo",
        help="Use the fixed LEARNING.md snapshot. Does not call Kalshi",
    ),
) -> None:
    """Walk a live Kalshi 15m market through learning Steps 1–4. No order is placed."""
    if demo:
        quote = demo_quote()
    else:
        try:
            quote = load_walk_quote(asset)
        except httpx.HTTPStatusError as exc:
            if not is_kalshi_rate_limit(exc):
                raise
            typer.echo(
                "Kalshi rate-limited. Wait and retry once. "
                "No lesson was saved. No order was placed."
            )
            raise typer.Exit(1)
        if quote is None:
            console.print(
                f"[yellow]No active Kalshi 15m market for {asset.upper()}.[/yellow]"
            )
            raise typer.Exit(1)
    console.print(
        Panel(
            format_walk(quote, spend, demo=demo),
            title="NorthStar practice walk",
            border_style="blue",
        )
    )
    if save:
        path = append_journal_entry(
            journal_entry(quote, spend, source="demo" if demo else None)
        )
        console.print(f"[dim]{SAVE_NOTE}[/dim]")
        console.print(f"[dim]{path}[/dim]")


def _read_practice_journal(*, as_json: bool):
    path = default_journal_path()
    try:
        return path, load_journal(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        msg = f"Could not read journal: {exc}"
        if as_json:
            typer.echo(msg, err=True)
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)


def _emit_journal_json(entries, last: int) -> None:
    print(json.dumps(dump_journal_json(entries, last), indent=2))


@practice_app.command("journal")
def practice_journal(
    last: int = typer.Option(
        5, "--last", help="How many recent lesson snapshots to show"
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Print saved lessons as JSON (stdout only)"
    ),
) -> None:
    """Show saved practice walks. Read-only — not a trade."""
    path, blob = _read_practice_journal(as_json=as_json)
    entries = blob.get("entries") or []
    if as_json:
        _emit_journal_json(entries, last)
        return
    if not entries:
        console.print("[dim]No saved walks yet. Run: northstar practice walk --save[/dim]")
        console.print("[dim]This is a notebook, not a trade.[/dim]")
        return

    rows = recent_journal_entries(entries, last)
    table = Table(title="Practice journal (lessons, not trades)")
    table.add_column("Time")
    table.add_column("Kind")
    table.add_column("Asset", style="cyan")
    table.add_column("YES", justify="right")
    table.add_column("NO", justify="right")
    table.add_column("Spend", justify="right")
    table.add_column("Edge")
    table.add_column("Hedge")
    for e in rows:
        table.add_row(
            format_journal_time(str(e.get("saved_at", ""))),
            last_walk_kind(e) or "",
            str(e.get("asset", "")),
            f"{float(e.get('yes_price', 0)):.2f}",
            f"{float(e.get('no_price', 0)):.2f}",
            f"${float(e.get('spend', 0)):.2f}",
            format_journal_edge(e.get("edge")),
            str(e.get("hedge", "")),
        )
    console.print(table)
    console.print(f"[dim]{path}[/dim]")
    console.print("[dim]This is a notebook, not a trade.[/dim]")


@practice_app.command("last")
def practice_last(
    n: int = typer.Option(
        1, "--n", help="How many recent lessons to reprint (newest first)"
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Print saved lessons as JSON (stdout only)"
    ),
) -> None:
    """Replay saved walks in teaching voice. Read-only — no market fetch."""
    _path, blob = _read_practice_journal(as_json=as_json)
    entries = blob.get("entries") or []
    if as_json:
        _emit_journal_json(entries, n)
        return
    if not entries:
        console.print("[dim]No saved walks yet. Run: northstar practice walk --save[/dim]")
        console.print("[dim]This is a notebook, not a trade.[/dim]")
        return

    for entry in recent_journal_entries(entries, n):
        quote, spend = quote_from_journal_entry(entry)
        console.print(
            Panel(
                format_walk(
                    quote,
                    spend,
                    replay=True,
                    saved_at=str(entry.get("saved_at") or ""),
                    demo=last_walk_kind(entry) == "demo",
                ),
                title="NorthStar practice replay",
                border_style="blue",
            )
        )


def _print_account_honesty() -> None:
    console.print(f"[dim]{ACCOUNT_BANNER}[/dim]")
    console.print(f"[dim]{ACCOUNT_WALK_HINT}[/dim]")


@practice_app.command("pnl")
def practice_pnl() -> None:
    """Bottom-line: are you up or down on the practice account?"""
    account = load_account()
    realized = account.total_realized_pnl()
    risk = account.total_capital_at_risk()
    equity = account.bankroll + risk
    total_vs_start = equity - account.starting_bankroll
    color = "green" if total_vs_start >= 0 else "red"
    _print_account_honesty()
    console.print(
        f"\n[bold]Practice P&L[/bold]\n"
        f"  Starting bankroll:  ${account.starting_bankroll:,.2f}\n"
        f"  Cash now:           ${account.bankroll:,.2f}\n"
        f"  Capital at risk:    ${risk:,.2f}\n"
        f"  Realized P&L:       ${realized:+,.2f}\n"
        f"  [bold {color}]Total vs start:     ${total_vs_start:+,.2f}[/bold {color}]\n"
        f"  [dim](Open positions valued at cost until closed — "
        f"use `practice status` for per-position detail.)[/dim]\n"
    )


@practice_app.command("status")
def practice_status() -> None:
    """Show the current practice account: cash, open positions, history."""
    account = load_account()
    _print_account_honesty()

    table = Table(title="Practice account")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Cash", f"${account.bankroll:,.2f}")
    table.add_row("Starting bankroll", f"${account.starting_bankroll:,.2f}")
    table.add_row("Open positions", str(len(account.open_positions())))
    table.add_row("Realized P&L", f"${account.total_realized_pnl():+,.2f}")
    table.add_row("Capital at risk", f"${account.total_capital_at_risk():,.2f}")
    table.add_row("State file", str(default_state_path()))
    console.print(table)

    open_pos = account.open_positions()
    if open_pos:
        pos_table = Table(title="Open positions")
        pos_table.add_column("ID")
        pos_table.add_column("Asset")
        pos_table.add_column("Side")
        pos_table.add_column("Tickets", justify="right")
        pos_table.add_column("Entry", justify="right")
        pos_table.add_column("Cost", justify="right")
        pos_table.add_column("Strategy", style="dim")
        for p in open_pos:
            pos_table.add_row(
                p.id,
                p.asset,
                p.side,
                f"{p.shares:.2f}",
                f"{p.entry_price:.3f}",
                f"${p.capital_used:.2f}",
                p.strategy,
            )
        console.print(pos_table)

    if account.history:
        hist_table = Table(title=f"Last {min(8, len(account.history))} settlements")
        hist_table.add_column("Asset")
        hist_table.add_column("Side")
        hist_table.add_column("Entry", justify="right")
        hist_table.add_column("Close", justify="right")
        hist_table.add_column("P&L", justify="right")
        hist_table.add_column("Note", style="dim")
        for ev in account.history[-8:]:
            pnl_style = "green" if ev.realized_pnl >= 0 else "red"
            hist_table.add_row(
                ev.asset,
                ev.side,
                f"{ev.entry_price:.3f}",
                f"{ev.closing_price:.3f}",
                f"[{pnl_style}]{ev.realized_pnl:+.2f}[/]",
                ev.note,
            )
        console.print(hist_table)


@practice_app.command("reset")
def practice_reset(
    bankroll: float = typer.Option(1000.0, help="New starting bankroll"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Wipe the practice account and start fresh."""
    path = default_state_path()
    if path.exists() and not yes:
        confirm = typer.confirm(
            f"This will erase {path}. Continue?", default=False
        )
        if not confirm:
            raise typer.Exit(0)
    if path.exists():
        path.unlink()
    account = load_account(starting_bankroll=bankroll)
    save_account(account)
    console.print(f"[green]Practice account reset with ${bankroll:,.2f}[/green]")


@practice_app.command("buy")
def practice_buy(
    asset: str = typer.Argument(..., help="Asset symbol, e.g. BTC"),
    side: str = typer.Argument(..., help="UP or DOWN"),
    usd: float = typer.Argument(..., help="Dollar amount to risk"),
) -> None:
    """Manually buy UP or DOWN on the current 5m market for an asset."""
    asset_u = asset.upper()
    side_u = side.upper()
    if side_u not in ("UP", "DOWN"):
        console.print("[red]side must be UP or DOWN[/red]")
        raise typer.Exit(1)

    account = load_account()
    if usd > account.bankroll:
        console.print(
            f"[red]Insufficient cash: have ${account.bankroll:,.2f}, need ${usd:,.2f}[/red]"
        )
        raise typer.Exit(1)

    with GammaClient() as gamma, ClobClient() as clob:
        markets = gamma.list_updown_5m(assets=[asset_u])
        if not markets:
            console.print(f"[yellow]No active 5m market for {asset_u}[/yellow]")
            raise typer.Exit(1)
        m = markets[0]
        token_id = m.up_token_id if side_u == "UP" else m.down_token_id
        price = clob.get_midpoint(token_id)
        if price is None:
            price = m.gamma_up_price if side_u == "UP" else m.gamma_down_price

    pos = account.buy(
        market_slug=m.slug,
        asset=m.asset,
        side=side_u,  # type: ignore[arg-type]
        usd=usd,
        price=price,
        strategy="manual",
    )
    save_account(account)
    console.print(
        f"[green]Bought {pos.shares:.2f} {pos.asset} {pos.side} tickets @ {pos.entry_price:.3f} "
        f"for ${pos.capital_used:.2f}[/green]"
    )
    console.print(f"  position id: [bold]{pos.id}[/bold]")
    console.print(f"  market: {m.question}")
    console.print(f"  cash remaining: ${account.bankroll:,.2f}")
    _print_account_honesty()


@practice_app.command("close")
def practice_close(
    position_id: str = typer.Argument(..., help="Position ID from `northstar practice status`"),
) -> None:
    """Close an open position at the current mid price (no real fill, just practice)."""
    account = load_account()
    pos = next((p for p in account.positions if p.id == position_id and not p.closed), None)
    if not pos:
        console.print(f"[red]No open position with id {position_id}[/red]")
        raise typer.Exit(1)

    with ClobClient() as clob, GammaClient() as gamma:
        markets = gamma.list_updown_5m(assets=[pos.asset])
        if markets and markets[0].slug == pos.market_slug:
            tok = markets[0].up_token_id if pos.side == "UP" else markets[0].down_token_id
            mid = clob.get_midpoint(tok) or pos.entry_price
        else:
            # market already rolled — try Gamma lookup for final price
            raw = gamma.get_market_by_slug(pos.market_slug)
            mid = pos.entry_price
            if raw and raw.get("closed"):
                from poly.clients.gamma import _parse_json_list

                outcomes = _parse_json_list(raw.get("outcomes"))
                prices = _parse_json_list(raw.get("outcomePrices"))
                for i, name in enumerate(outcomes):
                    if str(name).upper() == pos.side and i < len(prices):
                        mid = float(prices[i])

    ev = account.close_at_price(pos, sell_price=mid, note="user closed")
    save_account(account)
    pnl_style = "green" if ev.realized_pnl >= 0 else "red"
    console.print(
        f"Closed {pos.asset} {pos.side} @ {mid:.3f}: "
        f"[{pnl_style}]${ev.realized_pnl:+,.2f}[/]"
    )
    console.print(f"  cash now: ${account.bankroll:,.2f}")
    _print_account_honesty()


@practice_app.command("run")
def practice_run(
    duration: int = typer.Option(300, help="Session length in seconds"),
    auto: bool = typer.Option(True, "--auto/--manual", help="Auto-trade on signals"),
    strategy: str = typer.Option("both", help="markov | hedged | both"),
    assets: str = typer.Option("BTC,ETH,SOL,BNB,XRP", help="Comma-separated assets"),
    hedged_buy_below: float = typer.Option(
        0.45, help="Hedged auto-trade trigger (each leg must be at/below this)"
    ),
) -> None:
    """Live practice dashboard: real prices, virtual money."""
    settings = Settings(poly_mode=ExecutionMode.DRY)
    strat_map = {
        "markov": ["markov"],
        "hedged": ["hedged"],
        "both": ["markov", "hedged"],
    }
    strat_list = strat_map.get(strategy.lower())
    if not strat_list:
        console.print(f"[red]Unknown strategy: {strategy}[/red]")
        raise typer.Exit(1)

    asset_list = [a.strip().upper() for a in assets.split(",") if a.strip()]
    _print_account_honesty()
    run_practice_session(
        duration_seconds=duration,
        settings=settings,
        auto_trade=auto,
        strategies=strat_list,
        assets=asset_list,
        hedged_buy_below=hedged_buy_below,
    )


@app.command()
def status(
    as_json: bool = typer.Option(
        False, "--json", help="Print the same facts as JSON (stdout only)"
    ),
) -> None:
    """What this project is allowed to do, and the last saved lesson. Read-only."""
    _path, blob = _read_practice_journal(as_json=as_json)
    entries = blob.get("entries") or []
    payload = product_status_payload(entries)
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    table = Table(title="NorthStar status")
    table.add_column("Setting")
    table.add_column("Value")
    fences = payload["fences"]
    table.add_row("Live orders", str(fences["live_orders"]))
    table.add_row("Generator", str(fences["generator"]))
    table.add_row("Graph command", str(fences["graph_command"]))
    table.add_row("Last lesson", format_last_walk_kind(payload["last_walk"]))
    table.add_row("Last saved lesson", format_last_walk_line(payload["last_walk"]))
    table.add_row("Continue", "\n".join(CONTINUE))
    console.print(table)
    console.print(f"[dim]{STATUS_FOOTER}[/dim]")


if __name__ == "__main__":
    app()
