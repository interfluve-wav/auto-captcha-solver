"""pytest configuration and shared fixtures."""

import pytest
from auto_captcha_solver import CaptchaSolver, CaptchaResult

# Skip integration tests that hit real API unless explicitly requested
def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that call NopeCHA API (requires NOPECHA_API_KEY)",
    )

@pytest.fixture
def solver():
    """Return a CaptchaSolver with a dummy API key."""
    return CaptchaSolver(api_key="test-key-for-unit-tests")

@pytest.fixture
def sample_captcha_result():
    """A successful CaptchaResult for assertions."""
    return CaptchaResult(
        success=True,
        captcha_type="hcaptcha",
        token="sample-token-12345",
        attempts=3,
        elapsed_sec=12.5,
    )
