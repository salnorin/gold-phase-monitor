#!/usr/bin/env bash
# نسخه‌های مستقل ارگانیسم طلا روی Termux/لینوکس، هر کدام با دیتا و پورت خودش، داخل tmux.
#   ./scripts/clone_gold.sh gold-a gold-b      # ساخت/اجرا (پورت‌ها از 5001)
#   ./scripts/clone_gold.sh list               # فهرست
#   ./scripts/clone_gold.sh stop               # توقف همه (دیتا حذف نمی‌شود)
# نیاز: pkg install tmux
set -euo pipefail
SESSION="${GOLD_SESSION:-gold}"
BASE="${GOLD_BASE:-$HOME/.local/share/gold-phase-monitor}"
PORT0="${GOLD_PORT0:-5001}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python}"
command -v "$PY" >/dev/null || PY=python3

need_tmux() { command -v tmux >/dev/null || { echo "tmux not found: pkg install tmux" >&2; exit 1; }; }

case "${1:-}" in
  ""|-h|--help) sed -n '2,7p' "$0"; exit 0 ;;
  stop) need_tmux; tmux kill-session -t "$SESSION" 2>/dev/null && echo "stopped '$SESSION'" || echo "no session '$SESSION'"; exit 0 ;;
  list)
    for f in "$BASE"/*/port; do [ -f "$f" ] || continue; d="$(dirname "$f")"
      echo "$(basename "$d")  http://127.0.0.1:$(cat "$f")  db=$d/live_account_gold.sqlite"; done
    command -v tmux >/dev/null && tmux list-windows -t "$SESSION" 2>/dev/null || echo "(session '$SESSION' not running)"
    exit 0 ;;
esac

need_tmux
used=" "
for f in "$BASE"/*/port; do [ -f "$f" ] && used+="$(cat "$f") "; done
next=$PORT0
for name in "$@"; do
  [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad name: $name" >&2; exit 1; }
  dir="$BASE/$name"; mkdir -p "$dir"
  if [ -f "$dir/port" ]; then port="$(cat "$dir/port")"
  else while [[ "$used" == *" $next "* ]]; do next=$((next+1)); done
       port=$next; echo "$port" > "$dir/port"; used+="$port "; fi
  db="$dir/live_account_gold.sqlite"
  rec="cd '$REPO' && GPM_DATA_DIR='$dir' $PY -m core.recorder --data-dir '$dir'"
  dash="cd '$REPO' && $PY -m dashboard_lite --db '$db' --port $port"
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux new-session -d -s "$SESSION" -n "$name-rec" "$rec"
  elif tmux list-windows -t "$SESSION" -F '#W' | grep -qx "$name-rec"; then
    echo "$name already running"; continue
  else tmux new-window -t "$SESSION" -n "$name-rec" "$rec"; fi
  tmux new-window -t "$SESSION" -n "$name-web" "$dash"
  echo "$name  ->  http://127.0.0.1:$port   data=$dir"
done
echo "attach: tmux attach -t $SESSION   (detach: Ctrl+B then D)"
