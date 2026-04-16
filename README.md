# auto-captcha

Universal captcha solver for Playwright browser automation. Detects hCaptcha and reCAPTCHA v2, solves them via the NopeCHA API, and injects tokens — so your scripts never get stuck.

Works as a **Python library**, **CLI tool**, **MCP server**, and **Hermes skill**.

## Install

```bash
pip install auto-captcha
python -m playwright install chromium

# Or from source
git clone https://github.com/interfluve-wav/auto-captcha.git
cd auto-captcha
pip install -e ".[all]"
```

## Quick Start (1 line)

```python
from auto_captcha import smart_page

with smart_page(api_key="your-key") as page:
    page.goto("https://protected-site.com")
    page.fill("#email", "user@example.com")
    page.click("#submit")   # captcha auto-solved
```

## Three Ways to Use

### 1. `smart_page()` — Context Manager (easiest)

```python
from auto_captcha import smart_page

with smart_page(api_key="your-key") as page:
    page.goto("https://example.com")
    page.fill("#email", "user@test.com")
    page.click("#submit")
    print(page.captcha_log)  # [{'type': 'hcaptcha', 'status': 'solved'}]
```

### 2. `SmartPage` — Wrap Existing Browser

```python
from auto_captcha import SmartPage
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True)
page = SmartPage(browser.new_page(), api_key="your-key")

page.goto("https://example.com")
page.fill("#input", "value")
```

### 3. `CaptchaSolver` — Full Control

```python
from auto_captcha import CaptchaSolver

solver = CaptchaSolver(api_key="your-key")

captchas = solver.detect(page)       # [{'type': 'hcaptcha', 'sitekey': '...'}]
token = solver.solve("hcaptcha", sitekey, url)   # CaptchaResult(success=True, token='...')
solver.inject(page, "hcaptcha", token)
results = solver.auto_solve(page)    # detect + solve + inject
```

## CLI

```bash
# Check credits
auto-captcha credits --key YOUR_KEY

# Detect captchas
auto-captcha detect --url https://example.com --key YOUR_KEY

# Solve captchas
auto-captcha solve --url https://example.com --key YOUR_KEY
```

## MCP Server (for AI agents)

Works with Claude Code, OpenClaw, Cursor, and any MCP-compatible agent.

```bash
# Add to Claude Code
claude mcp add auto-captcha -- python -m auto_captcha.mcp_server

# Or configure in MCP config
{
  "mcpServers": {
    "auto-captcha": {
      "command": "python",
      "args": ["-m", "auto_captcha.mcp_server"],
      "env": {"NOPECHA_API_KEY": "your-key"}
    }
  }
}
```

Provides three MCP tools:
- `captcha_detect` — detect captchas on a URL
- `captcha_solve` — detect and solve all captchas
- `captcha_credits` — check NopeCHA credit balance

## Hermes Skill

Copy the `hermes-skill/` directory to `~/.hermes/skills/auto-captcha/` and set `NOPECHA_API_KEY` in your `.env`.

## Supported Captcha Types

| Type | Detection | Speed | Reliability |
|------|-----------|-------|-------------|
| hCaptcha (checkbox) | iframe + DOM | 10-40s | High |
| hCaptcha (enterprise) | iframe + DOM | 10-40s | High |
| reCAPTCHA v2 | iframe + DOM | 60-120s+ | Medium (queue) |

**Not supported:** reCAPTCHA v3 (score-based, no challenge), Cloudflare Turnstile, FunCAPTCHA

## Pitfalls

- **reCAPTCHA queues are slow** — can take 60-120+ seconds during peak
- **Each solve costs 1 credit** — check with `solver.get_credits()`
- **Headless detection** — some sites block headless; use `headless=False`
- **Lazy-loaded captchas** — add `time.sleep()` after actions that might trigger them

## NopeCHA API Key

Get free credits at [nopecha.com](https://nopecha.com). Set as environment variable:

```bash
export NOPECHA_API_KEY="your-key"
```

## License

MIT
