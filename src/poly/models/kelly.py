from __future__ import annotations


def kelly_binary_yes(prob_win: float, market_price: float) -> float:
    """
    Kelly fraction for buying YES at `market_price` when true win prob is `prob_win`.

    For a $1 payout share bought at price c:
      b = (1 - c) / c   (net odds on capital risked)
      f* = (p * b - (1 - p)) / b  = (p - c) / (1 - c)  when simplified for binary

    Returns 0 if edge is negative (no bet).
    """
    p = max(0.0, min(1.0, prob_win))
    c = max(1e-6, min(1.0 - 1e-6, market_price))
    if p <= c:
        return 0.0
    return (p - c) / (1.0 - c)


def size_bet_usd(
    bankroll: float,
    prob_win: float,
    market_price: float,
    kelly_fraction: float = 0.25,
    max_bet_fraction: float = 0.10,
) -> float:
    """Dollar size using fractional Kelly, capped per settings."""
    f_star = kelly_binary_yes(prob_win, market_price)
    f = f_star * kelly_fraction
    f = min(f, max_bet_fraction)
    return max(0.0, bankroll * f)
