"""
Core captcha solver — detects and solves captchas via pluggable providers.

Supported providers: NopeCHA (default), CaptchaAI (2Captcha-compatible API).

Usage:
    from auto_captcha_solver import CaptchaSolver

    solver = CaptchaSolver(api_key="your-key", provider="nopecha")
    results = solver.auto_solve(page)
"""

from __future__ import annotations

import re
import time
from typing import Any, cast

from .providers import get_provider
from .providers.base import CaptchaProvider
from .providers.nopecha import EXPERIMENTAL_ENDPOINTS, TOKEN_ENDPOINTS
from .types import CaptchaInfo, CaptchaResult, sanitize_detect_results

__all__ = [
    "CaptchaSolver",
    "CaptchaResult",
    "CaptchaInfo",
    "sanitize_detect_results",
    "TOKEN_ENDPOINTS",
    "EXPERIMENTAL_ENDPOINTS",
]


class CaptchaSolver:
    """
    Drop-in captcha solver for Playwright browser automation.

    Args:
        api_key: Provider API key
        provider: ``"nopecha"`` (default) or ``"captchaai"``
        poll_interval: Seconds between status polls (default: 4.0)
        max_polls: Maximum polling attempts (default: 25)
        timeout_sec: Overall timeout in seconds (default: 120.0)
        proxy: Optional proxy dict (format depends on provider)
    """

    def __init__(
        self,
        api_key: str,
        provider: str | CaptchaProvider = "nopecha",
        poll_interval: float = 4.0,
        max_polls: int = 25,
        timeout_sec: float = 120.0,
        proxy: dict[str, Any] | None = None,
    ):
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self.timeout_sec = timeout_sec
        self.proxy = proxy
        if isinstance(provider, str):
            self._provider = get_provider(provider, api_key)
        else:
            self._provider = provider
        self.provider = self._provider.name

    def get_credits(self) -> int:
        """Check remaining provider credits/balance."""
        return self._provider.get_credits()

    # ── Detection ────────────────────────────────────────────────

    def detect(self, page: Any) -> list[CaptchaInfo]:
        """
        Scan a Playwright page for captcha challenges.

        Detects: hCaptcha, reCAPTCHA v2, reCAPTCHA v3, Cloudflare Turnstile.

        Returns list of dicts: {type, sitekey, url, frame}
        """
        found = []
        page_url = page.url
        seen_types = set()

        # Method 1: Check Playwright frames
        for frame in page.frames:
            furl = frame.url.lower()

            if "hcaptcha.com" in furl and "frame=checkbox" in furl and "hcaptcha" not in seen_types:
                sitekey = self._extract_sitekey(frame.url)
                if not sitekey:
                    sitekey = self._extract_dom_sitekey(page, "hcaptcha")
                if sitekey:
                    found.append(
                        {
                            "type": "hcaptcha",
                            "sitekey": sitekey,
                            "url": page_url,
                            "frame": frame,
                        }
                    )
                    seen_types.add("hcaptcha")

            elif "recaptcha" in furl and "/anchor" in furl and "recaptcha2" not in seen_types and "recaptcha3" not in seen_types:
                sitekey = self._extract_sitekey(frame.url)
                if not sitekey:
                    sitekey = self._extract_dom_sitekey(page, "recaptcha")
                if sitekey:
                    # Anchor iframe carries size=normal (v2) or size=invisible (v3 enterprise)
                    is_invisible = "size=invisible" in furl
                    found.append(
                        {
                            "type": "recaptcha3" if is_invisible else "recaptcha2",
                            "sitekey": sitekey,
                            "url": page_url,
                            "frame": frame,
                        }
                    )
                    seen_types.add("recaptcha3" if is_invisible else "recaptcha2")

            elif "challenges.cloudflare.com" in furl and "turnstile" not in seen_types:
                sitekey = self._extract_sitekey(frame.url)
                if not sitekey:
                    sitekey = self._extract_dom_sitekey(page, "turnstile")
                if sitekey:
                    found.append(
                        {
                            "type": "turnstile",
                            "sitekey": sitekey,
                            "url": page_url,
                            "frame": frame,
                        }
                    )
                    seen_types.add("turnstile")

        # Method 2: DOM fallback for each type — must match specific widget markers
        if "hcaptcha" not in seen_types:
            has_hcaptcha_widget = page.evaluate("""() => {
                return !!document.querySelector('.h-captcha, [data-hcaptcha-sitekey]') ||
                    document.querySelectorAll('iframe[src*="hcaptcha"]').length > 0;
            }""")
            if has_hcaptcha_widget:
                sk = self._extract_dom_sitekey(page, "hcaptcha")
                if sk:
                    found.append({"type": "hcaptcha", "sitekey": sk, "url": page_url})
                    seen_types.add("hcaptcha")

        if "recaptcha2" not in seen_types and "recaptcha3" not in seen_types:
            has_recaptcha_widget = page.evaluate("""() => {
                // Real reCAPTCHA iframes live under google.com/recaptcha, recaptcha.net,
                // or gstatic.com/recaptcha. We must NOT match a bare 'recaptcha' substring:
                // the hCaptcha widget iframe URL carries `recaptchacompat=true`, which
                // would otherwise false-positive here and mis-detect a phantom reCAPTCHA.
                return !!document.querySelector('.g-recaptcha, .g-recaptcha-response') ||
                    document.querySelectorAll(
                        'iframe[src*="google.com/recaptcha"], iframe[src*="recaptcha.net"], iframe[src*="gstatic.com/recaptcha"]'
                    ).length > 0;
            }""")
            if has_recaptcha_widget:
                sk = self._extract_dom_sitekey(page, "recaptcha")
                if sk:
                    # Distinguish v2 (visible widget) from v3 (invisible).
                    # A rendered .g-recaptcha container is ALWAYS a v2 widget —
                    # v3 has no container, only a script (render=explicit/none)
                    # plus a floating badge. The old `data-size` check was wrong:
                    # default-size v2 widgets don't set data-size, so they were
                    # mislabeled v3 whenever the anchor iframe hadn't loaded yet.
                    has_container = page.evaluate("""() => {
                        return !!document.querySelector('.g-recaptcha');
                    }""")
                    if has_container:
                        found.append({"type": "recaptcha2", "sitekey": sk, "url": page_url})
                    else:
                        found.append({"type": "recaptcha3", "sitekey": sk, "url": page_url})
                    seen_types.add("recaptcha2")

        if "recaptcha3" not in seen_types and "recaptcha2" not in seen_types:
            has_v3 = page.evaluate("""() => {
                // Must have a real reCAPTCHA script/widget with render param, AND no
                // visible widget. Match only genuine reCAPTCHA origins (not the
                // `recaptchacompat=true` substring in hCaptcha iframe URLs).
                if (document.querySelector('.g-recaptcha, .g-recaptcha-response, iframe[src*="google.com/recaptcha"], iframe[src*="recaptcha.net"], iframe[src*="gstatic.com/recaptcha"]')) return false;
                const scripts = document.querySelectorAll('script[src*="google.com/recaptcha"], script[src*="recaptcha.net"], script[src*="gstatic.com/recaptcha"]');
                for (const s of scripts) {
                    if (s.src.includes('render=')) return true;
                }
                return false;
            }""")
            if has_v3:
                sk = self._extract_dom_sitekey(page, "recaptcha3")
                if sk:
                    found.append({"type": "recaptcha3", "sitekey": sk, "url": page_url})
                    seen_types.add("recaptcha3")

        if "turnstile" not in seen_types:
            has_turnstile_widget = page.evaluate("""() => {
                return !!document.querySelector('.cf-turnstile') ||
                    document.querySelectorAll('script[src*="turnstile"]').length > 0;
            }""")
            if has_turnstile_widget:
                sk = self._extract_dom_sitekey(page, "turnstile")
                if sk:
                    found.append({"type": "turnstile", "sitekey": sk, "url": page_url})

        return found

    def _extract_sitekey(self, url: str) -> str | None:
        """Extract sitekey from iframe URL query params or fragment."""
        # reCAPTCHA style: ?k=<sitekey>
        match = re.search(r"[?&#]k=([A-Za-z0-9_-]+)", url)
        if match:
            return match.group(1)
        # hCaptcha/Turnstile style: sitekey=<sitekey>
        match = re.search(r"[?&#]sitekey=([A-Za-z0-9_-]+)", url)
        return match.group(1) if match else None

    def _extract_dom_sitekey(self, page: Any, captcha_type: str) -> str | None:
        """Extract sitekey from page DOM."""
        try:
            if captcha_type == "hcaptcha":
                return cast(
                    str | None,
                    page.evaluate("""() => {
                    // data-sitekey on any element
                    let el = document.querySelector('[data-sitekey]');
                    if (el) return el.getAttribute('data-sitekey');
                    // iframe src
                    for (const f of document.querySelectorAll('iframe')) {
                        const m = f.src.match(/[?&#]sitekey=([A-Za-z0-9_-]+)/);
                        if (m) return m[1];
                    }
                    return null;
                }"""),
                )
            elif captcha_type == "recaptcha":
                return cast(
                    str | None,
                    page.evaluate("""() => {
                    // Only the reCAPTCHA widget carries its own sitekey. Do NOT fall
                    // back to a bare [data-sitekey]: hCaptcha/Turnstile use that same
                    // attribute, so a bare match would steal the wrong provider's key.
                    let el = document.querySelector('.g-recaptcha[data-sitekey], .g-recaptcha');
                    if (el) return el.getAttribute('data-sitekey');
                    for (const f of document.querySelectorAll('iframe[src*="google.com/recaptcha"], iframe[src*="recaptcha.net"]')) {
                        const m = f.src.match(/[?&#]k=([A-Za-z0-9_-]+)/);
                        if (m) return m[1];
                    }
                    return null;
                }"""),
                )
            elif captcha_type == "recaptcha3":
                return cast(
                    str | None,
                    page.evaluate(r"""() => {
                    // reCAPTCHA v3 is loaded via grecaptcha.execute on a real reCAPTCHA
                    // script (only match genuine reCAPTCHA origins).
                    const scripts = document.querySelectorAll('script[src*="google.com/recaptcha"], script[src*="recaptcha.net"], script[src*="gstatic.com/recaptcha"]');
                    for (const s of scripts) {
                        const m = s.src.match(/[?&]render=([A-Za-z0-9_-]+)/);
                        if (m) return m[1];
                    }
                    // Check inline scripts (grecaptcha.execute is reCAPTCHA-specific)
                    for (const s of document.querySelectorAll('script')) {
                        const m = (s.textContent || '').match(/grecaptcha\.execute\(['"]([^'"]+)['"]/);
                        if (m) return m[1];
                    }
                    return null;
                }"""),
                )
            elif captcha_type == "turnstile":
                return cast(
                    str | None,
                    page.evaluate("""() => {
                    let el = document.querySelector('[data-sitekey]');
                    if (el) {
                        const parent = el.closest('.cf-turnstile') || el;
                        if (parent) return el.getAttribute('data-sitekey');
                    }
                    // Turnstile script
                    for (const s of document.querySelectorAll('script[src*="turnstile"]')) {
                        const m = s.src.match(/[?&]sitekey=([A-Za-z0-9_-]+)/);
                        if (m) return m[1];
                    }
                    return null;
                }"""),
                )
        except Exception:
            pass
        return None

    # ── Solving ──────────────────────────────────────────────────

    def solve(
        self,
        captcha_type: str,
        sitekey: str,
        url: str,
        *,
        useragent: str | None = None,
        cookies: list[dict[str, Any]] | None = None,
        data: dict[str, Any] | None = None,
    ) -> CaptchaResult:
        """Submit a captcha to the configured provider and poll for the solved token.

        Args:
            captcha_type: One of the provider's supported types.
            sitekey: Public site key of the captcha.
            url: URL of the page hosting the captcha.
            useragent: Real browser User-Agent to match the solve context.
            cookies: Browser cookies (Playwright ``context.cookies()`` shape).
            data: Captcha-type metadata (reCAPTCHA v3 ``action``/``s``/``theme``/
                ``enterprise``; Turnstile ``action``/``cdata``).
        """
        if captcha_type == "turnstile":
            if not self.proxy:
                return CaptchaResult(
                    success=False,
                    captcha_type=captcha_type,
                    error=(
                        "turnstile requires a proxy: NopeCHA's schema marks proxy "
                        "Required for this endpoint (the solver's exit IP must match "
                        "the client's). Pass CaptchaSolver(proxy={...})."
                    ),
                )
            if self.proxy.get("username") or self.proxy.get("password"):
                scheme = self.proxy.get("scheme", "http")
                if scheme not in ("http", "https"):
                    import warnings

                    warnings.warn(
                        f"proxy scheme '{scheme}' ignores username/password; "
                        "NopeCHA only supports proxy auth for http/https.",
                        stacklevel=2,
                    )
        return self._provider.solve(
            captcha_type,
            sitekey,
            url,
            poll_interval=self.poll_interval,
            max_polls=self.max_polls,
            timeout_sec=self.timeout_sec,
            proxy=self.proxy,
            useragent=useragent,
            cookies=cookies,
            data=data,
        )

    # ── Injection ────────────────────────────────────────────────

    def inject(self, page: Any, captcha_type: str, token: str) -> bool:
        """Inject solved token into the page's captcha callback."""
        try:
            if captcha_type == "hcaptcha":
                page.evaluate(
                    """(t) => {
                    document.querySelectorAll(
                        "textarea[name='h-captcha-response'], textarea#g-recaptcha-response"
                    ).forEach(ta => ta.value = t);
                    if (typeof hcaptcha !== 'undefined') {
                        try { hcaptcha.execute(); } catch(e) {}
                    }
                }""",
                    token,
                )

            elif captcha_type == "recaptcha2":
                page.evaluate(
                    """(t) => {
                    const ta = document.getElementById("g-recaptcha-response");
                    if (ta) { ta.value = t; ta.style.display = "block"; }
                    document.querySelectorAll("textarea[name='g-recaptcha-response']")
                        .forEach(x => x.value = t);
                    try {
                        const clients = Object.values(___grecaptcha_cfg.clients);
                        for (const cl of clients) {
                            for (const k of Object.keys(cl)) {
                                const o = cl[k];
                                if (o && typeof o.callback === "function") {
                                    o.callback(t);
                                    return;
                                }
                            }
                        }
                    } catch(e) {}
                }""",
                    token,
                )

            elif captcha_type == "recaptcha3":
                page.evaluate(
                    """(t) => {
                    // reCAPTCHA v3 — inject token and trigger callback
                    document.querySelectorAll("textarea[name='g-recaptcha-response']")
                        .forEach(x => x.value = t);
                    if (typeof ___grecaptcha_cfg !== 'undefined') {
                        try {
                            const clients = Object.values(___grecaptcha_cfg.clients);
                            for (const cl of clients) {
                                for (const k of Object.keys(cl)) {
                                    const o = cl[k];
                                    if (o && typeof o.callback === "function") {
                                        o.callback(t);
                                        return;
                                    }
                                }
                            }
                        } catch(e) {}
                    }
                }""",
                    token,
                )

            elif captcha_type == "turnstile":
                page.evaluate(
                    """(t) => {
                    // Cloudflare Turnstile — inject into hidden input
                    document.querySelectorAll("input[name='cf-turnstile-response']")
                        .forEach(x => x.value = t);
                    document.querySelectorAll("textarea[name='cf-turnstile-response']")
                        .forEach(x => x.value = t);
                    // Try calling the turnstile callback
                    if (typeof turnstile !== 'undefined') {
                        try { turnstile.getResponse(); } catch(e) {}
                    }
                }""",
                    token,
                )

            return True
        except Exception:
            return False

    # ── Auto Flow ────────────────────────────────────────────────

    def auto_solve(
        self,
        page: Any,
        click_checkbox: bool = True,
        clone_context: bool = True,
    ) -> list[CaptchaResult]:
        """
        Detect → Solve → Inject all captchas on the page.

        When ``clone_context`` is true (default), the page's real User-Agent and
        cookies are forwarded to the provider so the token is minted in a context
        matching the presenting browser — critical for evading token-context
        binding checks (especially Turnstile / reCAPTCHA v3).

        Args:
            page: Playwright page object
            click_checkbox: Try to click captcha checkbox first
            clone_context: Forward the browser's UA + cookies to the solver

        Returns:
            List of CaptchaResult for each captcha found.
        """
        results = []
        captchas = self.detect(page)

        useragent = None
        cookies = None
        if clone_context:
            useragent = self._page_useragent(page)
            cookies = self._page_cookies(page)

        for cap in captchas:
            if click_checkbox and cap.get("frame"):
                self._click_checkbox(cap)

            data = self._widget_data(page, cap["type"])

            result = self.solve(
                cap["type"],
                cap["sitekey"],
                cap["url"],
                useragent=useragent,
                cookies=cookies,
                data=data,
            )

            if result.success:
                self.inject(page, cap["type"], result.token)

            results.append(result)

        return results

    def _page_useragent(self, page: Any) -> str | None:
        """Read the live browser User-Agent from the page."""
        try:
            ua = page.evaluate("() => navigator.userAgent")
            return str(ua) if ua else None
        except Exception:
            return None

    def _page_cookies(self, page: Any) -> list[dict[str, Any]] | None:
        """Read cookies for the page's URL from the browser context."""
        try:
            ctx = getattr(page, "context", None)
            if ctx is None:
                return None
            cookies = ctx.cookies(page.url)
            return list(cookies) if cookies else None
        except Exception:
            return None

    def _widget_data(self, page: Any, captcha_type: str) -> dict[str, Any] | None:
        """Extract type-specific metadata (data-action) from the live widget."""
        try:
            if captcha_type == "recaptcha3":
                action = page.evaluate(
                    """() => {
                    const el = document.querySelector('[data-action]');
                    return el ? el.getAttribute('data-action') : null;
                }"""
                )
                return {"action": str(action)} if action else None
            if captcha_type == "turnstile":
                info = page.evaluate(
                    """() => {
                    const el = document.querySelector('.cf-turnstile, [data-sitekey]');
                    if (!el) return null;
                    return {
                        action: el.getAttribute('data-action'),
                        cdata: el.getAttribute('data-cdata'),
                    };
                }"""
                )
                if info and (info.get("action") or info.get("cdata")):
                    return {k: v for k, v in info.items() if v}
        except Exception:
            pass
        return None

    def _click_checkbox(self, cap: dict) -> None:
        try:
            frame = cap["frame"]
            if cap["type"] == "hcaptcha":
                cb = frame.locator("#checkbox, .checkbox")
                if cb.count() > 0:
                    cb.click(timeout=3000)
                    time.sleep(1)
            elif cap["type"] == "recaptcha2":
                cb = frame.locator(".recaptcha-checkbox-border")
                if cb.count() > 0:
                    cb.click(timeout=3000)
                    time.sleep(1)
            # Turnstile and reCAPTCHA v3 don't need checkbox clicks
        except Exception:
            pass

    # ── Info ──────────────────────────────────────────────────────

    def supported_types(self) -> list[str]:
        """Return captcha types with stable support for the active provider."""
        return self._provider.supported_types()

    def experimental_types(self) -> list[str]:
        """Return experimental captcha types for the active provider."""
        return self._provider.experimental_types()

    @staticmethod
    def default_supported_types() -> list[str]:
        """Default (NopeCHA) stable captcha types."""
        from .providers.nopecha import NopechaProvider

        return NopechaProvider.supported_types()

    @staticmethod
    def default_experimental_types() -> list[str]:
        """Default (NopeCHA) experimental captcha types."""
        from .providers.nopecha import NopechaProvider

        return NopechaProvider.experimental_types()
