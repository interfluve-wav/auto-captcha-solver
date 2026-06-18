"""Shared captcha solver types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CaptchaInfo = dict[str, Any]


@dataclass
class CaptchaResult:
    """Result of a captcha solve attempt."""

    success: bool
    captcha_type: str = ""
    token: str = ""
    error: str = ""
    attempts: int = 0
    elapsed_sec: float = 0.0


def sanitize_detect_results(captchas: list[CaptchaInfo]) -> list[CaptchaInfo]:
    """Strip non-JSON-serializable fields (e.g. Playwright frames) from detect results."""
    return [{k: v for k, v in cap.items() if k != "frame"} for cap in captchas]
