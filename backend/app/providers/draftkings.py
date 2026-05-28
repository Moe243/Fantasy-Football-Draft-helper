"""DraftKings adapter placeholder."""

from .provider_stub import ConfiguredProvider


class DraftKingsClient(ConfiguredProvider):
    source_name = "draftkings"
    env_var = "DRAFTKINGS_API_KEY"
    message = "DraftKings direct API is not configured. Use an approved odds provider, licensed feed, or JSON import."
