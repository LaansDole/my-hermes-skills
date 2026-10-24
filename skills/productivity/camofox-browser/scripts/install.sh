#!/bin/bash
# Installs the Camofox runtime (~/.camofox), helper CLI and launchd plist. Idempotent.
# Does NOT load the launchd job: run the printed launchctl command yourself (agents are blocked from it).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; D="$HOME/.camofox"; SRC="$HOME/Projects/camofox-browser"
[ -d "$SRC" ] || { git clone --depth 1 https://github.com/jo-inc/camofox-browser "$SRC"; (cd "$SRC" && npm install --omit=dev); }
mkdir -p "$D" "$HOME/.local/bin" "$HOME/Library/LaunchAgents"; umask 077
[ -f "$D/env" ] || printf 'CAMOFOX_ADMIN_KEY=%s\nCAMOFOX_CRASH_REPORT_ENABLED=false\n' "$(openssl rand -hex 32)" > "$D/env"
[ -f "$D/mode" ] || echo off > "$D/mode"
install -m 700 "$HERE/run.sh" "$D/run.sh"; install -m 700 "$HERE/camofox" "$D/camofox"
ln -sf "$D/camofox" "$HOME/.local/bin/camofox"
sed "s#__HOME__#$HOME#g" "$HERE/com.laansdole.camofox.plist.template" > "$HOME/Library/LaunchAgents/com.laansdole.camofox.plist"
grep -q '^CAMOFOX_URL=' "$HOME/.hermes/.env" 2>/dev/null || printf '\nCAMOFOX_URL=http://localhost:9377\n' >> "$HOME/.hermes/.env"
hermes config set browser.cloud_provider camofox --force >/dev/null
hermes config set browser.camofox.managed_persistence true >/dev/null
echo "Installed. Now run in your own terminal:"
echo "  launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/com.laansdole.camofox.plist && camofox status"
