# Scout click alerts on Mini

**Date:** 2026-09-17
**Status:** Approved design. No code until the human says **implement scout alerts**.
**Scope:** Optional `--alert` / `--speak` / `--no-sound` on existing `northstar practice scout`. Fire only on a `SCOUT CLICK`. Mini desk. Never sends.

## 1. Goal

When Mini is running scout and a real YES click prints, ping the human (chime + banner, optional speech) so they can send `$2` themselves. Grok overnight stays quiet unless those flags are passed.

Not a new command. Not phone push. Not auto-send.

## 2. Locked fences

- Helper still must not run `kalshi-live`, halt, resume, paper book, or paper settle.
- Default CONTINUE / overnight command stays `uv run northstar practice scout --hours 6` (no `--alert`).
- Click filter, hours 1–8, opens-only, no `--save`, no `--both` stay unchanged.
- Generator stubbed. Graph stop. Walk math unchanged.
- Alerts are best-effort: never raise into the scout loop.

## 3. Flags (same shape as `kalshi-dry`)

```bash
uv run northstar practice scout --hours 6 --alert --speak
```

| Flag | Rule |
| --- | --- |
| `--alert` | Glass chime + Notification Center on click only |
| `--speak` | Implies `--alert`. Speaks the click line |
| `--no-sound` | With `--alert`, mute chime; banner stays; speech stays if `--speak` |

Defaults off. Start line, end line, skips, 429s: **no** alert.

## 4. Payload

Reuse `AlertConfig` + `fire()` in `src/poly/alerts.py`. Do not add a new alert backend.

- Title: `SCOUT CLICK`
- Banner message: `{ticker} YES {yes:.2f} edge {edge:+.2f}`
- Spoken (if `--speak`): `Scout click {asset} YES {cents} cents, edge plus {edge:.2f}.` Negative edge cannot be a click; do not invent “minus.”
- Cents in speech are the YES ask in whole cents (0.44 → `44`).

Wire in `practice_scout` `on_click` after the header/panel print. `run_scout` stays free of `afplay`/`say`.

## 5. Tests and docs

- Skip / leftover / 429 → `fire` not called (inject a fake `fire` or count).
- Click + `--alert` → `fire` once with sound+notification, speech empty unless `--speak`.
- `--speak` without `--alert` → still alerts (implies `--alert`).
- `--hours 0` → refuse, no loop, no fire.
- CHEATSHEET: Mini scout line with `--alert --speak`.
- GROK_BOT: optional flags listed; default allowlist command unchanged.

## 6. What this will not build

- ntfy / SMS / email
- Always-on speech with no flags
- `--open` browser
- Alerts on Grok as a required overnight behavior
- Changing the click filter
