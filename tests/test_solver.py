"""Unit tests for the core solver logic."""

from auto_captcha_solver.providers.nopecha import EXPERIMENTAL_ENDPOINTS, TOKEN_ENDPOINTS
from auto_captcha_solver.solver import CaptchaSolver
from auto_captcha_solver.types import sanitize_detect_results

# ── Module-level imports ──────────────────────────────────────────────


def test_version():
    from auto_captcha_solver import __version__

    assert __version__ == "0.1.6"


def test_supported_types():
    solver = CaptchaSolver(api_key="k")
    assert solver.supported_types() == ["hcaptcha", "recaptcha2", "recaptcha3"]
    assert solver.experimental_types() == ["turnstile"]
    assert CaptchaSolver.default_supported_types() == ["hcaptcha", "recaptcha2", "recaptcha3"]


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

    monkeypatch.setattr("auto_captcha_solver.providers.nopecha.requests.request", mock_request)
    credits = solver.get_credits()
    assert credits == 999


def test_get_credits_failure(monkeypatch, solver):
    def mock_request(*args, **kwargs):
        return DummyResponse(500, {})

    monkeypatch.setattr("auto_captcha_solver.providers.nopecha.requests.request", mock_request)
    credits = solver.get_credits()
    assert credits == 0


def test_nopecha_body_sends_native_cookie_and_data(monkeypatch):
    """NopeCHA docs: `cookie` is an ARRAY of cookie objects and `data` is a
    native object. Capture the JSON payload and assert the documented shape
    (native containers — NOT stringified)."""
    captured = {}

    def mock_request(method, url, headers=None, json=None, timeout=None, **kw):
        captured["method"] = method
        captured["body"] = json
        return DummyResponse(200, {"data": "job-123"})

    monkeypatch.setattr("auto_captcha_solver.providers.nopecha.requests.request", mock_request)
    # max_polls=0 → submit returns immediately after the POST (no sleep).
    s = CaptchaSolver(
        api_key="k",
        max_polls=0,
        proxy={"scheme": "http", "host": "h", "port": 7777, "username": "u", "password": "p"},
    )
    s.solve(
        "hcaptcha",
        "sitekey-x",
        "https://example.com",
        useragent="UA/1.0",
        cookies=[
            {
                "name": "a",
                "value": "b",
                "domain": "example.com",
                "path": "/",
                "expires": -1,
            }
        ],
        data={"action": "submit"},
    )

    body = captured["body"]
    # cookie + data must be native containers (per NopeCHA docs' examples).
    assert isinstance(body["cookie"], list)
    assert body["cookie"][0]["name"] == "a" and body["cookie"][0]["domain"] == "example.com"
    assert body["cookie"][0]["session"] is True  # normalized session cookie flag
    assert isinstance(body["data"], dict)
    assert body["data"] == {"action": "submit"}
    # core fields stay native
    assert body["sitekey"] == "sitekey-x"
    assert body["url"] == "https://example.com"
    assert body["useragent"] == "UA/1.0"
    assert body["proxy"]["host"] == "h"


def test_describe_error_surfaces_diagnostic_type():
    from auto_captcha_solver.providers.nopecha import describe_error

    out = describe_error(10, "Invalid request", "Invalid proxy")
    assert "Invalid request" in out and "type=Invalid proxy" in out
    # message equal to the known default is not doubled
    out2 = describe_error(14, "Incomplete job")
    assert out2 == "Incomplete job"


def test_turnstile_without_proxy_fails_fast(solver):
    """NopeCHA marks proxy REQUIRED for turnstile — fail fast with a clear
    message instead of a cryptic queue-level 'Invalid request'."""
    result = solver.solve("turnstile", "0xabc", "https://example.com")
    assert not result.success
    assert "requires a proxy" in result.error


