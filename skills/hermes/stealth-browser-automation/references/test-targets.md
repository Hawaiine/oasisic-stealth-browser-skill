# Canonical Detection Sites

Use these targets to triangulate *what* is failing when a real-world site blocks you. Each tells you something different about the stack.

## The four-target probe

| Target | What it tests | Fail signal | What a fail tells you |
|---|---|---|---|
| `https://nowsecure.nl/` | CF + nodriver-style automation flag detection | HTTP 403 / "Just a moment..." | Install is broken or webdriver/CDP signals are leaking. CloakBrowser should always pass this. |
| `https://www.browserscan.net/bot-detection` | webdriver / UA / CDP / navigator surface | Test Results: BOT (red) | Surface fingerprint patches not active. Reinstall binary. |
| `https://demo.fingerprint.com/playground` | Commercial-grade fingerprint + tampering ML | `Bot: Detected` | Lost the bot-score check. Note: `Browser Tampering: Yes` is **expected** even when bot=undetected — that's a separate signal. |
| `https://nopecha.com/demo/cloudflare` | Full CF Bot Management + Turnstile interactive | HTTP 403, Ray ID, "Performing security verification" | Tier-1 (datacenter + headless) is not enough. Promote to tier-2 (residential proxy + Xvfb headed + humanize). |

## Recorded baseline (CloakBrowser 0.3.31, Chromium 146.0.7680.177.5, Linux Debian 13)

Tier-1 only: `launch(humanize=True)`, no proxy, headless, datacenter-class egress IP.

```
nowsecure.nl                        ✅ HTTP 200, body "NOWSECURE BY NODRIVER"
browserscan.net/bot-detection       ✅ HTTP 200, "Test Results: Normal" (4/4 green)
demo.fingerprint.com/playground     ✅ HTTP 200, Bot: Not detected, Visitor ID issued
                                      ⚠️ Browser Tampering: Yes 🖥️🔧
                                      ⚠️ UA reported as Chrome 146 / Windows 11 (spoofed)
nopecha.com/demo/cloudflare         ❌ HTTP 403, Ray ID a01f6c9f1aee4bac
                                      "Performing security verification"
```

Conclusion of this baseline: **fingerprint patches are working, but Cloudflare's full Bot Management still rejects datacenter-IP traffic regardless of clean signals.** Promote to tier-2 for that site.

## How to read mixed results on a real target

- **All four pass except your target** → IP / behavior / site-specific JS challenge. Add `proxy=`, `geoip=True`, headed, humanize. Maybe add a real cookie/session warmup.
- **nopecha fails, others pass** → expected baseline; tier-1 is fine for everyday work, only need tier-2 for sites at nopecha's protection level.
- **fingerprint.com `Bot: Detected`** → upgrade CloakBrowser (`cloakbrowser update`); the fingerprint patches are stale.
- **nowsecure or browserscan fails** → install is broken or you're not actually launching the CloakBrowser binary (check `launch()` is from `cloakbrowser`, not `playwright`).
- **fingerprint.com shows `Browser Tampering: Yes`** but bot=No → ignore for most use cases; only matters if your target site explicitly checks the tampering flag.
- **bot.incolumitas.com** is a useful supplementary target — it returns a structured JSON-style scoreboard. Expected baseline: `intoli` 6/6 OK, `fpscanner` 14/15 OK with **only `WEBDRIVER: FAIL`** (W3C spec field, can't be removed without breaking the API surface). Anything more than that one fail = patches degraded.

## Smoking-gun signals when CF rejects at the IP layer

Distinguish "challenge failed" from "IP refused" — they need totally different fixes:

| Signal | IP-layer block | Challenge-layer block |
|---|---|---|
| HTTP status | 403 | 403 (often) or 200 stuck on challenge |
| `cf-mitigated` header | `challenge` | `challenge` |
| Turnstile iframe in DOM | **absent** (`document.querySelector('iframe[src*="challenges.cloudflare.com"]')` → null) | **present** |
| Repeat behavior | Identical 403 every time, no variance | Sometimes succeeds, varies with humanize/timing |
| Ray ID | Present | Present |
| What helps | Different egress IP (residential proxy / SSH SOCKS5 to home box) | Tweak headed/humanize/cookies |

If iframe is absent **no amount of cloakbrowser tuning will help**. Stop and switch egress.

## What CloakBrowser DOES NOT solve

- **DataDome, Kasada, 极验, PerimeterX** — README acknowledges these. Headed + residential is necessary but not always sufficient. Plan for fallback: solver service or human-in-the-loop.
- **CAPTCHAs that actually appear** — CloakBrowser prevents them; once shown, you need a solver.
- **Account-bound rate limits** — fingerprint stealth doesn't help if the site rate-limits your *account*. Use rotating accounts or back off.

## Useful page-body markers for blocked detection

When a screenshot looks legit but the page is actually a CF challenge, grep body text for any of:

```
just a moment
checking your browser
verifying you are human
attention required
access denied
performing security verification
ray id
```

Always combine with `response.status` — a 403 with a "Just a moment..." page can fool a title-only check.
