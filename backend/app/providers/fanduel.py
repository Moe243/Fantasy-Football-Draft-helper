"""FanDuel adapter placeholder."""

from .provider_stub import ConfiguredProvider


class FanDuelClient(ConfiguredProvider):
    source_name = "fanduel"
    env_var = "FANDUEL_API_KEY"
    message = "FanDuel direct API is not configured. Use an approved odds provider, licensed feed, or JSON import."
