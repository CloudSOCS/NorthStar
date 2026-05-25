import numpy as np

from poly.models.kelly import kelly_binary_yes, size_bet_usd
from poly.models.markov import MarkovModel, price_to_state, build_demo_transition
from poly.models.edge import compute_edge


def test_price_to_state_bins():
    assert price_to_state(0.0, 10) == 0
    assert price_to_state(0.95, 10) == 9


def test_markov_fit_stochastic_matrix():
    prices = [0.5 + 0.01 * i for i in range(20)]
    model = MarkovModel.fit(prices, n_bins=10)
    assert model.transition.shape == (10, 10)
    assert np.allclose(model.transition.sum(axis=1), 1.0)


def test_monte_carlo_probability_bounds():
    model = MarkovModel(build_demo_transition(10), n_bins=10)
    p = model.monte_carlo_up_probability(0.5, n_steps=5, n_paths=200, seed=1)
    assert 0.0 <= p <= 1.0


def test_kelly_zero_on_negative_edge():
    assert kelly_binary_yes(0.5, 0.6) == 0.0


def test_kelly_positive_with_edge():
    f = kelly_binary_yes(0.6, 0.5)
    assert f > 0


def test_size_bet_respects_cap():
    bet = size_bet_usd(1000, 0.9, 0.5, kelly_fraction=1.0, max_bet_fraction=0.05)
    assert bet <= 50.0 + 1e-6


def test_edge_decision_band():
    d = compute_edge(0.92, 0.88, min_edge=0.03, entry_min=0.83, entry_max=0.97)
    assert d.should_trade is True

    d_low = compute_edge(0.89, 0.88, min_edge=0.03, entry_min=0.83, entry_max=0.97)
    assert d_low.should_trade is False
