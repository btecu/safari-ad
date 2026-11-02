#!/usr/bin/env bash
# Quit Safari and wait until the process is really gone (it writes its state files on the way out).
osascript -e 'tell application "Safari" to quit' 2>/dev/null || true
for _ in $(seq 1 30); do pgrep -xq Safari || exit 0; sleep 1; done
echo "::warning::Safari didn't quit; killing it"
pkill -x Safari || true
sleep 2
