from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


def price_to_state(price: float, n_bins: int = 10) -> int:
    """Map contract price in [0,1] to bin index in [0, n_bins-1]."""
    p = float(np.clip(price, 0.0, 0.999999))
    return min(int(p * n_bins), n_bins - 1)


def state_to_mid_price(state: int, n_bins: int = 10) -> float:
    """Representative mid-price for a bin (for display)."""
    return (state + 0.5) / n_bins


@dataclass
class MarkovModel:
    """
    Discrete Markov chain over price bins.

    Transition matrix P[i,j] = P(next_state=j | current_state=i).
    Fitted from a sequence of observed prices (e.g. ticks inside a 5m window).
    """

    transition: np.ndarray
    n_bins: int

    @classmethod
    def fit(cls, prices: List[float], n_bins: int = 10) -> "MarkovModel":
        counts = np.zeros((n_bins, n_bins), dtype=float)
        states = [price_to_state(p, n_bins) for p in prices]
        for i in range(len(states) - 1):
            counts[states[i], states[i + 1]] += 1.0

        # Laplace smoothing so empty rows still work
        counts += 1.0
        row_sums = counts.sum(axis=1, keepdims=True)
        transition = counts / row_sums
        return cls(transition=transition, n_bins=n_bins)

    def simulate_terminal_up(
        self,
        start_state: int,
        n_steps: int,
        up_threshold_state: Optional[int] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> bool:
        """
        Random walk for n_steps; return True if terminal state is in the
        'up' half of the price ladder (proxy for YES resolving up).
        """
        if rng is None:
            rng = np.random.default_rng()
        if up_threshold_state is None:
            up_threshold_state = self.n_bins // 2

        state = start_state
        for _ in range(n_steps):
            probs = self.transition[state]
            state = int(rng.choice(self.n_bins, p=probs))
        return state >= up_threshold_state

    def monte_carlo_up_probability(
        self,
        start_price: float,
        n_steps: int,
        n_paths: int = 500,
        seed: Optional[int] = None,
    ) -> float:
        """Fraction of paths that end in the 'up' region."""
        rng = np.random.default_rng(seed)
        start_state = price_to_state(start_price, self.n_bins)
        wins = sum(
            self.simulate_terminal_up(start_state, n_steps, rng=rng)
            for _ in range(n_paths)
        )
        return wins / n_paths

    def expected_next_price(self, start_price: float) -> float:
        """E[next mid-price] from current state."""
        s = price_to_state(start_price, self.n_bins)
        probs = self.transition[s]
        mids = np.array([state_to_mid_price(i, self.n_bins) for i in range(self.n_bins)])
        return float(np.dot(probs, mids))


def build_demo_transition(n_bins: int = 10, persistence: float = 0.7) -> np.ndarray:
    """Synthetic transition matrix biased toward staying in the same bin."""
    p = np.zeros((n_bins, n_bins))
    for i in range(n_bins):
        p[i, i] = persistence
        remainder = 1.0 - persistence
        if i > 0:
            p[i, i - 1] += remainder / 2
        if i < n_bins - 1:
            p[i, i + 1] += remainder / 2
        if i == 0:
            p[i, i + 1] += remainder / 2
        if i == n_bins - 1:
            p[i, i - 1] += remainder / 2
        p[i] /= p[i].sum()
    return p
