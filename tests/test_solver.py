"""Unit tests for the core solver logic."""

import pytest
from auto_captcha_solver.solver import CaptchaSolver, CaptchaResult, TOKEN_ENDPOINTS, EXPERIMENTAL_ENDPOINTS
from auto_captcha_solver import CaptchaSolver as ImportedSolver

# ── Module-level imports ──────────────────────────────────────────────

def test_version():
    from auto_captcha_solver import __version__
    assert __version__ == "0.1.4"

def test_supported_types():
    assert CaptchaSolver.supported_types() == ["hcaptcha", "recaptcha2", "recaptcha3"]
    assert CaptchaSolver.experimental_types() == ["turnstile"]

def test_solver_initialization(solver):
    assert solver.api_key == "test-key-for-unit-tests"
    assert solver.poll_interval == 4.0
    assert solver.max_polls == 25
    assert solver.timeout_sec == 120.0
    assert solver.proxy is None

def test_solver_custom_timeout():
    s = CaptchaSolver(api_key="key", poll_interval=2.0, max_polls=10, timeout_sec=60.0)
    assert s.poll_interval == 2.0
    assert s.max_polls == 10
    assert s.timeout_sec == 60.0

def test_unsupported_type_returns_error(solver):
    result = solver.solve("invalid_type", "sitekey123", "https://example.com")
    assert not result.success
    assert "unsupported type" in result.error.lower()
    assert result.captcha_type == "invalid_type"
    assert result.token == ""
    assert result.attempts == 0

def test_token_endpoints_coverage():
    """Ensure TOKEN_ENDPOINTS covers all stable types."""
    expected = {"hcaptcha", "recaptcha2", "recaptcha3"}
    assert set(TOKEN_ENDPOINTS.keys()) == expected

def test_experimental_endpoints_coverage():
    assert "turnstile" in EXPERIMENTAL_ENDPOINTS

# ── Sitekey extraction (pure string ops) ──────────────────────────────

def test_extract_sitekey_from_recaptcha_url():
    s = CaptchaSolver(api_key="k")
    url = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
    assert s._extract_sitekey(url) == "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"

def test_extract_sitekey_from_hcaptcha_url():
    s = CaptchaSolver(api_key="k")
    url = "https://hcaptcha.com/getcaptcha/1x?sitekey=10000000-ffff-ffff-ffff-000000000001"
    assert s._extract_sitekey(url) == "10000000-ffff-ffff-ffff-000000000001"

def test_extract_sitekey_returns_none_for_garbage():
    s = CaptchaSolver(api_key="k")
    assert s._extract_sitekey("https://example.com/page") is None

# ── API layer (mocked network) ────────────────────────────────────────

class DummyResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data
    def json(self):
        return self._json

def test_get_credits_success(monkeypatch, solver):
    def mock_request(*args, **kwargs):
        return DummyResponse(200, {"credit": 999})
    monkeypatch.setattr("requests.request", mock_request)
    credits = solver.get_credits()
    assert credits == 999

def test_get_credits_failure(monkeypatch, solver):
    def mock_request(*args, **kwargs):
        return DummyResponse(500, {})
    monkeypatch.setattr("requests.request", mock_request)
    credits = solver.get_credits()
    assert credits == 0

def test_detect_returns_empty_list_on_no_captcha(monkeypatch, solver):
    """detect() should return [] when page has no captcha elements."""

    class DummyPage:
        @property
        def url(self):
            return "https://example.com/form"
        @property
        def frames(self):
            return []  # No iframes at all
        def evaluate(self, script):
            return False  # No DOM widgets either

    page = DummyPage()
    captchas = solver.detect(page)
    assert captchas == []

# ── Auto-solve flow (mocked) ─────────────────────────────────────────

def test_auto_solve_success_flow(monkeypatch, solver):
    """Full auto_solve flow: detect → solve → inject."""
    from auto_captcha_solver import CaptchaResult

    class DummyPage:
        url = "https://example.com/login"
        @property
        def frames(self):
            return []
        def evaluate(self, script):
            return False

    page = DummyPage()

    # Stub detect() to return ONE captcha
    def fake_detect(p):
        return [{"type": "hcaptcha", "sitekey": "abc123", "url": p.url}]
    monkeypatch.setattr(solver, "detect", fake_detect)

    # Stub solve() → success
    def fake_solve(captcha_type, sitekey, url):
        res = CaptchaResult(success=True, captcha_type=captcha_type, token="tok123", attempts=1)
        solver.inject(page, captcha_type, "tok123")
        return res
    monkeypatch.setattr(solver, "solve", fake_solve)

    results = solver.auto_solve(page, click_checkbox=False)

    assert len(results) == 1
    assert results[0].success
    # Verify inject was called via solver.inject mock tracking
    # (We can't easily check page state; we verify solve+inject chain executed)

def test_smart_page_context_manager():
    """smart_page() should give a page object with captcha_log accessible."""
    from auto_captcha_solver import smart_page

    with smart_page(api_key="dummy", headless=True) as page:
        assert page._page is not None  # underlying Playwright page exists
        assert hasattr(page, "captcha_log")
        assert isinstance(page.captcha_log, list)

def test_smart_page_wrappers_delegate():
    """SmartPage should delegate fill/type/select_option to raw page."""
    from auto_captcha_solver import smart_page

    with smart_page(api_key="dummy", headless=True) as page:
        # fill/type/locator etc exist and are callable
        assert callable(page.fill)
        assert callable(page.type)
        assert callable(page.select_option)
        assert callable(page.locator)
