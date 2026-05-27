---
name: stealth-browser-automation
description: Automate / scrape sites behind Cloudflare, Turnstile, FingerprintJS, BrowserScan, DataDome and similar anti-bot stacks. Drop-in stealth Chromium (CloakBrowser) replaces Playwright/Puppeteer; choose tier-1 (headless, datacenter IP) for ~80% of detection sites and tier-2 (headed Xvfb + residential proxy + humanize + geoip) for full CF Bot Management / interactive challenges.
when_to_use:
  - Stock Playwright / Puppeteer / Selenium gets a 403 "Just a moment..." / "Performing security verification" page.
  - Need to bypass Cloudflare Turnstile (non-interactive or managed), FingerprintJS, BrowserScan, ShieldSquare, nodriver checks.
  - User asks "can X bypass CF" / "how do I scrape this protected site" / mentions a stealth-browser tool.
  - Existing automation works locally but breaks on CI / VPS due to headless detection.
  - Need a drop-in replacement for `playwright-stealth`, `undetected-chromedriver`, `puppeteer-extra-plugin-stealth` that doesn't break on every Chrome update.
version: 1
---

# Stealth Browser Automation

Source-level patched Chromium for sites that detect or block Playwright / Puppeteer / Selenium. The standard stack is **CloakBrowser** (`pip install cloakbrowser` → ~206MB stealth Chromium binary). Patches are compiled into the C++, not injected at runtime, so detection sites see a real browser because it *is* a real browser.

## Why CloakBrowser over the alternatives

| Tool | Patch level | Cloudflare Turnstile | Survives Chrome updates |
|---|---|---|---|
| `playwright-stealth` | JS injection | Sometimes | Breaks often |
| `undetected-chromedriver` | Config patches | Sometimes | Breaks often |
| nodriver / Camoufox | C++ (Firefox fork) | Pass | Yes, but unstable |
| **CloakBrowser** | C++ Chromium source | **Pass** | Yes, actively maintained |

If a session uses `playwright-stealth` and gets blocked, switch to CloakBrowser before touching anything else.

## The two-tier playbook

**Tier-1 — 80% of sites, headless OK:** webdriver flag, UA, plugins, canvas/WebGL/audio/GPU/screen/WebRTC indicators. Just install and call `launch()`. No proxy, no Xvfb. Empirically beats nowsecure.nl, BrowserScan bot-detection, FingerprintJS demo, generic CF-protected pages that only check fingerprint signals.

```python
from cloakbrowser import launch
browser = launch()                          # auto-downloads binary on first run
page = browser.new_page()
page.goto("https://target.com")
browser.close()
```

**Tier-2 — aggressive sites (full CF Bot Management, Turnstile interactive, DataDome, Kasada, 极验):** behavioral + IP + ML scoring. Datacenter IPs alone will trip them even with perfect fingerprints.

```python
browser = launch(
    proxy="http://user:pass@residential-ip:port",  # MUST be residential
    geoip=True,        # match TZ + locale to proxy IP (auto WebRTC IP spoof)
    headless=False,    # under Xvfb on Linux servers
    humanize=True,     # Bezier mouse, per-character typing, realistic scroll
)
```

On a headless server, run under Xvfb: `xvfb-run -a python script.py`.

## Install + first-run

```bash
mkdir -p /tmp/cb && cd /tmp/cb
python -m venv .venv && source .venv/bin/activate
pip install cloakbrowser
cloakbrowser install      # ~206MB download, ~30s
```

Binary lands under `~/.cloakbrowser/chromium-<ver>/chrome` and auto-updates in background. System deps on Debian/Ubuntu: `libnss3 libatk-bridge2.0-0 libatk1.0-0 libgbm1 libasound2 xvfb` are typically present out of the box on most server images.

CloakBrowser exports a Playwright-compatible API; existing Playwright code migrates with one import swap.

## Diagnose first: is the failure fingerprint-side or IP-side?

When a target returns 403 / challenge, **don't tweak browser flags blindly**. Run this two-step triage before promoting tiers:

```bash
# 1. What ASN is this box on?
curl -s "https://ipinfo.io/$(curl -s https://api.ipify.org)/json"
# Look at "org" — AS36352 HostPapa, AS14061 DigitalOcean, AS16509 Amazon, etc. = datacenter
# Residential ASNs look like "AS4837 China Unicom", "AS7922 Comcast Cable", "AS3320 Deutsche Telekom"

# 2. Did CF inject the challenge widget, or reject at IP layer?
# In the page after navigation, evaluate:
#   document.querySelector('iframe[src*="challenges.cloudflare.com"]')
# - iframe present → fingerprint/behavior failed the challenge → tweaking browser MIGHT help
# - iframe absent + HTTP 403 + cf-mitigated: challenge → IP-layer block → NO browser change will help
```

When `has_iframe: false` and the response is 403, **stop touching CloakBrowser**. CF refused to even run the challenge. The only fix is a different egress IP (tier-2 proxy, residential routing, etc.).

## Pitfalls discovered in real testing

- **`Browser Tampering: Yes 🖥️🔧` on FingerprintJS** even when `Bot: Not detected`. The C++ patches *are* visible to fingerprint.com's tampering heuristic. Bot-score-only sites pass; sites that gate on tampering will reject. Mitigation: tier-2 (proxy + geoip) sometimes resolves; otherwise no clean fix today.
- **Datacenter IP → CF 403 even on tier-1.** A nopecha CF demo returned `HTTP 403, Ray ID …, Performing security verification` despite clean fingerprints. ISP/ASN is part of the score. Don't blame the patches; bring a residential proxy. Confirm with the diagnose step above.
- **Timezone / IP mismatch is its own detection signal.** Without `geoip=True` the browser reports `timezone: UTC, getTimezoneOffset: 0` while the egress IP geo-locates elsewhere. Bot-management ML cross-checks this. Always pair `proxy=` with `geoip=True` in tier-2; never run tier-2 with one and not the other.
- **Pure headless can fail Turnstile interactive / managed.** Some sites cross-check headless heuristics (e.g. window focus, viewport timing) independent of fingerprint. Promote to `headless=False` under Xvfb before adding more flags.
- **`xvfb-run` fails with `xauth command not found`** on minimal Debian/Ubuntu containers without root to `apt install xauth`. Workaround — start Xvfb directly and export DISPLAY:
  ```bash
  # Background it via your scheduler / systemd, NOT '&' wrapping
  Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp
  # then in the run command:
  DISPLAY=:99 python script.py
  ```
  This bypasses the `xvfb-run` wrapper entirely and works as a non-root user. Verify with `pgrep -a Xvfb` and `ls /tmp/.X11-unix/X99`.
- **Manually unpacking Chromium via `python -c "zipfile.ZipFile(...).extractall(...)"` strips the Unix `+x` mode bit.** Browser launches with `chrome_crashpad_handler: Permission denied (13)` then SIGTRAP / `Received signal 6`. Happens when `unzip` isn't installed on a minimal container and you fall back to Python's stdlib (Python's `zipfile` doesn't preserve POSIX permissions). Fix:
  ```bash
  cd <chromium-dir>/chrome-linux64
  find . -type f -exec sh -c 'head -c 4 "$1" | grep -q ELF && chmod +x "$1"' _ {} \;
  ```
  Then re-launch. Cleaner: install `unzip` (`apt install unzip`) before extracting. CloakBrowser's own installer doesn't have this problem because it shells out to `unzip`; the bug only appears when you're hand-rolling a Playwright Chromium install in a `unzip`-less environment.
