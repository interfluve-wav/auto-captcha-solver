"""Turnkey auto-solve helpers.

These wrap :class:`CaptchaSolver` into a one-call flow: launch (or reuse) a
browser, navigate, wait for captchas that render late, solve every challenge,
and report. No fiddly compose-your-own pipeline required.

Two entry points:

- :func:`auto_solve_page` — you already have a Playwright page; this waits for,
  solves, and injects every captcha on it. Wire it into your own scripts.
- :func:`auto_solve_url` — self-contained: launches its own browser (stealth by
  default), loads a URL, solves everything, and returns an :class:`AutoSolveReport`.

Proxy rotation is supported through ``proxy_pool``: one proxy is chosen per
session and used for BOTH browser egress and the solver request, so the token's
IP always matches the browser's IP (required for token validity, especially
Turnstile). Pass a callable ``proxy_rotator`` instead for custom rotation
(round-robin, random, sticky-by-host, ...).
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .solver import CaptchaSolver
from .stealth import apply_stealth
from .types import CaptchaInfo, CaptchaResult

__all__ = [
    "AutoSolveReport",
    "auto_solve_page",
    "auto_solve_url",
    "wait_for_captchas",
    "round_robin_rotator",
    "proxy_server_url",
    "check_proxy_egress",
]

Proxy = dict[str, Any]
ProxyRotator = Callable[[], Proxy | None]


@dataclass
class AutoSolveReport:
    """Outcome of a turnkey auto-solve run."""

    url: str
    detected: list[CaptchaInfo] = field(default_factory=list)
    results: list[CaptchaResult] = field(default_factory=list)
    elapsed_sec: float = 0.0
    proxy: Proxy | None = None
    page_title: str = ""
    browser_mode: str = "local"

    @property
    def solved(self) -> bool:
        return any(r.success for r in self.results)

    @property
    def summary(self) -> str:
        if not self.detected:
            return f"No captchas detected on {self.url}"
        statuses = " | ".join(
            f"{r.captcha_type}:{'OK' if r.success else r.error or 'failed'}" for r in self.results
        )
        return f"{self.url} — {statuses}"


def round_robin_rotator(proxies: Sequence[Proxy]) -> ProxyRotator:
    """Return a rotator that cycles a proxy pool, one per call (per session)."""
    if not proxies:
        return lambda: None
    state = {"i": 0}

    def _rotate() -> Proxy | None:
        proxy = proxies[state["i"] % len(proxies)]
        state["i"] += 1
        return proxy

    return _rotate


def proxy_server_url(proxy: Proxy) -> str:
    """Render a Playwright/requests proxy as ``scheme://user:pass@host:port``."""
    scheme = proxy.get("scheme", "http")
    host = proxy.get("host", "")
    port = proxy.get("port", "")
    auth = ""
    if proxy.get("username") or proxy.get("password"):
        auth = f"{proxy.get('username', '')}:{proxy.get('password', '')}@"
    return f"{scheme}://{auth}{host}:{port}"


