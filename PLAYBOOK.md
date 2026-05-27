# Stealth Browser Automation — Agent Playbook

Single-file playbook for any AI coding agent (Claude Code, Cursor, OpenCode, Aider, Continue, OpenClaude, Hermes Agent, etc.) or human. Drop this into your project, reference it from your agent's instruction file, or read it top-to-bottom.

The repo it lives in: <https://github.com/Hawaiine/oasisic-stealth-browser-skill>

---

## When to load / use this playbook

Load this when any of the following is true:

- Stock Playwright / Puppeteer / Selenium gets a 403 "Just a moment..." / "Performing security verification" page.
- You need to bypass Cloudflare Turnstile (non-interactive or managed), FingerprintJS, BrowserScan, ShieldSquare, nodriver checks.
- The user asks "can X bypass CF" / "how do I scrape this protected site" / mentions a stealth-browser tool.
- Existing automation works locally but breaks on CI / VPS due to headless detection.
- You need a drop-in replacement for `playwright-stealth`, `undetected-chromedriver`, `puppeteer-extra-plugin-stealth` that doesn't break on every Chrome update.

---

## The tool: CloakBrowser

Source-level patched Chromium for sites that detect or block Playwright / Puppeteer / Selenium. Install: `pip install cloakbrowser` → `cloakbrowser install` (~206MB stealth Chromium binary). Patches are compiled into the C++, not injected at runtime, so detection sites see a real browser because it *is* a real browser.

| Tool | Patch level | Cloudflare Turnstile | Survives Chrome updates |
|---|---|---|---|
| `playwright-stealth` | JS injection | Sometimes | Breaks often |
| `undetected-chromedriver` | Config patches | Sometimes | Breaks often |
| nodriver / Camoufox | C++ (Firefox fork) | Pass | Yes, but unstable |
| **CloakBrowser** | C++ Chromium source | **Pass** | Yes, actively maintained |

If a session uses `playwright-stealth` and gets blocked, switch to CloakBrowser before touching anything else.

---

## The two-tier playbook

### Tier-1 — 80% of sites, headless OK

Just install and call `launch()`. No proxy, no Xvfb. Empirically beats nowsecure.nl, BrowserScan bot-detection, FingerprintJS demo, generic CF-protected pages that only check fingerprint signals.

```python
from cloakbrowser import launch
browser = launch(humanize=True)              # auto-downloads binary on first run
page = browser.new_page()
page.goto("https://target.com")
browser.close()
```

### Tier-2 — aggressive sites

Full CF Bot Management, Turnstile interactive, DataDome, Kasada, 极验 GeeTest. These do behavioral + IP + ML scoring. Datacenter IPs alone will trip them even with perfect fingerprints.

```python
browser = launch(
    proxy="http://user:pass@residential-host:port",  # MUST be residential
    geoip=True,        # match TZ + locale to proxy IP (auto WebRTC IP spoof)
    headless=False,    # under Xvfb on Linux servers
    humanize=True,     # Bezier mouse, per-character typing, realistic scroll
)
```

On a headless server, run under Xvfb: `xvfb-run -a python script.py`.

---

## Install + first-run

```bash
mkdir -p stealth && cd stealth
python -m venv .venv && source .venv/bin/activate
pip install cloakbrowser
cloakbrowser install      # ~206MB download, ~30s
```

Binary lands under `~/.cloakbrowser/chromium-<ver>/chrome` and auto-updates in background.

System deps (Debian/Ubuntu): `libnss3 libatk-bridge2.0-0 libatk1.0-0 libgbm1 libasound2 xvfb` — present out of the box on most server images.

CloakBrowser exports a Playwright-compatible API; existing Playwright code migrates with one import swap.

---

## Diagnose first — IP-side vs fingerprint-side

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

| Signal | IP-layer block | Challenge-layer block |
|---|---|---|
| HTTP status | 403 | 403 (often) or 200 stuck on challenge |
| `cf-mitigated` header | `challenge` | `challenge` |
| Turnstile iframe in DOM | **absent** | **present** |
| Repeat behavior | Identical 403 every time, no variance | Sometimes succeeds, varies with humanize/timing |
| Ray ID | Present | Present |
| What helps | Different egress IP (residential proxy / SSH SOCKS5 to home) | Tweak headed/humanize/cookies |

