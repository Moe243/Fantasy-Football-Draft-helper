"""ESPN adapter placeholder.

ESPN fantasy football does not have a stable public official fantasy API in this
MVP. Use JSON imports or add an authenticated/licensed adapter explicitly.
"""

from .provider_stub import ConfiguredProvider


class ESPNClient(ConfiguredProvider):
    source_name = "espn"
    env_var = "ESPN_API_KEY"
    message = "ESPN direct API is not configured. Use JSON import, an approved provider, or a licensed/authenticated ESPN adapter."
