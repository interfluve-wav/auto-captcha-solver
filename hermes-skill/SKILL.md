---
name: auto-captcha-solver
description: Universal captcha auto-solver for Playwright browser automation. Detects hCaptcha and reCAPTCHA v2 on any page, solves via NopeCHA API, and injects tokens automatically. Drop-in CaptchaSolver class with auto_solve(page) method.
category: software-development
---

# Auto-Captcha

Auto-detect and solve captchas during Playwright browser automation using the NopeCHA API.

## When to Use

- Browser automation hits a captcha wall
- Web scraping tasks need captcha bypass
- Automated testing against captcha-protected sites
- Any Playwright script that might encounter hCaptcha or reCAPTCHA v2

## Prerequisites

- `NOPECHA_API_KEY` env var set (get free credits at https://nopecha.com)
- Python `requests` and `playwright` installed
- Playwright browser installed (`python -m playwright install chromium`)

## Quick Start

```python
from auto_captcha_solver import CaptchaSolver

solver = CaptchaSolver(api_key="your-key")

# Auto-detect + solve + inject (one-liner)
results = solver.auto_solve(page)
```

## Full API

### Detect
```python
captchas = solver.detect(page)
# Returns: [{"type": "hcaptcha"|"recaptcha2", "sitekey": "...", "url": "...", "frame": ...}]
```

### Solve
```python
result = solver.solve("hcaptcha", sitekey, page_url)
# Returns: CaptchaResult(success=True, token="...", attempts=5, elapsed_sec=38.0)
```

### Inject
```python
solver.inject(page, "hcaptcha", token)
# Injects token into page's captcha callback
```

### Auto (detect + solve + inject)
```python
results = solver.auto_solve(page)
for r in results:
    print(f"{r.captcha_type}: {'OK' if r.success else r.error}")
```

## SmartPage (transparent wrapper)

```python
from auto_captcha_solver import smart_page

with smart_page(api_key="your-key") as page:
    page.goto("https://protected-site.com")
    page.fill("#email", "user@example.com")
    page.click("#submit")   # captcha auto-solved after each action
```

## Supported Captcha Types

| Type | API Endpoint | Status |
|------|-------------|--------|
| hCaptcha (checkbox) | `/v1/token/hcaptcha` | Working |
| hCaptcha (enterprise) | `/v1/token/hcaptcha` | Working |
| reCAPTCHA v2 | `/v1/token/recaptcha2` | Works but queue can be slow |
| reCAPTCHA v3 | Not supported | — |
| Cloudflare Turnstile | Not supported | — |

## NopeCHA API Details

- **Base URL**: `https://api.nopecha.com`
- **Auth**: `Authorization: Basic <API_KEY>` header (NOT query param, NOT Bearer)
- **Status check**: `GET /v1/status`
- **Submit hCaptcha**: `POST /v1/token/hcaptcha` body `{"sitekey": "...", "url": "..."}`
- **Submit reCAPTCHA**: `POST /v1/token/recaptcha2` body `{"sitekey": "...", "url": "..."}`
- **Poll result**: `GET /v1/token/<type>?id=<job_id>`
- **Response**: `{"data": "<token>"}` on success, `{"error": 14}` = still in queue (retryable), other errors = fail
- **hCaptcha** solves fast (~30-40s). **reCAPTCHA** queue is often slow (60-120s+).

## Pitfalls

- **reCAPTCHA queues can be slow** — may take 60-120+ seconds during peak times
- **hCaptcha iframe detection** — look for `hcaptcha.com` in frame URLs; some sites load hCaptcha without an iframe (use DOM fallback: `document.querySelector('[data-sitekey]')`). Always add `time.sleep(3)` after page load for lazy loading.
- **reCAPTCHA iframe detection** — look for `recaptcha` AND `/anchor` in frame URL; the `?k=<sitekey>` param has the key
- **reCAPTCHA callback injection** — needs `___grecaptcha_cfg` to exist; if site uses enterprise, injection may fail silently
- **Credits** — each solve costs 1 credit; check with `solver.get_credits()`
- **Headless detection** — some sites detect headless browsers; use `headless=False` or stealth plugins if needed

## Installation

```bash
pip install auto-captcha-solver
python -m playwright install chromium
```

## MCP Server

Works with Claude Code, OpenClaw, and any MCP-compatible agent:

```bash
claude mcp add auto-captcha-solver -- python -m auto_captcha_solver.mcp_server
```

## File Location

```
~/.hermes/skills/auto-captcha-solver/
```