If iframe is absent, **no amount of cloakbrowser tuning will help**. Stop and switch egress.

---

## Pitfalls discovered in real testing

These cost hours when discovered the hard way. Listed roughly in order of how often they bite.

- **`Browser Tampering: Yes 🖥️🔧` on FingerprintJS** even when `Bot: Not detected`. The C++ patches *are* visible to fingerprint.com's tampering heuristic. Bot-score-only sites pass; sites that gate on tampering will reject. Mitigation: tier-2 (proxy + geoip) sometimes resolves; otherwise no clean fix today.

- **Datacenter IP → CF 403 even on tier-1.** A nopecha CF demo returned `HTTP 403, Ray ID …, Performing security verification` despite clean fingerprints. ISP/ASN is part of the score. Don't blame the patches; bring a residential proxy. Confirm with the diagnose step above.

- **Timezone / IP mismatch is its own detection signal.** Without `geoip=True` the browser reports `timezone: UTC, getTimezoneOffset: 0` while the egress IP geo-locates elsewhere. Bot-management ML cross-checks this. Always pair `proxy=` with `geoip=True` in tier-2; never run tier-2 with one and not the other.

- **Pure headless can fail Turnstile interactive / managed.** Some sites cross-check headless heuristics (e.g. window focus, viewport timing) independent of fingerprint. Promote to `headless=False` under Xvfb before adding more flags.

- **`xvfb-run` fails with `xauth command not found`** on minimal Debian/Ubuntu containers without root to `apt install xauth`. Workaround — start Xvfb directly and export DISPLAY:
  ```bash
  Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
  DISPLAY=:99 python script.py
  ```
  Verify with `pgrep -a Xvfb` and `ls /tmp/.X11-unix/X99`. This bypasses the `xvfb-run` wrapper entirely and works as a non-root user.

- **Manually unpacking Chromium via `python -c "zipfile.ZipFile(...).extractall(...)"` strips the Unix `+x` mode bit.** Browser launches with `chrome_crashpad_handler: Permission denied (13)` then SIGTRAP / `Received signal 6`. Happens when `unzip` isn't installed on a minimal container and you fall back to Python's stdlib (Python's `zipfile` doesn't preserve POSIX permissions). Fix:
  ```bash
  cd <chromium-dir>/chrome-linux64
  find . -type f -exec sh -c 'head -c 4 "$1" | grep -q ELF && chmod +x "$1"' _ {} \;
  ```
  Then re-launch. Cleaner: install `unzip` (`apt install unzip`) before extracting. CloakBrowser's own installer doesn't have this problem because it shells out to `unzip`; the bug only appears when hand-rolling a Playwright Chromium install in a `unzip`-less environment.

- **Playwright searches for `chrome-linux/chrome` not `chrome-linux64/chrome`.** When you manually install Chromium for Testing (`cdn.playwright.dev/builds/cft/<ver>/linux64/chrome-linux64.zip`), the archive extracts to `chrome-linux64/`. Symlink it: `ln -sfn chrome-linux64 chrome-linux` inside the version directory. Also pass `channel='chromium'` to `launch()` — the default selects `chromium_headless_shell`, which is a *different* binary that won't be present unless you installed it separately. Mixed install: you can symlink one Playwright browsers dir into another so a single `PLAYWRIGHT_BROWSERS_PATH` resolves both.

- **First-run downloads 206MB.** Account for it in cron / CI; cache `~/.cloakbrowser/` between runs.

- **Ko-fi banner prints to stdout** every install. Strip when capturing logs.

- **Screenshots can lie** — always check `response.status` and grep page body for blocking markers (`just a moment`, `checking your browser`, `verifying you are human`, `attention required`, `access denied`, `performing security verification`, `ray id`). A 403 often still renders a "Just a moment..." page that a naive title check passes.

