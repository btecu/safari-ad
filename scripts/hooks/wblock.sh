#!/usr/bin/env bash
# wBlock ships its content blockers with an empty placeholder rule list; the app downloads
# and compiles filter lists into its app-group container. This hook gives the app time to do
# that and captures screenshots so the first-run UI can be scripted once we know what it shows.
# TODO: once the onboarding UI is known from the screenshots, click through "Apply"/"Done" here.
set -uo pipefail
APP_PATH="$1"; DIAG="$2"
open "$APP_PATH"
for i in 1 2 3 4 5 6; do sleep 20; screencapture -x "$DIAG/wblock-$i.png"; done
GC="$HOME/Library/Group Containers/DNP7DGUB7B.group.skula.wBlock"
ls -laR "$GC" > "$DIAG/wblock-group-container.txt" 2>&1 || true
