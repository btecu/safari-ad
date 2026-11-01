# Safari Ad Blocker Benchmark

Automated, repeatable comparison of Safari ad-blocking extensions on GitHub-hosted macOS
runners: how much they block, what they cost in page-load speed and memory, and whether
they break pages.

## Results

<!-- RESULTS:START -->
_Last run: 2026-11-01 · Safari 26.6.2 · macOS 26.6.2 · GitHub-hosted runner. Deltas compare each blocker with a no-blocker baseline measured on the same runner._

### Was the blocker active?

Test-page requests blocked, in a normal Safari window vs. a WebDriver (automation) window. If the WebDriver column is 0 but the normal column isn't, Safari isn't loading extensions in automation windows, and the WebDriver-based speed/real-site numbers mostly reflect no blocking.

| Extension | Normal window | WebDriver window |
|---|---|---|
| **uBlock Origin Lite** | 25/25 | 0/25 |
| **wBlock** | 0/25 | 0/25 |

### Ad blocking

| Extension | Ad/tracker requests blocked | Ad elements hidden | Ad requests per page (none → with blocker) | Nothing broken |
|---|---|---|---|---|
| **uBlock Origin Lite** | 100% (25/25) | 0% (0/10) | 68.5 → 1.5 (97.8% fewer) | ✅ |
| **wBlock** | 0% (0/25) | 0% (0/10) | 53 → 42 (20.8% fewer) | ✅ |

### Public ad-block test sites (score, higher is better)

_Scores are read from each page's text after the test finishes (best effort; see screenshots)._

| Test site | No blocker | uBlock Origin Lite | wBlock |
|---|---|---|---|
| AdBlock Tester (turtlecute) | — | — | — |
| adblock-tester.com | 41% | 91% | 41% |
| d3ward Toolz | — | — | — |

### Speed

| Extension | Median page load (none → with blocker) | Change | Data transferred | Speedometer 3.1 (none → with blocker) |
|---|---|---|---|---|
| **uBlock Origin Lite** | 775 ms → 682 ms | -12% | -41.5% | 14.3 → 13.7 |
| **wBlock** | 498 ms → 1089 ms | +119% | -28.6% | 12.3 → 15 |

### Memory (Safari + WebKit + extension processes)

| Extension | Idle | Δ idle | 6 sites open | Δ with sites open |
|---|---|---|---|---|
| **uBlock Origin Lite** | 1388 MB | +910 MB | 2863 MB | -30.4 MB |
| **wBlock** | 741 MB | +268 MB | 3440 MB | +116 MB |

```mermaid
xychart-beta
  title "Ad/tracker requests blocked (%)"
  x-axis ["uBlock Origin Lite", "wBlock"]
  y-axis "%" 0 --> 100
  bar [100, 0]
```

```mermaid
xychart-beta
  title "Median page load time (ms, lower is better)"
  x-axis ["No blocker", "uBlock Origin Lite", "wBlock"]
  bar [636, 682, 1089]
```

<details><summary>Screenshots (normal Safari window)</summary>

| Page | No blocker | uBlock Origin Lite | wBlock |
|---|---|---|---|
| `adblock-tester-com` | <img src="results/screenshots/baseline/adblock-tester-com.jpg" width="260"> | <img src="results/screenshots/ublock-origin-lite/adblock-tester-com.jpg" width="260"> | <img src="results/screenshots/wblock/adblock-tester-com.jpg" width="260"> |
| `adblock-turtlecute-org` | <img src="results/screenshots/baseline/adblock-turtlecute-org.jpg" width="260"> | <img src="results/screenshots/ublock-origin-lite/adblock-turtlecute-org.jpg" width="260"> | <img src="results/screenshots/wblock/adblock-turtlecute-org.jpg" width="260"> |
| `canyoublockit-com-extreme-test` | <img src="results/screenshots/baseline/canyoublockit-com-extreme-test.jpg" width="260"> | <img src="results/screenshots/ublock-origin-lite/canyoublockit-com-extreme-test.jpg" width="260"> | <img src="results/screenshots/wblock/canyoublockit-com-extreme-test.jpg" width="260"> |
| `d3ward-github-io-toolz-adblock` | <img src="results/screenshots/baseline/d3ward-github-io-toolz-adblock.jpg" width="260"> | <img src="results/screenshots/ublock-origin-lite/d3ward-github-io-toolz-adblock.jpg" width="260"> | <img src="results/screenshots/wblock/d3ward-github-io-toolz-adblock.jpg" width="260"> |
| `fixture` | <img src="results/screenshots/baseline/fixture.jpg" width="260"> | <img src="results/screenshots/ublock-origin-lite/fixture.jpg" width="260"> | <img src="results/screenshots/wblock/fixture.jpg" width="260"> |

</details>

<details><summary>Test requests that weren't blocked</summary>

