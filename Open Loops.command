#!/bin/bash
# Open Loops - double-click me. macOS equivalent of "Open Loops.cmd".
#   Not installed yet?  -> runs the installer (install.sh), which puts Open Loops in
#                          ~/Documents/OpenLoops and a launcher on your Desktop.
#   Already installed?  -> starts it (backgrounded) and opens the page in your browser.
set -e
# Non-interactive shells don't read the user's profile, so claude (Homebrew or the official
# installer) may not be on PATH. Jobs inherit this.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
APP="$HOME/Documents/OpenLoops/openloops/app.py"
if [ -f "$APP" ]; then
    cd "$HOME/Documents/OpenLoops"
    nohup python3 -m openloops.app >/dev/null 2>&1 &
    disown
    sleep 1
    exit 0
fi
echo "Installing Open Loops..."
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$DIR/install.sh"
