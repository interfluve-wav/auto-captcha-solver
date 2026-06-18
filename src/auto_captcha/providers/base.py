"""Captcha solve provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..types import CaptchaResult


class CaptchaProvider(ABC):
    """Backend that submits captchas and returns solved tokens."""

    name: str = "base"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    @abstractmethod
    def get_credits(self) -> int:
        """Return remaining account balance/credits."""

    @abstractmethod
    def solve(
        self,
        captcha_type: str,
        sitekey: str,
        url: str,
        *,
        poll_interval: float,
        max_polls: int,
        timeout_sec: float,
        proxy: dict[str, Any] | None = None,
    ) -> CaptchaResult:
        """Solve a captcha and return the token."""

    @classmethod
    @abstractmethod
    def supported_types(cls) -> list[str]:
        """Captcha types with stable support on this provider."""

    @classmethod
    @abstractmethod
    def experimental_types(cls) -> list[str]:
        """Captcha types that may be slow or unreliable on this provider."""
