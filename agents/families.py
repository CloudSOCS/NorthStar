"""Deterministic family tags for Hypothesis Graph entries."""

_EXPLICIT = {
    "mean_reversion": "mean_reversion",
    "mean_reversion_pro": "mean_reversion",
    "vwap_reversion": "mean_reversion",
    "bollinger_bands": "mean_reversion",
    "pairs_spread": "mean_reversion",
    "macd": "trend",
    "ema_crossover": "trend",
    "triple_ema": "trend",
    "supertrend": "trend",
    "sma_crossover": "trend",
    "tema_cross": "trend",
    "adx_trend": "trend",
    "momentum": "trend",
    "parabolic_sar": "trend",
    "heikin_ashi_ema": "trend",
    "stoch_rsi": "trend",
    "rsi": "trend",
    "rsi_macd_combo": "trend",
    "volume_weighted": "trend",
    "atr_breakout": "breakout",
    "breakout": "breakout",
    "squeeze_momentum": "squeeze",
    "sweep_squeeze_combo": "squeeze",
    "ichimoku_cloud": "cloud",
    "range_scalper": "range",
    "order_blocks": "range",
    "regime_adaptive": "regime",
    "regime_adaptive_htf": "regime",
}


def family_for(name: str) -> str:
    return _EXPLICIT.get(name, "misc")
