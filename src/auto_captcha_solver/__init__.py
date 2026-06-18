"""auto-captcha: Universal captcha solver for Playwright automation."""

from .solver import CaptchaSolver
from .types import CaptchaResult
from .wrapper import SmartPage, smart_page

__version__ = "0.1.5"
__all__ = ["CaptchaSolver", "CaptchaResult", "SmartPage", "smart_page"]
