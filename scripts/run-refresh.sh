#!/bin/bash
# Unattended refresh of open loops (launchd, weekdays) - macOS equivalent of run-refresh.ps1.
# launchd agents get PATH=/usr/bin:/bin:/usr/sbin:/sbin - claude would never be found without this.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LOG_DIR="$ROOT/state/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/runner-$(date +%Y-%m-%d).log"

DOW=$(date +%u)  # 1=Monday .. 7=Sunday
if [ "$DOW" -ge 6 ]; then
    echo "weekend - skipped" >> "$LOG"
    exit 0
fi

echo "=== refresh $(date +%H:%M:%S)" >> "$LOG"
python3 refresh.py >> "$LOG" 2>&1
echo "refresh exit $?" >> "$LOG"

# --- timer-driven chasing (no-op unless auto_chase.enabled in config.json) ---
echo "=== autochase $(date +%H:%M:%S)" >> "$LOG"
python3 autochase.py >> "$LOG" 2>&1
exit 0
