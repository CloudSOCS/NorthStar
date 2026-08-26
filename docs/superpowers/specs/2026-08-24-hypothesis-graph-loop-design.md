# Hypothesis Graph + Critic Ingest — Cycle 1 Design

**Date:** 2026-08-24
**Status:** Approved — implementation plan next.
**Scope:** Research-memory infrastructure only. No new strategy. No backtester,
data, risk, or execution changes.

This is sub-project 1 of a self-improving loop. Later increments (strategy
generator that emits `@register` code; live/paper deploy) are out of scope
here and must not be started from this spec.

## 1. Goal

Give the research loop a persistent, git-tracked memory of every recorded
attempt and failure, and a critic that can ingest existing M1/M5 harness
output into that memory. Failures cannot be overwritten, deleted, or
forgotten. Kill/salvage decisions live in code, not in prompts.

Universe for this loop is the existing M1/M5 audit slice: BTC/ETH/SOL × 1h/4h,
BinanceUS fee model. This spec does **not** add a US-equities data layer.

## 2. Core design decisions (locked)

| Decision | Choice |
|---|---|
| Persistence | Versioned JSON in git: `agents/hypothesis_graph.json` |
| API | `agents/hypothesis_graph.py` load / validate / query / append |
| Mutation | Append-only. Never delete. Never rewrite an old entry. |
| Supersede | New entry may set `supersedes: "<old_id>"`. Append stamps `superseded_by` on the old entry (pointer only). Old entry is never deleted. `relevant()` returns it with `obsolete: true`. |
| Critic | `agents/critic.py` maps harness JSON → status/verdict using the table below |
| Loop CLI | `agents/loop_controller.py`: `status`, `relevant`, `ingest-m1`, `ingest-m5`, `run-m1` |
| Generator / post-mortem | Stubs that load the graph first and refuse to emit strategy code |
| Harness failure | Fail the CLI loudly; write **nothing** to the graph |
| Spawn | `run-m1` subprocesses existing `backtest/eval_windows.py` only. No `run-m5` this increment. |
| Tests | `agents/test_*.py`; add `agents` to pytest `testpaths` |
| Seed | Curated: M5 deprecate + graduate_m1 + #983 + #997 + mean_reversion_pro incomplete |

## 3. Boundaries (must not break)

**Reuse, do not rewrite:** `backtest/backtester.py`, `backtest/eval_windows.py`,
`backtest/fee_audit.py`, `backtest/run_backtest.py`,
`shared_strategies/open/registry.py`, Go risk/execution (`scheduler/`).

Strategy contract (for later cycles, not this one): `@register` + function
`(df, **params) -> df` with a `signal` column in `{1, -1, 0}`.

**This increment must not:**
- Register a new strategy or edit `PLATFORM_ORDER` / `init.go` / `DEFAULT_PARAM_RANGES`
- Import or call the live scheduler
- Place orders, touch kill-switch, or write `state.db`
- Invent a parallel backtester, window set, or fee model
- Parse `docs/research/fee-audit-m5.md` as a runtime dependency (seed is
  checked-in JSON; markdown is provenance only)

## 4. File layout

```
agents/
  __init__.py
  hypothesis_graph.py       # schema, load, save, append, relevant()
  hypothesis_graph.json     # git-tracked source of truth
  critic.py                 # kill/salvage rules in code; ingest helpers
  loop_controller.py        # CLI
  generator.py              # stub
  post_mortem.py            # stub
  test_hypothesis_graph.py
  test_critic.py
  test_loop_controller.py
  fixtures/                 # tiny synthetic M1/M5 JSON for unit tests
experiments/
  README.md                 # cycle artifacts live here; not the graph
docs/superpowers/specs/2026-08-24-hypothesis-graph-loop-design.md
```

`pyproject.toml` `[tool.pytest.ini_options] testpaths` gains `"agents"`.

Hard import rule: `scheduler/` and `shared_scripts/` must not import `agents`.
`agents` may subprocess `backtest/eval_windows.py` and parse JSON; it must not
reimplement `run_leg` / `score_candidate`.

## 5. Graph JSON schema (`schema_version`: 1)

Root object:

