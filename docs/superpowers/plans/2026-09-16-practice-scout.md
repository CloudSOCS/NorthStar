# Practice Scout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only `northstar practice scout --hours 6` that waits for Kalshi 15m opens and prints Steps 1–4 only on a real YES click.

**Architecture:** New `src/poly/practice/scout.py` owns clock, click filter, and the injectable loop. It reuses `load_walk_quote`, `format_walk`, and `last_walk_window`. CLI prints start/end and a walk panel on click. Helper allowlist gains scout only.

**Tech Stack:** Existing Typer CLI, `httpx` for 429 detection, `zoneinfo` America/New_York via `VENUE_TZ`.

**Spec:** `docs/superpowers/specs/2026-09-16-practice-scout-design.md`

## Global Constraints

- Helper gains `practice scout`. Helper must not gain `kalshi-live`, halt, resume, paper book, or paper settle.
- No live order. No PEM. No `--save`. No `--demo`. No `--both`.
- Scout does not write walk journal or paper positions.
- `MIN_EDGE_TO_CARE` stays 0.03 in walk.py; scout reads it.
- Generator stubbed. Graph stop. `execution/live.py` unwired.
- Clock and 429 tests use fakes. No live Kalshi in CI.

## File map

| Path | Responsibility |
| --- | --- |
| `src/poly/practice/scout.py` | Hours refuse, next-open clock, `is_scout_click`, `run_scout` |
| `src/poly/cli.py` | `practice scout` command |
| `src/poly/practice/orientation.py` | CONTINUE line |
| `docs/GROK_BOT.md` | Allowlist |
| `docs/CHEATSHEET.md` | Scout block |
| `tests/test_scout.py` | Filter, clock, hours, 429, CLI, allowlist |
| `tests/test_status.py` | CONTINUE list includes scout |

---

### Task 1: Click filter + hours refuse + next-open clock

**Files:**
- Create: `tests/test_scout.py`
- Create: `src/poly/practice/scout.py`

**Interfaces:**
- Produces: `HOURS_REFUSE`, `scout_hours_refuse(hours: int) -> Optional[str]`, `is_scout_click(quote, now=None) -> bool`, `next_scout_wake(now) -> datetime`, `OPEN_GRACE_SECONDS=90`, `POST_OPEN_DELAY_SECONDS=5`

TDD: leftover / closing / over / tiny / negative / not-ready skip; 38¢ +0.07 live clicks; hours 0 and 9 refuse; wake within 90s of open vs mid-window.

### Task 2: Loop with fakes (one walk per window, 429 retry then skip)

**Files:**
- Modify: `src/poly/practice/scout.py`
- Modify: `tests/test_scout.py`

**Interfaces:**
- Produces: `ScoutCounts`, `format_scout_start`, `format_scout_end`, `format_scout_click_header`, `run_scout(*, hours, asset, spend, now_fn, sleep_fn, load_fn, on_click) -> ScoutCounts`

After a window is handled, sleep until the **next** open (do not re-walk grace). 429: wait `WALK_RATE_LIMIT_WAIT` once, retry once, then skip and increment `rate_limits`. None quote → skip. Deadline: do not start a sleep that ends after `now + hours`.

### Task 3: CLI + allowlist + docs

**Files:**
- Modify: `src/poly/cli.py`
- Modify: `src/poly/practice/orientation.py`
- Modify: `docs/GROK_BOT.md`
- Modify: `docs/CHEATSHEET.md`
- Modify: `tests/test_status.py`
- Modify: `tests/test_scout.py`

Command: `practice scout --hours` default 6, `--asset` BTC, `--spend` default 2. No `--save`/`--demo`. Hours refuse exit 1. Inspect scout CLI source: no `attempt_live_book` / `signed_create_order`. CONTINUE and GROK_BOT section 4 include `uv run northstar practice scout --hours 6` and still omit `kalshi-live`.

---

Do not commit per task unless the human asks. After Task 3 run `uv run pytest tests/test_scout.py tests/test_status.py tests/test_kalshi_live.py -q`.
