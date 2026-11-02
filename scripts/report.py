#!/usr/bin/env python3
"""Aggregate per-extension job results into results/*.json and the README results section.

Usage: scripts/report.py <results-dir>
  <results-dir>/<extension-id>/baseline.json and extension.json, one pair per matrix job.
Every extension is compared with the "no blocker" baseline measured on the same runner,
so the deltas aren't skewed by differences between runner machines.
"""
import json
import re
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def site_medians(run, key):
    out = {}
    for url, runs in run.get("sites", {}).items():
        vals = [r.get(key) or (r.get("wall_ms") if key == "load_ms" else None)
                for r in runs if "error" not in r]
        m = med(vals)
        if m is not None:
            out[url] = m
    return out


def paired(base, ext, key):
    b, e = site_medians(base, key), site_medians(ext, key)
    common = sorted(set(b) & set(e))
    return med([b[u] for u in common]), med([e[u] for u in common]), len(common)


def blocked_count(bt, et):
    """(blocked, reachable) for the fixture's network probes, or None if either run is missing."""
    if not bt or not et:
        return None
    reachable = [i for i, r in enumerate(bt["network"]) if r["requested"]]
    return sum(not et["network"][i]["requested"] for i in reachable), len(reachable)


def summarize(ext_id, name, base, ext, nbase, next_):
    s = {"id": ext_id, "name": name, "safari_version": ext.get("safari_version"), "macos": ext.get("macos")}
    # Is the extension active at all? Compare the fixture in a normal window vs. a WebDriver window.
    s["active_normal"] = blocked_count((nbase or {}).get("adtest"), (next_ or {}).get("adtest"))
    s["active_webdriver"] = blocked_count(base["adtest"], ext["adtest"])
    # Ad blocking: use whichever window shows the blocker active (more probes blocked; ties go to
    # the normal window). Only probes that loaded in the baseline (reachable from the runner) count.
    use_normal = bool(s["active_normal"]) and (
        not s["active_webdriver"] or s["active_normal"][0] >= s["active_webdriver"][0])
    s["blocking_source"] = "normal window" if use_normal else "WebDriver"
    bt, et = (nbase["adtest"], next_["adtest"]) if use_normal else (base["adtest"], ext["adtest"])
    reachable = [i for i, r in enumerate(bt["network"]) if r["requested"]]
    blocked = [i for i in reachable if not et["network"][i]["requested"]]
    s["network_blocked"], s["network_reachable"] = len(blocked), len(reachable)
    s["network_block_pct"] = round(100 * len(blocked) / len(reachable)) if reachable else None
    s["cosmetic_hidden"], s["cosmetic_total"] = et["cosmetic_hidden"], et["cosmetic_total"]
    s["cosmetic_pct"] = round(100 * et["cosmetic_hidden"] / et["cosmetic_total"])
    s["no_breakage"] = bool(et["controls_ok"] and et["control_element_visible"])
    s["missed"] = [et["network"][i]["url"] for i in reachable if i not in blocked]

    for key, label in [("load_ms", "load"), ("ad_requests", "ads"), ("requests", "requests"),
                       ("transfer_kb", "transfer"), ("visible_ads", "visible_ads")]:
        b, e, n = paired(base, ext, key)
        s[f"{label}_baseline"], s[f"{label}_ext"], s["sites_compared"] = b, e, n
    s["load_delta_pct"] = pct(s["load_baseline"], s["load_ext"])
    s["ads_reduction_pct"] = -pct(s["ads_baseline"], s["ads_ext"]) if s["ads_baseline"] else None
    s["visible_ads_reduction_pct"] = (-pct(s["visible_ads_baseline"], s["visible_ads_ext"])
                                      if s["visible_ads_baseline"] else None)
    s["transfer_delta_pct"] = pct(s["transfer_baseline"], s["transfer_ext"])

    for phase in ("idle", "loaded"):
        b, e = base.get(f"memory_{phase}", {}), ext.get(f"memory_{phase}", {})
        s[f"mem_{phase}_baseline"], s[f"mem_{phase}_ext"] = b.get("total_mb"), e.get("total_mb")
        s[f"mem_{phase}_delta"] = round(e["total_mb"] - b["total_mb"], 1) if b and e else None
    s["speedometer_baseline"], s["speedometer_ext"] = base.get("speedometer"), ext.get("speedometer")
    s["test_sites"] = {k: {"baseline": (base.get("test_sites") or {}).get(k, {}).get("pct"),
                           "ext": v.get("pct"), "raw": v.get("raw") or v.get("error")}
                       for k, v in (ext.get("test_sites") or {}).items()}
    return s


