"""Draft365 adapter placeholder."""

from .provider_stub import ConfiguredProvider


class Draft365Client(ConfiguredProvider):
    source_name = "draft365"
    env_var = "DRAFT365_API_KEY"
    message = "Draft365 direct API is not configured. Use a documented API, licensed feed, or JSON import."
