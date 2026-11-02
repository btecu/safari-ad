#!/usr/bin/env python3
"""Benchmark Safari via safaridriver (W3C WebDriver over plain HTTP, no dependencies).

Usage: harness/run.py --label baseline --out out/baseline.json [--iterations 3] [--speedometer]
           [--ext-process "wBlock Ads" ...]

Expects `safaridriver -p 4444` running and the fixture server on http://127.0.0.1:8000.
"""
import argparse
import base64
import json
import re
import platform
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DRIVER = "http://127.0.0.1:4444"
FIXTURE = "http://127.0.0.1:8000/fixtures/adtest.html"
SPEEDOMETER = "https://browserbench.org/Speedometer3.1/?startAutomatically=true"


class WebDriverError(Exception):
    pass


def _req(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(DRIVER + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}").get("value")
    except urllib.error.HTTPError as e:
        try:
            v = json.loads(e.read()).get("value", {})
            raise WebDriverError(f"{v.get('error')}: {v.get('message')}") from None
        except (ValueError, AttributeError):
            raise WebDriverError(str(e)) from None


class Session:
    def __init__(self):
        caps = {"capabilities": {"alwaysMatch": {"browserName": "safari", "pageLoadStrategy": "normal"}}}
        self.id = _req("POST", "/session", caps)["sessionId"]
        _req("POST", f"/session/{self.id}/timeouts", {"pageLoad": 60000, "script": 60000})

    def get(self, url):
        _req("POST", f"/session/{self.id}/url", {"url": url}, timeout=90)

    def js(self, script, *args):
        return _req("POST", f"/session/{self.id}/execute/sync", {"script": script, "args": list(args)})

    def screenshot(self, path):
        """Viewport screenshot, downscaled to a JPEG small enough to commit."""
        png = base64.b64decode(_req("GET", f"/session/{self.id}/screenshot"))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".png")
        tmp.write_bytes(png)
        subprocess.run(["sips", "-Z", "1400", "-s", "format", "jpeg", "-s", "formatOptions", "70",
                        str(tmp), "--out", str(path)], capture_output=True)
        tmp.unlink()

    def new_tab(self):
        h = _req("POST", f"/session/{self.id}/window/new", {"type": "tab"})["handle"]
        _req("POST", f"/session/{self.id}/window", {"handle": h})

    def close(self):
        try:
            _req("DELETE", f"/session/{self.id}")
        except Exception:
            pass


def load_ad_hosts():
    lines = (ROOT / "harness/ad_hosts.txt").read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def is_ad(url, hosts):
    p = urlparse(url)
    host = p.hostname or ""
    for entry in hosts:
        h, _, path = entry.partition("/")
        if (host == h or host.endswith("." + h)) and p.path.startswith("/" + path):
            return True
    return False


PAGE_METRICS_JS = """
const nav = performance.getEntriesByType('navigation')[0] || {};
const res = performance.getEntriesByType('resource');
const paint = performance.getEntriesByType('paint').find(p => p.name === 'first-contentful-paint');
return {
  dcl: nav.domContentLoadedEventEnd || null,
  load: nav.loadEventEnd || null,
  fcp: paint ? paint.startTime : null,
  transfer_bytes: res.reduce((a, r) => a + (r.transferSize || 0), 0) + (nav.transferSize || 0),
  resources: res.map(r => r.name),
  visible_ads: visibleAds()
};

// Visible ad slots: elements matching common ad-container selectors that are on screen and at least
// 30x30px. Nested matches count once (only the outermost matching element).
function visibleAds() {
  const SEL = [
    'ins.adsbygoogle', '[id^="div-gpt-ad"]', '[id^="google_ads_iframe"]', '[data-google-query-id]',
    'iframe[src*="doubleclick.net"]', 'iframe[src*="googlesyndication.com"]', 'iframe[src*="amazon-adsystem.com"]',
    'iframe[id^="google_ads"]', '[data-ad-slot]', '[data-ad-unit]', '[aria-label="Advertisement" i]',
    '[id^="taboola-"]', '.trc_rbox_container', '.OUTBRAIN', '[data-widget-id][class*="ob-"]',
    '.ad-slot', '.ad-container', '.ad-unit', '.advertisement', '[class^="ad-"][class*="slot"]'
  ].join(',');
  let n = 0;
  for (const el of document.querySelectorAll(SEL)) {
    if (el.parentElement && el.parentElement.closest(SEL)) continue;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.width >= 30 && r.height >= 30 && cs.display !== 'none' && cs.visibility !== 'hidden'
        && parseFloat(cs.opacity) > 0) n++;
  }
  return n;
}
"""


def run_adtest(s):
    # Each WebDriver session starts a fresh browsing context, and extensions need a few seconds to
    # load their rules into it. Without this warm-up the first page loads with nothing blocked.
    s.get("https://example.com/")
    time.sleep(10)
    s.get(FIXTURE)
    for _ in range(60):
        r = s.js("return window.__adtest || null")
        if r:
            return r
        time.sleep(0.5)
    raise RuntimeError("ad test fixture did not finish")


