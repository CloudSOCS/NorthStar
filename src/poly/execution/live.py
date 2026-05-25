"""
Phase 3 — Live execution.

Requires POLYGON_PRIVATE_KEY, POLY_MODE=live, and CLI --live flag.
"""

from __future__ import annotations

from poly.config import Settings


def assert_live_allowed(settings: Settings, cli_live_flag: bool) -> None:
    if settings.poly_mode.value != "live":
        raise RuntimeError("POLY_MODE must be 'live' in .env")
    if not cli_live_flag:
        raise RuntimeError("Refusing to trade: pass --live on the command line")
    if not settings.polygon_private_key:
        raise RuntimeError("POLYGON_PRIVATE_KEY missing in .env")


def run_live_loop(settings: Settings, cli_live_flag: bool) -> None:
    assert_live_allowed(settings, cli_live_flag)
    raise NotImplementedError("Live trading is Phase 3 — finish dry-run first.")
