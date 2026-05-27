"""
CloakBrowser detection-site probe.

Runs the stealth Chromium against four canonical detection targets and emits
PASS/FAIL based on HTTP status + body-text heuristics (titles lie — a 403 CF
challenge page often has a normal-looking title).

Usage:
    # headless (datacenter IP, default — tier-1 baseline)
    python scripts/probe.py

    # headed under Xvfb (tier-2 baseline; pair with PROXY=... if testing aggressive sites)
    XVFB=1 xvfb-run -a python scripts/probe.py

Env:
    XVFB=1     run headed (otherwise headless)
    PROXY=...  optional proxy URL passed to launch(proxy=...)
    GEOIP=1    enable geoip TZ/locale match (only meaningful with PROXY)
    OUT=dir    output dir for screenshots + JSON (default /tmp/cloak-probe)
"""
import os, json, sys
from pathlib import Path
from cloakbrowser import launch

OUT = Path(os.environ.get("OUT", "/tmp/cloak-probe"))
OUT.mkdir(parents=True, exist_ok=True)
HEADLESS = os.environ.get("XVFB") != "1"
PROXY = os.environ.get("PROXY") or None
GEOIP = os.environ.get("GEOIP") == "1"

# (name, url, post_load_wait_sec, what_a_fail_means)
TARGETS = [
    ("nowsecure_cf",      "https://nowsecure.nl/",                          12, "install/CDP signals broken — should always pass"),
    ("browserscan_bot",   "https://www.browserscan.net/bot-detection",      10, "surface fingerprint patches inactive — reinstall"),
    ("fpjs_demo",         "https://demo.fingerprint.com/playground",        10, "lost bot score — upgrade cloakbrowser"),
    ("turnstile_demo",    "https://nopecha.com/demo/cloudflare",            12, "expected on tier-1 datacenter IP; needs tier-2"),
]

# Body-text markers that mean we're stuck on a challenge page even if HTTP looked OK
BLOCK_MARKERS = [
    "just a moment", "checking your browser", "verifying you are human",
    "attention required", "access denied", "performing security verification",
]

def main() -> int:
    mode = "headed" if not HEADLESS else "headless"
    print(f"[probe] mode={mode} proxy={'yes' if PROXY else 'no'} geoip={GEOIP}")

    launch_kwargs = {"headless": HEADLESS, "humanize": True}
    if PROXY:
        launch_kwargs["proxy"] = PROXY
        if GEOIP:
            launch_kwargs["geoip"] = True

    results = {}
    browser = launch(**launch_kwargs)
    try:
        ctx = browser.new_context()
        for name, url, wait, why in TARGETS:
            page = ctx.new_page()
            entry = {"url": url, "ok": False, "title": None, "http_status": None,
                     "body_snippet": None, "screenshot": None, "fail_means": why}
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(wait * 1000)
                entry["http_status"] = resp.status if resp else None
                entry["title"] = page.title()
                body = page.evaluate(
                    "() => document.body && document.body.innerText.slice(0, 600)"
                ) or ""
                entry["body_snippet"] = body
                shot = OUT / f"{mode}_{name}.png"
                page.screenshot(path=str(shot), full_page=False)
                entry["screenshot"] = str(shot)
                low = body.lower()
                blocked = any(m in low for m in BLOCK_MARKERS)
                http_ok = (entry["http_status"] or 0) < 400
                entry["ok"] = http_ok and not blocked
            except Exception as e:
                entry["err"] = f"{type(e).__name__}: {e}"
            finally:
                try: page.close()
                except Exception: pass
            results[name] = entry
            verdict = "PASS" if entry["ok"] else "FAIL"
            print(f"[{mode}] {verdict:4s} {name:20s} http={entry['http_status']} title={entry['title']!r}")
            if not entry["ok"]:
                print(f"             ↳ fail means: {why}")
    finally:
        try: browser.close()
        except Exception: pass

    out_path = OUT / f"results_{mode}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"[probe] wrote {out_path}")

    # Exit non-zero if any of the *baseline* targets (the first three) failed —
    # turnstile_demo is expected to fail on tier-1, so it doesn't gate the exit code.
    baseline_fail = any(not results[n]["ok"] for n in ("nowsecure_cf", "browserscan_bot", "fpjs_demo")
                        if n in results)
    return 1 if baseline_fail else 0


if __name__ == "__main__":
    sys.exit(main())
