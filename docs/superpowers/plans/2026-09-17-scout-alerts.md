# Scout Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mini `practice scout --alert --speak` chimes, banners, and speaks only on a SCOUT CLICK. Never sends.

**Architecture:** Keep `run_scout` free of `afplay`/`say`. Add payload helpers plus `alert_scout_click` in `scout.py` that calls existing `fire()`. CLI matches `kalshi-dry` flags and fires from `on_click` after the walk panel.

**Tech Stack:** Existing `AlertConfig` / `fire` in `src/poly/alerts.py`. Typer flags.

**Spec:** `docs/superpowers/specs/2026-09-17-scout-alerts-design.md`

## Global Constraints

- Default overnight command stays `uv run northstar practice scout --hours 6` (no `--alert`).
- Helper must not gain `kalshi-live`.
- Click filter and hours refuse unchanged.
- Alerts best-effort; `fire` already never raises into the loop.
- No ntfy, `--open`, or always-on speech.

## File map

| Path | Responsibility |
| --- | --- |
| `src/poly/practice/scout.py` | Alert copy, `scout_alert_config`, `alert_scout_click` |
| `src/poly/cli.py` | `--alert` `--speak` `--no-sound` on `practice scout` |
| `tests/test_scout.py` | Fire on click only; speak implies alert; hours 0 no fire |
| `docs/CHEATSHEET.md` | Mini `--alert --speak` line |
| `docs/GROK_BOT.md` | Optional flags; default allowlist unchanged |

---

### Task 1: Alert payload helpers (TDD)

`format_scout_alert_message(quote) -> str` = `{ticker} YES {yes:.2f} edge {edge:+.2f}`

`format_scout_spoken(quote) -> str` = `Scout click {asset} YES {cents} cents, edge plus {edge:.2f}.` with cents = `round(yes_price * 100)`.

`scout_alert_config(alert, speak, no_sound) -> Optional[AlertConfig]`: None if both flags off; `--speak` implies alert; sound = not no_sound.

`alert_scout_click(config, quote, fire_fn=fire)`: title `SCOUT CLICK`; spoken only if `config.speech`.

### Task 2: CLI + docs

Wire flags like `kalshi-dry`. `on_click` prints then `alert_scout_click` if config. Tests: leftover skip does not fire; click+alert fires once speech empty; speak without alert still fires with speech; hours 0 no fire; CONTINUE has no `--alert`; GROK_BOT default command unchanged.

Do not commit unless the human asks. Run `uv run pytest tests/test_scout.py tests/test_status.py -q`.
