#!/usr/bin/env bash
# Zip an extension app bundle into extensions/<id>.zip (preserves signatures).
# Usage: scripts/package.sh "/path/to/Some Blocker.app" <id>
# Then add an entry to extensions/manifest.json if it's a new extension.
set -euo pipefail
app="$1"; id="$2"
cd "$(dirname "$0")/.."
rm -f "extensions/$id.zip"
ditto -c -k --keepParent "$app" "extensions/$id.zip"
codesign --verify --deep --strict "$app" && echo "signature OK"
ls -lh "extensions/$id.zip"
