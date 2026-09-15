#!/bin/bash
# Build OpenLoops.dmg - a disk image holding "Install Open Loops.app". macOS only (hdiutil).
#
# The installer app does NOT contain Open Loops. Double-clicked, it opens Terminal, downloads the
# repo from GitHub, and runs the repo's own install.sh (Python / Claude Code if missing, copy to
# ~/Documents/OpenLoops, Open Loops.app on the Desktop and in the Dock, weekday refresh).
#
#   bash packaging/macos/build-dmg.sh                        -> dist/OpenLoops.dmg, pulls main
#   bash packaging/macos/build-dmg.sh --ref v0.2 --version 0.2   (release build - pulls that tag)
set -e

REPO="OscarC178/Open-Loops"
REF="main"
VERSION="0.1"
OUT="dist/OpenLoops.dmg"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo) REPO="$2"; shift 2 ;;
        --ref) REF="$2"; shift 2 ;;
        --version) VERSION="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        *) echo "unknown option $1" >&2; exit 1 ;;
    esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
STAGE="$(mktemp -d)"
APP="$STAGE/Install Open Loops.app"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$ROOT/docs/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
sed -e "s|@VERSION@|$VERSION|g" "$HERE/Info.plist" > "$APP/Contents/Info.plist"
sed -e "s|@REPO@|$REPO|g" -e "s|@REF@|$REF|g" "$HERE/install-openloops.command" \
    > "$APP/Contents/Resources/Install Open Loops.command"
cp "$HERE/launcher.sh" "$APP/Contents/MacOS/installer"
chmod +x "$APP/Contents/MacOS/installer" "$APP/Contents/Resources/Install Open Loops.command"
sed -e "s|@REPO@|$REPO|g" "$HERE/README.txt" > "$STAGE/Read me first.txt"

# Ad-hoc signature: not a Developer ID, but it stops macOS calling the app "damaged".
if command -v codesign >/dev/null 2>&1; then
    codesign --force --deep --sign - "$APP" || true
fi

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
hdiutil create -volname "Open Loops" -srcfolder "$STAGE" -ov -format UDZO "$OUT" >/dev/null
echo "built $OUT"
