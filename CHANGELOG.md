# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MCP server — use from Claude Code, Cursor, and other MCP-compatible agents
- `captcha_credits` CLI subcommand — check NopeCHA balance without solving
- Type hints on all public functions and classes

### Changed
- Refactored detection logic for cleaner frame vs DOM fallback paths
- Standardized JSON output format in CLI (`--pretty` for formatted)
- Improved error messages for unsupported captcha types

### Fixed
- reCAPTCHA v3 detection edge-cases where v2 was incorrectly reported
- Turnstile sitekey extraction from script URLs
- `SmartPage.submit()` now works with non-form selector parameter

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
