# Scout auto-fill live book line

**Date:** 2026-09-17
**Status:** Approved design. No code until the human says **implement scout autofill**.
**Scope:** On every `SCOUT CLICK`, print a Mini-only `kalshi-live book` paste line. Scout does not send. Helper must not run the line.

## 1. Goal

After a real YES click print, both lookers show a copy-paste command with ticker / YES / NO / edge / spend filled in. The human runs it on Mini with env already set. No auto-trade. No `--last`. No `--both`.

## 2. Locked fences

- Helper allowlist still has **no** `kalshi-live`. Section 5: if scout prints `kalshi-live book`, do **not** execute it.
- Scout does not call `attempt_live_book` or `signed_create_order`.
- Click filter, hours, opens-only, `--save` absent, `--alert` unchanged.
- Generator stubbed. Graph stop. Halt/PEM Mini-only.
- Dead windows never print a book line because they are not clicks.

## 3. Copy (exact)

Warning line:

`Run this on Mini. Helper must not run kalshi-live.`

Command (one line, `uv run`):

`uv run northstar kalshi-live book --ticker {ticker} --side yes --spend {spend} --yes-price {yes:.2f} --no-price {no:.2f} --edge {edge:+.2f} --i-approve-live`

- `--side yes` always (YES one-side scout).
- `{spend}` is scout `--spend` after walk clamp (default 2). Whole dollars print as `2`; otherwise two decimals (e.g. `2.50`).
- `{edge}` is the numeric click edge (already ≥ +0.03).
- No `export` lines. No `--both`. No `--last`. No `--i-approve-not-ready`.

Print **after** the walk panel and **before** `--alert` fire. Skip / 429 / start / end: do not print these two lines.

## 4. Where it lives

| Path | Role |
| --- | --- |
| `src/poly/practice/scout.py` | `SCOUT_BOOK_WARNING`, `format_scout_book_command(quote, spend)` |
| `src/poly/cli.py` `on_click` | Print warning then command |
| `docs/GROK_BOT.md` | Forbid running the printed book line |
| `docs/CHEATSHEET.md` | Mini pastes the printed command |
| `tests/test_scout.py` | Click has both lines; skip does not; no live send symbols |

`run_scout` stays free of Kalshi POST.

## 5. Tests

- Leftover / skip / 429 → `kalshi-live` not in printed on_click output (on_click not called).
- Click at YES 0.38 edge +0.07 spend 2 → command contains that ticker, `--yes-price 0.38`, `--edge +0.07`, `--spend 2`, `--i-approve-live`, and does not contain `--both` or `--last`.
- CONTINUE / GROK_BOT section 4 still omit `kalshi-live`.
- `src/poly/practice/scout.py` and `practice_scout` still omit `attempt_live_book` / `signed_create_order`.

## 6. What this will not build

- Auto-send, env-var printing, `--last` on live book, Grok executing the line, filling OVER tickers, `--both`
