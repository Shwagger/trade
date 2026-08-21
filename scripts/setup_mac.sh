#!/usr/bin/env bash
# One command to go from a fresh clone to a finished validation run.
#
#   bash scripts/setup_mac.sh
#
# Written as a script on purpose: pasting a block of commented commands into
# zsh fails with "parse error near ')'", because interactive zsh does not treat
# '#' as a comment. A script file has no such problem.

set -euo pipefail

SYMBOL="${SYMBOL:-EURUSD}"
TIMEFRAME="${TIMEFRAME:-1h}"
YEARS="${YEARS:-2}"
DATA="data/raw/${SYMBOL}_$(echo "$TIMEFRAME" | tr '[:lower:]' '[:upper:]').csv"

cd "$(dirname "$0")/.."

echo "==> python environment"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo "==> tests"
python -m pytest tests/ -q

echo "==> downloading real ${SYMBOL} ${TIMEFRAME} bars"
if python -m forexai fetch --symbol "$SYMBOL" --timeframe "$TIMEFRAME" --years "$YEARS"; then
    SOURCE_ARGS=(--source csv --path "$DATA")
else
    echo
    echo "Download failed. Falling back to synthetic bars so you can still see"
    echo "the pipeline run end to end. Put a broker export in data/raw/ and"
    echo "re-run to validate anything real."
    SOURCE_ARGS=(--source synthetic --bars 30000)
fi

echo "==> walk-forward validation"
python -m forexai walkforward "${SOURCE_ARGS[@]}" || true

echo
echo "==> done. Artefacts are in runs/"
echo "    next:  source .venv/bin/activate"
echo "           python -m forexai search --n 4000 --jobs 4"
echo "           python -m forexai train ${SOURCE_ARGS[*]}"
echo "           python -m forexai monitor --interval 300 --telegram"
