"""auto-captcha: Universal captcha solver for Playwright automation."""

from .solver import CaptchaResult, CaptchaSolver
from .wrapper import SmartPage, smart_page

__version__ = "0.1.4"
__all__ = ["CaptchaSolver", "CaptchaResult", "SmartPage", "smart_page"]
