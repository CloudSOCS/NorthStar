"""
Practice trading account: persistent virtual bankroll, positions, history.

State is saved to JSON so a session survives Ctrl+C and reruns. No real money
ever touches this. Settlements use live Gamma data (closed market + outcomePrices)
to mark positions UP or DOWN.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional

Side = Literal["UP", "DOWN"]

ACCOUNT_BANNER = (
    "This is a fake-money wallet, not a Kalshi live account — no live order will be placed."
)
ACCOUNT_WALK_HINT = (
    "Four-step lesson (ticket, P&L, edge, hedge): northstar practice walk"
)


@dataclass
class Position:
    id: str
    market_slug: str
    asset: str
    side: Side
    shares: float
    entry_price: float
    capital_used: float
    opened_at: float
    strategy: str = "manual"
    closed: bool = False
    settled_at: Optional[float] = None
    realized_pnl: Optional[float] = None
    closing_price: Optional[float] = None


@dataclass
class SettlementEvent:
    position_id: str
    market_slug: str
    asset: str
    side: Side
    shares: float
    entry_price: float
    closing_price: float
    realized_pnl: float
    note: str
    settled_at: float = field(default_factory=time.time)


@dataclass
class PracticeAccount:
    bankroll: float
    starting_bankroll: float
    positions: List[Position] = field(default_factory=list)
    history: List[SettlementEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_saved: float = field(default_factory=time.time)

    def open_positions(self) -> List[Position]:
        return [p for p in self.positions if not p.closed]

    def open_for_market(self, market_slug: str, side: Optional[Side] = None) -> List[Position]:
        out = []
        for p in self.open_positions():
            if p.market_slug == market_slug and (side is None or p.side == side):
                out.append(p)
        return out

    def total_capital_at_risk(self) -> float:
        return sum(p.capital_used for p in self.open_positions())

    def total_realized_pnl(self) -> float:
        return sum(ev.realized_pnl for ev in self.history)

    def mark_to_market(self, mids: Dict[str, Dict[Side, float]]) -> float:
        """Sum of mid-price value of all open positions."""
        total = 0.0
        for p in self.open_positions():
            market_mids = mids.get(p.market_slug, {})
            mid = market_mids.get(p.side, p.entry_price)
            total += p.shares * mid
        return total

    def unrealized_pnl(self, mids: Dict[str, Dict[Side, float]]) -> float:
        risk = self.total_capital_at_risk()
        return self.mark_to_market(mids) - risk

    def buy(
        self,
        market_slug: str,
        asset: str,
        side: Side,
        usd: float,
        price: float,
        strategy: str = "manual",
    ) -> Position:
        if usd <= 0:
            raise ValueError("usd must be > 0")
        if not (0 < price < 1):
            raise ValueError(f"price must be in (0,1), got {price}")
        if usd > self.bankroll + 1e-6:
            raise ValueError(f"insufficient bankroll: have ${self.bankroll:.2f}, need ${usd:.2f}")

        shares = usd / price
        pos = Position(
            id=uuid.uuid4().hex[:8],
            market_slug=market_slug,
            asset=asset,
            side=side,
            shares=shares,
            entry_price=price,
            capital_used=usd,
            opened_at=time.time(),
            strategy=strategy,
        )
        self.bankroll -= usd
        self.positions.append(pos)
        return pos

    def settle(
        self,
        position: Position,
        won: bool,
        note: str = "market resolved",
    ) -> SettlementEvent:
        if position.closed:
            raise ValueError(f"position {position.id} already closed")
        payout = position.shares * 1.0 if won else 0.0
        realized = payout - position.capital_used
        position.closed = True
        position.settled_at = time.time()
        position.realized_pnl = realized
        position.closing_price = 1.0 if won else 0.0
        self.bankroll += payout
        ev = SettlementEvent(
            position_id=position.id,
            market_slug=position.market_slug,
            asset=position.asset,
            side=position.side,
            shares=position.shares,
            entry_price=position.entry_price,
            closing_price=position.closing_price,
            realized_pnl=realized,
            note=note,
        )
        self.history.append(ev)
        return ev

    def close_at_price(
        self,
        position: Position,
        sell_price: float,
        note: str = "user closed",
    ) -> SettlementEvent:
        """Manual close: sell shares back at current mid price (no real fill, ok for practice)."""
        if position.closed:
            raise ValueError(f"position {position.id} already closed")
        proceeds = position.shares * sell_price
        realized = proceeds - position.capital_used
        position.closed = True
        position.settled_at = time.time()
        position.realized_pnl = realized
        position.closing_price = sell_price
        self.bankroll += proceeds
        ev = SettlementEvent(
            position_id=position.id,
            market_slug=position.market_slug,
            asset=position.asset,
            side=position.side,
            shares=position.shares,
            entry_price=position.entry_price,
            closing_price=sell_price,
            realized_pnl=realized,
            note=note,
        )
        self.history.append(ev)
        return ev


def default_state_path() -> Path:
    override = os.environ.get("POLY_PRACTICE_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".poly" / "practice.json"


def save_account(account: PracticeAccount, path: Optional[Path] = None) -> Path:
    path = path or default_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    account.last_saved = time.time()
    blob = {
        "bankroll": account.bankroll,
        "starting_bankroll": account.starting_bankroll,
        "created_at": account.created_at,
        "last_saved": account.last_saved,
        "positions": [asdict(p) for p in account.positions],
        "history": [asdict(e) for e in account.history],
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(blob, indent=2))
    tmp.replace(path)
    return path


def load_account(
    path: Optional[Path] = None,
    starting_bankroll: float = 1000.0,
) -> PracticeAccount:
    path = path or default_state_path()
    if not path.exists():
        return PracticeAccount(
            bankroll=starting_bankroll,
            starting_bankroll=starting_bankroll,
        )
    blob = json.loads(path.read_text())
    return PracticeAccount(
        bankroll=blob.get("bankroll", starting_bankroll),
        starting_bankroll=blob.get("starting_bankroll", starting_bankroll),
        created_at=blob.get("created_at", time.time()),
        last_saved=blob.get("last_saved", time.time()),
        positions=[Position(**p) for p in blob.get("positions", [])],
        history=[SettlementEvent(**e) for e in blob.get("history", [])],
    )
