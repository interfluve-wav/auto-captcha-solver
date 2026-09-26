# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **reCAPTCHA v2/v3 misclassification** — detection labeled default-size v2 widgets as v3 when the anchor iframe hadn't loaded yet (the DOM fallback relied on a `data-size` attribute that Google only sets for non-default sizes), sending v2 sitekeys to the v3 endpoint and failing with NopeCHA "Invalid request". The frame path also misread enterprise v3 (invisible) anchors as v2. Discriminator is now the rendered `.g-recaptcha` container (v2) vs script-only (v3) on DOM, and `size=invisible` on anchor frames; regression tests cover both pages at early/late load.

## [0.1.6] - 2026-08-29

### Added
- **Proxy preflight** — `check_proxy_egress()` verifies a proxy connects and reports its egress IP before any credits are spent; `proxy_server_url()` renders the Playwright/requests form. `auto_solve_url(..., verify_proxy=True)` and CLI `solve` run it automatically when a proxy is set; CLI `proxy-check` subcommand works without an API key
- **CLI proxy support** — `solve`/`detect` accept `--proxy-url` or `--proxy`/`--proxy-port`/`--proxy-user`/`--proxy-pass` (with `CAPTCHA_PROXY_URL` / `NOVADA_*` env fallback); Turnstile/reCAPTCHA-v3 are now solvable from the command line
- **Novada sticky sessions** — e2e runner builds the documented sticky-session username `USERNAME-zone-<zone>[-region-XX]-session-<id>-sessTime-<N>` from `NOVADA_SESSION` (+ `NOVADA_ZONE` default `res`, `NOVADA_REGION` 2-letter code, `NOVADA_SESS_TIME` default 120, max 120; session id validated to alphanumeric/underscore, no hyphens — Novada's `-` auth delimiter). Zone is the product (`res`/`isp`/`dcp`/`mob`), distinct from the host's region (e.g. `.na.`). Needed for rotating pools; dedicated single-IP hosts leave it unset
- **NopeCHA hardening** — Turnstile without a proxy now fails fast with a clear error (NopeCHA's schema marks proxy **Required** for this endpoint) instead of a cryptic queue-level error 10; error responses' diagnostic `type` field is surfaced in error strings on submit and poll; socks proxy auth warned (NopeCHA only honors auth on http/https)
- **Remote / hosted browser mode (CDP)** — `auto_solve_url(..., cdp_url=...)` connects over CDP to a Browserless / Steel / any-hosted browser instead of launching one (opens a context, solves, closes the context without killing the remote session); `connect_kwargs` for handshake headers; CLI `--cdp-url` + repeatable `--cdp-header` (or `CAPTCHA_CDP_URL` env); `AutoSolveReport.browser_mode` ("local" / "cdp")
- **Stealth helper** — `apply_stealth(context)` masks in-page headless fingerprint leaks (`navigator.webdriver`, `window.chrome`, `navigator.plugins`, WebGL vendor string, `navigator.languages`)
- **Autopilot** — `auto_solve_url` / `auto_solve_page` turnkey one-call flow: launch headless browser, wait for late-rendering widgets, solve, inject, and report; `round_robin_rotator` + `proxy_pool` for per-session rotating proxies (browser + solver share the proxy so the token IP matches client IP)
- **Context cloning** — `clone_context(page)` snapshots the browser's real User-Agent + cookies; `auto_solve(..., clone_context=True)` (default) forwards them so the token's mint context matches the presenting browser
- **Metadata extraction** — `auto_solve` reads `data-action`/`data-cdata` off live reCAPTCHA v3 / Turnstile widgets and forwards per NopeCHA docs
- **Cookie normalization** — Playwright cookie shape → NopeCHA `cookie[]` shape (`hostOnly`/`httpOnly`/`secure`/`session` flags)
- **Provider field parity** — NopeCHA now accepts `useragent`, `cookies`, `data` (rqdata, action, cdata, s, theme, enterprise); CaptchaAI maps `data.action`/`min_score`/`data.cdata` + `userAgent` + cookies

### Changed
- `CaptchaSolver.solve()` and both providers accept optional `useragent`/`cookies`/`data`
- Version 0.1.5 → 0.1.6

### Fixed
- README MCP examples referenced the legacy `auto_captcha` module instead of `auto_captcha_solver`

## [0.1.5] - 2026-06-18

### Added
- **CaptchaAI provider** — 2Captcha-compatible `in.php`/`res.php` backend for reCAPTCHA v2/v3 and Turnstile
- `provider` parameter on `CaptchaSolver`, `SmartPage`, and `smart_page()` (`nopecha` | `captchaai`)
- CLI `--provider` flag and `CAPTCHA_PROVIDER` / `CAPTCHAAI_API_KEY` environment variables
- MCP server reads `CAPTCHA_PROVIDER` and provider-specific API keys

### Changed
- Refactored NopeCHA integration into pluggable `providers/` package

## [0.1.4] - 2026-04-25

### Added
- GitHub Actions CI pipeline (build, test, publish to PyPI on release)
- `typing-extensions` backport for Python <3.11
- `ruff` and `mypy` tooling for code quality
- pytest test suite skeleton with fixtures

### Changed
- **Project version**: 0.1.3 → 0.1.4
- Requires Python 3.10+ (from >=3.9)
- Updated README with architecture diagram, performance stats, and table of contents
- Packages now use `src/` layout consistently with `__init__.py` re-exports

### Fixed
- README code blocks use correct import paths (`from auto_captcha_solver import ...`)
- Distribution builds now include all required data files

### Security
- Proxy support added for NopeCHA requests (experimental)

## [0.1.3] - 2025-10-12

### Added
- Initial public release
- Support for hCaptcha and reCAPTCHA v2
- `CaptchaSolver` core class with detect/solve/inject API
- `SmartPage` wrapper with auto-solve on navigation
- CLI tool (`auto-captcha solve/detect/credits`)
- Hermes skill integration

[0.1.4]: https://github.com/interfluve-wav/auto-captcha-solver/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/interfluve-wav/auto-captcha-solver/releases/tag/v0.1.3
