"""Captcha solve providers."""

from __future__ import annotations

from .base import CaptchaProvider
from .captchaai import CaptchaAIProvider
from .nopecha import EXPERIMENTAL_ENDPOINTS, TOKEN_ENDPOINTS, NopechaProvider

PROVIDERS: dict[str, type[CaptchaProvider]] = {
    "nopecha": NopechaProvider,
    "captchaai": CaptchaAIProvider,
}


def get_provider(name: str, api_key: str) -> CaptchaProvider:
    """Instantiate a provider by name."""
    provider_cls = PROVIDERS.get(name.lower())
    if provider_cls is None:
        supported = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unknown provider '{name}'. Choose from: {supported}")
    return provider_cls(api_key)


def resolve_api_key(provider: str, explicit_key: str = "") -> str:
    """Resolve API key from CLI arg or provider-specific env var."""
    import os

    if explicit_key:
        return explicit_key
    env_vars = {
        "nopecha": "NOPECHA_API_KEY",
        "captchaai": "CAPTCHAAI_API_KEY",
    }
    env_name = env_vars.get(provider.lower(), "NOPECHA_API_KEY")
    return os.environ.get(env_name, "")


__all__ = [
    "CaptchaAIProvider",
    "CaptchaProvider",
    "EXPERIMENTAL_ENDPOINTS",
    "NopechaProvider",
    "PROVIDERS",
    "TOKEN_ENDPOINTS",
    "get_provider",
    "resolve_api_key",
]
