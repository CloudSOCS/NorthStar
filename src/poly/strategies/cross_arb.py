"""
Phase 2 — Cross-market statistical arbitrage (Polymarket ↔ Kalshi).

Inspired by @ridark_eth's roadmap:
  1. Ingest + normalize order books from both venues
  2. Match equivalent events (strict resolution / timing checks)
  3. Compute fee-adjusted arb: cost(YES_A) + cost(NO_B) < 1
  4. Size by bottleneck liquidity; execute both legs in parallel

This module is a stub until dry-run mode is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ArbOpportunity:
    polymarket_title: str
    kalshi_title: str
    match_score: float
    gross_edge_bps: float
    net_edge_bps: float
    notes: str


def scan_cross_arb_placeholder() -> Optional[ArbOpportunity]:
    """Returns None until Phase 2 wires real feeds."""
    return None
