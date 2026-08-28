# NorthStar

A **beginner-friendly** Polymarket/Kalshi trading toolkit inspired by two quant threads:

| Source | Idea |
|--------|------|
| [@antpalkin](https://x.com/antpalkin/status/2046654122892403188) | **Markov chains** on short-window crypto markets → Monte Carlo fair value → **edge** vs market price → **Kelly** sizing |
| [@ridark_eth](https://x.com/ridark_eth/status/2055979590435115022) | **Cross-market stat arb** (Polymarket ↔ Kalshi) when the same event is mispriced |

You will grow through **three modes** on purpose — never jump to live until paper and dry-run feel boring.

The CLI command is `northstar` (`poly` still works as an alias). The Python package path remains `src/poly/` until a later rename.

## Roadmap (how we build slowly)

### Phase 1 — Paper (you are here) ✅

- Learn the math with **fake money** and **sample price data**
- Markov transition matrix → simulate outcomes → only “trade” when edge clears a threshold
- Kelly fraction caps how much you risk per bet

```bash
cd /Volumes/App/NorthStar
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
northstar paper --windows 200
northstar explain   # plain-English walkthrough of one decision
```

### Phase 1.5 — Hedged YES+NO (Gabagool-style)

- Buys BOTH sides cheap → locks in profit no matter how the market resolves
- Tutorial for *why win rate is the wrong metric*
- Inspired by the [Gabagool bot](https://github.com/satyasumn7/Polymarket-Trading-Bot-Gabagool)

```bash
northstar hedged --windows 150
```

### Phase 2 — Dry-run ✅

Real Polymarket **Gamma + CLOB** prices. Logs signals only — **no wallet, no orders**.

```bash
cp .env.example .env   # optional: set POLY_MODE=dry
northstar markets                    # list active 5m BTC/ETH/SOL markets
northstar dry --duration 0           # one snapshot of signals
northstar dry --duration 120         # poll 2 minutes (every 5s)
northstar dry --strategy markov      # Markov only
northstar dry --strategy hedged      # hedged only
```

APIs used (all public, read-only):

| API | URL |
|-----|-----|
| Gamma | `https://gamma-api.polymarket.com` |
| CLOB | `https://clob.polymarket.com` |

### Phase 2.5 — Practice trading ✅

Live Polymarket prices, **virtual money**. Persistent account in `~/.poly/practice.json`.

```bash
# Fresh virtual $1k (add -y to skip confirmation)
northstar practice reset --bankroll 1000 -y

# 5-minute live dashboard with auto-trade
northstar practice run --duration 300

# Watch only — no auto-trades
northstar practice run --duration 300 --manual

# Manual buy $25 of ETH UP (run in another terminal while dashboard runs)
northstar practice buy ETH UP 25

northstar practice status
northstar practice close POSITION_ID
```

The dashboard shows live UP/DOWN mids, your open positions with mark-to-market PnL,
and auto-settles positions when their 5m markets close on Polymarket.

### Phase 2.6 — Kalshi cross-market dry-run ✅

Public Kalshi market data (no API key needed) for the same crypto assets.

```bash
northstar kalshi                            # active 15m BTC/ETH/SOL Kalshi markets
northstar cross-arb                         # Polymarket vs Kalshi side-by-side
northstar cross-arb --min-edge-bps 50 --fee-bps 30
```

Kalshi rate-limits burst traffic. Run **`northstar cross-arb` alone** (it includes both
sides). If you see `429 Too Many Requests`, wait ~10 seconds and retry once.

Note: Polymarket's 5-minute windows and Kalshi's 15-minute windows resolve at
different times, so a price gap is **not** risk-free arbitrage — treat it as a
divergence signal. Same-window matching comes when Kalshi launches 5m crypto
markets (or with manual time alignment).

### Phase 2.7 — Kalshi dry-run (for US traders) ✅

Signals for **Kalshi 15m** markets — the platform you can trade today.

```bash
northstar kalshi-dry
northstar kalshi-dry --duration 300
```

Green **▶** = open Kalshi app and place the trade manually. See [docs/KALSHI_SETUP.md](docs/KALSHI_SETUP.md).

```bash
northstar practice pnl    # quick up/down on virtual account
```

### Phase 3 — Live Kalshi orders (next)

- RSA API key from Kalshi Settings → see [docs/KALSHI_SETUP.md](docs/KALSHI_SETUP.md)

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
src/poly/          Python package (name unchanged for now)
  models/          markov, kelly, edge math
  strategies/      markov_crypto (active), cross_arb (stub)
  execution/       paper (active), dry + live (stubs)
  data/            sample generators for learning
agents/            Hypothesis Graph research memory (append-only)
```

## Commands

| Command | What it does |
|---------|----------------|
| `northstar paper` | Markov+Kelly directional paper backtest |
| `northstar hedged` | Hedged YES+NO paper backtest (direction-neutral) |
| `northstar explain` | Step-by-step explanation of one Markov trade decision |
| `northstar markets` | List live 5m Up/Down markets (Polymarket Gamma) |
| `northstar kalshi` | List live 15m crypto markets (Kalshi) |
| `northstar kalshi-dry` | Kalshi-only signals (trade manually in app) |
| `northstar cross-arb` | Polymarket vs Kalshi price comparison |
| `northstar practice pnl` | Quick practice account up/down |
| `northstar dry` | Real prices, dry-run signals (no orders) |
| `northstar practice run` | Live dashboard with virtual bankroll |
| `northstar practice buy / close / status / reset` | Manage your practice account |
| `northstar status` | Fences + last saved lesson (read-only; `--json` for agents) |

## Safety

- **Never** commit `.env` or private keys.
- Paper mode cannot spend money.
- Live mode will refuse to run without both env flag and `--live`.

## Learn more

- Polymarket [docs](https://docs.polymarket.com/)
- Chainlink resolution for ETH up/down 5m markets
- Kelly criterion: bet size ∝ edge / variance
