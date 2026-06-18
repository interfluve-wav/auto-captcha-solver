"""auto-captcha: Universal captcha solver for Playwright automation."""

from .solver import CaptchaSolver, CaptchaResult
from .wrapper import SmartPage, smart_page

__version__ = "0.1.4"
__all__ = ["CaptchaSolver", "CaptchaResult", "SmartPage", "smart_page"]