- **Use `launch_persistent_context(user_data_dir=...)` for repeat visits** — keeps cookies / localStorage across sessions, bypasses incognito-detection signals, and lets a successful CF clearance cookie persist for hours. Cheaper than burning a fresh challenge per run.

- **Cloudflare Turnstile widgets render in a closed shadow root.** `document.querySelectorAll('iframe')` and `document.getElementsByTagName('iframe')` return empty even when the widget is fully visible and functional. Use `page.frames` (Playwright/CDP-level) to detect the CF iframe — its URL matches `challenges.cloudflare.com/.../turnstile/...`. Do NOT call `page.set_viewport_size()` after `goto()`; it can re-trigger CF's bot-score and break challenge mounting. Set viewport at context creation (or rely on Xvfb's screen size).

- **Turnstile interactive checkbox in tier-2 (headed Xvfb): blind-click works.** Because the widget lives in a closed shadow root, neither DOM queries nor `frame_locator` can find the visible checkbox to click. Workaround: take a screenshot, ask vision for pixel coords of the unchecked checkbox, then `page.mouse.click(x, y, delay=80)` with a humanized approach (move-then-click in 2-3 hops). Token reliably appears within 30-90s after click. The checkbox sits ~30px from the widget's left edge.

- **`render=explicit` + `window.turnstile` undefined ≠ blocked.** When you intercept early via `add_init_script`, the patched `window.turnstile` getter/setter prevents the real script from initializing. Don't add init-scripts that touch `window.turnstile`. If you need to introspect the API, use page-level `page.evaluate` after the widget is already mounted.

---

## Cheap residential-IP options when no proxy budget

Tier-2 needs residential egress. Before paying for BrightData / Smartproxy / IPRoyal, check what's already available:

- **Your home network.** If you have residential broadband, run `ssh -D 1080 -N user@home-box` from the server, then point CloakBrowser at `proxy="socks5://127.0.0.1:1080"` plus `geoip=True`. Free, real residential ASN, real geolocation.
- **Mobile tethering / 5G dongle.** Most carrier mobile IPs are classified residential / mobile by CF; works for low-volume scraping.
- **A friend / second home.** Same SOCKS5 trick. CloakBrowser supports SOCKS5 natively (`proxy="socks5://user:pass@host:port"`).
- Only fall back to paid residential proxies (IPRoyal pay-as-you-go is cheapest at ~$2/GB) when none of the above is available.

---

## Verification probe

A ready-to-run probe lives at [`scripts/probe.py`](./scripts/probe.py) — runs the stealth browser against four canonical detection sites (CF + nodriver, FingerprintJS demo, BrowserScan, Cloudflare Turnstile demo), saves screenshots + JSON results, and uses both HTTP status and body-text heuristics to call PASS/FAIL. Run it whenever:

- Validating a fresh install
- Sanity-checking after a CloakBrowser version bump
- Diagnosing whether a target failure is fingerprint-side or IP-side (probe nowsecure.nl alone — if that fails too, install is broken; if only your target fails, it's IP/behavior, go tier-2)

```bash
cd /path/to/cloakbrowser-venv && source .venv/bin/activate
python scripts/probe.py            # headless
XVFB=1 xvfb-run -a python scripts/probe.py  # headed
```

---

## When CloakBrowser is the wrong tool

- **Sign-in / check-in flows that expose a JSON API** → hit the API directly with a session cookie. Faster, idempotent, doesn't need a 200MB browser. Reverse-engineer from the JS bundle.
- **CAPTCHA solving** — CloakBrowser prevents CAPTCHAs from appearing, it doesn't solve them. If a CAPTCHA still shows, you need a downstream solver (2captcha, capsolver).
- **Pure HTTP scraping** of unprotected JSON endpoints — `curl`/`httpx` is enough. Don't reach for a stealth browser if the site has no JS challenge.
- **DataDome, Kasada, 极验 GeeTest, PerimeterX** — README acknowledges these. Headed + residential is *necessary but not always sufficient*. Plan for fallback: solver service or human-in-the-loop.

---

## Reference detail

- [`references/test-targets.md`](./references/test-targets.md) — canonical detection sites with expected baseline behavior (what passing/failing each one tells you about the stack), and a recorded run.
