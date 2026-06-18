"""CaptchaAI provider tests."""

from auto_captcha_solver import CaptchaSolver
from auto_captcha_solver.providers.captchaai import CaptchaAIProvider


class DummyResponse:
    def __init__(self, text: str = "", json_data: dict | None = None):
        self.text = text
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def test_captchaai_supported_types():
    assert CaptchaAIProvider.supported_types() == ["recaptcha2", "recaptcha3", "turnstile"]


def test_captchaai_rejects_hcaptcha():
    provider = CaptchaAIProvider(api_key="test")
    result = provider.solve(
        "hcaptcha",
        "sitekey",
        "https://example.com",
        poll_interval=0.01,
        max_polls=1,
        timeout_sec=1,
    )
    assert not result.success
    assert "not supported" in result.error.lower()


def test_captchaai_solve_recaptcha2(monkeypatch):
    calls: list[tuple[str, str]] = []

    def mock_post(url, data=None, timeout=30):
        calls.append(("POST", url))
        return DummyResponse(json_data={"status": 1, "request": "task-123"})

    def mock_get(url, params=None, timeout=30):
        calls.append(("GET", url))
        return DummyResponse(json_data={"status": 1, "request": "token-abc"})

    monkeypatch.setattr("auto_captcha_solver.providers.captchaai.requests.post", mock_post)
    monkeypatch.setattr("auto_captcha_solver.providers.captchaai.requests.get", mock_get)

    provider = CaptchaAIProvider(api_key="key")
    result = provider.solve(
        "recaptcha2",
        "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI",
        "https://example.com",
        poll_interval=0.01,
        max_polls=3,
        timeout_sec=5,
    )

    assert result.success
    assert result.token == "token-abc"
    assert calls[0][1].endswith("/in.php")


def test_captchaai_get_credits(monkeypatch):
    monkeypatch.setattr(
        "auto_captcha_solver.providers.captchaai.requests.get",
        lambda *args, **kwargs: DummyResponse(text="42.5"),
    )
    assert CaptchaAIProvider(api_key="k").get_credits() == 42


def test_solver_accepts_captchaai_provider():
    solver = CaptchaSolver(api_key="k", provider="captchaai")
    assert solver.provider == "captchaai"
    assert solver.supported_types() == ["recaptcha2", "recaptcha3", "turnstile"]
