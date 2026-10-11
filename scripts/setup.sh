#!/usr/bin/env bash
# Setup (Linux / macOS, bash or zsh). Creates .venv and installs dependencies.
set -eu
cd "$(dirname "$0")/.."
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "Python 3.11+ not found (macOS: brew install python@3.11)"; exit 1; }
"$PY" -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
echo "OK. Run: scripts/run.sh   (tests: .venv/bin/python -m pytest -q)"
