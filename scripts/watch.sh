#!/usr/bin/env bash
# Keep watching the market and alerting on Telegram.
#
#   export TELEGRAM_BOT_TOKEN="123456789:AAF..."
#   export TELEGRAM_CHAT_ID="987654321"
#   bash scripts/watch.sh
#
# Paper only: this never sends an order to a broker.

set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source .venv/bin/activate

INTERVAL="${INTERVAL:-300}"
RETRAIN="${RETRAIN:-500}"

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    echo "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - alerts will print here."
fi

exec python -m forexai monitor --interval "$INTERVAL" --retrain-every "$RETRAIN" --telegram
