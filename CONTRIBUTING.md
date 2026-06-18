# Contributing to auto-captcha

Thank you for your interest! This document outlines the development workflow, conventions, and expectations for contributing to **auto-captcha**.

## Quick Setup

```bash
# Clone
git clone https://github.com/interfluve-wav/auto-captcha-solver.git
cd auto-captcha-solver

# Editable install with all dev tools
pip install -e ".[dev,playwright]"

# Install Playwright browsers
python -m playwright install chromium

# Run tests
pytest tests/ -v

# Lint & type-check
 ruff check src tests
 mypy src
```

## Environment

- **Python**: 3.10 minimum (f-strings, union types, `list[str]` syntax)
- **Package manager**: pip (no poetry/poetry.lock)
- **Formatter**: `ruff format .`
- **Linter**: `ruff check` (extends PEP 8 + opinionated rules)
- **Type checker**: `mypy --strict src`

## Project Layout

```
auto-captcha-solver/
├── src/auto_captcha_solver/
│   ├── __init__.py          # public exports
│   ├── solver.py            # core detection + solve logic
│   ├── wrapper.py           # SmartPage class
│   ├── cli.py               # command-line interface
│   └── mcp_server.py        # MCP stdio server
├── tests/                   # pytest suite
├── .github/workflows/       # CI (lint, test, build, publish)
├── docs/                    # supplementary docs (architecture diagrams)
├── README.md                # public-facing docs
└── CHANGELOG.md             # user-facing change log
```

## Development Workflow

1. **Branch naming**: `type/short-desc` (e.g. `bug/fix-turnstile-detection`, `feat/add-retry-logic`)
2. **Commits**: Use clear, imperative messages. Reference issues with `#123`.
   ```
   feat: Cloudflare Turnstile sitekey fallback

   - Add DOM fallback when iframe sitekey missing
   - Update detection flow order
   - Add test case for script-only widgets
   ```
3. **Before submitting PR**:
   - `ruff format .` — auto-format everything
   - `ruff check src tests` — fix lints
   - `mypy src` — fix type errors
   - `pytest tests/ -v` — ensure green (write tests for new behavior)

4. **Opening a PR**: Fill out the PR template completely. Link the related issue. CI must pass.

## Adding a New Captcha Type

1. Add endpoint to `EXPERIMENTAL_ENDPOINTS` or `TOKEN_ENDPOINTS` in `solver.py`
2. Extend `detect()` with a DOM/in-frame detector block
3. Add `inject()` branch for token injection callback
4. Document in README supported table
5. Add basic smoke in `tests/test_detection.py`

## Release Process (maintainers only)

1. Update `__version__` in `src/auto_captcha_solver/__init__.py`
2. Update `CHANGELOG.md` — move Unreleased → `[0.1.x]` section
3. Commit + push to main (CI builds artifacts)
4. Tag and push:
   ```bash
   git tag v0.1.4
   git push origin v0.1.4
   ```
5. GitHub Actions auto-publishes to PyPI and creates a Release draft.
6. Edit Release with changelog highlights and publish.

## Testing Strategy

- **Unit tests** for pure functions (sitekey extraction regexes, result parsing)
- **Integration tests** require Playwright and a running browser; use `@pytest.mark.playwright`
- **API tests** are skipped unless `NOPECHA_API_KEY` is set (use `pytest -m "not api"` to skip)

Run full suite locally:

```bash
NOPECHA_API_KEY="test-key" pytest tests/ -v
```

## Questions?

Open an issue — we'll triage promptly. For security concerns, email security@interfluve-wav.github.io or use GitHub's private vulnerability reporting.
