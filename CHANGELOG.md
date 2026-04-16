# Changelog

Renamed from `auto-captcha` to `auto-captcha-solver`.

## 0.1.3 (2026-04-16)

- Move Turnstile to experimental (NopeCHA queue 5-10+ min, needs proxy)
- Add `solver.experimental_types()` method
- Add proxy support to CaptchaSolver constructor
- Stable: hcaptcha, recaptcha2, recaptcha3
- Experimental: turnstile

## 0.1.2 (2026-04-16)

- Add: reCAPTCHA v3 Token API support
- Add: Cloudflare Turnstile Token API support
- Add: `solver.supported_types()` method
- Fix: detection no longer false-positives across captcha types

## 0.1.1 (2026-04-16)

- Fix: hCaptcha sitekey extraction from iframe URL fragments
- Fix: detect hCaptcha when iframes are cross-origin

## 0.1.0 (2026-04-16)

Initial release — hCaptcha + reCAPTCHA v2, CLI, MCP server, Hermes skill.
