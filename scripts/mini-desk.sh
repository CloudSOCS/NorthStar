#!/usr/bin/env bash
# Mini desk loop: scout + alert + speak + Approve dialog for live book.
# Helper / Grok must not run this. Human APPROVE still required per click.
set -euo pipefail
cd "$(dirname "$0")/.."

export POLY_MODE="${POLY_MODE:-live}"
export KALSHI_PRIVATE_KEY_PATH="${KALSHI_PRIVATE_KEY_PATH:-/Volumes/App/Kalshi-k/kalshi_private.pem}"

if [[ -z "${KALSHI_API_KEY:-}" ]]; then
  echo "Set KALSHI_API_KEY in this shell first (do not commit it)."
  exit 1
fi

if [[ ! -f "$KALSHI_PRIVATE_KEY_PATH" ]]; then
  echo "PEM not found: $KALSHI_PRIVATE_KEY_PATH"
  exit 1
fi

echo "Mini desk · PEM=$KALSHI_PRIVATE_KEY_PATH · POLY_MODE=$POLY_MODE"
exec uv run northstar practice scout --hours "${1:-6}" --alert --speak --offer-live
