"""Provider placeholder helpers for sources without configured public access."""

from __future__ import annotations

import os

from .http import ProviderError


class ConfiguredProvider:
    source_name = "provider"
    env_var = ""
    message = "Provider API is not configured."

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.getenv(self.env_var, "")

    def require_configured(self) -> None:
        if not self.api_key:
            raise ProviderError(self.message)

    def fetch(self):
        self.require_configured()
        raise ProviderError(f"{self.source_name} adapter is configured, but no official endpoint is implemented yet. Use JSON import or a licensed feed.")
