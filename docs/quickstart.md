# Quick Start Guide

## 1. Get an API Key

Go to https://nopecha.com and sign up. Free tier gives 100 credits.

## 2. Install

```bash
pip install requests playwright
python -m playwright install chromium
```

## 3. Set Your Key

```bash
export NOPECHA_API_KEY=your-key-here
```

## 4. Run the Demo

```python
from auto_captcha import smart_page

with smart_page(api_key="your-key") as page:
    page.goto("https://nopecha.com/captcha/hcaptcha#enterprise")
    print(page.captcha_log)
    # → [{'type': 'hcaptcha', 'status': 'solved', 'url': '...'}]
```

## 5. Use in Your Script

```python
from auto_captcha import smart_page

with smart_page(api_key="your-key") as page:
    # Navigate to a captcha-protected site
    page.goto("https://example.com/login")
    
    # Fill in credentials
    page.fill("#email", "user@example.com")
    page.fill("#password", "secret")
    
    # Captcha is auto-detected and solved here
    page.click("#submit")
    
    # Check what was solved
    for log in page.captcha_log:
        print(f"{log['type']}: {log['status']}")
```

## 6. Check Credits

```python
from auto_captcha import CaptchaSolver
solver = CaptchaSolver(api_key="your-key")
print(f"Credits: {solver.get_credits()}")
```

## What Happens

```
Your code                Behind the scenes
─────────────────────────────────────────────
page.goto("url")    →    Browser loads page
                    →    Wait 3 seconds
                    →    Scan for captcha iframes
                    →    Scan DOM for sitekey
                    →    Found hCaptcha!
                    →    POST to NopeCHA API
                    →    Poll for token (10-40s)
                    →    Inject token into page
                    →    Return to your code
page.fill("#input") →    Works normally
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No captcha detected | Add `time.sleep(5)` after goto, some sites load captchas slowly |
| Solve times out | reCAPTCHA queues can take 60-120s, try again later |
| Credits depleted | Check with `solver.get_credits()`, buy more at nopecha.com |
| Headless detected | Use `smart_page(api_key="...", headless=False)` |
| Solved once, blocked again | Use a sticky residential proxy for both Playwright and `CaptchaSolver(proxy=...)` — see [Production Tips](../README.md#production-tips-proxies--sticky-sessions) |