def check_proxy_egress(
    proxy: Proxy,
    url: str = "https://api.ipify.org",
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Verify a proxy works and report its egress IP.

    Send a request THROUGH the proxy to an IP-echo endpoint and parse the
    answer. Use this before a Turnstile/reCAPTCHA-v3 solve: NopeCHA requires
    the solver's exit IP to match the browser's, so a dead or wrong proxy
    shows up later as a queue-level 'Invalid request' — catching it here is
    far cheaper.

    Args:
        proxy: Proxy dict (scheme/host/port/username/password).
        url: IP-echo endpoint to fetch through the proxy.
        timeout: Request timeout in seconds.

    Returns:
        ``{"ok": True, "ip": str, "country": str|None, "raw": str}`` on
        success.

    Raises:
        RuntimeError: if the proxy connection or the echo fetch fails (bad
            creds, blocked network, dead endpoint). The message never contains
            credentials.
    """
    import json as _json

    import requests

    server = proxy_server_url(proxy)
    proxies = {"http": server, "https": server}
    try:
        r = requests.get(url, proxies=proxies, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        host = proxy.get("host", "?")
        raise RuntimeError(
            f"proxy egress check failed for {host}: {type(exc).__name__}: {exc}"
        ) from exc
    if r.status_code != 200:
        raise RuntimeError(
            f"proxy egress check got HTTP {r.status_code} from {url} "
            "(proxy may be rejecting auth)"
        )
    ip: str | None = None
    country: str | None = None
    raw = r.text.strip()[:300]
    # ipinfo-style JSON first, then bare-IP responses.
    try:
        data = _json.loads(r.text)
        ip = data.get("ip")
        country = data.get("country")
    except Exception:
        parts = raw.split()
        if parts and parts[0].count(".") == 3:
            ip = parts[0]
    if not ip:
        raise RuntimeError(f"proxy egress check: could not parse IP from {raw!r}")
    return {"ok": True, "ip": ip, "country": country, "raw": raw}


def wait_for_captchas(
    solver: CaptchaSolver,
    page: Any,
    timeout_sec: float = 30.0,
    interval_sec: float = 1.0,
    click_checkbox: bool = True,
) -> list[CaptchaInfo]:
    """Poll until the page surfaces captcha widgets.

    Many sites lazy-load challenge widgets after the main page settles, and
    Turnstile pages never reach Playwright's ``networkidle`` (the widget holds
    a long-lived connection). Polling :meth:`CaptchaSolver.detect` sidesteps
    both problems instead of hanging on a load-state wait.

    Wraps each entry in the same shape ``detect()`` returns and clicks the
    hCaptcha/reCAPTCHA checkbox if one becomes available.
    """
    deadline = time.monotonic() + timeout_sec
    last: list[CaptchaInfo] = []
    while time.monotonic() < deadline:
        found = solver.detect(page)
        if found:
            if click_checkbox:
                for cap in found:
                    if cap.get("frame"):
                        try:
                            solver._click_checkbox(cap)
                        except Exception:
                            pass
            return found
        last = found
        time.sleep(interval_sec)
    # Page might have been removed or navigated away mid-poll.
    try:
        if page.is_closed():
            return []
    except Exception:
        pass
    return last


def auto_solve_page(
    page: Any,
    solver: CaptchaSolver,
    *,
    max_wait_sec: float = 30.0,
    humanize: bool = True,
    retries: int = 1,
    click_checkbox: bool = True,
) -> AutoSolveReport:
    """Wait for and solve every captcha on an existing page.

    Args:
        page: Playwright page you already control.
        solver: Configured CaptchaSolver.
        max_wait_sec: How long to wait for widgets that render late.
        humanize: Wait a short random beat before solving (looks less scripted).
        retries: Extra solve attempts per captcha on transient failure.
        click_checkbox: Click the hCaptcha/reCAPTCHA checkbox when present.

    Returns:
        AutoSolveReport with per-captcha results.
    """
    start = time.monotonic()
    detected = wait_for_captchas(
        solver, page, timeout_sec=max_wait_sec, click_checkbox=click_checkbox
    )

    useragent = solver._page_useragent(page)
    cookies = solver._page_cookies(page)

    results: list[CaptchaResult] = []
    for cap in detected:
        data = solver._widget_data(page, cap["type"])
        result = solver.solve(
            cap["type"],
            cap["sitekey"],
            cap["url"],
            useragent=useragent,
            cookies=cookies,
            data=data,
        )
        for _attempt in range(retries):
            if result.success:
                break
            if result.error and "timeout" not in result.error.lower() and "network" not in result.error.lower():
                break  # non-transient (bad key, out of credit, unsupported...) — don't retry
            if humanize:
                time.sleep(random.uniform(1.5, 3.5))
            result = solver.solve(
                cap["type"],
                cap["sitekey"],
                cap["url"],
                useragent=useragent,
                cookies=cookies,
                data=data,
            )
        if result.success:
            try:
                solver.inject(page, cap["type"], result.token)
            except Exception:
                pass
        results.append(result)

    page_title = ""
    try:
        page_title = page.title()
    except Exception:
        pass

    return AutoSolveReport(
        url=getattr(page, "url", ""),
        detected=detected,
        results=results,
        elapsed_sec=time.monotonic() - start,
        page_title=page_title,
    )


def auto_solve_url(
    url: str,
    api_key: str,
    *,
    provider: str = "nopecha",
    headless: bool = True,
    stealth: bool = True,
    proxy: Proxy | None = None,
    proxy_pool: Sequence[Proxy] | None = None,
    proxy_rotator: ProxyRotator | None = None,
    max_wait_sec: float = 30.0,
    humanize: bool = True,
    retries: int = 1,
    click_checkbox: bool = True,
    screenshot_path: str | None = None,
    launch_kwargs: dict[str, Any] | None = None,
    cdp_url: str | None = None,
    connect_kwargs: dict[str, Any] | None = None,
    verify_proxy: bool | str = True,
    solver_kwargs: dict[str, Any] | None = None,
) -> AutoSolveReport:
    """Self-contained: launch a browser, load a URL, solve every captcha, report.

    Two browser modes:

    - **Local (default)** — launches a fresh Chromium via
      ``chromium.launch()``. ``proxy`` is applied to that browser's egress AND
      forwarded to the solve provider, so the token's IP always matches the
      browser's IP.
    - **Remote / hosted** — pass ``cdp_url`` (a ``ws://`` or ``http://``
      ``connect_over_cdp`` endpoint) to drive an existing browser such as
      Browserless.io, Steel, or any CDP-hosted browser. The browser's egress is
      whatever the host uses (you cannot re-route it), so to keep the token's
      IP valid, pass a ``proxy`` whose egress IP matches the remote browser's —
      it is forwarded to the solve provider. This function opens a fresh context
      on the remote browser, solves, and closes *that context* without tearing
      down the remote browser session.

    Args:
        url: Page to load.
        api_key: Provider API key.
        provider: ``"nopecha"`` (default) or ``"captchaai"``.
        headless: Launch headless (default True; ignored in CDP mode — the
            remote browser's own headless setting applies).
        stealth: Apply fingerprint masking (default True).
        proxy: Single proxy forwarded to the solve provider (and, in local
            mode, to the launched browser's egress).
        proxy_pool: List of proxies rotated per session; one picked per call and
            used for browser + solver so the token IP matches client IP.
        proxy_rotator: Custom callable returning a proxy dict (overrides pool).
        max_wait_sec: How long to wait for late-rendering widgets.
        humanize: Random short beat before solving (looks less scripted).
        retries: Extra solve attempts per captcha on transient failure.
        click_checkbox: Click hCaptcha/reCAPTCHA checkbox when present.
        screenshot_path: Save a screenshot to this path after solving.
        launch_kwargs: Extra Playwright ``chromium.launch()`` kwargs (local mode
            only; ignored in CDP mode).
        cdp_url: A ``connect_over_cdp`` endpoint (Browserless, Steel, etc.). When
            set, connects to that remote browser instead of launching locally.
        connect_kwargs: Extra Playwright ``chromium.connect_over_cdp()`` kwargs
            (e.g. ``headers={"Authorization": ...}`` for Browserless,
            ``timeout``).
        solver_kwargs: Extra CaptchaSolver kwargs (e.g. ``timeout_sec=300``,
            ``max_polls=60``) — useful for Turnstile's slow experimental queue.
        verify_proxy: Preflight egress check behavior. ``True`` (default)
            warns and continues on failure; ``"strict"`` aborts with
            ``RuntimeError`` before any browser launch or credit spend;
            ``False`` skips the check entirely.

    Returns:
        AutoSolveReport (``solved`` is True if any captcha was solved).
    """
    start = time.monotonic()

    rotator = proxy_rotator
    if rotator is None and (proxy_pool or (proxy is None and proxy_pool is not None)):
        rotator = round_robin_rotator(proxy_pool or [])
    session_proxy = proxy
    if rotator is not None:
        session_proxy = rotator() or proxy

    if session_proxy and verify_proxy:
        # Preflight: prove the proxy connects and show its egress IP BEFORE
        # spending credits. For Turnstile/reCAPTCHA-v3 the solver's exit IP
        # must match the browser's — a dead proxy here becomes a queue-level
        # 'Invalid request' later. Output never contains credentials.
        try:
            info = check_proxy_egress(session_proxy)
            print(f"Proxy preflight OK — egress {info['ip']} ({info['country']})")
        except RuntimeError as exc:
            if verify_proxy == "strict":
                raise RuntimeError(
                    f"proxy preflight FAILED (strict mode): {exc}"
                ) from exc
            print(f"Proxy preflight FAILED — {exc}")
            print("Continuing anyway (set verify_proxy=False to silence this); "
                  "Turnstile/reCAPTCHA-v3 solves will likely fail.")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "auto_solve_url needs playwright: pip install auto-captcha-solver[playwright]"
        ) from exc

    launch: dict[str, Any] = {"headless": headless}
    owns_browser = cdp_url is None
    if owns_browser:
        if session_proxy:
            # Playwright's launch proxy: {"server": "scheme://host:port", "username": ..., "password": ...}
            scheme = session_proxy.get("scheme", "http")
            host = session_proxy.get("host")
            port = session_proxy.get("port")
            if host and port:
                launch["proxy"] = {
                    "server": f"{scheme}://{host}:{port}",
                    "username": session_proxy.get("username", ""),
                    "password": session_proxy.get("password", ""),
                }
        if launch_kwargs:
            launch.update(launch_kwargs)
    else:
        # Remote/hosted browser (Browserless, Steel, ...): connect, don't launch.
        # Its egress IP is fixed by the host — match it with `proxy` for the
        # solve request or the token will be minted for a different IP.
        launch = {}

    solver = CaptchaSolver(
        api_key=api_key,
        provider=provider,
        proxy=session_proxy,
        **(solver_kwargs or {}),
    )

    with sync_playwright() as pw:
        if cdp_url is None:
            browser = pw.chromium.launch(**launch)
        else:
            browser = pw.chromium.connect_over_cdp(cdp_url, **(connect_kwargs or {}))
        context = browser.new_context()
        if stealth:
            apply_stealth(context)
        page = context.new_page()
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        report = auto_solve_page(
            page,
            solver,
            max_wait_sec=max_wait_sec,
            humanize=humanize,
            retries=retries,
            click_checkbox=click_checkbox,
        )
        if screenshot_path:
            page.screenshot(path=screenshot_path, full_page=True)
        context.close()
        # Local mode: browser.close() tears down the launched browser.
        # CDP mode: browser.close() only severs the CDP connection — the remote
        # browser (Browserless/Steel session) keeps running for other tabs.
        browser.close()

    report.elapsed_sec = time.monotonic() - start
    report.proxy = session_proxy
    report.browser_mode = "cdp" if cdp_url else "local"
    return report