```json
{
  "schema_version": 1,
  "updated": "2026-08-24",
  "universe": {
    "note": "M1/M5 audit slices — do not silently change",
    "datasets": [
      ["BTC/USDT", "1h"], ["BTC/USDT", "4h"],
      ["ETH/USDT", "1h"], ["ETH/USDT", "4h"],
      ["SOL/USDT", "1h"], ["SOL/USDT", "4h"]
    ],
    "windows": {
      "is": ["2025-06-10", "2026-01-01"],
      "oos": ["2026-01-01", null]
    }
  },
  "entries": []
}
```

Unknown `schema_version` or missing required root keys → refuse to load.
Do not repair in place.

### Entry fields

Required:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable slug, e.g. `mean_reversion.spot.m5.2026-06-12` |
| `name` | string | Registry strategy name |
| `version` | string | Candidate version (`defaults`, `v2`, …) |
| `family` | string | Query key (`mean_reversion`, `trend`, `squeeze`, `breakout`, `cloud`, …) |
| `core_idea` | string | 1–2 sentences |
| `status` | enum | `killed` \| `salvage` \| `incomplete` \| `survived` \| `open` |
| `failure_reason` | string | Exact reason, or `"survived"` |
| `regime_or_period` | string | Window + datasets + direction, human-readable |
| `metrics` | object | Harness numbers (see below) |
| `lesson` | string | Precise, actionable |
| `date` | string | ISO date `YYYY-MM-DD` |
| `harness` | enum | `m1` \| `m5` \| `m2` \| `m3` \| `documented` |
| `verdict` | enum | `deprecate` \| `graduate_m1` \| `healthy` \| `unscreened_short` \| `no_trades` \| `m1_fail` \| `m1_pass` \| `liquidated` \| `documented` |
| `source` | string | Artifact path and/or issue (`docs/research/fee-audit-m5.md`, `#983`, …) |

Optional:

| Field | Type | Meaning |
|---|---|---|
| `supersedes` | string | On the **new** entry: `id` of the earlier entry this one replaces |
| `superseded_by` | string | On the **old** entry: `id` of the replacement. Stamped by `append_entry`; callers must not set it on a new row. |
| `direction` | string | `long` \| `short` \| `both` |
| `registry` | string | `spot` \| `futures` |
| `window` | string | `is` \| `oos` \| `is+oos` \| `audit_continuous` |
| `issue` | string | GitHub issue id |

`metrics` is a JSON object. Copy harness keys; do not rename. M5 rows use
`mean_net_ret`, `mean_gross_ret`, `net_sharpe` (if present), `trades`,
`trades_per_year`, `fee_drag_pp`. M1 window scores use `mean_sharpe`,
`mean_bar_sharpe`, `mean_ddadj`, `mean_bar_ddadj`, `verdict`,
`scored_datasets`. Missing keys are allowed; inventing numbers is not.

### Uniqueness and supersede

Duplicate key: `(name, registry, harness, window, direction, version)`.
`registry` missing is treated as `""` so documented issue write-ups do not
collide with an M5 row of the same `name`. This is required because M5 can
emit the same strategy on both `spot` and `futures` (e.g. `momentum`).

