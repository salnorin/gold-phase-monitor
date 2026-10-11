#!/usr/bin/env bash
# Run the dashboard (Linux / macOS). Paper trading only.
set -eu
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || scripts/setup.sh
exec .venv/bin/python -m streamlit run app.py "$@"
