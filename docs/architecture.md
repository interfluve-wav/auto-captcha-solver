# Architecture

## Layers

```
Your Code
    ↓
smart_page() — context manager, opens browser, returns SmartPage
    ↓
SmartPage — wraps Playwright page, intercepts goto/click to auto-solve
    ↓
CaptchaSolver — detect/solve/inject engine
    ↓
NopeCHA API — external captcha-solving service
    ↓
Browser Page — Playwright Chromium with captcha token injected
```

## Detection (Dual Method)

### Method 1: Playwright Frame Scan
```python
for frame in page.frames:
    if "hcaptcha.com" in frame.url:
        sitekey = extract_from_url(frame.url)
```

### Method 2: DOM Fallback
```python
page.evaluate('document.querySelector("[data-sitekey]").getAttribute("data-sitekey")')
```

Method 2 catches cases where Playwright doesn't list the iframe as a separate frame (common with lazy-loaded captchas).

## API Flow

```
1. POST /v1/token/hcaptcha {sitekey, url}
   → Returns JOB_ID

2. GET /v1/token/hcaptcha?id=JOB_ID (poll every 4s)
   → error 14 = still solving, retry
   → data = solved token

3. Inject token into page
   → hCaptcha: textarea[name="h-captcha-response"] = token
   → reCAPTCHA: #g-recaptcha-response + callback(token)
```

## Supported Types

| Type | Detection | Speed | Reliability |
|------|-----------|-------|-------------|
| hCaptcha | iframe + DOM | 10-40s | High |
| reCAPTCHA v2 | iframe + DOM | 60-120s | Medium (queue) |

## Credits

Each solve costs 1 NopeCHA credit. Check remaining:
```python
solver.get_credits()  # Returns int
```
