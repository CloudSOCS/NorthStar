from poly.clients.gamma import (
    UpDownMarket,
    _asset_from_slug,
    _is_5m_updown_market,
    _parse_json_list,
)


def test_parse_json_list_string():
    assert _parse_json_list('["Up", "Down"]') == ["Up", "Down"]


def test_is_5m_slug():
    assert _is_5m_updown_market(
        {"slug": "eth-updown-5m-123", "question": "Ethereum Up or Down - x"}
    )
    assert not _is_5m_updown_market(
        {"slug": "eth-updown-15m-123", "question": "Ethereum Up or Down - x"}
    )


def test_asset_from_slug():
    assert _asset_from_slug("btc-updown-5m-1") == "BTC"


def test_updown_market_dataclass():
    m = UpDownMarket(
        market_id="1",
        asset="ETH",
        question="Ethereum Up or Down",
        slug="eth-updown-5m-1",
        up_token_id="111",
        down_token_id="222",
        gamma_up_price=0.51,
        gamma_down_price=0.49,
    )
    assert m.asset == "ETH"
