# Scout Autofill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On SCOUT CLICK, print a Mini paste line for `kalshi-live book`. Do not send. Helper must not run it.

**Architecture:** `format_scout_book_command` + `SCOUT_BOOK_WARNING` in `scout.py`. CLI `on_click` prints warning then command after the walk panel and before `--alert`. No POST.

**Tech Stack:** Existing Typer scout command.

**Spec:** `docs/superpowers/specs/2026-09-17-scout-autofill-design.md`

## Global Constraints

- Allowlist has no `kalshi-live`. Scout does not call `attempt_live_book` / `signed_create_order`.
- `--side yes`, no `--both`, no `--last`, no env in the paste.
- Click filter unchanged.

Do not commit unless asked. Run `uv run pytest tests/test_scout.py tests/test_status.py -q`.
