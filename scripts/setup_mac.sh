#!/usr/bin/env bash
# From a fresh clone to seeing the bot work, in one command.
#
#   git clone https://github.com/Shwagger/trade.git
#   cd trade
#   bash scripts/setup_mac.sh
#
# It is a script rather than a list of commands to paste because interactive
# zsh does not treat '#' as a comment: pasting a commented block fails with
# "parse error near ')'".

set -uo pipefail

SYMBOL="${SYMBOL:-EURUSD}"
TIMEFRAME="${TIMEFRAME:-1h}"
YEARS="${YEARS:-2}"

cd "$(dirname "$0")/.." || exit 1

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
die() { printf '\n\033[31m!! %s\033[0m\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------- python
say "looking for python 3"
PY=""
for candidate in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
        case "$version" in
            3.9|3.1[0-9]) PY="$candidate"; break ;;
        esac
    fi
done

if [ -z "$PY" ]; then
    die "no usable python 3 found.

macOS does not ship one by default. Install Apple's command line tools:

    xcode-select --install

Accept the dialog, wait for it to finish, then run this script again.
If that does not work, install Homebrew from https://brew.sh and then:

    brew install python@3.12"
fi
echo "    using $PY ($("$PY" --version 2>&1))"

# ---------------------------------------------------------------- env
say "creating the virtual environment"
if [ ! -d .venv ]; then
    "$PY" -m venv .venv || die "could not create .venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate || die "could not activate .venv"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt || die "dependency install failed"
echo "    ready: $(python --version 2>&1)"

# ---------------------------------------------------------------- tests
say "running the test suite (about a minute)"
python -m pytest tests/ -q || die "tests failed - stopping before trusting any number"

# ---------------------------------------------------------------- data
say "downloading real $SYMBOL $TIMEFRAME bars"
DATA="data/raw/${SYMBOL}_$(printf '%s' "$TIMEFRAME" | tr '[:lower:]' '[:upper:]').csv"
if python -m forexai fetch --symbol "$SYMBOL" --timeframe "$TIMEFRAME" --years "$YEARS"; then
    SOURCE=(--source csv --path "$DATA")
    REAL=1
else
    printf '\n\033[33m    download failed. Falling back to synthetic bars so you can still
    watch the whole pipeline run. Nothing below validates an edge until
    real bars are in place.\033[0m\n'
    SOURCE=(--source synthetic --bars 30000)
    REAL=0
fi

# ---------------------------------------------------------------- run
say "walk-forward validation (out-of-sample)"
python -m forexai walkforward "${SOURCE[@]}"

say "training the model on everything available"
python -m forexai train "${SOURCE[@]}" || die "training failed"

say "the decision on the last closed bar - this is what an alert looks like"
python -m forexai signal "${SOURCE[@]}"

say "replaying recent bars so you can see trades being taken"
python -m forexai paper "${SOURCE[@]}" --window 800

# ---------------------------------------------------------------- next
printf '\n\033[1m==> done.\033[0m Artefacts are in runs/\n\n'
echo "Every command below needs the environment active first:"
echo
echo "    source .venv/bin/activate"
echo
echo "Watch the market and get alerts (paper only, never sends an order):"
echo "    python -m forexai monitor --interval 300 --telegram"
echo
echo "Sweep thousands of strategies out of the 700-million space:"
echo "    python -m forexai search --n 4000 --jobs 4"
echo
if [ "$REAL" = "0" ]; then
    echo "You are still on synthetic data. Get real bars with:"
    echo "    python -m forexai fetch --symbol EURUSD --timeframe 1h --years 2"
    echo
fi
