"""
SmartPage wrapper — makes Playwright pages auto-solve captchas transparently.

Usage:
    from auto_captcha import smart_page

    with smart_page(api_key="your-key") as page:
        page.goto("https://protected-site.com")
        page.fill("#email", "user@example.com")
        page.click("#submit")   # captcha auto-solved
"""

import time
from .solver import CaptchaSolver


class SmartPage:
    """
    Wraps a Playwright page to auto-solve captchas after navigation.

    Usage:
        from auto_captcha import SmartPage
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = SmartPage(browser.new_page(), api_key="your-key")
        page.goto("https://site.com")  # captchas auto-solved
    """

    def __init__(self, page, api_key: str, wait_after_load: float = 3.0):
        self._page = page
        self._solver = CaptchaSolver(api_key)
        self._wait = wait_after_load
        self._log = []

    def _solve_if_present(self):
        captchas = self._solver.detect(self._page)
        for cap in captchas:
            print(f"  [captcha] Detected {cap['type']} — solving...")
            token = self._solver.solve(cap["type"], cap["sitekey"], cap["url"])
            if token and token.success:
                self._solver.inject(self._page, cap["type"], token.token)
                print(f"  [captcha] Solved! ({len(token.token)} chars)")
                self._log.append({"type": cap["type"], "status": "solved", "url": self._page.url})
            else:
                print(f"  [captcha] Failed to solve {cap['type']}")
                self._log.append({"type": cap["type"], "status": "failed", "url": self._page.url})

    # -- Auto-solve wrappers --

    def goto(self, url, **kwargs):
        result = self._page.goto(url, **kwargs)
        time.sleep(self._wait)
        self._solve_if_present()
        return result

    def click(self, selector, **kwargs):
        self._page.click(selector, **kwargs)
        time.sleep(self._wait)
        self._solve_if_present()

    def submit(self, selector="form"):
        self._page.evaluate(f'''() => {{
            const form = document.querySelector("{selector}");
            if (form) form.submit();
        }}''')
        time.sleep(self._wait)
        self._solve_if_present()

    # -- Pass-through methods --

    def fill(self, selector, value, **kwargs):
        return self._page.fill(selector, value, **kwargs)

    def type(self, selector, text, **kwargs):
        return self._page.type(selector, text, **kwargs)

    def select_option(self, selector, value, **kwargs):
        return self._page.select_option(selector, value, **kwargs)

    def check(self, selector, **kwargs):
        return self._page.check(selector, **kwargs)

    def text_content(self, selector, **kwargs):
        return self._page.text_content(selector, **kwargs)

    def screenshot(self, **kwargs):
        return self._page.screenshot(**kwargs)

    def evaluate(self, expr, *args, **kwargs):
        return self._page.evaluate(expr, *args, **kwargs)

    def locator(self, selector):
        return self._page.locator(selector)

    def wait_for_selector(self, selector, **kwargs):
        return self._page.wait_for_selector(selector, **kwargs)

    def wait_for_load_state(self, state="load", **kwargs):
        return self._page.wait_for_load_state(state, **kwargs)

    @property
    def url(self):
        return self._page.url

    @property
    def title(self):
        return self._page.title()

    @property
    def captcha_log(self):
        return self._log

    @property
    def raw(self):
        """Access the underlying Playwright page directly."""
        return self._page


def smart_page(api_key: str, headless: bool = True, **launch_kwargs):
    """
    Context manager that gives you a ready-to-use SmartPage.

    Usage:
        with smart_page(api_key="your-key") as page:
            page.goto("https://example.com")
            page.fill("#input", "value")
            page.click("#submit")
    """
    class _Ctx:
        def __init__(self):
            self._pw = None
            self._browser = None
            self.page = None

        def __enter__(self):
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=headless, **launch_kwargs)
            raw_page = self._browser.new_page()
            self.page = SmartPage(raw_page, api_key=api_key)
            return self.page

        def __exit__(self, *args):
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()

    return _Ctx()
