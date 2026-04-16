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

## Get an API Key

Get free credits at [nopecha.com](https://nopecha.com). Set as environment variable:

```bash
export NOPECHA_API_KEY="your-key"
```

## License

MIT
