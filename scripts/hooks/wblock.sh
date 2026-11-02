#!/usr/bin/env bash
# wBlock ships its content blockers with an empty placeholder rule list; the app downloads and
# compiles filter lists into its app-group container after first-run onboarding. This hook
# clicks through onboarding with the default ("Recommended") choices, then waits for the rules.
# Runs after the extensions are enabled in Safari (wBlock's last onboarding step checks that).
#
# On CI the app's "Apply Changes" sheet has hung at "Converting Rules 0/5" with 0% CPU (it takes ~10 s
# on a real Mac). Fallbacks, in order: run wBlock's own background updater (FilterUpdateAgent, which
# downloads + converts + reloads by itself), then relaunch the app. Each stall is stack-sampled.
set -uo pipefail
APP_PATH="$1"; DIAG="$2"
GC="$HOME/Library/Group Containers/DNP7DGUB7B.group.skula.wBlock"

rules_ready() { # the Ads blocker is on by default and its compiled list is several MB
  [[ -n "$(find "$GC" -maxdepth 1 -name 'rules_ads_macos.json' -size +100k 2>/dev/null)" ]]
}

# wait_rules <label> <minutes>: poll for compiled rules, logging CPU each minute.
wait_rules() {
  local label=$1 mins=$2 i
  for i in $(seq 1 $((mins * 12))); do
    if rules_ready; then echo "wBlock rules ready ($label) after $((i * 5))s"; return 0; fi
    if (( i % 12 == 0 )); then
      echo "--- $label $((i / 12)) min:" | tee -a "$DIAG/wblock-cpu.txt"
      ps -axo %cpu=,rss=,command= | grep -iE '[w]Block|[F]ilterUpdate' | grep -v 'scripts/' | cut -c1-160 \
        | tee -a "$DIAG/wblock-cpu.txt"
    fi
    sleep 5
  done
  return 1
}

# stall_diag <label>: what is the stuck process waiting on?
stall_diag() {
  local label=$1 pid
  screencapture -x "$DIAG/wblock-stall-$label.png"
  for pid in $(pgrep -f "$APP_PATH/Contents"); do
    sample "$pid" 3 -file "$DIAG/wblock-sample-$label-$pid.txt" >/dev/null 2>&1 || true
  done
  cp "$GC/auto_update.log" "$DIAG/wblock-auto_update-$label.log" 2>/dev/null || true
  ls -la "$GC" > "$DIAG/wblock-group-container-$label.txt" 2>&1 || true
}

open "$APP_PATH"
sleep 10
osascript "$(dirname "$0")/wblock-onboarding.applescript" "$DIAG" | tee "$DIAG/wblock-onboarding.txt" \
  || echo "::warning::wBlock onboarding script failed"

if ! wait_rules app 8; then
  echo "::warning::wBlock app stuck converting rules; trying its background updater"
  stall_diag app
  pkill -x wBlock; sleep 3
  # Run the updater directly instead of waiting for launchd, which normally starts it every 15 min.
  "$APP_PATH/Contents/MacOS/FilterUpdateAgent" > "$DIAG/wblock-agent-stdout.txt" 2>&1 &
  agent=$!
  if ! wait_rules agent 6; then
    stall_diag agent
    kill "$agent" 2>/dev/null
    echo "::warning::wBlock updater didn't produce rules either; relaunching the app"
    open "$APP_PATH"; sleep 15
    osascript -e 'tell application "System Events" to key code 36' >/dev/null 2>&1 || true # confirm any apply prompt
    wait_rules relaunch 6 || { stall_diag relaunch; echo "::warning::wBlock produced no compiled rules"; }
  fi
  kill "$agent" 2>/dev/null || true
fi

sleep 20 # let Safari reload the blockers
screencapture -x "$DIAG/wblock-after-setup.png"
ls -la "$GC" > "$DIAG/wblock-group-container.txt" 2>&1 || true
cp "$GC/auto_update.log" "$DIAG/wblock-auto_update.log" 2>/dev/null || true
log show --last 45m --style compact \
  --predicate 'process CONTAINS "wBlock" OR process CONTAINS "FilterUpdate" OR subsystem CONTAINS "wBlock"' \
  2>/dev/null | tail -3000 > "$DIAG/wblock-unified.log" || true
ls -la "$GC"/rules_*_macos.json 2>/dev/null || true
