"""
SmartPage wrapper — makes Playwright pages auto-solve captchas transparently.

Usage:
    from auto_captcha import smart_page

    with smart_page(api_key="your-key") as page:
        page.goto("https://protected-site.com")
        page.fill("#email", "user@example.com")
        page.click("#submit")   # captcha auto-solved
"""

from __future__ import annotations

import time
from typing import Any, cast

from .solver import CaptchaSolver

CaptchaLogEntry = dict[str, str]


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

    def __init__(
        self,
        page: Any,
        api_key: str,
        wait_after_load: float = 3.0,
        proxy: dict[str, Any] | None = None,
    ):
        self._page = page
        self._solver = CaptchaSolver(api_key, proxy=proxy)
        self._wait = wait_after_load
        self._log: list[CaptchaLogEntry] = []

    def _solve_if_present(self) -> None:
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

    def goto(self, url: str, **kwargs: Any) -> Any:
        result = self._page.goto(url, **kwargs)
        time.sleep(self._wait)
        self._solve_if_present()
        return result

    def click(self, selector: str, **kwargs: Any) -> None:
        self._page.click(selector, **kwargs)
        time.sleep(self._wait)
        self._solve_if_present()

    def submit(self, selector: str = "form") -> None:
        self._page.evaluate(f'''() => {{
            const form = document.querySelector("{selector}");
            if (form) form.submit();
        }}''')
        time.sleep(self._wait)
        self._solve_if_present()

    # -- Pass-through methods --

    def fill(self, selector: str, value: str, **kwargs: Any) -> Any:
        return self._page.fill(selector, value, **kwargs)

    def type(self, selector: str, text: str, **kwargs: Any) -> Any:
        return self._page.type(selector, text, **kwargs)

    def select_option(self, selector: str, value: str, **kwargs: Any) -> Any:
        return self._page.select_option(selector, value, **kwargs)

    def check(self, selector: str, **kwargs: Any) -> Any:
        return self._page.check(selector, **kwargs)

    def text_content(self, selector: str, **kwargs: Any) -> Any:
        return self._page.text_content(selector, **kwargs)

    def screenshot(self, **kwargs: Any) -> Any:
        return self._page.screenshot(**kwargs)

    def evaluate(self, expr: str, *args: Any, **kwargs: Any) -> Any:
        return self._page.evaluate(expr, *args, **kwargs)

    def locator(self, selector: str) -> Any:
        return self._page.locator(selector)

    def wait_for_selector(self, selector: str, **kwargs: Any) -> Any:
        return self._page.wait_for_selector(selector, **kwargs)

    def wait_for_load_state(self, state: str = "load", **kwargs: Any) -> Any:
        return self._page.wait_for_load_state(state, **kwargs)

    @property
    def url(self) -> str:
        return cast(str, self._page.url)

    @property
    def title(self) -> str:
        return cast(str, self._page.title())

    @property
    def captcha_log(self) -> list[CaptchaLogEntry]:
        return self._log

    @property
    def raw(self) -> Any:
        """Access the underlying Playwright page directly."""
        return self._page


def smart_page(
    api_key: str,
    headless: bool = True,
    proxy: dict[str, Any] | None = None,
    **launch_kwargs: Any,
) -> _SmartPageContext:
    """
    Context manager that gives you a ready-to-use SmartPage.

    Usage:
        with smart_page(api_key="your-key") as page:
            page.goto("https://example.com")
            page.fill("#input", "value")
            page.click("#submit")

    Pass ``proxy`` for NopeCHA solve requests. For browser traffic, pass Playwright's
    ``proxy`` via launch kwargs so both paths share the same sticky session, e.g.
    ``smart_page(api_key="...", proxy=nopecha_proxy, proxy=browser_proxy)`` is wrong —
    use ``smart_page(api_key="...", proxy=nopecha_proxy, **{"proxy": browser_proxy})``.
    """
    return _SmartPageContext(
        api_key=api_key, headless=headless, proxy=proxy, launch_kwargs=launch_kwargs
    )


class _SmartPageContext:
    def __init__(
        self,
        api_key: str,
        headless: bool,
        proxy: dict[str, Any] | None,
        launch_kwargs: dict[str, Any],
    ):
        self._api_key = api_key
        self._headless = headless
        self._proxy = proxy
        self._launch_kwargs = launch_kwargs
        self._pw: Any = None
        self._browser: Any = None
        self.page: SmartPage | None = None

    def __enter__(self) -> SmartPage:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless, **self._launch_kwargs)
        raw_page = self._browser.new_page()
        self.page = SmartPage(raw_page, api_key=self._api_key, proxy=self._proxy)
        return self.page

    def __exit__(self, *args: Any) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
