#!/usr/bin/env bash
# wBlock ships its content blockers with an empty placeholder rule list; the app downloads and
# compiles filter lists into its app-group container after first-run onboarding. This hook
# clicks through onboarding with the default ("Recommended") choices, then waits for the rules.
# Runs after the extensions are enabled in Safari (wBlock's last onboarding step checks that).
set -uo pipefail
APP_PATH="$1"; DIAG="$2"
GC="$HOME/Library/Group Containers/DNP7DGUB7B.group.skula.wBlock"

open "$APP_PATH"
sleep 10
osascript "$(dirname "$0")/wblock-onboarding.applescript" "$DIAG" | tee "$DIAG/wblock-onboarding.txt" \
  || echo "::warning::wBlock onboarding script failed"

# Wait for wBlock to download + compile filter lists (rules_*_macos.json in its app group).
for i in $(seq 1 60); do
  size=$(find "$GC" -maxdepth 1 -name 'rules_*_macos.json' -size +100k 2>/dev/null | wc -l | tr -d ' ')
  [[ "$size" -ge 3 ]] && { echo "wBlock rules ready after $((i * 5))s"; break; }
  sleep 5
done
sleep 20 # let the last lists finish and Safari reload the blockers
screencapture -x "$DIAG/wblock-after-setup.png"
ls -la "$GC" > "$DIAG/wblock-group-container.txt" 2>&1 || true
ls -la "$GC"/rules_*_macos.json 2>/dev/null || echo "::warning::wBlock produced no compiled rules"
