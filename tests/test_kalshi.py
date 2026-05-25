from poly.clients.gamma import UpDownMarket
from poly.clients.kalshi import KALSHI_CRYPTO_SERIES, KalshiMarket
from poly.strategies.cross_arb import find_all_arbs, find_arb_for_asset


def test_kalshi_series_map_has_majors():
    for asset in ["BTC", "ETH", "SOL", "BNB", "XRP"]:
        assert asset in KALSHI_CRYPTO_SERIES


def test_kalshi_market_mid_with_bid_ask():
    m = KalshiMarket(
        asset="BTC",
        ticker="KXBTC15M-T",
        event_ticker="KXBTC15M",
        title="BTC price up in next 15 mins?",
        yes_sub_title="Target: $70k",
        yes_bid=0.80,
        yes_ask=0.82,
        no_bid=0.18,
        no_ask=0.20,
        last_price=0.81,
        close_time="2026-05-25T21:15:00Z",
    )
    assert 0.80 <= m.yes_mid <= 0.82
    assert m.no_mid == 1 - m.yes_mid


def _poly(asset: str, up: float, down: float) -> UpDownMarket:
    return UpDownMarket(
        market_id="1",
        asset=asset,
        question=f"{asset} Up or Down",
        slug=f"{asset.lower()}-updown-5m-1",
        up_token_id="111",
        down_token_id="222",
        gamma_up_price=up,
        gamma_down_price=down,
    )


def _kalshi(asset: str, yes_ask: float, no_ask: float) -> KalshiMarket:
    return KalshiMarket(
        asset=asset,
        ticker="t",
        event_ticker="e",
        title="t",
        yes_sub_title="",
        yes_bid=yes_ask - 0.01,
        yes_ask=yes_ask,
        no_bid=no_ask - 0.01,
        no_ask=no_ask,
        last_price=yes_ask,
        close_time="2026-05-25T21:15:00Z",
    )


def test_arb_detects_positive_edge():
    pm = _poly("ETH", up=0.40, down=0.62)
    km = _kalshi("ETH", yes_ask=0.55, no_ask=0.55)
    arb = find_arb_for_asset(pm, km)
    # poly-UP 0.40 + kalshi-NO 0.55 = 0.95 < 1.00 → edge ~500 bps
    assert arb.has_arb is True
    assert arb.edge_bps > 400


def test_arb_no_edge_when_aligned():
    pm = _poly("BTC", up=0.50, down=0.50)
    km = _kalshi("BTC", yes_ask=0.51, no_ask=0.51)
    arb = find_arb_for_asset(pm, km)
    assert arb.has_arb is False


def test_find_all_arbs_filters_by_edge():
    pm_eth = _poly("ETH", up=0.40, down=0.62)
    pm_btc = _poly("BTC", up=0.50, down=0.50)
    km_eth = _kalshi("ETH", yes_ask=0.55, no_ask=0.55)
    km_btc = _kalshi("BTC", yes_ask=0.51, no_ask=0.51)
    out = find_all_arbs([pm_eth, pm_btc], [km_eth, km_btc], min_edge_bps=100)
    assets = [a.asset for a in out]
    assert "ETH" in assets
    assert "BTC" not in assets