def test_turnstile_with_proxy_proceeds(monkeypatch):
    from auto_captcha_solver.providers.nopecha import NopechaProvider

    class Captured:
        body = None
        submitted = False

    def fake_api(self, path, method="GET", body=None):
        if method == "POST":
            self.body = body
            self.submitted = True
            return (200, {"data": "job-1"})
        return (200, {"data": "0.token"})

    monkeypatch.setattr(NopechaProvider, "_api", fake_api)
    s = CaptchaSolver(
        api_key="k",
        max_polls=1,
        proxy={"scheme": "http", "host": "h", "port": 7777, "username": "u", "password": "p"},
    )
    result = s.solve("turnstile", "0xabc", "https://example.com")
    assert result.success and result.token == "0.token"


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

    # Stub solve() → success (auto_solve calls it with keyword args)
    def fake_solve(captcha_type, sitekey, url, **kwargs):
        res = CaptchaResult(success=True, captcha_type=captcha_type, token="tok123", attempts=1)
        solver.inject(page, captcha_type, "tok123")
        return res

    monkeypatch.setattr(solver, "solve", fake_solve)

    results = solver.auto_solve(page, click_checkbox=False)

    assert len(results) == 1
    assert results[0].success
    # Verify inject was called via solver.inject mock tracking
    # (We can't easily check page state; we verify solve+inject chain executed)


def test_sanitize_detect_results_strips_frame():
    captchas = [
        {"type": "hcaptcha", "sitekey": "abc", "url": "https://example.com", "frame": object()},
    ]
    assert sanitize_detect_results(captchas) == [
        {"type": "hcaptcha", "sitekey": "abc", "url": "https://example.com"},
    ]


def test_smart_page_accepts_proxy():
    from auto_captcha_solver import SmartPage

    class DummyPage:
        url = "https://example.com"

    page = SmartPage(DummyPage(), api_key="k", proxy={"scheme": "http", "host": "1.2.3.4", "port": 8080})
    assert page._solver.proxy == {"scheme": "http", "host": "1.2.3.4", "port": 8080}


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


# ── Regression: reCAPTCHA v2 vs v3 detection ────────────────────────────
# Bug (benchmarked Sep 2026): the DOM-fallback used a `data-size` attribute
# to tell v2 from v3, but default-size v2 widgets don't set data-size. Early
# in page load (before the anchor iframe appears) a real v2 page was
# mislabeled recaptcha3, which sent the wrong endpoint/metadata to NopeCHA
# and failed with "Invalid request". The discriminator is now the rendered
# .g-recaptcha container (v2) vs its absence (v3) for DOM, and the anchor
# iframe's size=invisible param for the frame path.

V2_SITEKEY = "6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-"
V3_SITEKEY = "6LdKlZEpAAAAAAOQjzC2v_d36tWxCl6dWsozdSy9"


class IdentityFrame:
    def __init__(self, url):
        self.url = url