PAGE_LINES_JS = "return (document.body.innerText || '').split('\\n').map(l => l.trim()).filter(Boolean);"

# Reads a test page's score. With a selector, parse that element. Otherwise only consider lines that
# weren't on the page before the test started (so static copy like "Scoring below 85%?" is ignored),
# preferring lines that mention score/blocked/result/total.
SCORE_JS = """
const [sel, max, before] = arguments;
const el = sel ? document.querySelector(sel) : null;
let lines = ((el ? el.innerText : document.body.innerText) || '').split('\\n').map(l => l.trim()).filter(Boolean);
if (!el) {
  const old = new Set(before || []);
  const fresh = lines.filter(l => !old.has(l));
  const keyed = fresh.filter(l => /score|blocked|result|total|protect/i.test(l));
  lines = keyed.concat(fresh.filter(l => !keyed.includes(l)));
}
for (const l of lines) {
  let m = l.match(/(\\d+(?:\\.\\d+)?)\\s*(?:\\/|out of)\\s*(\\d+)/i);
  if (m && +m[2] > 0) return {pct: 100 * m[1] / m[2], raw: l};
  m = l.match(/(\\d+(?:\\.\\d+)?)\\s*%/);
  if (m) return {pct: +m[1], raw: l};
  if (el && (m = l.match(/^(\\d+(?:\\.\\d+)?)$/))) return {pct: 100 * m[1] / (max || 100), raw: l};
}
// "Total : 132" + "80 blocked" on separate lines (turtlecute).
const all = lines.join(' | ');
const tot = all.match(/total\\s*:?\\s*(\\d+)/i), blk = all.match(/(\\d+)\\s*blocked/i);
if (tot && blk && +tot[1] > 0) return {pct: 100 * blk[1] / tot[1], raw: all.slice(0, 300)};
return {pct: null, raw: all.slice(0, 600)};
"""

CLICK_JS = """
const [sel, text] = arguments;
let b = sel ? document.querySelector(sel) : null;
if (!b && text) b = [...document.querySelectorAll('button, a, [role=button]')]
  .find(e => e.innerText.trim().toLowerCase() === text.toLowerCase());
if (b) { b.scrollIntoView({block: 'center'}); b.click(); return true; }
return false;
"""


def slug(url):
    return re.sub(r"[^a-z0-9]+", "-", url.split("//", 1)[-1].lower()).strip("-")[:60]


def run_test_sites(s, shots_dir):
    """Public ad-blocker test pages: start the test if needed, poll until the score settles,
    screenshot the result. Raw text is kept for debugging the score extraction."""
    sites = json.loads((ROOT / "harness/test_sites.json").read_text())["sites"]
    out = {}
    for t in sites:
        if t.get("score") is False:
            continue
        r = {"pct": None}
        try:
            s.get(t["url"])
            time.sleep(t.get("settle", 5))
            before = s.js(PAGE_LINES_JS)
            if t.get("click") or t.get("click_text"):
                if not s.js(CLICK_JS, t.get("click"), t.get("click_text")):
                    r["error"] = "start button not found"
            # Poll until the score is present and unchanged across two checks, or time runs out.
            deadline, last, stable = time.time() + t.get("wait", 30), None, 0
            while time.time() < deadline:
                time.sleep(5)
                r = {**r, **s.js(SCORE_JS, t.get("score_selector"), t.get("max"), before)}
                stable = stable + 1 if r["pct"] is not None and r["pct"] == last else 0
                last = r["pct"]
                if stable >= 2:
                    break
            if r["pct"] is not None:
                r["pct"] = round(r["pct"], 1)
            s.screenshot(shots_dir / f"{slug(t['url'])}.jpg")
        except Exception as e:
            r = {"pct": None, "error": str(e)[:200]}
        out[t["name"]] = r
        print(f"  {t['name']}: {r.get('pct')}  ({(r.get('raw') or r.get('error') or '')[:120]})", flush=True)
    return out


