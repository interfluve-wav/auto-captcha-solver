"""
Core captcha solver — detects and solves hCaptcha + reCAPTCHA v2 via NopeCHA API.

Usage:
    from auto_captcha import CaptchaSolver

    solver = CaptchaSolver(api_key="your-key")
    results = solver.auto_solve(page)
"""

import requests
import re
import time
from dataclasses import dataclass, field
from typing import Optional


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
    Supports hCaptcha and reCAPTCHA v2 via NopeCHA API.

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
    ):
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self.timeout_sec = timeout_sec

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

        Returns list of dicts: {type, sitekey, url, frame}
        """
        found = []
        page_url = page.url
        seen_types = set()

        # Method 1: Check Playwright frames
        for frame in page.frames:
            furl = frame.url.lower()

            if "hcaptcha.com" in furl and "hcaptcha" not in seen_types:
                sitekey = self._extract_sitekey(frame.url)
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
                if sitekey:
                    found.append({
                        "type": "recaptcha2",
                        "sitekey": sitekey,
                        "url": page_url,
                        "frame": frame,
                    })
                    seen_types.add("recaptcha2")

        # Method 2: Fallback — check DOM directly
        if "hcaptcha" not in seen_types:
            dom = page.evaluate('''() => {
                const el = document.querySelector('[data-sitekey]');
                const hc = document.querySelector('.h-captcha');
                const iframes = document.querySelectorAll('iframe[src*="hcaptcha"]');
                return {
                    sitekey: el ? el.getAttribute('data-sitekey') : null,
                    hasWidget: !!hc || iframes.length > 0
                };
            }''')
            if dom.get("sitekey") and dom.get("hasWidget"):
                found.append({"type": "hcaptcha", "sitekey": dom["sitekey"], "url": page_url})

        if "recaptcha2" not in seen_types:
            dom = page.evaluate('''() => {
                const el = document.querySelector('.g-recaptcha');
                const iframes = document.querySelectorAll('iframe[src*="recaptcha"]');
                return {
                    sitekey: el ? el.getAttribute('data-sitekey') : null,
                    hasWidget: !!el || iframes.length > 0
                };
            }''')
            if dom.get("sitekey") and dom.get("hasWidget"):
                found.append({"type": "recaptcha2", "sitekey": dom["sitekey"], "url": page_url})

        return found

    def _extract_sitekey(self, url: str) -> Optional[str]:
        match = re.search(r"[?&]k=([A-Za-z0-9_-]+)", url)
        return match.group(1) if match else None

    # ── Solving ──────────────────────────────────────────────────

    def solve(self, captcha_type: str, sitekey: str, url: str) -> CaptchaResult:
        """
        Submit a captcha to NopeCHA and poll for the solved token.

        Args:
            captcha_type: "hcaptcha" or "recaptcha2"
            sitekey: The site's captcha sitekey
            url: The page URL

        Returns:
            CaptchaResult with success=True and token on success.
        """
        start = time.time()
        ep = "hcaptcha" if captcha_type == "hcaptcha" else "recaptcha2"

        # Submit job
        status, data = self._api(f"/v1/token/{ep}", "POST", {"sitekey": sitekey, "url": url})

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
            status, result = self._api(f"/v1/token/{ep}?id={job_id}")

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
            else:
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
        except Exception:
            pass
