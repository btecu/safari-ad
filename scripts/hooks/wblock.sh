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
# Converting ~170k rules is slow on a CI VM; log wBlock's CPU use each minute so a stall (idle) can be
# told apart from slow progress (busy), and screenshot the progress dialog.
ready=0
for i in $(seq 1 240); do
  n=$(find "$GC" -maxdepth 1 -name 'rules_*_macos.json' -size +100k 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$n" -ge 3 ]]; then echo "wBlock rules ready after $((i * 5))s"; ready=1; break; fi
  if (( i % 12 == 0 )); then
    m=$((i / 12))
    echo "--- ${m} min: $n compiled rule files; wBlock processes (%CPU RSS command):"
    ps -axo %cpu=,rss=,command= | grep -i '[w]Block' | cut -c1-160 | tee -a "$DIAG/wblock-cpu.txt"
    (( m % 5 == 0 )) && screencapture -x "$DIAG/wblock-progress-${m}min.png"
  fi
  sleep 5
done
[[ $ready == 1 ]] || echo "::warning::wBlock didn't finish compiling its rules within 20 minutes"
sleep 20 # let the last lists finish and Safari reload the blockers
screencapture -x "$DIAG/wblock-after-setup.png"
ls -la "$GC" > "$DIAG/wblock-group-container.txt" 2>&1 || true
ls -la "$GC"/rules_*_macos.json 2>/dev/null || echo "::warning::wBlock produced no compiled rules"
