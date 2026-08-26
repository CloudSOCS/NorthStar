"""Curated Hypothesis Graph seed from M5 fee-audit rows + documented kills."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from agents.critic import map_m5_payload
from agents.hypothesis_graph import (
    DEFAULT_PATH,
    append_entry,
    empty_graph,
    save_graph,
)

# (name, registry, trades, trades_per_year, mean_gross_ret, mean_net_ret,
#  fee_drag_pp, mean_net_sharpe, verdict) — copied from docs/research/fee-audit-m5.md
_M5_ROWS: List[Tuple[Any, ...]] = [
    ("vwap_reversion", "spot", 1467, 249.7, -6.21, -34.59, 28.39, -1.90, "deprecate"),
    ("parabolic_sar", "spot", 1301, 221.5, -8.22, -33.26, 25.04, -1.88, "deprecate"),
    ("macd", "spot", 1231, 209.5, -8.05, -30.98, 22.93, -1.83, "deprecate"),
    ("heikin_ashi_ema", "spot", 787, 134.0, -13.16, -28.08, 14.92, -1.56, "deprecate"),
    ("stoch_rsi", "spot", 652, 111.0, -12.01, -24.96, 12.95, -1.42, "deprecate"),
    ("regime_adaptive", "spot", 495, 84.3, 3.96, -8.46, 12.43, -0.94, "graduate_m1"),
    ("ema_crossover", "spot", 554, 94.3, -10.48, -22.10, 11.62, -1.40, "deprecate"),
    ("triple_ema", "spot", 507, 86.3, -6.12, -16.98, 10.87, -1.08, "deprecate"),
    ("tema_cross", "spot", 444, 75.6, 0.59, -9.71, 10.30, -0.97, "graduate_m1"),
    ("supertrend", "spot", 466, 79.3, -9.76, -19.90, 10.14, -1.20, "deprecate"),
    ("mean_reversion", "spot", 487, 82.9, -17.58, -26.87, 9.30, -1.51, "deprecate"),
    ("atr_breakout", "spot", 382, 65.0, -3.62, -12.36, 8.74, -1.02, "deprecate"),
    ("bollinger_bands", "spot", 338, 57.5, -11.50, -18.98, 7.48, -1.07, "deprecate"),
    ("sma_crossover", "spot", 358, 60.9, -7.35, -14.75, 7.40, -0.93, "deprecate"),
    ("pairs_spread", "spot", 367, 62.5, -18.37, -25.23, 6.86, -1.48, "deprecate"),
    ("breakout", "futures", 260, 44.3, 5.28, -1.54, 6.82, -0.10, "graduate_m1"),
    ("order_blocks", "spot", 288, 49.0, -1.63, -8.37, 6.74, -0.57, "deprecate"),
    ("momentum", "futures", 285, 48.5, -8.12, -14.61, 6.49, -1.17, "deprecate"),
    ("volume_weighted", "spot", 275, 46.8, -6.92, -12.69, 5.78, -0.70, "deprecate"),
    ("adx_trend", "spot", 199, 33.9, -19.38, -23.44, 4.06, -1.21, "deprecate"),
    ("ichimoku_cloud", "spot", 171, 29.1, -1.67, -5.21, 3.54, -0.59, "deprecate"),
    ("squeeze_momentum", "spot", 131, 22.3, -0.29, -3.69, 3.40, -0.10, "deprecate"),
    ("rsi_macd_combo", "spot", 175, 29.8, -19.87, -23.22, 3.35, -1.11, "deprecate"),
    ("momentum", "spot", 127, 21.6, -9.30, -11.95, 2.65, -0.80, "deprecate"),
    ("rsi", "spot", 116, 19.7, -19.75, -21.95, 2.20, -1.17, "deprecate"),
    ("vol_momentum", "spot", 86, 14.6, -0.43, -2.56, 2.13, -0.57, "deprecate"),
    ("amd_ifvg", "spot", 85, 14.5, -8.50, -10.18, 1.68, -0.55, "deprecate"),
    ("mtf_confluence", "spot", 63, 10.7, -1.14, -2.58, 1.45, -0.23, "deprecate"),
    ("regime_adaptive_htf", "spot", 37, 6.3, 0.27, -0.66, 0.94, -0.05, "graduate_m1"),
    ("sweep_squeeze_combo", "spot", 25, 4.3, -6.65, -7.18, 0.52, -0.52, "deprecate"),
    ("range_scalper", "spot", 11, 1.9, -8.29, -8.47, 0.17, -0.47, "deprecate"),
    # Incomplete: long-leg only; short unmeasured
    ("mean_reversion_pro", "spot", 18, 3.1, -2.73, -3.13, 0.40, -0.04, "unscreened_short"),
]

_SEED_SOURCE = "docs/research/fee-audit-m5.md"
_SEED_DATE = "2026-06-12"

_DOCUMENTED_983: Dict[str, Any] = {
    "id": "squeeze_momentum.documented.983",
    "name": "squeeze_momentum",
    "version": "defaults",
    "family": "squeeze",
    "core_idea": "TTM-style squeeze momentum; #983 froze entry and swept close stacks.",
    "status": "killed",
    "failure_reason": (
        "25-stack close sweep did not cut -58.5% DD without losing the "
        "+47.9pt vs-B&H edge."
    ),
    "regime_or_period": "continuous audit 2025-06-10→latest cache; BTC/ETH/SOL 1h+4h",
    "metrics": {"worst_max_dd_pct": -58.5, "vs_bh_pts": 47.9},
    "lesson": (
        "DD is regime exposure not an exit-stack problem; persistent long/flat "
        "entries re-enter next bar after stop-out (fee churn); holding-structure "
        "changes must be re-run on the continuous audit window."
    ),
    "date": "2026-06-12",
    "harness": "documented",
    "verdict": "documented",
    "source": "backtest/candidates/squeeze_983/README.md",
    "issue": "#983",
    "window": "audit_continuous",
    "direction": "long",
}

_DOCUMENTED_997: Dict[str, Any] = {
    "id": "ichimoku_cloud.documented.997",
    "name": "ichimoku_cloud",
    "version": "defaults",
    "family": "cloud",
    "core_idea": "Ichimoku cloud; #997 M3 exit-quality knobs on frozen entry.",
    "status": "killed",
    "failure_reason": "M3 knobs fail OOS on every tried stop/time/zscore combo; late giveback dominates.",
    "regime_or_period": "M1/M3 IS+OOS; BTC/ETH/SOL 1h+4h",
    "metrics": {},
    "lesson": "Exit-quality knobs did not rescue ichimoku OOS; do not retune the same exits expecting a pass.",
    "date": "2026-06-12",
    "harness": "documented",
    "verdict": "documented",
    "source": "backtest/candidates/ichimoku_997/README.md",
    "issue": "#997",
    "window": "oos",
    "direction": "long",
}


def _synthetic_m5_payload() -> Dict[str, Any]:
    rows = []
    for (
        name, registry, trades, tpy, gross, net, drag, sharpe, verdict,
    ) in _M5_ROWS:
        rows.append({
            "strategy": name,
            "registry": registry,
            "trades": trades,
            "trades_per_year": tpy,
            "mean_gross_ret": gross,
            "mean_net_ret": net,
            "fee_drag_pp": drag,
            "mean_net_sharpe": sharpe,
            "n_liquidated": 0,
            "verdict": verdict,
        })
    return {"registry": "both", "direction": "long", "rows": rows}


def build_seed_graph() -> Dict[str, Any]:
    """Build the committed seed graph from M5 table + #983/#997 documented kills."""
    payload = _synthetic_m5_payload()
    mapped = map_m5_payload(
        payload,
        include_incomplete=True,
        source=_SEED_SOURCE,
        date=_SEED_DATE,
    )
    # Payload lists only one incomplete row; keep that invariant explicit.
    mapped = [
        e for e in mapped
        if e["verdict"] != "unscreened_short" or e["name"] == "mean_reversion_pro"
    ]
    g = empty_graph(updated=_SEED_DATE)
    for entry in mapped:
        g = append_entry(g, entry)
    g = append_entry(g, _DOCUMENTED_983)
    g = append_entry(g, _DOCUMENTED_997)
    return g


if __name__ == "__main__":
    graph = build_seed_graph()
    save_graph(graph, DEFAULT_PATH)
    print(f"wrote {DEFAULT_PATH} entries={len(graph['entries'])}")