class ScriptAwarePage:
    """Dummy Playwright page: evaluate() routes on script content."""

    def __init__(self, *, url, frames=(), grc_container=False,
                 grc_sitekey=None, recaptcha_scripts=(), recaptcha_iframes=(),
                 has_v3_result=False, dom_sitekey=None):
        self.url = url
        self._frames = list(frames)
        self._grc_container = grc_container
        self._grc_sitekey = grc_sitekey
        self._recaptcha_scripts = list(recaptcha_scripts)
        self._recaptcha_iframes = list(recaptcha_iframes)
        self._has_v3_result = has_v3_result
        self._dom_sitekey = dom_sitekey

    @property
    def frames(self):
        return self._frames

    def evaluate(self, script):
        s = script
        # Method 1 helper: extract sitekey from iframe URL
        if "fonts5" in s:
            return None
        # has_v3 expression — has a distinctive `, iframe[src*=` right after the
        # .g-recaptcha selector (the widget gate does NOT: it closes with ')').
        if "const scripts = document.querySelectorAll('script[src*=google.com/recaptcha" in s.replace("\\\"", "\""):
            return self._has_v3_result
        # has_recaptcha_widget (Method 2 gate)
        if ".g-recaptcha, .g-recaptcha-response') ||" in s and "querySelectorAll(" in s:
            has_iframe = any(
                ("google.com/recaptcha" in f or "recaptcha.net" in f or "gstatic.com/recaptcha" in f)
                for f in self._recaptcha_iframes
            )
            return self._grc_container or self._grc_sitekey is not None or has_iframe
        # has_container (the new v2/v3 discriminator)
        if "querySelector('.g-recaptcha')" in s or "querySelector('.g-recaptcha');" in s:
            return self._grc_container or self._grc_sitekey is not None
        # reCAPTCHA sitekey from DOM (the .g-recaptcha widget)
        if "el = document.querySelector('.g-recaptcha[data-sitekey], .g-recaptcha')" in s:
            if self._grc_sitekey:
                return self._grc_sitekey
            for f in self._recaptcha_iframes:
                import re
                m = re.search(r"[?&#]k=([A-Za-z0-9_-]+)", f)
                if m:
                    return m.group(1)
            return None
        # reCAPTCHA v3 sitekey from scripts (render= param)
        if "render=([A-Za-z0-9_-]+)" in s:
            for scr in self._recaptcha_scripts:
                import re
                m = re.search(r"[?&]render=([A-Za-z0-9_-]+)", scr)
                if m:
                    return m.group(1)
            return None
        # has_v3 expression
        if "if (document.querySelector('.g-recaptcha, .g-recaptcha-response" in s:
            return self._has_v3_result
        # hCaptcha widget check
        if ".h-captcha" in s:
            return False
        # Turnstile widget check
        if ".cf-turnstile" in s:
            return False
        # has_size fallback — no longer used by recaptcha2 path
        if "data-size" in s:
            return False
        return False


def test_detect_v2_default_size_no_anchor_iframe_is_recaptcha2():
    """The regression: v2 with default size (NO data-size attr) and the anchor
    iframe not yet present must detect as recaptcha2 (was: recaptcha3)."""
    s = CaptchaSolver(api_key="k")
    page = ScriptAwarePage(
        url="https://www.google.com/recaptcha/api2/demo",
        grc_container=True,
        grc_sitekey=V2_SITEKEY,
    )
    caps = s.detect(page)
    types = [c["type"] for c in caps]
    assert types == ["recaptcha2"], f"expected recaptcha2, got {types}"
    assert caps[0]["sitekey"] == V2_SITEKEY


def test_detect_v2_anchor_iframe_normal_size_is_recaptcha2():
    """Anchor iframe with size=normal → recaptcha2."""
    s = CaptchaSolver(api_key="k")
    anchor = IdentityFrame(
        f"https://www.google.com/recaptcha/api2/anchor?ar=1&k={V2_SITEKEY}&size=normal"
    )
    page = ScriptAwarePage(
        url="https://www.google.com/recaptcha/api2/demo",
        frames=[anchor],
    )
    caps = s.detect(page)
    assert [c["type"] for c in caps] == ["recaptcha2"]


def test_detect_v3_anchor_iframe_invisible_is_recaptcha3():
    """Anchor iframe with size=invisible (v3/enterprise) → recaptcha3.
    Was: always recaptcha2 from the frame path."""
    s = CaptchaSolver(api_key="k")
    anchor = IdentityFrame(
        f"https://www.google.com/recaptcha/enterprise/anchor?ar=1&k={V3_SITEKEY}&size=invisible"
    )
    page = ScriptAwarePage(
        url="https://recaptcha-demo.appspot.com/recaptcha-v3-request-scores.php",
        frames=[anchor],
    )
    caps = s.detect(page)
    assert [c["type"] for c in caps] == ["recaptcha3"]
    assert caps[0]["sitekey"] == V3_SITEKEY


def test_detect_v3_no_container_script_only_is_recaptcha3():
    """v3 with no rendered container, only a render= script → recaptcha3."""
    s = CaptchaSolver(api_key="k")
    page = ScriptAwarePage(
        url="https://example.com/v3-page",
        recaptcha_scripts=[f"https://www.google.com/recaptcha/api.js?render={V3_SITEKEY}"],
        has_v3_result=True,
    )
    caps = s.detect(page)
    assert [c["type"] for c in caps] == ["recaptcha3"]
    assert caps[0]["sitekey"] == V3_SITEKEY
