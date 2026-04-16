"""
Core captcha solver — detects and solves captchas via NopeCHA Token API.

Supported types: hCaptcha, reCAPTCHA v2, reCAPTCHA v3, Cloudflare Turnstile.

Usage:
    from auto_captcha import CaptchaSolver

    solver = CaptchaSolver(api_key="your-key")
    results = solver.auto_solve(page)
"""

import requests
import re
import time
from dataclasses import dataclass
from typing import Optional


# NopeCHA Token API endpoints
TOKEN_ENDPOINTS = {
    "hcaptcha":    "/v1/token/hcaptcha",
    "recaptcha2":  "/v1/token/recaptcha2",
    "recaptcha3":  "/v1/token/recaptcha3",
}

# Experimental — NopeCHA queue extremely slow (5-10+ min), needs proxy
EXPERIMENTAL_ENDPOINTS = {
    "turnstile":   "/v1/token/turnstile",
}


@dataclass
class CaptchaResult:
    """Result of a captcha solve attempt."""
    success: bool
    captcha_type: str = ""
    token: str = ""
    error: str = ""
    attempts: int = 0
    elapsed_sec: float = 0.0


class CaptchaSolver:
    """
    Drop-in captcha solver for Playwright browser automation.
    Supports hCaptcha, reCAPTCHA v2/v3, and Cloudflare Turnstile via NopeCHA API.

    Args:
        api_key: NopeCHA API key
        poll_interval: Seconds between status polls (default: 4.0)
        max_polls: Maximum polling attempts (default: 25)
        timeout_sec: Overall timeout in seconds (default: 120.0)
    """

    BASE_URL = "https://api.nopecha.com"

    def __init__(
        self,
        api_key: str,
        poll_interval: float = 4.0,
        max_polls: int = 25,
        timeout_sec: float = 120.0,
        proxy: dict = None,
    ):
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self.timeout_sec = timeout_sec
        self.proxy = proxy  # {"scheme": "http", "host": "1.2.3.4", "port": 8080, "username": "...", "password": "..."}

    # ── API Layer ────────────────────────────────────────────────

    def _api(self, path: str, method: str = "GET", body: dict = None):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {self.api_key}",
        }
        r = requests.request(
            method,
            f"{self.BASE_URL}{path}",
            headers=headers,
            json=body,
            timeout=30,
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"error": "invalid_json"}

    def get_credits(self) -> int:
        """Check remaining NopeCHA credits."""
        status, data = self._api("/v1/status")
        if status == 200:
            return data.get("credit", 0)
        return 0

    # ── Detection ────────────────────────────────────────────────

    def detect(self, page) -> list:
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
                    found.append({
                        "type": "hcaptcha",
                        "sitekey": sitekey,
                        "url": page_url,
                        "frame": frame,
                    })
                    seen_types.add("hcaptcha")

            elif "recaptcha" in furl and "/anchor" in furl and "recaptcha2" not in seen_types:
                sitekey = self._extract_sitekey(frame.url)
                if not sitekey:
                    sitekey = self._extract_dom_sitekey(page, "recaptcha")
                if sitekey:
                    found.append({
                        "type": "recaptcha2",
                        "sitekey": sitekey,
                        "url": page_url,
                        "frame": frame,
                    })
                    seen_types.add("recaptcha2")

            elif "challenges.cloudflare.com" in furl and "turnstile" not in seen_types:
                sitekey = self._extract_sitekey(frame.url)
                if not sitekey:
                    sitekey = self._extract_dom_sitekey(page, "turnstile")
                if sitekey:
                    found.append({
                        "type": "turnstile",
                        "sitekey": sitekey,
                        "url": page_url,
                        "frame": frame,
                    })
                    seen_types.add("turnstile")

        # Method 2: DOM fallback for each type — must match specific widget markers
        if "hcaptcha" not in seen_types:
            has_hcaptcha_widget = page.evaluate('''() => {
                return !!document.querySelector('.h-captcha, [data-hcaptcha-sitekey]') ||
                    document.querySelectorAll('iframe[src*="hcaptcha"]').length > 0;
            }''')
            if has_hcaptcha_widget:
                sk = self._extract_dom_sitekey(page, "hcaptcha")
                if sk:
                    found.append({"type": "hcaptcha", "sitekey": sk, "url": page_url})
                    seen_types.add("hcaptcha")

        if "recaptcha2" not in seen_types:
            has_recaptcha_widget = page.evaluate('''() => {
                return !!document.querySelector('.g-recaptcha, .g-recaptcha-response') ||
                    document.querySelectorAll('iframe[src*="recaptcha"]').length > 0;
            }''')
            if has_recaptcha_widget:
                sk = self._extract_dom_sitekey(page, "recaptcha")
                if sk:
                    # Distinguish v2 (visible widget) from v3 (invisible)
                    has_size = page.evaluate('''() => {
                        return !!document.querySelector('.g-recaptcha[data-size], [data-size]');
                    }''')
                    if has_size:
                        found.append({"type": "recaptcha2", "sitekey": sk, "url": page_url})
                    else:
                        found.append({"type": "recaptcha3", "sitekey": sk, "url": page_url})
                    seen_types.add("recaptcha2")

        if "recaptcha3" not in seen_types and "recaptcha2" not in seen_types:
            has_v3 = page.evaluate('''() => {
                // Must have recaptcha script with render param, AND no visible widget
                if (document.querySelector('.g-recaptcha, .g-recaptcha-response, iframe[src*="recaptcha"]')) return false;
                const scripts = document.querySelectorAll('script[src*="recaptcha"]');
                for (const s of scripts) {
                    if (s.src.includes('render=')) return true;
                }
                return false;
            }''')
            if has_v3:
                sk = self._extract_dom_sitekey(page, "recaptcha3")
                if sk:
                    found.append({"type": "recaptcha3", "sitekey": sk, "url": page_url})
                    seen_types.add("recaptcha3")

        if "turnstile" not in seen_types:
            has_turnstile_widget = page.evaluate('''() => {
                return !!document.querySelector('.cf-turnstile') ||
                    document.querySelectorAll('script[src*="turnstile"]').length > 0;
            }''')
            if has_turnstile_widget:
                sk = self._extract_dom_sitekey(page, "turnstile")
                if sk:
                    found.append({"type": "turnstile", "sitekey": sk, "url": page_url})

        return found

    def _extract_sitekey(self, url: str) -> Optional[str]:
        """Extract sitekey from iframe URL query params or fragment."""
        # reCAPTCHA style: ?k=<sitekey>
        match = re.search(r"[?&#]k=([A-Za-z0-9_-]+)", url)
        if match:
            return match.group(1)
        # hCaptcha/Turnstile style: sitekey=<sitekey>
        match = re.search(r"[?&#]sitekey=([A-Za-z0-9_-]+)", url)
        return match.group(1) if match else None

    def _extract_dom_sitekey(self, page, captcha_type: str) -> Optional[str]:
        """Extract sitekey from page DOM."""
        try:
            if captcha_type == "hcaptcha":
                return page.evaluate('''() => {
                    // data-sitekey on any element
                    let el = document.querySelector('[data-sitekey]');
                    if (el) return el.getAttribute('data-sitekey');
                    // iframe src
                    for (const f of document.querySelectorAll('iframe')) {
                        const m = f.src.match(/[?&#]sitekey=([A-Za-z0-9_-]+)/);
                        if (m) return m[1];
                    }
                    return null;
                }''')
            elif captcha_type == "recaptcha":
                return page.evaluate('''() => {
                    let el = document.querySelector('.g-recaptcha, [data-sitekey]');
                    if (el) return el.getAttribute('data-sitekey');
                    for (const f of document.querySelectorAll('iframe')) {
                        const m = f.src.match(/[?&#]k=([A-Za-z0-9_-]+)/);
                        if (m) return m[1];
                    }
                    return null;
                }''')
            elif captcha_type == "recaptcha3":
                return page.evaluate('''() => {
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
                }''')
            elif captcha_type == "turnstile":
                return page.evaluate('''() => {
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
                }''')
        except Exception:
            pass
        return None

    # ── Solving ──────────────────────────────────────────────────

    def solve(self, captcha_type: str, sitekey: str, url: str) -> CaptchaResult:
        """
        Submit a captcha to NopeCHA and poll for the solved token.

        Args:
            captcha_type: "hcaptcha", "recaptcha2", "recaptcha3", or "turnstile"
            sitekey: The site's captcha sitekey
            url: The page URL

        Returns:
            CaptchaResult with success=True and token on success.
        """
        start = time.time()

        ep = TOKEN_ENDPOINTS.get(captcha_type) or EXPERIMENTAL_ENDPOINTS.get(captcha_type)
        if not ep:
            return CaptchaResult(
                success=False,
                captcha_type=captcha_type,
                error=f"unsupported type: {captcha_type}. Supported: {list(TOKEN_ENDPOINTS.keys())}",
                elapsed_sec=time.time() - start,
            )

        # Submit job
        body = {"sitekey": sitekey, "url": url}
        if self.proxy:
            body["proxy"] = self.proxy

        status, data = self._api(ep, "POST", body)

        if status != 200 or not data.get("data"):
            return CaptchaResult(
                success=False,
                captcha_type=captcha_type,
                error=f"submit failed: {data}",
                elapsed_sec=time.time() - start,
            )

        job_id = data["data"]

        # Poll for result
        for i in range(self.max_polls):
            elapsed = time.time() - start
            if elapsed > self.timeout_sec:
                break

            time.sleep(self.poll_interval)
            status, result = self._api(f"{ep}?id={job_id}")

            err = result.get("error")
            if err == 14:  # Still in queue
                continue
            if err:
                return CaptchaResult(
                    success=False,
                    captcha_type=captcha_type,
                    error=f"error {err}: {result.get('message', '')}",
                    attempts=i + 1,
                    elapsed_sec=time.time() - start,
                )
            if result.get("data"):
                token = result["data"]
                if isinstance(token, list):
                    token = token[0]
                return CaptchaResult(
                    success=True,
                    captcha_type=captcha_type,
                    token=token,
                    attempts=i + 1,
                    elapsed_sec=time.time() - start,
                )

        return CaptchaResult(
            success=False,
            captcha_type=captcha_type,
            error="timeout",
            attempts=self.max_polls,
            elapsed_sec=time.time() - start,
        )

    # ── Injection ────────────────────────────────────────────────

    def inject(self, page, captcha_type: str, token: str) -> bool:
        """Inject solved token into the page's captcha callback."""
        try:
            if captcha_type == "hcaptcha":
                page.evaluate('''(t) => {
                    document.querySelectorAll(
                        "textarea[name='h-captcha-response'], textarea#g-recaptcha-response"
                    ).forEach(ta => ta.value = t);
                    if (typeof hcaptcha !== 'undefined') {
                        try { hcaptcha.execute(); } catch(e) {}
                    }
                }''', token)

            elif captcha_type == "recaptcha2":
                page.evaluate('''(t) => {
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
                }''', token)

            elif captcha_type == "recaptcha3":
                page.evaluate('''(t) => {
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
                }''', token)

            elif captcha_type == "turnstile":
                page.evaluate('''(t) => {
                    // Cloudflare Turnstile — inject into hidden input
                    document.querySelectorAll("input[name='cf-turnstile-response']")
                        .forEach(x => x.value = t);
                    document.querySelectorAll("textarea[name='cf-turnstile-response']")
                        .forEach(x => x.value = t);
                    // Try calling the turnstile callback
                    if (typeof turnstile !== 'undefined') {
                        try { turnstile.getResponse(); } catch(e) {}
                    }
                }''', token)

            return True
        except Exception:
            return False

    # ── Auto Flow ────────────────────────────────────────────────

    def auto_solve(self, page, click_checkbox: bool = True) -> list:
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

    def _click_checkbox(self, cap: dict):
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

    @staticmethod
    def supported_types() -> list:
        """Return list of supported captcha types (stable)."""
        return list(TOKEN_ENDPOINTS.keys())

    @staticmethod
    def experimental_types() -> list:
        """Return list of experimental captcha types (slow/unreliable)."""
        return list(EXPERIMENTAL_ENDPOINTS.keys())