def pct(b, e):
    return round(100 * (e - b) / b, 1) if b and e is not None else None


def fmt(v, suffix="", signed=False):
    if v is None:
        return "—"
    if isinstance(v, float) and (v.is_integer() or abs(v) >= 100):
        v = round(v)
    return (f"{v:+}" if signed else f"{v}") + suffix


def render(rows, generated):
    L = [f"_Last run: {generated} · Safari {rows[0]['safari_version']} · macOS {rows[0]['macos']} "
         f"· GitHub-hosted runner. Deltas compare each blocker with a no-blocker baseline "
         f"measured on the same runner._", ""]

    L += ["### Was the blocker active?", "",
          "Test-page requests blocked in a normal Safari window and in a WebDriver (automation) window, "
          "which runs the speed, real-site and test-site benchmarks. Both should be well above 0; a 0 means "
          "the blocker wasn't active in that window for that run (see `results/diag/`).", "",
          "| Extension | Normal window | WebDriver window |", "|---|---|---|"]
    for r in rows:
        f = lambda t: f"{t[0]}/{t[1]}" if t else "—"
        L.append(f"| **{r['name']}** | {f(r['active_normal'])} | {f(r['active_webdriver'])} |")

    L += ["", "### Ad blocking", "",
          "Real-site columns are medians across the sites in `harness/sites.json`, without → with the blocker.", "",
          "| Extension | Ad/tracker requests blocked (test page) | Ad requests per page (real sites) "
          "| Visible ads per page (real sites) | Generic hiding rules (test page) | Nothing broken |",
          "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| **{r['name']}** | {fmt(r['network_block_pct'], '%')} ({r['network_blocked']}/{r['network_reachable']}) "
                 f"| {fmt(r['ads_baseline'])} → {fmt(r['ads_ext'])} ({fmt(r['ads_reduction_pct'], '% fewer')}) "
                 f"| {fmt(r.get('visible_ads_baseline'))} → {fmt(r.get('visible_ads_ext'))} "
                 f"({fmt(r.get('visible_ads_reduction_pct'), '% fewer')}) "
                 f"| {r['cosmetic_hidden']}/{r['cosmetic_total']} "
                 f"| {'✅' if r['no_breakage'] else '⚠️'} |")
    L += ["", "_Generic hiding rules hide ad-like elements on any site. Some blockers only use them in a "
          "non-default mode (uBlock Origin Lite: \"Complete\"), so 0 there is expected with default settings. "
          "Visible ads on real sites is the better measure of hidden ads._"]

    sites = sorted({k for r in rows for k in r["test_sites"]})
    if sites:
        L += ["", "### Public ad-block test sites (score, higher is better)", "",
              "_Scores are read from each page's text after the test finishes (best effort; see screenshots)._", "",
              "| Test site | No blocker | " + " | ".join(r["name"] for r in rows) + " |",
              "|---|---|" + "---|" * len(rows)]
        for site in sites:
            base = next((r["test_sites"][site]["baseline"] for r in rows if site in r["test_sites"]), None)
            L.append(f"| {site} | {fmt(base, '%')} | "
                     + " | ".join(fmt(r["test_sites"].get(site, {}).get("ext"), "%") for r in rows) + " |")

    L += ["", "### Speed", "",
          "| Extension | Median page load (none → with blocker) | Change | Data transferred | Speedometer 3.1 (none → with blocker) |",
          "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| **{r['name']}** | {fmt(r['load_baseline'], ' ms')} → {fmt(r['load_ext'], ' ms')} "
                 f"| {fmt(r['load_delta_pct'], '%', True)} | {fmt(r['transfer_delta_pct'], '%', True)} "
                 f"| {fmt(r['speedometer_baseline'])} → {fmt(r['speedometer_ext'])} |")

    L += ["", "### Memory (Safari + WebKit + extension processes)", "",
          "| Extension | Idle | Δ idle | 6 sites open | Δ with sites open |", "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| **{r['name']}** | {fmt(r['mem_idle_ext'], ' MB')} | {fmt(r['mem_idle_delta'], ' MB', True)} "
                 f"| {fmt(r['mem_loaded_ext'], ' MB')} | {fmt(r['mem_loaded_delta'], ' MB', True)} |")

    names = ", ".join(f'"{r["name"]}"' for r in rows)
    L += ["", "```mermaid", "xychart-beta", '  title "Ad/tracker requests blocked (%)"',
          f"  x-axis [{names}]", '  y-axis "%" 0 --> 100',
          f"  bar [{', '.join(str(r['network_block_pct'] or 0) for r in rows)}]", "```"]
    L += ["", "```mermaid", "xychart-beta", '  title "Median page load time (ms, lower is better)"',
          f'  x-axis ["No blocker", {names}]',
          f"  bar [{round(med([r['load_baseline'] for r in rows]) or 0)}, "
          f"{', '.join(str(round(r['load_ext'] or 0)) for r in rows)}]", "```"]

    shots = ROOT / "results" / "screenshots"
    if (shots / "baseline").exists():
        cols = ["baseline"] + [r["id"] for r in rows]
        heads = ["No blocker"] + [r["name"] for r in rows]
        L += ["", "<details><summary>Screenshots (normal Safari window)</summary>", "",
              "| Page | " + " | ".join(heads) + " |", "|---|" + "---|" * len(cols)]
        for img in sorted((shots / "baseline").glob("*.jpg")):
            cells = [f'<img src="results/screenshots/{c}/{img.name}" width="260">'
                     if (shots / c / img.name).exists() else "—" for c in cols]
            L.append(f"| `{img.stem}` | " + " | ".join(cells) + " |")
        L += ["", "</details>"]

    missed = [r for r in rows if r["missed"]]
    if missed:
        L += ["", "<details><summary>Test requests that weren't blocked</summary>", ""]
        for r in missed:
            L.append(f"- **{r['name']}**: " + ", ".join(f"`{u.split('/')[2]}`" for u in r["missed"]))
        L += ["", "</details>"]
    return "\n".join(L)


