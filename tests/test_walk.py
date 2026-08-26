from poly.practice.walk import (
    DEFAULT_SPEND,
    FOOTER,
    MAX_SPEND,
    WalkQuote,
    clamp_spend,
    format_walk,
    lose_pnl,
    pair_cost,
    tickets_bought,
    win_pnl,
)


def test_step2_pnl_two_dollars_at_forty_cents():
    spend = 2.0
    price = 0.40
    assert tickets_bought(spend, price) == 5.0
    assert win_pnl(spend, price) == 3.0
    assert lose_pnl(spend, price) == -2.0


def test_cheap_pair_under_one_dollar():
    assert pair_cost(0.40, 0.40) == 0.80
    assert pair_cost(0.40, 0.40) < 1.0
    assert pair_cost(0.60, 0.55) == 1.15
    assert pair_cost(0.60, 0.55) > 1.0


def test_clamp_spend_default_and_cap():
    assert clamp_spend(2.0) == (2.0, None)
    usd, note = clamp_spend(10.0)
    assert usd == MAX_SPEND
    assert note is not None
    usd, note = clamp_spend(0.0)
    assert usd == DEFAULT_SPEND
    assert note is not None


def test_format_walk_has_four_steps_and_practice_only_footer():
    quote = WalkQuote(
        asset="ETH",
        question="Will ETH be above the strike?",
        yes_price=0.40,
        no_price=0.40,
        model_prob=0.50,
        edge=0.10,
    )
    text = format_walk(quote, spend=2.0)
    assert "Step 1" in text
    assert "Step 2" in text
    assert "Step 3" in text
    assert "Step 4" in text
    assert FOOTER in text
    assert "+$3.00" in text
    assert "too cheap" in text.lower()
    assert "cheap pair" in text.lower()


def test_format_walk_expensive_pair_and_negative_edge():
    quote = WalkQuote(
        asset="BTC",
        question="BTC up/down",
        yes_price=0.80,
        no_price=0.55,
        model_prob=0.70,
        edge=-0.10,
    )
    text = format_walk(quote, spend=2.0)
    assert "too expensive" in text.lower()
    assert "skip" in text.lower()


def test_format_walk_without_guess_does_not_invent_edge():
    quote = WalkQuote(
        asset="SOL",
        question="SOL",
        yes_price=0.50,
        no_price=0.50,
        model_prob=None,
        edge=None,
    )
    text = format_walk(quote, spend=2.0)
    assert "wait" in text.lower()
    assert "too cheap" not in text.lower()


def test_walk_module_does_not_import_live():
    import inspect

    from poly.practice import walk

    source = inspect.getsource(walk)
    assert "execution.live" not in source
    assert "run_live_loop" not in source