- **Playwright searches for `chrome-linux/chrome` not `chrome-linux64/chrome`.** When you manually install Chromium for Testing (`cdn.playwright.dev/builds/cft/<ver>/linux64/chrome-linux64.zip`), the archive extracts to `chrome-linux64/`. Symlink it: `ln -sfn chrome-linux64 chrome-linux` inside the version directory. Also pass `channel='chromium'` to `launch()` — the default selects `chromium_headless_shell`, which is a *different* binary that won't be present unless you installed it separately. Mixed install: you can symlink one Playwright browsers dir into another so a single `PLAYWRIGHT_BROWSERS_PATH` resolves both.
- **First-run downloads 206MB.** Account for it in cron / CI; cache `~/.cloakbrowser/` between runs.
- **Ko-fi banner prints to stdout** every install. Strip when capturing logs.
- **Screenshots can lie** — always check `response.status` and grep page body for blocking markers (`just a moment`, `checking your browser`, `verifying you are human`, `attention required`, `access denied`, `performing security verification`, `ray id`). A 403 often still renders a "Just a moment..." page that a naive title check passes.
- **Use `launch_persistent_context(user_data_dir=...)` for repeat visits** — keeps cookies / localStorage across sessions, bypasses incognito-detection signals, and lets a successful CF clearance cookie persist for hours. Cheaper than burning a fresh challenge per run.
- **Cloudflare Turnstile widgets render in a closed shadow root.** `document.querySelectorAll('iframe')` and `document.getElementsByTagName('iframe')` return empty even when the widget is fully visible and functional. Use `page.frames` (Playwright/CDP-level) to detect the CF iframe — its URL matches `challenges.cloudflare.com/.../turnstile/...`. Do NOT call `page.set_viewport_size()` after `goto()`; it can re-trigger CF's bot-score and break challenge mounting. Set viewport at context creation (or rely on Xvfb's screen size).
- **Turnstile interactive checkbox in tier-2 (headed Xvfb): blind-click works.** Because the widget lives in a closed shadow root, neither DOM queries nor `frame_locator` can find the visible checkbox to click. Workaround: take a screenshot, ask vision for pixel coords of the unchecked checkbox, then `page.mouse.click(x, y, delay=80)` with a humanized approach (move-then-click in 2-3 hops). Token reliably appears within 30-90s after click. The checkbox sits ~30px from the widget's left edge.
- **`render=explicit` + `window.turnstile` undefined ≠ blocked.** When you intercept early via `add_init_script`, the patched `window.turnstile` getter/setter prevents the real script from initializing. Don't add init-scripts that touch `window.turnstile`. If you need to introspect the API, use page-level `page.evaluate` after the widget is already mounted.

## Cheap residential-IP options when no proxy budget

Tier-2 needs residential egress. Before paying for BrightData / Smartproxy / IPRoyal, check what the user already has:

- **User's home network.** If they have residential broadband (and you can SSH there), run `ssh -D 1080 -N user@home-box` from the agent server, then point CloakBrowser at `proxy="socks5://127.0.0.1:1080"` plus `geoip=True`. Free, real residential ASN, real geolocation.
- **Mobile tethering / 5G dongle.** Most carrier mobile IPs are classified residential / mobile by CF; works for low-volume scraping.
- **A friend / second home.** Same SOCKS5 trick. CloakBrowser supports SOCKS5 natively (`proxy="socks5://user:pass@host:port"`).
- Only fall back to paid residential proxies (IPRoyal pay-as-you-go is cheapest at ~$2/GB) when none of the above is available.

## Verification probe

A ready-to-run probe lives at `scripts/probe.py` — runs the stealth browser against four canonical detection sites (CF + nodriver, FingerprintJS demo, BrowserScan, Cloudflare Turnstile demo), saves screenshots + JSON results, and uses both HTTP status and body-text heuristics to call PASS/FAIL. Run it whenever:
- Validating a fresh install
- Sanity-checking after a CloakBrowser version bump
- Diagnosing whether a target failure is fingerprint-side or IP-side (probe nowsecure.nl alone — if that fails too, install is broken; if only the user's target fails, it's IP/behavior, go tier-2)

```bash
cd /path/to/cloakbrowser-venv && source .venv/bin/activate
python scripts/probe.py            # headless
XVFB=1 xvfb-run -a python scripts/probe.py  # headed
```

## When CloakBrowser is the wrong tool

- **Sign-in / check-in flows that expose a JSON API** → use a direct API approach (e.g. `web-signin-cron-jobs` or `website-checkin-automation` skills if you're on Hermes). Hitting the API directly with a session cookie is faster, idempotent, and doesn't need a 200MB browser.
- **CAPTCHA solving** — CloakBrowser prevents CAPTCHAs from appearing, it doesn't solve them. If a CAPTCHA still shows, you need a solver (2captcha, capsolver) downstream.
- **Pure HTTP scraping** of unprotected JSON endpoints — `curl`/`httpx` is enough. Don't reach for a stealth browser if the site has no JS challenge.

## Reference detail

- `references/test-targets.md` — canonical detection sites with expected baseline behavior (what passing/failing each one tells you about the stack), and a recorded run.
