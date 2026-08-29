# NorthStar Grok Bot setup

First run on the bot computer. A human does this once, watches the walk, then the worker uses the same repo. Always `uv run northstar …` from the repo root. This is not a trade.

You need **git** and **uv** on the machine.

## 1. Clone

```bash
git clone https://github.com/CloudSOCS/NorthStar.git
cd NorthStar
```

## 2. Install

```bash
uv sync
```

## 3. First proof

```bash
uv run northstar status --json
```

You should see `live_orders` = `unwired`, `generator` = `stubbed`, `graph_command` = `stop`, and `last_walk` = `null` (no lesson saved yet). Believe that JSON. Do not invent a different fence.

## 4. Watched demo (human on the keyboard)

Stay at the machine. Watch this print Steps 1–4. No order is placed.

```bash
uv run northstar practice walk --save
```

If Kalshi rate-limits, use the teaching snapshot instead (no live market):

```bash
uv run northstar practice walk --demo --save
```

`--save` writes a local lesson notebook. That is not a trade. If it says **Guess: not ready**, that is the real answer — do not invent an edge. `--demo` is not a live Kalshi market.

## 5. Proof the notebook wrote

```bash
uv run northstar practice last --json
```

You should get JSON with a non-empty `entries` list. The newest lesson is first. Quote only what it printed.

## 6. What “done” looks like

Run status again:

```bash
uv run northstar status --json
```

Done when:

- `fences.live_orders` is still `unwired`
- `fences.generator` is still `stubbed`
- `fences.graph_command` is still `stop`
- `last_walk` is **not** `null`

Paste the worker charter from `docs/GROK_BOT.md` into the Grok Bot. The worker stays inside that allowlist.

## 7. What not to do

Do not add live keys. Do not un-stub the generator. Do not write the Hypothesis Graph. Do not run any command that is not on the charter list. Do not click Yes/No or enter an amount — the bot only suggests.