def run_sites(s, sites, iterations, hosts):
    out = {}
    for url in sites:
        runs = []
        # One extra warm-up load (discarded) so baseline and extension passes both see warm DNS/caches.
        for _ in range(iterations + 1):
            try:
                s.get("about:blank")
                t0 = time.time()
                s.get(url)
                wall = (time.time() - t0) * 1000
                # Scroll once to trigger lazy-loaded ads, come back, let late ad requests fire.
                s.js("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(2)
                s.js("window.scrollTo(0, 0)")
                time.sleep(2)
                m = s.js(PAGE_METRICS_JS)
                third = [u for u in m["resources"] if urlparse(u).hostname
                         and not _same_site(urlparse(u).hostname, urlparse(url).hostname)]
                runs.append({
                    "wall_ms": round(wall), "load_ms": m["load"], "dcl_ms": m["dcl"], "fcp_ms": m["fcp"],
                    "requests": len(m["resources"]), "third_party_requests": len(third),
                    "ad_requests": sum(is_ad(u, hosts) for u in m["resources"]),
                    "transfer_kb": round(m["transfer_bytes"] / 1024),
                    "visible_ads": m["visible_ads"],
                })
            except Exception as e:  # sites blocking CI IPs, timeouts, etc.
                runs.append({"error": str(e)[:200]})
        runs = runs[1:]
        out[url] = runs
        ok =[r for r in runs if "error" not in r]
        print(f"  {url}: {len(ok)}/{len(runs)} ok"
              + (f", load {statistics.median(r['load_ms'] or r['wall_ms'] for r in ok):.0f}ms,"
                 f" ads {statistics.median(r['ad_requests'] for r in ok)}" if ok else ""), flush=True)
    return out


def _same_site(a, b):
    sa, sb = a.split(".")[-2:], b.split(".")[-2:]
    return sa == sb


def sample_memory(ext_processes):
    """Sum RSS (MB) of Safari + WebKit helper processes and the extension's own processes."""
    ps = subprocess.run(["ps", "-axo", "rss=,comm="], capture_output=True, text=True).stdout
    safari = webkit = ext = 0
    for line in ps.splitlines():
        rss, _, comm = line.strip().partition(" ")
        kb = int(rss or 0)
        if any(name in comm for name in ext_processes):
            ext += kb
        elif "/Safari.app/" in comm or "SafariPlatformSupport" in comm or "SafariServices" in comm:
            safari += kb
        elif "com.apple.WebKit" in comm:
            webkit += kb
    mb = lambda kb: round(kb / 1024, 1)
    return {"safari_mb": mb(safari), "webkit_mb": mb(webkit), "extension_mb": mb(ext),
            "total_mb": mb(safari + webkit + ext)}


def run_memory(s, sites, ext_processes):
    """Open the site list in tabs, let them settle, then sample memory a few times."""
    for i, url in enumerate(sites[:6]):
        if i:
            s.new_tab()
        try:
            s.get(url)
        except Exception:
            pass
    time.sleep(15)
    samples = []
    for _ in range(5):
        samples.append(sample_memory(ext_processes))
        time.sleep(3)
    return {k: statistics.median(x[k] for x in samples) for k in samples[0]}


def run_speedometer(s):
    s.get(SPEEDOMETER)
    deadline = time.time() + 20 * 60
    while time.time() < deadline:
        time.sleep(15)
        try:
            score = s.js("""
              const el = document.querySelector('#result-number');
              const t = el && el.textContent.trim();
              return t && !isNaN(parseFloat(t)) ? parseFloat(t) : null;""")
            if score:
                return score
        except WebDriverError:
            pass
    return None


def safari_version():
    try:
        return subprocess.run(["defaults", "read", "/Applications/Safari.app/Contents/Info.plist",
                               "CFBundleShortVersionString"], capture_output=True, text=True).stdout.strip()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--speedometer", action="store_true")
    ap.add_argument("--ext-process", action="append", default=[])
    ap.add_argument("--shots", help="screenshot dir for test-site results (default out/results/shots/<label>)")
    a = ap.parse_args()

    sites = json.loads((ROOT / "harness/sites.json").read_text())["sites"]
    hosts = load_ad_hosts()
    result = {"label": a.label, "safari_version": safari_version(), "macos": platform.mac_ver()[0],
              "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    print(f"[{a.label}] memory (idle)", flush=True)
    s = Session()
    try:
        s.get("about:blank")
        time.sleep(5)
        result["memory_idle"] = sample_memory(a.ext_process)

        print(f"[{a.label}] ad block fixture", flush=True)
        result["adtest"] = run_adtest(s)
        print(f"  network blocked {result['adtest']['network_blocked']}/{result['adtest']['network_total']}, "
              f"cosmetic hidden {result['adtest']['cosmetic_hidden']}/{result['adtest']['cosmetic_total']}",
              flush=True)

        print(f"[{a.label}] public test sites", flush=True)
        result["test_sites"] = run_test_sites(s, Path(a.shots) if a.shots else ROOT / "out/results/shots" / a.label)

        print(f"[{a.label}] page loads x{a.iterations}", flush=True)
        result["sites"] = run_sites(s, sites, a.iterations, hosts)
    finally:
        s.close()

    print(f"[{a.label}] memory (loaded tabs)", flush=True)
    s = Session()
    try:
        result["memory_loaded"] = run_memory(s, sites, a.ext_process)
        print(f"  {result['memory_loaded']}", flush=True)
    finally:
        s.close()

    if a.speedometer:
        print(f"[{a.label}] Speedometer", flush=True)
        s = Session()
        try:
            result["speedometer"] = run_speedometer(s)
            print(f"  score {result['speedometer']}", flush=True)
        finally:
            s.close()

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    sys.exit(main())