def main():
    src = Path(sys.argv[1])
    manifest = {e["id"]: e for e in json.loads((ROOT / "extensions/manifest.json").read_text())["extensions"]}
    rows = []
    shots_dir = ROOT / "results" / "screenshots"
    shutil.rmtree(shots_dir, ignore_errors=True)
    for d in sorted(p for p in src.iterdir() if p.is_dir()):
        b, e = d / "baseline.json", d / "extension.json"
        if not (b.exists() and e.exists()):
            print(f"skipping {d.name}: missing results", file=sys.stderr)
            continue
        name = manifest.get(d.name, {}).get("name", d.name)
        load = lambda f: json.loads(f.read_text()) if f.exists() else None
        rows.append(summarize(d.name, name, load(b), load(e),
                              load(d / "normal-baseline.json"), load(d / "normal-extension.json")))
        # Screenshots -> results/screenshots/<id>/ (each job's "baseline" set overwrites the previous one).
        for sub in (d / "shots").glob("*") if (d / "shots").exists() else []:
            shutil.copytree(sub, shots_dir / sub.name, dirs_exist_ok=True)
        # Raw per-run JSON, for digging into a result without downloading artifacts.
        raw = ROOT / "results" / "raw" / d.name
        shutil.rmtree(raw, ignore_errors=True)
        raw.mkdir(parents=True)
        for f in d.glob("*.json"):
            shutil.copy(f, raw / f.name)
        diag = ROOT / "results" / "diag" / d.name
        shutil.rmtree(diag, ignore_errors=True)
        if (d / "diag").exists():
            shutil.copytree(d / "diag", diag)
    if not rows:
        sys.exit("no results")
    rows.sort(key=lambda r: -(r["network_block_pct"] or 0))

    generated = time.strftime("%Y-%m-%d", time.gmtime())
    out = ROOT / "results"
    (out / "history").mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"generated": generated, "results": rows}, indent=2)
    (out / "latest.json").write_text(payload)
    (out / "history" / f"{generated}.json").write_text(payload)

    readme = ROOT / "README.md"
    text = readme.read_text()
    section = f"{START}\n{render(rows, generated)}\n{END}"
    readme.write_text(re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: section, text, flags=re.S))
    print(render(rows, generated))


if __name__ == "__main__":
    main()
