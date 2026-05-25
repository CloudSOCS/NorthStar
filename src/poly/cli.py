from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from poly.config import Settings
from poly.execution.paper import pick_explanation_window, run_paper_backtest
from poly.modes import describe_mode

app = typer.Typer(
    name="poly",
    help="Polymarket quant toolkit — paper → dry → live",
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
    console.print(Panel("\n".join(lines), title="How poly decides one trade", border_style="blue"))


@app.command()
def status() -> None:
    """Show config and which build phase is active."""
    settings = Settings()
    mode = describe_mode(settings)

    table = Table(title="poly status")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Mode", mode.mode.value)
    table.add_row("Markov strategy", "on" if mode.markov_active else "off")
    table.add_row("Cross-market arb", "on" if mode.cross_arb_active else "stub")
    table.add_row("Places real orders", "yes" if mode.places_orders else "no")
    table.add_row("Min edge", str(settings.min_edge))
    table.add_row("Entry band", f"{settings.entry_min_price} – {settings.entry_max_price}")
    table.add_row("Kelly fraction", str(settings.kelly_fraction))
    table.add_row("Bankroll (paper)", f"${settings.starting_bankroll:,.0f}")
    console.print(table)
    console.print(f"\n[dim]{mode.notes}[/dim]")


if __name__ == "__main__":
    app()
