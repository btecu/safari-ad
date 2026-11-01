#!/usr/bin/env bash
# Install an extension app from the manifest on a CI runner and enable it in Safari.
# Usage: scripts/install_extension.sh <id> <diag-dir>
set -euo pipefail
cd "$(dirname "$0")/.."
ID="$1"; DIAG="${2:-out/diag}"; mkdir -p "$DIAG"

field() { python3 -c "import json,sys;e=[x for x in json.load(open('extensions/manifest.json'))['extensions'] if x['id']==sys.argv[1]][0];print(e.get(sys.argv[2]) or '')" "$ID" "$1"; }
ARCHIVE="$(field archive)"; APP="$(field app)"; HOOK="$(field setup_hook)"
APP_PATH="/Applications/$APP"
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister

echo "::group::Install $APP"
sudo rm -rf "$APP_PATH"
sudo ditto -x -k "$ARCHIVE" /Applications
sudo xattr -dr com.apple.quarantine "$APP_PATH" 2>/dev/null || true
codesign --verify --deep --strict "$APP_PATH" && echo "signature OK"
"$LSREGISTER" -f -R -trusted "$APP_PATH"
echo "::endgroup::"

echo "::group::Register app extensions"
NAMES=()
for appex in "$APP_PATH"/Contents/PlugIns/*.appex; do
  bid=$(plutil -extract CFBundleIdentifier raw "$appex/Contents/Info.plist")
  point=$(plutil -extract NSExtension.NSExtensionPointIdentifier raw "$appex/Contents/Info.plist")
  case "$point" in com.apple.Safari.*) ;; *) continue ;; esac
  name=$(plutil -extract CFBundleDisplayName raw "$appex/Contents/Info.plist" 2>/dev/null || basename "$appex" .appex)
  NAMES+=("$name")
  pluginkit -a "$appex" || true
  pluginkit -e use -i "$bid" || true
  echo "$point  $bid  \"$name\""
done
echo "::endgroup::"

echo "::group::Enable in Safari"
# Safari must be quit while its extension-state plists are edited.
osascript -e 'tell application "Safari" to quit' 2>/dev/null || true
sleep 2
if ! python3 scripts/enable_in_safari.py "$APP_PATH"; then
  echo "::warning::Couldn't write Safari's settings files; falling back to clicking through Safari Settings"
  osascript scripts/enable_in_safari.applescript "$DIAG/safari-settings-ui.txt" "${NAMES[@]}" \
    || echo "::warning::Safari UI enable script failed (see diagnostics)"
  osascript -e 'tell application "Safari" to quit' 2>/dev/null || true
fi
# Launch Safari once so it loads the new state (apps querying "is my blocker enabled?" then see it).
open -a Safari "http://127.0.0.1:8000/fixtures/adtest.html"
sleep 10
osascript -e 'tell application "Safari" to quit' 2>/dev/null || true
echo "::endgroup::"

# Launch the containing app once (some extensions only register / build rules after first launch),
# then run the extension's setup hook (e.g. click through first-run onboarding).
open -g "$APP_PATH" || true
sleep 8
if [[ -n "$HOOK" ]]; then
  echo "::group::Setup hook $HOOK"
  bash "$HOOK" "$APP_PATH" "$DIAG" || echo "::warning::setup hook failed"
  echo "::endgroup::"
fi

# Screenshot the fixture with the blocker fully set up.
osascript -e 'tell application "Safari" to quit' 2>/dev/null || true
open -a Safari "http://127.0.0.1:8000/fixtures/adtest.html"
sleep 10
screencapture -x "$DIAG/after-enable.png" || true
osascript -e 'tell application "Safari" to quit' 2>/dev/null || true

pluginkit -mAvvv -p com.apple.Safari.content-blocker > "$DIAG/pluginkit-content-blockers.txt" 2>&1 || true
pluginkit -mAvvv -p com.apple.Safari.web-extension  > "$DIAG/pluginkit-web-extensions.txt" 2>&1 || true