- Append with a duplicate key → reject, exit non-zero, no write (`version` is part of the key, so a real supersede already differs).
- Append with `supersedes: "<old_id>"` requires `old_id` exists, `version` **differs**, and the old entry is not already superseded. The old entry is **not deleted**; `append_entry` stamps `superseded_by` to the new `id` (failure reason / metrics / status stay).
- `relevant()` still returns the old row with `obsolete: true` and `superseded_by` set (stored pointer, or computed from a later row's `supersedes` if the stamp is missing).

`id` values must be unique. Collision → reject.

### `relevant(family=...)`

Returns entries whose `family` matches, including obsolete ones, ordered by
`date` then `id`. Status filter is optional. This is the list the generator
and critic must read before proposing or evaluating anything in that family.

## 6. Critic rules (code, not prompts)

Implemented in `agents/critic.py`. Do not re-derive salvage math — M5 JSON
rows already contain `verdict` (from `salvage_verdict()`). Map it:

| Input | Graph `status` | Graph `verdict` |
|---|---|---|
| M5 row `verdict` `deprecate` | `killed` | `deprecate` |
| M5 row `verdict` `graduate_m1` | `salvage` | `graduate_m1` |
| M5 row `verdict` `unscreened_short` | `incomplete` | `unscreened_short` |
| M5 row `verdict` `no_trades` | `incomplete` | `no_trades` |
| M5 row `verdict` `healthy` | `survived` | `healthy` |
| M1 window_score `verdict` `fail` | `killed` | `m1_fail` |
| M1 window_score `verdict` `pass` | `survived` | `m1_pass` |
| M1 window_score `verdict` `degenerate` | `killed` | `m1_fail` |
| M1 window_score `verdict` `no data` | refuse ingest (exit non-zero, no write) | — |
| `#1005` `liquidated` on a payload | `killed` | `liquidated` |
| Seeded issue write-up (#983, #997) | `killed` | `documented` |

`liquidated` wins over any other verdict on the same payload.

`ingest-m1` writes **one graph entry per window** in `window_scores` (uniqueness
`window` is `is` / `oos` / held-out name). An OOS `fail` is the protocol kill;
an IS `fail` is still recorded as `killed` for that window so it cannot be
forgotten. If `window_scores` is missing or empty, refuse ingest.

`ingest-m5` default writes rows whose `verdict` is `deprecate`, `graduate_m1`,
`healthy`, or that carry `liquidated`. It skips `unscreened_short` / `no_trades`
unless `--include-incomplete` is set (status `incomplete`, not a kill). The
curated seed hand-includes only `mean_reversion_pro` as incomplete.

## 7. Data flow

```
eval_windows.py --json FILE   ──ingest-m1──▶  critic.map_m1  ──append──▶ hypothesis_graph.json
fee_audit.py     --json FILE  ──ingest-m5──▶  critic.map_m5  ──append──▶ hypothesis_graph.json
loop_controller run-m1        ──subprocess──▶ eval_windows.py --json experiments/<run>/m1.json
                                             ──ingest-m1──▶ graph  (only if subprocess exit 0 and JSON parses)
```

Writes use temp-file + atomic rename. A crash must not leave truncated JSON.

`run-m1` flag surface is a thin pass-through of the existing
`eval_windows.py` CLI (`--strategy`, `--registry`, `--direction`, `--windows`,
`--params`). It must not invent new window dates.

On subprocess non-zero, timeout, or JSON that fails critic parse: print the
error, exit non-zero, **do not append**, **do not** leave a partial
`experiments/` tree that looks like a successful cycle (a failed run dir is
allowed only if clearly named `*.failed` or deleted — prefer delete / not
create). Implementation choice: do not create the experiments dir until the
harness returns 0.

CLI commands:

```text
uv run --no-sync python -m agents.loop_controller status
uv run --no-sync python -m agents.loop_controller relevant --family mean_reversion
uv run --no-sync python -m agents.loop_controller ingest-m5 --json PATH
uv run --no-sync python -m agents.loop_controller ingest-m1 --json PATH
uv run --no-sync python -m agents.loop_controller run-m1 --strategy NAME [--registry spot|futures] [--direction long|short] [--windows oos]
```

`status` prints entry counts by `status` and `family`, plus `updated`.
`generator.py` / `post_mortem.py` expose `require_graph()` and raise
`NotImplementedError` on any “propose strategy” / “write production lesson
without ingest” call.

## 8. Curated seed (checked in with the JSON file)

Provenance: `docs/research/fee-audit-m5.md` (generated 2026-06-12),
`backtest/candidates/squeeze_983/`, `backtest/candidates/ichimoku_997/`.
Copy numbers from those artifacts; do not re-run the full M5 screen to seed.

Include:

1. **Every M5 `deprecate` row** as its own `killed`/`deprecate` entry
   (`registry` from the table; `window` `is+oos`; `direction` `long`;
   `harness` `m5`; `date` `2026-06-12`).
2. **Every M5 `graduate_m1` row** as `salvage`/`graduate_m1` with lesson
   “gross edge exists; raise selectivity (fewer trades) before any live
   consideration.”
3. **Documented #983** (`squeeze_momentum`, family `squeeze`, `harness`
   `documented`, `date` `2026-06-12`, `source`
   `backtest/candidates/squeeze_983/README.md`): 25-stack close sweep did not
   cut −58.5% DD without losing the +47.9pt vs-B&H edge; DD is regime
   exposure; persistent long/flat entries re-enter next bar after stop-out
   (fee churn); holding-structure changes must be re-run on the continuous
   audit window.
4. **Documented #997** (`ichimoku_cloud`, family `cloud`, `harness`
   `documented`, `date` `2026-06-12`, `source`
   `backtest/candidates/ichimoku_997/README.md`): M3 knobs fail OOS on every
   tried stop/time/zscore combo (late giveback dominates).
