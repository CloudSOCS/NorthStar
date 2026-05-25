from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EdgeDecision:
    model_prob: float
    market_price: float
    edge: float
    in_entry_band: bool
    should_trade: bool
    reason: str


def compute_edge(
    model_prob: float,
    market_price: float,
    min_edge: float,
    entry_min: float,
    entry_max: float,
) -> EdgeDecision:
    edge = model_prob - market_price
    in_band = entry_min <= market_price <= entry_max

    if not in_band:
        return EdgeDecision(
            model_prob=model_prob,
            market_price=market_price,
            edge=edge,
            in_entry_band=False,
            should_trade=False,
            reason=f"Price {market_price:.2f} outside entry band [{entry_min}, {entry_max}]",
        )
    if edge < min_edge:
        return EdgeDecision(
            model_prob=model_prob,
            market_price=market_price,
            edge=edge,
            in_entry_band=True,
            should_trade=False,
            reason=f"Edge {edge:.3f} below minimum {min_edge:.3f}",
        )
    return EdgeDecision(
        model_prob=model_prob,
        market_price=market_price,
        edge=edge,
        in_entry_band=True,
        should_trade=True,
        reason=f"Edge {edge:.3f} clears threshold — signal to buy YES",
    )
