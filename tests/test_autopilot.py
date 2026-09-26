"""Unit tests for the turnkey autopilot helpers (no browser/API needed)."""

from auto_captcha_solver.autopilot import (
    AutoSolveReport,
    auto_solve_page,
    round_robin_rotator,
    wait_for_captchas,
)
from auto_captcha_solver.types import CaptchaResult

# ── Proxy rotation ────────────────────────────────────────────────────


def test_round_robin_rotator_cycles():
    rot = round_robin_rotator(
        [{"host": "a"}, {"host": "b"}, {"host": "c"}],
    )
    hosts = []
    for _ in range(5):
        proxy = rot()
        assert proxy is not None
        hosts.append(proxy["host"])
    assert hosts == ["a", "b", "c", "a", "b"]


def test_round_robin_rotator_empty():
    rot = round_robin_rotator([])
    assert rot() is None


# ── Report helpers ────────────────────────────────────────────────────


def test_report_solved_property():
    fail = AutoSolveReport(url="https://x", results=[CaptchaResult(success=False, error="nope")])
    assert not fail.solved
    ok = AutoSolveReport(
        url="https://x",
        results=[CaptchaResult(success=True, token="tok")],
    )
    assert ok.solved


def test_report_summary_no_captchas():
    r = AutoSolveReport(url="https://x")
    assert "No captchas" in r.summary


# ── wait_for_captchas polling ─────────────────────────────────────────


def test_wait_for_captchas_polls_until_found():
    calls = {"n": 0}

    class DummyPage:
        def is_closed(self):
            return False

    class DummySolver:
        def detect(self, page):
            calls["n"] += 1
            if calls["n"] >= 3:
                return [{"type": "hcaptcha", "sitekey": "sk", "url": "https://x"}]
            return []

    found = wait_for_captchas(
        DummySolver(),  # type: ignore[arg-type]
        DummyPage(),  # type: ignore[arg-type]
        timeout_sec=2.0,
        interval_sec=0.01,
        click_checkbox=False,
    )
    assert len(found) == 1
    assert calls["n"] == 3


