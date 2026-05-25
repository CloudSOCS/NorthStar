"""
Cross-market statistical arbitrage (Polymarket ↔ Kalshi).

Inspired by @ridark_eth's roadmap:
  1. Ingest + normalize order books from both venues
  2. Match equivalent events by asset (and roughly by direction)
  3. Compute fee-adjusted arb: cost(YES_A) + cost(NO_B) < 1
  4. (Later) size by bottleneck liquidity; execute both legs in parallel

IMPORTANT — Polymarket's 5m windows and Kalshi's 15m windows are NOT the same
contract. Polymarket asks "Will price be higher 5 min from now?"; Kalshi asks
"...15 min from now?". The numbers below are *price-vs-price* gaps, not true
event-equivalent arbitrage. Treat them as a sentiment-divergence signal first;
only call it real arb when the underlying questions match exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from poly.clients.gamma import UpDownMarket
from poly.clients.kalshi import KalshiMarket


@dataclass(frozen=True)
class ArbOpportunity:
    asset: str
    polymarket_up_price: float
    polymarket_down_price: float
    kalshi_yes_ask: float
    kalshi_no_ask: float
    kalshi_title: str
    polymarket_question: str

    yes_a_no_b_cost: float
    no_a_yes_b_cost: float
    best_cost: float
    best_direction: str
    edge: float
    edge_bps: float

    note: str

    @property
    def has_arb(self) -> bool:
        return self.best_cost < 1.0


def find_arb_for_asset(
    poly_market: UpDownMarket,
    kalshi_market: KalshiMarket,
    fee_bps: float = 0.0,
) -> ArbOpportunity:
    """
    Compute the cheaper of the two direction-paired baskets:

      A) YES on Polymarket (UP)  +  NO on Kalshi
      B) NO on Polymarket (DOWN) +  YES on Kalshi

    `fee_bps` lets you bake in a worst-case fee/slippage cushion.
    """
    fee_factor = fee_bps / 10_000.0
    poly_up = poly_market.gamma_up_price * (1 + fee_factor)
    poly_down = poly_market.gamma_down_price * (1 + fee_factor)
    kalshi_yes_ask = (kalshi_market.yes_ask or kalshi_market.yes_mid) * (1 + fee_factor)
    kalshi_no_ask = (kalshi_market.no_ask or kalshi_market.no_mid) * (1 + fee_factor)
    if kalshi_no_ask <= 0:
        kalshi_no_ask = 1.0 - kalshi_market.yes_mid

    cost_a = poly_up + kalshi_no_ask
    cost_b = poly_down + kalshi_yes_ask
    if cost_a <= cost_b:
        best_cost = cost_a
        direction = "poly-UP + kalshi-NO"
    else:
        best_cost = cost_b
        direction = "poly-DOWN + kalshi-YES"

    edge = 1.0 - best_cost
    edge_bps = edge * 10_000.0

    note = (
        "Both contracts directionally aligned but on DIFFERENT windows "
        "(Polymarket 5m vs Kalshi 15m). Treat as divergence signal, NOT risk-free arb."
    )

    return ArbOpportunity(
        asset=poly_market.asset,
        polymarket_up_price=poly_market.gamma_up_price,
        polymarket_down_price=poly_market.gamma_down_price,
        kalshi_yes_ask=kalshi_market.yes_ask or kalshi_market.yes_mid,
        kalshi_no_ask=kalshi_market.no_ask or kalshi_market.no_mid,
        kalshi_title=kalshi_market.title,
        polymarket_question=poly_market.question,
        yes_a_no_b_cost=cost_a,
        no_a_yes_b_cost=cost_b,
        best_cost=best_cost,
        best_direction=direction,
        edge=edge,
        edge_bps=edge_bps,
        note=note,
    )


def find_all_arbs(
    poly_markets: List[UpDownMarket],
    kalshi_markets: List[KalshiMarket],
    min_edge_bps: float = 50.0,
    fee_bps: float = 0.0,
) -> List[ArbOpportunity]:
    by_asset_kalshi = {m.asset: m for m in kalshi_markets}
    out: List[ArbOpportunity] = []
    for pm in poly_markets:
        km = by_asset_kalshi.get(pm.asset)
        if km is None:
            continue
        arb = find_arb_for_asset(pm, km, fee_bps=fee_bps)
        if arb.edge_bps >= min_edge_bps:
            out.append(arb)
    return out
