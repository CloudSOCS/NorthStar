"""
Phase 2 — Dry-run execution.

Will connect to Polymarket CLOB (read-only) and optionally Kalshi,
log TradeSignal / ArbOpportunity rows, never submit orders.
"""

from __future__ import annotations


def run_dry_loop() -> None:
    raise NotImplementedError(
        "Dry-run mode is Phase 2. Set POLY_MODE=paper and run: poly paper"
    )
