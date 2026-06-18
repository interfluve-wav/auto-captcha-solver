"""CaptchaAI provider (2Captcha-compatible in.php / res.php API)."""

from __future__ import annotations

import time
from typing import Any

import requests

from ..types import CaptchaResult
from .base import CaptchaProvider

BASE_URL = "https://ocr.captchaai.com"

# CaptchaAI does not support hCaptcha yet (see https://captchaai.com/lp/switch-from-2captcha)
STABLE_METHODS = {
    "recaptcha2": "userrecaptcha",
    "recaptcha3": "userrecaptcha",
    "turnstile": "turnstile",
}

EXPERIMENTAL_METHODS: dict[str, str] = {}


def _proxy_fields(proxy: dict[str, Any] | None) -> dict[str, str]:
    if not proxy:
        return {}
    scheme = str(proxy.get("scheme", "http")).upper()
    proxytype = {
        "HTTP": "HTTP",
        "HTTPS": "HTTPS",
        "SOCKS4": "SOCKS4",
        "SOCKS5": "SOCKS5",
    }.get(scheme, "HTTP")
    host = str(proxy["host"])
    port = str(proxy["port"])
    username = str(proxy.get("username", ""))
    password = str(proxy.get("password", ""))
    return {
        "proxy": f"{host}:{port}:{username}:{password}",
        "proxytype": proxytype,
    }


class CaptchaAIProvider(CaptchaProvider):
    """2Captcha-compatible provider backed by CaptchaAI."""

    name = "captchaai"

    def __init__(self, api_key: str):
        super().__init__(api_key)

    def get_credits(self) -> int:
        response = requests.get(
            f"{BASE_URL}/res.php",
            params={"key": self.api_key, "action": "getbalance"},
            timeout=30,
        )
        try:
            return int(float(response.text.strip()))
        except ValueError:
            return 0

    def _submit(self, payload: dict[str, Any]) -> tuple[bool, str]:
        data = {"key": self.api_key, "json": 1, **payload}
        response = requests.post(f"{BASE_URL}/in.php", data=data, timeout=30)
        try:
            body = response.json()
        except Exception:
            return False, f"invalid response: {response.text[:200]}"

        if body.get("status") == 1:
            return True, str(body["request"])
        return False, str(body.get("request", body))

    def _poll(self, task_id: str, poll_interval: float, max_polls: int) -> tuple[bool, str]:
        for _ in range(max_polls):
            response = requests.get(
                f"{BASE_URL}/res.php",
                params={
                    "key": self.api_key,
                    "action": "get",
                    "id": task_id,
                    "json": "1",
                },
                timeout=30,
            )
            try:
                body = response.json()
            except Exception:
                return False, f"invalid response: {response.text[:200]}"

            token = body.get("request")
            if token == "CAPCHA_NOT_READY":
                time.sleep(poll_interval)
                continue
            if body.get("status") == 1 and token:
                return True, str(token)
            return False, str(token or body)

        return False, "timeout"

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
        start = time.time()
        method = STABLE_METHODS.get(captcha_type) or EXPERIMENTAL_METHODS.get(captcha_type)
        if not method:
            if captcha_type == "hcaptcha":
                return CaptchaResult(
                    success=False,
                    captcha_type=captcha_type,
                    error="hcaptcha is not supported by CaptchaAI; use provider='nopecha'",
                    elapsed_sec=time.time() - start,
                )
            supported = list(STABLE_METHODS.keys()) + list(EXPERIMENTAL_METHODS.keys())
            return CaptchaResult(
                success=False,
                captcha_type=captcha_type,
                error=f"unsupported type: {captcha_type}. Supported: {supported}",
                elapsed_sec=time.time() - start,
            )

        payload: dict[str, Any] = {
            "method": method,
            "pageurl": url,
        }
        if captcha_type in {"recaptcha2", "recaptcha3"}:
            payload["googlekey"] = sitekey
        else:
            payload["sitekey"] = sitekey

        if captcha_type == "recaptcha3":
            payload["version"] = "v3"
            payload["action"] = "verify"

        payload.update(_proxy_fields(proxy))

        ok, task_or_error = self._submit(payload)
        if not ok:
            return CaptchaResult(
                success=False,
                captcha_type=captcha_type,
                error=f"submit failed: {task_or_error}",
                elapsed_sec=time.time() - start,
            )

        polls = min(max_polls, max(1, int(timeout_sec / poll_interval)))
        ok, token_or_error = self._poll(task_or_error, poll_interval, polls)
        if ok:
            return CaptchaResult(
                success=True,
                captcha_type=captcha_type,
                token=token_or_error,
                attempts=polls,
                elapsed_sec=time.time() - start,
            )

        return CaptchaResult(
            success=False,
            captcha_type=captcha_type,
            error=token_or_error,
            attempts=polls,
            elapsed_sec=time.time() - start,
        )

    @classmethod
    def supported_types(cls) -> list[str]:
        return list(STABLE_METHODS.keys())

    @classmethod
    def experimental_types(cls) -> list[str]:
        return list(EXPERIMENTAL_METHODS.keys())
