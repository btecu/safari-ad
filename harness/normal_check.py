#!/usr/bin/env python3
"""Run the ad-block fixture and the public test sites in a *normal* Safari window (no WebDriver).

WebDriver sessions run in isolated automation windows, which may not load extensions, so this
is the ground truth for "is the extension actually active?". Also screenshots each public test site.

Usage: harness/normal_check.py --label <label> --out out/results/normal-<label>.json --shots out/shots/<label>
Expects harness/server.py running on 127.0.0.1:8000.
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def osa(script):
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True)


def open_url(url):
    subprocess.run(["open", "-a", "Safari", url], check=False)


def quit_safari():
    osa('tell application "Safari" to quit')
    time.sleep(2)


def screenshot(path):
    """Full-screen capture, downscaled to a JPEG small enough to commit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    png = path.with_suffix(".png")
    subprocess.run(["screencapture", "-x", str(png)], check=False)
    if png.exists():
        subprocess.run(["sips", "-Z", "1400", "-s", "format", "jpeg", "-s", "formatOptions", "70",
                        str(png), "--out", str(path)], capture_output=True)
        png.unlink()


def slug(url):
    return re.sub(r"[^a-z0-9]+", "-", url.split("//", 1)[-1].lower()).strip("-")[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shots", required=True)
    a = ap.parse_args()

    result = {"label": a.label}
    report = ROOT / "out" / "reports" / f"normal-{a.label}.json"
    report.unlink(missing_ok=True)

    quit_safari()
    open_url(f"http://127.0.0.1:8000/fixtures/adtest.html?report=normal-{a.label}")
    for _ in range(60):
        if report.exists():
            break
        time.sleep(1)
    if report.exists():
        r = json.loads(report.read_text())
        result["adtest"] = r
        print(f"[normal/{a.label}] network blocked {r['network_blocked']}/{r['network_total']}, "
              f"cosmetic hidden {r['cosmetic_hidden']}/{r['cosmetic_total']}")
    else:
        result["adtest"] = None
        print(f"::warning::[normal/{a.label}] fixture never reported back (page didn't load or JS failed)")
    screenshot(Path(a.shots) / "fixture.jpg")

    # Public test sites: screenshot in a real window (the WebDriver pass extracts scores).
    sites = json.loads((ROOT / "harness/test_sites.json").read_text())["sites"]
    for s in sites:
        quit_safari()
        open_url(s["url"])
        time.sleep(s.get("wait", 20))
        screenshot(Path(a.shots) / f"{slug(s['url'])}.jpg")
    quit_safari()

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
