#!/bin/bash
# Open Loops - one-click installer for macOS. macOS equivalent of setup.ps1.
#
#   Double-click "Open Loops.command", or from a terminal:
#       bash install.sh
#
# What it does (all on this computer, nothing sent anywhere):
#   1. Checks for Python 3 and Claude Code, offering to install via Homebrew / the official
#      installer if missing.
#   2. Copies Open Loops to ~/Library/Application Support/OpenLoops.
#   3. Puts Open Loops.app (with the logo) on the Desktop and in ~/Applications.
#   4. Sets it to refresh every weekday morning (default 09:15) via launchd.
#   5. Opens the app - which walks you through connecting Slack and email.
set -e

AT="09:15"
NAME=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --at) AT="$2"; shift 2 ;;
        --name) NAME="$2"; shift 2 ;;
        *) shift ;;
    esac
done

say() { echo ""; echo "  $1"; }
ok()  { echo "  [ok] $1"; }

echo ""
echo "  ============================"
echo "   Open Loops - setup"
echo "  ============================"

# ---------- 1. Python ----------
say "Checking Python..."
if ! command -v python3 >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
        say "Installing Python (this can take a minute)..."
        brew install python3
    else
        echo "  Python 3 wasn't found and Homebrew isn't installed." >&2
        echo "  Install Python 3 from https://www.python.org/downloads/ and run this again." >&2
        exit 1
    fi
fi
ok "Python $(python3 --version | sed 's/Python //')"

# ---------- 2. Claude Code ----------
say "Checking Claude..."
if ! command -v claude >/dev/null 2>&1; then
    say "Installing Claude Code (this can take a minute)..."
    if ! curl -fsSL https://claude.ai/install.sh | bash; then
        if command -v brew >/dev/null 2>&1; then
            brew install --cask claude-code || true
        fi
    fi
    export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v claude >/dev/null 2>&1; then
    echo "  Couldn't install Claude automatically. Please install it from https://claude.ai/code and run this again." >&2
    exit 1
fi
ok "Claude is installed"

# ---------- 3. Copy files ----------
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Install into ~/Documents - visible and easy to find (config.json, state.json and state/logs are
# plain files a user may want to open directly), and it works wherever the download was unzipped
# (Downloads, Desktop, a USB stick). The Desktop launcher points here, so the downloaded folder
# can be deleted afterwards.
DEST="$HOME/Documents/OpenLoops"

if [ "$SRC" = "$DEST" ]; then
    say "Already installed here - updating."
else
    say "Installing Open Loops to $DEST ..."
    mkdir -p "$DEST"
    rsync -a --exclude 'state' --exclude 'voice.json' --exclude 'state.json' --exclude 'config.json' \
        --exclude 'people_suggested.json' --exclude '.git' "$SRC"/ "$DEST"/
fi
mkdir -p "$DEST/state/logs"

# fresh state + config unless the person already has them
STATE_FILE="$DEST/state.json"
if [ ! -f "$STATE_FILE" ]; then
    CURSOR=$(python3 -c "from datetime import datetime, timedelta; print((datetime.now().astimezone()-timedelta(days=7)).isoformat(timespec='minutes'))")
    cat > "$STATE_FILE" <<EOF
{
  "cursor": "$CURSOR",
  "last_refresh": null,
  "loops": []
}
EOF
fi
CFG_FILE="$DEST/config.json"
if [ ! -f "$CFG_FILE" ]; then
    while [ -z "$NAME" ]; do
        read -r -p "  Your first name (used so messages sound like you): " NAME
    done
    python3 - "$SRC/config.template.json" "$CFG_FILE" "$NAME" "$AT" <<'PYEOF'
import json, sys
tpl_path, cfg_path, name, at = sys.argv[1:5]
cfg = json.load(open(tpl_path, encoding="utf-8-sig"))
cfg["owner_name"] = name
cfg["refresh_time"] = at
json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), indent=2)
PYEOF
fi
ok "Files in place"

# ---------- 4. App with logo (Dock + Desktop) ----------
# Real .app so it can sit in the Dock. The zip's Open Loops.command is only first-run install.
mkdir -p "$HOME/Applications" "$HOME/Desktop"
DOCK_FLAG=""
# Don't pin to the Dock from a throwaway $HOME (tests) — killall Dock would hit the real Dock.
if [ "$HOME" = "/Users/$(whoami)" ]; then
    DOCK_FLAG="--dock"
fi
bash "$DEST/scripts/macos-app.sh" --app-dir "$DEST" --out "$HOME/Applications/Open Loops.app" $DOCK_FLAG
rm -f "$HOME/Desktop/Open Loops.command"
rm -rf "$HOME/Desktop/Open Loops.app"
cp -R "$HOME/Applications/Open Loops.app" "$HOME/Desktop/Open Loops.app"
ok "Open Loops.app on the Desktop (drag it to the Dock if it isn't there)"

# ---------- 5. Morning refresh ----------
bash "$DEST/scripts/register-task.sh" --at "$AT"
ok "Will refresh itself weekdays at $AT"

# ---------- 6. Open it ----------
say "Opening Open Loops - it will guide you through connecting Slack and email."
cd "$DEST"
nohup python3 -m openloops.app >/dev/null 2>&1 &
disown
echo ""
echo "  Done. You can close this window."
echo ""
