"""NopeCHA Token API provider."""

from __future__ import annotations

import time
from typing import Any

import requests

from ..types import CaptchaResult
from .base import CaptchaProvider

TOKEN_ENDPOINTS = {
    "hcaptcha": "/v1/token/hcaptcha",
    "recaptcha2": "/v1/token/recaptcha2",
    "recaptcha3": "/v1/token/recaptcha3",
}

# Experimental — NopeCHA queue extremely slow (5-10+ min), needs proxy
EXPERIMENTAL_ENDPOINTS = {
    "turnstile": "/v1/token/turnstile",
}


class NopechaProvider(CaptchaProvider):
    name = "nopecha"
    BASE_URL = "https://api.nopecha.com"

    def __init__(self, api_key: str):
        super().__init__(api_key)

    def _api(
        self, path: str, method: str = "GET", body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {self.api_key}",
        }
        response = requests.request(
            method,
            f"{self.BASE_URL}{path}",
            headers=headers,
            json=body,
            timeout=30,
        )
        try:
            return response.status_code, response.json()
        except Exception:
            return response.status_code, {"error": "invalid_json"}

    def get_credits(self) -> int:
        status, data = self._api("/v1/status")
        if status == 200:
            return int(data.get("credit", 0))
        return 0

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
        endpoint = TOKEN_ENDPOINTS.get(captcha_type) or EXPERIMENTAL_ENDPOINTS.get(captcha_type)
        if not endpoint:
            supported = list(TOKEN_ENDPOINTS.keys()) + list(EXPERIMENTAL_ENDPOINTS.keys())
            return CaptchaResult(
                success=False,
                captcha_type=captcha_type,
                error=f"unsupported type: {captcha_type}. Supported: {supported}",
                elapsed_sec=time.time() - start,
            )

        body: dict[str, Any] = {"sitekey": sitekey, "url": url}
        if proxy:
            body["proxy"] = proxy

        status, data = self._api(endpoint, "POST", body)
        if status != 200 or not data.get("data"):
            return CaptchaResult(
                success=False,
                captcha_type=captcha_type,
                error=f"submit failed: {data}",
                elapsed_sec=time.time() - start,
            )

        job_id = data["data"]
        for attempt in range(max_polls):
            if time.time() - start > timeout_sec:
                break

            time.sleep(poll_interval)
            status, result = self._api(f"{endpoint}?id={job_id}")

            err = result.get("error")
            if err == 14:
                continue
            if err:
                return CaptchaResult(
                    success=False,
                    captcha_type=captcha_type,
                    error=f"error {err}: {result.get('message', '')}",
                    attempts=attempt + 1,
                    elapsed_sec=time.time() - start,
                )
            if result.get("data"):
                token = result["data"]
                if isinstance(token, list):
                    token = token[0]
                return CaptchaResult(
                    success=True,
                    captcha_type=captcha_type,
                    token=str(token),
                    attempts=attempt + 1,
                    elapsed_sec=time.time() - start,
                )

        return CaptchaResult(
            success=False,
            captcha_type=captcha_type,
            error="timeout",
            attempts=max_polls,
            elapsed_sec=time.time() - start,
        )

    @classmethod
    def supported_types(cls) -> list[str]:
        return list(TOKEN_ENDPOINTS.keys())

    @classmethod
    def experimental_types(cls) -> list[str]:
        return list(EXPERIMENTAL_ENDPOINTS.keys())