5. **`mean_reversion_pro` spot M5 `unscreened_short`** as `incomplete`:
   long-leg net −3.13% over 18 trades is **not** a kill; short leg unmeasured.
   Naive `mean_reversion` remains the family kill (`deprecate`).

Seed `regime_or_period` for M5 rows:

`IS 2025-06-10→2026-01-01 + OOS 2026-01-01→latest; BTC/ETH/SOL 1h+4h; direction=long`

Family tags for seed (deterministic):

| Family | Names |
|---|---|
| `mean_reversion` | `mean_reversion`, `mean_reversion_pro`, `vwap_reversion`, `bollinger_bands`, `pairs_spread` |
| `trend` | `macd`, `ema_crossover`, `triple_ema`, `supertrend`, `sma_crossover`, `tema_cross`, `adx_trend`, `momentum`, `parabolic_sar`, `heikin_ashi_ema`, `stoch_rsi`, `rsi`, `rsi_macd_combo`, `volume_weighted` |
| `breakout` | `atr_breakout`, `breakout` |
| `squeeze` | `squeeze_momentum`, `sweep_squeeze_combo` |
| `cloud` | `ichimoku_cloud` |
| `range` | `range_scalper`, `order_blocks` |
| `regime` | `regime_adaptive`, `regime_adaptive_htf` |
| `misc` | anything else in the deprecate list not covered above (`amd_ifvg`, `mtf_confluence`, `vol_momentum`, …) |

## 9. Error handling

| Condition | Behavior |
|---|---|
| Missing required field / bad enum | Refuse write, exit non-zero |
| Duplicate key | Refuse write, exit non-zero |
| `supersedes` id missing, `version` unchanged, or target already superseded | Refuse write, exit non-zero |
| New entry sets `superseded_by` | Refuse write, exit non-zero |
| Unknown `schema_version` / corrupt JSON | Refuse load, exit non-zero |
| Ingest file missing or not JSON | Refuse write, exit non-zero |
| `run-m1` non-zero, timeout, or unparsable JSON | Exit non-zero, graph byte-identical |
| Concurrent writers | Last atomic rename wins; no locking this increment (single operator CLI) |

## 10. Tests (no market data, no real harness spawn)

Fixtures are tiny synthetic JSON, not production audit dumps.

1. **Schema:** required fields; reject duplicate; accept `supersedes` with new
   `version`; stamp `superseded_by` on the old id; `relevant()` returns old id as
   obsolete; reject a second supersede of the same target; `id` unique.
2. **Critic:** fixture rows map deprecate / graduate_m1 / unscreened_short /
   healthy / liquidated / m1_fail / m1_pass to section 6.
3. **Ingest:** `ingest-m5` from a fixture appends; file after a simulated
   `run-m1` failure is byte-identical to before.
4. **Relevant:** `--family mean_reversion` includes naive `mean_reversion`
   kill and `mean_reversion_pro` incomplete, and does not drop obsolete
   entries.

## 11. Out of scope (later sub-projects)

- `generator.py` emitting new `@register` strategy code
- `post_mortem.py` reading live trade logs / Discord
- `run-m5` (full-registry fee audit is expensive; ingest existing JSON)
- Paper/live deploy, kill-switch changes, US equities
- Changing M1 windows, incumbents, or fee model
- Auto-loop / cron; this CLI is operator-invoked

## 12. Success criteria

- `hypothesis_graph.json` is in git with the curated seed.
- `relevant --family mean_reversion` shows the naive deprecate kill and the
  pro incomplete short-leg note.
- A failed `run-m1` cannot alter the graph.
- `pytest` discovers `agents/`.
- No production strategy, backtester, or scheduler file changes except
  `pyproject.toml` `testpaths`.
