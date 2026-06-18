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

            elif "recaptcha" in furl and "/anchor" in furl and "recaptcha2" not in seen_types:
                sitekey = self._extract_sitekey(frame.url)
                if not sitekey:
                    sitekey = self._extract_dom_sitekey(page, "recaptcha")
                if sitekey:
                    found.append(
                        {
                            "type": "recaptcha2",
                            "sitekey": sitekey,
                            "url": page_url,
                            "frame": frame,
                        }
                    )
                    seen_types.add("recaptcha2")

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

        if "recaptcha2" not in seen_types:
            has_recaptcha_widget = page.evaluate("""() => {
                return !!document.querySelector('.g-recaptcha, .g-recaptcha-response') ||
                    document.querySelectorAll('iframe[src*="recaptcha"]').length > 0;
            }""")
            if has_recaptcha_widget:
                sk = self._extract_dom_sitekey(page, "recaptcha")
                if sk:
                    # Distinguish v2 (visible widget) from v3 (invisible)
                    has_size = page.evaluate("""() => {
                        return !!document.querySelector('.g-recaptcha[data-size], [data-size]');
                    }""")
                    if has_size:
                        found.append({"type": "recaptcha2", "sitekey": sk, "url": page_url})
                    else:
                        found.append({"type": "recaptcha3", "sitekey": sk, "url": page_url})
                    seen_types.add("recaptcha2")

        if "recaptcha3" not in seen_types and "recaptcha2" not in seen_types:
            has_v3 = page.evaluate("""() => {
                // Must have recaptcha script with render param, AND no visible widget
                if (document.querySelector('.g-recaptcha, .g-recaptcha-response, iframe[src*="recaptcha"]')) return false;
                const scripts = document.querySelectorAll('script[src*="recaptcha"]');
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
                    let el = document.querySelector('.g-recaptcha, [data-sitekey]');
                    if (el) return el.getAttribute('data-sitekey');
                    for (const f of document.querySelectorAll('iframe')) {
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
                    // reCAPTCHA v3 is loaded via grecaptcha.enterprise.execute or grecaptcha.execute
                    const scripts = document.querySelectorAll('script[src*="recaptcha"]');
                    for (const s of scripts) {
                        const m = s.src.match(/[?&]render=([A-Za-z0-9_-]+)/);
                        if (m) return m[1];
                    }
                    // Check inline scripts
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

    def solve(self, captcha_type: str, sitekey: str, url: str) -> CaptchaResult:
        """Submit a captcha to the configured provider and poll for the solved token."""
        return self._provider.solve(
            captcha_type,
            sitekey,
            url,
            poll_interval=self.poll_interval,
            max_polls=self.max_polls,
            timeout_sec=self.timeout_sec,
            proxy=self.proxy,
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

    def auto_solve(self, page: Any, click_checkbox: bool = True) -> list[CaptchaResult]:
        """
        Detect → Solve → Inject all captchas on the page.

        Args:
            page: Playwright page object
            click_checkbox: Try to click captcha checkbox first

        Returns:
            List of CaptchaResult for each captcha found.
        """
        results = []
        captchas = self.detect(page)

        for cap in captchas:
            if click_checkbox and cap.get("frame"):
                self._click_checkbox(cap)

            result = self.solve(cap["type"], cap["sitekey"], cap["url"])

            if result.success:
                self.inject(page, cap["type"], result.token)

            results.append(result)

        return results

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
