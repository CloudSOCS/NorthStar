# Practice scout loop — Grok Bot looker

**Date:** 2026-09-16
**Status:** Approved design. No code until the human says **implement scout**.
**Scope:** Read-only `northstar practice scout` that waits for Kalshi 15m **opens**, walks once per window, and prints the teaching panel **only** on a one-side YES click. Helper allowlist. Never sends.

## 1. Goal

Replace the hand-run “Walk Mini every 5 minutes” hunt with one Grok Bot command for a 6-hour day. Same walk fetch and Steps 1–4 voice as `practice walk`. Filter leftover / CLOSING / OVER / tiny-or-negative edge in code so the helper does not have to remember the rule.

Not a new trading seat. Not SEARCH / SNIPER / EXIT. Not `kalshi-dry`. Not `kalshi-live`.

## 2. Locked fences

- Helper **gains** `practice scout` on the allowlist. Helper **must not** gain `kalshi-live`, halt, resume, paper book, or paper settle.
- No live order. No PEM. No `--i-approve-live`. No `--both`. No `--save`.
- Generator stays stubbed. Graph command stays stop. `execution/live.py` stays unwired.
- Two notebooks stay unmixed: scout does not write Mini `~/.poly/` or the bot walk journal.
- Halt file and Kalshi PEM stay Mini-only.
- Walk math, one-side paper P&L formulas, and `MIN_EDGE_TO_CARE` (0.03) stay unchanged. Scout **reads** that constant; it does not change walk.

## 3. Command

```bash
uv run northstar practice scout
uv run northstar practice scout --hours 6
uv run northstar practice scout --asset BTC --hours 6
```

| Flag | Rule |
| --- | --- |
| `--hours` | Optional. Default **6**. Integer **1–8** inclusive. Outside that range → refuse, print one line, exit 1, no sleep, no fetch. |
| `--asset` | Optional. Default **BTC**. Same as `practice walk`. |
| `--spend` | Optional. Default **$2**, same clamp as walk (printed Step 2 only). Not a send size. |
| `--save` | **Absent.** Do not add it. |
| `--demo` | **Absent.** Scout is live Kalshi only. |

Footer on every printed walk panel: `This is practice only — no live order was placed.`

## 4. Where it lives

| Path | Role |
| --- | --- |
| `src/poly/practice/scout.py` | Next-open clock, click filter, loop, 429 skip. No HTTP except through `load_walk_quote`. |
| `src/poly/practice/walk.py` | Unchanged fetch + `format_walk` + `last_walk_window`. Scout imports; does not fork the panel. |
| `src/poly/cli.py` | `practice scout` command. |
| `src/poly/practice/orientation.py` `CONTINUE` | Add `uv run northstar practice scout --hours 6`. Still no `kalshi-live`. |
| `docs/GROK_BOT.md` section 4 | Same command on the allowlist. Section 5 still forbids live / paper book / settle. |
| `docs/CHEATSHEET.md` | One short scout block. |
| `tests/test_scout.py` | Filter, hours refuse, 429 skip, allowlist. |

`src/poly/clients/kalshi.py` stays unsigned GET. Do not add a scout client.

## 5. Timing (venue America/New_York)

Windows are `:00` / `:15` / `:30` / `:45`.

Constants (exact):

- `OPEN_GRACE_SECONDS = 90` — if `now` is within 90 seconds after the current window open, walk **this** window (just opened).
- `POST_OPEN_DELAY_SECONDS = 5` — after sleeping to an open, wait 5 more seconds so the book exists.
- Otherwise sleep until the **next** open + 5 seconds. Do **not** walk mid-window leftover.

One walk per window, then sleep again.

Stop when wall-clock `--hours` has elapsed. If a walk is already in flight, finish that walk (print or skip), then exit. Do not start a new sleep that would end after the cap.

**429:** same 10s wait as walk (`WALK_RATE_LIMIT_WAIT`), **one** retry, then skip that window, increment a 429 counter, keep the day going. Do not exit 1 for a single 429.

**No market / fetch error:** skip that window, keep going.

## 6. Click filter (the only walk panel)

Print **only** if all of these are true. Otherwise skip with no Steps 1–4 panel.

1. `last_walk_window` is **`live`** (not `closing`, not `over`, not `unknown`).
2. `edge` is a **number** and `edge >= MIN_EDGE_TO_CARE` (0.03). `None` / `"not ready"` / tiny gap / negative → skip. Do not invent a guess.
3. YES ask is **not leftover:** `yes_price > 0.15` **and** `yes_price < 0.90`.
4. Hedge SKIP does **not** block a print.

On a hit:

- One header line: `SCOUT CLICK` plus ticker, YES price, edge.
- Then the same `format_walk` panel as `practice walk` (live, not demo, not replay).

YES one-side only. No NO scouting. No `--both`.

## 7. Start and end lines

**Start** (always):

`Scout {asset} for {hours} hours. Opens only. Silent except a real click. No order will be placed.`

**End** (always, even zero clicks):

`Scout done. windows={n} clicks={n} skips={n} rate_limits={n}. This is practice only — no live order was placed.`

No per-skip line. No heartbeat every window.

## 8. Tests (must fail closed)

- Leftover YES 0.06 / 0.15 / 0.90 / 1.00 → not a click (even if edge is large).
- Window `closing` or `over` → not a click.
- Edge `None` or `+0.02` or `-0.08` → not a click.
- Live, YES 0.38, edge `+0.07` → click.
- `--hours 0` and `--hours 9` → exit 1, no loop.
- `CONTINUE` / `GROK_BOT.md` section 4 contain `practice scout` and do **not** contain `kalshi-live`.
- Scout module / CLI path does not call `attempt_live_book`, `signed_create_order`, paper book, or paper settle.

Clock and 429 tests use fakes (no live Kalshi required in CI).

## 9. What this will not build

- Auto-send, Mini book, halt/resume, PEM, `--save`, `--demo`, `--alert`, `--speak`, `--open`
- 5-minute polling
- CHEAP PAIR / `--both` as a click reason
- Extra helper seats
- Changing walk P&L or hedge math (`pair_cost < 1.0` stays CHEAP PAIR; `$1.00` stays SKIP)
