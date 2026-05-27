# Stealth Browser Automation Playbook
### 反爬虫战场的实战手册 · 给所有 AI agent 和真人用的

> **一句话简介 (TL;DR)**
> Cloudflare 又把你拦在"Just a moment..."那一页了？这是一份在真实战场上磨出来的手册，配套一个能直接 drop-in 替换 Playwright 的隐身浏览器（[CloakBrowser](https://pypi.org/project/cloakbrowser/)），帮你穿过 Cloudflare、Turnstile、FingerprintJS、BrowserScan、DataDome 的层层关卡。
>
> **80% 的检测站点**只要 `launch(humanize=True)` 一行代码就能过。剩下 20% 的硬骨头（CF Bot Management 全开、Turnstile 互动验证、DataDome、Kasada、极验）需要 tier-2：住宅代理 + Xvfb 有头模式 + geoip 时区匹配。两套打法都在下面。

---

## 这个项目解决什么问题

你写了一个爬虫，本地跑得好好的，丢到服务器上就 403。你换了 `playwright-stealth`，还是 403。换 `undetected-chromedriver`，过两周 Chrome 一更新又挂了。

问题的根源是：**反爬虫这事已经不是 1v1 的代码博弈了，而是 ML 评分系统**。Cloudflare、FingerprintJS、DataDome 在背后给每个请求打分 —— 浏览器指纹、行为模式、IP 段、TLS 指纹，全维度打分一起看。你光把 webdriver 标志改成 false，分数才扣两分而已。

CloakBrowser 的思路是：**不在运行时打补丁，直接改 Chromium 源码重新编译**。所以检测站点看到的是一个"真"浏览器 —— 因为它真的就是。配合这本手册里总结的 tier-1/tier-2 双层策略，能把大部分 CF 站点啃下来。

This repo distills hands-on findings from real targets: **what works tier-1 (headless, datacenter IP), when to escalate to tier-2 (residential proxy + Xvfb headed + humanize + geoip), and the pitfalls that cost hours to discover.**

It ships in two formats:

- **[`PLAYBOOK.md`](./PLAYBOOK.md)** — 单文件手册，丢给任何 agent 都能读（Claude Code、Cursor、OpenCode、Aider、Continue、OpenClaude，或者真人）
- **[`skills/hermes/stealth-browser-automation/`](./skills/hermes/stealth-browser-automation/)** — [Hermes Agent](https://hermes-agent.nousresearch.com) 原生 skill 格式，clone 完直接 `cp -r` 进 `~/.skills/`

A ready-to-run **`scripts/probe.py`** runs your install against four canonical detection sites and reports PASS/FAIL with screenshots. 装完先跑一遍，确认武器没问题再上战场。

---

## 一图看懂两层打法

```
┌─────────────────────────────────────────────────────────────┐
│  Tier-1  ── 便装上街，对付 80% 的检测站点                   │
│                                                             │
│      launch(humanize=True)                                  │
│      ├── headless 无头                                      │
│      ├── 数据中心 IP 也行                                   │
│      └── 不需要代理                                         │
│                                                             │
│      ✓ nowsecure.nl                                         │
│      ✓ BrowserScan bot detection                            │
│      ✓ FingerprintJS demo (Bot: Not detected)               │
│      ✓ 大部分只看指纹的 CF 防护                             │
└─────────────────────────────────────────────────────────────┘
                          ⬇ 顶不住时升级
┌─────────────────────────────────────────────────────────────┐
│  Tier-2  ── 穿邻居衣服借邻居车，啃硬骨头                    │
│                                                             │
│      launch(                                                │
│          proxy="http://user:pass@residential:port",         │
│          geoip=True,        # 时区/语言自动匹配代理 IP      │
│          headless=False,    # Linux 服务器配 Xvfb           │
│          humanize=True,     # 贝塞尔曲线鼠标 + 真人打字     │
│      )                                                      │
│                                                             │
│      ✓ Cloudflare Bot Management 全开                       │
│      ✓ Turnstile 互动验证                                   │
│      ⚠ DataDome / Kasada / 极验 (尽力但不保证)              │
└─────────────────────────────────────────────────────────────┘
```

> **关键认知 / Key insight**
> 数据中心 IP 就像穿西装去夜店蹦迪 —— 衣冠楚楚但一眼假。CF 在 IP 这一层就把你 403 掉了，根本不会让你的浏览器有机会展示指纹。**先诊断再调参**，否则你只是在改一个 CF 根本没看到的浏览器。

---

## 为什么不用 playwright-stealth / undetected-chromedriver / nodriver

| 工具 | 补丁层级 | Cloudflare Turnstile | 抗 Chrome 升级 |
|---|---|---|---|
| `playwright-stealth` | 运行时注入 JS | 偶尔能过 | 经常崩 |
| `undetected-chromedriver` | 配置改改 | 偶尔能过 | 经常崩 |
| nodriver / Camoufox | C++ 改 (Firefox 分支) | 能过 | 能扛但不稳 |
| **CloakBrowser** | **C++ 改 Chromium 源码** | **稳过** | **稳，活跃维护** |

补丁编进 C++、不是运行时注入 —— 这是和其他方案最本质的区别。如果你的 session 用 `playwright-stealth` 被拦了，先换 CloakBrowser，别先怀疑别的。

---

## 安装 / Install

```bash
mkdir -p stealth && cd stealth
python -m venv .venv && source .venv/bin/activate
pip install cloakbrowser
cloakbrowser install      # ~206MB 二进制，~30s 下完
```

Chromium 二进制装在 `~/.cloakbrowser/chromium-<ver>/chrome`，会在后台自动更新。

**Debian / Ubuntu 系统依赖：** `libnss3 libatk-bridge2.0-0 libatk1.0-0 libgbm1 libasound2 xvfb` —— 主流服务器镜像基本都自带。

CloakBrowser 暴露的是 Playwright 兼容 API，已有 Playwright 代码改一行 import 就能迁过来。

---

## Hello world

```python
from cloakbrowser import launch

# Tier-1: 一行搞定 80% 的站点
browser = launch(humanize=True)
page = browser.new_page()
page.goto("https://nowsecure.nl/")
print(page.title())
browser.close()
```

Tier-2 升级版：

```python
browser = launch(
    proxy="http://user:pass@residential-host:port",  # 必须是住宅 IP
    geoip=True,        # 时区/locale 跟代理 IP 对齐 (顺手伪造 WebRTC IP)
    headless=False,    # Linux 服务器要配 Xvfb
    humanize=True,     # 贝塞尔鼠标 + 逐字符打字 + 真实滚动
)
```

无头服务器跑有头模式： `xvfb-run -a python script.py`

---

## 装完先跑探针 / Verify with the probe

[`scripts/probe.py`](./scripts/probe.py) 会拿你的 stealth 装备去打四个检测站，每个截图存档，根据 HTTP 状态 + 页面文本判 PASS/FAIL（光看 title 会被骗 —— 一个 CF 403 challenge 页的 `<title>` 也可能正常）。

```bash
# Tier-1: 无头 + 数据中心 IP
python scripts/probe.py

# Tier-2: 有头 + 住宅代理
PROXY="http://user:pass@residential-host:port" GEOIP=1 \
  XVFB=1 xvfb-run -a python scripts/probe.py
```

输出落在 `/tmp/cloak-probe/`（用 `OUT=` 改）。

**实测基线** (CloakBrowser 0.3.31, Chromium 146, Linux Debian 13, 数据中心级出口 IP, 仅 tier-1)：

```
nowsecure.nl                        ✅ HTTP 200, 页面 "NOWSECURE BY NODRIVER"
browserscan.net/bot-detection       ✅ HTTP 200, "Test Results: Normal" (4/4 全绿)
demo.fingerprint.com/playground     ✅ HTTP 200, Bot: Not detected, 拿到 Visitor ID
                                      ⚠️ Browser Tampering: Yes 🖥️🔧
                                      ⚠️ UA 报为 Chrome 146 / Windows 11 (伪造的)
nopecha.com/demo/cloudflare         ❌ HTTP 403, Ray ID ...
                                      "Performing security verification"
```

最后一行的失败是**预期且有信息量的** —— 它告诉你指纹补丁工作正常，但 CF 完整版 Bot Management 在 IP 这层就把你毙了，跟你的浏览器伪装得多像没关系。这种站点必须升级到 tier-2。

---

## 失败诊断：是指纹问题还是 IP 问题？

目标站返回 403 / 卡在 challenge 时，**别瞎调浏览器参数**。先做两步分诊：

```bash
# 1. 你这台机器是什么 ASN？
curl -s "https://ipinfo.io/$(curl -s https://api.ipify.org)/json" | jq .org
# 数据中心:  "AS14061 DigitalOcean", "AS16509 Amazon", "AS36352 HostPapa"
# 住宅:      "AS4837 China Unicom", "AS7922 Comcast", "AS3320 Deutsche Telekom"

# 2. CF 是注入了 challenge 控件，还是直接在 IP 层把你打回去了？
# 在页面打开后跑这段 JS：
#   document.querySelector('iframe[src*="challenges.cloudflare.com"]')
```

| 信号 | IP 层拦截 | challenge 层拦截 |
|---|---|---|
| HTTP 状态码 | 403 | 403（常见）或 200 卡在 challenge |
| `cf-mitigated` 响应头 | `challenge` | `challenge` |
| Turnstile iframe 在 DOM | **找不到** | **能找到** |
| 重复访问行为 | 每次都是一样的 403 | 偶尔能过，看 humanize/timing |
| 怎么救 | **必须换出口 IP** | 调有头/humanize/cookie |

**iframe 找不到 + 403 = CF 在 IP 层就把你拒了，不管你浏览器调成什么样都没用。** 唯一出路是换 IP（住宅代理 / SSH SOCKS5 到家里的盒子 / 4G 网卡 等等）。

---

## 真实战场上踩过的坑 / Pitfalls discovered in real testing

按"踩坑频率"从高到低排：

- **FingerprintJS 显示 `Browser Tampering: Yes 🖥️🔧`** 哪怕 `Bot: Not detected`。C++ 补丁在 fingerprint.com 的 tampering 启发式里**是会被看到的**。只看 bot 分的站点能过；明确门槛设在 tampering 那条的站点会拒。tier-2 (proxy + geoip) 偶尔能掩盖，目前没有干净的修复方案。

- **数据中心 IP 让 CF 直接 403，连 tier-1 都顶不住。** nopecha 的 CF demo 在指纹完全干净的情况下还是返回 `HTTP 403, Ray ID ..., Performing security verification`。ISP/ASN 是评分的一部分。**别怪补丁，去拿个住宅代理。** 上面的诊断步骤能确认这一点。

- **时区和 IP 不匹配本身就是检测信号。** 不开 `geoip=True` 的话，浏览器报 `timezone: UTC, getTimezoneOffset: 0`，但出口 IP 地理位置在别处。Bot management ML 会做交叉校验。tier-2 永远 `proxy=` 和 `geoip=True` 一起用，从来不要只开一个。

- **纯无头也能在 Turnstile 互动验证上翻车。** 有些站点会交叉检查 headless 启发式（窗口聚焦、视口时序），跟指纹无关。先升级到 `headless=False` 配 Xvfb，再考虑加别的 flag。

- **`xvfb-run` 在没装 `xauth` 的极简容器里报 `xauth command not found`**，没 root 没法 `apt install`。绕开方法：直接起 Xvfb 然后导出 DISPLAY：
  ```bash
  Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
  DISPLAY=:99 python script.py
  ```
  用 `pgrep -a Xvfb` 和 `ls /tmp/.X11-unix/X99` 验证。这样绕过 `xvfb-run` 包装器，非 root 也能跑。

- **手动用 `python -c "zipfile.ZipFile(...).extractall(...)"` 解压 Chromium 会丢掉 Unix `+x` 权限位。** 浏览器启动报 `chrome_crashpad_handler: Permission denied (13)` 然后 SIGTRAP / `Received signal 6`。原因是极简容器没装 `unzip`，回退到 Python stdlib（`zipfile` 不保留 POSIX 权限）。修：
  ```bash
  cd <chromium-dir>/chrome-linux64
  find . -type f -exec sh -c 'head -c 4 "$1" | grep -q ELF && chmod +x "$1"' _ {} \;
  ```
  更干净的做法：解压前 `apt install unzip`。CloakBrowser 自己的 installer 不会有这问题，因为它直接 shell out 到 `unzip`；只有手动装 Playwright Chromium 在没 `unzip` 的环境里才会踩。

- **Playwright 找的是 `chrome-linux/chrome` 不是 `chrome-linux64/chrome`。** 手动装 Chromium for Testing (`cdn.playwright.dev/builds/cft/<ver>/linux64/chrome-linux64.zip`) 时，压缩包解出来是 `chrome-linux64/`。建个软链：`ln -sfn chrome-linux64 chrome-linux` 在版本目录里。另外 `launch()` 要传 `channel='chromium'` —— 默认会去找 `chromium_headless_shell`，那是**另一个**二进制，没单独装的话不存在。

- **首次跑要下 206MB。** 上 cron / CI 时算进时间，并把 `~/.cloakbrowser/` 缓存好。

- **每次 install 都会打印 Ko-fi 横幅** 到 stdout。日志采集时记得过滤。

- **截图会骗人** —— 一定要同时检查 `response.status` 和页面正文里的拦截关键词（`just a moment`、`checking your browser`、`verifying you are human`、`attention required`、`access denied`、`performing security verification`、`ray id`）。一个 403 页可能渲染成普通的 "Just a moment..."，只看 title 会以为成功了。

- **重复访问用 `launch_persistent_context(user_data_dir=...)`** —— 跨 session 保留 cookie / localStorage，绕过隐身模式检测，让 CF clearance cookie 能续上几小时。比每次重过一次 challenge 便宜得多。

- **Cloudflare Turnstile 控件渲染在 closed shadow root 里。** `document.querySelectorAll('iframe')` 和 `getElementsByTagName('iframe')` 都返回空 —— 哪怕控件正在你眼前显示。要用 `page.frames` (Playwright/CDP 层) 才能拿到 CF iframe，URL 形如 `challenges.cloudflare.com/.../turnstile/...`。**不要**在 `goto()` 之后调 `page.set_viewport_size()`，会重新触发 CF 评分把 challenge 挂掉。viewport 在 context 创建时一次设好（或者直接靠 Xvfb 的屏幕尺寸）。

- **Tier-2 (有头 Xvfb) 下点 Turnstile 互动复选框：盲点能用。** 控件在 closed shadow root 里，DOM query 和 `frame_locator` 都找不到那个可见的复选框。绕开方式：截图 → 让 vision 给出复选框像素坐标 → `page.mouse.click(x, y, delay=80)`，配合 2-3 跳的拟人化路径。点完 30-90 秒内 token 会稳定出现。复选框一般在控件左边缘内 ~30px。

- **`render=explicit` + `window.turnstile undefined` ≠ 被拦了。** 你用 `add_init_script` 早期介入时，那个被打了补丁的 `window.turnstile` getter/setter 反而会阻止真正的 turnstile 脚本初始化。**别**在 init script 里碰 `window.turnstile`。要看 API 的话用 `page.evaluate`，等控件已经挂载之后再调。

---

## 没预算买代理时的住宅 IP 替代方案

Tier-2 必须住宅出口。在掏钱买 BrightData / Smartproxy / IPRoyal 之前，先看看手边有什么：

- **🏠 自己家的网络。** 家里有宽带的话，从服务器 SSH 过去：`ssh -D 1080 -N user@home-box`，然后 CloakBrowser 指过去：`proxy="socks5://127.0.0.1:1080"` 加 `geoip=True`。免费、真住宅 ASN、真地理位置。
- **📱 手机热点 / 5G 上网卡。** 大部分运营商移动 IP 被 CF 归类为住宅/移动，低频抓取够用。
- **👨‍👩‍👧 朋友家 / 第二个住处。** 同样的 SOCKS5 套路。CloakBrowser 原生支持 SOCKS5：`proxy="socks5://user:pass@host:port"`。
- 实在没辙再去买付费住宅代理。IPRoyal 按量付费 ~$2/GB 算便宜的。

---

## 什么时候 CloakBrowser 是错的工具

不是所有反爬场景都该上隐身浏览器。下面这些情况掉头去用别的方案：

- **签到 / 打卡类有 JSON API 的** → 直接打 API 配 session cookie。更快、幂等、不需要 200MB 的浏览器。逆向方法：从前端 JS bundle 里挖出 endpoint。
- **真的弹出了 CAPTCHA** → CloakBrowser 是**预防** CAPTCHA 出现，不是解 CAPTCHA。真弹了你需要下游打码服务（2captcha、capsolver）。
- **目标站根本没 JS challenge，纯 HTTP 抓 JSON** → `curl` / `httpx` 就够了，别拿大炮打蚊子。
- **DataDome、Kasada、极验 GeeTest、PerimeterX** —— README 自己也承认这些。有头 + 住宅是**必要但不充分**条件。打算上这些站点时记得规划 fallback：打码服务或 human-in-the-loop。

---

## 仓库结构 / Repo layout

```
.
├── README.md                                    你正在看的文件
├── PLAYBOOK.md                                  单文件 agent 手册
├── LICENSE                                      MIT
├── scripts/
│   └── probe.py                                 4-站检测探针
├── references/
│   └── test-targets.md                          检测站点详解 + 怎么读混合结果
└── skills/
    └── hermes/
        └── stealth-browser-automation/          自包含、可直接 drop-in
            ├── SKILL.md                         Hermes Agent skill 格式
            ├── references/test-targets.md
            └── scripts/probe.py
```

---

## 怎么给不同 agent 用 / Use with various AI agents

### [Hermes Agent](https://hermes-agent.nousresearch.com)

```bash
git clone https://github.com/Hawaiine/oasisic-stealth-browser-skill.git
cp -r oasisic-stealth-browser-skill/skills/hermes/stealth-browser-automation \
      ~/.skills/devops/
hermes skills list | grep stealth-browser-automation
```

### Claude Code / Cursor / OpenCode / Aider / Continue / OpenClaude

把 [`PLAYBOOK.md`](./PLAYBOOK.md) 喂给你的 agent —— 单文件、自包含，装机步骤、双层策略、诊断流程、踩坑清单全在里面。可以提交进项目仓库、放进 agent 的 instruction 目录、或者在需要时直接 paste 相关章节。

Claude Code 专门的：
```bash
mkdir -p .claude && cp PLAYBOOK.md .claude/stealth-browser.md
# 然后在 CLAUDE.md 里 reference 它
```

### 真人

直接看 [`PLAYBOOK.md`](./PLAYBOOK.md)。跑一遍 `scripts/probe.py` 验证武器没问题。"踩过的坑"那一节是这份手册最值钱的地方。

---

## 想贡献？/ Contributing

踩到清单里没有的坑？发现一个用 tier-2 也搞不定的新站点？欢迎 PR。**贡献的关键是具体** —— 站点名 + 失败现象 + 修复方法。这个 repo 的价值在具体观察，不在泛泛而谈的建议。

---

## License

MIT —— 看 [LICENSE](./LICENSE)。

## Credits / 致谢

- [CloakBrowser](https://pypi.org/project/cloakbrowser/) —— 真正干重活的隐身 Chromium。这份手册只是它的使用心得。
- 实战观察由 [Hermes Agent](https://hermes-agent.nousresearch.com) 在真实自动化任务中积累而来。
