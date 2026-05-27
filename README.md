# Stealth Browser Automation Playbook

Battle-tested playbook for scraping and automating sites behind **Cloudflare**, **Turnstile**, **FingerprintJS**, **BrowserScan**, **DataDome** and similar anti-bot stacks — using [CloakBrowser](https://pypi.org/project/cloakbrowser/), a source-patched Chromium that drops in for Playwright.

This repo distills hands-on findings from real targets: **what works tier-1 (headless, datacenter IP), when to escalate to tier-2 (residential proxy + Xvfb headed + humanize + geoip), and the pitfalls that cost hours to discover.** It ships in two formats:

- **[`PLAYBOOK.md`](./PLAYBOOK.md)** — universal playbook readable by any agent or human (Claude Code, Cursor, OpenCode, Aider, Continue, OpenClaude, plain humans, etc.)
- **[`skills/hermes/stealth-browser-automation/`](./skills/hermes/stealth-browser-automation/)** — drop-in [Hermes Agent](https://hermes-agent.nousresearch.com) skill format with frontmatter + linked references

A ready-to-run **`probe.py`** runs your stealth install against four canonical detection sites and reports PASS/FAIL with screenshots, so you can validate the stack before pointing it at a real target.

---

## TL;DR — the two-tier playbook

```
Tier-1  ~80% of detection sites pass:  launch(humanize=True)
                                       headless, datacenter IP, no proxy
                                       beats nowsecure.nl, BrowserScan,
                                       FingerprintJS demo

Tier-2  Aggressive sites (full CF Bot Management, Turnstile interactive,
        DataDome, Kasada, 极验 GeeTest):
            launch(proxy="http://user:pass@residential-host:port",
                   geoip=True, headless=False, humanize=True)
        + run under Xvfb on Linux servers
```

If tier-1 fails on your target, **diagnose IP-side vs fingerprint-side first** (see [Diagnose the failure](#diagnose-the-failure-ip-side-vs-fingerprint-side) below) before tweaking flags. CF refuses datacenter IPs at the IP layer regardless of fingerprint quality, and no amount of browser tuning fixes that.

---

## Why CloakBrowser over the alternatives

| Tool | Patch level | Cloudflare Turnstile | Survives Chrome updates |
|---|---|---|---|
| `playwright-stealth` | JS injection | Sometimes | Breaks often |
| `undetected-chromedriver` | Config patches | Sometimes | Breaks often |
| nodriver / Camoufox | C++ (Firefox fork) | Pass | Yes, but unstable |
| **CloakBrowser** | C++ Chromium source | **Pass** | Yes, actively maintained |

Patches are compiled into the C++, not injected at runtime, so detection sites see a real browser because it *is* a real browser. If a session uses `playwright-stealth` and gets blocked, switch to CloakBrowser before touching anything else.

---

## Install

```bash
mkdir -p stealth && cd stealth
python -m venv .venv && source .venv/bin/activate
pip install cloakbrowser
cloakbrowser install      # ~206MB download, ~30s
```

Binary lands under `~/.cloakbrowser/chromium-<ver>/chrome` and auto-updates in background.

**System deps (Debian/Ubuntu):** `libnss3 libatk-bridge2.0-0 libatk1.0-0 libgbm1 libasound2 xvfb` — already present on most server images.

CloakBrowser exports a Playwright-compatible API; existing Playwright code migrates with one import swap.

---

## Hello world

```python
from cloakbrowser import launch

browser = launch(humanize=True)               # tier-1 default
page = browser.new_page()
page.goto("https://nowsecure.nl/")
print(page.title())
browser.close()
```

For tier-2:

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

## Verify the install with the probe

[`scripts/probe.py`](./scripts/probe.py) runs against four canonical detection sites, screenshots each result, and prints PASS/FAIL based on HTTP status + body-text heuristics (titles lie — a 403 CF challenge page often has a normal-looking title).

```bash
# tier-1 (headless, no proxy)
python scripts/probe.py

# tier-2 (headed under Xvfb, with proxy)
PROXY="http://user:pass@residential-host:port" GEOIP=1 \
  XVFB=1 xvfb-run -a python scripts/probe.py
```

Output goes to `/tmp/cloak-probe/` (override with `OUT=...`).

**Recorded baseline** (CloakBrowser 0.3.31, Chromium 146, Linux Debian 13, datacenter egress, tier-1 `launch(humanize=True)`):

```
nowsecure.nl                        ✅ HTTP 200, body "NOWSECURE BY NODRIVER"
browserscan.net/bot-detection       ✅ HTTP 200, "Test Results: Normal" (4/4 green)
demo.fingerprint.com/playground     ✅ HTTP 200, Bot: Not detected, Visitor ID issued
                                      ⚠️ Browser Tampering: Yes 🖥️🔧
                                      ⚠️ UA reported as Chrome 146 / Windows 11 (spoofed)
nopecha.com/demo/cloudflare         ❌ HTTP 403, Ray ID ...
                                      "Performing security verification"
```

The nopecha failure on tier-1 is **expected and informative** — it tells you that fingerprint patches are working, but full CF Bot Management still rejects datacenter IPs regardless of clean signals. Promote to tier-2 for that class of site.

---

## Diagnose the failure: IP-side vs fingerprint-side

When a target returns 403 / challenge, **don't tweak browser flags blindly**. Two-step triage:

```bash
# 1. What ASN is your egress?
curl -s "https://ipinfo.io/$(curl -s https://api.ipify.org)/json" | jq .org
# Datacenter:   "AS14061 DigitalOcean", "AS16509 Amazon", "AS36352 HostPapa"
# Residential: "AS4837 China Unicom", "AS7922 Comcast", "AS3320 Deutsche Telekom"

# 2. Did CF inject the challenge widget, or reject at IP layer?
# In the page after navigation, evaluate:
#   document.querySelector('iframe[src*="challenges.cloudflare.com"]')
```

| Signal | IP-layer block | Challenge-layer block |
|---|---|---|
| HTTP status | 403 | 403 (often) or 200 stuck on challenge |
| `cf-mitigated` header | `challenge` | `challenge` |
| Turnstile iframe in DOM | **absent** | **present** |
| Repeat behavior | Identical 403 every time | Varies with humanize/timing |
| What helps | **Different egress IP only** | Tweak headed/humanize/cookies |

**If iframe is absent and HTTP is 403, no amount of CloakBrowser tuning will help.** CF refused to even run the challenge. The only fix is a different egress IP.

---

## Pitfalls discovered in real testing

These cost hours when discovered the hard way. Listed roughly in order of how often they bite.

- **`Browser Tampering: Yes 🖥️🔧` on FingerprintJS** even when `Bot: Not detected`. The C++ patches *are* visible to fingerprint.com's tampering heuristic. Bot-score-only sites pass; sites that gate on tampering will reject. Mitigation: tier-2 (proxy + geoip) sometimes resolves; otherwise no clean fix today.

- **Datacenter IP → CF 403 even on tier-1.** Clean fingerprints don't matter when the ASN is on a deny list. Don't blame the patches; bring a residential proxy. Confirm with the diagnose step above.

- **Timezone / IP mismatch is its own detection signal.** Without `geoip=True`, the browser reports `timezone: UTC, getTimezoneOffset: 0` while the egress IP geo-locates elsewhere. Bot-management ML cross-checks this. Always pair `proxy=` with `geoip=True` in tier-2; never run tier-2 with one and not the other.

- **Pure headless can fail Turnstile interactive / managed.** Some sites cross-check headless heuristics (window focus, viewport timing) independent of fingerprint. Promote to `headless=False` under Xvfb before adding more flags.

- **`xvfb-run` fails with `xauth command not found`** on minimal Debian/Ubuntu containers without root to `apt install xauth`. Workaround — start Xvfb directly and export `DISPLAY`:
  ```bash
  Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
  DISPLAY=:99 python script.py
  ```
  Verify with `pgrep -a Xvfb` and `ls /tmp/.X11-unix/X99`.

- **Manually unpacking Chromium via `python -c "zipfile.ZipFile(...).extractall(...)"` strips the Unix `+x` mode bit.** Browser launches with `chrome_crashpad_handler: Permission denied (13)` then SIGTRAP. Python's stdlib `zipfile` doesn't preserve POSIX permissions. Fix:
  ```bash
  cd <chromium-dir>/chrome-linux64
  find . -type f -exec sh -c 'head -c 4 "$1" | grep -q ELF && chmod +x "$1"' _ {} \;
  ```
  Cleaner: install `unzip` (`apt install unzip`) before extracting. CloakBrowser's own installer uses `unzip`; this only bites when hand-rolling installs in `unzip`-less environments.

- **Playwright searches for `chrome-linux/chrome` not `chrome-linux64/chrome`.** When manually installing Chromium for Testing (`cdn.playwright.dev/builds/cft/<ver>/linux64/chrome-linux64.zip`), the archive extracts to `chrome-linux64/`. Symlink it: `ln -sfn chrome-linux64 chrome-linux` inside the version directory. Also pass `channel='chromium'` to `launch()` — the default selects `chromium_headless_shell`, a *different* binary that won't be present unless installed separately.

- **First-run downloads 206MB.** Account for it in cron / CI; cache `~/.cloakbrowser/` between runs.

- **Ko-fi banner prints to stdout** every install. Strip it when capturing logs.

- **Screenshots can lie** — always check `response.status` and grep page body for blocking markers (`just a moment`, `checking your browser`, `verifying you are human`, `attention required`, `access denied`, `performing security verification`, `ray id`). A 403 often still renders a "Just a moment..." page that a naive title check passes.

- **Use `launch_persistent_context(user_data_dir=...)` for repeat visits** — keeps cookies / localStorage across sessions, bypasses incognito-detection signals, and lets a successful CF clearance cookie persist for hours. Cheaper than burning a fresh challenge per run.

- **Cloudflare Turnstile widgets render in a closed shadow root.** `document.querySelectorAll('iframe')` and `document.getElementsByTagName('iframe')` return empty even when the widget is fully visible. Use `page.frames` (Playwright/CDP-level) to detect the CF iframe — its URL matches `challenges.cloudflare.com/.../turnstile/...`. Do NOT call `page.set_viewport_size()` after `goto()`; it can re-trigger CF's bot-score and break challenge mounting. Set viewport at context creation (or rely on Xvfb's screen size).

- **Turnstile interactive checkbox in tier-2 (headed Xvfb): blind-click works.** The widget lives in a closed shadow root, so neither DOM queries nor `frame_locator` can find the visible checkbox. Workaround: take a screenshot, ask vision for pixel coords of the unchecked checkbox, then `page.mouse.click(x, y, delay=80)` with a humanized 2-3-hop approach. Token reliably appears within 30-90s after click. Checkbox sits ~30px from the widget's left edge.

- **`render=explicit` + `window.turnstile` undefined ≠ blocked.** When you intercept early via `add_init_script`, the patched `window.turnstile` getter/setter prevents the real script from initializing. Don't add init-scripts that touch `window.turnstile`. Use page-level `page.evaluate` after the widget mounts.

---

## Cheap residential-IP options when no proxy budget

Tier-2 needs residential egress. Before paying for BrightData / Smartproxy / IPRoyal:

- **Your own home network.** SSH from the server to your home box: `ssh -D 1080 -N user@home-box`, then point CloakBrowser at `proxy="socks5://127.0.0.1:1080"` plus `geoip=True`. Free, real residential ASN, real geolocation.
- **Mobile tethering / 5G dongle.** Most carrier mobile IPs are classified residential / mobile by CF; works for low-volume scraping.
- **A friend's home / second residence.** Same SOCKS5 trick.
- Only fall back to paid residential proxies (IPRoyal pay-as-you-go ~$2/GB is cheapest) when none of the above is available.

CloakBrowser accepts SOCKS5 natively: `proxy="socks5://user:pass@host:port"`.

---

## When CloakBrowser is the wrong tool

- **Sign-in / check-in flows that expose a JSON API** → hit the API directly with a session cookie. Faster, idempotent, doesn't need a 200MB browser. Reverse-engineer from the JS bundle.
- **CAPTCHA solving** — CloakBrowser *prevents* CAPTCHAs from appearing; it doesn't solve them. If a CAPTCHA still shows, downstream solver (2captcha, capsolver) is needed.
- **Pure HTTP scraping** of unprotected JSON endpoints — `curl`/`httpx` is enough. Don't reach for a stealth browser if there's no JS challenge.
- **DataDome, Kasada, 极验 GeeTest, PerimeterX** — headed + residential is *necessary but not always sufficient*. Plan for fallback: solver service or human-in-the-loop. CloakBrowser README acknowledges these limits.

---

## Repo layout

```
.
├── README.md                                    you are here
├── PLAYBOOK.md                                  agent-readable single-file playbook
├── LICENSE                                      MIT
├── scripts/
│   └── probe.py                                 4-target detection probe
├── references/
│   └── test-targets.md                          canonical detection sites + how to read mixed results
└── skills/
    └── hermes/
        └── stealth-browser-automation/
            ├── SKILL.md                         Hermes Agent skill format
            ├── references/test-targets.md       (symlinked to ../references)
            └── scripts/probe.py                 (symlinked to ../scripts)
```

---

## Use with various AI coding agents

### [Hermes Agent](https://hermes-agent.nousresearch.com)

```bash
git clone https://github.com/Hawaiine/oasisic-stealth-browser-skill.git
cp -r oasisic-stealth-browser-skill/skills/hermes/stealth-browser-automation \
      ~/.skills/devops/
hermes skills list | grep stealth-browser-automation
```

### Claude Code / Cursor / OpenCode / Aider / Continue / OpenClaude

Point your agent at [`PLAYBOOK.md`](./PLAYBOOK.md) — it's a single self-contained file with all the install steps, the two-tier strategy, the diagnose flow, and the pitfalls list. Either commit it into your project, drop it into your agent's instruction folder, or paste the relevant section as context.

For Claude Code specifically:
```bash
mkdir -p .claude && cp PLAYBOOK.md .claude/stealth-browser.md
# then reference it from CLAUDE.md
```

### Plain humans

Read [`PLAYBOOK.md`](./PLAYBOOK.md). Run `scripts/probe.py` to validate. The pitfalls section is where the time savings live.

---

## Contributing

Hit a pitfall not in the list? Found a target that breaks tier-2 in a new way? PRs welcome. Keep additions specific (target name, what failed, what fixed it) — the value of this repo is concrete observations, not generic advice.

---

## License

MIT — see [LICENSE](./LICENSE).

## Credits

- [CloakBrowser](https://pypi.org/project/cloakbrowser/) — the actual stealth Chromium that does the heavy lifting.
- Findings recorded by [Hermes Agent](https://hermes-agent.nousresearch.com) during real-world automation work.