def test_wait_for_captchas_timeout_returns_empty():
    class DummySolver:
        def detect(self, page):
            return []

    found = wait_for_captchas(
        DummySolver(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        timeout_sec=0.1,
        interval_sec=0.01,
    )
    assert found == []


# ── auto_solve_page flow ──────────────────────────────────────────────


def test_auto_solve_page_solves_and_injects(monkeypatch):
    class DummyPage:
        url = "https://x"

        def title(self):
            return "Test Page"

    page = DummyPage()

    injected = []

    class DummySolver:
        def detect(self, page):
            return [{"type": "hcaptcha", "sitekey": "sk", "url": page.url}]

        def _page_useragent(self, page):
            return "UA"

        def _page_cookies(self, page):
            return [{"name": "a", "value": "b", "domain": "x", "path": "/"}]

        def _widget_data(self, page, captcha_type):
            return None

        def solve(self, captcha_type, sitekey, url, **kwargs):
            return CaptchaResult(success=True, captcha_type=captcha_type, token="tok")

        def inject(self, page, captcha_type, token):
            injected.append((captcha_type, token))

        def _click_checkbox(self, cap):
            pass

    report = auto_solve_page(
        page,  # type: ignore[arg-type]
        DummySolver(),  # type: ignore[arg-type]
        max_wait_sec=2.0,
        humanize=False,
    )
    assert report.solved
    assert injected == [("hcaptcha", "tok")]
    assert report.page_title == "Test Page"


def test_auto_solve_page_retries_transient_timeout(monkeypatch):
    class DummyPage:
        url = "https://x"

        def title(self):
            return ""

    calls = {"n": 0}

    class DummySolver:
        def detect(self, page):
            return [{"type": "hcaptcha", "sitekey": "sk", "url": page.url}]

        def _page_useragent(self, page):
            return None

        def _page_cookies(self, page):
            return None

        def _widget_data(self, page, captcha_type):
            return None

        def solve(self, captcha_type, sitekey, url, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return CaptchaResult(success=False, captcha_type=captcha_type, error="timeout")
            return CaptchaResult(success=True, captcha_type=captcha_type, token="tok")

        def inject(self, page, captcha_type, token):
            pass

        def _click_checkbox(self, cap):
            pass

    report = auto_solve_page(
        DummyPage(),  # type: ignore[arg-type]
        DummySolver(),  # type: ignore[arg-type]
        max_wait_sec=2.0,
        humanize=False,
        retries=1,
    )
    assert report.solved
    assert calls["n"] == 2


def test_auto_solve_page_no_retry_on_non_transient():
    class DummyPage:
        url = "https://x"

        def title(self):
            return ""

    calls = {"n": 0}

    class DummySolver:
        def detect(self, page):
            return [{"type": "hcaptcha", "sitekey": "sk", "url": page.url}]

        def _page_useragent(self, page):
            return None

        def _page_cookies(self, page):
            return None

        def _widget_data(self, page, captcha_type):
            return None

        def solve(self, captcha_type, sitekey, url, **kwargs):
            calls["n"] += 1
            return CaptchaResult(success=False, captcha_type=captcha_type, error="Out of credit")

        def inject(self, page, captcha_type, token):
            pass

        def _click_checkbox(self, cap):
            pass

    report = auto_solve_page(
        DummyPage(),  # type: ignore[arg-type]
        DummySolver(),  # type: ignore[arg-type]
        max_wait_sec=2.0,
        humanize=False,
        retries=3,
    )
    assert not report.solved
    assert calls["n"] == 1


# ── proxy helpers ─────────────────────────────────────────────────────


def test_proxy_server_url_with_auth():
    from auto_captcha_solver import proxy_server_url

    url = proxy_server_url(
        {"scheme": "http", "host": "h", "port": 7777, "username": "u", "password": "p"}
    )
    assert url == "http://u:p@h:7777"


def test_proxy_server_url_without_auth():
    from auto_captcha_solver import proxy_server_url

    assert proxy_server_url({"scheme": "socks5", "host": "h", "port": 1080}) == "socks5://h:1080"


def test_check_proxy_egress_parses_bare_ip(monkeypatch):
    import auto_captcha_solver.autopilot as ap

    class R:
        status_code = 200
        text = "203.0.113.7"

    monkeypatch.setattr("requests.get", lambda *a, **k: R())
    out = ap.check_proxy_egress({"host": "h", "port": 1})
    assert out["ok"] and out["ip"] == "203.0.113.7"


def test_check_proxy_egress_parses_json(monkeypatch):
    import json

    import auto_captcha_solver.autopilot as ap

    class R:
        status_code = 200
        text = json.dumps({"ip": "198.51.100.9", "country": "US"})

    monkeypatch.setattr("requests.get", lambda *a, **k: R())
    out = ap.check_proxy_egress({"host": "h", "port": 1})
    assert out["ip"] == "198.51.100.9" and out["country"] == "US"


def test_check_proxy_egress_raises_on_http_error(monkeypatch):
    import auto_captcha_solver.autopilot as ap

    class R:
        status_code = 407
        text = "Proxy Authentication Required"

    monkeypatch.setattr("requests.get", lambda *a, **k: R())
    try:
        ap.check_proxy_egress({"host": "h", "port": 1})
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "407" in str(e)


def test_check_proxy_egress_raises_on_network(monkeypatch):
    import requests as _requests

    import auto_captcha_solver.autopilot as ap

    def boom(*a, **k):
        raise _requests.exceptions.ConnectionError("no route")

    monkeypatch.setattr("requests.get", boom)
    try:
        ap.check_proxy_egress({"host": "h", "port": 1})
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "no route" in str(e)
        assert "u:" not in str(e)  # never leak creds


def test_auto_solve_url_runs_proxy_preflight(monkeypatch):
    """With a proxy set, auto_solve_url must run the egress preflight (and
    still solve). Patch check_proxy_egress to record the call."""
    from auto_captcha_solver import auto_solve_url

    calls: dict = {}
    _install_fake_playwright(monkeypatch, calls)

    from auto_captcha_solver import autopilot

    def fake_check(proxy, **k):
        calls["preflight"] = proxy
        return {"ok": True, "ip": "203.0.113.9", "country": "US", "raw": ""}

    monkeypatch.setattr(autopilot, "check_proxy_egress", fake_check)
    proxy = {"scheme": "http", "host": "h", "port": 7777, "username": "u", "password": "p"}
    report = auto_solve_url("https://x", api_key="k", proxy=proxy, max_wait_sec=0.0, humanize=False)
    assert report.proxy == proxy
    assert calls["preflight"] == proxy


def test_auto_solve_url_skips_preflight_when_disabled(monkeypatch):
    from auto_captcha_solver import auto_solve_url

    calls: dict = {}
    _install_fake_playwright(monkeypatch, calls)

    from auto_captcha_solver import autopilot

    def fake_check(proxy, **k):
        calls["preflight"] = proxy
        return {"ok": True, "ip": "1.2.3.4", "country": None, "raw": ""}

    monkeypatch.setattr(autopilot, "check_proxy_egress", fake_check)
    proxy = {"scheme": "http", "host": "h", "port": 7777}
    auto_solve_url(
        "https://x", api_key="k", proxy=proxy, verify_proxy=False, max_wait_sec=0.0, humanize=False
    )
    assert "preflight" not in calls


def test_auto_solve_url_strict_mode_aborts_on_preflight_failure(monkeypatch):
    """verify_proxy='strict' must raise before any browser launch or credit
    spend when the egress preflight fails (dead proxy, bad creds, blocked
    network)."""
    from auto_captcha_solver import auto_solve_url

    calls: dict = {}
    _install_fake_playwright(monkeypatch, calls)

    from auto_captcha_solver import autopilot

    def fake_check(proxy, **k):
        raise RuntimeError("proxy connect failed")

    monkeypatch.setattr(autopilot, "check_proxy_egress", fake_check)
    proxy = {"scheme": "http", "host": "h", "port": 7777}
    try:
        auto_solve_url(
            "https://x",
            api_key="k",
            proxy=proxy,
            verify_proxy="strict",
            max_wait_sec=0.0,
            humanize=False,
        )
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "strict mode" in str(e)
    assert "launch" not in calls  # never got to browser launch


def test_auto_solve_url_strict_mode_passes_on_success(monkeypatch):
    """verify_proxy='strict' with a healthy proxy proceeds to solve."""
    from auto_captcha_solver import auto_solve_url

    calls: dict = {}
    _install_fake_playwright(monkeypatch, calls)

    from auto_captcha_solver import autopilot

    def fake_check(proxy, **k):
        return {"ok": True, "ip": "203.0.113.77", "country": "US", "raw": ""}

    monkeypatch.setattr(autopilot, "check_proxy_egress", fake_check)
    proxy = {"scheme": "http", "host": "h", "port": 7777}
    report = auto_solve_url(
        "https://x",
        api_key="k",
        proxy=proxy,
        verify_proxy="strict",
        max_wait_sec=0.0,
        humanize=False,
    )
    assert report.proxy == proxy
    assert calls.get("launch") is not None


# ── auto_solve_url browser mode (local vs CDP) ─────────────────────────


def _install_fake_playwright(monkeypatch, calls: dict) -> None:
    """Point `playwright.sync_api.sync_playwright` at a recording fake."""
    from auto_captcha_solver.autopilot import auto_solve_url  # noqa: F401  (import target exists)

    class FakePage:
        url = "https://x"

        def goto(self, *a, **k):
            pass

        def title(self):
            return "T"

        def is_closed(self):
            return False

        def screenshot(self, **k):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def add_init_script(self, **k):
            pass

        def close(self):
            calls["context_close"] = True

    class FakeBrowser:
        def new_context(self):
            return FakeContext()

        def close(self):
            calls["browser_close"] = True

    class FakeChromium:
        def launch(self, **k):
            calls["launch"] = k
            return FakeBrowser()

        def connect_over_cdp(self, url, **k):
            calls["connect"] = {"url": url, **k}
            return FakeBrowser()

    class FakePW:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_sync_playwright():
        return FakePW()

    monkeypatch.setattr("playwright.sync_api.sync_playwright", fake_sync_playwright)
    # No captchas to detect -> short-circuit the wait loop, no solve/sleep.
    from auto_captcha_solver import autopilot

    monkeypatch.setattr(autopilot, "wait_for_captchas", lambda *a, **k: [])


def test_auto_solve_url_cdp_mode_connects(monkeypatch):
    from auto_captcha_solver import auto_solve_url

    calls: dict = {}
    _install_fake_playwright(monkeypatch, calls)
    proxy = {"scheme": "http", "host": "h", "port": 7777, "username": "u", "password": "p"}

    report = auto_solve_url(
        "https://x",
        api_key="k",
        cdp_url="wss://browserless.io:443?token=***",
        proxy=proxy,
        max_wait_sec=0.0,
        humanize=False,
        stealth=True,
    )

    assert report.browser_mode == "cdp"
    assert calls.get("connect", {}).get("url") == "wss://browserless.io:443?token=***"
    assert "launch" not in calls  # must NOT launch locally in CDP mode
    assert calls.get("browser_close") is True
    assert calls.get("context_close") is True  # context torn down, remote browser kept
    # Proxy is still forwarded to the solver (token IP must match browser egress).
    assert report.proxy == proxy


def test_auto_solve_url_local_mode_launches(monkeypatch):
    from auto_captcha_solver import auto_solve_url

    calls: dict = {}
    _install_fake_playwright(monkeypatch, calls)

    report = auto_solve_url("https://x", api_key="k", max_wait_sec=0.0, humanize=False)

    assert report.browser_mode == "local"
    assert "launch" in calls
    assert "connect" not in calls
    # No proxy -> no proxy key on launch.
    assert "proxy" not in calls["launch"]


def test_cli_browser_headers_parses_key_value():
    from auto_captcha_solver.cli import _browser_headers

    class A:
        cdp_header = ["Authorization: Bearer abc", "X-Custom: v1"]

    assert _browser_headers(A()) == {"Authorization": "Bearer abc", "X-Custom": "v1"}


def test_cli_browser_headers_empty_returns_none():
    from auto_captcha_solver.cli import _browser_headers

    class A:
        cdp_header = []

    assert _browser_headers(A()) is None
