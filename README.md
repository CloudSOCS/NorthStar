# poly

A **beginner-friendly** Polymarket trading toolkit inspired by two quant threads:

| Source | Idea |
|--------|------|
| [@antpalkin](https://x.com/antpalkin/status/2046654122892403188) | **Markov chains** on short-window crypto markets → Monte Carlo fair value → **edge** vs market price → **Kelly** sizing |
| [@ridark_eth](https://x.com/ridark_eth/status/2055979590435115022) | **Cross-market stat arb** (Polymarket ↔ Kalshi) when the same event is mispriced |

You will grow through **three modes** on purpose — never jump to live until paper and dry-run feel boring.

## Roadmap (how we build slowly)

### Phase 1 — Paper (you are here) ✅

- Learn the math with **fake money** and **sample price data**
- Markov transition matrix → simulate outcomes → only “trade” when edge clears a threshold
- Kelly fraction caps how much you risk per bet

```bash
cd ~/Projects/poly
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
poly paper --windows 200
poly explain   # plain-English walkthrough of one decision
```

### Phase 1.5 — Hedged YES+NO (Gabagool-style)

- Buys BOTH sides cheap → locks in profit no matter how the market resolves
- Tutorial for *why win rate is the wrong metric*
- Inspired by the [Gabagool bot](https://github.com/satyasumn7/Polymarket-Trading-Bot-Gabagool)

```bash
poly hedged --windows 150
```

### Phase 2 — Dry-run (next)

- Pull **real** Polymarket prices (public APIs, no wallet)
- Print signals: *“would buy UP @ 0.52, edge 4.2%, size $12”*
- Optional Kalshi feed for cross-market arb **detection only**

### Phase 3 — Live (last)

- Requires wallet + API keys in `.env`
- Master switch: `POLY_MODE=live` **and** explicit `--live` flag
- Quarter-Kelly, drawdown circuit breaker, position caps

## Quick concepts (60 seconds)

1. **Markov state** — bucket the contract price into bins (e.g. 80–90¢). The *next* price depends mainly on the *current* bin, not the whole history.
2. **Edge** — `edge = model_probability − market_price`. Positive edge ⇒ model thinks YES is cheap.
3. **Kelly** — optimal bet size from edge and odds. We use **fractional Kelly** (default 25%) so one bad streak does not wipe you.

## Project layout

```
src/poly/
  models/       markov, kelly, edge math
  strategies/   markov_crypto (active), cross_arb (stub)
  execution/    paper (active), dry + live (stubs)
  data/         sample generators for learning
```

## Commands

| Command | What it does |
|---------|----------------|
| `poly paper` | Markov+Kelly directional paper backtest |
| `poly hedged` | Hedged YES+NO paper backtest (direction-neutral) |
| `poly explain` | Step-by-step explanation of one Markov trade decision |
| `poly status` | Show current config and which phase is wired |

## Safety

- **Never** commit `.env` or private keys.
- Paper mode cannot spend money.
- Live mode will refuse to run without both env flag and `--live`.

## Learn more

- Polymarket [docs](https://docs.polymarket.com/)
- Chainlink resolution for ETH up/down 5m markets
- Kelly criterion: bet size ∝ edge / variance
