#!/usr/bin/env bash
# Make sure Safari's stored state still has the app's extensions enabled with all-websites access
# (Safari rewrites its state files when it quits); re-apply if not. Leaves Safari quit.
# Usage: scripts/ensure_enabled.sh "/Applications/Some Blocker.app"
cd "$(dirname "$0")/.."
scripts/quit_safari.sh
if ! python3 scripts/enable_in_safari.py --check "$1"; then
  echo "::warning::Safari's stored extension state was changed; re-applying"
  python3 scripts/enable_in_safari.py "$1"
  python3 scripts/enable_in_safari.py --check "$1" || echo "::error::extension state still wrong after re-applying"
fi
