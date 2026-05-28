"""Caesars adapter placeholder."""

from .provider_stub import ConfiguredProvider


class CaesarsClient(ConfiguredProvider):
    source_name = "caesars"
    env_var = "CAESARS_API_KEY"
    message = "Caesars direct API is not configured. Use an approved odds provider, licensed feed, or JSON import."
