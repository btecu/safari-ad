#!/usr/bin/env python3
"""Enable every Safari extension inside an app by writing Safari's extension-state plists.

Safari keeps per-extension state, keyed "<bundle id> (<team id>)", in:
  WebExtensions/Extensions.plist      web extensions (Enabled + granted permissions/website access)
  AppExtensions/ContentBlockers.plist content blockers (Enabled)
under ~/Library/Containers/com.apple.Safari/Data/Library/Safari/. Safari must not be running.

Usage: scripts/enable_in_safari.py "/Applications/Some Blocker.app"
Exit code 2 if the Safari container can't be written (missing Full Disk Access / TCC).
"""
import datetime
import json
import plistlib
import re
import subprocess
import sys
from pathlib import Path

SAFARI = Path.home() / "Library/Containers/com.apple.Safari/Data/Library/Safari"
FOREVER = datetime.datetime(4001, 1, 1)  # what Safari stores for "granted indefinitely"


def team_id(path):
    out = subprocess.run(["codesign", "-dv", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"TeamIdentifier=(\w+)", out)
    return m.group(1) if m else None


def load(path):
    try:
        with open(path, "rb") as f:
            return plistlib.load(f)
    except FileNotFoundError:
        return {}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)


def main():
    app = Path(sys.argv[1])
    now = datetime.datetime.utcnow().replace(microsecond=0)
    web_path, cb_path = SAFARI / "WebExtensions/Extensions.plist", SAFARI / "AppExtensions/ContentBlockers.plist"
    try:
        web, cb = load(web_path), load(cb_path)
    except PermissionError as e:
        print(f"::error::Can't read Safari's container ({e}); the runner lacks Full Disk Access")
        return 2

    written = []
    for appex in sorted((app / "Contents/PlugIns").glob("*.appex")):
        with open(appex / "Contents/Info.plist", "rb") as f:
            info = plistlib.load(f)
        point = info.get("NSExtension", {}).get("NSExtensionPointIdentifier", "")
        key = f"{info['CFBundleIdentifier']} ({team_id(appex) or team_id(app)})"

        if point == "com.apple.Safari.content-blocker":
            cb[key] = {**cb.get(key, {}), "Enabled": True, "EnabledByUserGesture": True,
                       "EnabledModificationDate": now}
            written.append(key)
            print(f"content blocker  {key}: enabled")
        elif point == "com.apple.Safari.web-extension":
            manifest = json.loads((appex / "Contents/Resources/manifest.json").read_text())
            perms = manifest.get("permissions", [])
            web[key] = {
                **web.get(key, {}),
                "AddedDate": web.get(key, {}).get("AddedDate", now),
                "Enabled": True, "EnabledByUserGesture": True, "EnabledModificationDate": now,
                "AllowInPrivateBrowsing": True,
                "Permissions": perms,
                "GrantedPermissions": {p: FOREVER for p in perms},
                "AccessibleOrigins": ["<all_urls>"],
                # "Always allow on every website"
                "GrantedPermissionOrigins": {"*://*/*": FOREVER},
                "RevokedPermissions": {}, "RevokedPermissionOrigins": {},
                "HasAbilityToInjectContentIntoWebpages": True,
            }
            written.append(key)
            print(f"web extension    {key}: enabled, all websites allowed, permissions {perms}")

    try:
        save(web_path, web)
        save(cb_path, cb)
    except PermissionError as e:
        print(f"::error::Can't write Safari's container ({e}); the runner lacks Full Disk Access")
        return 2
    # Read back to confirm the writes stuck.
    saved = {**load(web_path), **load(cb_path)}
    bad = [k for k in written if not saved.get(k, {}).get("Enabled")]
    if not written:
        print("::warning::no Safari extensions found in the app")
    print(f"::warning::not enabled after write: {bad}" if bad else f"verified {len(written)} extension(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
