from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionMode(str, Enum):
    PAPER = "paper"
    DRY = "dry"
    LIVE = "live"


class Settings(BaseSettings):
    """All tunables; override via .env or environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    poly_mode: ExecutionMode = Field(default=ExecutionMode.PAPER, alias="POLY_MODE")

    # Polymarket APIs (read-only for dry-run)
    gamma_api_url: str = Field(
        default="https://gamma-api.polymarket.com", alias="GAMMA_API_URL"
    )
    clob_api_url: str = Field(
        default="https://clob.polymarket.com", alias="CLOB_API_URL"
    )
    dry_poll_seconds: float = Field(default=5.0, alias="DRY_POLL_SECONDS")
    dry_assets: str = Field(
        default="BTC,ETH,SOL,BNB,XRP", alias="DRY_ASSETS"
    )

    # Markov / edge strategy
    min_edge: float = Field(default=0.03, alias="MIN_EDGE")
    entry_min_price: float = Field(default=0.83, alias="ENTRY_MIN_PRICE")
    entry_max_price: float = Field(default=0.97, alias="ENTRY_MAX_PRICE")
    kelly_fraction: float = Field(default=0.25, alias="KELLY_FRACTION")
    max_bet_fraction: float = Field(default=0.10, alias="MAX_BET_FRACTION")
    starting_bankroll: float = Field(default=1000.0, alias="STARTING_BANKROLL")
    n_markov_bins: int = Field(default=10, alias="N_MARKOV_BINS")
    monte_carlo_paths: int = Field(default=500, alias="MONTE_CARLO_PATHS")

    # Cross-market arb (Phase 2)
    min_arb_edge_bps: int = Field(default=50, alias="MIN_ARB_EDGE_BPS")
    match_auto_threshold: float = Field(default=0.85, alias="MATCH_AUTO_THRESHOLD")

    # Live-only (optional)
    polygon_private_key: Optional[str] = Field(default=None, alias="POLYGON_PRIVATE_KEY")
    kalshi_api_key: Optional[str] = Field(default=None, alias="KALSHI_API_KEY")
    kalshi_api_secret: Optional[str] = Field(default=None, alias="KALSHI_API_SECRET")


def get_settings() -> Settings:
    return Settings()
