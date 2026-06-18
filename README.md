# auto-captcha

[![PyPI version](https://img.shields.io/pypi/v/auto-captcha)](https://pypi.org/project/auto-captcha-solver/)
[![Python](https://img.shields.io/pypi/pyversions/auto-captcha)](https://pypi.org/project/auto-captcha-solver/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-blue)](#mcp-server)
[![Hermes Skill](https://img.shields.io/badge/Hermes-Skill-gold)](#hermes-skill)

Universal captcha solver for Playwright browser automation. Detects hCaptcha and reCAPTCHA v2, solves them via the NopeCHA API, and injects tokens — so your scripts never get stuck.

```
Your script → page loads → captcha detected → NopeCHA API → token injected → continue
```

## Install

```bash
pip install auto-captcha-solver
python -m playwright install chromium
```

## Quick Start

```python
from auto_captcha_solver import smart_page

with smart_page(api_key="your-key") as page:
    page.goto("https://protected-site.com")
    page.fill("#email", "user@example.com")
    page.click("#submit")   # captcha auto-solved
```

## Three Ways to Use

### 1. `smart_page()` — Context Manager (easiest)

```python
from auto_captcha_solver import smart_page

with smart_page(api_key="your-key") as page:
    page.goto("https://example.com")
    page.fill("#email", "user@test.com")
    page.click("#submit")
    print(page.captcha_log)  # [{'type': 'hcaptcha', 'status': 'solved'}]
```

### 2. `SmartPage` — Wrap Existing Browser

```python
from auto_captcha_solver import SmartPage
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True)
page = SmartPage(browser.new_page(), api_key="your-key")

page.goto("https://example.com")
page.fill("#input", "value")
```

### 3. `CaptchaSolver` — Full Control

```python
from auto_captcha_solver import CaptchaSolver

solver = CaptchaSolver(api_key="your-key")

captchas = solver.detect(page)       # [{'type': 'hcaptcha', 'sitekey': '...'}]
result = solver.solve("hcaptcha", sitekey, url)   # CaptchaResult(success=True, token='...')
solver.inject(page, "hcaptcha", result.token)
results = solver.auto_solve(page)    # detect + solve + inject
```

## CLI

```bash
auto-captcha-solver credits --key YOUR_KEY           # Check NopeCHA balance
auto-captcha-solver detect --url https://example.com # Detect captchas
auto-captcha-solver solve --url https://example.com  # Solve captchas
```

## MCP Server

Works with Claude Code, OpenClaw, Cursor, and any MCP-compatible agent.

```bash
claude mcp add auto-captcha -- python -m auto_captcha_solver.mcp_server
```

Or in your MCP config:

```json
{
  "mcpServers": {
    "auto-captcha": {
      "command": "python",
      "args": ["-m", "auto_captcha_solver.mcp_server"],
      "env": {"NOPECHA_API_KEY": "your-key"}
    }
  }
}
```

**Tools provided:**
- `captcha_detect` — detect captchas on a URL
- `captcha_solve` — detect and solve all captchas
- `captcha_credits` — check NopeCHA credit balance

## Hermes Skill

Copy the `hermes-skill/` directory to `~/.hermes/skills/auto-captcha-solver/` and set `NOPECHA_API_KEY` in your `.env`.

## Supported Captcha Types

| Type | Detection | Speed | Reliability |
|------|-----------|-------|-------------|
| hCaptcha (checkbox) | iframe + DOM | 10-40s | High |
| hCaptcha (enterprise) | iframe + DOM | 10-40s | High |
| reCAPTCHA v2 | iframe + DOM | 60-120s+ | Medium (queue) |

**Coming soon:** reCAPTCHA v3, Cloudflare Turnstile, FunCAPTCHA — [track progress](../../issues)

## Pitfalls

- **reCAPTCHA queues are slow** — can take 60-120+ seconds during peak
- **Each solve costs 1 credit** — check with `solver.get_credits()`
- **Headless detection** — some sites block headless; use `headless=False`
- **Lazy-loaded captchas** — add `time.sleep()` after actions that might trigger them

## Production: Proxies & Sticky Sessions

Solving captchas is only one part of stable long-term scraping. Modern sites cross-validate **IP identity**, **persistent cookies**, and **request behavior** as a single risk signal. Even when every challenge is solved successfully, an unstable request pipeline will keep triggering anti-bot restrictions.

For crawlers that run for hours or days, pair this library with **residential proxies that support sticky sessions**:

- **Rotate between sessions** — assign each browser context or worker its own proxy endpoint so traffic is spread across IPs.
- **Keep the same IP within a session** — after a captcha is solved, all follow-up requests (navigation, XHR, cookies) must leave from the same IP that earned the token.
- **Match proxy on both sides** — configure the same sticky proxy for Playwright *and* for the NopeCHA solve request so the token and subsequent page loads share one identity.

```python
from playwright.sync_api import sync_playwright
from auto_captcha_solver import CaptchaSolver

# Same sticky residential proxy for browser traffic and token API
proxy = {
    "scheme": "http",
    "host": "gate.provider.com",
    "port": 7777,
    "username": "user-session-abc123",  # session id pins the IP
    "password": "secret",
}

playwright_proxy = {
    "server": f"http://{proxy['host']}:{proxy['port']}",
    "username": proxy["username"],
    "password": proxy["password"],
}

solver = CaptchaSolver(api_key="your-key", proxy=proxy)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, proxy=playwright_proxy)
    page = browser.new_page()
    page.goto("https://cloudflare-heavy-site.com")
    solver.auto_solve(page)  # token solved from the same IP as the browser
```

**Practical tips:**

- One sticky session per browser context — do not rotate mid-crawl after a solve.
- Reuse cookies/storage for the lifetime of that session; discard the context when you rotate IPs.
- For Cloudflare-heavy targets (e.g. SERP crawling), residential sticky proxies noticeably reduce repeat challenges compared to captcha solving alone.

> Residential providers with session pinning work well with this pattern. For example, [Novada](https://developer.novada.com/novada/proxies/rotating-residential-proxy/session-type) pins an IP by appending `session-{id}` to the proxy username (e.g. `USERNAME-zone-res-session-job42:PASSWORD` on `super.novada.pro:7777`). Any provider that supports sticky sessions and HTTP proxy auth is fine — the key is keeping browser and solver traffic on the same IP.

## Get an API Key

Get free credits at [nopecha.com](https://nopecha.com). Set as environment variable:

```bash
export NOPECHA_API_KEY="your-key"
```

## License

MIT