- **wBlock**: `pagead2.googlesyndication.com`, `securepubads.g.doubleclick.net`, `www.googletagservices.com`, `static.doubleclick.net`, `www.google-analytics.com`, `www.googletagmanager.com`, `connect.facebook.net`, `static.ads-twitter.com`, `c.amazon-adsystem.com`, `cdn.taboola.com`, `widgets.outbrain.com`, `acdn.adnxs.com`, `bat.bing.com`, `snap.licdn.com`, `static.hotjar.com`, `cdn.mxpnl.com`, `sb.scorecardresearch.com`, `www.clarity.ms`, `static.criteo.net`, `ads.pubmatic.com`, `mc.yandex.ru`, `secure.quantserve.com`, `js-agent.newrelic.com`, `s.pinimg.com`, `analytics.tiktok.com`

</details>
<!-- RESULTS:END -->

## Extensions tested

| Extension | Type | Source of binary |
|---|---|---|
| uBlock Origin Lite | Safari web extension (declarativeNetRequest) | Mac App Store build |
| wBlock | Safari content blockers + web extension | Notarized Developer ID build |

## How it works

Each extension gets its own fresh macOS runner (a matrix job). On that runner:

1. **Baseline:** Safari is benchmarked with no blocker installed.
2. **Install:** the extension's app is unzipped into `/Applications`, registered with
   LaunchServices/`pluginkit`, and switched on by writing Safari's extension-state files
   (`scripts/enable_in_safari.py`). Web extensions are also granted "Always allow on every website".
   Each extension runs with its default settings, after its app's first-run setup if it has one.
3. **With blocker:** the same benchmark runs again.

Comparing with a baseline from the *same* runner cancels out most of the variation between the
shared virtual machines GitHub hands out.

### What's measured

| Test | How |
|---|---|
| **Ad/tracker requests blocked** | `fixtures/adtest.html` tries to load 25 well-known ad and tracker scripts. A request counts as blocked if it never shows up in the Resource Timing API. Only scripts that loaded in the baseline count, so a host that's unreachable from CI isn't scored as "blocked". |
| **Ad elements hidden** | Elements on the same page that EasyList's generic hiding rules target (`.adsbygoogle`, `#ad_banner`, `div-gpt-ad-*`, …). |
| **Breakage** | Two normal CDN scripts and a plain element on the page must still load and stay visible. |
| **Ad requests on real sites** | Each site in `harness/sites.json` is loaded and every request to a domain in `harness/ad_hosts.txt` is counted. |
| **Page load time** | `loadEventEnd` from the Navigation Timing API, median of N loads per site after one discarded warm-up load, then the median across sites. |
| **Data transferred** | Sum of the `transferSize` values reported for the page. |
| **Memory** | Resident memory (RSS) of Safari, the WebKit helper processes and the extension's own processes, measured idle and with 6 sites open in tabs (median of 5 samples). |
| **Public test sites** | [adblock-tester.com](https://adblock-tester.com/), [AdBlock Tester](https://adblock.turtlecute.org/), [Super Adblock Test](https://superadblocktest.com/) and [Blockify's test](https://getblockify.com/adblock-test) are run, and each score is read once it stops changing. [Can You Block It](https://canyoublockit.com/extreme-test/) has no score, so it's screenshot only. Screenshots of every page are in the gallery above. Each site uses its own method, so compare blockers within a site rather than across sites. |
| **Speedometer 3.1** | Browser responsiveness score, to show the overhead a blocker adds on pages without ads. |

### Caveats

- GitHub runners are shared VMs, so absolute numbers are noisy. Rely on the same-runner deltas and the trend across runs, not one run.
- Real sites change constantly and some block datacenter IPs. Failed loads are excluded from the comparison.
- Cross-origin `transferSize` is often reported as 0, which makes "data transferred" an undercount.
- Speedometer pages contain no ads, so a good score here means the blocker adds little overhead. It doesn't measure blocking.

## Adding or updating an extension

```sh
scripts/package.sh "/Applications/Some Blocker.app" some-blocker   # writes extensions/some-blocker.zip
```

Then add an entry to `extensions/manifest.json`:

```json
{ "id": "some-blocker", "name": "Some Blocker", "archive": "extensions/some-blocker.zip",
  "app": "Some Blocker.app", "setup_hook": null }
```

`setup_hook` is an optional script that runs after the extension is enabled, for apps that need
first-run setup before they block anything. wBlock's (`scripts/hooks/wblock.sh`) clicks through its
onboarding with the default choices, then waits while the app downloads and compiles its filter lists.

## Running

Actions → **Benchmark Safari ad blockers** → *Run workflow*. It also runs weekly. Each job
uploads `diag-<id>` artifacts (screenshots, the Safari Settings UI dump, `pluginkit` state) for
debugging the install and enable steps.
