from __future__ import annotations

from dataclasses import dataclass

from poly.config import ExecutionMode, Settings


@dataclass(frozen=True)
class ModeStatus:
    mode: ExecutionMode
    markov_active: bool
    cross_arb_active: bool
    places_orders: bool
    notes: str


def describe_mode(settings: Settings) -> ModeStatus:
    if settings.poly_mode == ExecutionMode.PAPER:
        return ModeStatus(
            mode=ExecutionMode.PAPER,
            markov_active=True,
            cross_arb_active=False,
            places_orders=False,
            notes="Synthetic data only. Safest place to learn.",
        )
    if settings.poly_mode == ExecutionMode.DRY:
        return ModeStatus(
            mode=ExecutionMode.DRY,
            markov_active=True,
            cross_arb_active=True,
            places_orders=False,
            notes="Real feeds, logged signals, no wallet (Phase 2).",
        )
    return ModeStatus(
        mode=ExecutionMode.LIVE,
        markov_active=True,
        cross_arb_active=True,
        places_orders=True,
        notes="Real orders — requires keys + --live (Phase 3).",
    )
